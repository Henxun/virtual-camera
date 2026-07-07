# AK Virtual Camera

Cross-platform virtual camera for video conferencing, livestreaming, and AI effects.

- **Windows**: DirectShow Source Filter (Phase 2) + Media Foundation Virtual Camera (Phase 3)
- **macOS**: CoreMediaIO Camera Extension (Phase 4)
- **Desktop**: Python 3.11–3.14 + PySide6, MVVM

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

If your host app needs to bundle the AKVC native runtime into its own package
layout, the package now also exposes distribution helpers:

```python
from akvc.distribution import prepare_macos_host_runtime

prepared = prepare_macos_host_runtime(
    "dist/amaran Desktop.app",
    app_executable="dist/amaran Desktop.app/Contents/MacOS/amaran Desktop",
    embed_extension=True,
)
layout = prepared.layout
env = prepared.env
```

That pattern is intended for external desktop apps such as `amaran-desktop`:
- `pip install` the SDK package
- copy packaged AKVC runtime assets into your own app bundle/resources
- optionally embed the generated `.systemextension` into `Contents/Library/SystemExtensions`
- pass the returned env vars into your app's virtual-camera backend

If you want the install step itself to generate the local macOS build outputs
before packaging the Python wheel/editable install, set:

```bash
AKVC_BUILD_MACOS_RUNTIME=1 pip install -e .
```

Optional overrides:
- `AKVC_MACOS_ARCHS="arm64 x86_64"`
- `AKVC_MACOS_DEPLOYMENT_TARGET=13.0`

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

On macOS you can also bind the default target name at construction time and
let the first `send()` / `push_frame()` trigger an implicit startup:

```python
import numpy as np
from akvc.sdk import VirtualCamera

vc = VirtualCamera(
    width=1280,
    height=720,
    fps=30,
    camera_name="AK Virtual Camera",
    direct_only=True,
)

frame = np.zeros((720, 1280, 3), dtype=np.uint8)
vc.send(frame)
vc.shutdown()
```

On macOS, if you want the closest path to
`/Users/admir/workspace/cameraextension/vcam.mm` and do not want a helper in
the frame hot path, you can also use the native direct-sender object directly:

```python
import numpy as np
from akvc import MacDirectCameraSender

sender = MacDirectCameraSender(
    width=1280,
    height=720,
    fps=30.0,
    camera_name="AK Virtual Camera",
)
try:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    sender.send(frame)
finally:
    sender.stop()
```

If you prefer to stay on the higher-level SDK surface while still requiring the
pure macOS direct path, use:

```python
from akvc.sdk import VirtualCamera

vc = VirtualCamera(width=1280, height=720, fps=30, direct_only=True)
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
