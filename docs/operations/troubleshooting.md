# Troubleshooting

## 2026-07-01 — CMake-native `_core_native` configure fails with `No module named pybind11`

- Symptom: after moving `akvc._core_native` into the root CMake graph, `uv run tools/make.py configure` stopped in `camera-core/native/CMakeLists.txt` because `python -m pybind11 --cmakedir` failed.
- Root cause: the active project virtualenv did not have the `pybind11` Python module installed, so CMake could not discover the pip-installed pybind11 CMake config directory.
- Fix: make `tools/make.py configure` self-check Python build dependencies and install missing `pybind11` / `numpy` into the active environment before running root CMake configure.
- Verification: build log `.akvc/logs/build/20260701T082103-attempt-03-configure.log` should no longer contain `No module named pybind11` and should proceed into the project configure/build stage.

## 2026-06-22 — `tools/make.py build --python` fails with `No module named pip`

- Symptom: native build completes, then the `--python` editable-install phase fails because `.venv\Scripts\python.exe` cannot import `pip`.
- Root cause: the project virtualenv was missing `pip`, so `tools/make.py` could not perform its post-build editable installs.
- Fix: bootstrap `pip` in the existing virtualenv with `python -m ensurepip --upgrade`, then rerun `tools/make.py build --python`.
- Verification: build log `.akvc/logs/build/20260622T060737-attempt-02.log` shows successful native outputs plus editable installs for `camera-core` and `apps/desktop` (which now also carries the `akvc` compatibility command surface).

## 2026-06-22 — `akvc doctor` reports filter not registered

- Symptom: `akvc status` shows `Inproc DLL: (not registered)` and `akvc doctor` exits with `Filter is not registered`.
- Root cause: the built/package DLL exists, but the system-level DShow registration step has not yet been run on the current machine.
- Fix: run `akvc register` or `python tools\make.py register` from an elevated shell.
- Verification: expected follow-up is `akvc status` reporting a non-empty `Inproc DLL` path and `akvc doctor` returning exit code 0.

## 2026-06-22 — dev-mode `akvc register` can target stale packaged runtime DLLs

- Symptom: in an editable/dev checkout, `akvc status` showed the registered DLL path under `akvc\_runtime\windows\akvc-dshow.dll` even after a fresh native rebuild produced `build\bin\Release\akvc-dshow.dll`.
- Root cause: `akvc.runtime._find_asset()` preferred packaged resources before local build outputs, so CLI registration in a development environment could bind the system registration to an older packaged DLL instead of the freshly built one.
- Fix: in development mode, check `build/bin/Release/*` candidates before packaged resources in `akvc/runtime.py`.
- Verification: `akvc status` now reports `Build DLL: E:\workspace\virtual-camera\build\bin\Release\akvc-dshow.dll`, and after explicit re-register the registered `Inproc DLL` also points at the build output.

## 2026-06-22 — `VideoInputDeviceCategory` instance key is named by friendly name, not CLSID

- Symptom: the first version of `tools/diag/dshow_enum.py` reported `Filter not in VideoInputDeviceCategory` because it looked for `...\Instance\{8E14549A-...}`.
- Root cause: `IFilterMapper2::RegisterFilter` created the instance key as `...\Instance\AK Virtual Camera`, with `CLSID`, `FriendlyName`, and `FilterData` stored as values under that key.
- Fix: update diagnostics to enumerate `...\Instance\*` and match by the child key's `CLSID` value, rather than assuming the subkey name equals the filter CLSID.
- Verification: registry inspection shows `AK Virtual Camera` under `HKCR\CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance` with `CLSID={8E14549A-DB61-4309-AFA1-3578E927E933}` and `FilterData` present.

## 2026-06-22 — current VC-3 blocker is in the ctypes diagnostic script, not native registration

- Symptom: `tools/diag/dshow_enum.py` now reports registration PASS, but `check_directshow_enum()` still fails with repeated `BindToStorage hr=0x80004002` before it can read `FriendlyName`.
- Root cause: the custom ctypes COM call sequence for `IMoniker::BindToStorage(..., IID_IPropertyBag, ...)` is still incorrect, so the script cannot yet prove `ICreateDevEnum` enumeration even though registry-based registration is present.
- Fix: correct the COM vtable binding/signature in the diagnostic script, or replace the low-level ctypes path with a more reliable COM helper for `IEnumMoniker` + `IPropertyBag` reads.
- Verification: after fixing the enumeration path, `tools/diag/dshow_enum.py` should list `AK Virtual Camera` under `=== DirectShow Enumeration ===`; until then, do not interpret the current VC-3 FAIL as a proven product bug.

## 2026-07-08 — `akvc-dshow.dll` relink fails with LNK1104 "无法打开文件" (DLL locked by consumer)

- Symptom: `cmake --build build --config Release` fails on the `akvc_dshow` target with `LINK : fatal error LNK1104: 无法打开文件"...\build\bin\Release\akvc-dshow.dll"`, while other targets (`akvc_camera_core`, `akvc_helper.exe`, `akvc-mf.dll`) link fine.
- Root cause: a consumer process has the DShow filter DLL loaded. DirectShow loads the filter into any process that enumerates video capture devices — Chrome (a tab on a camera page), OBS, Zoom, GraphStudioNext, or even the agent/editor process (`Codex.exe`). The linker cannot overwrite the locked output.
- Verify which process holds it:
  ```powershell
  Get-Process | Where-Object { $_.Modules | Where-Object { $_.FileName -like '*akvc-dshow.dll' } } | Select Id,ProcessName
  ```
- Fix (non-disruptive, preferred during refactor): build only the targets you changed, avoiding the locked-DLL relink — `cmake --build build --config Release --target akvc_camera_core akvc_camera_tests`. The existing `akvc-dshow.dll` stays current as long as no DShow source changed; a relink would produce a byte-identical binary.
- Fix (full build, e.g. at acceptance): close the consumer holding the DLL (close Chrome's camera tab / quit OBS), then rebuild. Do NOT kill Chrome processes blindly — that crashes the user's browser session.
- Verification: targeted build exits 0; `ctest` green. Full build green only after the consumer releases the DLL.

## 2026-07-08 — `bgr24_to_nv12` of pure green yields Y=144 (not 145)

- Symptom: `bgr24_to_nv24` of pure green (B=0, G=255, R=0) produces Y=144; a naive hand-calculation gives 145.
- Root cause: `yv = ((66*0 + 129*255 + 25*0 + 128) >> 8) + 16 = (33023 >> 8) + 16`. `33023 = 0x80FF`, so `>>8 = 0x80 = 128` (NOT 129, because `256*129 = 33024 > 33023`). Thus `Y = 128 + 16 = 144`. This is bit-identical to the legacy `rgb24_to_nv12_frame`; the off-by-one is a hand-calculation trap, not a code bug.
- Fix: assert Y=144 for green in `camera-core/tests/test_pipeline_ops.cpp`. BT.601 limited-range reference values used in the test: black=16/UV=128, white=235/UV=128, green=144/(54,34), blue=41/(240,110), red=82/(90,240).
- Verification: `ctest -C Release` → `akvc_camera_pipeline_tests` Passed.


## 2026-07-08 - Chrome/Edge (Media Foundation) shows no picture while OBS (DShow) works

- Symptom: on Windows 11, OBS/Zoom (DirectShow) show the AK Virtual Camera feed, but Chrome/Edge/Teams (Media Foundation) show no picture (or no device).
- Root cause (two, both required):
  1. The MF virtual camera was never registered via `MFCreateVirtualCamera`. Win11 Chrome/Edge use Media Foundation, not DirectShow; without an MF virtual camera registered, MF consumers have no device to open. The DShow filter (regsvr32) does not cover them.
  2. `akvc-mf.dll` set `MF_DEVICESTREAM_STREAM_CATEGORY = KSCATEGORY_VIDEO_CAMERA` in `MediaSourceActivate::ctor`. `KSCATEGORY_VIDEO_CAMERA` is only for `MFCreateVirtualCamera` device registration/aggregation; the stream category must be `PINNAME_VIDEO_CAPTURE` (matching `GetStreamAttributes`). With the wrong category the MF frame server cannot start the stream.
- Fix:
  - Control layer `start()` calls `MFCreateVirtualCamera` (via the elevated helper's `register_mf` pipe command, `CMD_REGISTER_MF=0x4`) on Windows 11+ (build >= 22000, detected via `RtlGetVersion`). See `camera-core/src/platform/windows/windows_session.cpp` + `helper_client_runtime.cpp`. Registration is idempotent.
  - `virtualcam/windows/mf/src/mf_source.cpp` `MediaSourceActivate::ctor` sets `MF_DEVICESTREAM_STREAM_CATEGORY` to `PINNAME_VIDEO_CAPTURE` (matches `GetStreamAttributes`).
- Verification: `tools/diag/mf_enum.py` (WinRT `DeviceInformation::FindAllAsync(VideoCapture)`) lists `AK Virtual Camera` - this is the enumeration Chrome/Edge use (NOT `Get-PnpDevice`). Chrome getUserMedia sample then shows the feed.
- Note: `MFCreateVirtualCamera` requires the helper to run elevated. If `start()` returns `HelperUnavailable` with "MF virtual camera registration failed", ensure the helper was launched elevated (scheduled task `AKVirtualCameraHelper` with `/rl highest`, or UAC-approved launch).
- RULE-OVERRIDE: the control layer originally excluded installation, but Win11 MF registration (`MFCreateVirtualCamera`) is now part of `start()` because MF consumers cannot see the device without it. DShow `regsvr32` remains a separate one-time install step.

## 2026-07-08 - Virtual camera picture flickers (alternating frames / black)

- Symptom: OBS/Chrome show the AK Virtual Camera feed but it flickers (alternating frames, or real<->black).
- Root cause: MULTIPLE producer processes writing to the same frame-bus shared memory (`Global\akvc-frames-v1` / `AKVirtualCamera\akvc-frames-v1.bin`). Each producer takes over `writer_pid` and publishes to the 4-slot ring; with 2+ producers their frames interleave and the consumer reads a mix -> flicker. Common way to get multiple producers: launching the desktop app twice, or leaving `cpp_camera_demo.py` running while the app is also streaming, or a `kill <bash_pid>` that did not terminate the actual `python.exe` (Git Bash `kill` uses POSIX signals that often do not stop native Windows processes).
- Diagnose: sample the shm control block - `writer_pid` alternates between two (or more) PIDs across samples. `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` shows multiple `akvc_app`/`cpp_camera_demo` instances.
- Fix: keep exactly ONE producer. Kill all others with `Stop-Process -Id <pid> -Force` (PowerShell; Git Bash `kill` is unreliable on native Windows processes). Verify `writer_pid` is stable (single PID) across samples.
- Note: a single `python -m akvc_app` launch may show TWO `python.exe` PIDs (parent = `.venv\Scripts\python.exe` launcher, child = the real uv-managed interpreter it spawns). That is ONE logical app instance, not two producers.
- Rule: only one app/demo instance may stream at a time.
