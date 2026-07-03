# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation-session summary contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_validation_session_summary_contract.py"


def test_macos_validation_session_summary_contract_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "macos_validation_session_summary.py" in text
    assert "full_summary_includes_headings_and_app_groups" in text
    assert "missing_values_render_as_unknown_or_dash" in text
    assert "target_app_groups_derive_from_matrix_when_counts_missing" in text
    assert "validation_passed_app_ids" in text
    assert "validation_reviewed_app_ids" in text
    assert "validation_observed_target_app_ids" in text
    assert "validation_missing_target_app_ids" in text
    assert "validation_unexpected_target_app_ids" in text
    assert "validation_target_app_ids_complete" in text
    assert "validation_manual_validation_ready" in text
    assert "validation_manual_validation_complete" in text
    assert "validation_manual_validation_all_passed" in text
    assert "manual_app_validation_ready" in text
    assert "manual_app_validation_blockers" in text
    assert "effective_devices" in text
    assert "surfaces_validation_app_matrix_evidence" in text
    assert "device_listed" in text
    assert "device_selected" in text
    assert "preview_visible" in text
    assert "screenshot" in text
    assert "effective_all_devices" in text
    assert "effective_device_prefix" in text
    assert "Device Name Cohesion" in text
    assert "demo_camera_name_matches_effective_prefix" in text
    assert "list_devices_binary_check_prefix_matches_effective_prefix" in text
    assert "validation_devices" in text
    assert "validation_all_devices" in text
    assert "validation_device_prefix" in text
    assert "validation_install_status_devices" in text
    assert "validation_install_status_all_devices" in text
    assert "validation_install_device_prefix" in text
    assert "install_session_devices" in text
    assert "install_session_all_devices" in text
    assert "install_session_device_prefix" in text
    assert "validation_install_phase" in text
    assert "validation_install_ipc_ready" in text
    assert "install_session_ipc_ready" in text
    assert "install_session_sync_ipc_success" in text
    assert "release_sync_ipc_tool_exists" in text
    assert "release_sync_ipc_tool_signed" in text
    assert "release_sync_ipc_tool_universal2_ready" in text
    assert "Runtime Asset Provenance" in text
    assert "release_app_bundle_path" in text
    assert "runtime_release_product_identity_consistent" in text
    assert "release_command_tools_signed" in text
    assert "release_pkg_payload_appledouble_clean" in text
    assert "Runtime Command Tools" in text
    assert "All tools signed" in text
    assert "PKG payload AppleDouble clean" in text
    assert "Runtime Topology" in text
    assert "runtime_topology_kind" in text
    assert "runtime_frame_path" in text
    assert "runtime_host_role" in text
    assert "runtime_host_in_frame_hot_path" in text
    assert "runtime_dedicated_host_daemon_required" in text
    assert "runtime_container_app_configured" in text
    assert "runtime_data_plane" in text
    assert "runtime_control_plane" in text
    assert "Control-plane prerequisites satisfied" in text
    assert "target_apps_all_passed" in text
    assert "system_camera_device_visible" in text
    assert "auto_install_ready" in text
    assert "macos_13_plus_declared" in text
    assert "universal2_ready" in text
    assert "release_packaging_ready" in text
    assert "pyside6_path_exercised" in text
    assert "python_entrypoints_consistent" in text
    assert "runtime_assets_packaged" in text
    assert "sync_ipc_control_plane_ready" in text
    assert "validation_app_matrix" in text
    assert "PySide6 Demo" in text
    assert "Runtime Command Tools" in text
    assert "Sync IPC Tool" in text
    assert "Python Entrypoints" in text
    assert "entrypoints_contract_present" in text
    assert "sdk_contract_present" in text
    assert "sdk_contract_passed" in text
    assert "sdk_contract_direct_sender_exports_present" in text
    assert "acceptance_contract_present" in text
    assert "acceptance_contract_passed" in text
    assert "entrypoints_contract_report" in text
    assert "sdk_contract_report" in text
    assert "acceptance_contract_report" in text
    assert "validation_demo_frame_source_kind" in text
    assert "validation_demo_python_entrypoint_kind" in text
    assert "validation_demo_sdk_streamer_factory_used" in text
    assert "validation_demo_sdk_latest_provider_factory_used" in text
    assert "validation_demo_sdk_direct_push_used" in text
    assert "validation_benchmark_kind" in text
    assert "validation_benchmark_matrix_profiles" in text
    assert "benchmark_matrix_complete" in text
    assert "benchmark_fps_targets_met" in text
    assert "Profiles covered" in text
    assert "Required profile set complete" in text
    assert "Benchmark Matrix" in text
    assert "Manual App Validation Readiness" in text
    assert "Target App Details" in text
    assert "steps=`0` checks=`0`" in text
    assert "Acceptance failed count" in text
    assert "Acceptance Contract" in text
    assert "--output" in text


def test_macos_validation_session_summary_contract_tool_reports_expected_render_behavior(
    tmp_path,
) -> None:
    output = tmp_path / "validation-session-summary-contract.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["consistency"]["source_complete"] is True
    assert payload["consistency"]["render_cases_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True

    cases = {item["name"]: item for item in payload["render_cases"]}
    assert cases["full_summary_includes_headings_and_app_groups"]["all_substrings_match"] is True
    assert cases["missing_values_render_as_unknown_or_dash"]["all_substrings_match"] is True
    assert cases["manifest_summary_gate_fallback_without_acceptance_report"]["all_substrings_match"] is True
    assert cases["target_app_groups_derive_from_matrix_when_counts_missing"]["all_substrings_match"] is True
