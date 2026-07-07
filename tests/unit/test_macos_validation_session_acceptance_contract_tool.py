# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation-session acceptance contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_validation_session_acceptance_contract.py"


def test_macos_validation_session_acceptance_contract_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "macos_validation_session_acceptance.py" in text
    assert "complete_acceptance_passes_key_gates" in text
    assert "only_counts_keep_target_apps_unknown" in text
    assert "manifest_identity_fields_override_validation_summary_and_fail_target_gate" in text
    assert "missing_entrypoints_contract_and_benchmark_keep_gates_unknown" in text
    assert "EXPECTED_APP_IDS" in text
    assert "validation_observed_target_app_ids" in text
    assert "validation_missing_target_app_ids" in text
    assert "validation_unexpected_target_app_ids" in text
    assert "benchmark_matrix_complete" in text
    assert "manual_app_validation_ready" in text
    assert "manual_app_validation_blockers" in text
    assert "pyside6_path_exercised" in text
    assert "python_direct_runtime_ready" in text
    assert "python_entrypoints_consistent" in text
    assert "sync_ipc_control_plane_ready" in text
    assert "direct_push_demo_using_direct_sender" in text
    assert "direct_push_demo_shared_memory_fallback_used" in text
    assert "install_session_sync_ipc_present" in text
    assert "install_session_sync_ipc_success" in text
    assert "command_tools_signed" in text
    assert "release_command_tools_signed" in text
    assert "pkg_payload_appledouble_clean" in text
    assert "runtime_release_product_mismatch_fails_release_packaging_gate" in text
    assert "custom_device_name_visibility_failure_keeps_runtime_name_in_evidence" in text
    assert "runtime_release_product_identity_consistent" in text
    assert "effective_device_prefix" in text
    assert "validation_demo_camera_name" in text
    assert "demo_camera_name_matches_effective_prefix" in text
    assert "target_app_missing_evidence_ids" in text
    assert "preview_visible" in text
    assert "--output" in text


def test_macos_validation_session_acceptance_contract_tool_reports_expected_behavior(
    tmp_path,
) -> None:
    output = tmp_path / "validation-session-acceptance-contract.json"

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

    assert payload["source"]["defines_expected_app_ids"] is True
    assert payload["source"]["reads_validation_observed_target_app_ids"] is True
    assert payload["source"]["reads_validation_missing_target_app_ids"] is True
    assert payload["source"]["reads_validation_unexpected_target_app_ids"] is True
    assert payload["source"]["defines_expected_benchmark_profiles"] is True
    assert payload["source"]["exports_benchmark_matrix_gate"] is True
    assert payload["source"]["reads_benchmark_required_profiles_present"] is True
    assert payload["source"]["reads_benchmark_missing_required_profiles"] is True
    assert payload["source"]["exports_python_direct_runtime_gate"] is True
    assert payload["source"]["reads_direct_push_demo_using_direct_sender"] is True
    assert payload["source"]["reads_direct_push_demo_helper_hot_path_used"] is True
    assert payload["source"]["reads_direct_push_demo_shared_memory_fallback_used"] is True
    assert payload["source"]["missing_target_ids_fail_gate"] is True
    assert payload["source"]["reads_install_session_sync_ipc_present"] is True
    assert payload["source"]["reads_install_session_sync_ipc_success"] is True
    assert payload["source"]["reads_release_command_tools_signed"] is True
    assert payload["source"]["reads_release_pkg_payload_appledouble_clean"] is True
    assert payload["source"]["exports_signing_command_tools_evidence"] is True
    assert payload["source"]["reads_effective_device_prefix"] is True
    assert payload["source"]["reads_validation_demo_camera_name"] is True
    assert payload["source"]["exports_device_name_match_evidence"] is True
    assert payload["source"]["reads_target_app_evidence"] is True
    assert payload["source"]["reports_missing_target_app_evidence"] is True
    assert payload["consistency"]["source_complete"] is True
    assert payload["consistency"]["cases_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True

    cases = {item["name"]: item for item in payload["cases"]}
    assert cases["complete_acceptance_passes_key_gates"]["actual"] == {
        "acceptance_ready": True,
        "manual_app_validation_ready": True,
        "manual_app_validation_blockers": [],
        "target_apps_all_passed": "pass",
        "benchmark_matrix_complete": "pass",
        "pyside6_path_exercised": "pass",
        "python_direct_runtime_ready": "pass",
        "python_entrypoints_consistent": "pass",
        "system_camera_device_visible": "pass",
        "sync_ipc_control_plane_ready": "pass",
    }
    assert cases["incomplete_benchmark_matrix_fails_matrix_gate"]["actual"] == {
        "acceptance_ready": False,
        "manual_app_validation_ready": True,
        "manual_app_validation_blockers": [],
        "benchmark_matrix_complete": "fail",
        "benchmark_fps_targets_met": "pass",
        "benchmark_1080p60_cpu_target_met": "pass",
    }
    assert cases["only_counts_keep_target_apps_unknown"]["actual"] == {
        "acceptance_ready": False,
        "target_apps_all_passed": "unknown",
    }
    assert cases["manifest_identity_fields_override_validation_summary_and_fail_target_gate"]["actual"] == {
        "acceptance_ready": False,
        "target_apps_all_passed": "fail",
    }
    assert cases["missing_entrypoints_contract_and_benchmark_keep_gates_unknown"]["actual"] == {
        "acceptance_ready": False,
        "manual_app_validation_ready": False,
        "manual_app_validation_blockers": [
            "macos_13_plus_declared",
            "universal2_ready",
            "release_packaging_ready",
            "signing_evidence_ready",
            "notarization_tooling_ready",
            "python_direct_runtime_ready",
            "python_entrypoints_consistent",
            "auto_install_ready",
            "system_camera_device_visible",
            "artifact_replay_passed",
            "runtime_assets_packaged",
        ],
        "benchmark_matrix_complete": "unknown",
        "python_entrypoints_consistent": "unknown",
        "benchmark_1080p60_cpu_target_met": "unknown",
    }
    assert cases["runtime_release_product_mismatch_fails_release_packaging_gate"]["actual"] == {
        "acceptance_ready": False,
        "release_packaging_ready": "fail",
    }
    assert cases["shared_memory_fallback_fails_python_direct_runtime_gate"]["actual"] == {
        "acceptance_ready": False,
        "python_direct_runtime_ready": "fail",
    }
    assert cases["custom_device_name_visibility_failure_keeps_runtime_name_in_evidence"]["actual"] == {
        "acceptance_ready": False,
        "system_camera_device_visible": "fail",
    }
    assert cases["custom_device_name_visibility_failure_keeps_runtime_name_in_evidence"]["custom_device_name_evidence"] == {
        "effective_device_prefix": "AKVC Demo",
        "validation_demo_camera_name": "AKVC Demo",
        "demo_camera_name_matches_effective_prefix": True,
        "list_devices_binary_check_device_prefix_matches_effective_prefix": True,
        "note_contains_runtime_name": True,
    }
