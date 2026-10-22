"""Downstream viewing sessions and device pairing.

A *viewing session* is one device watching one source. It is the local
counterpart of a relay subscriber. The hub tracks it so it can show what is
playing where (Connected Devices / Shared / Independent screens), expire
abandoned viewers, and drive upstream teardown.

Pairing uses a short-lived numeric code shown on the hub and typed on the
new device. No device joins without the operator seeing the code, which
keeps an unknown client on the LAN from attaching itself.
"""
from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field

from .db import DB


@dataclass
class ViewingSession:
    id: str
    device_id: str
    source_id: str
    started_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    mode: str = "unknown"          # shared | independent
    position_s: float = 0.0


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, ViewingSession] = {}

    def start(self, device_id: str, source_id: str, mode: str) -> ViewingSession:
        vs = ViewingSession(
            id=uuid.uuid4().hex[:12], device_id=device_id,
            source_id=source_id, mode=mode,
        )
        self._sessions[vs.id] = vs
        return vs

    def heartbeat(self, session_id: str, position_s: float | None = None) -> bool:
        vs = self._sessions.get(session_id)
        if not vs:
            return False
        vs.last_seen = time.time()
        if position_s is not None:
            vs.position_s = position_s
        return True

    def end(self, session_id: str) -> ViewingSession | None:
        return self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> ViewingSession | None:
        return self._sessions.get(session_id)

    def list(self) -> list[ViewingSession]:
        return list(self._sessions.values())

    def active_source_ids(self) -> set[str]:
        return {vs.source_id for vs in self._sessions.values()}

    def expire(self, idle_timeout: float) -> list[ViewingSession]:
        now = time.time()
        dead = [vs for vs in self._sessions.values()
                if now - vs.last_seen > idle_timeout]
        for vs in dead:
            self._sessions.pop(vs.id, None)
        return dead


@dataclass
class PairingRequest:
    code: str
    created_at: float = field(default_factory=time.time)


class DeviceManager:
    """Device registry plus a pairing-code handshake."""

    PAIR_TTL = 300.0  # seconds a pairing code stays valid

    def __init__(self, db: DB):
        self.db = db
        self._pending: dict[str, PairingRequest] = {}  # code -> request

    def start_pairing(self) -> str:
        code = f"{secrets.randbelow(900000) + 100000}"  # 6-digit
        self._pending[code] = PairingRequest(code=code)
        self._gc_pairings()
        return code

    def _gc_pairings(self) -> None:
        now = time.time()
        for c in list(self._pending):
            if now - self._pending[c].created_at > self.PAIR_TTL:
                del self._pending[c]

    def complete_pairing(self, code: str, name: str, platform: str) -> dict | None:
        self._gc_pairings()
        if code not in self._pending:
            return None
        del self._pending[code]
        return self.register(name, platform)

    def register(self, name: str, platform: str) -> dict:
        did = uuid.uuid4().hex[:12]
        now = time.time()
        self.db.execute(
            "INSERT INTO devices(id,name,platform,paired_at,last_seen,profile_id)"
            " VALUES(?,?,?,?,?,?)",
            (did, name, platform, now, now, "default"),
        )
        return self.get(did)  # type: ignore[return-value]

    def touch(self, device_id: str) -> None:
        self.db.execute(
            "UPDATE devices SET last_seen=? WHERE id=?", (time.time(), device_id)
        )

    def get(self, device_id: str) -> dict | None:
        r = self.db.query_one("SELECT * FROM devices WHERE id=?", (device_id,))
        return dict(r) if r else None

    def list(self) -> list[dict]:
        return [dict(r) for r in
                self.db.query("SELECT * FROM devices ORDER BY paired_at")]

    def remove(self, device_id: str) -> None:
        self.db.execute("DELETE FROM devices WHERE id=?", (device_id,))
