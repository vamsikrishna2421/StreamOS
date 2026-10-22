# StreamOS — iOS / iPhone client (scaffold)

**Status: not built in the development environment** (iOS builds require
macOS + Xcode, which were not available). This is a conventional SwiftUI app
you open and run in Xcode. No IPA was produced and no device test was run.

## What it is
A SwiftUI app that lists the hub's channels, calls `POST /api/play`, and plays
the returned `play_url` with **AVPlayer** — iOS's native, hardware-accelerated
HLS player (the right choice on Apple platforms; `hls.js` is not needed).

## Build & run
Option A — XcodeGen (recommended, project file not checked in):
```bash
brew install xcodegen
cd clients/ios
xcodegen generate          # creates StreamOS.xcodeproj from project.yml
open StreamOS.xcodeproj     # Run on a simulator or a device
```
Option B — New Xcode project: create an iOS App (SwiftUI), then add the files
under `StreamOS/` and the `NSAppTransportSecurity` keys from `Info.plist`.

Set the hub address in `HubClient.swift` (`baseURL`) to your hub's LAN IP, or
`http://localhost:8099` on the simulator.

## Notes
- `Info.plist` allows cleartext HTTP to the LAN hub (`NSAllowsLocalNetworking`).
  For a production build, serve the hub over HTTPS and remove the exception.
- Install to a personal device needs a free Apple Developer signing identity;
  TestFlight/App Store distribution needs a paid account. Documented, not
  assumed.
