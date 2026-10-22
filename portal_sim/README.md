# Mock IPTV Portal Simulator

A **local, synthetic** model of how MAG/Stalker/Ministra-style MAC-based
portals handle device identity and sessions. It exists so that portal
*mechanisms* can be studied and the hub can be made a well-behaved client
without ever touching a real portal.

It is **not** a Stalker-compatible client and does **not** reproduce any
provider's wire protocol. It models the state machine. All accounts and MAC
identities are invented and live only in memory.

## What it models, and how it maps to real concepts
| Simulator concept | Real-world counterpart |
|---|---|
| `Account(status, max_sessions, on_limit, fingerprint_required)` | A subscription and its concurrency/registration policy |
| `register(account, Identity(mac,serial,device_id))` | Binding a device identity to a subscription at the portal |
| `open_session` | Portal handshake/authorization that yields a session token |
| `renew_session` / `ttl` | Periodic session keep-alive the player must send |
| `on_limit = reject` | Portal refuses a session beyond the allowance |
| `on_limit = replace` | "Session stealing": a new login evicts an older one |
| `enumeration_safe` | Returning opaque errors so outsiders can't probe which accounts/MACs exist |
| rate limit + lockout | Portal throttling repeated failed authorizations |

## Why `on_limit = replace` matters
Experiment **M04** shows that under a one-session policy with `replace`, a
second device presenting the same identity evicts the first. That reproduces
the historical "two devices → playback keeps dropping" symptom **without any
network fault**. The hub's design conclusion: never present two upstream
identities for one source — open it once and share locally.

## Deliberate design choice: opaque failures by default
`enumeration_safe=True` (default) makes every authorization failure return the
same `invalid_credentials`, so an unknown MAC and a known-but-blocked MAC are
indistinguishable from outside. Turn it off only to study the weaker behaviour
of a portal that leaks specific reasons (used for contrast in M08/M10).

## Run it
```bash
# as a library (what the tests do)
python -c "from portal_sim.portal import MockPortal, Identity; \
p=MockPortal(); p.create_account('a'); p.register('a', Identity(mac='00:1A:79:AA:BB:01')); \
print(p.open_session(Identity(mac='00:1A:79:AA:BB:01')))"

# as an HTTP service (for the harness / a diagnostics UI)
python -m portal_sim.server      # :8200
```

## Experiments
All ten (M01–M10) are automated in `tests/test_portal_experiments.py` and
documented in `../EXPERIMENTS.md`. They cover registration, rejection,
prefix-independence, concurrency policies, multi-device accounts, expiry/
renewal, block/restore, identity collision, enumeration resistance, and rate
limiting.

## Boundary
This tool is for understanding and for building a compatible, polite client.
It must never be pointed at, or used to probe, a real provider.
