"""Runtime configuration for the StreamOS hub.

Values come from environment variables so the same image runs in dev,
tests, and deployment without code changes. Nothing here reaches out to a
network by itself.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # Where runtime state (sqlite db, cached segments) lives.
    data_dir: Path = Path(os.environ.get("STREAMOS_DATA", "./scratch/hubdata"))

    # Global cap on simultaneous upstream sessions the hub will open.
    # This models a provider-enforced concurrent-connection allowance.
    # The hub never exceeds it; it shares or rejects instead.
    max_upstream_sessions: int = _env_int("STREAMOS_MAX_UPSTREAM", 2)

    # Segment cache: how long a fetched segment stays warm (seconds).
    segment_ttl: float = _env_float("STREAMOS_SEGMENT_TTL", 30.0)

    # Live playlist cache TTL. Bounds upstream playlist fetches by time
    # rather than by downstream client count.
    playlist_ttl: float = _env_float("STREAMOS_PLAYLIST_TTL", 1.0)

    # A downstream session is considered dead if no request arrives within
    # this many seconds. Drives upstream teardown and cleanup.
    session_idle_timeout: float = _env_float("STREAMOS_SESSION_IDLE", 20.0)

    # Upstream request timeout (seconds).
    upstream_timeout: float = _env_float("STREAMOS_UPSTREAM_TIMEOUT", 10.0)

    def db_path(self) -> Path:
        return self.data_dir / "streamos.db"

    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


def load_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.cache_dir().mkdir(parents=True, exist_ok=True)
    return s
