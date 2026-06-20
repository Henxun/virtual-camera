---
name: windows-virtual-camera
description: Build a Windows virtual camera (DirectShow + Media Foundation dual-stack). Covers frame bus shared memory, DShow source filter, MF VirtualCamera MediaSource DLL, helper service, and the full set of integration pitfalls verified working in Chrome/OBS. Use when developing, debugging, or extending a Windows virtual camera.
---

# Windows Virtual Camera Development

A field-tested guide to building a Windows virtual camera that works across **both** the legacy DirectShow path (OBS/Zoom/WeChat) and the modern Media Foundation path (Chrome/Edge/Teams). Distilled from a full from-scratch implementation (AK Virtual Camera, Phase 2 + Phase 3) where every pitfall below was hit and resolved with evidence.

## 1. The two-path reality (read first)

Windows camera consumers split across two capture stacks:

| Consumer | Stack | Sees DShow filter? | Sees MF VirtualCamera? |
|---|---|---|---|
| OBS Studio | DirectShow | ✅ | ❌ |
| Zoom / WeChat / Discord (legacy) | DirectShow | ✅ | ❌ |
| **Chrome / Edge** | Media Foundation | ❌ | ✅ |
| **Microsoft Teams (new) / Skype 8** | Media Foundation | ❌ | ✅ |
| Windows Camera app | Media Foundation | ❌ | ✅ |

**Conclusion**: to cover all consumers you need BOTH a DShow source filter AND an MF VirtualCamera, sharing one frame source. A DShow-only camera will never appear in Chrome; an MF-only camera won't appear in OBS.

## 2. Architecture

```
Producer side (user session):
  UI App ──spawn──▶ FrameWorker (writes frames to SHM)
  UI App ──spawn──▶ Helper (owns Global\ SHM, registers MF device,
                              publishes placeholder frames when UI gone)

Consumer side:
  OBS/Zoom ──▶ DShow filter (akvc-dshow.dll, in-proc) ──▶ reads SHM
  Chrome/Edge ──▶ frameserver.exe (session 0) ──loads──▶ akvc-mf.dll
                  └─ IMFActivate → MediaSource → RequestSample → reads SHM

Shared:
  Global\akvc-frames-v1   (named file mapping, ring buffer, 4 slots)
  Global\akvc-frames-evt-v1 (new-frame event)
  Global\akvc-frames-mtx-v1 (write mutex)
```

## 3. Frame Bus (shared memory ring buffer)

### 3.1 Naming — use Global\, not Local\

**Critical pitfall**: `frameserver.exe` (the MF frame server) runs in **session 0**. `Local\` named objects are per-session-isolated — session 0 cannot see a `Local\akvc-frames-v1` created in the user session. The MF source's `OpenFileMappingW` returns `ERROR_FILE_NOT_FOUND` (le=2) and `Start()` fails.

- Use `Global\akvc-frames-v1` for the SHM, event, and mutex.
- Creating `Global\` objects requires `SeCreateGlobalPrivilege`. A normal user gets `ERROR_ACCESS_DENIED` (5). **The Helper must run elevated (admin)**, or be a Windows service (session 0 services have the privilege automatically).
- The DShow path (OBS) runs in-process with the consumer in the user session, so `Local\` worked there — but once MF is in the mix you must switch everything to `Global\`.

### 3.2 Protocol (akvc_protocol.h)

Ring control block (128 bytes, `#pragma pack(8)`):
```
magic, schema_version, slot_count, slot_size,
producer_seq (uint64), writer_pid, consumer_count,
created_pts_100ns, producer_heartbeat (uint64),
helper_pid, helper_reserved, pad[72]
```

Frame header (80 bytes, `#pragma pack(1)`):
```
magic, schema, fourcc, width, height, stride[2],
plane_offset[2], plane_size[2], flags, pts_100ns,
seq_head (uint64), seq_tail (uint64), reserved[2]
```

### 3.3 Tear protection — the #1 source of "frozen video"

Producer writes: `seq_head` → payload → `seq_tail` (with memory barriers). Reader validates `seq_head == seq_tail == producer_seq`.

**Pitfall**: if the reader snapshots `producer_seq` once and retries `seq_head`/`seq_tail` against that stale snapshot, a fast producer (30fps) advances `producer_seq` between the snapshot and the read, so `head(old) != producer_seq(new)` forever → `E_AKVC_FRAMEBUS_TORN_FRAME` on every frame.

**Fix**: on each tear-protection retry, **re-read `producer_seq`** and recompute the slot:
```cpp
for (int retry = 0; retry < 5; ++retry) {
    producer_seq = ctrl->producer_seq;        // re-read every retry
    slot_index = (producer_seq - 1) % slot_count;
    hdr = slot_ptr(slot_index);
    head = hdr->seq_head; MemoryBarrier();
    tail = hdr->seq_tail;
    if (head == tail && tail == producer_seq) { /* valid */ }
    SwitchToThread();
}
```

### 3.4 Heartbeat — the #1 source of "first frame shows, then frozen"

The Helper monitors `producer_heartbeat` to decide whether to publish placeholder (black) frames when the UI is gone. **The heartbeat time base MUST match between producer and Helper.**

**Pitfall (the actual bug that froze Chrome video)**: the Python worker wrote `producer_heartbeat` using `time.perf_counter_ns()` (relative, from process start), while the Helper read it and compared against `GetSystemTimePreciseAsFileTime` (absolute, since 1601). The elapsed delta was always enormous → Helper always thought the UI was gone → Helper continuously published placeholder frames that **overwrote the worker's real frames**. Chrome received only `flags=4` (PLACEHOLDER) black frames — the moving box appeared static.

**Fix**: both sides use `GetSystemTimeAsFileTime` (100ns ticks). In Python:
```python
ft = ctypes.wintypes.FILETIME()
_kernel32.GetSystemTimeAsFileTime(ctypes.byref(ft))
now_100ns = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
```

**Diagnostic**: log `hdr->flags` on every delivered frame. If you see `flags=4` (PLACEHOLDER) when the UI is actively streaming, the heartbeat time bases disagree.

## 4. DirectShow source filter (akvc-dshow.dll)

Standard `CSource` + `CSourceStream` from the Microsoft BaseClasses (Windows-classic-samples). Key points:

- Register under `CLSID_VideoInputDeviceCategory` via `IFilterMapper2` / `AMovieDllRegisterServer2`.
- `FillBuffer` reads from the Frame Bus consumer; on miss, output an animated placeholder so the device looks "alive".
- **Resolution must match the producer**: if the filter negotiates 1080p but the producer writes 720p, consumers get garbled/black video. Default the filter's media type to the producer's actual output (e.g. 720p NV12).

### BaseClasses build issues (modern MSVC / Windows SDK 10.0.26100)

- `GUID_NULL` is no longer `DEFINE_GUID`'d in `<uuids.h>` in new SDKs → force-include a `patch_guid.h` that does `DEFINE_GUID(GUID_NULL, 0L, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)`.
- `videoctl.cpp` / `ddmm.cpp` / `vtrans.cpp` pull in DirectDraw that the new compiler rejects → exclude them from the static lib.
- `transip.h` has an illegal qualified member name `HRESULT IMemInputPin::Copy` → patch to `HRESULT Copy`.
- Use `/permissive` (not `/permissive-`) and a broad `/wd####` suppress list. The build tool (`make.py`) rewrites `CMakeLists.txt` from an embedded template each run, so patch the template in `make.py`, not the generated file.

## 5. Media Foundation VirtualCamera (akvc-mf.dll) — the hard part

This is where most implementations stall. The frame server (`frameserver.exe`) loads the DLL via COM and has strict expectations. Reference implementations: `microsoft/Windows-Camera` Samples/VirtualCamera, `smourier/VCamSample`.

### 5.1 Registration (Synthetic / non-wrapping camera)

```cpp
MFCreateVirtualCamera(
    MFVirtualCameraType_SoftwareCameraSource,
    MFVirtualCameraLifetime_Session,      // Session = dies with helper process
    MFVirtualCameraAccess_CurrentUser,
    L"AK Virtual Camera",
    sourceId,       // = the MediaSource CLSID string "{...}"
    nullptr, 0,     // categories MUST be null/0 (NOT KSCATEGORY_VIDEO_CAMERA)
    &vc);
vc->SetUINT32(VCAM_KIND, 0);              // custom attr the activate reads
// Do NOT call AddDeviceSourceInfo — that's only for wrapping a physical
// camera (takes the physical cam's symbolic link, not a CLSID).
vc->Start(nullptr);
// Keep the vc reference alive for the helper's lifetime (don't Release).
```

- The CLSID must be registered under `HKLM\SOFTWARE\Classes\CLSID\{...}\InprocServer32` with `ThreadingModel=Both`, or the frame server returns `CO_E_CLASSSTRING` (0x800401f3).
- `MFVirtualCameraLifetime_Session` devices disappear when the helper exits. Use `System` lifetime + a service for persistence.

### 5.2 DLL structure — frame server wants IMFActivate, not IMFMediaSource

**The single most important insight**: `frameserver.exe` instantiates the CLSID and `QueryInterface`s for **`IMFActivate`** (IID `{7FEE9E9A-4A89-47A6-899C-B6A53A70FB67}`), NOT `IMFMediaSource`. If your class factory returns only `IMFMediaSource`, you get `E_NOINTERFACE` and `Start()` fails.

Implement a `MediaSourceActivate` that:
- Inherits `IMFActivate` (which inherits `IMFAttributes` — you must implement all ~30 `IMFAttributes` methods, delegating to an `MFCreateAttributes` store).
- `ActivateObject(REFIID riid, ...)` creates and returns the real `MediaSource` (QI for `IID_IMFMediaSourceEx {3C9B2EB9-...}`).
- `ShutdownObject` is a **NO-OP** (do NOT call `source->Shutdown()` here — that causes `MF_E_SHUTDOWN` on subsequent frame-server ops). Only `DetachObject` / the destructor release the source.

### 5.3 MediaSource interfaces

`MediaSource` must implement (multi-inherit):
- `IMFMediaSourceEx` (→ `IMFMediaSource` → `IMFMediaEventGenerator`)
- `IMFGetService` — return `MF_E_UNSUPPORTED_SERVICE`
- `IKsControl` — `KsProperty`/`KsMethod`/`KsEvent` return `HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND)` for unsupported property sets (this is the AVStream-driver convention the frame server expects; returning `E_NOTIML` makes it loop forever)
- `IMFSampleAllocatorControl` — see §5.6

`QueryInterface` must answer: `IUnknown`, `IMFMediaEventGenerator`, `IMFMediaSource`, `IMFMediaSourceEx`, `IMFGetService`, `IKsControl` (`__uuidof(IKsControl)`), `IMFSampleAllocatorControl`.

### 5.4 Mandatory attributes (without these, `Start()` fails)

`GetSourceAttributes` returns a persistent `IMFAttributes` with:
- `MF_DEVICEMFT_SENSORPROFILE_COLLECTION` = an `IMFSensorProfileCollection` containing at least a **Legacy** profile (`MFCreateSensorProfile(KSCAMERAPROFILE_Legacy, 0, nullptr, ...)`, with `AddProfileFilter(streamId, L"((RES==;FRT<=30,1;SUT==))")`). Missing this → `MF_E_ATTRIBUTENOTFOUND`.

`GetStreamAttributes(streamId)` returns `IMFAttributes` with:
- `MF_DEVICESTREAM_STREAM_CATEGORY` = `PINNAME_VIDEO_CAPTURE` (NOT `KSCATEGORY_VIDEO_CAMERA`)
- `MF_DEVICESTREAM_STREAM_ID`
- `MF_DEVICESTREAM_FRAMESERVER_SHARED` = 1
- `MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES` = `MFFrameSourceTypes_Color`

The stream descriptor (created in the source ctor, before `Start`) must call `handler->SetCurrentMediaType(mediaType)` after `MFCreateStreamDescriptor` — without it the frame server can't negotiate a format and the video is black.

`MF_DEVICESTREAM_*` and sensor-profile GUIDs need `INITGUID` defined + link `mfplat mfuuid mfsensorgroup`.

### 5.5 Start flow (without MENewStream, Chrome times out)

```cpp
HRESULT Start(IMFPresentationDescriptor* desc, ...) {
    fb_consumer.open();                         // Global\ SHM
    // Announce the stream to the frame server:
    IUnknown* streamUnk; stream->QI(IID_PPV_ARGS(&streamUnk));
    event_queue_->QueueEventParamUnk(MENewStream, GUID_NULL, S_OK, streamUnk);
    stream->QueueEvent(MEStreamStarted, GUID_NULL, S_OK, nullptr);
    QueueEvent(MESourceStarted, GUID_NULL, S_OK, nullptr);
    return S_OK;
}
```
Skipping `MENewStream` → the frame server never calls `RequestSample` → Chrome errors `Timeout starting video source (AbortError)`.

### 5.6 Sample delivery — use the frame server's allocator

**Pitfall**: allocating the sample buffer with `MFCreateMemoryBuffer` (a 1D buffer) produces samples the frame server receives but renders as black. The frame server expects a 2D buffer with a proper stride.

**Fix**: implement `IMFSampleAllocatorControl`:
- `GetAllocatorUsage` returns `MFSampleAllocatorUsage_UsesProvidedAllocator`.
- The frame server then calls `SetDefaultAllocator(streamId, pAllocator)`. QI `pAllocator` for `IMFVideoSampleAllocator`, call `InitializeSampleAllocator(10, mediaType)`, store it.

`RequestSample(token)` (pull model — the frame server calls this):
```cpp
wait_frame(fv);                                  // from Frame Bus
IMFSample* sample;
allocator->AllocateSample(&sample);              // 2D buffer, correct stride
IMFMediaBuffer* buf; sample->GetBufferByIndex(0, &buf);
IMF2DBuffer2* buf2d; buf->QueryInterface(&buf2d);
BYTE* scan0; LONG pitch; BYTE* start; DWORD len;
buf2d->Lock2DSize(MF2DBuffer_LockFlags_Write, &scan0, &pitch, &start, &len);
// Y plane (row by row, respecting pitch):
for (y in 0..h) memcpy(scan0 + y*pitch, fv.plane0 + y*w, w);
// UV plane (interleaved, half height, same pitch):
BYTE* uv = scan0 + pitch*h;
for (y in 0..h/2) memcpy(uv + y*pitch, fv.plane1 + y*w, w);
buf2d->Unlock2D();
sample->SetSampleTime(MFGetSystemTime());        // NOT the worker's pts
sample->SetSampleDuration(333333);               // ~30fps
if (token) sample->SetUnknown(MFSampleExtension_Token, token);
event_queue_->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, sample);
```

**Pitfall**: `SetSampleTime` must use `MFGetSystemTime()` (MF system time), not the worker's `perf_counter`-based `pts_100ns`. A wrong time base → black video.

The `.def` file must export `DllGetClassObject` and `DllCanUnloadNow` (registration is via `MFCreateVirtualCamera`, not `regsvr32`).

### 5.7 Debugging inside frameserver.exe

The frame server is a system service with no stderr. Use **both**:
- `OutputDebugStringA` (visible in DebugView).
- A log file written next to the DLL (`akvc-mf.log`) — get the DLL path via `GetModuleHandleW(L"akvc-mf")` + `GetModuleFileNameW`.

The frame server **caches the DLL**. After rebuilding `akvc-mf.dll`, you must restart the FrameServer service (admin) or it keeps running the old code:
```powershell
Stop-Service FrameServer; Start-Service FrameServer
```

### 5.8 Diagnostic progression (map error → cause)

| `Start()` / Chrome error | Cause | Fix |
|---|---|---|
| `E_NOINTERFACE` (0x80004002) | class factory returns IMFMediaSource, not IMFActivate | implement MediaSourceActivate |
| `CO_E_CLASSSTRING` (0x800401f3) | CLSID not in HKLM registry | write InprocServer32 + ThreadingModel |
| `ERROR_DEV_NOT_EXIST` (0x80070037) from AddDeviceSourceInfo | called AddDeviceSourceInfo on a Synthetic camera | remove the call |
| `MF_E_NOT_INITIALIZED` (0xc00d36b6) | GetSourceAttributes returned E_NOTIML | return valid attrs with sensor profile |
| `MF_E_ATTRIBUTENOTFOUND` (0xc00d36e6) | missing sensor profile collection / stream attrs | see §5.4 |
| `MF_E_SHUTDOWN` (0xc00d3e85) | ShutdownObject called source->Shutdown | make ShutdownObject a no-op |
| Chrome `NotReadableError` | missing IKsControl | implement IKsControl returning ERROR_SET_NOT_FOUND |
| Chrome `Timeout starting video source` (AbortError) | Start didn't send MENewStream | see §5.5 |
| `FrameBus open le=2 session=0` | Local\ SHM invisible to session-0 frame server | use Global\ + admin helper |
| `TORN_FRAME` | tear-protection used stale producer_seq | re-read producer_seq each retry |
| video shows first frame then frozen | heartbeat time-base mismatch → placeholders overwrite real frames | see §3.4 |
| video delivered but black | MFCreateMemoryBuffer (1D) / no SetCurrentMediaType / wrong sample time | see §5.6, §5.4, §5.6 |

## 6. Helper service

Owns the `Global\` SHM and registers the MF device. Responsibilities:
- Create the file mapping / event / mutex (with a SDDL granting `AU` Authenticated Users + `AC` AppContainer + `ALL_APP_PACKAGES` so both the user-session worker and the session-0 frame server can access).
- Monitor `producer_heartbeat`; when stale, publish placeholder frames so consumers never freeze.
- Register the MF virtual camera once (`MFCreateVirtualCamera` + `Start`); keep the `IMFVirtualCamera` reference alive.
- Must run **elevated** (for `SeCreateGlobalPrivilege`). Long-term: make it a Windows service.

IPC: stdin/stdout binary protocol (uint32 command → uint32 response). Named pipes leave stale kernel objects when the process is killed, so stdin/stdout is more robust.

Register MF **once per helper lifetime** — re-calling `MFCreateVirtualCamera` for an already-registered device makes it disappear from Chrome.

## 7. Operation cheat-sheet

Build (from an elevated VS / make.py):
```
uv run tools/make.py configure
uv run tools/make.py build --python
```

Run (admin shell — needed for Global\ SHM):
```
uv run python -m akvc_app      # start UI, pick a source, click Start
```

After rebuilding `akvc-mf.dll` (admin):
```powershell
Stop-Service FrameServer; Start-Service FrameServer
```

Test consumers:
- OBS: Sources → Video Capture Device → AK Virtual Camera (DShow path)
- Chrome: https://webrtc.github.io/samples/src/content/devices/input-output/ → AK Virtual Camera (MF path)
- Diagnose MF: read `build/bin/Release/akvc-mf.log`

## 8. Key references

- `microsoft/Windows-Camera` → `Samples/VirtualCamera/VirtualCameraMediaSource` (SimpleMediaSource, VirtualCameraMediaSourceActivate) — the authoritative MF sample.
- `smourier/VCamSample` — a simpler working MF virtual camera; useful for the `IMFSampleAllocatorControl` + `IMF2DBuffer2` pattern.
- `microsoft/Windows-classic-samples` → BaseClasses for the DShow filter.
- Windows SDK headers: `mfvirtualcamera.h` (MFCreateVirtualCamera, IMFVirtualCamera), `mfidl.h` (IMFMediaSourceEx, sensor profiles, MF_DEVICESTREAM_*), `ks.h`/`ksmedia.h` (IKsControl, PINNAME_VIDEO_CAPTURE, KSCAMERAPROFILE_*).
