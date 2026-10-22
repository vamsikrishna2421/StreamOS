"""Local media library.

Lets the hub play video files that already live on the user's own machine —
their movies, home videos, anything they have the right to watch. These are
served directly with HTTP range support (so seeking works) and never touch
the relay or any upstream session: a local file is yours, with no provider
concurrency limit to share around.

Only browser-playable container extensions are registered, so a user never
sees an item that silently fails. Files are matched by extension; on a real
laptop browser, .mp4/.m4v/.mov (H.264/AAC) and .webm/.ogv play natively.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .db import DB

# Extensions a mainstream desktop browser plays without transcoding. Limited
# to the broadly-supported set (H.264/AAC in mp4/m4v/mov, plus webm); .ogv/.ogg
# are excluded because Safari cannot decode them, which would show a card that
# silently fails. app.js also surfaces a message if any file fails to decode.
PLAYABLE = {".mp4", ".m4v", ".mov", ".webm"}
LOCAL_PREFIX = "file://"

# Directory names to skip while scanning: hidden dirs and macOS media-library
# bundles (each can contain thousands of internal files).
_SKIP_DIR_SUFFIXES = (".photoslibrary", ".tvlibrary", ".imovielibrary",
                      ".theater", ".fcpbundle", ".app")


def is_local(source: dict) -> bool:
    return str(source.get("upstream_url", "")).startswith(LOCAL_PREFIX)


def local_path(source: dict) -> Path:
    return Path(source["upstream_url"][len(LOCAL_PREFIX):])


def _stable_id(path: Path) -> str:
    return "local_" + hashlib.sha1(str(path).encode()).hexdigest()[:10]


class Library:
    def __init__(self, db: DB, roots: list[Path]):
        self.db = db
        # resolved, de-duplicated, existing directories only
        seen: set[str] = set()
        self.roots: list[Path] = []
        for r in roots:
            rp = r.expanduser().resolve()
            if rp.is_dir() and str(rp) not in seen:
                seen.add(str(rp))
                self.roots.append(rp)

    def contains(self, path: Path) -> bool:
        """True iff path is inside one of the configured roots (no escape)."""
        try:
            rp = path.resolve()
        except OSError:
            return False
        return any(str(rp).startswith(str(root) + os.sep) or rp == root
                   for root in self.roots)

    def scan(self) -> dict:
        """Register playable files under the roots; prune vanished ones.
        Idempotent — safe to call repeatedly."""
        found: dict[str, Path] = {}
        for root in self.roots:
            for dirpath, dirs, files in os.walk(root):
                # prune hidden dirs and library bundles in place so os.walk
                # never descends into them
                dirs[:] = [d for d in dirs
                           if not d.startswith(".")
                           and not d.lower().endswith(_SKIP_DIR_SUFFIXES)]
                for fn in files:
                    if fn.startswith("."):
                        continue
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in PLAYABLE:
                        p = Path(dirpath) / fn
                        found[_stable_id(p)] = p

        # upsert found files in one transaction (not one fsync per file)
        existing = {r["id"] for r in
                    self.db.query("SELECT id FROM sources WHERE upstream_url LIKE ?",
                                  (f"{LOCAL_PREFIX}%",))}
        new_rows = [
            (sid, p.stem, "vod", f"{LOCAL_PREFIX}{p}", 1, 1, None,
             self._group_for(p), 1, 0.0)
            for sid, p in found.items() if sid not in existing
        ]
        self.db.execute_many(
            "INSERT OR IGNORE INTO sources"
            "(id,name,kind,upstream_url,max_sessions,shareable,logo,"
            " group_name,enabled,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            new_rows,
        )
        added = len(new_rows)

        # prune local sources whose files are gone or now outside roots
        removed = 0
        for row in self.db.query(
                "SELECT id,upstream_url FROM sources WHERE upstream_url LIKE ?",
                (f"{LOCAL_PREFIX}%",)):
            path = Path(row["upstream_url"][len(LOCAL_PREFIX):])
            if not path.is_file() or not self.contains(path):
                self.db.execute("DELETE FROM sources WHERE id=?", (row["id"],))
                removed += 1

        return {"roots": [str(r) for r in self.roots],
                "registered": len(found), "added": added, "removed": removed}

    def _group_for(self, p: Path) -> str:
        """Group by the immediate parent folder under its root, else 'Library'."""
        for root in self.roots:
            try:
                rel = p.resolve().relative_to(root)
            except ValueError:
                continue
            parts = rel.parts
            if len(parts) >= 2:
                return parts[0]           # subfolder name, e.g. "Movies"
            return root.name or "Library"
        return "Library"
