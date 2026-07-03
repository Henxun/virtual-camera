# SPDX-License-Identifier: Apache-2.0
"""Build/architecture contract checks for the macOS virtual camera tree."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT_YML = ROOT / "virtualcam/macos/project.yml"
APP_PLIST = ROOT / "virtualcam/macos/demo_app/Info.plist"
EXTENSION_PLIST = ROOT / "virtualcam/macos/camera_extension/Info.plist"
MAKE_PY = ROOT / "tools/make.py"
AVFOUNDATION_COMMAND_TARGETS = [
    "akvc-demo-app",
    "akvc-macos-status",
    "akvc-macos-install",
    "akvc-macos-uninstall",
    "akvc-macos-list-devices",
    "akvc-macos-sync-ipc",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        data = plistlib.load(fh)
    return data if isinstance(data, dict) else {}


def parse_project_contract(text: str) -> dict[str, Any]:
    deployment_match = re.search(r'deploymentTarget:\s*\n\s*macOS:\s*"([^"]+)"', text)
    target_match = re.search(r'MACOSX_DEPLOYMENT_TARGET:\s*"([^"]+)"', text)
    arch_match = re.search(r'ARCHS:\s*"([^"]+)"', text)
    only_active_match = re.search(r"ONLY_ACTIVE_ARCH:\s*([A-Z]+)", text)
    return {
        "deployment_target": deployment_match.group(1) if deployment_match else None,
        "macosx_deployment_target": target_match.group(1) if target_match else None,
        "architectures": sorted((arch_match.group(1).split() if arch_match else [])),
        "only_active_arch": only_active_match.group(1) if only_active_match else None,
    }


def _target_block(text: str, target_name: str) -> str:
    pattern = rf"(?ms)^  {re.escape(target_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|^schemes:\n|\Z)"
    match = re.search(pattern, text)
    return match.group("body") if match else ""


def parse_project_framework_contract(text: str) -> dict[str, Any]:
    return {
        target: {
            "uses_command_support": "control_bridge/AKVCCommandSupport.mm" in _target_block(text, target),
            "links_avfoundation": "AVFoundation.framework" in _target_block(text, target),
        }
        for target in AVFOUNDATION_COMMAND_TARGETS
    }


def parse_plist_contract(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "minimum_system_version": payload.get("LSMinimumSystemVersion"),
        "bundle_identifier": payload.get("CFBundleIdentifier"),
    }


def parse_make_contract(text: str) -> dict[str, Any]:
    arch_default_match = re.search(r'MACOS_BUILD_ARCHS\s*=\s*os\.environ\.get\("MACOS_ARCHS",\s*"([^"]+)"\)', text)
    default_arches = sorted((arch_default_match.group(1).split() if arch_default_match else []))
    return {
        "default_arches": default_arches,
        "build_parser_supports_archs": 'pb.add_argument("--archs"' in text,
        "build_parser_supports_deployment_target": 'pb.add_argument("--deployment-target"' in text,
        "package_parser_supports_archs": 'pp.add_argument("--archs"' in text,
        "package_parser_supports_deployment_target": 'pp.add_argument("--deployment-target"' in text,
        "xcodebuild_sets_archs": 'f"ARCHS={effective_archs}"' in text,
        "xcodebuild_forces_only_active_arch_off": '"ONLY_ACTIVE_ARCH=NO"' in text,
        "xcodebuild_sets_deployment_target": 'f"MACOSX_DEPLOYMENT_TARGET={effective_deployment_target}"' in text,
        "xcodebuild_disables_codesign_by_default": (
            '"CODE_SIGNING_ALLOWED=NO"' in text
            and '"CODE_SIGNING_REQUIRED=NO"' in text
            and '"CODE_SIGN_IDENTITY="' in text
        ),
        "package_auto_signs_when_identity_present": (
            "sign_identity = _effective_macos_sign_identity()" in text
            and "if sign_identity:" in text
            and "cmd_sign_macos(args)" in text
        ),
    }


def evaluate_contract() -> dict[str, Any]:
    project_text = _read_text(PROJECT_YML)
    project = parse_project_contract(project_text)
    project_frameworks = parse_project_framework_contract(project_text)
    app_plist = parse_plist_contract(_read_plist(APP_PLIST))
    extension_plist = parse_plist_contract(_read_plist(EXTENSION_PLIST))
    make = parse_make_contract(_read_text(MAKE_PY))

    consistency = {
        "deployment_target_complete": (
            project["deployment_target"] == "13.0"
            and project["macosx_deployment_target"] == "13.0"
            and app_plist["minimum_system_version"] == "13.0"
            and extension_plist["minimum_system_version"] == "13.0"
            and make["xcodebuild_sets_deployment_target"] is True
        ),
        "universal_arches_declared": (
            project["architectures"] == ["arm64", "x86_64"]
            and project["only_active_arch"] == "NO"
            and make["default_arches"] == ["arm64", "x86_64"]
        ),
        "xcodebuild_propagates_arches": (
            make["xcodebuild_sets_archs"] is True
            and make["xcodebuild_forces_only_active_arch_off"] is True
        ),
        "cli_surface_complete": (
            make["build_parser_supports_archs"] is True
            and make["build_parser_supports_deployment_target"] is True
            and make["package_parser_supports_archs"] is True
            and make["package_parser_supports_deployment_target"] is True
        ),
        "unsigned_compile_path_available": (
            make["xcodebuild_disables_codesign_by_default"] is True
        ),
        "package_sign_bridge_present": (
            make["package_auto_signs_when_identity_present"] is True
        ),
        "command_support_targets_link_avfoundation": all(
            item["uses_command_support"] is True
            and item["links_avfoundation"] is True
            for item in project_frameworks.values()
        ),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "project": project,
        "project_frameworks": project_frameworks,
        "app_plist": app_plist,
        "extension_plist": extension_plist,
        "make": make,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS build/architecture contract checker")
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
        print("macOS build/architecture contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
