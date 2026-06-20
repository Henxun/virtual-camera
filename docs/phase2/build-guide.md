# Phase 2 — Build Guide (Windows DirectShow MVP)

**Last updated**: 2026-06-19
**Target**: Windows 10 22H2 / Windows 11 (x64)

## 1. Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Visual Studio 2022 (Community is fine) | 17.6 | Install workload **Desktop development with C++**; ensure **MSVC v143** and **Windows 10 SDK 10.0.22621.0** or later are checked |
| CMake | 3.25 | Bundled with VS, or [cmake.org](https://cmake.org/) |
| Python | 3.12.x (64-bit) | from python.org or `winget install Python.Python.3.12` |
| Git | any | for fetching DirectShow BaseClasses |

Open a **"x64 Native Tools Command Prompt for VS 2022"** for all build steps below.
The plain Command Prompt or PowerShell will NOT find `cl.exe` / `link.exe`.

## 2. One-time setup

```bat
git clone <your repo> akvc
cd akvc

REM Create a virtual env for the Python side.
python -m venv .venv
.venv\Scripts\activate

REM Pin pip and install build helpers.
python -m pip install --upgrade pip wheel setuptools
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

- `build\bin\Release\akvc-dshow.dll` — the DirectShow Source Filter
- `build\lib\Release\akvc_framebus.lib` — static lib used by the filter
- editable installs of `akvc-core`, `akvc-desktop`, `akvc-cli` in your venv

To rebuild incrementally, just `python tools\make.py build` again.

## 5. Register the filter

Registration writes:

- `HKCR\CLSID\{8E14549A-DB61-4309-AFA1-3578E927E933}\InprocServer32` → DLL path
- DirectShow Filter Mapper entry under `Video Capture Sources`

Open an **Administrator** Command Prompt:

```bat
python tools\make.py register
```

Equivalent to:
```bat
regsvr32 /s build\bin\Release\akvc-dshow.dll
```

To unregister:

```bat
python tools\make.py unregister
```

## 6. Verify

```bat
akvc status
```

Expected:

```
[akvc] CLSID:      {8E14549A-DB61-4309-AFA1-3578E927E933}
[akvc] Inproc DLL: F:\path\to\akvc\build\bin\Release\akvc-dshow.dll
[akvc] Build DLL:  F:\path\to\akvc\build\bin\Release\akvc-dshow.dll
```

Optional: open `graphedt.exe` (DirectShow filter graph editor, ships with
Windows SDK), choose **Graph → Insert Filters → Video Capture Sources** and
confirm `AK Virtual Camera` is listed.

## 7. Run the desktop application

```bat
python -m akvc_app
```

In the UI:

1. The **Source** dropdown lists USB cameras + a built-in **Test Pattern**.
2. Click **Start** — the FrameWorker subprocess opens the source and starts publishing NV12 frames into the shared-memory ring.
3. Open OBS / Zoom / Chrome `getUserMedia` and select **AK Virtual Camera**.

## 8. Common build errors

| Symptom | Cause | Fix |
|---|---|---|
| `streams.h: No such file` | `tools/make.py configure` did not finish | rerun configure with network on |
| `unresolved external symbol _DllMain*` | strmbase.lib not linked | rebuild — confirm `STRMBASE_LIB` path in CMake |
| `regsvr32: 0x80040201` | bitness mismatch | run from x64 Native Tools prompt; do not use 32-bit regsvr32 (`SysWOW64`) |
| LNK2019 about IID_IAMStreamConfig | `strmiids.lib` missing | already linked; check that linker order keeps strmbase before strmiids |
| `RuntimeError: Cannot open USB camera` | no camera attached / driver busy | use Test Pattern source; close other camera apps |

## 9. Repeatable clean build

```bat
python tools\make.py clean
python tools\make.py configure
python tools\make.py build --python
```

## 10. CI / non-interactive build

CI systems should call `tools/make.py` exactly as developers do, but invoke
`vcvars64.bat` first:

```bat
call "%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
python tools\make.py configure
python tools\make.py build --python
python tools\make.py test
```
