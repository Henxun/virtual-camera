# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS signing pipeline contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_signing_pipeline_contract.py"


def test_macos_signing_pipeline_contract_tool_exists_and_references_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "sign_app.sh" in text
    assert "build_pkg.sh" in text
    assert "notarize.sh" in text
    assert "staple.sh" in text
    assert "macos_release_diagnostics.py" in text
    assert "macos_validation_report.py" in text
    assert "sign_app_signs_extension_then_app_and_assesses_result" in text
    assert "build_pkg_optionally_signs_pkg_and_checks_signature" in text
    assert "notarize_rejects_unsigned_pkg_before_submit" in text
    assert "staple_runs_signature_check_stapler_and_spctl" in text
    assert "sign_app_checks_command_tools" in text
    assert "sign_app_checks_direct_sender_library" in text
    assert "sign_app_can_fallback_when_timestamp_unavailable" in text
    assert "sign_app_replaces_signed_outputs_atomically" in text
    assert "sign_app_verifies_final_outputs_after_replace" in text
    assert "sign_app_removes_stale_provisioning_profiles_when_unset" in text
    assert "sign_app_signs_direct_sender_library" in text
    assert "build_pkg_can_auto_detect_productsign_identity" in text
    assert "signs_all_command_tools" in text
    assert "signs_direct_sender_library" in text
    assert "notarize_submits_app_archive_and_pkg" in text
    assert "release_app_gatekeeper_accepted" in text
    assert "release_app_stapled" in text
    assert "release_pkg_gatekeeper_accepted" in text
    assert "release_pkg_stapled" in text
    assert "validation_report_surfaces_release_command_tools_signed" in text
    assert "validation_report_surfaces_release_pkg_signed" in text
    assert "--output" in text


def test_macos_signing_pipeline_contract_tool_reports_expected_signing_pipeline(
    tmp_path,
) -> None:
    output = tmp_path / "macos-signing-pipeline-contract.json"

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

    assert payload["surface"]["sign_app_checks_extension_bundle"] is True
    assert payload["surface"]["sign_app_checks_command_tools"] is True
    assert payload["surface"]["sign_app_checks_direct_sender_library"] is True
    assert payload["surface"]["sign_app_can_auto_detect_sign_identity"] is True
    assert payload["surface"]["sign_app_can_fallback_when_timestamp_unavailable"] is True
    assert payload["surface"]["sign_app_replaces_signed_outputs_atomically"] is True
    assert payload["surface"]["sign_app_verifies_final_outputs_after_replace"] is True
    assert payload["surface"]["sign_app_removes_stale_provisioning_profiles_when_unset"] is True
    assert payload["surface"]["sign_app_signs_extension_before_app"] is True
    assert payload["surface"]["sign_app_signs_command_tools"] is True
    assert payload["surface"]["sign_app_signs_direct_sender_library"] is True
    assert payload["surface"]["sign_app_verifies_extension_and_app"] is True
    assert payload["surface"]["sign_app_runs_spctl_assessment"] is True
    assert payload["surface"]["build_pkg_can_auto_detect_productsign_identity"] is True
    assert payload["surface"]["build_pkg_optionally_runs_productsign"] is True
    assert payload["surface"]["build_pkg_runs_pkgutil_signature_probe"] is True
    assert payload["surface"]["build_pkg_disables_appledouble_metadata"] is True
    assert payload["surface"]["build_pkg_uses_root_payload_not_component"] is True
    assert payload["surface"]["build_pkg_rebuilds_payload_and_bom"] is True
    assert payload["surface"]["notarize_requires_notary_profile"] is True
    assert payload["surface"]["notarize_supports_app_archive_submission"] is True
    assert payload["surface"]["notarize_rejects_unsigned_pkg"] is True
    assert payload["surface"]["notarize_uses_notarytool_submit_wait"] is True
    assert payload["surface"]["staple_supports_app_bundle"] is True
    assert payload["surface"]["staple_runs_pkgutil_check"] is True
    assert payload["surface"]["staple_runs_spctl_app_assessment"] is True
    assert payload["surface"]["staple_runs_stapler_staple_and_validate"] is True
    assert payload["surface"]["staple_runs_spctl_install_assessment"] is True
    assert payload["surface"]["release_diagnostics_exports_signing_summary"] is True
    assert payload["surface"]["validation_report_exports_release_signing_summary"] is True

    cases = {item["name"]: item for item in payload["script_cases"]}
    assert cases["sign_app_signs_extension_then_app_and_assesses_result"]["actual"] == {
        "returncode": 0,
        "signs_extension": True,
        "signs_embedded_extension": True,
        "signs_all_command_tools": True,
        "signs_direct_sender_library": True,
        "signs_app": True,
        "signs_extension_before_app": True,
        "assesses_app": True,
    }
    assert cases["sign_app_clears_stale_provisioning_profiles_when_profiles_are_unset"]["actual"] == {
        "returncode": 0,
        "app_profile_removed": True,
        "embedded_extension_profile_removed": True,
        "top_level_extension_profile_removed": True,
    }
    assert cases["build_pkg_optionally_signs_pkg_and_checks_signature"]["actual"] == {
        "returncode": 0,
        "productsign_invoked": True,
        "pkgbuild_uses_root": True,
        "payload_repack_invoked": True,
        "pkgutil_checked_signature": True,
        "final_pkg_exists": True,
    }
    assert cases["notarize_rejects_unsigned_pkg_before_submit"]["actual"] == {
        "returncode": 2,
        "rejects_unsigned_pkg": True,
        "notary_submit_skipped": True,
    }
    assert cases["notarize_submits_app_archive_and_pkg"]["actual"] == {
        "returncode": 0,
        "submitted_app_archive": True,
        "submitted_pkg": True,
        "submit_count": 2,
    }
    assert cases["staple_runs_signature_check_stapler_and_spctl"]["actual"] == {
        "returncode": 0,
        "stapler_staple_app_invoked": True,
        "stapler_validate_app_invoked": True,
        "spctl_app_assessment_invoked": True,
        "pkgutil_checked_signature": True,
        "stapler_staple_invoked": True,
        "stapler_validate_invoked": True,
        "spctl_install_assessment_invoked": True,
    }

    assert payload["release_surface_case"]["release_tool_has_pkg_signed_parser"] is True
    assert payload["release_surface_case"]["validation_report_uses_build_summary"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_app_signed"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_app_gatekeeper_accepted"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_app_stapled"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_extension_signed"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_command_tools_signed"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_pkg_signed"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_pkg_gatekeeper_accepted"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_release_pkg_stapled"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_bundle_id_expected"] is True
    assert payload["release_surface_case"]["validation_report_surfaces_minimum_system_version_expected"] is True

    assert payload["consistency"]["surface_complete"] is True
    assert payload["consistency"]["script_cases_match_expected"] is True
    assert payload["consistency"]["release_surface_case_complete"] is True
    assert payload["consistency"]["all_checks_passed"] is True
