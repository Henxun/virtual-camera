# Phase 2 — Run & Debug Guide

## 1. Process model recap

```
Desktop App (akvc_app.__main__)
   │  spawn (multiprocessing)
   ▼
FrameWorker subprocess          ── owns Frame Bus producer
   │  WindowsShmSink.publish()
   ▼
Named shared memory  Local\akvc-frames-v1
                     Local\akvc-frames-evt-v1
                     Local\akvc-frames-mtx-v1
   ▲
   │  in-proc COM  (akvc-dshow.dll loaded by consumer)
   │
Consumer process (OBS / Zoom / Chrome / WeChat / Discord / ...)
```

## 2. Logs

| Component | Default path |
|---|---|
| Desktop app (UI process) | `%LOCALAPPDATA%\AKVC\logs\akvc.app.log` |
| FrameWorker subprocess | `%LOCALAPPDATA%\AKVC\logs\akvc.worker.log` |
| DShow filter (in-proc) | not logged in Phase 2 (use OutputDebugString in DebugView) |

Logs are JSON Lines. View them with:

```pwsh
Get-Content $env:LOCALAPPDATA\AKVC\logs\akvc.worker.log -Tail 50 -Wait
```

## 3. Running with the test pattern (no camera required)

The desktop app always offers a **Test Pattern** source. Selecting it skips
USB enumeration and produces a synthetic SMPTE-style colorbar with a moving
white scan line — the moving line is the easiest visual signal that your
consumer is actually pulling frames in real time.

## 4. Verifying the device appears in OBS

1. **OBS Studio 30+** → **Sources → Video Capture Device → Add**.
2. **Device** dropdown → choose `AK Virtual Camera`.
3. **Configure Video** → **Resolution / FPS Type → Custom** → 1280×720, 30fps.
4. **Video Format**: NV12.
5. Click **OK** — the colorbar should appear. If it does not, OBS shows a
   black rectangle; check the FrameWorker log.

## 5. Verifying in Zoom

1. **Zoom Desktop → Settings → Video → Camera** → choose `AK Virtual Camera`.
2. The preview pane should show the same content as the desktop app.
3. If Zoom shows a **camera icon with a slash**, the producer never published a
   frame — verify the FrameWorker is `running=true` (status bar of the app).

## 6. Verifying in Chrome (`getUserMedia`)

1. Open https://webrtc.github.io/samples/src/content/devices/input-output/.
2. **Video source** dropdown → `AK Virtual Camera`.
3. Click **Open**. Chrome may ask for camera permission for the page; allow.

> Note: this only works when Chrome's MediaCapture is configured to use the
> DirectShow path. On modern Chrome/Edge (Win11) the default is Media
> Foundation, in which case our DShow filter is **not** visible. Phase 3 (MF
> Virtual Camera) covers those clients.

## 7. Debugging the DShow filter

Best entry point is `graphedt.exe` from the Windows SDK
(`C:\Program Files (x86)\Windows Kits\10\bin\<sdk>\x64\graphedt.exe`):

1. **Graph → Insert Filters → Video Capture Sources → AK Virtual Camera**.
2. Right-click the **Output** pin → **Render Pin**. The graph manager will
   add a Video Renderer.
3. **Graph → Run** (Ctrl+G). Frames flow through the same shared memory used
   by OBS/Zoom — you can run graphedt and OBS at the same time to confirm
   1→N broadcast.

Attach Visual Studio to a process that loads the filter (e.g. `obs64.exe`):

1. Start OBS (without picking the source yet).
2. **VS → Debug → Attach to Process** → `obs64.exe`.
3. Set breakpoints in `cvcam_stream.cpp::FillBuffer` / `framebus.cpp::wait_frame`.
4. In OBS, add the `AK Virtual Camera` source — your breakpoints should hit.

## 8. Debugging the Python side

VS Code `launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "AKVC desktop",
      "type": "python",
      "request": "launch",
      "module": "akvc_app",
      "console": "integratedTerminal",
      "subProcess": true,
      "justMyCode": false
    }
  ]
}
```

`subProcess: true` is essential to step into the FrameWorker subprocess.

## 9. Inspecting the shared region directly

```bat
python -c "import mmap; m = mmap.mmap(-1, 16*1024*1024, 'akvc-frames-v1'); print(m[:64].hex())"
```

Expected first 4 bytes: `41 4B 56 43` (= `'AKVC'`). If you see all zeros, the
producer hasn't created the region yet.

## 10. When something goes wrong

| Symptom | Diagnosis |
|---|---|
| Device appears but image is solid black/grey | producer not running; FillBuffer outputs placeholder |
| Device appears, but frame rate is 0–1 fps | source is slow or USB driver thrashing — try Test Pattern |
| OBS error "Failed to start capture" | media-type mismatch — restart the source pin (remove + re-add) |
| App crashes on Start | check `%LOCALAPPDATA%\AKVC\logs\akvc.worker.log` |
| Consumer CPU very high | mismatch in NV12 stride — verify `width == stride[0]` (Phase 2 requires no padding) |

## 11. Known limitations of the MVP

These are acknowledged Phase 2 limitations; **Phase 3 fixes them**:

1. The FrameWorker dies with the UI app, so the device shows placeholder
   (animated greyscale) once the app is closed.
2. Only x64 consumers can see the filter; 32-bit Skype Classic etc. cannot.
3. New Microsoft Teams, Edge MFCapture, Skype 8 are NOT covered (they use
   Media Foundation; Phase 3 ships an MF Virtual Camera).
4. No EV signing — SmartScreen and some AV vendors may warn on first launch.
