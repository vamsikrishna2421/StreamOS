"""Generate synthetic HLS content for experiments.

All content is generated from FFmpeg's built-in test sources — colour
patterns and sine tones. Nothing here is copyrighted and nothing is
downloaded. Two distinguishable live-style channels plus one VOD asset, as
the brief's experimental environment requires.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

# (dir, label, pattern, hz, seconds, seg_seconds)
CHANNELS = [
    ("ch1", "StreamOS Test Ch 1", "testsrc2", 440, 20, 2),
    ("ch2", "StreamOS Test Ch 2", "smptebars", 660, 20, 2),
]
VOD = ("vod1", "StreamOS Demo VOD", "mandelbrot", 220, 30, 4)


def _gen(root: Path, name: str, label: str, pattern: str,
         hz: int, seconds: int, seg: int) -> int:
    out = root / name
    out.mkdir(parents=True, exist_ok=True)
    vf = (f"{pattern}=size=640x360:rate=25"
          if pattern != "smptebars" else f"{pattern}=size=640x360:rate=25")
    drawtext = (f"drawtext=text='{label} %{{pts\\:hms}}':x=20:y=20:"
                f"fontsize=20:fontcolor=white:box=1:boxcolor=black@0.5")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"{vf}",
        "-f", "lavfi", "-i", f"sine=frequency={hz}:sample_rate=48000",
        "-t", str(seconds),
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "veryfast", "-g", "50",
        "-c:a", "aac", "-b:a", "96k",
        "-f", "hls", "-hls_time", str(seg), "-hls_list_size", "0",
        "-hls_segment_filename", str(out / "seg_%03d.ts"),
        str(out / "index.m3u8"),
    ]
    subprocess.run(cmd, check=True)
    segs = list(out.glob("seg_*.ts"))
    return len(segs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="./scratch/origin")
    args = ap.parse_args()
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, label, pattern, hz, secs, seg in CHANNELS:
        n = _gen(root, name, label, pattern, hz, secs, seg)
        print(f"{name}: {n} segments ({label})")
        total += n
    name, label, pattern, hz, secs, seg = VOD
    n = _gen(root, name, label, pattern, hz, secs, seg)
    print(f"{name}: {n} segments ({label}) [VOD]")
    total += n
    print(f"total segments: {total}")
    print(f"content root: {root.resolve()}")


if __name__ == "__main__":
    main()
