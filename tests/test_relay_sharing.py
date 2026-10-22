"""Shared-viewing experiments (brief section 7B).

Central claim under test: one upstream source feeding many local devices
produces ~1x upstream traffic, not Nx. We verify it from the origin's own
request counter, which the hub cannot fake.
"""
from __future__ import annotations

import asyncio

import pytest

from conftest import register_source

pytestmark = pytest.mark.asyncio


async def _play_whole_channel(client, source_id, device_id):
    """Simulate a device: pair-less play, fetch playlist, pull every segment."""
    r = await client.post("/api/play",
                          params={"device_id": device_id, "source_id": source_id})
    data = r.json()
    assert data["ok"], data
    pl = await client.get(data["play_url"])
    pl.raise_for_status()
    segs = [ln.strip() for ln in pl.text.splitlines()
            if ln.strip() and not ln.startswith("#")]
    for s in segs:
        rr = await client.get(f"/live/{source_id}/{s}")
        rr.raise_for_status()
    return len(segs)


@pytest.mark.parametrize("n_devices", [1, 2, 3, 5])
async def test_one_stream_many_devices_shares_upstream(hub, n_devices):
    origin = hub.origin
    src = await register_source(hub, origin, "Ch1", "ch1/index.m3u8")
    # reset origin + hub counters to measure just this experiment
    import httpx
    httpx.post(f"{origin}/reset")
    await hub.post("/api/metrics/reset")

    results = await asyncio.gather(*[
        _play_whole_channel(hub, src["id"], f"dev{i}")
        for i in range(n_devices)
    ])
    n_segs = results[0]
    assert all(r == n_segs for r in results)

    stats = httpx.get(f"{origin}/stats").json()
    # The origin should have served each distinct segment ~once, regardless
    # of device count. Allow a tiny slack for a playlist-TTL race only.
    assert stats["segment_requests"] == stats["distinct_segments"] == n_segs, stats

    m = (await hub.get("/api/metrics")).json()
    # Downstream served N x segments; upstream fetched them once.
    assert m["metrics"]["counters"]["downstream_segment_serves"] == n_segs * n_devices
    assert m["metrics"]["counters"]["upstream_segment_fetches"] == n_segs
    assert m["upstream_sessions"] == 1
    # Egress should be ~N x ingress: the sharing dividend.
    c = m["metrics"]["counters"]
    if n_devices > 1:
        assert c["downstream_bytes"] > c["upstream_bytes"]


async def test_late_joiner_uses_cache_not_new_upstream(hub):
    origin = hub.origin
    import httpx
    src = await register_source(hub, origin, "Ch1", "ch1/index.m3u8")
    httpx.post(f"{origin}/reset")
    await hub.post("/api/metrics/reset")

    n1 = await _play_whole_channel(hub, src["id"], "early")
    mid = httpx.get(f"{origin}/stats").json()["segment_requests"]
    # a second device joins after the first finished; cache is still warm
    n2 = await _play_whole_channel(hub, src["id"], "late")
    after = httpx.get(f"{origin}/stats").json()["segment_requests"]
    assert n1 == n2
    assert mid == n1
    assert after == n1   # late joiner added ZERO upstream fetches (cache hit)


async def test_disconnect_releases_session(hub):
    origin = hub.origin
    src = await register_source(hub, origin, "Ch1", "ch1/index.m3u8")
    r = await hub.post("/api/play",
                       params={"device_id": "d1", "source_id": src["id"]})
    j = r.json()
    sessions = (await hub.get("/api/sessions")).json()
    assert len(sessions) == 1
    sid = sessions[0]["id"]
    await hub.post(f"/api/sessions/{sid}/end")
    assert (await hub.get("/api/sessions")).json() == []
