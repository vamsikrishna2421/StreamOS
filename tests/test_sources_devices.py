"""Source CRUD, device pairing handshake, and watch-history persistence."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_source_crud(hub):
    origin = hub.origin
    r = await hub.post("/api/sources", json={
        "name": "Ch1", "kind": "live",
        "upstream_url": f"{origin}/ch1/index.m3u8",
    })
    sid = r.json()["id"]
    assert (await hub.get("/api/sources")).json()[0]["id"] == sid
    await hub.post(f"/api/sources/{sid}/enabled", params={"enabled": False})
    assert (await hub.get("/api/sources", params={"enabled_only": True})).json() == []
    await hub.delete(f"/api/sources/{sid}")
    assert (await hub.get("/api/sources")).json() == []


async def test_disabled_source_cannot_play(hub):
    origin = hub.origin
    r = await hub.post("/api/sources", json={
        "name": "Ch1", "kind": "live",
        "upstream_url": f"{origin}/ch1/index.m3u8", "enabled": True})
    sid = r.json()["id"]
    await hub.post(f"/api/sources/{sid}/enabled", params={"enabled": False})
    rp = await hub.post("/api/play", params={"device_id": "d1", "source_id": sid})
    assert rp.status_code == 404


async def test_pairing_handshake(hub):
    start = await hub.post("/api/pair/start", json={"name": "Living Room TV"})
    code = start.json()["code"]
    assert len(code) == 6
    bad = await hub.post("/api/pair/complete",
                         json={"code": "000000", "name": "x", "platform": "web"})
    assert bad.status_code == 400
    ok = await hub.post("/api/pair/complete",
                        json={"code": code, "name": "Living Room TV",
                              "platform": "androidtv"})
    assert ok.status_code == 200
    dev = ok.json()
    assert dev["platform"] == "androidtv"
    # code is single-use
    reuse = await hub.post("/api/pair/complete",
                           json={"code": code, "name": "y", "platform": "web"})
    assert reuse.status_code == 400
    assert len((await hub.get("/api/devices")).json()) == 1


async def test_watch_history_roundtrip(hub):
    origin = hub.origin
    r = await hub.post("/api/sources", json={
        "name": "VOD", "kind": "vod",
        "upstream_url": f"{origin}/vod1/index.m3u8"})
    sid = r.json()["id"]
    await hub.post("/api/history", json={"source_id": sid, "position_s": 42.0,
                                         "duration_s": 120.0})
    hist = (await hub.get("/api/history")).json()
    assert hist[0]["source_id"] == sid
    assert hist[0]["position_s"] == 42.0
    # upsert updates in place, not append
    await hub.post("/api/history", json={"source_id": sid, "position_s": 88.0,
                                         "duration_s": 120.0})
    hist2 = (await hub.get("/api/history")).json()
    assert len(hist2) == 1 and hist2[0]["position_s"] == 88.0
