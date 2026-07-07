# SPDX-License-Identifier: Apache-2.0
"""AK Virtual Camera SDK package."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

_DLL_DIRECTORY_HANDLE = None

if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    runtime_dir = Path(__file__).resolve().parent / "_runtime" / "windows"
    if runtime_dir.is_dir():
        _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(runtime_dir))

__version__ = "0.2.0"

_CAMERA_CORE_PACKAGE = Path(__file__).resolve().parents[1] / "camera-core" / "src" / "akvc"
if _CAMERA_CORE_PACKAGE.is_dir():
    _package_path = str(_CAMERA_CORE_PACKAGE)
    if _package_path not in __path__:
        __path__.append(_package_path)

__all__ = [
    "VirtualCamera",
    "MacDirectCameraSender",
    "DirectSenderError",
    "EmbeddedRuntimeConfig",
    "RuntimeAssetLayout",
    "build_runtime_env",
    "collect_runtime_layout",
    "copy_runtime_assets",
    "embed_macos_extension_in_app_bundle",
    "embed_macos_runtime_in_app_bundle",
    "prepare_macos_host_runtime",
    "create_direct_sender",
    "__version__",
]

if TYPE_CHECKING:
    from .distribution import (
        EmbeddedRuntimeConfig,
        RuntimeAssetLayout,
        build_runtime_env,
        collect_runtime_layout,
        copy_runtime_assets,
        embed_macos_extension_in_app_bundle,
        embed_macos_runtime_in_app_bundle,
        prepare_macos_host_runtime,
    )
    from .sdk import (
        DirectSenderError,
        MacDirectCameraSender,
        VirtualCamera,
        create_direct_sender,
    )


def __getattr__(name: str):
    if name == "VirtualCamera":
        from .sdk import VirtualCamera

        return VirtualCamera
    if name in {
        "EmbeddedRuntimeConfig",
        "RuntimeAssetLayout",
        "build_runtime_env",
        "collect_runtime_layout",
        "copy_runtime_assets",
        "embed_macos_extension_in_app_bundle",
        "embed_macos_runtime_in_app_bundle",
        "prepare_macos_host_runtime",
    }:
        from .distribution import (
            EmbeddedRuntimeConfig,
            RuntimeAssetLayout,
            build_runtime_env,
            collect_runtime_layout,
            copy_runtime_assets,
            embed_macos_extension_in_app_bundle,
            embed_macos_runtime_in_app_bundle,
            prepare_macos_host_runtime,
        )

        exports = {
            "EmbeddedRuntimeConfig": EmbeddedRuntimeConfig,
            "RuntimeAssetLayout": RuntimeAssetLayout,
            "build_runtime_env": build_runtime_env,
            "collect_runtime_layout": collect_runtime_layout,
            "copy_runtime_assets": copy_runtime_assets,
            "embed_macos_extension_in_app_bundle": embed_macos_extension_in_app_bundle,
            "embed_macos_runtime_in_app_bundle": embed_macos_runtime_in_app_bundle,
            "prepare_macos_host_runtime": prepare_macos_host_runtime,
        }
        return exports[name]
    if name in {"MacDirectCameraSender", "DirectSenderError", "create_direct_sender"}:
        from .sdk import (
            DirectSenderError,
            MacDirectCameraSender,
            create_direct_sender,
        )

        exports = {
            "MacDirectCameraSender": MacDirectCameraSender,
            "DirectSenderError": DirectSenderError,
            "create_direct_sender": create_direct_sender,
        }
        return exports[name]
    raise AttributeError(name)
