"""Source registry: the authorized streams the hub may relay.

A *source* is one upstream media URL plus its policy: whether the hub may
share it across devices and how many simultaneous upstream sessions it
permits. Policy is declared, not guessed — the operator sets it to match
what their provider actually allows.
"""
from __future__ import annotations

import time
import uuid

from .db import DB


class SourceRegistry:
    def __init__(self, db: DB):
        self.db = db

    def list(self, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM sources"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY group_name, name"
        return [self._row(r) for r in self.db.query(sql)]

    def get(self, source_id: str) -> dict | None:
        r = self.db.query_one("SELECT * FROM sources WHERE id=?", (source_id,))
        return self._row(r) if r else None

    def create(self, data: dict) -> dict:
        sid = data.get("id") or uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT INTO sources"
            "(id,name,kind,upstream_url,max_sessions,shareable,logo,group_name,"
            " enabled,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                sid, data["name"], data["kind"], data["upstream_url"],
                int(data.get("max_sessions", 1)), int(bool(data.get("shareable", True))),
                data.get("logo"), data.get("group_name"),
                int(bool(data.get("enabled", True))), time.time(),
            ),
        )
        return self.get(sid)  # type: ignore[return-value]

    def delete(self, source_id: str) -> None:
        self.db.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        self.db.execute(
            "UPDATE sources SET enabled=? WHERE id=?", (int(enabled), source_id)
        )

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["shareable"] = bool(d["shareable"])
        d["enabled"] = bool(d["enabled"])
        return d
