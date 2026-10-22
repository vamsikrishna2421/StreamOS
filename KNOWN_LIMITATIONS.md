# Known Limitations

Honest list of what is not done, not tested, or constrained. Nothing here is
hidden behind a passing test.

## Build-environment constraints (why some deliverables are scaffolds)
- **No Android SDK** in the container → the Android TV app cannot be compiled
  or run here. `clients/android-tv/` is a project scaffold with build
  instructions; no APK exists.
- **No macOS / Xcode** → the iOS app cannot be built. `clients/ios/` is a
  SwiftUI scaffold with instructions; no IPA exists.
- **Container Chromium lacks H.264/AAC** (open-source build) → the in-browser
  decode check uses a VP9/Opus channel. Device targets decode H.264/AAC
  natively; this is an environment limit, not a product one.
- **No NET_ADMIN** → the packet-loss / latency / bandwidth-cap matrix (brief
  §7D) via `tc`/`netem` is not run. The relay's failure paths (upstream 502,
  idle teardown) are tested; degraded-network behaviour is not yet measured.

## Relay / protocol
- **Media playlists only, single variant.** Master playlists with multiple
  bitrate variants (ABR) pass the top-level manifest through but nested
  variant selection is not yet relayed per-variant. MAP/KEY/MEDIA URIs are
  rewritten to basenames, which assumes flat segment naming (true for the
  test origin and most IPTV HLS; nested per-variant paths with colliding
  basenames are a gap).
- **No transcode / remux fallback.** A source whose codecs a given client
  can't decode is not transcoded. Planned as an explicit, opt-in path.
- **In-memory cache.** Segment cache is per-process; a hub restart is a cold
  cache (sources/devices/history persist, viewing sessions do not).
- **AES-128 HLS keys** are rewritten in the manifest but key relaying/caching
  is untested; encrypted upstreams are out of scope until provider
  integration is defined.

## Security
- **Protected against the browser-based attacks, but not yet token-authed.**
  The hub now enforces a **Host allowlist** (blocks DNS-rebinding), **refuses
  cross-origin writes** (blocks CSRF from a random web page), restricts
  `upstream_url` to `http(s)` (no `file://` arbitrary-file read via the API),
  and only serves playable files inside a configured media root. What is still
  missing: a **per-install access token**. So on `--lan`, any device already
  on your trusted Wi-Fi can use the API without a password. Keep the hub on a
  network you trust; do not port-forward it to the internet (use a VPN). TLS
  is also not yet configured.
- **Pairing** proves possession of a code shown on the hub, but the transport
  is plain HTTP on the LAN; a hostile LAN is not in the threat model yet.
- **No per-device authorization on media URLs** — any device on the allowed
  network that knows `/live/{sid}/…` or `/media/{id}` can fetch while valid.

## UX / features
- Favorites are stored client-side (localStorage), not yet synced via the
  `favorites` table that exists in the schema.
- Movies vs Series split is by `group_name` with a fallback to "all VOD"; no
  real metadata/EPG ingestion yet.
- No EPG, no search, no recommendations engine (listed in `FEATURES.md` as
  evaluated-not-built).

## Testing
- Load tested to 10 concurrent viewers in-process; not tested at dozens of
  real devices on real Wi-Fi.
- TTFF is measured hub-side (HTTP), not end-to-end on a device decoder.
- Long-run soak / memory-leak testing not performed.
