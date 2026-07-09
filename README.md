# AK Virtual Camera

Cross-platform virtual camera workspace.

- **`virtualcam/`** — native virtual-camera driver layer
  - Windows: DirectShow + Media Foundation
  - macOS: CoreMediaIO Camera Extension
- **`camera-core/`** — pure C++ / ObjC++ control layer for opening the virtual camera, starting the runtime path, and pushing frames
- **`apps/desktop/`** — PySide6 desktop app built on top of the thin Python binding

## Current architecture

The canonical architecture in this repo is:

1. native driver/runtime under `virtualcam/`
2. cross-platform control API under `camera-core/`
3. thin Python compatibility layer for the desktop app and Python-based integrations

That means the old `akvc.sdk` and `akvc` CLI surfaces should be understood as **compatibility/integration entrypoints**, not as the primary architecture definition.

For the current macOS baseline, see:
- [docs/macos/architecture.md](docs/macos/architecture.md)
- [docs/phase4/implementation-plan.md](docs/phase4/implementation-plan.md)
- [docs/phase4/verification-plan.md](docs/phase4/verification-plan.md)

## What is verified now

- Windows virtual-camera paths have been validated across the current DirectShow / Media Foundation rollout.
- macOS Camera Extension flow has passed acceptance on a real Mac.
- The macOS packaging flow includes a Nuitka app-bundle path used for validation in this repo.

## Integration surfaces

### Canonical control surface

The preferred long-term integration target is the native control layer under `camera-core/`.
Its public contract is centered on the `akvc::VirtualCamera` C++ API plus the platform sessions behind it.

### Python compatibility surface

The repo still keeps a thin Python binding and compatibility-oriented Python surfaces for:

- the desktop app in [apps/desktop](apps/desktop)
- Python-based diagnostics and demos
- external Python/PySide6 integrations that are not ready to move to the native API directly

Those surfaces remain supported as integration helpers, but they are not the source of truth for architecture decisions.

## macOS packaging and validation

The current repo-owned macOS packaging helper is [tools/package_nuitka.py](tools/package_nuitka.py).
It exists to package the desktop app, patch the bundle metadata, embed the `.systemextension`, and sign the resulting `.app` for validation.

For contributor-facing macOS validation and debug flow, see:
- [docs/phase4/run-debug-guide.md](docs/phase4/run-debug-guide.md)
- [docs/phase4/verification-plan.md](docs/phase4/verification-plan.md)

## Developer quick start

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e .[desktop]
python tools\make.py configure
python tools\make.py build --python
```

Desktop app:

```bat
python -m akvc_app
```

Windows registration / diagnostics when needed:

```bat
python tools\make.py register
uv run python tools/diag/dshow_enum.py
```

## Compatibility note

If you still consume `akvc.sdk` or the `akvc` CLI from older tooling, treat them as compatibility wrappers around the newer runtime/control-layer direction. New documentation and architecture decisions should follow the native `virtualcam/` + `camera-core/` split first.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The DirectShow filter base classes under `third_party/baseclasses/` are distributed under Microsoft's sample license terms.
