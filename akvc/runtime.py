# SPDX-License-Identifier: Apache-2.0
"""Runtime asset discovery for packaged installs and dev builds."""

from __future__ import annotations

import os
import plistlib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
_PACKAGE_WINDOWS_RUNTIME_DIR = _PACKAGE_ROOT / "_runtime" / "windows"
_PACKAGE_MACOS_RUNTIME_DIR = _PACKAGE_ROOT / "_runtime" / "macos"
_DEFAULT_PACKAGE_WINDOWS_RUNTIME_DIR = _PACKAGE_WINDOWS_RUNTIME_DIR
_DEFAULT_PACKAGE_MACOS_RUNTIME_DIR = _PACKAGE_MACOS_RUNTIME_DIR
_STAGED_WINDOWS_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "build" / "package-runtime" / "bin"
_STAGED_MACOS_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "build" / "package-runtime" / "macos"
_STAGED_RUNTIME_DIR = _STAGED_WINDOWS_RUNTIME_DIR
_APPLICATIONS_DIR = Path("/Applications")
_MACOS_EXTENSION_BUNDLE_NAME = "com.sidus.amaran-desktop.cameraextension.systemextension"


def _package_windows_runtime_dir() -> Path:
    if _PACKAGE_WINDOWS_RUNTIME_DIR != _DEFAULT_PACKAGE_WINDOWS_RUNTIME_DIR:
        return _PACKAGE_WINDOWS_RUNTIME_DIR
    return _PACKAGE_ROOT / "_runtime" / "windows"


def _package_macos_runtime_dir() -> Path:
    if _PACKAGE_MACOS_RUNTIME_DIR != _DEFAULT_PACKAGE_MACOS_RUNTIME_DIR:
        return _PACKAGE_MACOS_RUNTIME_DIR
    return _PACKAGE_ROOT / "_runtime" / "macos"


_PACKAGE_RUNTIME_DIR = _PACKAGE_WINDOWS_RUNTIME_DIR


def _resource_path(relative_path: str) -> Path | None:
    path = _PACKAGE_ROOT / relative_path
    if path.is_file():
        return path

    try:
        ref = resources.files("akvc").joinpath(*Path(relative_path).parts)
    except ModuleNotFoundError:
        return None
    path = Path(str(ref))
    if path.is_file():
        return path
    return None


def _build_search_roots() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[1]
    return [
        Path.cwd(),
        repo_root,
        repo_root / "camera-core" / "src",
    ]


def _existing_path_from_explicit(explicit: str | Path | None) -> Path | None:
    if not explicit:
        return None
    path = Path(explicit)
    if path.exists():
        return path
    return None


def _existing_file_from_explicit(explicit: str | Path | None) -> Path | None:
    if not explicit:
        return None
    path = Path(explicit)
    if path.is_file():
        return path
    return None


def _existing_path_from_env(env_var: str) -> Path | None:
    env = os.environ.get(env_var)
    if not env:
        return None
    path = Path(env)
    if path.exists():
        return path
    return None


def _existing_file_from_env(env_var: str) -> Path | None:
    env = os.environ.get(env_var)
    if not env:
        return None
    path = Path(env)
    if path.is_file():
        return path
    return None


def _find_existing_path(
    *,
    explicit: str | Path | None,
    env_var: str,
    build_relpaths: list[str],
    absolute_candidates: list[str] | None = None,
) -> Path | None:
    resolved = _existing_path_from_explicit(explicit)
    if resolved is not None:
        return resolved

    resolved = _existing_path_from_env(env_var)
    if resolved is not None:
        return resolved

    for candidate in absolute_candidates or []:
        path = Path(candidate)
        if path.exists():
            return path

    for base in _build_search_roots():
        for rel in build_relpaths:
            path = base / rel
            if path.exists():
                return path

    return None


def _find_directory_asset(
    *,
    explicit: str | Path | None,
    env_var: str,
    packaged_dir: Path | None = None,
    build_relpaths: list[str] | None = None,
    absolute_candidates: list[str] | None = None,
) -> Path | None:
    resolved = _existing_path_from_explicit(explicit)
    if resolved is not None and resolved.is_dir():
        return resolved

    resolved = _existing_path_from_env(env_var)
    if resolved is not None and resolved.is_dir():
        return resolved

    for candidate in absolute_candidates or []:
        path = Path(candidate)
        if path.is_dir():
            return path

    for base in _build_search_roots():
        for rel in build_relpaths or []:
            path = base / rel
            if path.is_dir():
                return path

    if packaged_dir is not None:
        staged = packaged_dir / _MACOS_EXTENSION_BUNDLE_NAME
        if staged.is_dir():
            return staged

    return None


def _find_file_asset(
    *,
    explicit: str | Path | None,
    env_var: str,
    resource_path: str | None,
    packaged_dir: Path | None = None,
    build_relpaths: list[str] | None = None,
    absolute_candidates: list[str] | None = None,
) -> Path | None:
    resolved = _existing_file_from_explicit(explicit)
    if resolved is not None:
        return resolved

    resolved = _existing_file_from_env(env_var)
    if resolved is not None:
        return resolved

    for candidate in absolute_candidates or []:
        path = Path(candidate)
        if path.is_file():
            return path

    for base in _build_search_roots():
        for rel in build_relpaths or []:
            path = base / rel
            if path.is_file():
                return path

    package_windows_runtime_dir = _package_windows_runtime_dir()
    package_macos_runtime_dir = _package_macos_runtime_dir()

    if packaged_dir in {package_windows_runtime_dir, _PACKAGE_RUNTIME_DIR} and resource_path is not None:
        staged = _STAGED_RUNTIME_DIR / Path(resource_path).name
        if staged.is_file():
            return staged

    if packaged_dir == package_macos_runtime_dir and resource_path is not None:
        staged = _STAGED_MACOS_RUNTIME_DIR / Path(resource_path).name
        if staged.is_file():
            return staged

    if packaged_dir is not None and resource_path is not None:
        staged = packaged_dir / Path(resource_path).name
        if staged.is_file():
            return staged

    if resource_path is not None:
        package_candidate = _PACKAGE_ROOT / resource_path
        if packaged_dir is None or package_candidate == packaged_dir / Path(resource_path).name:
            packaged = _resource_path(resource_path)
            if packaged is not None:
                return packaged

    return None


def find_helper_exe(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_HELPER_EXE",
        resource_path="_runtime/windows/akvc_helper.exe",
        packaged_dir=_PACKAGE_RUNTIME_DIR,
        build_relpaths=[
            "build/bin/Release/akvc_helper.exe",
            "build/bin/akvc_helper.exe",
        ],
    )


def find_dshow_dll(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_DSHOW_DLL",
        resource_path="_runtime/windows/akvc-dshow.dll",
        packaged_dir=_PACKAGE_RUNTIME_DIR,
        build_relpaths=[
            "build/bin/Release/akvc-dshow.dll",
            "build/bin/akvc-dshow.dll",
        ],
    )


def find_mf_dll(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MF_DLL",
        resource_path="_runtime/windows/akvc-mf.dll",
        packaged_dir=_PACKAGE_RUNTIME_DIR,
        build_relpaths=[
            "build/bin/Release/akvc-mf.dll",
            "build/bin/akvc-mf.dll",
        ],
    )


def _macos_runtime_relpath(name: str) -> str:
    return f"_runtime/macos/{name}"


def find_macos_status_tool(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_STATUS_TOOL",
        resource_path=_macos_runtime_relpath("akvc-macos-status"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/akvc-macos-status",
            "camera-core/src/akvc/_runtime/macos/akvc-macos-status",
        ],
    )


def find_macos_install_tool(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_INSTALL_TOOL",
        resource_path=_macos_runtime_relpath("akvc-macos-install"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/akvc-macos-install",
            "camera-core/src/akvc/_runtime/macos/akvc-macos-install",
        ],
    )


def find_macos_list_devices_tool(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_LIST_DEVICES_TOOL",
        resource_path=_macos_runtime_relpath("akvc-macos-list-devices"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/akvc-macos-list-devices",
            "camera-core/src/akvc/_runtime/macos/akvc-macos-list-devices",
        ],
    )


def find_macos_sync_ipc_tool(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_SYNC_IPC_TOOL",
        resource_path=_macos_runtime_relpath("akvc-macos-sync-ipc"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/akvc-macos-sync-ipc",
            "camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc",
        ],
    )


def find_macos_direct_sender_library(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_DIRECT_SENDER_LIB",
        resource_path=_macos_runtime_relpath("libakvc-macos-direct-sender.dylib"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/libakvc-macos-direct-sender.dylib",
            "camera-core/src/akvc/_runtime/macos/libakvc-macos-direct-sender.dylib",
        ],
    )


def find_macos_uninstall_tool(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_UNINSTALL_TOOL",
        resource_path=_macos_runtime_relpath("akvc-macos-uninstall"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/akvc-macos-uninstall",
            "camera-core/src/akvc/_runtime/macos/akvc-macos-uninstall",
        ],
    )


def find_macos_pkg(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_PKG",
        resource_path=_macos_runtime_relpath("VirtualCamera.pkg"),
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            "akvc/_runtime/macos/VirtualCamera.pkg",
            "camera-core/src/akvc/_runtime/macos/VirtualCamera.pkg",
        ],
    )


def find_macos_extension_bundle(explicit: str | Path | None = None) -> Path | None:
    return _find_directory_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_EXTENSION_BUNDLE",
        packaged_dir=_package_macos_runtime_dir(),
        build_relpaths=[
            f"akvc/_runtime/macos/{_MACOS_EXTENSION_BUNDLE_NAME}",
            f"camera-core/src/akvc/_runtime/macos/{_MACOS_EXTENSION_BUNDLE_NAME}",
            f"build/macos/Build/Products/Release/{_MACOS_EXTENSION_BUNDLE_NAME}",
        ],
    )


def find_macos_framebus_roundtrip_report(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON",
        resource_path=None,
        build_relpaths=["build/macos/session/framebus-roundtrip.json"],
    )


def find_macos_session_manifest(explicit: str | Path | None = None) -> Path | None:
    return _find_file_asset(
        explicit=explicit,
        env_var="AKVC_MACOS_SESSION_MANIFEST_JSON",
        resource_path=None,
        build_relpaths=["build/macos/session/session-manifest.json"],
    )


def _bundle_path_from_executable(path_like: str | Path | None) -> Path | None:
    if path_like is None:
        return None
    path = Path(path_like)
    parts = path.parts
    for index, part in enumerate(parts):
        if part.endswith(".app"):
            return Path(*parts[: index + 1])
    return None


def _bundle_executable(bundle_path: Path) -> Path | None:
    plist_path = bundle_path / "Contents" / "Info.plist"
    if plist_path.is_file():
        try:
            with plist_path.open("rb") as fh:
                payload = plistlib.load(fh)
        except Exception:
            payload = {}
        executable_name = payload.get("CFBundleExecutable") if isinstance(payload, dict) else None
        if isinstance(executable_name, str) and executable_name:
            executable = bundle_path / "Contents" / "MacOS" / executable_name
            if executable.is_file():
                return executable

    executable = bundle_path / "Contents" / "MacOS" / bundle_path.stem
    if executable.is_file():
        return executable
    children = list((bundle_path / "Contents" / "MacOS").glob("*"))
    for child in children:
        if child.is_file():
            return child
    return None


def _macos_app_embeds_extension(bundle_path: Path) -> bool:
    return (
        bundle_path
        / "Contents"
        / "Library"
        / "SystemExtensions"
        / _MACOS_EXTENSION_BUNDLE_NAME
    ).is_dir()


def _is_preferred_macos_container_app(bundle_path: Path) -> bool:
    return bundle_path.name != "akvc-host.app"


def _macos_app_search_dirs() -> list[Path]:
    search_dirs: list[Path] = [_APPLICATIONS_DIR]
    for base in _build_search_roots():
        for candidate in (
            base / "build" / "macos" / "Build" / "Products" / "Release",
            base / "build" / "macos",
        ):
            if candidate not in search_dirs:
                search_dirs.append(candidate)
    return search_dirs


def _find_macos_embedded_container_bundle() -> Path | None:
    for search_dir in _macos_app_search_dirs():
        if not search_dir.is_dir():
            continue
        candidates = sorted(path for path in search_dir.glob("*.app") if path.is_dir())
        for candidate in candidates:
            if _is_preferred_macos_container_app(candidate) and _macos_app_embeds_extension(candidate):
                return candidate
        for candidate in candidates:
            if _macos_app_embeds_extension(candidate):
                return candidate
    return None


def find_macos_host_app_bundle(explicit: str | Path | None = None) -> Path | None:
    resolved = _existing_path_from_explicit(explicit)
    if resolved is not None:
        return resolved if resolved.name.endswith(".app") else _bundle_path_from_executable(resolved)

    resolved = _existing_path_from_env("AKVC_HOST_APP_BUNDLE")
    if resolved is not None:
        return resolved

    resolved = _existing_path_from_env("AKVC_CONTAINER_APP_BUNDLE")
    if resolved is not None:
        return resolved

    executable = _existing_file_from_env("AKVC_CONTAINER_APP_EXECUTABLE")
    if executable is not None:
        return _bundle_path_from_executable(executable)

    executable = find_macos_host_executable()
    if executable is not None:
        return _bundle_path_from_executable(executable)

    embedded_bundle = _find_macos_embedded_container_bundle()
    if embedded_bundle is not None:
        return embedded_bundle

    return _find_existing_path(
        explicit=None,
        env_var="__AKVC_UNUSED__",
        build_relpaths=[
            "build/macos/Build/Products/Release/akvc-host.app",
            "build/macos/akvc-host.app",
        ],
        absolute_candidates=[str(_APPLICATIONS_DIR / "akvc-host.app")],
    )


def find_macos_host_executable(explicit: str | Path | None = None) -> Path | None:
    resolved = _existing_file_from_explicit(explicit)
    if resolved is not None:
        return resolved

    bundle = _existing_path_from_explicit(explicit)
    if bundle is not None and bundle.name.endswith(".app"):
        return _bundle_executable(bundle)

    resolved = _existing_file_from_env("AKVC_HOST_EXECUTABLE")
    if resolved is not None:
        return resolved

    bundle = _existing_path_from_env("AKVC_HOST_APP_BUNDLE")
    if bundle is not None:
        executable = _bundle_executable(bundle)
        if executable is not None:
            return executable

    resolved = _existing_file_from_env("AKVC_CONTAINER_APP_EXECUTABLE")
    if resolved is not None:
        return resolved

    bundle = _existing_path_from_env("AKVC_CONTAINER_APP_BUNDLE")
    if bundle is not None:
        executable = _bundle_executable(bundle)
        if executable is not None:
            return executable

    embedded_bundle = _find_macos_embedded_container_bundle()
    if embedded_bundle is not None:
        executable = _bundle_executable(embedded_bundle)
        if executable is not None:
            return executable

    bundle = _find_existing_path(
        explicit=None,
        env_var="__AKVC_UNUSED__",
        build_relpaths=[
            "build/macos/Build/Products/Release/akvc-host.app",
            "build/macos/akvc-host.app",
        ],
        absolute_candidates=[str(_APPLICATIONS_DIR / "akvc-host.app")],
    )
    if bundle is not None and bundle.name.endswith(".app"):
        return _bundle_executable(bundle)
    return None


def find_macos_container_app_bundle(explicit: str | Path | None = None) -> Path | None:
    resolved = _existing_path_from_explicit(explicit)
    if resolved is not None:
        return resolved if resolved.name.endswith(".app") else _bundle_path_from_executable(resolved)

    resolved = _existing_path_from_env("AKVC_CONTAINER_APP_BUNDLE")
    if resolved is not None:
        return resolved

    executable = _existing_file_from_env("AKVC_CONTAINER_APP_EXECUTABLE")
    if executable is not None:
        return _bundle_path_from_executable(executable)

    return find_macos_host_app_bundle()


def find_macos_container_app_executable(explicit: str | Path | None = None) -> Path | None:
    resolved = _existing_file_from_explicit(explicit)
    if resolved is not None:
        return resolved

    bundle = _existing_path_from_explicit(explicit)
    if bundle is not None and bundle.name.endswith(".app"):
        return _bundle_executable(bundle)

    resolved = _existing_file_from_env("AKVC_CONTAINER_APP_EXECUTABLE")
    if resolved is not None:
        return resolved

    bundle = _existing_path_from_env("AKVC_CONTAINER_APP_BUNDLE")
    if bundle is not None:
        executable = _bundle_executable(bundle)
        if executable is not None:
            return executable

    return find_macos_host_executable()


@dataclass(frozen=True)
class MacContainerAppDescriptor:
    app_bundle_path: Path | None
    app_executable_path: Path | None
    extension_bundle_path: Path | None
    installed_in_applications: bool
    source: str


def _find_system_extension_bundle(app_bundle: Path | None) -> Path | None:
    if app_bundle is None:
        return None
    extensions_dir = app_bundle / "Contents" / "Library" / "SystemExtensions"
    if not extensions_dir.is_dir():
        return None
    for candidate in sorted(extensions_dir.glob("*.systemextension")):
        return candidate
    return None


def resolve_macos_container_app(
    *,
    app_bundle: str | Path | None = None,
    app_executable: str | Path | None = None,
) -> MacContainerAppDescriptor:
    source = "auto"
    bundle = find_macos_container_app_bundle(app_bundle)
    executable = find_macos_container_app_executable(app_executable)
    if app_bundle is not None or app_executable is not None:
        source = "explicit"
    elif os.environ.get("AKVC_CONTAINER_APP_BUNDLE") or os.environ.get("AKVC_CONTAINER_APP_EXECUTABLE"):
        source = "env"
    elif os.environ.get("AKVC_HOST_APP_BUNDLE") or os.environ.get("AKVC_HOST_EXECUTABLE"):
        source = "host_env"

    if bundle is None and executable is not None:
        bundle = _bundle_path_from_executable(executable)
    if executable is None and bundle is not None:
        executable = _bundle_executable(bundle)

    extension_bundle = _find_system_extension_bundle(bundle)
    installed_in_applications = bool(bundle is not None and bundle.parent == _APPLICATIONS_DIR)
    return MacContainerAppDescriptor(
        app_bundle_path=bundle,
        app_executable_path=executable,
        extension_bundle_path=extension_bundle,
        installed_in_applications=installed_in_applications,
        source=source,
    )


__all__ = [
    "MacContainerAppDescriptor",
    "find_dshow_dll",
    "find_helper_exe",
    "find_macos_container_app_bundle",
    "find_macos_container_app_executable",
    "find_macos_direct_sender_library",
    "find_macos_extension_bundle",
    "find_macos_framebus_roundtrip_report",
    "find_macos_host_app_bundle",
    "find_macos_host_executable",
    "find_macos_install_tool",
    "find_macos_list_devices_tool",
    "find_macos_pkg",
    "find_macos_session_manifest",
    "find_macos_status_tool",
    "find_macos_sync_ipc_tool",
    "find_macos_uninstall_tool",
    "find_mf_dll",
    "resolve_macos_container_app",
]
