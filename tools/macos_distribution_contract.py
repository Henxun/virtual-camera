# SPDX-License-Identifier: Apache-2.0
"""Consistency checks for the macOS distribution/runtime asset contract.

This tool keeps the packaging-side runtime sync rules, packaged runtime asset
discovery, validation-report runtime snapshot, and release-diagnostics sync-ipc
surface aligned so macOS distribution assets do not silently drift apart.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAKE_TOOL = ROOT / "tools" / "make.py"
RUNTIME_LOCATOR_MODULE = ROOT / "akvc" / "runtime.py"
RUNTIME_SHIM_MODULE = ROOT / "camera-core" / "src" / "akvc" / "runtime.py"
VALIDATION_REPORT_TOOL = ROOT / "tools" / "macos_validation_report.py"
RELEASE_DIAGNOSTICS_TOOL = ROOT / "tools" / "macos_release_diagnostics.py"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_make_runtime_surface(text: str) -> dict[str, bool]:
    return {
        "defines_sync_runtime_function": "def _sync_macos_runtime_assets(" in text,
        "syncs_status_tool": '"akvc-macos-status"' in text,
        "syncs_install_tool": '"akvc-macos-install"' in text,
        "syncs_uninstall_tool": '"akvc-macos-uninstall"' in text,
        "syncs_list_devices_tool": '"akvc-macos-list-devices"' in text,
        "syncs_sync_ipc_tool": '"akvc-macos-sync-ipc"' in text,
        "syncs_direct_sender_library": '"libakvc-macos-direct-sender.dylib"' in text,
        "syncs_pkg_when_required": '"VirtualCamera.pkg"' in text and "if require_pkg:" in text,
        "skips_chmod_for_pkg": 'dst.name != "VirtualCamera.pkg"' in text,
    }


def parse_runtime_locator_surface(locator_text: str, shim_text: str) -> dict[str, bool]:
    return {
        "defines_find_macos_sync_ipc_tool": "def find_macos_sync_ipc_tool(" in locator_text,
        "defines_find_macos_direct_sender_library": "def find_macos_direct_sender_library(" in locator_text,
        "defines_find_macos_pkg": "def find_macos_pkg(" in locator_text,
        "uses_sync_ipc_env_var": "AKVC_MACOS_SYNC_IPC_TOOL" in locator_text,
        "uses_direct_sender_env_var": "AKVC_MACOS_DIRECT_SENDER_LIB" in locator_text,
        "uses_pkg_env_var": "AKVC_MACOS_PKG" in locator_text,
        "uses_packaged_sync_ipc_resource": "_runtime/macos/akvc-macos-sync-ipc" in locator_text,
        "uses_packaged_direct_sender_resource": "_runtime/macos/libakvc-macos-direct-sender.dylib" in locator_text,
        "uses_packaged_pkg_resource": "_runtime/macos/VirtualCamera.pkg" in locator_text,
        "uses_build_sync_ipc_release_path": "camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc" in locator_text,
        "uses_build_direct_sender_release_path": "camera-core/src/akvc/_runtime/macos/libakvc-macos-direct-sender.dylib" in locator_text,
        "uses_build_pkg_path": "camera-core/src/akvc/_runtime/macos/VirtualCamera.pkg" in locator_text,
        "shim_reexports_root_runtime": "_ROOT_RUNTIME" in shim_text and "__all__ = list(getattr(_MODULE, \"__all__\", ()))" in shim_text,
    }


def parse_validation_report_runtime_surface(text: str) -> dict[str, bool]:
    return {
        "declares_packaged_runtime_dir": "PACKAGED_MACOS_RUNTIME_DIR" in text,
        "declares_packaged_runtime_assets": "PACKAGED_MACOS_RUNTIME_ASSETS" in text,
        "tracks_packaged_sync_ipc_asset": '"akvc-macos-sync-ipc"' in text,
        "tracks_packaged_direct_sender_asset": '"libakvc-macos-direct-sender.dylib"' in text,
        "tracks_packaged_pkg_asset": '"VirtualCamera.pkg"' in text,
        "resolves_sync_ipc_tool": "find_macos_sync_ipc_tool()" in text,
        "resolves_direct_sender_library": "find_macos_direct_sender_library()" in text,
        "resolves_pkg": "find_macos_pkg()" in text,
        "exports_runtime_sync_ipc_tool_resolved": '"runtime_sync_ipc_tool_resolved"' in text,
        "exports_packaged_tools_present": '"packaged_tools_present"' in text,
        "exports_packaged_pkg_present": '"packaged_pkg_present"' in text,
        "exports_sync_ipc_tool_resolved": '"sync_ipc_tool_resolved"' in text,
        "exports_direct_sender_library_resolved": '"direct_sender_library_resolved"' in text,
    }


def parse_release_diagnostics_surface(text: str) -> dict[str, bool]:
    return {
        "declares_default_sync_ipc_tool": "DEFAULT_SYNC_IPC_TOOL" in text,
        "accepts_sync_ipc_cli_option": "--sync-ipc-tool" in text,
        "generate_release_diagnostics_accepts_sync_ipc_tool": "sync_ipc_tool: Path" in text,
        "loads_sync_ipc_binary_metadata": "_binary_metadata(sync_ipc_tool)" in text,
        "exports_sync_ipc_exists_summary": '"sync_ipc_tool_exists"' in text,
        "exports_sync_ipc_signed_summary": '"sync_ipc_tool_signed"' in text,
        "exports_sync_ipc_universal2_summary": '"sync_ipc_tool_universal2_ready"' in text,
        "exports_pkg_payload_appledouble_clean_summary": '"pkg_payload_appledouble_clean"' in text,
        "exports_release_artifacts_present": '"release_artifacts_present"' in text,
    }


def evaluate_sync_runtime_case() -> dict[str, Any]:
    module = _load_module(MAKE_TOOL, "macos_distribution_contract_make")
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        runtime_dir = tmpdir / "runtime"
        assets = {
            "MACOS_STATUS_TOOL": tmpdir / "akvc-macos-status",
            "MACOS_INSTALL_TOOL": tmpdir / "akvc-macos-install",
            "MACOS_UNINSTALL_TOOL": tmpdir / "akvc-macos-uninstall",
            "MACOS_LIST_DEVICES_TOOL": tmpdir / "akvc-macos-list-devices",
            "MACOS_SYNC_IPC_TOOL": tmpdir / "akvc-macos-sync-ipc",
            "MACOS_DIRECT_SENDER_LIB": tmpdir / "libakvc-macos-direct-sender.dylib",
            "MACOS_PKG": tmpdir / "VirtualCamera.pkg",
        }
        for path in assets.values():
            path.write_text(path.name, encoding="utf-8")

        originals = {
            key: getattr(module, key)
            for key in (*assets.keys(), "MACOS_RUNTIME_DIR")
        }
        try:
            for key, path in assets.items():
                setattr(module, key, path)
            setattr(module, "MACOS_RUNTIME_DIR", runtime_dir)
            rc = module._sync_macos_runtime_assets(require_pkg=True)
            synced = {
                name: (runtime_dir / path.name).is_file()
                for name, path in assets.items()
            }
            return {
                "returncode": rc,
                "synced": synced,
                "all_synced": rc == 0 and all(synced.values()),
            }
        finally:
            for key, value in originals.items():
                setattr(module, key, value)


def evaluate_runtime_discovery_case() -> dict[str, Any]:
    runtime_module = _load_module(
        RUNTIME_LOCATOR_MODULE,
        "macos_distribution_contract_runtime",
    )
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        runtime_root = tmpdir / "_runtime" / "macos"
        runtime_root.mkdir(parents=True)
        sync_ipc_tool = runtime_root / "akvc-macos-sync-ipc"
        direct_sender_library = runtime_root / "libakvc-macos-direct-sender.dylib"
        pkg = runtime_root / "VirtualCamera.pkg"
        sync_ipc_tool.write_bytes(b"x")
        direct_sender_library.write_bytes(b"x")
        pkg.write_bytes(b"x")

        original_package_root = runtime_module._PACKAGE_ROOT
        original_build_search_roots = runtime_module._build_search_roots
        try:
            runtime_module._PACKAGE_ROOT = tmpdir
            runtime_module._build_search_roots = lambda: [tmpdir / "__missing__"]
            resolved_sync_ipc = runtime_module.find_macos_sync_ipc_tool()
            resolved_direct_sender = runtime_module.find_macos_direct_sender_library()
            resolved_pkg = runtime_module.find_macos_pkg()
            return {
                "resolved_sync_ipc_tool": str(resolved_sync_ipc) if resolved_sync_ipc else None,
                "resolved_direct_sender_library": (
                    str(resolved_direct_sender) if resolved_direct_sender else None
                ),
                "resolved_pkg": str(resolved_pkg) if resolved_pkg else None,
                "packaged_assets_discoverable": (
                    resolved_sync_ipc == sync_ipc_tool
                    and resolved_direct_sender == direct_sender_library
                    and resolved_pkg == pkg
                ),
            }
        finally:
            runtime_module._PACKAGE_ROOT = original_package_root
            runtime_module._build_search_roots = original_build_search_roots


def evaluate_validation_report_runtime_case() -> dict[str, Any]:
    module = _load_module(
        VALIDATION_REPORT_TOOL,
        "macos_distribution_contract_validation_report",
    )
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        packaged_dir = tmpdir / "_runtime" / "macos"
        packaged_dir.mkdir(parents=True)
        for name in module.PACKAGED_MACOS_RUNTIME_ASSETS:
            (packaged_dir / name).write_bytes(b"x")
        status_tool = packaged_dir / "akvc-macos-status"
        install_tool = packaged_dir / "akvc-macos-install"
        devices_tool = packaged_dir / "akvc-macos-list-devices"
        uninstall_tool = packaged_dir / "akvc-macos-uninstall"
        sync_ipc_tool = packaged_dir / "akvc-macos-sync-ipc"
        direct_sender_library = packaged_dir / "libakvc-macos-direct-sender.dylib"
        pkg = packaged_dir / "VirtualCamera.pkg"

        original_runtime_dir = module.PACKAGED_MACOS_RUNTIME_DIR
        original_find_uninstall = module.find_macos_uninstall_tool
        original_find_sync_ipc = module.find_macos_sync_ipc_tool
        original_find_direct_sender = module.find_macos_direct_sender_library
        original_find_pkg = module.find_macos_pkg
        try:
            module.PACKAGED_MACOS_RUNTIME_DIR = packaged_dir
            module.find_macos_uninstall_tool = lambda explicit=None: uninstall_tool
            module.find_macos_sync_ipc_tool = lambda explicit=None: sync_ipc_tool
            module.find_macos_direct_sender_library = (
                lambda explicit=None: direct_sender_library
            )
            module.find_macos_pkg = lambda explicit=None: pkg
            snapshot = module._runtime_assets_snapshot(
                status_tool=status_tool,
                install_tool=install_tool,
                devices_tool=devices_tool,
            )
            summary = dict(snapshot.get("summary", {}))
            return {
                "summary": summary,
                "packaged_assets": dict(snapshot.get("packaged_assets", {})),
                "resolved_assets": dict(snapshot.get("resolved_assets", {})),
                "runtime_snapshot_complete": (
                    summary.get("sync_ipc_tool_resolved") is True
                    and summary.get("direct_sender_library_resolved") is True
                    and summary.get("packaged_tools_present") is True
                    and summary.get("packaged_pkg_present") is True
                ),
            }
        finally:
            module.PACKAGED_MACOS_RUNTIME_DIR = original_runtime_dir
            module.find_macos_uninstall_tool = original_find_uninstall
            module.find_macos_sync_ipc_tool = original_find_sync_ipc
            module.find_macos_direct_sender_library = original_find_direct_sender
            module.find_macos_pkg = original_find_pkg


def evaluate_release_diagnostics_case() -> dict[str, Any]:
    module = _load_module(
        RELEASE_DIAGNOSTICS_TOOL,
        "macos_distribution_contract_release_diagnostics",
    )
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        app_bundle = tmpdir / "akvc-host.app"
        extension_bundle = tmpdir / "com.sidus.amaran-desktop.cameraextension.systemextension"
        embedded_extension = (
            app_bundle
            / "Contents"
            / "Library"
            / "SystemExtensions"
            / extension_bundle.name
        )
        embedded_extension.mkdir(parents=True)
        extension_bundle.mkdir(parents=True)
        sync_ipc_tool = tmpdir / "akvc-macos-sync-ipc"
        pkg = tmpdir / "VirtualCamera.pkg"
        dmg = tmpdir / "VirtualCamera.dmg"
        zip_artifact = tmpdir / "VirtualCamera.zip"
        for path in (sync_ipc_tool, pkg, dmg, zip_artifact):
            path.write_bytes(b"x")

        original_bundle_metadata = module._bundle_metadata
        original_binary_metadata = module._binary_metadata
        original_pkg_metadata = module._pkg_metadata
        original_file_metadata = module._file_metadata
        try:
            module._bundle_metadata = lambda path: {
                "path": str(path),
                "exists": True,
                "bundle_identifier": (
                    module.EXPECTED_HOST_BUNDLE_ID
                    if path == app_bundle
                    else module.EXPECTED_EXTENSION_BUNDLE_ID
                ),
                "minimum_system_version": module.EXPECTED_MINIMUM_SYSTEM_VERSION,
                "architectures": ["arm64", "x86_64"],
                "codesign_verify": {"available": True, "returncode": 0},
            }
            module._binary_metadata = lambda path: {
                "path": str(path),
                "exists": True,
                "architectures": ["arm64", "x86_64"],
                "codesign_verify": {"available": True, "returncode": 0},
            }
            module._pkg_metadata = lambda path: {
                "path": str(path),
                "exists": True,
                "signed": True,
                "payload_files": [
                    "./akvc-host.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension"
                ],
                "payload_appledouble_files": [],
                "payload_appledouble_clean": True,
                "package_info": {
                    "identifier": "com.akvc.virtual-camera.pkg",
                    "version": "0.5.0",
                    "install_location": "/Applications",
                },
            }
            module._file_metadata = lambda path: {
                "path": str(path),
                "exists": True,
                "is_file": True,
            }
            payload = module.generate_release_diagnostics(
                app_bundle=app_bundle,
                extension_bundle=extension_bundle,
                sync_ipc_tool=sync_ipc_tool,
                pkg_path=pkg,
                dmg_path=dmg,
                zip_path=zip_artifact,
            )
            summary = dict(payload.get("summary", {}))
            return {
                "summary": summary,
                "sync_ipc_release_surface_complete": (
                    summary.get("sync_ipc_tool_exists") is True
                    and summary.get("sync_ipc_tool_signed") is True
                    and summary.get("sync_ipc_tool_universal2_ready") is True
                    and summary.get("pkg_payload_appledouble_clean") is True
                    and summary.get("release_artifacts_present") is True
                ),
            }
        finally:
            module._bundle_metadata = original_bundle_metadata
            module._binary_metadata = original_binary_metadata
            module._pkg_metadata = original_pkg_metadata
            module._file_metadata = original_file_metadata


def evaluate_contract() -> dict[str, Any]:
    make_surface = parse_make_runtime_surface(_load_text(MAKE_TOOL))
    runtime_locator_surface = parse_runtime_locator_surface(
        _load_text(RUNTIME_LOCATOR_MODULE),
        _load_text(RUNTIME_SHIM_MODULE),
    )
    validation_report_runtime_surface = parse_validation_report_runtime_surface(
        _load_text(VALIDATION_REPORT_TOOL)
    )
    release_diagnostics_surface = parse_release_diagnostics_surface(
        _load_text(RELEASE_DIAGNOSTICS_TOOL)
    )
    sync_runtime_case = evaluate_sync_runtime_case()
    runtime_discovery_case = evaluate_runtime_discovery_case()
    validation_report_runtime_case = evaluate_validation_report_runtime_case()
    release_diagnostics_case = evaluate_release_diagnostics_case()

    consistency = {
        "make_runtime_surface_complete": all(
            bool(value) for value in make_surface.values()
        ),
        "runtime_locator_surface_complete": all(
            bool(value) for value in runtime_locator_surface.values()
        ),
        "validation_report_runtime_surface_complete": all(
            bool(value) for value in validation_report_runtime_surface.values()
        ),
        "release_diagnostics_surface_complete": all(
            bool(value) for value in release_diagnostics_surface.values()
        ),
        "sync_runtime_case_passed": bool(sync_runtime_case["all_synced"]),
        "runtime_discovery_case_passed": bool(
            runtime_discovery_case["packaged_assets_discoverable"]
        ),
        "validation_report_runtime_case_passed": bool(
            validation_report_runtime_case["runtime_snapshot_complete"]
        ),
        "release_diagnostics_case_passed": bool(
            release_diagnostics_case["sync_ipc_release_surface_complete"]
        ),
    }
    consistency["all_checks_passed"] = all(
        bool(value) for value in consistency.values()
    )
    return {
        "make_runtime_surface": make_surface,
        "runtime_locator_surface": runtime_locator_surface,
        "validation_report_runtime_surface": validation_report_runtime_surface,
        "release_diagnostics_surface": release_diagnostics_surface,
        "sync_runtime_case": sync_runtime_case,
        "runtime_discovery_case": runtime_discovery_case,
        "validation_report_runtime_case": validation_report_runtime_case,
        "release_diagnostics_case": release_diagnostics_case,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS distribution/runtime asset contract checker"
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_contract()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    if not bool(payload["consistency"]["all_checks_passed"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
