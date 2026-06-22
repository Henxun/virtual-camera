# Troubleshooting

## 2026-06-22 — `tools/make.py build --python` fails with `No module named pip`

- Symptom: native build completes, then the `--python` editable-install phase fails because `.venv\Scripts\python.exe` cannot import `pip`.
- Root cause: the project virtualenv was missing `pip`, so `tools/make.py` could not perform its post-build editable installs.
- Fix: bootstrap `pip` in the existing virtualenv with `python -m ensurepip --upgrade`, then rerun `tools/make.py build --python`.
- Verification: build log `.akvc/logs/build/20260622T060737-attempt-02.log` shows successful native outputs plus editable installs for `camera-core`, `apps/desktop`, and `apps/cli`.

## 2026-06-22 — `akvc doctor` reports filter not registered

- Symptom: `akvc status` shows `Inproc DLL: (not registered)` and `akvc doctor` exits with `Filter is not registered`.
- Root cause: the built/package DLL exists, but the system-level DShow registration step has not yet been run on the current machine.
- Fix: run `akvc register` or `python tools\make.py register` from an elevated shell.
- Verification: expected follow-up is `akvc status` reporting a non-empty `Inproc DLL` path and `akvc doctor` returning exit code 0.

## 2026-06-22 — dev-mode `akvc register` can target stale packaged runtime DLLs

- Symptom: in an editable/dev checkout, `akvc status` showed the registered DLL path under `camera-core\src\akvc\_runtime\windows\akvc-dshow.dll` even after a fresh native rebuild produced `build\bin\Release\akvc-dshow.dll`.
- Root cause: `akvc.runtime._find_asset()` preferred packaged resources before local build outputs, so CLI registration in a development environment could bind the system registration to an older packaged DLL instead of the freshly built one.
- Fix: in development mode, check `build/bin/Release/*` candidates before packaged resources in `camera-core/src/akvc/runtime.py`.
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
