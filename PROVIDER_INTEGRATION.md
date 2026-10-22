# Provider Integration Requirements

Real-provider integration is **deliberately disabled**. Nothing in StreamOS
contacts a real IPTV provider. This document states what must be true, and
what the operator must supply, before it is enabled — and how the hub would
behave in each permitted case.

## Hard rules (do not violate)
- **Never modify the existing working TV registration** without explicit,
  separate approval. Development and all testing use the local simulator and
  synthetic content.
- No MAC enumeration, no identity guessing, no using another customer's
  identity, no DRM circumvention, no concealing upstream sessions.
- Enable a real source only after the provider's permitted connection method
  and redistribution rights for that source are established in writing/config
  by the operator.

## What must be established first
1. **Permitted connection method** — a provider-issued playlist (e.g. M3U/
   Xtream output the provider gives you), a documented third-party-player
   configuration, or an explicitly supported portal mode. The hub consumes a
   URL; the operator is responsible for it being an authorized one.
2. **Concurrent-connection allowance** — the real number of simultaneous
   upstream sessions permitted. This becomes `STREAMOS_MAX_UPSTREAM` and each
   source's `max_sessions`.
3. **Local redistribution rights** — whether relaying one upstream to multiple
   household devices is permitted. This sets each source's `shareable` flag.
4. **Registration/device allowance** — how many devices may be registered,
   and whether the hub counts as one device or a relay.

## Behaviour per permission outcome
| Provider permits | StreamOS configuration | Result |
|---|---|---|
| One stream, no redistribution | `max_upstream=1`, source `shareable=false` | One device at a time; others get a clear "source in use." |
| One stream, redistribution OK | `max_upstream=1`, source `shareable=true` | **Shared viewing**: many devices, one upstream session. |
| Multiple streams | `max_upstream=N` | **Independent viewing** up to N; hybrid sharing within that. |
| Unclear | integration stays **disabled** | Everything else (local media, authorized test sources) keeps working. |

## How integration will be wired (when enabled)
- The source's `upstream_url` points at the provider-authorized playlist.
- A small, source-specific **adapter** (not yet written) handles any
  handshake/renewal the authorized method documents — modelled on, and
  tested against, the local simulator's state machine (`portal_sim/`), which
  already covers registration, renewal (M07), concurrency (M05/M06), blocking
  recovery (M08), and correct back-off on limits.
- The hub presents **one** well-behaved upstream session per source and shares
  locally, which is the configuration least likely to trip concurrency
  policies (the simulator showed session-stealing, not the network, as the
  likely cause of the original dropouts — `EXPERIMENTS.md` M04).

## Until then
The product is fully usable with:
- local media you own,
- properly licensed demonstration streams,
- the bundled synthetic test channels and VOD.

No feature except live real-provider playback depends on this integration.
