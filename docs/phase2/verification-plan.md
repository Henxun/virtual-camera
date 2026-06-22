# Phase 2 — Verification Plan

This document is the explicit Phase 2 exit gate. All checks are manual unless
labeled **(automated)**. Each check has a clear pass criterion.

## A. Build & registration

| # | Check | How | Pass criterion |
|---|---|---|---|
| A1 | Native build succeeds | `python tools\make.py build --python` from x64 VS prompt | exit code 0; `build\bin\Release\akvc-dshow.dll` exists |
| A2 | (automated) Unit tests pass | `python tools\make.py test` or `pytest -q` | pytest exits 0 |
| A3 | DLL has version info | right-click DLL → Properties → Details | ProductName = "AK Virtual Camera", FileVersion = "0.2.0.0" |
| A4 | Registration succeeds | `python tools\make.py register` (admin) or `akvc register` | regsvr32 returns 0; `akvc status` shows DLL path |
| A5 | CLI self-check passes | `akvc status` + `akvc doctor` | DLL path shown; doctor exits 0 |
| A6 | DShow category registration exists | `uv run python tools/diag/dshow_enum.py` | registration section PASS |
| A7 | Unregister leaves no residue | `python tools\make.py unregister` then `akvc status` | `(not registered)` |

## B. Producer / FrameWorker

| # | Check | How | Pass criterion |
|---|---|---|---|
| B1 | UI starts | `python -m akvc_app` | window opens, source dropdown populated (at least Test Pattern) |
| B2 | Worker spawns on Start | click Start | Status bar shows "Streaming"; FPS ≈ 30; logs at `%LOCALAPPDATA%\AKVC\logs\akvc.worker.log` |
| B3 | Worker stops on Stop | click Stop | Status returns to "Idle"; FPS = 0; mapping released within 5s |
| B4 | Shared region is created and valid | while running, execute `uv run python tools/diag/dshow_enum.py` | frame-bus section shows `magic 0x43564B41`, non-zero `producer_seq`, and `frame valid: True` |
| B5 | App close also stops worker | close the UI window | worker process exits within 5s |

> 当前 frame bus 诊断名是 `Global\\akvc-frames-v1`。如你看到 `Local\\...`，那是旧说明。

## C. Consumer compatibility

Run with **Test Pattern** source so movement is unambiguous.

| # | Consumer | Steps | Pass criterion |
|---|---|---|---|
| C1 | OBS Studio 30+ | Sources → Video Capture Device → AK Virtual Camera; pixel format NV12; 1280×720@30 | colorbar with moving scan line, 30fps reported in OBS Stats |
| C2 | Zoom Desktop (current) | Settings → Video → Camera → AK Virtual Camera | same content visible in self-preview |
| C3 | Chrome — webrtc samples | open https://webrtc.github.io/samples/src/content/devices/input-output/, choose AK Virtual Camera | live preview of pattern |
| C4 | WeChat (PC) | Settings → Audio/Video → Camera → AK Virtual Camera | live preview |
| C5 | Discord | Settings → Voice & Video → Camera → AK Virtual Camera | live preview |
| C6 | graphedt / GraphStudioNext | Insert filter → render output pin → Run | Video Renderer window shows pattern |

**Phase 2 does NOT verify**:

- Microsoft Teams (new) — uses MF, covered in Phase 3
- Edge / new Chrome on a profile that picked Media Foundation capture
- Skype 8 — uses MF
- 32-bit hosts (no x86 DLL in Phase 2)

## D. Stability

| # | Check | How | Pass criterion |
|---|---|---|---|
| D1 | 30-min soak | Start, leave OBS receiving for 30 minutes | FPS stays within ±1 of target; `frames_dropped` < 0.5% of `frames_published` |
| D2 | UI restart | Start, close app without Stop, reopen, Start again | works, no errors in logs |
| D3 | 1→N broadcast | Open OBS, Zoom, graphedt simultaneously consuming | all three render the pattern |
| D4 | UI crash recovery | with worker running, kill the UI process via Task Manager → Subprocess Tree | OBS shows static placeholder image instead of crashing |

## E. Cleanup

| # | Check | How | Pass criterion |
|---|---|---|---|
| E1 | Unregister removes CLSID key | unregister, then `reg query "HKCR\CLSID\{8E14549A-...}"` | "ERROR: The system was unable to find the specified registry key or value." |
| E2 | Unregister removes Filter Mapper entry | open graphedt → Video Capture Sources | AK Virtual Camera no longer listed |
| E3 | DLL deletable after unregister | delete `build\bin\Release\akvc-dshow.dll` | no "in use" error |

## F. Phase 2 exit decision

Phase 2 is considered **complete** when all of A, B, C1–C3, D1–D2, E1–E2 pass on:

- Windows 10 22H2 (x64) — minimum supported
- Windows 11 23H2 (x64) — primary target

Failures in C4–C6 and D3–D4 are **non-blocking** for Phase 2 (treated as
known limitations), but D1 and D2 must pass.

## G. Current validated command chain

The current recommended verification chain for repository-local work is:

```bat
python tools\make.py build --python
akvc register
akvc status
akvc doctor
uv run python tools/diag/dshow_enum.py
```

A representative successful diagnostic run should report:

- Registration: `PASS`
- DirectShow: `PASS`
- Frame Bus: `PASS`

with `AK Virtual Camera` visible in the DirectShow enumeration output.
