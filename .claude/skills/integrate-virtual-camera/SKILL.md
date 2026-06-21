---
name: integrate-virtual-camera
description: Embed the AK Virtual Camera (DShow + MF dual-stack) into an external PySide6/Python project. Minimal-dependency recipe using akvc-core + 3 native binaries. Use when integrating virtual camera output into another application that already has its own video source.
---

# Integrate AK Virtual Camera into an External Project

This skill covers the **consumer side**: you already have a PySide6 (or any Python) app that produces video frames, and you want to push them to a system-wide virtual camera that Chrome/OBS/Teams/Zoom all see. You do NOT need the desktop app or the worker subprocess — just the `akvc-core` package and three native binaries.

The build/debug/internal-architecture knowledge is in the companion skill `windows-virtual-camera`; this skill is the integration shortcut.

## 1. Prerequisites (one-time, on the development/build machine)

Build the three native binaries from the AK Virtual Camera project (admin VS shell):
```bash
cd /path/to/amaran-virtual-camera
uv run tools/make.py configure
uv run tools/make.py build
```

Artifacts in `build/bin/Release/`:
| File | Role |
|---|---|
| `akvc_helper.exe` | Owns the `Global\` shared memory; registers the MF VirtualCamera; publishes placeholder frames when no producer is active. |
| `akvc-mf.dll` | MF VirtualCamera MediaSource DLL (loaded by `frameserver.exe`). |
| `akvc-dshow.dll` | DirectShow source filter (for OBS/Zoom/GraphStudioNext). |

One-time DShow registration (admin):
```bash
uv run python -m akvc_cli register
```

Install the Python package into your project:
```bash
pip install -e /path/to/amaran-virtual-camera/camera-core
```

## 2. Copy binaries into your project

Place the three files in a fixed directory (e.g. `bin/`):
```
your-project/
├── bin/
│   ├── akvc_helper.exe
│   ├── akvc-mf.dll
│   └── akvc-dshow.dll
└── main.py
```

Point the helper client at the exe via env var **before** importing `akvc`:
```python
import os
os.environ["AKVC_HELPER_EXE"] = os.path.join(os.path.dirname(__file__), "bin", "akvc_helper.exe")
```

## 3. Minimal integration class

```python
import os
import numpy as np

os.environ.setdefault("AKVC_HELPER_EXE",
                      os.path.join(os.path.dirname(__file__), "bin", "akvc_helper.exe"))

from akvc.core.helper.client import HelperService
from akvc.core.frame import Frame
from akvc.core.frame_pipeline import FramePipeline, ResizeStage, ColorConvertStage
from akvc.core.frame_sink.windows_shm import WindowsShmSink

class VirtualCamera:
    """Push BGR numpy frames to the system-wide AK Virtual Camera."""

    WIDTH, HEIGHT, FPS = 1280, 720, 30

    def __init__(self):
        self.helper = HelperService()
        self.sink = WindowsShmSink()
        self.pipeline = (
            FramePipeline()
            .add(ResizeStage(target_w=self.WIDTH, target_h=self.HEIGHT))
            .add(ColorConvertStage(dst="NV12"))
        )
        self._started = False

    def start(self) -> bool:
        """Start helper (registers MF device + creates Global\ SHM) and open
        the sink. MUST run elevated (admin) — Global\ SHM needs
        SeCreateGlobalPrivilege. Returns True on success."""
        if not self.helper.start():
            return False
        self.helper.register_mf()
        self.sink.open()
        self._started = True
        return True

    def push_frame(self, bgr: np.ndarray):
        """Push one BGR frame (HxWx3 uint8, any size — auto-resized).
        Call from your render timer / worker thread. Synchronous, ~1ms."""
        if not self._started:
            return
        frame = Frame.from_bgr(bgr)
        frame = self.pipeline.process(frame)   # → 1280×720 NV12
        self.sink.publish(frame)

    def stop(self):
        """Stop pushing; device stays registered (helper keeps running)."""
        if self._started:
            self.sink.close()
            self._started = False

    def shutdown(self):
        """Fully shut down — stop helper (MF device Stop'd). Call on app exit."""
        self.stop()
        self.helper.stop()
```

## 4. Usage in PySide6

```python
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import numpy as np, sys

app = QApplication(sys.argv)
vc = VirtualCamera()
if not vc.start():
    sys.exit("start failed — run as admin")

timer = QTimer()
seq = [0]
def on_tick():
    # Replace with your real frame source (QImage, OpenCV, render output…)
    bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
    bgr[:, :] = (seq[0] % 256, 100, 50)
    seq[0] += 4
    vc.push_frame(bgr)

timer.timeout.connect(on_tick)
timer.start(int(1000 / vc.FPS))
rc = app.exec()
vc.shutdown()
```

### Feeding real frames

From a QImage:
```python
def qimage_to_bgr(qimg):
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(qimg.height(), qimg.width(), 4)
    return arr[:, :, :3].copy()   # RGBA → BGR
```

From OpenCV:
```python
ok, bgr = cap.read()
if ok: vc.push_frame(bgr)
```

## 5. Constraints & gotchas

| Constraint | Why |
|---|---|
| **Run as admin** | Helper creates `Global\akvc-frames-v1` — needs `SeCreateGlobalPrivilege`. Without admin, `CreateFileMappingW` returns error 5. |
| **Frame size flexible** | `ResizeStage` resizes any input to 1280×720. `ColorConvertStage` converts BGR→NV12. You pass raw BGR. |
| **`push_frame` is synchronous** | ~1ms (SHM memcpy + event signal). Safe to call from a QThread; the SHM write is lock-protected. Not safe to call from multiple threads simultaneously — serialize calls. |
| **`register_mf` once per helper lifetime** | The helper internally tracks this; calling it again on Start→Stop→Start (source switch) is safe. |
| **App exit must call `shutdown()`** | Otherwise the helper is orphaned and the MF device node lingers (System lifetime). `shutdown()` → `helper.stop()` → helper reads stdin EOF → clean Stop. |
| **Restart FrameServer after replacing DLLs** | `frameserver.exe` caches `akvc-mf.dll`. After updating the DLL: `Stop-Service FrameServer; Start-Service FrameServer` (admin). |
| **Only one AK Virtual Camera device** | The MF device (KSCATEGORY_VIDEO_CAMERA) + DShow filter (VideoInputDeviceCategory) with identical friendly name are aggregated by Win11 into one device. Do not register the DShow filter under a different name. |
| **PnP name "Windows Virtual Camera Device"** | Cosmetic — Device Manager shows this because AddProperty can't override the MF VirtualCamera devnode name. Applications see "AK Virtual Camera" via the MF friendlyName. Ignore it. |

## 6. Threading model

The SHM sink (`WindowsShmSink.publish`) uses an internal `threading.Lock` and a Win32 mutex — so calls from one thread at a time are safe. For a GUI app:

- **Simple**: call `push_frame` from a `QTimer` (runs on the GUI thread, 30fps is fine — ~1ms overhead).
- **Heavy render**: push from a `QThread` worker to avoid blocking the GUI; queue the latest frame and let the timer pull it.

Do NOT start multiple `VirtualCamera` instances in the same process — the helper is a singleton (one SHM, one MF device).

## 7. Distribution / installer

For an installer (NSIS/MSI), you only need to:
1. Copy the 3 binaries + your Python app.
2. `regsvr32 /s bin\akvc-mf.dll` (optional — registers the MF CLSID in the registry; the helper does this at runtime too, but pre-registering avoids the first-run delay).
3. `regsvr32 /s bin\akvc-dshow.dll` (registers the DShow filter + VideoInputDeviceCategory entry).

The MF VirtualCamera itself is created at runtime by the helper (`MFCreateVirtualCamera`), not by the installer — this matches OBS 28+ behavior.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| `start()` returns False | `AKVC_HELPER_EXE` path correct? Running as admin? |
| Chrome can't see device | Helper running? (`vc.helper.ping()`). Restart FrameServer: `Stop-Service FrameServer; Start-Service FrameServer`. |
| OBS can't see device | DShow registered? (`akvc_cli register` once, admin). |
| Device visible but black | `push_frame` being called? Frame is valid BGR uint8? Helper log at `%LOCALAPPDATA%\AKVC\logs\akvc.worker.log`. |
| Device visible but frozen | `akvc-core` version has the heartbeat fix (uses `GetSystemTimeAsFileTime`, not `perf_counter`)? |
| Two devices in list | DShow and MF friendly names differ? Both must be "AK Virtual Camera". MF must register `KSCATEGORY_VIDEO_CAMERA`. |
| Orphaned device after crash | `Get-PnpDevice \| Where InstanceId -like '*VCAMDEVAPI*'` then admin `pnputil /remove-device <id>`. |
| `ImportError: akvc` | `pip install -e /path/to/camera-core` not done? |

## 9. What you do NOT need

- The desktop app (`apps/desktop/`) — it's a reference UI; your app replaces it.
- The FrameWorker subprocess (`frame_worker.py`) — that's for isolating the GUI from capture; you call `sink.publish()` directly.
- The CLI (`apps/cli/`) — only needed for the one-time `register`/`unregister`.
- The test patterns / USB provider — bring your own frame source.

## 10. File layout summary

```
your-project/
├── bin/                          # copy from build/bin/Release/
│   ├── akvc_helper.exe
│   ├── akvc-mf.dll
│   └── akvc-dshow.dll
├── your_app.py                   # sets AKVC_HELPER_EXE, imports akvc.core.*
└── (akvc-core installed via pip install -e)
```
