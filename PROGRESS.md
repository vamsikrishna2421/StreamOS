# Progress

## Milestones
- [x] **M0 — Environment inspected.** 4 vCPU / 15 GB / Ubuntu 24.04; Python
  3.13, Node 22, Go 1.24, FFmpeg (libx264/vp9/aac/opus), Docker, gradle/java,
  Chromium. No Android SDK, no macOS. (→ shaped D-07.)
- [x] **M1 — Synthetic test environment.** Instrumented origin + FFmpeg
  synthetic channels (2 live + 1 VOD, no copyrighted media) + VP9/Opus
  browser-decode channel.
- [x] **M2 — Portal simulator.** State machine + HTTP facade; experiments
  M01–M10 automated and passing.
- [x] **M3 — Streaming relay PoC.** Segment coalescing + TTL cache; shared and
  independent viewing working with typed capacity handling.
- [x] **M4 — Measured.** Harness proves 1−1/N upstream reduction, flat
  ingress, ~65 MB RSS; 28/28 tests green.
- [x] **M5 — Architecture selected on evidence.** Caching relay (B) + hybrid
  per-source policy (C) + web client (E). See `DECISIONS.md`.
- [x] **M6 — Web client.** 12 screens, D-pad + touch, browser-verified
  playback through the relay.
- [x] **M7 — Documentation set.** README, ARCHITECTURE, EXPERIMENTS,
  DECISIONS, TEST_RESULTS, KNOWN_LIMITATIONS, DEPLOYMENT,
  PROVIDER_INTEGRATION, FEATURES.
- [~] **M8 — Native clients.** Android TV + iOS **scaffolds** committed with
  build instructions; not buildable in this environment.
- [ ] **M9 — Degraded-network matrix** (needs NET_ADMIN).
- [ ] **M10 — mDNS discovery, favorites/profile sync, watch parties.**
- [ ] **M11 — Real provider adapter** (blocked on permissions —
  `PROVIDER_INTEGRATION.md`).

## Current state
Working, tested local streaming hub with shared + independent viewing, a
synthetic portal simulator, a browser-verified cross-platform client, and a
reproducible benchmark. Native app builds and real-provider integration are
the honest open items.

## Test status
`28 passed`. Benchmark reproducible via `python testkit/harness.py`.
UI check via `python scratch/ui_check.py` (regenerate from `testkit/`).

## Next actions (in order)
1. Build the Android TV app on a machine with the Android SDK (Media3/ExoPlayer
   client against `/live/{sid}/index.m3u8`); produce a real APK.
2. mDNS hub advertisement + client auto-discovery.
3. Wire favorites/profiles endpoints to the existing schema.
4. Degraded-network test matrix with `tc netem`.
5. Define and implement the first real-provider adapter once permissions are
   confirmed.
