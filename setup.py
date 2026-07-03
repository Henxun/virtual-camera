# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
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
MACOS_RUNTIME_STAGE = RUNTIME_STAGE / "macos"
MACOS_RUNTIME_SOURCE_DIR = ROOT / "akvc" / "_runtime" / "macos"
MACOS_BUILD_DIR = BUILD / "macos" / "Build" / "Products" / "Release"
MACOS_PKG = BUILD / "macos" / "VirtualCamera.pkg"
MACOS_EXTENSION_BUNDLE = MACOS_BUILD_DIR / "com.sidus.amaran-desktop.cameraextension.systemextension"
RUNTIME_FILES = ("akvc_helper.exe", "akvc-dshow.dll", "akvc-mf.dll")
MACOS_RUNTIME_FILES = (
    "akvc-macos-status",
    "akvc-macos-install",
    "akvc-macos-uninstall",
    "akvc-macos-list-devices",
    "akvc-macos-sync-ipc",
    "libakvc-macos-direct-sender.dylib",
    "VirtualCamera.pkg",
)


def _run_make(*args: str) -> None:
    subprocess.check_call([sys.executable, str(ROOT / "tools" / "make.py"), *args], cwd=ROOT)


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _stage_windows_runtime() -> Path | None:
    if sys.platform != "win32":
        return None

    _run_make("install-runtime", "--prefix", str(RUNTIME_STAGE))

    missing = [name for name in RUNTIME_FILES if not (RUNTIME_BIN / name).is_file()]
    if missing:
        raise RuntimeError(f"missing staged runtime artifacts: {', '.join(missing)}")
    return RUNTIME_BIN


def _maybe_build_macos_runtime() -> None:
    if sys.platform != "darwin":
        return
    if not _truthy_env("AKVC_BUILD_MACOS_RUNTIME"):
        return

    args = ["build"]
    archs = os.environ.get("AKVC_MACOS_ARCHS", "").strip()
    deployment_target = os.environ.get("AKVC_MACOS_DEPLOYMENT_TARGET", "").strip()
    if archs:
        args.extend(["--archs", archs])
    if deployment_target:
        args.extend(["--deployment-target", deployment_target])
    _run_make(*args)


def _stage_macos_runtime() -> Path | None:
    if sys.platform != "darwin":
        return None

    _maybe_build_macos_runtime()
    MACOS_RUNTIME_STAGE.mkdir(parents=True, exist_ok=True)
    copied_any = False
    for name in MACOS_RUNTIME_FILES:
        source_candidates = []
        if name == "VirtualCamera.pkg":
            source_candidates.append(MACOS_PKG)
        else:
            source_candidates.append(MACOS_BUILD_DIR / name)
        source_candidates.append(MACOS_RUNTIME_SOURCE_DIR / name)

        source = next((candidate for candidate in source_candidates if candidate.is_file()), None)
        if source is None:
            continue
        shutil.copy2(source, MACOS_RUNTIME_STAGE / name)
        copied_any = True

    extension_source_candidates = [
        MACOS_EXTENSION_BUNDLE,
        MACOS_RUNTIME_SOURCE_DIR / MACOS_EXTENSION_BUNDLE.name,
    ]
    extension_source = next(
        (candidate for candidate in extension_source_candidates if candidate.is_dir()),
        None,
    )
    if extension_source is not None:
        shutil.copytree(
            extension_source,
            MACOS_RUNTIME_STAGE / extension_source.name,
            dirs_exist_ok=True,
        )
        copied_any = True

    if not copied_any:
        return None
    return MACOS_RUNTIME_STAGE


def _copy_runtime_tree(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.iterdir():
        if source.is_dir():
            shutil.copytree(source, target_dir / source.name, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, target_dir / source.name)


class build_py(_build_py):
    def run(self) -> None:
        super().run()

        runtime_bin = _stage_windows_runtime()
        if runtime_bin is not None:
            target_dir = Path(self.build_lib) / "akvc" / "_runtime" / "windows"
            _copy_runtime_tree(runtime_bin, target_dir)

        macos_runtime = _stage_macos_runtime()
        if macos_runtime is not None:
            target_dir = Path(self.build_lib) / "akvc" / "_runtime" / "macos"
            _copy_runtime_tree(macos_runtime, target_dir)


if _editable_wheel is not None:

    class editable_wheel(_editable_wheel):
        def run(self) -> None:
            _stage_windows_runtime()
            _stage_macos_runtime()
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
