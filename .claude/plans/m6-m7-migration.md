# Migration plan — apps/desktop → akvc_camera binding, and Python SDK removal (M6/M7)

> Status: INCOMPLETE. The C++ control layer (M1-M5) is delivered and verified.
> M6/M7 are a large, intertwined refactor that needs dedicated effort. This doc
> is the concrete plan so the work can resume cleanly.

## Why M6/M7 are deferred

`apps/desktop` is deeply coupled to the Python `akvc/` package, not just the
C++ binding:

- `frame_worker.py` imports `NativeWindowsFrameBusProducer`, `NativeMacOsShmSink`,
  `NativeFpsRegulator`, `NativeMetrics`, `resize_rgb24_frame`, `rgb24_to_nv12_frame`.
- `facade.py` imports `akvc.sdk.VirtualCamera` (40+ methods: install_extension,
  direct_sender_*, sync_ipc, readiness, runtime_topology, …) and
  `akvc.platforms.macos.installer`.
- `source_provider.py`, `source_info.py` import `akvc._core_native` providers.
- `helper_service.py`, `windows_runtime.py` import `akvc.helper_service`, `akvc.runtime`.
- ~30 `tests/unit/test_*.py` depend on the `akvc` package; `make.py` unregister
  uses `akvc_cli`.

The new `akvc_camera` binding exposes only 6 methods (start/stop/push_frame/
started/consumer_count/last_error) — by design (the control layer excludes
installation). So the desktop app's install UI / macOS direct-sender facade
cannot be backed by the new binding directly. Removing `akvc/` therefore
requires either porting those features out of the control layer or dropping
them — a design decision plus a multi-file refactor, not a quick deletion.

## M6 — desktop app migration (sequenced)

1. **frame_worker.py**: replace `NativeWindowsFrameBusProducer` + resize/convert/
   fps with `akvc_camera.VirtualCamera` (start/push_frame/stop). The binding
   does resize→NV12→publish internally. Provider loop stays; push at provider
   rate (FPS regulation moves to the caller or a follow-up).
2. **source_provider.py / source_info.py**: the providers (test_pattern, usb)
   currently come from `_core_native`. Decide: keep providers as pure Python
   (re-implement without `_core_native`), or expose them via a new binding
   extension. Minimal: pure-Python test-pattern provider (sufficient for desktop
   demo); USB provider can follow.
3. **facade.py**: replace `akvc.sdk.VirtualCamera` with `akvc_camera.VirtualCamera`
   for the camera-control surface. Move macOS install/direct-sender facade
   methods behind a separate "installer" module (out of the control layer) or
   gate them out (macOS is BLOCKED in this env anyway).
4. **helper_service.py / windows_runtime.py**: `akvc.runtime`/`akvc.helper_service`
   are Python asset-resolution helpers. Port the minimal `find_helper_exe` /
   `find_dshow_dll` logic into `apps/desktop` (consumer-owned), or drop if the
   binding's start() self-launches the helper (it does, given helper_exe path).
5. **PySide6 integration** (`akvc.integrations.pyside6`): `push_widget` /
   `push_screen` / `LatestFrameProvider` / `PySide6VirtualCameraStreamer` are
   Python/Qt sugar. Re-implement in `apps/desktop` on top of
   `akvc_camera.VirtualCamera.push_frame` (capture widget → numpy → push).
6. **tests**: update `test_desktop_main_vm`, `test_desktop_main_window` to mock
   `akvc_camera.VirtualCamera` instead of `akvc.sdk`. Delete `test_cli_*`,
   `test_distribution`, `test_frame_input`, `test_frame*` that tested the
   deleted `akvc` package.

## M7 — Python SDK removal (after M6 green)

1. Delete `akvc/` (Python package: sdk, distribution, runtime, windows_runtime,
   helper_service, _runtime, _core_native.pyd).
2. Delete `apps/cli/` (akvc_cli). Update `make.py` unregister to call
   `regsvr32 /u` directly (or a C++ uninstall tool).
3. Delete `camera-core/native/` (legacy pybind `_core_native` module) and its
   `add_subdirectory` in root CMake.
4. Delete stale `camera-core/build/`, `akvc_core.egg-info`,
   `amaranth_virtual_camera.egg-info`, `apps/cli/akvc_cli.egg-info`.
5. Update root `pyproject.toml`/`setup.py`: drop `akvc*` packaging; the C++
   `akvc_camera` lib is built by CMake, not pip. Keep `apps/desktop` as the
   only Python package (depends on `akvc_camera` pyd at runtime).
6. Update `make.py`: `build` = CMake build of `akvc_camera` + pyd + desktop
   editable install; `test` = ctest + desktop pytest.

## Guard: do not break the desktop app mid-migration

Until M6 is green, KEEP `akvc/` + `camera-core/native` building so the desktop
app stays functional. M7 deletions happen only after M6's desktop pytest is
green. This avoids a broken intermediate state.
