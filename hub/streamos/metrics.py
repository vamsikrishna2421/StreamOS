"""Lightweight in-process metrics.

Real counters, not estimates. The diagnostics API and the test harness
read these to make empirical claims (upstream session counts, bytes moved,
cache hit ratio, time-to-first-segment).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Counters:
    upstream_segment_fetches: int = 0      # segments actually pulled upstream
    downstream_segment_serves: int = 0     # segments handed to local clients
    cache_hits: int = 0
    cache_misses: int = 0
    upstream_bytes: int = 0                # ingress from origin/provider
    downstream_bytes: int = 0              # egress to local devices
    upstream_playlist_fetches: int = 0
    stalls: int = 0                        # client reported / detected stalls
    errors: int = 0


class Metrics:
    """Thread- and task-safe counters plus per-source gauges."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.c = Counters()
        self._per_source: dict[str, Counters] = defaultdict(Counters)
        self._ttfs_samples: list[float] = []  # time-to-first-segment, seconds
        self.started_at = time.time()

    def add(self, field_name: str, n: int = 1, source: str | None = None) -> None:
        with self._lock:
            setattr(self.c, field_name, getattr(self.c, field_name) + n)
            if source is not None:
                sc = self._per_source[source]
                setattr(sc, field_name, getattr(sc, field_name) + n)

    def record_ttfs(self, seconds: float) -> None:
        with self._lock:
            self._ttfs_samples.append(seconds)

    def snapshot(self) -> dict:
        with self._lock:
            total = self.c.cache_hits + self.c.cache_misses
            hit_ratio = (self.c.cache_hits / total) if total else 0.0
            ttfs = sorted(self._ttfs_samples)
            return {
                "uptime_s": round(time.time() - self.started_at, 1),
                "counters": vars(self.c).copy(),
                "cache_hit_ratio": round(hit_ratio, 4),
                "ttfs_count": len(ttfs),
                "ttfs_avg_s": round(sum(ttfs) / len(ttfs), 4) if ttfs else None,
                "ttfs_p50_s": round(ttfs[len(ttfs) // 2], 4) if ttfs else None,
                "ttfs_max_s": round(ttfs[-1], 4) if ttfs else None,
                "per_source": {
                    k: vars(v).copy() for k, v in self._per_source.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self.c = Counters()
            self._per_source.clear()
            self._ttfs_samples.clear()
            self.started_at = time.time()


METRICS = Metrics()
