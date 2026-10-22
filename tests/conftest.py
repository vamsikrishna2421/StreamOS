"""Shared test fixtures.

The relay tests need a *real* origin server (the hub pulls from it over
HTTP with its own client) and the hub driven in-process over ASGI so we can
fire many concurrent downstream requests and inspect hub state directly.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hub"))
sys.path.insert(0, str(ROOT))

from testkit import origin as origin_mod  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _ensure_content() -> Path:
    root = ROOT / "scratch" / "origin"
    if not (root / "ch1" / "index.m3u8").exists():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "testkit" / "make_content.py"),
                        "--root", str(root)], check=True)
    return root


@pytest.fixture(scope="session")
def origin_server():
    content = _ensure_content()
    origin_mod.set_content_root(content)
    port = _free_port()
    config = uvicorn.Config(origin_mod.app, host="127.0.0.1", port=port,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{base}/stats", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("origin server did not start")
    yield base
    server.should_exit = True
    thread.join(timeout=5)


@pytest_asyncio.fixture
async def hub(origin_server, tmp_path, monkeypatch):
    # isolate hub data per test; keep caps small so limits are exercisable
    monkeypatch.setenv("STREAMOS_DATA", str(tmp_path / "hubdata"))
    monkeypatch.setenv("STREAMOS_MAX_UPSTREAM", "2")
    monkeypatch.setenv("STREAMOS_PLAYLIST_TTL", "0.5")
    monkeypatch.setenv("STREAMOS_SAMPLES", "0")
    monkeypatch.setenv("STREAMOS_ALLOWED_HOSTS", "hub")
    # import fresh so settings pick up env
    import importlib
    import streamos.config as cfg
    import streamos.main as main
    importlib.reload(cfg)
    importlib.reload(main)
    app = main.app
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://hub") as client:
            client.origin = origin_server  # type: ignore[attr-defined]
            yield client


@pytest_asyncio.fixture
async def hub_media(origin_server, tmp_path, monkeypatch):
    """Hub with a local media folder containing one dummy video file. The
    bytes are not a real codec — enough to exercise registration, the
    /media range server, and local-source play routing."""
    media = tmp_path / "movies"
    media.mkdir()
    clip = media / "clip.mp4"
    clip.write_bytes(bytes(range(256)) * 40)   # 10240 bytes, deterministic
    monkeypatch.setenv("STREAMOS_DATA", str(tmp_path / "hubdata"))
    monkeypatch.setenv("STREAMOS_MEDIA", str(media.resolve()))
    monkeypatch.setenv("STREAMOS_MAX_UPSTREAM", "2")
    monkeypatch.setenv("STREAMOS_SAMPLES", "0")
    monkeypatch.setenv("STREAMOS_ALLOWED_HOSTS", "hub")
    import importlib
    import streamos.config as cfg
    import streamos.main as main
    importlib.reload(cfg)
    importlib.reload(main)
    app = main.app
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://hub") as client:
            # the startup scan is now backgrounded; settle it deterministically
            await client.post("/api/library/rescan")
            client.clip = clip  # type: ignore[attr-defined]
            yield client


async def register_source(client, origin, name, path, **kw):
    body = {"name": name, "kind": kw.get("kind", "live"),
            "upstream_url": f"{origin}/{path}",
            "max_sessions": kw.get("max_sessions", 1),
            "shareable": kw.get("shareable", True)}
    r = await client.post("/api/sources", json=body)
    r.raise_for_status()
    return r.json()
