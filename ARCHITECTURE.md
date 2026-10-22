# StreamOS Architecture

## 1. The problem, stated precisely

A household has one or more **authorized** media sources. Some sources permit
only a limited number of simultaneous upstream connections. The household has
several screens. We want:

- **Shared viewing** — many screens on the same programme should cost ~one
  upstream connection, where redistribution is permitted.
- **Independent viewing** — different screens on different programmes, as far
  as the available source capacity allows.
- **Hybrid** — a mix, with the hub managing finite capacity intelligently.

The constraint the design is built around: *the provider counts upstream
connections, not living-room devices.* Everything follows from minimizing and
accounting for upstream connections.

## 2. Architectures considered

| | Approach | Verdict |
|---|---|---|
| A | Direct playback — each device connects to the source | Baseline. Upstream = devices. Rejected as the default: wastes the one thing that is scarce. Still supported per-source when sharing is not permitted. |
| B | **Local streaming relay** — one upstream per source, fanned out | **Chosen core.** Upstream = distinct sources, not devices. Measured 1−1/N reduction. |
| C | Hybrid source manager — relay *or* direct per source policy | **Chosen layer on top of B.** `shareable` + `max_sessions` per source select behaviour. |
| D | Native-player ecosystem (separate AndroidTV/iOS, shared backend) | Adopted for the *clients*; backend is B/C regardless. |
| E | Cross-platform client with native playback hooks | **Chosen for the first client**: the web client runs on every target today, including a TV browser, and was the only client buildable and testable in this environment. Native clients (D) are scaffolds. |
| F | *Innovative alternative* — see below | Partially adopted. |

### Architecture F — what we added beyond the list

- **Segment-level content-addressed cache with coalescing locks.** Instead of
  a process-per-stream transcode relay (MediaMTX-style), the hub is a thin
  caching HLS proxy. No transcode in the common path means near-zero added
  latency and CPU, and the cache makes late-joiners free. This is why the hub
  holds ~65 MB RSS serving 10 concurrent viewers instead of spawning FFmpeg
  per viewer.
- **Measurement as a first-class component.** The origin counts its own hits,
  so every sharing claim is verifiable from the provider's side of the wire,
  not just the hub's self-report. Few media stacks ship their own falsifier.

## 3. Component model

```
                    ┌──────────────────────────────────────────┐
  authorized        │                 StreamOS hub              │
  source(s) ───────▶│  Relay (relay.py)                         │────▶ devices
  (HLS)             │   ├─ UpstreamSession registry  (caps)     │     (web now;
                    │   ├─ segment cache + per-key locks        │      AndroidTV
                    │   └─ playlist TTL cache + URI rewrite      │      / iOS next)
                    │  SourceRegistry (sources.py, sqlite)      │
                    │  SessionManager (sessions.py)             │
                    │  DeviceManager  (pairing, sqlite)         │
                    │  Metrics (metrics.py) ──▶ /api/metrics    │
                    │  FastAPI app (main.py) + reaper task      │
                    │  Web client (web/) served static          │
                    └──────────────────────────────────────────┘
```

### Relay (the core)
- `acquire(source, session)` enforces **per-source** `max_sessions` and the
  **global** `max_upstream_sessions` cap. If a shareable session for the
  source exists, the viewer attaches to it (0 new upstream cost). Otherwise a
  new `UpstreamSession` opens if caps allow, else `RelayError(409/503)`.
- `get_segment` serves from cache; on a miss it takes a per-`(source,segment)`
  `asyncio.Lock`, re-checks the cache, then fetches upstream exactly once.
  This is what makes N simultaneous viewers cost one fetch.
- `get_playlist` caches the (rewritten) media playlist for `playlist_ttl`,
  bounding upstream playlist fetches by *time*, not viewer count. Segment and
  MAP/KEY URIs are rewritten to basenames so clients fetch back through the
  hub.
- A background **reaper** releases upstream sessions once their last viewer
  has been idle past `session_idle_timeout`, and prunes stale cache entries.

### Session & capacity accounting
- An **upstream session** is the unit a provider's concurrency policy acts on.
  The hub keeps ≤ `max_upstream_sessions` globally.
- A **viewing session** is one device watching one source — the local
  counterpart, used for the Shared/Independent/Devices screens and for
  driving upstream teardown.
- **Shared vs independent** is derived, not declared: if a source already has
  an upstream session when a device joins, that device is `shared`; if its
  join opens the source's first session, it is `independent`.

### Why SQLite
One writer, a household's worth of rows, zero ops, backup-by-copy, WAL for
concurrent reads. A networked DB would add failure modes with no benefit at
this scale.

## 4. Protocol choice: HLS

HLS was chosen over RTSP/RTP/WebRTC/SRT for the relay because it is
**cache-native**: media is already chunked into independently-addressable
segments with a text manifest, which is exactly what makes segment-level
sharing a few dozen lines instead of a media server. It is also the format
real MAG/IPTV deployments most commonly expose, and every target decoder
(ExoPlayer/Media3, AVPlayer, hls.js, VLC) speaks it. Trade-off: HLS adds
segment-duration latency; mitigated by small segments and, where a source
offers it, LL-HLS (future work).

## 5. Data & control flow for one "play"

1. Client `POST /api/play?device_id&source_id`.
2. Hub creates a viewing session, calls `relay.acquire` (cap check, share or
   open). Returns `{mode, play_url}` or a graceful `{ok:false, reason}`.
3. Client loads `play_url` (`/live/{sid}/index.m3u8`) via hls.js.
4. Playlist served from TTL cache (one upstream fetch per TTL). Segment GETs
   hit cache or coalesce into one upstream fetch each.
5. Client heartbeats position; hub stores watch history; on close the viewing
   session ends and the reaper later tears the upstream session down.

## 6. Security posture

- Devices join only via a **pairing code** the operator can see — no silent
  LAN attachment.
- The origin enforces **path containment** (no `..` escape from content root).
- Untrusted upstream URLs are fetched by the hub, never executed; failures
  surface as `502`, not crashes.
- The relay never exposes source credentials to clients; clients only ever
  see hub-relative URLs.
- Known gaps (auth on the admin API, TLS, binding) are listed in
  `KNOWN_LIMITATIONS.md` — this is a LAN appliance, not yet an internet-
  exposed service.
