# StreamOS

> **Just want to watch something on your laptop?** Read
> **[GETTING_STARTED.md](GETTING_STARTED.md)** — one prompt, one command, no
> technical steps.

A local **household streaming hub**. It takes the authorized streams you
already have the right to watch and makes them behave like a modern media
platform across every screen in the house: one upstream source can feed many
devices (shared viewing), different devices can watch different things
(independent viewing), and the hub manages the available source capacity in
between.

StreamOS is not a tool for getting around anyone's access controls. It does
not probe, enumerate, or authenticate against a third-party provider on its
own, it does not defeat DRM, and it ships with a **local, synthetic** portal
simulator so the behaviour of MAC-based IPTV systems can be studied without
touching a real one. See [Scope and boundaries](#scope-and-boundaries).

---

## What works today (measured, not promised)

| Capability | State | Evidence |
|---|---|---|
| One stream → many devices, ~1× upstream | **Working** | 90% upstream-fetch reduction at 10 viewers — `TEST_RESULTS.md` |
| Independent viewing + concurrency caps | **Working** | `tests/test_independent.py` |
| Graceful rejection when sources exhausted | **Working** | `tests/test_independent.py::test_global_cap_rejects_gracefully` |
| MAC/session mechanics (M01–M10) | **Working** | `tests/test_portal_experiments.py` (10 experiments) |
| Web client, 12 screens, D-pad + touch | **Working** | browser-verified playback — `scratch/ui_*.png` |
| Device pairing, watch history, diagnostics | **Working** | `tests/test_sources_devices.py` |
| Android TV app | **Scaffold only** | no Android SDK in build env — `clients/android-tv/` |
| iOS app | **Scaffold only** | needs macOS/Xcode — `clients/ios/` |
| Real provider integration | **Deliberately disabled** | pending permissions — `PROVIDER_INTEGRATION.md` |

28/28 automated tests pass. Nothing above claims a build or a device test
that was not actually run.

---

## Quick start

```bash
# 1. environment
python3 -m venv .venv && . .venv/bin/activate
pip install -r hub/requirements.txt

# 2. generate synthetic test content (FFmpeg, no copyrighted media)
python testkit/make_content.py --root ./scratch/origin

# 3. run the test origin (stands in for a provider) on :8100
python testkit/origin.py --content ./scratch/origin --port 8100 &

# 4. run the hub on :8099
cd hub && python -m uvicorn streamos.main:app --port 8099

# 5. open the client
#    http://localhost:8099  — add a source pointing at
#    http://127.0.0.1:8100/ch1/index.m3u8  under "Streaming Sources"
```

Reproduce the benchmark: `python testkit/harness.py`.
Run the tests: `python -m pytest`.

---

## How the sharing works (the one idea that matters)

A MAG/Stalker-style provider counts **connections to the source**, not
devices in your home. Five TVs each opening the upstream stream look like
five sessions. The hub opens each source **once** and fans the already-
fetched media out locally:

```
          ┌─────────── StreamOS hub ───────────┐
provider  │  relay: 1 fetch/segment, cached     │   TV
  source ─┼─▶ segment cache ◀── per-key locks ──┼─▶ phone
 (1 conn) │  session/cap manager                │   tablet
          └─────────────────────────────────────┘   (N devices)
```

Two mechanisms make it true and measurable:
1. **Per-segment coalescing locks** — simultaneous misses for the same
   segment collapse into one upstream fetch.
2. **Short-TTL cache** — steady-state requests are absorbed, so upstream
   fetches track the number of distinct segments, not the viewer count.

The result is exactly `1 − 1/N` upstream reduction (the theoretical maximum
for stream sharing), confirmed by the origin's own request counter.

---

## Repository layout

```
hub/streamos/      the hub: relay, sessions, sources, API, web client
portal_sim/        local synthetic MAG/Stalker-style portal + state machine
testkit/           instrumented origin, synthetic content, benchmark harness
tests/             28 tests incl. experiments M01–M10 and sharing proofs
clients/           Android TV + iOS project scaffolds (not built here)
docs/ + *.md       architecture, experiments, decisions, results, deployment
```

---

## Scope and boundaries

- All experiments run against **local synthetic** content and a **local
  mock portal**. The hub never contacts a real provider on its own.
- The mock portal uses **invented** accounts and MAC identities. It
  reproduces the *state machine* of MAC-based portals, not any provider's
  wire protocol, and is not a Stalker-compatible client.
- No identity guessing, no MAC enumeration, no DRM circumvention, no hiding
  of upstream sessions. Real integration stays disabled until the provider's
  permitted connection methods and redistribution rights are established —
  see `PROVIDER_INTEGRATION.md`.

Documentation index: `ARCHITECTURE.md` · `EXPERIMENTS.md` · `DECISIONS.md` ·
`TEST_RESULTS.md` · `KNOWN_LIMITATIONS.md` · `DEPLOYMENT.md` ·
`PROVIDER_INTEGRATION.md` · `FEATURES.md` · `PROGRESS.md`.
