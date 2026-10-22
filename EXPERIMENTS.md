# Experiments

Every experiment is reproducible from this repo. States: **PASS / FAIL /
PARTIAL / BLOCKED / NOT TESTED**. "Evidence" points at the code that proves
it. No experiment here touches a real provider.

## Part M — MAC / portal session mechanics

Run against the local synthetic portal (`portal_sim/portal.py`) with an
injectable clock, so expiry and lockout are deterministic. Mechanisms, not any
provider's wire format. Driver: `tests/test_portal_experiments.py`.

| ID | Hypothesis under test | Result | Observation |
|---|---|---|---|
| M01 | A registered identity can open a session | **PASS** | Registered MAC → token issued, active_count=1 |
| M02 | An unregistered identity is rejected | **PASS** | Unknown MAC → 403, no session |
| M03 | Shared MAC prefix ≠ equivalent registration | **PASS** | Same `00:1A:79` prefix, different suffix → rejected; only the exact registered suffix works. **Disproves** "prefix implies access." |
| M04 | Two devices, one-session policy | **PASS** | `on_limit=reject`: 2nd device → `session_limit`, 1st keeps playing. `on_limit=replace`: 2nd device **evicts** 1st — this reproduces the historical "second device keeps killing the first" dropout pattern. |
| M05 | Multiple registered devices, account-wide cap | **PASS** | 2 registered MACs, `max_sessions=2`: both play; a 3rd concurrent session hits the account cap. Limit is account-wide, not per-device. |
| M06 | Concurrent playback under configurable limits | **PASS** | Parametrized: limit=1 blocks the 2nd stream, limit=2 allows it. |
| M07 | Session expiry and renewal | **PASS** | Renew before expiry extends lifetime; past the renewed expiry the session is invalid and renew fails. |
| M08 | Account block then administrative restore | **PASS** | Blocked → denied and live sessions terminated; after restore, a fresh session opens normally. |
| M09 | Identity collision / ambiguous records | **PASS** | Same MAC registered to two accounts resolves deterministically to exactly one; no duplicate/ambiguous session created. |
| M10 | Enumeration resistance + rate limiting | **PASS** | In `enumeration_safe` mode, unknown-MAC and known-but-blocked-MAC return the *same* opaque `invalid_credentials`. Repeated failures trip a lockout (429) that clears after the window. |

**What M01–M10 told us about the product.** The single most likely cause of
the original "two devices = unreliable playback" is **M04 `replace` (session
stealing)** under a one-session policy — not network instability. The hub's
answer is to never present two upstream identities for one source: it opens
the source **once** and shares locally (Part B), so the provider sees one
well-behaved session that renews on time (M07) and backs off on limits
(M05/M06) instead of two sessions fighting.

## Part B — Shared viewing (one source, many devices)

Driver: `tests/test_relay_sharing.py` + `testkit/harness.py`. Evidence comes
from the **origin's own hit counter**, independent of the hub.

| ID | Experiment | Result | Observation |
|---|---|---|---|
| B01 | 1 / 2 / 3 / 5 devices, one stream | **PASS** | Origin serves each distinct segment exactly once for any N; hub serves N×segments downstream. `upstream_sessions == 1`. |
| B02 | Late joiner after first viewer finished | **PASS** | 2nd device adds **zero** upstream fetches (warm cache). |
| B03 | Viewer disconnect releases session | **PASS** | Ending the viewing session drops it; reaper tears down idle upstream. |
| B04 | N simultaneous **cold** viewers (harness) | **PASS** | Upstream fetches flat at 10 for N∈{1,2,3,5,10}; direct would be 10×N. See `TEST_RESULTS.md`. |

## Part C — Independent viewing & capacity

Driver: `tests/test_independent.py`.

| ID | Experiment | Result | Observation |
|---|---|---|---|
| C01 | Two distinct channels | **PASS** | 2 upstream sessions. |
| C02 | Live + VOD mix | **PASS** | 2 upstream sessions across kinds. |
| C03 | Global cap exhausted | **PASS** | 3rd distinct source under cap=2 → graceful `{ok:false, mode:"rejected", reason:"…limit…"}`, no zombie session. |
| C04 | Shared pair doesn't consume a 2nd slot | **PASS** | Two devices on one channel = 1 slot, leaving room for an independent viewer on another under cap=2. |
| C05 | Non-shareable source refuses 2nd device | **PASS** | `shareable=false` → 2nd viewer rejected with reason. |

## Part U — Client / UI (real browser)

Driver: `scratch/ui_check.py` (Playwright + container Chromium).

| ID | Experiment | Result | Observation |
|---|---|---|---|
| U01 | 12 screens render, D-pad focus model works | **PASS** | 12 nav items, cards/metrics render, screenshots in `scratch/ui_*.png`. |
| U02 | Playback decodes in-browser through the relay | **PASS** | `readyState=4`, `currentTime` advancing, 0 console errors — with a VP9/Opus channel (see note). |
| U03 | H.264/AAC decode in container Chromium | **BLOCKED** | Container Chromium is the open-source build without H.264/AAC. Not a product defect; real targets decode H.264 natively. Worked around with VP9 for the in-browser check. |

## Part D — Network / failure (partial)

| ID | Experiment | Result | Observation |
|---|---|---|---|
| D01 | Upstream fetch failure | **PASS** | Surfaces as `502`, counted in metrics, no crash (`relay.get_segment` error path). |
| D02 | Idle teardown / cleanup | **PASS** | Reaper releases sessions and prunes cache (`relay.reap`). |
| D03 | Packet loss / slow-Wi-Fi emulation (tc/netem) | **NOT TESTED** | Needs NET_ADMIN in container; deferred, documented in `KNOWN_LIMITATIONS.md`. |
| D04 | Hub restart state persistence | **PARTIAL** | Sources/devices/history persist (SQLite); in-flight viewing sessions are in-memory and intentionally reset. |

## Decisions triggered by experiments

- M04 → **never multiplex one upstream identity across devices**; share at the
  hub instead. (DECISIONS D-02)
- B04 → segment-coalescing lock is load-bearing; keep it and measure it in CI.
- C03 → exhaustion must be a typed, graceful result the UI can explain, never
  a stall. (DECISIONS D-05)
- U03 → ship H.264/AAC for devices; keep a VP9 asset only for CI browser
  decode. (DECISIONS D-06)
