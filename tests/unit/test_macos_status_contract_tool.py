# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS status/IPC contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_status_contract.py"


def test_macos_status_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "AKVCCommandSupport.mm" in text
    assert "_merge_framebus_roundtrip_status" in text
    assert "AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON" in text
    assert "python_fixture_behaviors_match_expected" in text
    assert "open_failed_errno_13" in text
    assert "producer_open_failed_errno_1" in text
    assert "consistency_marks_environment_blocked" in text


def test_macos_status_contract_tool_reports_consistent_status_behavior() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["native_source"]["reads_roundtrip_env"] is True
    assert payload["native_source"]["treats_errno_13_as_environment_blocked"] is True
    assert payload["consistency"]["native_source_complete"] is True
    assert payload["consistency"]["python_fixture_behaviors_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True
    fixture_names = [item["name"] for item in payload["fixture_cases"]]
    assert fixture_names == [
        "no_report",
        "invalid_report",
        "successful_probe",
        "open_failed_errno_13",
        "producer_open_failed_errno_1",
        "consistency_marks_environment_blocked",
    ]
    blocked_case = next(item for item in payload["fixture_cases"] if item["name"] == "open_failed_errno_13")
    assert blocked_case["actual_python_merge"]["ipc_ready"] is False
    assert blocked_case["actual_python_merge"]["ipc_environment_blocked"] is True
    assert blocked_case["actual_python_merge"]["ipc_direct_open_errno"] == 13
    assert blocked_case["all_keys_match"] is True
    producer_blocked_case = next(
        item for item in payload["fixture_cases"] if item["name"] == "producer_open_failed_errno_1"
    )
    assert producer_blocked_case["actual_python_merge"]["ipc_ready"] is False
    assert producer_blocked_case["actual_python_merge"]["ipc_environment_blocked"] is True
    assert producer_blocked_case["actual_python_merge"]["ipc_direct_open_errno"] == 1
    assert producer_blocked_case["all_keys_match"] is True
