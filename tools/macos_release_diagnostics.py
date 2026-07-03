# SPDX-License-Identifier: Apache-2.0
"""Release-artifact diagnostics for the macOS virtual camera build."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD_DIR = ROOT / "build" / "macos"
DEFAULT_PRODUCTS_DIR = DEFAULT_BUILD_DIR / "Build" / "Products" / "Release"
# Demo-app fallback only. Real container-app selection should go through
# `_detect_default_app_bundle()` so the main app can replace the repo demo app.
DEFAULT_FALLBACK_APP_BUNDLE = DEFAULT_PRODUCTS_DIR / "akvc-demo-app.app"
DEFAULT_EXTENSION_BUNDLE = DEFAULT_PRODUCTS_DIR / "com.sidus.amaran-desktop.cameraextension.systemextension"
DEFAULT_SYNC_IPC_TOOL = DEFAULT_PRODUCTS_DIR / "akvc-macos-sync-ipc"
DEFAULT_COMMAND_TOOLS = {
    "status": DEFAULT_PRODUCTS_DIR / "akvc-macos-status",
    "install": DEFAULT_PRODUCTS_DIR / "akvc-macos-install",
    "uninstall": DEFAULT_PRODUCTS_DIR / "akvc-macos-uninstall",
    "list_devices": DEFAULT_PRODUCTS_DIR / "akvc-macos-list-devices",
    "sync_ipc": DEFAULT_SYNC_IPC_TOOL,
}
DEFAULT_PKG = DEFAULT_BUILD_DIR / "VirtualCamera.pkg"
DEFAULT_DMG = DEFAULT_BUILD_DIR / "VirtualCamera.dmg"
DEFAULT_ZIP = DEFAULT_BUILD_DIR / "VirtualCamera.zip"
EXPECTED_HOST_BUNDLE_ID = "com.sidus.amaran-desktop"
EXPECTED_EXTENSION_BUNDLE_ID = "com.sidus.amaran-desktop.cameraextension"
EXPECTED_MINIMUM_SYSTEM_VERSION = "13.0"
EMBEDDED_EXTENSION_BUNDLE_NAME = "com.sidus.amaran-desktop.cameraextension.systemextension"


def _run_probe(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "available": False,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "available": True,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _read_plist(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            data = plistlib.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _find_bundle_executable(bundle_path: Path, payload: dict[str, Any]) -> tuple[str | None, Path | None]:
    macos_dir = bundle_path / "Contents" / "MacOS"
    executable_name = str(payload.get("CFBundleExecutable") or "") or None
    if executable_name:
        executable_path = macos_dir / executable_name
        if executable_path.is_file():
            return executable_name, executable_path

    if macos_dir.is_dir():
        candidates = sorted(path for path in macos_dir.iterdir() if path.is_file())
        if len(candidates) == 1:
            return candidates[0].name, candidates[0]
    return executable_name, None


def _bundle_metadata(bundle_path: Path) -> dict[str, Any]:
    if not bundle_path.is_dir():
        return {
            "path": str(bundle_path),
            "exists": False,
        }
    plist_path = bundle_path / "Contents" / "Info.plist"
    payload = _read_plist(plist_path)
    executable, executable_path = _find_bundle_executable(bundle_path, payload)
    lipo = (
        _run_probe(["lipo", "-archs", str(executable_path)])
        if executable_path is not None and executable_path.is_file()
        else None
    )
    codesign_verify = _run_probe(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(bundle_path)])
    spctl_assess = _run_probe(["spctl", "-a", "-vvv", str(bundle_path)])
    stapler_validate = _run_probe(["xcrun", "stapler", "validate", str(bundle_path)])
    arches = []
    if isinstance(lipo, dict) and lipo.get("available") and lipo.get("returncode") == 0:
        arches = sorted(str(lipo.get("stdout", "")).split())
    return {
        "path": str(bundle_path),
        "exists": True,
        "plist_path": str(plist_path),
        "bundle_identifier": payload.get("CFBundleIdentifier"),
        "minimum_system_version": payload.get("LSMinimumSystemVersion"),
        "executable_name": executable,
        "executable_path": str(executable_path) if executable_path is not None else None,
        "executable_exists": bool(executable_path is not None and executable_path.is_file()),
        "architectures": arches,
        "lipo": lipo,
        "codesign_verify": codesign_verify,
        "spctl_assess": spctl_assess,
        "stapler_validate": stapler_validate,
    }


def _app_embeds_extension(bundle_path: Path, extension_bundle_name: str = EMBEDDED_EXTENSION_BUNDLE_NAME) -> bool:
    return (bundle_path / "Contents" / "Library" / "SystemExtensions" / extension_bundle_name).is_dir()


def _is_preferred_container_app(bundle_path: Path) -> bool:
    return bundle_path.name != "akvc-host.app"


def _detect_default_app_bundle(
    products_dir: Path = DEFAULT_PRODUCTS_DIR,
    extension_bundle_name: str = EMBEDDED_EXTENSION_BUNDLE_NAME,
) -> Path:
    candidates = sorted(path for path in products_dir.glob("*.app") if path.is_dir())
    for candidate in candidates:
        if _is_preferred_container_app(candidate) and _app_embeds_extension(candidate, extension_bundle_name):
            return candidate
    for candidate in candidates:
        if _app_embeds_extension(candidate, extension_bundle_name):
            return candidate
    if products_dir == DEFAULT_PRODUCTS_DIR and DEFAULT_FALLBACK_APP_BUNDLE.is_dir():
        return DEFAULT_FALLBACK_APP_BUNDLE
    return DEFAULT_FALLBACK_APP_BUNDLE


def _pkg_signed(signature_probe: dict[str, Any] | None) -> bool | None:
    if not isinstance(signature_probe, dict):
        return None
    if not signature_probe.get("available"):
        return None
    combined = "\n".join(
        part for part in (
            str(signature_probe.get("stdout", "")),
            str(signature_probe.get("stderr", "")),
        ) if part
    ).lower()
    if "no signature" in combined or "not signed" in combined:
        return False
    return signature_probe.get("returncode") == 0


def _probe_passed(probe: dict[str, Any] | None) -> bool | None:
    if not isinstance(probe, dict):
        return None
    if not probe.get("available"):
        return None
    return probe.get("returncode") == 0


def _pkg_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
        }
    signature = _run_probe(["pkgutil", "--check-signature", str(path)])
    payload_files_probe = _run_probe(["pkgutil", "--payload-files", str(path)])
    payload_files = [
        line.strip()
        for line in str(payload_files_probe.get("stdout", "")).splitlines()
        if line.strip()
    ] if payload_files_probe.get("available") else []
    payload_appledouble_files = [
        item
        for item in payload_files
        if Path(item).name.startswith("._") or "/._" in item or item.startswith("._")
    ]

    package_info: dict[str, Any] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="akvc-release-diagnostics-") as temp_dir:
            expanded_dir = Path(temp_dir) / "expanded"
            expand_probe = _run_probe(["pkgutil", "--expand-full", str(path), str(expanded_dir)])
            if expand_probe.get("available") and expand_probe.get("returncode") == 0:
                package_info_path = expanded_dir / "PackageInfo"
                if package_info_path.is_file():
                    root = ET.fromstring(package_info_path.read_text(encoding="utf-8"))
                    package_info = {
                        "identifier": root.attrib.get("identifier"),
                        "version": root.attrib.get("version"),
                        "install_location": root.attrib.get("install-location"),
                        "auth": root.attrib.get("auth"),
                        "format_version": root.attrib.get("format-version"),
                        "bundle_ids": sorted(
                            {
                                child.attrib["id"]
                                for child in root.findall("./bundle")
                                if "id" in child.attrib
                            }
                        ),
                        "payload_number_of_files": (
                            int(root.find("./payload").attrib.get("numberOfFiles", "0"))
                            if root.find("./payload") is not None
                            else None
                        ),
                        "payload_install_kbytes": (
                            int(root.find("./payload").attrib.get("installKBytes", "0"))
                            if root.find("./payload") is not None
                            else None
                        ),
                    }
    except (OSError, ET.ParseError, ValueError):
        package_info = None

    spctl_assess = _run_probe(["spctl", "-a", "-vvv", "-t", "install", str(path)])
    stapler_validate = _run_probe(["xcrun", "stapler", "validate", str(path)])
    return {
        "path": str(path),
        "exists": True,
        "signature": signature,
        "payload_files": payload_files,
        "payload_appledouble_files": payload_appledouble_files,
        "payload_appledouble_clean": not payload_appledouble_files if payload_files_probe.get("available") else None,
        "payload_files_probe": payload_files_probe,
        "package_info": package_info,
        "signed": _pkg_signed(signature),
        "spctl_assess": spctl_assess,
        "stapler_validate": stapler_validate,
    }


def _file_metadata(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
    }


def _binary_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
        }
    lipo = _run_probe(["lipo", "-archs", str(path)])
    codesign_verify = _run_probe(["codesign", "--verify", "--strict", "--verbose=2", str(path)])
    spctl_assess = _run_probe(["spctl", "-a", "-vvv", str(path)])
    arches = []
    if isinstance(lipo, dict) and lipo.get("available") and lipo.get("returncode") == 0:
        arches = sorted(str(lipo.get("stdout", "")).split())
    return {
        "path": str(path),
        "exists": True,
        "is_file": True,
        "executable": bool(path.stat().st_mode & 0o111),
        "architectures": arches,
        "lipo": lipo,
        "codesign_verify": codesign_verify,
        "spctl_assess": spctl_assess,
    }


def generate_release_diagnostics(
    *,
    app_bundle: Path,
    extension_bundle: Path,
    sync_ipc_tool: Path,
    command_tools: dict[str, Path] | None = None,
    pkg_path: Path,
    dmg_path: Path,
    zip_path: Path,
) -> dict[str, Any]:
    app = _bundle_metadata(app_bundle)
    extension = _bundle_metadata(extension_bundle)
    sync_ipc = _binary_metadata(sync_ipc_tool)
    resolved_command_tools = (
        dict(command_tools)
        if command_tools is not None
        else {
            "status": sync_ipc_tool.parent / "akvc-macos-status",
            "install": sync_ipc_tool.parent / "akvc-macos-install",
            "uninstall": sync_ipc_tool.parent / "akvc-macos-uninstall",
            "list_devices": sync_ipc_tool.parent / "akvc-macos-list-devices",
            "sync_ipc": sync_ipc_tool,
        }
    )
    command_tool_metadata = {
        name: _binary_metadata(path)
        for name, path in sorted(resolved_command_tools.items())
    }
    pkg = _pkg_metadata(pkg_path)
    dmg = _file_metadata(dmg_path)
    zip_artifact = _file_metadata(zip_path)

    app_signed = (
        isinstance(app.get("codesign_verify"), dict)
        and app["codesign_verify"].get("available")
        and app["codesign_verify"].get("returncode") == 0
    )
    extension_signed = (
        isinstance(extension.get("codesign_verify"), dict)
        and extension["codesign_verify"].get("available")
        and extension["codesign_verify"].get("returncode") == 0
    )
    sync_ipc_signed = (
        isinstance(sync_ipc.get("codesign_verify"), dict)
        and sync_ipc["codesign_verify"].get("available")
        and sync_ipc["codesign_verify"].get("returncode") == 0
    )
    app_arches = list(app.get("architectures") or [])
    extension_arches = list(extension.get("architectures") or [])
    sync_ipc_arches = list(sync_ipc.get("architectures") or [])
    command_tool_values = list(command_tool_metadata.values())
    expected_arches = ["arm64", "x86_64"]
    universal2_ready = (
        sorted(app_arches) == expected_arches and sorted(extension_arches) == expected_arches
    )
    sync_ipc_universal2_ready = sorted(sync_ipc_arches) == expected_arches
    command_tools_exist = all(bool(item.get("exists")) for item in command_tool_values)
    command_tools_signed = all(
        isinstance(item.get("codesign_verify"), dict)
        and item["codesign_verify"].get("available")
        and item["codesign_verify"].get("returncode") == 0
        for item in command_tool_values
    )
    command_tools_universal2_ready = all(
        sorted(list(item.get("architectures") or [])) == expected_arches
        for item in command_tool_values
    )
    package_info = pkg.get("package_info") if isinstance(pkg.get("package_info"), dict) else {}
    payload_files = list(pkg.get("payload_files") or [])
    includes_extension_payload = any(
        "Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension" in path
        for path in payload_files
    )
    embedded_extension_path = app_bundle / "Contents" / "Library" / "SystemExtensions" / extension_bundle.name
    host_embeds_extension_bundle = embedded_extension_path.is_dir()

    return {
        "artifacts": {
            "app_bundle": app,
            "extension_bundle": extension,
            "command_tools": command_tool_metadata,
            "sync_ipc_tool": sync_ipc,
            "pkg": pkg,
            "dmg": dmg,
            "zip": zip_artifact,
            "embedded_extension_path": str(embedded_extension_path),
        },
        "summary": {
            "app_exists": bool(app.get("exists")),
            "extension_exists": bool(extension.get("exists")),
            "command_tools_exist": command_tools_exist,
            "sync_ipc_tool_exists": bool(sync_ipc.get("exists")),
            "pkg_exists": bool(pkg.get("exists")),
            "dmg_exists": bool(dmg.get("exists")),
            "zip_exists": bool(zip_artifact.get("exists")),
            "app_signed": app_signed,
            "app_gatekeeper_accepted": _probe_passed(app.get("spctl_assess")),
            "app_stapled": _probe_passed(app.get("stapler_validate")),
            "extension_signed": extension_signed,
            "command_tools_signed": command_tools_signed if command_tool_values else None,
            "sync_ipc_tool_signed": sync_ipc_signed if sync_ipc.get("exists") else None,
            "pkg_signed": pkg.get("signed"),
            "pkg_gatekeeper_accepted": _probe_passed(pkg.get("spctl_assess")),
            "pkg_stapled": _probe_passed(pkg.get("stapler_validate")),
            "universal2_ready": universal2_ready,
            "command_tools_universal2_ready": (
                command_tools_universal2_ready if command_tool_values else None
            ),
            "sync_ipc_tool_universal2_ready": sync_ipc_universal2_ready if sync_ipc.get("exists") else None,
            "bundle_identifiers_present": bool(app.get("bundle_identifier") and extension.get("bundle_identifier")),
            "host_bundle_identifier_expected": app.get("bundle_identifier") == EXPECTED_HOST_BUNDLE_ID,
            "extension_bundle_identifier_expected": extension.get("bundle_identifier") == EXPECTED_EXTENSION_BUNDLE_ID,
            "minimum_system_version_expected": (
                app.get("minimum_system_version") == EXPECTED_MINIMUM_SYSTEM_VERSION
                and extension.get("minimum_system_version") == EXPECTED_MINIMUM_SYSTEM_VERSION
            ),
            "host_embeds_extension_bundle": host_embeds_extension_bundle,
            "release_artifacts_present": bool(pkg.get("exists") and zip_artifact.get("exists")),
            "pkg_install_location_expected": package_info.get("install_location") == "/Applications",
            "pkg_identifier_expected": package_info.get("identifier") == "com.akvc.virtual-camera.pkg",
            "pkg_version_present": bool(package_info.get("version")),
            "pkg_includes_extension_payload": includes_extension_payload,
            "pkg_payload_appledouble_clean": pkg.get("payload_appledouble_clean"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS release diagnostics helper")
    parser.add_argument("--app-bundle")
    parser.add_argument("--extension-bundle", default=str(DEFAULT_EXTENSION_BUNDLE))
    parser.add_argument("--sync-ipc-tool", default=str(DEFAULT_SYNC_IPC_TOOL))
    parser.add_argument("--pkg-path", default=str(DEFAULT_PKG))
    parser.add_argument("--dmg-path", default=str(DEFAULT_DMG))
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP))
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    app_bundle = Path(args.app_bundle) if args.app_bundle else _detect_default_app_bundle()

    payload = generate_release_diagnostics(
        app_bundle=app_bundle,
        extension_bundle=Path(args.extension_bundle),
        sync_ipc_tool=Path(args.sync_ipc_tool),
        pkg_path=Path(args.pkg_path),
        dmg_path=Path(args.dmg_path),
        zip_path=Path(args.zip_path),
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
