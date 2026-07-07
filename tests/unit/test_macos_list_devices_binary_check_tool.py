# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS built list-devices tool checker."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_list_devices_binary_check.py"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_macos_list_devices_binary_check_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "find_macos_list_devices_tool" in text
    assert "AKVC_DEVICE_PREFIX" in text
    assert "read_camera_name_override" in text
    assert "default_prefix" in text
    assert "override_prefix_no_match" in text
    assert "filtered_subset_of_all_devices" in text
    assert "filtered_devices_match_prefix" in text
    assert "override_prefix_returns_empty_devices" in text
    assert "--list-devices-tool" in text
    assert "--expected-prefix" in text
    assert "--output" in text


def test_macos_list_devices_binary_check_tool_reports_expected_probe_behavior(tmp_path) -> None:
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    output = tmp_path / "list-devices-binary-check.json"

    _write_executable(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
import os

prefix = os.environ.get("AKVC_DEVICE_PREFIX", "AK Virtual Camera")
all_devices = [
    "FaceTime HD Camera",
    "AK Virtual Camera",
    "AK Virtual Camera 4K",
]
devices = [name for name in all_devices if name.startswith(prefix)]
print(json.dumps({
    "devices": devices,
    "all_devices": all_devices,
    "device_prefix": prefix,
}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--list-devices-tool",
            str(list_devices_tool),
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
    assert payload["list_devices_tool"] == str(list_devices_tool)
    assert payload["expected_prefix"] == "AK Virtual Camera"
    assert payload["payload"]["device_prefix"] == "AK Virtual Camera"
    assert payload["payload"]["devices"] == ["AK Virtual Camera", "AK Virtual Camera 4K"]
    assert payload["payload"]["all_devices"] == [
        "FaceTime HD Camera",
        "AK Virtual Camera",
        "AK Virtual Camera 4K",
    ]
    assert payload["consistency"]["command_succeeded"] is True
    assert payload["consistency"]["json_shape_valid"] is True
    assert payload["consistency"]["default_prefix_case_passed"] is True
    assert payload["consistency"]["override_prefix_case_passed"] is True
    assert payload["consistency"]["all_checks_passed"] is True
    assert [case["name"] for case in payload["probe_cases"]] == [
        "default_prefix",
        "override_prefix_no_match",
    ]
    default_case = payload["probe_cases"][0]
    override_case = payload["probe_cases"][1]
    assert default_case["consistency"]["filtered_subset_of_all_devices"] is True
    assert default_case["consistency"]["filtered_devices_match_prefix"] is True
    assert override_case["payload"]["device_prefix"].startswith("__AKVC_BINARY_CHECK_NO_MATCH__")
    assert override_case["payload"]["devices"] == []
    assert override_case["consistency"]["override_prefix_returns_empty_devices"] is True


def test_macos_list_devices_binary_check_tool_honors_expected_prefix_override(tmp_path) -> None:
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    output = tmp_path / "list-devices-binary-check.json"

    _write_executable(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
import os

prefix = os.environ.get("AKVC_DEVICE_PREFIX", "AKVC Demo")
all_devices = [
    "FaceTime HD Camera",
    "AKVC Demo",
    "AKVC Demo 4K",
]
devices = [name for name in all_devices if name.startswith(prefix)]
print(json.dumps({
    "devices": devices,
    "all_devices": all_devices,
    "device_prefix": prefix,
}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--list-devices-tool",
            str(list_devices_tool),
            "--expected-prefix",
            "AKVC Demo",
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
    assert payload["expected_prefix"] == "AKVC Demo"
    assert payload["payload"]["device_prefix"] == "AKVC Demo"
    assert payload["payload"]["devices"] == ["AKVC Demo", "AKVC Demo 4K"]
    assert payload["consistency"]["default_prefix_case_passed"] is True
    assert payload["consistency"]["override_prefix_case_passed"] is True
    assert payload["consistency"]["all_checks_passed"] is True
