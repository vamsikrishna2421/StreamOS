# Decisions

Each entry: assumption → experiment → observation → decision → status. Newest
decisions reflect evidence gathered in this repo.

### D-01 · Relay over per-stream transcode server
- **Assumption:** we'd need MediaMTX/FFmpeg relaying per stream.
- **Experiment:** built a thin caching HLS proxy instead; benchmarked 10
  concurrent viewers.
- **Observation:** ~65 MB RSS, ~30% of one core, no transcode in the common
  path, 1−1/N upstream reduction achieved.
- **Decision:** caching proxy is the core; transcode is reserved for a future
  compatibility fallback only, not the hot path.
- **Status:** adopted.

### D-02 · Never multiplex one upstream identity across devices
- **Assumption:** the original dropouts were "network instability."
- **Experiment:** M04 with `on_limit=replace`.
- **Observation:** a second device presenting the same identity **evicts** the
  first — a perfect reproduction of the reported symptom, with no network
  fault involved.
- **Decision:** the hub always opens a source once and shares locally; it never
  presents two upstream identities for one source.
- **Status:** adopted; load-bearing.

### D-03 · HLS as the relay protocol
- **Assumption:** could use RTSP/WebRTC/SRT.
- **Observation:** HLS is cache-native (addressable segments + text manifest),
  universally decodable by targets, and the format real IPTV most often
  exposes. Segment-level sharing becomes trivial.
- **Decision:** HLS for the relay; revisit LL-HLS/WebRTC only for latency-
  critical sources.
- **Status:** adopted. Trade-off (segment latency) documented.

### D-04 · SQLite for persistence
- **Decision:** single-file WAL SQLite for sources/devices/history/profiles.
  One household, one writer, trivial backup. No external DB.
- **Status:** adopted.

### D-05 · Capacity exhaustion is a typed result, never a stall
- **Experiment:** C03 global-cap test.
- **Decision:** `/api/play` returns `{ok:false, mode:"rejected", reason}` the
  UI can explain ("All source slots in use"). The relay raises typed
  `RelayError(409/503)`; nothing silently hangs.
- **Status:** adopted.

### D-06 · H.264/AAC for devices; VP9 only for CI browser decode
- **Experiment:** U02/U03 — container Chromium is codec-stripped.
- **Decision:** synthetic device content is H.264/AAC (universal on targets);
  a single VP9/Opus channel exists solely so the headless browser check can
  prove the relay→decode path.
- **Status:** adopted.

### D-07 · Web client first, native clients as scaffolds
- **Assumption:** start with native Android TV + iOS.
- **Observation:** no Android SDK and no macOS in the build environment — a
  native build could be neither compiled nor tested here, only asserted.
- **Decision:** ship a cross-platform web client that actually runs and is
  browser-verified; provide native scaffolds with honest build instructions
  and no fabricated build claims.
- **Status:** adopted; native builds are the next milestone on real tooling.

### D-08 · Derive shared/independent instead of declaring it
- **Decision:** a viewer is `shared` iff the source already had an upstream
  session at join time, else `independent`. No mode flag to keep in sync with
  reality.
- **Status:** adopted.

### D-09 · Pairing-code device enrolment
- **Decision:** devices join only via a 6-digit code the operator sees, TTL
  300 s, single-use. Prevents silent LAN attachment.
- **Status:** adopted. (Transport auth/TLS still open — `KNOWN_LIMITATIONS.md`.)

### D-10 · Keep real-provider integration disabled by default
- **Decision:** no code path contacts a real provider until its permitted
  connection methods and redistribution rights are established and configured
  by the operator. The simulator covers all development needs.
- **Status:** adopted; see `PROVIDER_INTEGRATION.md`.
