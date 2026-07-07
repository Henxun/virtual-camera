# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS app-matrix contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_app_matrix_contract.py"


def test_macos_app_matrix_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "camera-core/src/akvc/platforms/macos/installer.py" in text
    assert "tools/macos_validation_report.py" in text
    assert "tools/macos_smoke.py" in text
    assert "macos_validation_session_acceptance.py" in text
    assert 'VALIDATION_SESSION = ROOT / "tools" / "macos_validation_session.py"' in text
    assert 'VALIDATION_SESSION_SUMMARY = ROOT / "tools" / "macos_validation_session_summary.py"' in text
    assert 'VALIDATION_SESSION_ACCEPTANCE = ROOT / "tools" / "macos_validation_session_acceptance.py"' in text
    assert "docs/macos/manual_validation_results.example.json" in text
    assert "EXPECTED_APP_COUNT" in text
    assert "EXPECTED_APP_IDS" in text
    assert "manual_result_ids_match_targets" in text
    assert "acceptance_expected_app_ids_match_targets" in text
    assert "example_template_fields_complete" in text
    assert "example_template_checks_present" in text
    assert "example_template_evidence_shape_complete" in text
    assert "acceptance_expected_app_count_matches_targets" in text
    assert "target_ids_complete" in text
    assert "validation_session_exports_target_identity_fields" in text
    assert "validation_session_summary_surfaces_target_identity_fields" in text


def test_macos_app_matrix_contract_tool_reports_expected_target_application_set() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["targets"]["ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
        "zoom",
    ]
    assert payload["targets"]["names"] == [
        "FaceTime",
        "Google Meet",
        "OBS",
        "QuickTime",
        "Teams",
        "Zoom",
    ]
    assert payload["manual_results"]["ids"] == payload["targets"]["ids"]
    assert payload["example_template"]["ids"] == payload["targets"]["ids"]
    assert payload["acceptance"]["expected_app_count"] == 6
    assert payload["acceptance"]["expected_app_ids"] == payload["targets"]["ids"]
    assert payload["example_template"]["shape_complete"] is True
    assert payload["example_template"]["check_lists_present"] is True
    assert payload["example_template"]["step_lists_present"] is True
    assert payload["example_template"]["evidence_shape_complete"] is True
    assert payload["consistency"]["target_ids_complete"] is True
    assert payload["consistency"]["manual_result_ids_match_targets"] is True
    assert payload["consistency"]["example_template_ids_match_targets"] is True
    assert payload["consistency"]["example_template_fields_complete"] is True
    assert payload["consistency"]["example_template_checks_present"] is True
    assert payload["consistency"]["example_template_steps_present"] is True
    assert payload["consistency"]["example_template_evidence_shape_complete"] is True
    assert payload["consistency"]["acceptance_expected_app_ids_match_targets"] is True
    assert payload["consistency"]["acceptance_expected_app_count_matches_targets"] is True
    assert payload["consistency"]["smoke_uses_shared_targets"] is True
    assert payload["consistency"]["validation_report_uses_shared_targets"] is True
    assert payload["consistency"]["validation_session_exports_target_identity_fields"] is True
    assert payload["consistency"]["validation_session_summary_surfaces_target_identity_fields"] is True
    assert payload["consistency"]["all_checks_passed"] is True
