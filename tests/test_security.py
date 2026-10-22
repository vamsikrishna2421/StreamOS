"""Security hardening tests: DNS-rebinding/host allowlist, cross-origin write
block, and upstream-URL scheme validation (no file:// arbitrary read)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_create_source_rejects_file_scheme(hub):
    r = await hub.post("/api/sources", json={
        "name": "evil", "kind": "vod", "upstream_url": "file:///etc/passwd"})
    assert r.status_code == 400


async def test_create_source_rejects_non_http_scheme(hub):
    for url in ("ftp://host/x", "gopher://x", "/etc/passwd", "data:text/plain,x"):
        r = await hub.post("/api/sources", json={
            "name": "x", "kind": "vod", "upstream_url": url})
        assert r.status_code == 400, url


async def test_cross_origin_write_is_refused(hub):
    # a page on evil.com trying to POST (CSRF / rebinding) is blocked
    r = await hub.post("/api/sources",
                       headers={"origin": "http://evil.com"},
                       json={"name": "x", "kind": "live",
                             "upstream_url": "http://127.0.0.1/x.m3u8"})
    assert r.status_code == 403


async def test_same_origin_write_allowed(hub):
    r = await hub.post("/api/sources",
                       headers={"origin": "http://hub"},
                       json={"name": "ok", "kind": "live",
                             "upstream_url": "http://127.0.0.1/x.m3u8"})
    assert r.status_code == 200


async def test_foreign_host_header_rejected(hub):
    # DNS-rebinding: request arrives with a Host the hub was not told to trust
    r = await hub.get("/api/health", headers={"host": "attacker.example"})
    assert r.status_code == 400


async def test_trusted_host_allowed(hub):
    r = await hub.get("/api/health", headers={"host": "hub"})
    assert r.status_code == 200
