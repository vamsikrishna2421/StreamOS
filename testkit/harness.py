"""Reproducible performance harness for StreamOS.

Measures, with real HTTP traffic against a real origin, what sharing
actually buys. For each viewer count N it runs two scenarios:

  direct  — N viewers pull straight from the origin (Architecture A)
  shared  — N viewers pull through the hub relay (Architecture B)

and records origin load, bytes moved, time-to-first-segment (hub-side), and
hub process CPU/RAM. Writes scratch/benchmark.json and prints a table.

Numbers here are produced by running the code, not estimated. Time-to-
first-segment is measured at the HTTP layer (request -> first segment
bytes); real on-device TTFF adds client decoder warm-up on top.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import statistics
import subprocess
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv" / "bin" / "python"


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait(url: str, tries: int = 150) -> bool:
    for _ in range(tries):
        try:
            httpx.get(url, timeout=0.5); return True
        except Exception:
            time.sleep(0.1)
    return False


async def _segments(client: httpx.AsyncClient, base: str) -> list[str]:
    r = await client.get(f"{base}/index.m3u8")
    r.raise_for_status()
    return [ln.strip() for ln in r.text.splitlines()
            if ln.strip() and not ln.startswith("#") and not ln.endswith(".m3u8")]


async def _viewer(client: httpx.AsyncClient, base: str) -> dict:
    """Fetch the whole channel; return per-viewer timing and bytes."""
    t0 = time.perf_counter()
    segs = await _segments(client, base)
    first_dt = None
    total = 0
    for i, s in enumerate(segs):
        r = await client.get(f"{base}/{s}")
        r.raise_for_status()
        total += len(r.content)
        if i == 0:
            first_dt = time.perf_counter() - t0
    return {"ttfs_s": first_dt, "bytes": total, "wall_s": time.perf_counter() - t0}


async def _run_scenario(base: str, source_id: str | None, n: int,
                        hub_url: str | None) -> dict:
    """Run N concurrent viewers against a base URL (origin direct or hub)."""
    limits = httpx.Limits(max_connections=64)
    async with httpx.AsyncClient(limits=limits, timeout=30) as client:
        if hub_url and source_id:
            # register N viewers as playing (acquire upstream session once)
            await client.post(
                f"{hub_url}/api/play",
                params={"device_id": "probe", "source_id": source_id})
        tasks = [_viewer(client, base) for _ in range(n)]
        results = await asyncio.gather(*tasks)
    ttfs = [r["ttfs_s"] for r in results if r["ttfs_s"] is not None]
    return {
        "n": n,
        "ttfs_avg_s": round(statistics.mean(ttfs), 4),
        "ttfs_max_s": round(max(ttfs), 4),
        "client_bytes_total": sum(r["bytes"] for r in results),
        "wall_s": round(max(r["wall_s"] for r in results), 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--viewers", default="1,2,3,5,10")
    ap.add_argument("--channel", default="ch1")
    args = ap.parse_args()
    counts = [int(x) for x in args.viewers.split(",")]

    op, hp = free_port(), free_port()
    env = dict(os.environ, STREAMOS_DATA=str(ROOT / "scratch" / "bench"),
               STREAMOS_MAX_UPSTREAM="8", STREAMOS_SEGMENT_TTL="120")
    subprocess.run(["rm", "-rf", str(ROOT / "scratch" / "bench")])
    origin = subprocess.Popen(
        [str(VENV), str(ROOT / "testkit" / "origin.py"),
         "--content", str(ROOT / "scratch" / "origin"), "--port", str(op)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    hub = subprocess.Popen(
        [str(VENV), "-m", "uvicorn", "streamos.main:app", "--host", "127.0.0.1",
         "--port", str(hp), "--log-level", "warning"],
        cwd=str(ROOT / "hub"), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    origin_url = f"http://127.0.0.1:{op}"
    hub_url = f"http://127.0.0.1:{hp}"
    report: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "channel": args.channel, "rows": []}
    try:
        assert wait(f"{hub_url}/api/health"), "hub did not start"
        assert wait(f"{origin_url}/stats"), "origin did not start"
        src = httpx.post(f"{hub_url}/api/sources", json={
            "name": "Bench", "kind": "live",
            "upstream_url": f"{origin_url}/{args.channel}/index.m3u8"}).json()
        sid = src["id"]
        hub_proc = psutil.Process(hub.pid)
        hub_proc.cpu_percent(None)  # prime

        for n in counts:
            # --- direct scenario ---
            httpx.post(f"{origin_url}/reset")
            direct = asyncio.run(_run_scenario(
                f"{origin_url}/{args.channel}", None, n, None))
            direct_origin = httpx.get(f"{origin_url}/stats").json()

            # --- shared scenario (through hub) ---
            # cold start: clear relay cache so this run measures N *simultaneous*
            # cold viewers, not warm-cache late joiners from a prior N.
            httpx.post(f"{hub_url}/api/relay/flush")
            httpx.post(f"{origin_url}/reset")
            httpx.post(f"{hub_url}/api/metrics/reset")
            cpu0 = hub_proc.cpu_percent(None)
            shared = asyncio.run(_run_scenario(
                f"{hub_url}/live/{sid}", sid, n, hub_url))
            cpu1 = hub_proc.cpu_percent(None)
            shared_origin = httpx.get(f"{origin_url}/stats").json()
            m = httpx.get(f"{hub_url}/api/metrics").json()
            rss_mb = round(hub_proc.memory_info().rss / 1e6, 1)

            du = direct_origin["segment_requests"]
            su = shared_origin["segment_requests"]
            saved = round(100 * (1 - su / du), 1) if du else 0.0
            row = {
                "viewers": n,
                "direct_origin_segment_fetches": du,
                "shared_origin_segment_fetches": su,
                "upstream_fetch_reduction_pct": saved,
                "shared_ttfs_avg_s": shared["ttfs_avg_s"],
                "shared_ttfs_max_s": shared["ttfs_max_s"],
                "hub_downstream_serves": m["metrics"]["counters"]["downstream_segment_serves"],
                "hub_upstream_bytes": m["metrics"]["counters"]["upstream_bytes"],
                "hub_downstream_bytes": m["metrics"]["counters"]["downstream_bytes"],
                "hub_upstream_sessions": m["upstream_sessions"],
                "hub_cpu_pct_during": round(cpu1, 1),
                "hub_rss_mb": rss_mb,
                "shared_wall_s": shared["wall_s"],
            }
            report["rows"].append(row)
            print(f"N={n:2d}  direct_upstream={du:3d}  shared_upstream={su:3d}  "
                  f"reduction={saved:5.1f}%  ttfs_avg={shared['ttfs_avg_s']*1000:6.1f}ms  "
                  f"rss={rss_mb}MB cpu~{cpu1:.0f}%")
    finally:
        hub.terminate(); origin.terminate()

    out = ROOT / "scratch" / "benchmark.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")

    # emit a markdown table for the report doc
    md = ["| Viewers | Direct upstream fetches | Shared upstream fetches | "
          "Reduction | Avg TTFS (ms) | Hub RSS (MB) |",
          "|--:|--:|--:|--:|--:|--:|"]
    for r in report["rows"]:
        md.append(f"| {r['viewers']} | {r['direct_origin_segment_fetches']} | "
                  f"{r['shared_origin_segment_fetches']} | "
                  f"{r['upstream_fetch_reduction_pct']}% | "
                  f"{round(r['shared_ttfs_avg_s']*1000,1)} | {r['hub_rss_mb']} |")
    (ROOT / "scratch" / "benchmark_table.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
