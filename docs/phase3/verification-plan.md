# Phase 3 — Verification Plan

This document is the explicit Phase 3 exit gate for the Windows Media Foundation virtual-camera path. It layers on top of the Phase 2 DShow verification and turns the Phase 3 MF-specific acceptance items into a concrete checklist.

## A. Build & registration

| # | Check | How | Pass criterion |
|---|---|---|---|
| A1 | Native build succeeds | `uv run tools/make.py build --python` from x64 VS prompt | exit code 0; `build/bin/Release/akvc-mf.dll` and `build/bin/Release/akvc_helper.exe` exist |
| A2 | (automated) Unit tests pass | `uv run python tools/make.py test` or targeted pytest | pytest exits 0 |
| A3 | Helper install surface exists | `uv run akvc helper status` | command exits 0 and prints helper install/runtime state |
| A4 | Helper install succeeds | `uv run akvc helper install` (admin/elevated approval if needed) | scheduled task or equivalent persistent launcher exists |
| A5 | MF COM registration is healthy | `powershell -ExecutionPolicy Bypass -File tools/diag/camera_audit.ps1` | MF source CLSID points at current `akvc-mf.dll`; `ThreadingModel=Both` |
| A6 | MF registration/start succeeds | `uv run akvc helper start` then `uv run akvc helper status` | helper reachable; MF virtual camera marked registered/started; no `ACCESS_DENIED` |

## B. Persistent helper lifecycle

| # | Check | How | Pass criterion |
|---|---|---|---|
| B1 | Installed helper is reachable | `uv run akvc helper status` | status shows helper pipe reachable |
| B2 | App start reuses persistent helper | start desktop app, click Start, then inspect `akvc helper status` | helper PID remains stable or is reused instead of respawn-per-start |
| B3 | Worker does not become bus owner | stop helper, then attempt stream start | start fails with actionable ownership error instead of silently creating `Global\\akvc-frames-v1` |
| B4 | Explicit helper stop works | `uv run akvc helper stop` then `uv run akvc helper status` | helper transitions to not running |
| B5 | Autostart config persists | reinstall or relaunch environment, then `uv run akvc helper status` | installed state remains visible without manual reconfiguration |

## C. MF enumeration & open path

| # | Check | How | Pass criterion |
|---|---|---|---|
| C1 | MF enumeration sees one logical AK camera | `uv run python tools/diag/mf_enum.py` | `AK Virtual Camera` appears once; duplicates are called out if present |
| C2 | PnP / DShow aggregation is coherent | `powershell -ExecutionPolicy Bypass -File tools/diag/camera_audit.ps1` | MF + DShow registrations point to one user-visible `AK Virtual Camera` path |
| C3 | Chrome or Edge sees device | open a WebRTC input-device sample in Chrome/Edge | `AK Virtual Camera` appears in the device list |
| C4 | Chrome or Edge opens device | choose `AK Virtual Camera` in Chrome/Edge | live preview starts without `NotReadableError` / timeout |
| C5 | Teams (new) sees and opens device | Teams Settings → Devices / Video | `AK Virtual Camera` appears and preview opens |

## D. Persistence after UI exit

| # | Check | How | Pass criterion |
|---|---|---|---|
| D1 | UI close does not kill helper | start streaming, close UI, then check `akvc helper status` | helper remains running |
| D2 | Placeholder takeover works | after UI close, wait > heartbeat timeout and inspect helper log/status | helper reports placeholder publishing instead of exiting |
| D3 | Device stays present for 30 seconds | close UI while Chrome/Edge/Teams preview is active | device remains open/available for at least 30 seconds |

## E. Cleanup & repair

| # | Check | How | Pass criterion |
|---|---|---|---|
| E1 | Helper uninstall removes persistent launcher | `uv run akvc helper uninstall` | helper autostart registration no longer exists |
| E2 | Repair path is explicit | invoke documented repair flow only when diagnostics show stale registration | no unnecessary remove/recreate on healthy startup |
| E3 | Manual stop leaves recoverable state | `uv run akvc helper stop`, then `uv run akvc helper start` | helper and MF camera can recover without deleting nodes manually |

## F. Phase 3 exit decision

Phase 3 is considered **complete** when all of the following pass on Windows 11 x64:

- A1–A6
- B1–B5
- C1–C5
- D1–D3
- E1–E3

If graphical consumers (Teams / Chrome / Edge) cannot be run in the current environment, those items are **BLOCKED**, not PASS. CLI/API-side checks (helper install/status/start, COM registration, MF enumeration, ownership behavior) are not allowed to be skipped.

## G. Recommended verification chain

```bat
uv run tools/make.py build --python
uv run akvc helper install
uv run akvc helper start
uv run akvc helper status
powershell -ExecutionPolicy Bypass -File tools/diag/camera_audit.ps1
uv run python tools/diag/mf_enum.py
uv run python -m akvc_app
uv run akvc status
uv run akvc doctor
```

A representative successful Phase 3 diagnostic run should show:

- helper installed / reachable
- MF source CLSID bound to the current `akvc-mf.dll`
- `AK Virtual Camera` visible in MF enumeration
- no duplicate or stale logical devices left unexplained
