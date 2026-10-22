"""SQLite persistence for sources, devices, watch history, and profiles.

SQLite is sufficient for a single-household hub: one writer, modest row
counts, zero operational overhead, and trivial backup (copy one file).
WAL mode keeps concurrent reads from blocking the occasional write.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('live','vod')),
    upstream_url TEXT NOT NULL,
    max_sessions INTEGER NOT NULL DEFAULT 1,
    shareable    INTEGER NOT NULL DEFAULT 1,   -- may the hub relay to >1 device
    logo         TEXT,
    group_name   TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    platform   TEXT,                 -- androidtv / ios / web / ...
    paired_at  REAL NOT NULL,
    last_seen  REAL,
    profile_id TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    profile_id TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    PRIMARY KEY (profile_id, source_id)
);

CREATE TABLE IF NOT EXISTS watch_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    position_s REAL NOT NULL DEFAULT 0,
    duration_s REAL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_profile ON watch_history(profile_id, updated_at);
"""


class DB:
    def __init__(self, path: Path):
        self._path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._ensure_default_profile()

    def _ensure_default_profile(self) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM profiles WHERE id='default'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO profiles(id,name) VALUES('default','Household')"
                )
                self._conn.commit()

    # --- generic helpers -------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # --- watch history ---------------------------------------------------
    def upsert_history(self, profile_id: str, source_id: str,
                       position_s: float, duration_s: float | None) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM watch_history WHERE profile_id=? AND source_id=?",
                (profile_id, source_id),
            ).fetchone()
            now = time.time()
            if row:
                self._conn.execute(
                    "UPDATE watch_history SET position_s=?,duration_s=?,updated_at=? "
                    "WHERE id=?",
                    (position_s, duration_s, now, row["id"]),
                )
            else:
                self._conn.execute(
                    "INSERT INTO watch_history"
                    "(profile_id,source_id,position_s,duration_s,updated_at) "
                    "VALUES(?,?,?,?,?)",
                    (profile_id, source_id, position_s, duration_s, now),
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
