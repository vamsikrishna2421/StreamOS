"""HLS relay with upstream session sharing and segment coalescing.

Why this design
---------------
A MAG/Stalker-style provider counts *connections to the source*, not
devices in your home. If five TVs each open the upstream stream, the
provider sees five sessions and may enforce its concurrency limit. The hub
opens the upstream **once per source** and fans the already-fetched media
out to every local device.

Two mechanisms make that true and measurable:

1. Per-(source, segment) async locks coalesce simultaneous misses, so the
   hub never fetches the same segment upstream twice at once.
2. A short-TTL segment + playlist cache absorbs the steady-state request
   rate, so upstream fetches track the *number of distinct segments the
   channel produces*, independent of how many devices are watching.

The "upstream session" is the unit the provider's concurrency policy acts
on. The hub keeps at most ``max_upstream_sessions`` open globally and at
most ``source.max_sessions`` per source, sharing or rejecting otherwise.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from .config import Settings
from .metrics import METRICS


@dataclass
class _CacheEntry:
    data: bytes
    content_type: str
    fetched_at: float


@dataclass
class UpstreamSession:
    """One active relay of one source. Shared by all local viewers of it."""
    source_id: str
    upstream_url: str
    opened_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    subscribers: set[str] = field(default_factory=set)  # downstream session ids

    @property
    def base(self) -> str:
        # everything up to and including the last '/'
        return self.upstream_url.rsplit("/", 1)[0] + "/"


class RelayError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Relay:
    def __init__(self, settings: Settings):
        self.s = settings
        self._sessions: dict[str, UpstreamSession] = {}
        self._seg_cache: dict[str, _CacheEntry] = {}      # key: sid/name
        self._pl_cache: dict[str, _CacheEntry] = {}       # key: sid
        self._seg_locks: dict[str, asyncio.Lock] = {}
        self._state_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            timeout=settings.upstream_timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=32),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def flush(self) -> dict:
        """Drop all caches and sessions. Operator 'clear cache' action; also
        gives experiments a cold start between runs."""
        async with self._state_lock:
            n_sessions = len(self._sessions)
            n_seg = len(self._seg_cache)
            self._sessions.clear()
            self._seg_cache.clear()
            self._pl_cache.clear()
            self._seg_locks.clear()
        return {"cleared_sessions": n_sessions, "cleared_segments": n_seg}

    # --- session accounting ---------------------------------------------
    def upstream_count(self) -> int:
        return len(self._sessions)

    def sessions_view(self) -> list[dict]:
        now = time.time()
        return [
            {
                "source_id": s.source_id,
                "subscribers": len(s.subscribers),
                "age_s": round(now - s.opened_at, 1),
                "idle_s": round(now - s.last_activity, 1),
            }
            for s in self._sessions.values()
        ]

    async def acquire(self, source: dict, session_id: str) -> UpstreamSession:
        """Attach a downstream viewer to a source, opening an upstream
        session if needed. Enforces per-source and global caps. Raises
        RelayError(409) when no capacity and no shareable session exists.
        """
        sid = source["id"]
        async with self._state_lock:
            existing = self._sessions.get(sid)
            if existing is not None:
                if not source["shareable"] and existing.subscribers:
                    raise RelayError(409, "source not shareable; already in use")
                existing.subscribers.add(session_id)
                existing.last_activity = time.time()
                return existing

            # Need a new upstream session. Check caps.
            per_source_open = 1 if sid in self._sessions else 0
            if per_source_open >= source["max_sessions"]:
                raise RelayError(409, "per-source session limit reached")
            if len(self._sessions) >= self.s.max_upstream_sessions:
                raise RelayError(
                    503,
                    f"global upstream session limit "
                    f"({self.s.max_upstream_sessions}) reached",
                )
            sess = UpstreamSession(source_id=sid, upstream_url=source["upstream_url"])
            sess.subscribers.add(session_id)
            self._sessions[sid] = sess
            return sess

    async def release(self, source_id: str, session_id: str) -> None:
        async with self._state_lock:
            sess = self._sessions.get(source_id)
            if sess is None:
                return
            sess.subscribers.discard(session_id)
            # Teardown happens in the reaper to allow brief gaps / zapping.

    async def reap(self) -> int:
        """Drop idle upstream sessions and stale cache entries. Returns the
        number of sessions torn down. Called periodically by the app."""
        now = time.time()
        dropped = 0
        async with self._state_lock:
            for sid in list(self._sessions):
                sess = self._sessions[sid]
                idle = now - sess.last_activity
                if not sess.subscribers and idle > self.s.session_idle_timeout:
                    del self._sessions[sid]
                    dropped += 1
        # prune caches
        for store, ttl in ((self._seg_cache, self.s.segment_ttl),
                            (self._pl_cache, self.s.playlist_ttl * 4)):
            for k in list(store):
                if now - store[k].fetched_at > ttl:
                    del store[k]
        return dropped

    # --- media fetching --------------------------------------------------
    async def get_playlist(self, source: dict, session_id: str) -> tuple[bytes, str]:
        sid = source["id"]
        sess = self._sessions.get(sid)
        if sess is None:
            raise RelayError(409, "no active session; call acquire first")
        sess.last_activity = time.time()

        cached = self._pl_cache.get(sid)
        if cached and (time.time() - cached.fetched_at) < self.s.playlist_ttl:
            METRICS.add("cache_hits", source=sid)
            return cached.data, cached.content_type

        METRICS.add("cache_misses", source=sid)
        try:
            resp = await self._client.get(sess.upstream_url)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001 - surface upstream failure
            METRICS.add("errors", source=sid)
            raise RelayError(502, f"upstream playlist fetch failed: {e}") from e

        METRICS.add("upstream_playlist_fetches", source=sid)
        METRICS.add("upstream_bytes", len(resp.content), source=sid)
        rewritten = self._rewrite_playlist(resp.text)
        entry = _CacheEntry(rewritten, "application/vnd.apple.mpegurl", time.time())
        self._pl_cache[sid] = entry
        return entry.data, entry.content_type

    # tags that carry a URI="..." attribute pointing at a fetchable resource
    _URI_TAGS = ("#EXT-X-MAP:", "#EXT-X-KEY:", "#EXT-X-MEDIA:",
                 "#EXT-X-I-FRAME-STREAM-INF:")

    @classmethod
    def _rewrite_playlist(cls, text: str) -> bytes:
        """Rewrite media URIs to their basename so the client fetches them
        back through the hub at /live/{sid}/{name}. Segment lines and the
        URI="" attribute of MAP/KEY/MEDIA tags are both handled; other tags
        pass through untouched."""
        import re

        def _basename_uri(m: "re.Match") -> str:
            return f'URI="{m.group(1).rsplit("/", 1)[-1]}"'

        out: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                out.append(line)
                continue
            if stripped.startswith("#"):
                if any(stripped.startswith(t) for t in cls._URI_TAGS):
                    stripped = re.sub(r'URI="([^"]+)"', _basename_uri, stripped)
                out.append(stripped)
                continue
            out.append(stripped.rsplit("/", 1)[-1])
        return ("\n".join(out) + "\n").encode()

    async def get_segment(self, source: dict, name: str,
                          session_id: str) -> tuple[bytes, str]:
        sid = source["id"]
        sess = self._sessions.get(sid)
        if sess is None:
            raise RelayError(409, "no active session; call acquire first")
        sess.last_activity = time.time()

        key = f"{sid}/{name}"
        cached = self._seg_cache.get(key)
        if cached and (time.time() - cached.fetched_at) < self.s.segment_ttl:
            METRICS.add("cache_hits", source=sid)
            METRICS.add("downstream_segment_serves", source=sid)
            METRICS.add("downstream_bytes", len(cached.data), source=sid)
            return cached.data, cached.content_type

        # Coalesce concurrent misses for the same segment into one fetch.
        lock = self._seg_locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._seg_cache.get(key)
            if cached and (time.time() - cached.fetched_at) < self.s.segment_ttl:
                METRICS.add("cache_hits", source=sid)
                METRICS.add("downstream_segment_serves", source=sid)
                METRICS.add("downstream_bytes", len(cached.data), source=sid)
                return cached.data, cached.content_type

            METRICS.add("cache_misses", source=sid)
            upstream = urljoin(sess.base, name)
            try:
                resp = await self._client.get(upstream)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                METRICS.add("errors", source=sid)
                raise RelayError(502, f"upstream segment fetch failed: {e}") from e

            METRICS.add("upstream_segment_fetches", source=sid)
            METRICS.add("upstream_bytes", len(resp.content), source=sid)
            ctype = resp.headers.get("content-type", "video/MP2T")
            entry = _CacheEntry(resp.content, ctype, time.time())
            self._seg_cache[key] = entry

        METRICS.add("downstream_segment_serves", source=sid)
        METRICS.add("downstream_bytes", len(entry.data), source=sid)
        return entry.data, entry.content_type
