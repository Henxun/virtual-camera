# Phase 3 — Native USB Capture Design

## Goal

Remove the runtime Python `cv2.VideoCapture` dependency from the Windows USB live-capture path while keeping the existing `UsbCameraProvider` / `create_provider_from_source_id()` seam unchanged for the rest of the app.

## Why this shape

The current runtime boundary is Python-owned only at physical-camera ingest:

- `akvc/core/frame_provider/usb.py` imports `cv2`
- `camera-core/native/src/providers/usb_provider.cpp` calls back into Python `cv2.VideoCapture`

That means the desktop runtime host is native-backed, but USB ingest still requires Python + OpenCV at runtime. The shortest safe migration is to keep the Python provider wrapper as an API shell and move real camera enumeration/open/read/close into `_core_native`.

## Files

- `camera-core/native/src/providers/usb_provider.cpp`
- `akvc/core/frame_provider/usb.py`
- `camera-core/build_support.py`
- `tests/unit/test_usb_provider.py`
- `tests/unit/test_service_facade.py`

## Design

### 1. Native device enumeration

Use Windows Media Foundation device enumeration (`MFEnumDeviceSources`) to list video-capture devices. The Python wrapper will keep exposing `usb:<index>` source IDs so the rest of the desktop code remains unchanged.

### 2. Native camera handle

Replace the pybind callback bridge with a native camera handle that owns:

- COM / MF initialization
- selected device activation
- `IMFSourceReader` creation
- media-type negotiation
- blocking sample reads
- conversion into AKVC `Frame` objects

The Python wrapper will store this native handle in `_cap`, but `_cap` will no longer be a Python `cv2.VideoCapture` object.

### 3. Output contract

The native capture path should emit `FOURCC_RGB24` frames so the existing native preview generation and pipeline stages continue to work unchanged:

- runtime-host preview path expects RGB24 before NV12 conversion
- `ResizeStage` / `ColorConvertStage` already handle RGB24 correctly

### 4. Media-type strategy

Prefer an `IMFSourceReader` output type of `MFVideoFormat_RGB32`, then convert BGRA/BGRX to AKVC RGB24 in native code. Keep a fallback path that accepts the negotiated current type when the exact requested size/fps cannot be set, as long as the subtype is one of the explicitly supported formats.

## Success criteria

1. `akvc/core/frame_provider/usb.py` no longer imports `cv2`.
2. `_core_native` no longer calls back into Python `cv2.VideoCapture` for enumerate/open/read/close.
3. `ServiceFacade.start()` still works with `usb:<index>` sources without API changes above the provider layer.
4. Build / run / tests pass with logged evidence under the project workflow.
