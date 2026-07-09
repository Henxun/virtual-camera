# AK Virtual Camera — Desktop App

PySide6 desktop application built on top of the repo's compatibility layer.

```bash
python -m akvc_app
```

## Position in the architecture

The desktop app is **not** the architecture source of truth.
It sits above the canonical split:

- `virtualcam/` — native driver/runtime layer
- `camera-core/` — cross-platform control layer
- desktop app — PySide6 UI that consumes the thin Python binding and compatibility helpers

Use this app when you want to:

- validate the end-user streaming flow
- exercise the compatibility layer from Python/PySide6
- inspect macOS Camera Extension activation and status from a GUI

## Runtime notes

- On Windows, the app ultimately drives the frame-bus producer / virtual-camera runtime path.
- On macOS, the app participates in activation, status inspection, and producer startup, but the Camera Extension remains the native system-facing implementation.
- The app should be understood as a host/client of the control layer, not as the definition of the virtual-camera architecture itself.

## macOS status UX

The desktop app currently exposes the accepted macOS activation/status baseline, including:

- Camera Extension activation state
- device visibility feedback
- `Activate` / `Open Settings` / `Recheck` actions
- guidance for approval / retry / target-app validation
- readiness gating before `Start`
- runtime dependency checks for `numpy` / `cv2`
- IPC status summaries and validation hints
- capability summaries such as supported formats / frame rates
- runtime topology summaries that explain the host/container role

## PySide6 compatibility helpers

The repo also keeps Python/PySide6 integration helpers for compatibility scenarios, such as:

- `push_qimage(...)`
- `push_qpixmap(...)`
- `push_widget(...)`
- `push_screen(...)`
- latest-frame provider / streamer helpers
- demo and validation scripts for PySide6-driven producer flows

These are useful integration tools, but they should be treated as consumers of the control/runtime stack rather than as the primary architecture contract.
