# Feature Discovery & Evaluation

Features beyond "play a stream," each weighed on user benefit, feasibility,
complexity, performance, security, maintenance, and whether it belongs in the
first release. **Built** = implemented and tested here. Reliable playback was
never traded for any of these.

## Built in this release
| Feature | Why it earns its place | Notes |
|---|---|---|
| **Stream sharing (1 upstream → N devices)** | The core differentiator; directly addresses the concurrency limit. | 1−1/N upstream reduction, measured. |
| **Capacity-aware source allocation** | Turns "it randomly stops working" into "all slots in use," explained. | Typed rejection, no stalls. |
| **Continue Watching across devices** | Start on the TV, finish on the phone. | Server-side watch history; any device reads it. |
| **Pairing-code device setup** | No typing URLs on a TV remote; blocks silent LAN joins. | 6-digit, single-use, TTL. |
| **Live diagnostics dashboard** | A home appliance should show its own health. | Upstream sessions, cache hit ratio, bandwidth, TTFS, host CPU/RAM. |
| **Shared / Independent viewing screens** | Makes the invisible visible: who is watching what, and how. | Derived from live session state. |
| **D-pad + touch one codebase** | Works on a TV remote and an iPhone without two UIs. | Spatial focus navigation. |
| **Local-vendored player** | Plays LAN streams with no internet dependency. | hls.js served from the hub. |
| **Self-falsifying measurement** | Every sharing claim is checkable from the origin side. | Instrumented origin + harness. |

## Evaluated, deferred (with reasoning)
| Feature | Benefit | Why not first release |
|---|---|---|
| **mDNS/zeroconf hub discovery** | Devices find the hub automatically | High benefit, medium effort; next up. No protocol risk. |
| **EPG integration** | Live guide | Needs a data source + ingestion; large surface. |
| **Watch parties / synced playback across screens** | Social; novel | Needs a sync/clock protocol (WebSocket drift correction). Real work; strong candidate for v2. |
| **Favorites sync** | Cross-device stars | Schema exists; endpoints not wired. Small, soon. |
| **Multi-profile households** | Per-person history/favorites | Schema has `profiles`; UI not built. |
| **Adaptive bitrate relay (ABR)** | Quality on poor Wi-Fi | Requires multi-variant relay (see limitations). Valuable, non-trivial. |
| **Offline download for owned content** | Travel | Rights-sensitive; only for content explicitly allowed. |
| **Remote (phone-as-remote) control of the TV** | Convenience | Needs a device-to-device command channel. |
| **Transcode fallback for incompatible codecs** | Compatibility | FFmpeg present; CPU cost per stream; make it opt-in. |
| **Recommendations from local history** | Discovery | Only worth it after a real catalog exists. |
| **Low-power / idle mode** | NAS/Pi power draw | Reaper already releases idle sessions; a deeper sleep is a refinement. |

## Explicitly rejected (for now)
- **Per-stream transcode-everything relay** — kills the low-CPU property that
  makes the hub cheap; only transcode on demand.
- **Internet exposure without auth/TLS** — unsafe; LAN + VPN instead.
- **Flashy animated UI over reliable zapping** — the brief's own warning; the
  UI stays fast and remote-navigable.
