# AK Virtual Camera

Cross-platform virtual camera for video conferencing, livestreaming, and AI effects.

- **Windows**: DirectShow Source Filter (Phase 2) + Media Foundation Virtual Camera (Phase 3)
- **macOS**: CoreMediaIO Camera Extension (Phase 4)
- **Desktop**: Python 3.11–3.12 + PySide6, MVVM

> Phase 2 (this snapshot) ships the Windows DirectShow MVP.
> The device appears in OBS Studio, Zoom, Chrome `getUserMedia`, WeChat, QQ, Discord, etc.
> Microsoft Teams (new) / Edge / Chrome via MFCapture / new Skype are covered in Phase 3.

## Quick start (SDK consumers)

Recommended for external PySide6 / Python apps:

```bash
pip install <repo-url>
```

After install you can use:

```python
from akvc.sdk import VirtualCamera
```

The package builds and bundles the Windows runtime assets during installation:
- `akvc_helper.exe`
- `akvc-mf.dll`
- `akvc-dshow.dll`

Minimal example:

```python
import numpy as np
from akvc.sdk import VirtualCamera

vc = VirtualCamera()
vc.start(name="AK Virtual Camera")

frame = np.zeros((720, 1280, 3), dtype=np.uint8)
vc.push_frame(frame)
vc.shutdown()
```

Important:
- `pip install` does **not** automatically register the DShow filter or grant admin rights.
- On Windows you still need an elevated shell for registration/runtime steps that require it.
- If you want OBS / Zoom / GraphStudioNext to discover the DShow device, run:

```bash
akvc register
akvc status
akvc doctor
```

For deeper diagnosis in a development checkout:

```bash
uv run python tools/diag/dshow_enum.py
```

That script verifies DShow registration, DirectShow enumeration, and live frame-bus traffic on `Global\\akvc-frames-v1`.

If you need the desktop app dependencies too:

```bash
pip install "<repo-url>[desktop]"
```

## Quick start (developers)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e .[desktop]

python tools\make.py configure
python tools\make.py build --python
python tools\make.py register      # admin required
python -m akvc_app
```

During local development, runtime asset lookup prefers fresh binaries under `build/bin/Release`, then the staged install-time runtime under `build/package-runtime/bin`, before packaged runtime resources.

See:
- `docs/integration-guide.md`
- `docs/phase2/build-guide.md`
- `docs/phase2/verification-plan.md`

## License

Apache-2.0. See `LICENSE` and `NOTICE`.

The DirectShow filter base classes (`third_party/baseclasses/`) are
distributed under Microsoft's sample license terms.
