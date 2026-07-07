# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS delivery gate contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_delivery_gate_contract.py"


def test_macos_delivery_gate_contract_tool_exists_and_references_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "macos_validation_session_acceptance.py" in text
    assert "release_diagnostics_fallback_and_install_session_yield_all_delivery_gates_pass" in text
    assert "partial_release_evidence_and_partial_notarization_keep_unknown" in text
    assert "blocked_install_session_and_missing_signature_fail_delivery_gates" in text
    assert "exact_target_app_ids_all_pass_yield_target_apps_gate_pass" in text
    assert "target_app_counts_without_exact_ids_keep_gate_unknown" in text
    assert "missing_or_unexpected_target_ids_fail_target_apps_gate" in text
    assert "manifest_target_identity_fields_override_validation_summary_for_target_gate" in text
    assert "_preferred_summary_value" in text
    assert "_all_true_or_false_or_none" in text
    assert "EXPECTED_APP_IDS" in text
    assert "signing_evidence_ready" in text
    assert "command_tools_signed" in text
    assert "notarization_tooling_ready" in text
    assert "auto_install_ready" in text
    assert "sync_ipc_control_plane_ready" in text
    assert "system_camera_device_visible" in text
    assert "list_devices_binary_check_passed" in text
    assert "install_session_sync_ipc_present" in text
    assert "install_session_sync_ipc_success" in text
    assert "target_apps_all_passed" in text
    assert "target_apps_require_preview_evidence" in text
    assert "preview_visible" in text
    assert "--output" in text


def test_macos_delivery_gate_contract_tool_reports_expected_gate_behavior(
    tmp_path,
) -> None:
    output = tmp_path / "macos-delivery-gate-contract.json"

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

    assert payload["source"]["defines_preferred_summary_value"] is True
    assert payload["source"]["defines_tri_state_gate_helper"] is True
    assert payload["source"]["release_gate_reads_release_summary_pkg_signed"] is True
    assert payload["source"]["release_gate_reads_release_summary_command_tools_signed"] is True
    assert payload["source"]["release_gate_reads_release_summary_appledouble_clean"] is True
    assert payload["source"]["target_apps_define_expected_ids"] is True
    assert payload["source"]["target_apps_read_validation_passed_ids"] is True
    assert payload["source"]["target_apps_read_validation_observed_ids"] is True
    assert payload["source"]["target_apps_read_validation_missing_ids"] is True
    assert payload["source"]["target_apps_read_validation_unexpected_ids"] is True
    assert payload["source"]["target_apps_compute_missing_ids"] is True
    assert payload["source"]["target_apps_require_preview_evidence"] is True
    assert payload["source"]["auto_install_uses_install_session_ipc_ready"] is True
    assert payload["source"]["sync_gate_reads_release_sync_ipc_tool_exists"] is True
    assert payload["source"]["sync_gate_reads_release_sync_ipc_tool_signed"] is True
    assert payload["source"]["sync_gate_reads_release_sync_ipc_tool_universal2_ready"] is True
    assert payload["source"]["sync_gate_reads_install_session_sync_ipc_present"] is True
    assert payload["source"]["sync_gate_reads_install_session_sync_ipc_supported"] is True
    assert payload["source"]["sync_gate_reads_install_session_sync_ipc_success"] is True
    assert payload["source"]["exports_sync_ipc_gate"] is True
    assert payload["source"]["exports_system_camera_device_gate"] is True
    assert payload["source"]["system_camera_gate_reads_list_devices_check_passed"] is True
    assert payload["source"]["system_camera_gate_reads_filtered_device_count"] is True
    assert payload["source"]["notarization_uses_can_notarize"] is True
    assert payload["consistency"]["source_complete"] is True
    assert payload["consistency"]["gate_cases_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True

    cases = {item["name"]: item for item in payload["gate_cases"]}
    assert cases["release_diagnostics_fallback_and_install_session_yield_all_delivery_gates_pass"]["actual"] == {
        "macos_13_plus_declared": "pass",
        "universal2_ready": "pass",
        "release_packaging_ready": "pass",
        "signing_evidence_ready": "pass",
        "notarization_tooling_ready": "pass",
        "system_camera_device_visible": "pass",
        "auto_install_ready": "pass",
        "sync_ipc_control_plane_ready": "pass",
    }
    assert cases["partial_release_evidence_and_partial_notarization_keep_unknown"]["actual"] == {
        "macos_13_plus_declared": "pass",
        "universal2_ready": "unknown",
        "release_packaging_ready": "unknown",
        "signing_evidence_ready": "unknown",
        "notarization_tooling_ready": "unknown",
        "system_camera_device_visible": "unknown",
        "auto_install_ready": "unknown",
        "sync_ipc_control_plane_ready": "unknown",
    }
    assert cases["blocked_install_session_and_missing_signature_fail_delivery_gates"]["actual"] == {
        "signing_evidence_ready": "fail",
        "notarization_tooling_ready": "fail",
        "system_camera_device_visible": "fail",
        "auto_install_ready": "fail",
        "sync_ipc_control_plane_ready": "fail",
    }
    assert cases["exact_target_app_ids_all_pass_yield_target_apps_gate_pass"]["actual"] == {
        "target_apps_all_passed": "pass",
    }
    assert cases["target_app_counts_without_exact_ids_keep_gate_unknown"]["actual"] == {
        "target_apps_all_passed": "unknown",
    }
    assert cases["missing_or_unexpected_target_ids_fail_target_apps_gate"]["actual"] == {
        "target_apps_all_passed": "fail",
    }
    assert cases["manifest_target_identity_fields_override_validation_summary_for_target_gate"]["actual"] == {
        "target_apps_all_passed": "fail",
    }
