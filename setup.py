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
SOURCE_RUNTIME_BIN = ROOT / "akvc" / "_runtime" / "windows"
SOURCE_NATIVE_DIR = ROOT / "akvc"


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


def _copy_native_extension(target_dir: Path) -> None:
    staged_native = RUNTIME_STAGE / "akvc"
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = False
    for artifact in staged_native.glob("_core_native*.pyd"):
        shutil.copy2(artifact, target_dir / artifact.name)
        if artifact.name != "_core_native.pyd":
            shutil.copy2(artifact, target_dir / "_core_native.pyd")
        copied = True
    if not copied:
        raise RuntimeError("missing staged native extension: _core_native*.pyd")


def _has_source_runtime() -> bool:
    return all((SOURCE_RUNTIME_BIN / name).is_file() for name in RUNTIME_FILES)


def _has_source_native_extension() -> bool:
    return any(SOURCE_NATIVE_DIR.glob("_core_native*.pyd"))


def _ensure_editable_runtime_ready() -> None:
    if _has_source_runtime() and _has_source_native_extension():
        return
    _stage_windows_runtime()
    _copy_native_extension(SOURCE_NATIVE_DIR)


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
        _copy_native_extension(Path(self.build_lib) / "akvc")


if _editable_wheel is not None:

    class editable_wheel(_editable_wheel):
        def run(self) -> None:
            _ensure_editable_runtime_ready()
            super().run()

    CMDCLASS = {
        "build_py": build_py,
        "editable_wheel": editable_wheel,
    }
else:
    CMDCLASS = {
        "build_py": build_py,
    }


setup(
    cmdclass=CMDCLASS,
)
