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

## 0. Package the desktop app with Nuitka (for end-to-end macOS verification)

`tools/package_nuitka.py` produces a standalone `dist/AKVirtualCamera.app` that
bundles the PySide6 desktop app + the C++ `akvc_camera` pybind binding, and
embeds the camera extension under `Contents/Library/SystemExtensions/` (if you
built it via `python tools/make.py build`).

```sh
pip install nuitka
python tools/package_nuitka.py
```

The script:
1. Builds the C++ `akvc_camera_python` target (cmake) if `akvc_camera.so` is missing.
2. Runs Nuitka (`--standalone --macos-create-app-bundle --enable-plugin=pyside6
   --include-module=akvc_camera --include-package=akvc_app`) on
   `apps/desktop/main.py` (a top-level entry that avoids relative-import issues).
3. Embeds `com.sidus.amaran-desktop.cameraextension.systemextension` into the
   `.app` bundle if present.

Then open `dist/AKVirtualCamera.app`, approve the system-extension prompt
(`systemextensionsctl developer on` first for debug), and verify VC-M-2..5
(FaceTime/Zoom/Safari/OBS).

> NOTE: the script is authored on Windows and is best-effort for macOS. If
> Nuitka or the linker reports missing modules/symbols, adjust the `--include-*`
> flags or the `akvc_camera_macos` source list in `camera-core/CMakeLists.txt`.
> The `akvc_camera.so` links the macOS frameworks (Foundation/AVFoundation/
> CoreMedia/CoreMediaIO/CoreVideo/SystemExtensions) statically via the
> `akvc_camera_macos` lib; Nuitka's standalone mode bundles the dylib deps.
