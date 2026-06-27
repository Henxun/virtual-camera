# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

try:
    from setuptools.command.editable_wheel import editable_wheel as _editable_wheel
except ImportError:  # pragma: no cover
    _editable_wheel = None

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
RUNTIME_STAGE = BUILD / "package-runtime"
RUNTIME_BIN = RUNTIME_STAGE / "bin"
RUNTIME_FILES = ("akvc_helper.exe", "akvc-dshow.dll", "akvc-mf.dll")


def _run_make(*args: str) -> None:
    subprocess.check_call([sys.executable, str(ROOT / "tools" / "make.py"), *args], cwd=ROOT)


def _stage_windows_runtime() -> Path | None:
    if sys.platform != "win32":
        return None

    _run_make("install-runtime", "--prefix", str(RUNTIME_STAGE))

    missing = [name for name in RUNTIME_FILES if not (RUNTIME_BIN / name).is_file()]
    if missing:
        raise RuntimeError(f"missing staged runtime artifacts: {', '.join(missing)}")
    return RUNTIME_BIN


class build_py(_build_py):
    def run(self) -> None:
        super().run()

        runtime_bin = _stage_windows_runtime()
        if runtime_bin is None:
            return

        target_dir = Path(self.build_lib) / "akvc" / "_runtime" / "windows"
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in RUNTIME_FILES:
            shutil.copy2(runtime_bin / name, target_dir / name)


if _editable_wheel is not None:

    class editable_wheel(_editable_wheel):
        def run(self) -> None:
            _stage_windows_runtime()
            super().run()

    CMDCLASS = {
        "build_py": build_py,
        "editable_wheel": editable_wheel,
    }
else:
    CMDCLASS = {"build_py": build_py}


setup(cmdclass=CMDCLASS)
