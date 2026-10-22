"""Verify a LOCAL movie file plays in the browser through the hub.

Starts the hub with a media folder, opens the web client, plays the local
file, and confirms the video element decodes it with working seek (range
requests). Uses a WebM fixture because the container browser lacks H.264;
on a real laptop the shipped MP4 plays the same way.
"""
import glob, json, os, socket, subprocess, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv" / "bin" / "python"


def find_chrome():
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",):
        h = sorted(glob.glob(pat))
        if h:
            return h[-1]
    raise FileNotFoundError("no chromium")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait(url, n=150):
    for _ in range(n):
        try:
            httpx.get(url, timeout=0.5); return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    media = ROOT / "scratch" / "mymovies"
    assert (media / "MyMovie.webm").exists(), "run the webm fixture step first"
    hp = free_port()
    env = dict(os.environ, STREAMOS_DATA=str(ROOT / "scratch" / "localcheck"),
               STREAMOS_MEDIA=str(media.resolve()))
    subprocess.run(["rm", "-rf", str(ROOT / "scratch" / "localcheck")])
    hub = subprocess.Popen(
        [str(VENV), "-m", "uvicorn", "streamos.main:app", "--host", "127.0.0.1",
         "--port", str(hp), "--log-level", "warning"],
        cwd=str(ROOT / "hub"), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {}
    try:
        assert wait(f"http://127.0.0.1:{hp}/api/health"), "hub did not start"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=find_chrome(), headless=True,
                                   args=["--autoplay-policy=no-user-gesture-required",
                                         "--no-sandbox"])
            page = b.new_page(viewport={"width": 1280, "height": 720})
            errs = []
            page.on("console", lambda m: errs.append(m.text)
                    if m.type == "error" and "favicon" not in m.text else None)
            page.goto(f"http://127.0.0.1:{hp}/", wait_until="networkidle")
            page.click('.nav-item[data-route="movies"]')
            page.wait_for_selector(".card", timeout=5000)
            # click the card whose title contains MyMovie
            page.click(".card:has-text('MyMovie')")
            page.wait_for_selector("#player.open", timeout=5000)
            started = False
            for _ in range(60):
                ct = page.evaluate("document.getElementById('pl-video').currentTime")
                rs = page.evaluate("document.getElementById('pl-video').readyState")
                if ct and ct > 0.3 and rs >= 2:
                    started = True; break
                time.sleep(0.25)
            # exercise seek (range request): jump to 3s and confirm it moves
            page.evaluate("document.getElementById('pl-video').currentTime = 3.0")
            time.sleep(1.0)
            seeked = page.evaluate("document.getElementById('pl-video').currentTime")
            out["playback_started"] = started
            out["readyState"] = page.evaluate("document.getElementById('pl-video').readyState")
            out["seeked_to"] = round(seeked, 2)
            out["seek_works"] = seeked > 2.0
            out["console_errors"] = errs
            page.screenshot(path=str(ROOT / "scratch" / "ui_localmovie.png"))
            b.close()
    finally:
        hub.terminate()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("playback_started") and out.get("seek_works")
             and not out.get("console_errors") else 1)


if __name__ == "__main__":
    main()
