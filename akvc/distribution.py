# SPDX-License-Identifier: Apache-2.0
"""Helpers for embedding packaged AKVC runtime assets into host applications."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import sys

from .runtime import (
    find_dshow_dll,
    find_helper_exe,
    find_macos_direct_sender_library,
    find_macos_extension_bundle,
    find_macos_install_tool,
    find_macos_list_devices_tool,
    find_macos_pkg,
    find_macos_status_tool,
    find_macos_sync_ipc_tool,
    find_macos_uninstall_tool,
    find_mf_dll,
)


WINDOWS_RUNTIME_ENV_MAP: tuple[tuple[str, str], ...] = (
    ("AKVC_HELPER_EXE", "akvc_helper.exe"),
    ("AKVC_DSHOW_DLL", "akvc-dshow.dll"),
    ("AKVC_MF_DLL", "akvc-mf.dll"),
)

MACOS_RUNTIME_ENV_MAP: tuple[tuple[str, str], ...] = (
    ("AKVC_MACOS_STATUS_TOOL", "akvc-macos-status"),
    ("AKVC_MACOS_INSTALL_TOOL", "akvc-macos-install"),
    ("AKVC_MACOS_UNINSTALL_TOOL", "akvc-macos-uninstall"),
    ("AKVC_MACOS_LIST_DEVICES_TOOL", "akvc-macos-list-devices"),
    ("AKVC_MACOS_SYNC_IPC_TOOL", "akvc-macos-sync-ipc"),
    ("AKVC_MACOS_DIRECT_SENDER_LIB", "libakvc-macos-direct-sender.dylib"),
    ("AKVC_MACOS_PKG", "VirtualCamera.pkg"),
)

_WINDOWS_LOCATOR_NAMES = {
    "akvc_helper.exe": "find_helper_exe",
    "akvc-dshow.dll": "find_dshow_dll",
    "akvc-mf.dll": "find_mf_dll",
}

_MACOS_LOCATOR_NAMES = {
    "akvc-macos-status": "find_macos_status_tool",
    "akvc-macos-install": "find_macos_install_tool",
    "akvc-macos-uninstall": "find_macos_uninstall_tool",
    "akvc-macos-list-devices": "find_macos_list_devices_tool",
    "akvc-macos-sync-ipc": "find_macos_sync_ipc_tool",
    "libakvc-macos-direct-sender.dylib": "find_macos_direct_sender_library",
    "VirtualCamera.pkg": "find_macos_pkg",
}


def _normalize_platform_name(platform_name: str | None = None) -> str:
    value = sys.platform if platform_name is None else str(platform_name).strip().lower()
    if value in {"darwin", "macos", "mac", "osx"}:
        return "darwin"
    if value in {"win32", "windows", "win"}:
        return "win32"
    return value


@dataclass(frozen=True)
class RuntimeAssetLayout:
    platform: str
    root: Path | None
    assets: tuple[tuple[str, Path], ...]
    missing: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing

    def as_dict(self) -> dict[str, Path]:
        return dict(self.assets)


@dataclass(frozen=True)
class EmbeddedRuntimeConfig:
    layout: RuntimeAssetLayout
    env: dict[str, str]
    extension_bundle_path: Path | None = None


def _locator_table(platform: str) -> dict[str, object]:
    if platform == "win32":
        return {
            filename: globals()[locator_name]
            for filename, locator_name in _WINDOWS_LOCATOR_NAMES.items()
        }
    if platform == "darwin":
        return {
            filename: globals()[locator_name]
            for filename, locator_name in _MACOS_LOCATOR_NAMES.items()
        }
    return {}


def collect_runtime_layout(platform_name: str | None = None) -> RuntimeAssetLayout:
    platform = _normalize_platform_name(platform_name)
    locators = _locator_table(platform)
    assets: list[tuple[str, Path]] = []
    missing: list[str] = []

    for filename, locator in locators.items():
        path = locator()
        if path is None:
            missing.append(filename)
            continue
        assets.append((filename, Path(path)))

    roots = {path.parent for _, path in assets}
    root = next(iter(roots)) if len(roots) == 1 else None
    return RuntimeAssetLayout(
        platform=platform,
        root=root,
        assets=tuple(sorted(assets, key=lambda item: item[0])),
        missing=tuple(missing),
    )


def copy_runtime_assets(
    target_dir: str | Path,
    *,
    platform_name: str | None = None,
    overwrite: bool = True,
    require_complete: bool = True,
) -> RuntimeAssetLayout:
    layout = collect_runtime_layout(platform_name)
    if require_complete and layout.missing:
        missing_text = ", ".join(layout.missing)
        raise FileNotFoundError(
            f"missing packaged runtime assets for {layout.platform}: {missing_text}"
        )

    target_root = Path(target_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    copied_assets: list[tuple[str, Path]] = []
    for filename, source in layout.assets:
        destination = target_root / filename
        if destination.exists() and not overwrite:
            copied_assets.append((filename, destination))
            continue
        shutil.copy2(source, destination)
        copied_assets.append((filename, destination))

    return RuntimeAssetLayout(
        platform=layout.platform,
        root=target_root,
        assets=tuple(sorted(copied_assets, key=lambda item: item[0])),
        missing=layout.missing,
    )


def build_runtime_env(
    *,
    platform_name: str | None = None,
    runtime_dir: str | Path | None = None,
    app_bundle: str | Path | None = None,
    app_executable: str | Path | None = None,
) -> dict[str, str]:
    platform = _normalize_platform_name(platform_name)
    env_map = WINDOWS_RUNTIME_ENV_MAP if platform == "win32" else MACOS_RUNTIME_ENV_MAP if platform == "darwin" else ()

    if runtime_dir is None:
        layout = collect_runtime_layout(platform)
        assets = layout.as_dict()
    else:
        runtime_root = Path(runtime_dir)
        assets = {filename: runtime_root / filename for _, filename in env_map}

    env = {
        env_name: str(assets[filename])
        for env_name, filename in env_map
        if filename in assets and assets[filename].exists()
    }
    if platform == "darwin":
        if app_bundle is not None:
            env["AKVC_CONTAINER_APP_BUNDLE"] = str(Path(app_bundle))
        if app_executable is not None:
            env["AKVC_CONTAINER_APP_EXECUTABLE"] = str(Path(app_executable))
    return env


def embed_macos_runtime_in_app_bundle(
    app_bundle: str | Path,
    *,
    relative_dir: str | Path = "Contents/Resources/virtual_camera/macos",
    overwrite: bool = True,
    require_complete: bool = True,
) -> RuntimeAssetLayout:
    bundle_path = Path(app_bundle)
    target_dir = bundle_path / Path(relative_dir)
    return copy_runtime_assets(
        target_dir,
        platform_name="darwin",
        overwrite=overwrite,
        require_complete=require_complete,
    )


def embed_macos_extension_in_app_bundle(
    app_bundle: str | Path,
    *,
    extension_bundle: str | Path | None = None,
    overwrite: bool = True,
) -> Path:
    source = find_macos_extension_bundle(extension_bundle)
    if source is None:
        raise FileNotFoundError("missing packaged macOS camera extension bundle")

    bundle_path = Path(app_bundle)
    target_dir = bundle_path / "Contents" / "Library" / "SystemExtensions" / source.name
    if target_dir.exists() and not overwrite:
        return target_dir
    shutil.copytree(source, target_dir, dirs_exist_ok=overwrite)
    return target_dir


def prepare_macos_host_runtime(
    app_bundle: str | Path,
    *,
    app_executable: str | Path | None = None,
    relative_dir: str | Path = "Contents/Resources/virtual_camera/macos",
    embed_extension: bool = False,
    overwrite: bool = True,
    require_complete: bool = True,
) -> EmbeddedRuntimeConfig:
    bundle_path = Path(app_bundle)
    executable_path = (
        Path(app_executable)
        if app_executable is not None
        else bundle_path / "Contents" / "MacOS" / bundle_path.stem
    )
    layout = embed_macos_runtime_in_app_bundle(
        bundle_path,
        relative_dir=relative_dir,
        overwrite=overwrite,
        require_complete=require_complete,
    )
    env = build_runtime_env(
        platform_name="darwin",
        runtime_dir=layout.root,
        app_bundle=bundle_path,
        app_executable=executable_path,
    )
    extension_bundle_path = None
    if embed_extension:
        extension_bundle_path = embed_macos_extension_in_app_bundle(
            bundle_path,
            overwrite=overwrite,
        )
        env["AKVC_MACOS_EXTENSION_BUNDLE"] = str(extension_bundle_path)
    return EmbeddedRuntimeConfig(
        layout=layout,
        env=env,
        extension_bundle_path=extension_bundle_path,
    )


__all__ = [
    "EmbeddedRuntimeConfig",
    "MACOS_RUNTIME_ENV_MAP",
    "WINDOWS_RUNTIME_ENV_MAP",
    "RuntimeAssetLayout",
    "build_runtime_env",
    "collect_runtime_layout",
    "copy_runtime_assets",
    "embed_macos_extension_in_app_bundle",
    "embed_macos_runtime_in_app_bundle",
    "prepare_macos_host_runtime",
]
