# macOS control layer — user verification script

> The macOS control layer (`akvc_camera_macos`) cannot be built or tested in the
> Windows dev environment. Run this on a Mac to verify M3/M4. Per
> `.claude/rules/virtual-camera.md` §6 and `macos.md` §9, macOS gates are
> BLOCKED until the user runs this.

## Prerequisites

- macOS 12.3+ with Xcode + Command Line Tools.
- The camera extension built & its `.systemextension` available (see
  `virtualcam/macos/project.yml` / `docs/phase4/`).
- `systemextensionsctl developer on` for debug builds (Developer ID signing +
  notarization required for non-debug machines — see `docs/phase4/signing-notarization.md`).

## 1. Build the macOS control library

```sh
cmake -S . -B build-macos -DCMAKE_BUILD_TYPE=Release
cmake --build build-macos --target akvc_camera_macos -j
```

Expected: `build-macos/libakvc_camera_macos.a` is produced with no errors.

> If the source list is incomplete (unresolved symbols from
> `AKVCCommandSupport` / `macos_ipc` / `framebus_posix`), add the missing
> `.mm`/`.cpp`/`.c` sources under `virtualcam/macos/` to
> `camera-core/CMakeLists.txt` `akvc_camera_macos` target and rebuild.

## 2. Smoke test: start + push one frame

Write `camera-core/tests/test_macos_session.mm`:

```objc++
#include "akvc/platform/macos/macos_session.h"
int main() {
    akvc::macos::MacVirtualCameraSession s(1280, 720, 30.0, "AK Virtual Camera");
    auto st = s.start();
    if (st != akvc::Status::Ok) { __builtin_trap(); }
    std::vector<uint8_t> frame(1280*720*3, 128);
    akvc::FrameInput f{frame.data(), 1280, 720, 1280*3, akvc::PixelFormat::BGR24, 0};
    s.push_frame(f);
    return 0;
}
```

Build & run:

```sh
c++ -std=c++17 -ObjC++ test_macos_session.mm \
    -Icamera-core/include \
    build-macos/libakvc_camera_macos.a \
    -framework Foundation -framework AVFoundation -framework CoreMedia \
    -framework CoreMediaIO -framework CoreVideo -framework SystemExtensions
./a.out
```

Expected: `start()` triggers the system-extension activation prompt (approve it
once); the process exits 0. `consumer_count()` returns 1 once a consumer
(FaceTime/Zoom) opens the camera.

## 3. End-to-end (VC-M-2..5)

- Open **FaceTime → Video → Camera** → select `AK Virtual Camera`.
- Open **Zoom → Settings → Video → Camera** → select `AK Virtual Camera`.
- Open **Safari** at `https://webrtc.github.io/samples/src/content/devices/input-output/`.
- Open **OBS → Sources → Video Capture Device** → select `AK Virtual Camera`.

For each, run the smoke test pushing a recognizable test pattern and confirm
the preview shows it. Record results in the acceptance table (VC-M-2..5).

## RULE-OVERRIDE note

`start()` calls `OSSystemExtensionRequest activationRequestForExtension` per the
user's explicit design decision (2026-07-08). CLAUDE.md §4 lists
`OSSystemExtensionRequest` as a human-authorization-gated action; the design is
authorized, and runtime execution still shows the macOS system approval dialog.
