"""Instrumented origin server — the 'provider' stand-in for experiments.

Serves a content directory as plain HTTP and counts every request per path.
The counts let an experiment prove, from the origin's own point of view,
how many times the hub actually pulled each segment upstream — independent
of whatever the hub reports about itself.

This serves only local synthetic files. It is a measurement fixture, not a
reimplementation of any provider's portal.
"""
from __future__ import annotations

import argparse
import threading
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

app = FastAPI(title="StreamOS test origin")
_lock = threading.Lock()
_hits: dict[str, int] = defaultdict(int)
_CONTENT = Path("./scratch/origin").resolve()


def set_content_root(p: Path) -> None:
    global _CONTENT
    _CONTENT = p.resolve()


@app.get("/stats")
def stats():
    with _lock:
        total = sum(_hits.values())
        seg_ext = (".ts", ".m4s")
        segs = {k: v for k, v in _hits.items() if k.endswith(seg_ext)}
        pls = {k: v for k, v in _hits.items() if k.endswith(".m3u8")}
        return {
            "total_requests": total,
            "segment_requests": sum(segs.values()),
            "playlist_requests": sum(pls.values()),
            "distinct_segments": len(segs),
            "by_path": dict(sorted(_hits.items())),
        }


@app.post("/reset")
def reset():
    with _lock:
        _hits.clear()
    return {"ok": True}


@app.get("/{path:path}")
def serve(path: str):
    target = (_CONTENT / path).resolve()
    # containment check: never serve outside the content root
    if not str(target).startswith(str(_CONTENT)):
        raise HTTPException(403, "path escapes content root")
    if not target.is_file():
        raise HTTPException(404, "not found")
    with _lock:
        _hits[path] += 1
    ctype = ("application/vnd.apple.mpegurl" if path.endswith(".m3u8")
             else "video/MP2T" if path.endswith(".ts")
             else "application/octet-stream")
    return Response(content=target.read_bytes(), media_type=ctype)


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default="./scratch/origin")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()
    set_content_root(Path(args.content))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
