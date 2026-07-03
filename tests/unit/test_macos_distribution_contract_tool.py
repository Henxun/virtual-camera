# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS distribution/runtime contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_distribution_contract.py"


def test_macos_distribution_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "make.py" in text
    assert "runtime.py" in text
    assert "macos_validation_report.py" in text
    assert "macos_release_diagnostics.py" in text
    assert "akvc-macos-sync-ipc" in text
    assert "libakvc-macos-direct-sender.dylib" in text
    assert "VirtualCamera.pkg" in text
    assert "sync_runtime_case_passed" in text
    assert "runtime_discovery_case_passed" in text
    assert "validation_report_runtime_case_passed" in text
    assert "release_diagnostics_case_passed" in text
    assert "--output" in text
    assert "pkg_payload_appledouble_clean" in text


def test_macos_distribution_contract_tool_reports_consistent_distribution_surface(
    tmp_path,
) -> None:
    output = tmp_path / "macos-distribution-contract.json"

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

    assert payload["make_runtime_surface"]["syncs_sync_ipc_tool"] is True
    assert payload["make_runtime_surface"]["syncs_direct_sender_library"] is True
    assert payload["make_runtime_surface"]["syncs_pkg_when_required"] is True
    assert payload["runtime_locator_surface"]["defines_find_macos_sync_ipc_tool"] is True
    assert payload["runtime_locator_surface"]["defines_find_macos_direct_sender_library"] is True
    assert payload["runtime_locator_surface"]["uses_packaged_pkg_resource"] is True
    assert payload["validation_report_runtime_surface"]["tracks_packaged_sync_ipc_asset"] is True
    assert payload["validation_report_runtime_surface"]["tracks_packaged_direct_sender_asset"] is True
    assert payload["validation_report_runtime_surface"]["exports_packaged_pkg_present"] is True
    assert payload["release_diagnostics_surface"]["exports_sync_ipc_universal2_summary"] is True
    assert payload["release_diagnostics_surface"]["exports_pkg_payload_appledouble_clean_summary"] is True
    assert payload["sync_runtime_case"]["all_synced"] is True
    assert payload["runtime_discovery_case"]["packaged_assets_discoverable"] is True
    assert payload["validation_report_runtime_case"]["summary"]["sync_ipc_tool_resolved"] is True
    assert payload["validation_report_runtime_case"]["summary"]["direct_sender_library_resolved"] is True
    assert payload["validation_report_runtime_case"]["summary"]["packaged_tools_present"] is True
    assert payload["validation_report_runtime_case"]["summary"]["packaged_pkg_present"] is True
    assert payload["release_diagnostics_case"]["summary"]["sync_ipc_tool_exists"] is True
    assert payload["release_diagnostics_case"]["summary"]["sync_ipc_tool_signed"] is True
    assert payload["release_diagnostics_case"]["summary"]["sync_ipc_tool_universal2_ready"] is True
    assert payload["release_diagnostics_case"]["summary"]["pkg_payload_appledouble_clean"] is True
    assert payload["release_diagnostics_case"]["summary"]["release_artifacts_present"] is True
    assert payload["consistency"]["make_runtime_surface_complete"] is True
    assert payload["consistency"]["runtime_locator_surface_complete"] is True
    assert payload["consistency"]["validation_report_runtime_surface_complete"] is True
    assert payload["consistency"]["release_diagnostics_surface_complete"] is True
    assert payload["consistency"]["sync_runtime_case_passed"] is True
    assert payload["consistency"]["runtime_discovery_case_passed"] is True
    assert payload["consistency"]["validation_report_runtime_case_passed"] is True
    assert payload["consistency"]["release_diagnostics_case_passed"] is True
    assert payload["consistency"]["all_checks_passed"] is True
