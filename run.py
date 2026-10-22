#!/usr/bin/env python3
"""StreamOS one-command launcher (macOS, Windows, Linux).

What it does, in order:
  1. creates a private Python environment (first run only),
  2. installs the hub's dependencies into it (first run only),
  3. finds your movies folder (or you point it at one),
  4. starts the hub,
  5. opens it in your web browser.

Usage:
    python run.py                     # auto-detect your Movies/Videos folder
    python run.py --media "D:/Films"  # use a specific folder of videos
    python run.py --lan               # also let other devices on your Wi-Fi watch
    python run.py --port 9000         # use a different port

Stop it with Ctrl+C. Only the Python standard library is used here, so it
runs before anything is installed.
"""
from __future__ import annotations

import argparse
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def say(msg: str) -> None:
    print(f"  {msg}", flush=True)


def ensure_env() -> Path:
    py = venv_python()
    if not py.exists():
        say("Setting up (first run only — this takes about a minute)...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    # install/update deps (fast no-op once satisfied)
    say("Checking dependencies...")
    r = subprocess.run(
        [str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check",
         "-r", str(ROOT / "hub" / "requirements.txt")],
    )
    if r.returncode != 0:
        say("Dependency install failed. Are you online? Try again.")
        sys.exit(1)
    return py


def detect_media(explicit: str | None) -> str | None:
    """Return an ABSOLUTE media folder path, or None. Absolute matters:
    the hub resolves relative paths against its own working dir, not yours."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            say(f"Note: '{explicit}' is not a folder — ignoring it.")
            return None
        return str(p.resolve())
    home = Path.home()
    for name in ("Movies", "Videos"):          # macOS uses Movies; Win/Linux Videos
        cand = home / name
        if cand.is_dir():
            return str(cand.resolve())
    return None


def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def wait_health(url: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Launch the StreamOS hub.")
    ap.add_argument("--media", help="folder of your video files")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--lan", action="store_true",
                    help="allow other devices on your network to watch")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    print("\nStreamOS\n" + "-" * 40)
    py = ensure_env()

    media = detect_media(args.media)
    if media:
        say(f"Your videos: {media}")
    else:
        say("No movies folder given. The bundled welcome video will be shown.")
        say("Tip: python run.py --media \"<path to your movies>\"")

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    port = free_port(args.port)

    env = dict(os.environ)
    env["STREAMOS_DATA"] = str((ROOT / ".streamos-data").resolve())
    if media:
        env["STREAMOS_MEDIA"] = media

    cmd = [str(py), "-m", "uvicorn", "streamos.main:app",
           "--app-dir", str(ROOT / "hub"), "--host", host, "--port", str(port),
           "--log-level", "warning"]
    say("Starting the hub...")
    hub = subprocess.Popen(cmd, env=env)

    local_url = f"http://127.0.0.1:{port}"
    if not wait_health(f"{local_url}/api/health"):
        say("The hub did not start. See the messages above.")
        hub.terminate()
        sys.exit(1)

    print("-" * 40)
    print(f"  StreamOS is running.  Open:  {local_url}")
    if args.lan:
        ip = _lan_ip()
        if ip:
            print(f"  On other devices (same Wi-Fi):  http://{ip}:{port}")
    print("  Press Ctrl+C here to stop.")
    print("-" * 40 + "\n")

    if not args.no_browser:
        try:
            webbrowser.open(local_url)
        except Exception:
            pass

    try:
        hub.wait()
    except KeyboardInterrupt:
        say("Stopping...")
        hub.terminate()
        try:
            hub.wait(timeout=5)
        except Exception:
            hub.kill()


def _lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))     # no packets sent; just picks the egress IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


if __name__ == "__main__":
    main()
