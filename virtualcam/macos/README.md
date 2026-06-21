# AK Virtual Camera — macOS (Phase 4 scaffold)

> **Status: SCAFFOLD — not buildable without a Mac.** Every uncertain API
> call site is marked `// VERIFY`. See `docs/phase4/` for the full design.

This directory contains the macOS port of the AK Virtual Camera: a
CoreMediaIO **Camera Extension** (System Extension) that reads NV12 frames
from a POSIX shared-memory ring written by the Python producer
(`camera-core/src/akvc/core/frame_sink/macos_shm.py`).

## Layout

```
virtualcam/macos/
├── project.yml                 # XcodeGen project spec → .xcodeproj
├── framebus/                   # Portable C consumer (POSIX shm)
│   ├── include/akvc/framebus_posix.h
│   └── src/framebus_posix.c    # shm_open + ring read + tear protection
├── CameraExtension/            # System Extension target (Swift)
│   ├── CameraExtension.swift   # log subsystem anchor
│   ├── Provider.swift          # CMIOExtensionProvider
│   ├── Device.swift            # CMIOExtensionDevice
│   ├── Stream.swift            # CMIOExtensionStream (frame delivery — VERIFY)
│   ├── FrameBusReader.swift    # C consumer → CVPixelBuffer
│   ├── CameraExtension-Bridging-Header.h
│   ├── Info.plist
│   └── CameraExtension.entitlements
└── host/                       # Host app (activates the extension)
    ├── main.swift              # OSSystemExtensionRequest
    ├── Info.plist
    └── HostApp.entitlements
```

## IPC contract (shared with Windows)

| Aspect | Windows | macOS |
|---|---|---|
| Region | `Global\akvc-frames-v1` (file mapping) | `/akvc-frames-v1` (`shm_open`) |
| Schema | `akvc_protocol.h` (identical) | `akvc_protocol.h` (identical) |
| Sync | named Event + Mutex | **none** — 30 fps poll + seq tear-protection |
| Heartbeat time base | FILETIME (1601 epoch, 100ns) | CLOCK_REALTIME (Unix epoch, 100ns) |
| Producer | Python `windows_shm.py` | Python `macos_shm.py` |
| Consumer | DShow filter / MF frameserver | Camera Extension (Swift, via `framebus_posix.c`) |

The producer creates the region with `0o666` so the sandboxed extension
process can open it read-only.

## Build (on a Mac)

```bash
brew install xcodegen
cd virtualcam/macos
xcodegen generate                 # → akvc-macos.xcodeproj
# Extension only (dev, unsigned):
xcodebuild -project akvc-macos.xcodeproj \
  -scheme akvc-camera-extension -configuration Release build \
  -derivedDataPath ../../build/macos
```

Or from the repo root:

```bash
uv run tools/make.py configure    # runs xcodegen
uv run tools/make.py build        # runs xcodebuild
```

## VERIFY checklist (do this first on the Mac)

Before claiming the extension builds/loads, resolve every `// VERIFY`
marker against the Apple **CameraExtension** sample
(`https://developer.apple.com/documentation/coremediaio`) and the
`CoreMediaIO/CMIOExtension*.h` headers:

1. **Frame delivery** (`Stream.swift` → `pushFrame`): the exact
   `CMIOExtensionStream` API to deliver a `CMSampleBuffer`. This is the
   single biggest unknown.
2. **Clock** (`Stream.swift`): `CMIOExtensionClock` resume/pause/advance
   semantics + whether `consumeClockValue` must be implemented.
3. **Provider/Device/Stream attach** (`Provider.swift`, `Device.swift`):
   `attach`/`detach` API names.
4. **Initializers**: `CMIOExtensionDevice`, `CMIOExtensionStream`,
   `CMIOExtensionStreamFormat` initializer signatures + property container.
5. **Info.plist keys**: `CMIOExtension` provider key + `NSExtensionPointIdentifier`
   (`com.apple.coremediaio.extension`?).
6. **Entitlements**: the camera-extension entitlement key name.
7. **`shm_open` sandbox** (top risk): whether the extension can open
   `/akvc-frames-v1` created by a user process. If not → Plan B
   (XPC + IOSurface), documented in `docs/phase4/implementation-plan.md`.

## Sign + notarize

See `docs/phase4/signing-notarization.md`. Short version:
Developer ID Application cert → `codesign --deep --options runtime
--entitlements ... --timestamp` → `xcrun notarytool submit` →
`xcrun stapler staple`. System extensions must be notarized to load on
non-debug machines.

## Debug

```bash
log stream --predicate 'subsystem == "com.akvc.camera-extension"' --level debug
# or Console.app, filter subsystem "com.akvc.camera-extension"
systemextensionsctl list          # see installed extensions
systemextensionsctl developer on  # one-time, allow unsigned dev builds
```

## Known gaps (Phase 4 follow-ups)

- Host app does not yet publish placeholder frames when no Python producer
  is connected (`FrameBusReader.publishPlaceholder` is a stub).
- No Python↔host bridge for activating the extension from the desktop app
  (facade currently just assumes the extension is active on macOS).
- `shm_open` sandbox risk unresolved until tested on-device.
