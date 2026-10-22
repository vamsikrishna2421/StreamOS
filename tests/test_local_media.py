"""Local media library + range-serving tests.

Covers the path a non-technical user actually takes: point the hub at a
folder of their own videos, press play, and seek. No relay, no upstream
session — a local file is served directly with HTTP range support.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_library_registers_local_file(hub_media):
    sources = (await hub_media.get("/api/sources")).json()
    names = {s["name"] for s in sources}
    assert "clip" in names
    clip = next(s for s in sources if s["name"] == "clip")
    assert clip["kind"] == "vod"
    assert clip["upstream_url"].startswith("file://")


async def test_play_local_returns_media_url_no_upstream(hub_media):
    sources = (await hub_media.get("/api/sources")).json()
    clip = next(s for s in sources if s["name"] == "clip")
    r = await hub_media.post("/api/play",
                             params={"device_id": "laptop", "source_id": clip["id"]})
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "local"
    assert body["play_url"] == f"/media/{clip['id']}"
    # a local file must not consume a provider/upstream session
    assert body["upstream_sessions"] == 0


async def test_media_full_and_range_requests(hub_media):
    sources = (await hub_media.get("/api/sources")).json()
    cid = next(s for s in sources if s["name"] == "clip")["id"]

    full = await hub_media.get(f"/media/{cid}")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert int(full.headers["content-length"]) == 10240

    part = await hub_media.get(f"/media/{cid}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.headers["content-range"] == "bytes 0-99/10240"
    assert int(part.headers["content-length"]) == 100
    assert len(part.content) == 100

    mid = await hub_media.get(f"/media/{cid}", headers={"Range": "bytes=100-199"})
    assert mid.status_code == 206
    # content returned is exactly the requested slice (deterministic fixture)
    assert mid.content == (bytes(range(256)) * 40)[100:200]


async def test_media_unsatisfiable_range(hub_media):
    sources = (await hub_media.get("/api/sources")).json()
    cid = next(s for s in sources if s["name"] == "clip")["id"]
    r = await hub_media.get(f"/media/{cid}", headers={"Range": "bytes=999999-"})
    assert r.status_code == 416


async def test_media_rejects_unknown_source(hub_media):
    r = await hub_media.get("/media/local_doesnotexist")
    assert r.status_code == 404


async def test_rescan_is_idempotent(hub_media):
    first = (await hub_media.post("/api/library/rescan")).json()
    assert first["added"] == 0           # already registered at startup
    again = (await hub_media.post("/api/library/rescan")).json()
    assert again["added"] == 0 and again["removed"] == 0
