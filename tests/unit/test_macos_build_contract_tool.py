# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS build/architecture contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_build_contract.py"


def test_macos_build_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "virtualcam/macos/project.yml" in text
    assert "demo_app/Info.plist" in text
    assert "camera_extension/Info.plist" in text
    assert "tools/make.py" in text
    assert "universal_arches_declared" in text
    assert "deployment_target_complete" in text
    assert "command_support_targets_link_avfoundation" in text


def test_macos_build_contract_tool_reports_expected_architecture_and_version_surface() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["project"]["deployment_target"] == "13.0"
    assert payload["project"]["macosx_deployment_target"] == "13.0"
    assert payload["project"]["architectures"] == ["arm64", "x86_64"]
    assert payload["project"]["only_active_arch"] == "NO"
    assert payload["app_plist"]["minimum_system_version"] == "13.0"
    assert payload["extension_plist"]["minimum_system_version"] == "13.0"
    assert payload["make"]["default_arches"] == ["arm64", "x86_64"]
    assert payload["make"]["build_parser_supports_archs"] is True
    assert payload["make"]["build_parser_supports_deployment_target"] is True
    assert payload["make"]["package_parser_supports_archs"] is True
    assert payload["make"]["package_parser_supports_deployment_target"] is True
    assert payload["make"]["xcodebuild_forces_only_active_arch_off"] is True
    assert payload["make"]["xcodebuild_sets_deployment_target"] is True
    assert payload["make"]["xcodebuild_disables_codesign_by_default"] is True
    assert payload["make"]["package_auto_signs_when_identity_present"] is True
    for target in (
        "akvc-demo-app",
        "akvc-macos-status",
        "akvc-macos-install",
        "akvc-macos-uninstall",
        "akvc-macos-list-devices",
        "akvc-macos-sync-ipc",
    ):
        assert payload["project_frameworks"][target]["uses_command_support"] is True
        assert payload["project_frameworks"][target]["links_avfoundation"] is True
    assert payload["consistency"]["deployment_target_complete"] is True
    assert payload["consistency"]["universal_arches_declared"] is True
    assert payload["consistency"]["xcodebuild_propagates_arches"] is True
    assert payload["consistency"]["cli_surface_complete"] is True
    assert payload["consistency"]["unsigned_compile_path_available"] is True
    assert payload["consistency"]["package_sign_bridge_present"] is True
    assert payload["consistency"]["command_support_targets_link_avfoundation"] is True
    assert payload["consistency"]["all_checks_passed"] is True
