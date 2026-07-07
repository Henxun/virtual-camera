# SPDX-License-Identifier: Apache-2.0
"""Windows runtime asset discovery for packaged installs and dev builds."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Optional

_RUNTIME_PACKAGE = "akvc._runtime.windows"
_PACKAGE_RUNTIME_DIR = Path(__file__).resolve().parent / "_runtime" / "windows"
_STAGED_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "build" / "package-runtime" / "bin"


def _resource_path(name: str) -> Optional[Path]:
    path = _PACKAGE_RUNTIME_DIR / name
    if path.is_file():
        return path

    try:
        ref = resources.files(_RUNTIME_PACKAGE).joinpath(name)
    except ModuleNotFoundError:
        return None
    path = Path(str(ref))
    if path.is_file():
        return path
    return None


def find_helper_exe(explicit: str | Path | None = None) -> Optional[Path]:
    return _find_asset(
        explicit=explicit,
        env_var="AKVC_HELPER_EXE",
        resource_name="akvc_helper.exe",
        build_relpaths=["build/bin/Release/akvc_helper.exe", "build/bin/akvc_helper.exe"],
    )


def find_dshow_dll(explicit: str | Path | None = None) -> Optional[Path]:
    return _find_asset(
        explicit=explicit,
        env_var="AKVC_DSHOW_DLL",
        resource_name="akvc-dshow.dll",
        build_relpaths=["build/bin/Release/akvc-dshow.dll", "build/bin/akvc-dshow.dll"],
    )


def find_mf_dll(explicit: str | Path | None = None) -> Optional[Path]:
    return _find_asset(
        explicit=explicit,
        env_var="AKVC_MF_DLL",
        resource_name="akvc-mf.dll",
        build_relpaths=["build/bin/Release/akvc-mf.dll", "build/bin/akvc-mf.dll"],
    )


def _build_search_roots() -> list[Path]:
    return [Path.cwd(), Path(__file__).resolve().parents[1]]


def _find_asset(
    *,
    explicit: str | Path | None,
    env_var: str,
    resource_name: str,
    build_relpaths: list[str],
) -> Optional[Path]:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path

    env = os.environ.get(env_var)
    if env:
        path = Path(env)
        if path.is_file():
            return path

    for base in _build_search_roots():
        for rel in build_relpaths:
            path = base / rel
            if path.is_file():
                return path

    staged = _STAGED_RUNTIME_DIR / resource_name
    if staged.is_file():
        return staged

    packaged = _resource_path(resource_name)
    if packaged is not None:
        return packaged

    return None
