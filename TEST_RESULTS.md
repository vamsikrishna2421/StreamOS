# Test Results & Performance Benchmark

Generated from an actual run in the build environment (4 vCPU, 15 GB RAM,
Ubuntu 24.04, Python 3.13, FFmpeg system build). Reproduce with
`python -m pytest` and `python testkit/harness.py`.

## Automated test suite

```
28 passed in ~2.5s
```

| File | Tests | Covers |
|---|--:|---|
| `test_portal_experiments.py` | 12 | M01–M10 portal mechanics |
| `test_relay_sharing.py` | 7 | one-stream-many-devices, late join, disconnect |
| `test_independent.py` | 5 | distinct channels, caps, non-shareable, mix |
| `test_sources_devices.py` | 4 | source CRUD, pairing handshake, history |

## Benchmark: sharing dividend (the headline result)

N **simultaneous cold** viewers of one channel, measured from the origin's
own request counter. "Direct" = each viewer pulls from the origin
(Architecture A). "Shared" = each viewer pulls through the hub relay
(Architecture B). Channel = 10 segments, ~2.29 MB.

| Viewers | Direct upstream fetches | Shared upstream fetches | Reduction | Avg TTFS (ms) | Hub RSS (MB) |
|--:|--:|--:|--:|--:|--:|
| 1 | 10 | 10 | 0.0% | 24.0 | 65.4 |
| 2 | 20 | 10 | 50.0% | 14.5 | 66.5 |
| 3 | 30 | 10 | 66.7% | 14.5 | 68.8 |
| 5 | 50 | 10 | 80.0% | 25.6 | 65.8 |
| 10 | 100 | 10 | 90.0% | 35.2 | 68.3 |

Reduction follows `1 − 1/N` exactly — the theoretical maximum for stream
sharing. The coalescing lock holds under genuinely concurrent load, not just
sequential cache hits.

### Bandwidth: ingress flat, egress linear

| Viewers | Hub ingress (MB, from source) | Hub egress (MB, to devices) | Ratio |
|--:|--:|--:|--:|
| 1 | 2.29 | 2.29 | 1.0× |
| 2 | 2.29 | 4.59 | 2.0× |
| 3 | 2.29 | 6.88 | 3.0× |
| 5 | 2.30 | 11.47 | 5.0× |
| 10 | 2.29 | 22.93 | 10.0× |

**Upstream bandwidth is constant regardless of how many devices watch.** This
is the whole point: the scarce resource (the provider connection) is spent
once; the abundant resource (LAN bandwidth) scales freely.

### Resource cost of the hub

| Metric | Observed |
|---|---|
| RSS serving 10 concurrent viewers | ~65–69 MB |
| CPU during a 10-viewer burst | ~28–37% of one core (transient; relay does no transcode) |
| Wall time, 10 viewers pull full channel | 0.24 s |
| Time-to-first-segment (hub-side), avg | 14–35 ms |

TTFS here is the HTTP-layer figure (play request → first segment bytes).
On-device TTFF adds decoder warm-up, which is client/codec dependent and not
measured in this container.

## In-browser playback verification

`scratch/ui_check.py` drove the web client in the container's Chromium:

| Check | Result |
|---|---|
| 12 navigation screens render | PASS |
| Home cards + diagnostics metrics render | PASS (2 cards, 12 metrics) |
| Video decodes through the relay | PASS — `readyState=4`, `currentTime` advancing |
| Console errors | 0 |

Screenshots: `scratch/ui_home.png`, `scratch/ui_player.png`,
`scratch/ui_diag.png`. H.264/AAC could not be decoded by the container's
open-source Chromium (no proprietary codecs); the in-browser check used a
VP9/Opus channel. Device targets (Android TV, Fire TV, iOS, Chrome, Safari)
all decode the H.264/AAC default natively.

## What is NOT claimed

- No Android APK or iOS IPA was built — the build environment has no Android
  SDK and no macOS/Xcode. The client projects are scaffolds.
- No hardware-device playback test was run.
- No real IPTV provider was contacted; all upstream traffic was synthetic
  content served by the local test origin.
- Netem-based packet-loss/latency matrices (brief §7D) are not yet run; they
  need elevated container networking. See `KNOWN_LIMITATIONS.md`.
