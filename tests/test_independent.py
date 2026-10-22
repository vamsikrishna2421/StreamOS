"""Independent-viewing and capacity experiments (brief section 7C).

Verifies distinct channels open distinct upstream sessions, the global cap
is honoured, non-shareable sources refuse a second viewer, and exhaustion
is handled gracefully (a clear rejection, not a crash or a silent stall).
"""
from __future__ import annotations

import pytest

from conftest import register_source

pytestmark = pytest.mark.asyncio


async def test_two_distinct_channels_two_upstream_sessions(hub):
    origin = hub.origin
    a = await register_source(hub, origin, "Ch1", "ch1/index.m3u8")
    b = await register_source(hub, origin, "Ch2", "ch2/index.m3u8")
    ra = await hub.post("/api/play",
                        params={"device_id": "tv", "source_id": a["id"]})
    rb = await hub.post("/api/play",
                        params={"device_id": "phone", "source_id": b["id"]})
    assert ra.json()["mode"] == "independent"
    assert rb.json()["mode"] == "independent"
    m = (await hub.get("/api/metrics")).json()
    assert m["upstream_sessions"] == 2


async def test_live_plus_vod_mix(hub):
    origin = hub.origin
    live = await register_source(hub, origin, "Ch1", "ch1/index.m3u8", kind="live")
    vod = await register_source(hub, origin, "VOD", "vod1/index.m3u8", kind="vod")
    r1 = await hub.post("/api/play",
                        params={"device_id": "tv", "source_id": live["id"]})
    r2 = await hub.post("/api/play",
                        params={"device_id": "tab", "source_id": vod["id"]})
    assert r1.json()["ok"] and r2.json()["ok"]
    assert (await hub.get("/api/metrics")).json()["upstream_sessions"] == 2


async def test_global_cap_rejects_gracefully(hub):
    # hub fixture sets STREAMOS_MAX_UPSTREAM=2
    origin = hub.origin
    a = await register_source(hub, origin, "Ch1", "ch1/index.m3u8")
    b = await register_source(hub, origin, "Ch2", "ch2/index.m3u8")
    c = await register_source(hub, origin, "VOD", "vod1/index.m3u8", kind="vod")
    await hub.post("/api/play", params={"device_id": "d1", "source_id": a["id"]})
    await hub.post("/api/play", params={"device_id": "d2", "source_id": b["id"]})
    r3 = await hub.post("/api/play",
                        params={"device_id": "d3", "source_id": c["id"]})
    body = r3.json()
    assert body["ok"] is False
    assert body["mode"] == "rejected"
    assert "limit" in body["reason"]
    # no partial/zombie session was left behind
    assert (await hub.get("/api/metrics")).json()["upstream_sessions"] == 2


async def test_shared_viewer_does_not_consume_second_slot(hub):
    """Two devices on the SAME channel use one slot, leaving room for an
    independent viewer on another channel under a cap of 2."""
    origin = hub.origin
    a = await register_source(hub, origin, "Ch1", "ch1/index.m3u8")
    b = await register_source(hub, origin, "Ch2", "ch2/index.m3u8")
    await hub.post("/api/play", params={"device_id": "tv", "source_id": a["id"]})
    r2 = await hub.post("/api/play",
                        params={"device_id": "phone", "source_id": a["id"]})
    assert r2.json()["mode"] == "shared"
    r3 = await hub.post("/api/play",
                        params={"device_id": "tab", "source_id": b["id"]})
    assert r3.json()["ok"] is True       # still room: shared pair = 1 slot
    assert (await hub.get("/api/metrics")).json()["upstream_sessions"] == 2


async def test_non_shareable_refuses_second_device(hub):
    origin = hub.origin
    a = await register_source(hub, origin, "Ch1", "ch1/index.m3u8",
                              shareable=False)
    r1 = await hub.post("/api/play",
                        params={"device_id": "tv", "source_id": a["id"]})
    assert r1.json()["ok"] is True
    r2 = await hub.post("/api/play",
                        params={"device_id": "phone", "source_id": a["id"]})
    assert r2.json()["ok"] is False
    assert "shareable" in r2.json()["reason"]
