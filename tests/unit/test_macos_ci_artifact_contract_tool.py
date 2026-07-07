# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS CI artifact publishing contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_ci_artifact_contract.py"


def test_macos_ci_artifact_contract_tool_references_required_surfaces() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert ".github/workflows/macos.yml" in text
    assert "jenkins/macos.Jenkinsfile" in text
    assert "actions/upload-artifact@v4" in text
    assert "archiveArtifacts" in text
    assert "VirtualCamera.pkg" in text
    assert "VirtualCamera.dmg" in text
    assert "VirtualCamera.zip" in text
    assert "build/macos/benchmark.json" in text
    assert "REQUIRED_BENCHMARK_COMMAND_FRAGMENTS" in text
    assert "runs_benchmark_smoke" in text
    assert "akvc-macos-list-devices" in text
    assert "list-devices-binary-check.json" in text
    assert "session-summary.md" in text
    assert "manual-results.template.json" in text
    assert "--run-list-devices-binary-check" in text


def test_macos_ci_artifact_contract_tool_reports_complete_artifact_sets() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["consistency"]["all_checks_passed"] is True
    assert payload["github"]["uses_upload_artifact"] is True
    assert payload["github"]["archives_release_artifacts"] is True
    assert payload["github"]["archives_runtime_artifacts"] is True
    assert payload["github"]["archives_validation_artifacts"] is True
    assert payload["github"]["artifact_presence"]["build/macos/benchmark.json"] is True
    assert payload["github"]["runs_benchmark_smoke"] is True
    assert payload["github"]["benchmark_command_presence"]["tools/macos_benchmark.py"] is True
    assert payload["github"]["benchmark_command_presence"]["--output build/macos/benchmark.json"] is True
    assert payload["github"]["runs_validation_artifact_replay"] is True
    assert payload["github"]["renders_session_summary"] is True
    assert payload["github"]["runs_list_devices_binary_check"] is True
    assert payload["jenkins"]["uses_archive_artifacts"] is True
    assert payload["jenkins"]["archives_release_artifacts"] is True
    assert payload["jenkins"]["archives_runtime_artifacts"] is True
    assert payload["jenkins"]["archives_validation_artifacts"] is True
    assert payload["jenkins"]["artifact_presence"]["build/macos/benchmark.json"] is True
    assert payload["jenkins"]["runs_benchmark_smoke"] is True
    assert payload["jenkins"]["benchmark_command_presence"]["tools/macos_benchmark.py"] is True
    assert payload["jenkins"]["benchmark_command_presence"]["--output build/macos/benchmark.json"] is True
    assert payload["jenkins"]["runs_validation_artifact_replay"] is True
    assert payload["jenkins"]["renders_session_summary"] is True
    assert payload["jenkins"]["runs_list_devices_binary_check"] is True
    assert payload["consistency"]["github_and_jenkins_archive_same_required_artifacts"] is True
