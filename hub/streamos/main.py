"""StreamOS hub application.

Wires the registry, relay, session and device managers behind a small HTTP
API and serves the web client. A background reaper expires idle viewers and
tears down the upstream sessions they were holding.
"""
from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import os
from pathlib import Path

import psutil
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .db import DB
from .library import Library, is_local, local_path
from .metrics import METRICS
from .models import (AllocResult, DeviceOut, DevicePairComplete, DevicePairStart,
                     HistoryIn, SourceIn, SourceOut)
from .relay import Relay, RelayError
from .sessions import DeviceManager, SessionManager
from .sources import SourceRegistry

WEB_DIR = Path(__file__).parent / "web"
_CHUNK = 256 * 1024


async def _reaper(app: FastAPI) -> None:
    s = app.state.settings
    while True:
        await asyncio.sleep(5)
        try:
            dead = app.state.sessions.expire(s.session_idle_timeout)
            for vs in dead:
                await app.state.relay.release(vs.source_id, vs.id)
            await app.state.relay.reap()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - reaper must never die
            METRICS.add("errors")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    db = DB(settings.db_path())
    app.state.settings = settings
    app.state.db = db
    app.state.registry = SourceRegistry(db)
    app.state.relay = Relay(settings)
    app.state.sessions = SessionManager()
    app.state.devices = DeviceManager(db)
    app.state.library = Library(db, settings.media_dirs())
    try:
        app.state.library.scan()
    except Exception:  # noqa: BLE001 - a bad media dir must not stop the hub
        METRICS.add("errors")
    task = asyncio.create_task(_reaper(app))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await app.state.relay.aclose()
        db.close()


app = FastAPI(title="StreamOS Hub", version="0.3.0", lifespan=lifespan)


# --- health & metrics ----------------------------------------------------
@app.get("/api/health")
async def health():
    return {"ok": True, "version": app.version}


@app.get("/api/metrics")
async def metrics():
    try:
        host = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "mem_percent": psutil.virtual_memory().percent,
        }
    except Exception:  # noqa: BLE001
        host = {}
    return {
        "metrics": METRICS.snapshot(),
        "upstream_sessions": app.state.relay.upstream_count(),
        "upstream_detail": app.state.relay.sessions_view(),
        "viewing_sessions": len(app.state.sessions.list()),
        "host": host,
    }


@app.post("/api/metrics/reset")
async def metrics_reset():
    METRICS.reset()
    return {"ok": True}


@app.post("/api/relay/flush")
async def relay_flush():
    """Clear relay caches and active sessions (operator 'clear cache')."""
    cleared = await app.state.relay.flush()
    app.state.sessions = SessionManager()
    return {"ok": True, **cleared}


# --- sources -------------------------------------------------------------
@app.get("/api/sources", response_model=list[SourceOut])
async def list_sources(enabled_only: bool = False):
    return app.state.registry.list(enabled_only=enabled_only)


@app.post("/api/sources", response_model=SourceOut)
async def create_source(body: SourceIn):
    return app.state.registry.create(body.model_dump())


@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: str):
    app.state.registry.delete(source_id)
    return {"ok": True}


@app.post("/api/sources/{source_id}/enabled")
async def set_source_enabled(source_id: str, enabled: bool):
    app.state.registry.set_enabled(source_id, enabled)
    return {"ok": True}


# --- devices & pairing ---------------------------------------------------
@app.post("/api/pair/start")
async def pair_start(_: DevicePairStart | None = None):
    code = app.state.devices.start_pairing()
    return {"code": code, "ttl_s": DeviceManager.PAIR_TTL}


@app.post("/api/pair/complete", response_model=DeviceOut)
async def pair_complete(body: DevicePairComplete):
    dev = app.state.devices.complete_pairing(body.code, body.name, body.platform)
    if dev is None:
        raise HTTPException(400, "invalid or expired pairing code")
    return dev


@app.get("/api/devices", response_model=list[DeviceOut])
async def list_devices():
    return app.state.devices.list()


@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    app.state.devices.remove(device_id)
    return {"ok": True}


# --- allocation / play ---------------------------------------------------
@app.post("/api/play", response_model=AllocResult)
async def play(device_id: str, source_id: str):
    source = app.state.registry.get(source_id)
    if source is None or not source["enabled"]:
        raise HTTPException(404, "unknown or disabled source")

    # Local files are served directly with range support — no upstream
    # session, no relay, no concurrency cap. They are the user's own media.
    if is_local(source):
        path = local_path(source)
        if not path.is_file() or not app.state.library.contains(path):
            raise HTTPException(404, "media file not found")
        vs = app.state.sessions.start(device_id, source_id, mode="local")
        app.state.devices.touch(device_id)
        return AllocResult(
            ok=True, mode="local", source_id=source_id,
            play_url=f"/media/{source_id}",
            upstream_sessions=app.state.relay.upstream_count(),
        )

    already_open = source_id in {s["source_id"]
                                 for s in app.state.relay.sessions_view()}
    try:
        vs = app.state.sessions.start(device_id, source_id, mode="pending")
        await app.state.relay.acquire(source, vs.id)
    except RelayError as e:
        app.state.sessions.end(vs.id)
        return AllocResult(ok=False, mode="rejected", source_id=source_id,
                           reason=e.detail,
                           upstream_sessions=app.state.relay.upstream_count())
    vs.mode = "shared" if already_open else "independent"
    app.state.devices.touch(device_id)
    return AllocResult(
        ok=True, mode=vs.mode, source_id=source_id,
        play_url=f"/live/{source_id}/index.m3u8",
        upstream_sessions=app.state.relay.upstream_count(),
    )


@app.get("/api/sessions")
async def list_sessions():
    out = []
    for vs in app.state.sessions.list():
        src = app.state.registry.get(vs.source_id)
        dev = app.state.devices.get(vs.device_id)
        out.append({
            "id": vs.id, "mode": vs.mode,
            "source_id": vs.source_id,
            "source_name": src["name"] if src else vs.source_id,
            "device_id": vs.device_id,
            "device_name": dev["name"] if dev else vs.device_id,
            "position_s": vs.position_s,
            "age_s": round(__import__("time").time() - vs.started_at, 1),
        })
    return out


@app.post("/api/sessions/{session_id}/heartbeat")
async def heartbeat(session_id: str, position_s: float | None = None):
    ok = app.state.sessions.heartbeat(session_id, position_s)
    if not ok:
        raise HTTPException(404, "unknown session")
    return {"ok": True}


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str):
    vs = app.state.sessions.end(session_id)
    if vs:
        await app.state.relay.release(vs.source_id, vs.id)
    return {"ok": True}


# --- watch history -------------------------------------------------------
@app.post("/api/history")
async def put_history(body: HistoryIn):
    app.state.db.upsert_history(body.profile_id, body.source_id,
                                body.position_s, body.duration_s)
    return {"ok": True}


@app.get("/api/history")
async def get_history(profile_id: str = "default", limit: int = 20):
    rows = app.state.db.query(
        "SELECT h.*, s.name AS source_name, s.kind FROM watch_history h "
        "LEFT JOIN sources s ON s.id=h.source_id "
        "WHERE h.profile_id=? ORDER BY h.updated_at DESC LIMIT ?",
        (profile_id, limit),
    )
    return [dict(r) for r in rows]


# --- local media library -------------------------------------------------
@app.post("/api/library/rescan")
async def library_rescan():
    return app.state.library.scan()


def _ranged_file(path: Path, range_header: str | None) -> Response:
    """Serve a file with HTTP range support so players can seek. Returns 206
    for a valid Range, 200 for the whole file, 416 for an unsatisfiable range.
    Streams in chunks — never reads the whole movie into memory."""
    size = path.stat().st_size
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    base_headers = {"Accept-Ranges": "bytes"}

    if not range_header or not range_header.strip().lower().startswith("bytes="):
        def full():
            with open(path, "rb") as f:
                while chunk := f.read(_CHUNK):
                    yield chunk
        return StreamingResponse(full(), media_type=ctype,
                                 headers={**base_headers, "Content-Length": str(size)})

    try:
        rng = range_header.split("=", 1)[1]
        start_s, end_s = rng.split("-", 1)
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else size - 1
    except (ValueError, IndexError):
        start, end = 0, size - 1

    if size == 0 or start >= size or start < 0 or start > end:
        return Response(status_code=416,
                        headers={**base_headers, "Content-Range": f"bytes */{size}"})
    end = min(end, size - 1)
    length = end - start + 1

    def ranged():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0 and (chunk := f.read(min(_CHUNK, remaining))):
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        ranged(), status_code=206, media_type=ctype,
        headers={**base_headers, "Content-Length": str(length),
                 "Content-Range": f"bytes {start}-{end}/{size}"})


@app.get("/media/{source_id}")
async def media_file(source_id: str, request: Request):
    source = app.state.registry.get(source_id)
    if source is None or not is_local(source):
        raise HTTPException(404, "unknown local source")
    path = local_path(source)
    # defence in depth: only ever serve inside a configured media root
    if not path.is_file() or not app.state.library.contains(path):
        raise HTTPException(404, "media file not found")
    return _ranged_file(path, request.headers.get("range"))


# --- relay media endpoints ----------------------------------------------
@app.get("/live/{source_id}/index.m3u8")
async def live_playlist(source_id: str):
    source = app.state.registry.get(source_id)
    if source is None:
        raise HTTPException(404, "unknown source")
    try:
        data, ctype = await app.state.relay.get_playlist(source, "web")
    except RelayError as e:
        raise HTTPException(e.status, e.detail)
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "no-cache"})


@app.get("/live/{source_id}/{name}")
async def live_segment(source_id: str, name: str):
    source = app.state.registry.get(source_id)
    if source is None:
        raise HTTPException(404, "unknown source")
    if name.endswith(".m3u8"):
        # nested media playlist (single level) — treat like the index
        try:
            data, ctype = await app.state.relay.get_playlist(source, "web")
        except RelayError as e:
            raise HTTPException(e.status, e.detail)
        return Response(content=data, media_type=ctype)
    try:
        data, ctype = await app.state.relay.get_segment(source, name, "web")
    except RelayError as e:
        raise HTTPException(e.status, e.detail)
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "max-age=30"})


# --- web client (mounted last so /api and /live win) --------------------
if WEB_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
