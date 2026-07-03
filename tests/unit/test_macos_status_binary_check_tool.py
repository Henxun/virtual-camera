# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS built status-tool checker."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_status_binary_check.py"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_macos_status_binary_check_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "find_macos_status_tool" in text
    assert "AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON" in text
    assert "ipc_probe_path_matches_fixture" in text
    assert "ipc_direct_open_errno_matches_fixture" in text
    assert "consumer_open_failed_errno_13" in text
    assert "producer_open_failed_errno_1" in text
    assert "fixture_cases" in text
    assert "--status-tool" in text
    assert "--output" in text


def test_macos_status_binary_check_tool_reports_expected_fixture_merge(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    output = tmp_path / "status-binary-check.json"

    _write_executable(
        status_tool,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

report = Path(os.environ["AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON"])
report_payload = json.loads(report.read_text(encoding="utf-8"))
observed = report_payload.get("observed", {})
error_parts = []
if report_payload.get("error"):
    error_parts.append(str(report_payload["error"]))
if observed.get("status"):
    error_parts.append(f"probe status={observed.get('status')}")
if observed.get("direct_open_errno") is not None:
    error_parts.append(f"direct_open_errno={observed.get('direct_open_errno')}")
print(json.dumps({
    "state": "install_failed",
    "devices": [],
    "enabled": False,
    "ipc_transport": report_payload.get("transport") or "shared_memory_ringbuffer",
    "ipc_probe_present": True,
    "ipc_ready": False,
    "ipc_environment_blocked": True,
    "ipc_last_error": "; ".join(error_parts),
    "ipc_probe_path": str(report),
    "ipc_direct_open_errno": observed.get("direct_open_errno", 13),
}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--status-tool",
            str(status_tool),
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
    assert payload["status_tool"] == str(status_tool)
    assert payload["payload"]["ipc_probe_present"] is True
    assert payload["payload"]["ipc_ready"] is False
    assert payload["payload"]["ipc_environment_blocked"] is True
    assert payload["payload"]["ipc_direct_open_errno"] == 13
    assert payload["consistency"]["command_succeeded"] is True
    assert payload["consistency"]["ipc_keys_present"] is True
    assert payload["consistency"]["ipc_probe_path_matches_fixture"] is True
    assert payload["consistency"]["ipc_direct_open_errno_matches_fixture"] is True
    assert payload["consistency"]["fixture_case_count"] == 2
    assert payload["consistency"]["all_fixture_cases_passed"] is True
    assert payload["consistency"]["all_checks_passed"] is True
    assert [case["name"] for case in payload["fixture_cases"]] == [
        "consumer_open_failed_errno_13",
        "producer_open_failed_errno_1",
    ]
    consumer_case = payload["fixture_cases"][0]
    producer_case = payload["fixture_cases"][1]
    assert consumer_case["consistency"]["ipc_direct_open_errno_matches_fixture"] is True
    assert consumer_case["consistency"]["ipc_transport_matches_fixture"] is True
    assert producer_case["payload"]["ipc_direct_open_errno"] == 1
    assert producer_case["payload"]["ipc_transport"] == "iosurface_ring"
    assert producer_case["consistency"]["ipc_last_error_mentions_fixture"] is True
