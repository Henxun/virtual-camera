# Phase 2 — Build Guide (Windows DirectShow MVP)

**Last updated**: 2026-06-22
**Target**: Windows 10 22H2 / Windows 11 (x64)

## 1. Two installation paths

### 1.1 SDK consumer path (repo-root install)

If you only want to consume the virtual-camera SDK from another Python 3.11–3.12 / PySide6 app:

```bat
pip install <repo-url>
```

After install you can:
- `from akvc.sdk import VirtualCamera`
- `akvc register`
- `akvc status`
- `akvc doctor`

For deeper diagnosis in a development checkout:

```bat
uv run python tools/diag/dshow_enum.py
```

This path installs Python code and compiles the Windows runtime assets during the install/build step.
It does **not** automatically complete privileged registration steps.

If you also want desktop dependencies:

```bat
pip install "<repo-url>[desktop]"
```

### 1.2 Developer / contributor path

Open a **"x64 Native Tools Command Prompt for VS 2022"** for all build steps below.
The plain Command Prompt or PowerShell will NOT find `cl.exe` / `link.exe`.

## 2. One-time developer setup

```bat
git clone <your repo> akvc
cd akvc

python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip wheel setuptools
pip install -e .[desktop]
```

## 3. Configure

`tools/make.py configure` does three things:

1. Sparse-clones Microsoft's `Windows-classic-samples` and copies the
   `multimedia/directshow/baseclasses` subtree to `third_party/baseclasses/`.
2. Builds `strmbase.lib` (Release, x64) under `third_party/baseclasses/build/Release/`.
3. Generates the top-level CMake build tree under `build/`.

```bat
python tools\make.py configure
```

Expected end-of-output: `-- Generating done` followed by `-- Build files have been written to: ...\build`.

## 4. Build

```bat
python tools\make.py build --python
```

Outputs:

- `build\bin\Release\akvc-dshow.dll`
- `build\bin\Release\akvc-mf.dll`
- `build\bin\Release\akvc_helper.exe`
- editable installs / local development installs for Python packages

To rebuild incrementally, just `python tools\make.py build` again.

### Development runtime lookup behavior

During repository-local development, runtime discovery now prefers freshly built binaries under `build/bin/Release`, then install-time staged binaries under `build/package-runtime/bin`, before packaged runtime assets.

That means:
- `akvc register`
- `akvc status`
- the SDK runtime locator

will prefer your newest local build outputs when they exist.

## 5. Register the filter

Open an **Administrator** Command Prompt:

```bat
python tools\make.py register
```

Or, if you installed from the root package already:

```bat
akvc register
```

To unregister:

```bat
python tools\make.py unregister
```

## 6. Verify

```bat
akvc status
akvc doctor
uv run python tools/diag/dshow_enum.py
```

Expected:
- the CLI can locate `akvc-dshow.dll`
- registration state is shown correctly
- DirectShow enumeration includes `AK Virtual Camera`
- live frame-bus traffic is visible on `Global\\akvc-frames-v1`

## 7. Run the desktop application

```bat
python -m akvc_app
```

In the UI:

1. The **Source** dropdown lists USB cameras + a built-in **Test Pattern**.
2. Click **Start** — the FrameWorker subprocess opens the source and starts publishing NV12 frames into the shared-memory ring.
3. Open OBS / Zoom / Chrome `getUserMedia` and select **AK Virtual Camera**.

## 8. Common build/runtime errors

| Symptom | Cause | Fix |
|---|---|---|
| `streams.h: No such file` | `tools/make.py configure` did not finish | rerun configure with network on |
| `regsvr32: 0x80040201` | bitness mismatch | run from x64 Native Tools prompt; do not use 32-bit regsvr32 (`SysWOW64`) |
| `RuntimeError: failed to start akvc helper` | helper path missing or insufficient privileges | verify install-time build/staging completed; run elevated if required |
| `akvc register` cannot find DLL | runtime DLL missing | reinstall package, rebuild runtime, or point `AKVC_DSHOW_DLL` explicitly |
| `RuntimeError: Cannot open USB camera` | no camera attached / driver busy | use Test Pattern source; close other camera apps |
| `dshow_enum.py` says SHM not found | app/helper not publishing yet | start the app, click Start, then rerun the diagnostic |
| `dshow_enum.py` opens `Local\\...` in old notes | stale guidance | use `Global\\akvc-frames-v1` as the current frame-bus name |
