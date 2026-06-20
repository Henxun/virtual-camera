# AK Virtual Camera

Cross-platform virtual camera for video conferencing, livestreaming, and AI effects.

- **Windows**: DirectShow Source Filter (Phase 2) + Media Foundation Virtual Camera (Phase 3)
- **macOS**: CoreMediaIO Camera Extension (Phase 4)
- **Desktop**: Python 3.12 + PySide6, MVVM

> Phase 2 (this snapshot) ships the Windows DirectShow MVP.
> The device appears in OBS Studio, Zoom, Chrome `getUserMedia`, WeChat, QQ, Discord, etc.
> Microsoft Teams (new) / Edge / Chrome via MFCapture / new Skype are covered in Phase 3.

## Quick start (developers)

```
python -m venv .venv
.venv\Scripts\activate
pip install -e camera-core -e apps\desktop -e apps\cli

python tools\make.py configure
python tools\make.py build
python tools\make.py register      # admin required
python tools\make.py run
```

See `docs/phase2/build-guide.md`, `run-debug-guide.md`, `verification-plan.md`.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.

The DirectShow filter base classes (`third_party/baseclasses/`) are
distributed under Microsoft's sample license terms.
