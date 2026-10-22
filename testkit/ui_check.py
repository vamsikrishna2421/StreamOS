"""Headless-browser smoke test of the StreamOS web client.

Launches origin + hub, registers a channel, drives the UI in Chromium, and
confirms the video element actually starts decoding frames through the hub
relay. Produces screenshots. This is a real end-to-end check, not a mock.
"""
import subprocess, sys, time, socket, json, os
from pathlib import Path
import httpx

import glob
ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv" / "bin" / "python"


def _find_chrome() -> str:
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    raise FileNotFoundError("no Chromium under /opt/pw-browsers; set CHROME env")


CHROME = os.environ.get("CHROME") or _find_chrome()


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait(url, tries=100):
    for _ in range(tries):
        try:
            httpx.get(url, timeout=0.5); return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    op, hp = free_port(), free_port()
    env = dict(os.environ, STREAMOS_DATA=str(ROOT / "scratch" / "uicheck"))
    subprocess.run(["rm", "-rf", str(ROOT / "scratch" / "uicheck")])
    origin = subprocess.Popen([str(VENV), str(ROOT / "testkit" / "origin.py"),
                               "--content", str(ROOT / "scratch" / "origin"),
                               "--port", str(op)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    hub = subprocess.Popen([str(VENV), "-m", "uvicorn", "streamos.main:app",
                            "--host", "127.0.0.1", "--port", str(hp),
                            "--log-level", "warning"],
                           cwd=str(ROOT / "hub"), env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = {}
    try:
        assert wait(f"http://127.0.0.1:{hp}/api/health"), "hub did not start"
        assert wait(f"http://127.0.0.1:{op}/stats"), "origin did not start"
        # VP9/Opus channel: the only codecs the container's open-source
        # Chromium can decode, so the in-browser decode check is meaningful.
        httpx.post(f"http://127.0.0.1:{hp}/api/sources", json={
            "name": "Ch1 Live", "kind": "live",
            "upstream_url": f"http://127.0.0.1:{op}/chweb/index.m3u8"})
        httpx.post(f"http://127.0.0.1:{hp}/api/sources", json={
            "name": "Demo VOD", "kind": "vod",
            "upstream_url": f"http://127.0.0.1:{op}/vod1/index.m3u8"})

        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROME, headless=True,
                                         args=["--autoplay-policy=no-user-gesture-required",
                                               "--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            logs = []
            page.on("console", lambda m: (logs.append(m.text),
                     errors.append(m.text) if m.type == "error"
                     and "favicon" not in m.text else None))
            page.goto(f"http://127.0.0.1:{hp}/", wait_until="networkidle")

            nav = page.query_selector_all(".nav-item")
            results["nav_items"] = len(nav)
            page.wait_for_selector(".card", timeout=5000)
            results["home_cards"] = len(page.query_selector_all(".card"))
            page.screenshot(path=str(ROOT / "scratch" / "ui_home.png"))

            # go to Live TV and play the first channel
            page.click('.nav-item[data-route="live"]')
            page.wait_for_selector(".card", timeout=5000)
            page.click(".card")
            page.wait_for_selector("#player.open", timeout=5000)
            # let the relay feed a few segments into the decoder
            started = False
            for _ in range(60):
                ct = page.evaluate("document.getElementById('pl-video').currentTime")
                rs = page.evaluate("document.getElementById('pl-video').readyState")
                if ct and ct > 0.3 and rs >= 2:
                    started = True; break
                time.sleep(0.25)
            results["video_currentTime"] = page.evaluate("document.getElementById('pl-video').currentTime")
            results["video_readyState"] = page.evaluate("document.getElementById('pl-video').readyState")
            results["playback_started"] = started
            page.screenshot(path=str(ROOT / "scratch" / "ui_player.png"))

            # diagnostics screen renders live metrics
            page.keyboard.press("Escape")
            page.click('.nav-item[data-route="diagnostics"]')
            page.wait_for_selector(".metric", timeout=5000)
            results["diag_metrics"] = len(page.query_selector_all(".metric"))
            page.screenshot(path=str(ROOT / "scratch" / "ui_diag.png"))
            results["console_errors"] = errors
            results["hls_logs"] = [l for l in logs if "HLS_ERR" in l]
            browser.close()

        stats = httpx.get(f"http://127.0.0.1:{op}/stats").json()
        results["origin_segment_requests"] = stats["segment_requests"]
    finally:
        hub.terminate(); origin.terminate()
    print(json.dumps(results, indent=2))
    ok = (results.get("playback_started") and results.get("nav_items") == 12
          and not results.get("console_errors"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
