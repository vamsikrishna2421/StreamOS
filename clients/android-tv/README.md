# StreamOS — Android TV / Fire TV client (scaffold)

**Status: not built in the development environment** (no Android SDK was
available there). This is a complete, conventional project you build on a
machine with the Android SDK. Nothing here claims a produced APK.

## What it is
A minimal Android TV app (Leanback `banner`, D-pad first) that:
1. reads the channel list from the hub (`GET /api/sources?enabled_only=true`),
2. calls `POST /api/play` to open a (possibly shared) upstream session,
3. plays the returned `play_url` with **Media3 / ExoPlayer** (native HLS,
   hardware-decoded H.264/AAC),
4. heartbeats position and posts watch history on exit.

Why Media3/ExoPlayer: first-party, hardware HLS, adaptive, the standard for
Android TV and Fire TV. The hub does the sharing; the client is a thin,
well-behaved player.

## Build
```bash
# with Android Studio Hedgehog+ or command-line SDK
export ANDROID_HOME=~/Android/Sdk
./gradlew :app:assembleDebug          # -> app/build/outputs/apk/debug/app-debug.apk
# install on a device / emulator
adb install -r app/build/outputs/apk/debug/app-debug.apk
```
Set the hub address on first launch (defaults to `http://10.0.2.2:8099` for
the emulator; use the hub's LAN IP on real hardware).

## Requirements
- Android SDK 34, min SDK 23 (covers Fire TV Gen 2+ and Android TV 5.1+)
- JDK 17, Gradle 8.x (wrapper expected; run `gradle wrapper` once)

## Files that matter
- `app/src/main/java/os/stream/tv/MainActivity.kt` — channel grid + player
- `app/src/main/java/os/stream/tv/HubClient.kt` — hub API client
- `app/src/main/AndroidManifest.xml` — Leanback + TV intent filter
