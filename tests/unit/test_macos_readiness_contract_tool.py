# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS readiness contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_readiness_contract.py"


def test_macos_readiness_contract_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "ExtensionReadiness" in text
    assert "infer_extension_phase" in text
    assert "evaluate_extension_readiness" in text
    assert "approval_overrides_stale_ipc" in text
    assert "stale_ipc_does_not_override_not_installed" in text
    assert "ipc_environment_blocked" in text
    assert "device_not_visible" in text
    assert "--output" in text


def test_macos_readiness_contract_tool_reports_expected_case_outcomes(tmp_path) -> None:
    output = tmp_path / "readiness-contract.json"

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
    assert payload["consistency"]["phase_cases_match_expected"] is True
    assert payload["consistency"]["readiness_cases_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True

    phase_cases = {item["name"]: item for item in payload["phase_cases"]}
    assert phase_cases["visible_device"]["actual_phase"] == "installed_visible"
    assert phase_cases["pending_approval"]["actual_phase"] == "pending_approval"
    assert phase_cases["enabled_without_device"]["actual_phase"] == "timeout_waiting_for_device"

    readiness_cases = {item["name"]: item for item in payload["readiness_cases"]}
    assert readiness_cases["ready_visible_device"]["actual"]["blocker_code"] == "ready"
    assert readiness_cases["approval_overrides_stale_ipc"]["actual"]["blocker_code"] == "approval_required"
    assert readiness_cases["stale_ipc_does_not_override_not_installed"]["actual"]["blocker_code"] == "not_installed"
    assert readiness_cases["device_not_visible"]["actual"]["blocker_code"] == "device_not_visible"
    assert readiness_cases["ipc_environment_blocked"]["actual"]["blocker_code"] == "ipc_environment_blocked"
    assert readiness_cases["ipc_environment_blocked"]["actual"]["verification_targets_ready"] is True
    assert readiness_cases["ipc_not_ready"]["actual"]["blocker_code"] == "ipc_not_ready"
    assert readiness_cases["package_install_failed"]["actual"]["blocker_code"] == "package_install_failed"
    assert readiness_cases["generic_install_failed"]["actual"]["blocker_code"] == "install_failed"
