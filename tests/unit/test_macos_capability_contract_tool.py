# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS capability contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_capability_contract.py"


def test_macos_capability_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "AKVCFrameProvider.mm" in text
    assert "AKVCCommandSupport.mm" in text
    assert "installer.py" in text
    assert "macos_smoke.py" in text
    assert "macos_install_session.py" in text
    assert "macos_validation_report.py" in text
    assert "macos_validation_session.py" in text
    assert "macos_benchmark.py" in text
    assert "macos_virtual_camera_benchmark.md" in text
    assert "benchmark_matrix_complete" in text
    assert "status_formats_nv12_only" in text
    assert "smoke_surface_preserves_capabilities" in text
    assert "validation_report_surface_preserves_capabilities" in text
    assert "validation_session_surface_preserves_capabilities" in text


def test_macos_capability_contract_tool_reports_consistent_capabilities() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["frame_provider"]["frame_rates"] == [30, 60]
    assert payload["status_payload"]["frame_rates"] == [30, 60]
    assert payload["consistency"]["resolutions_match"] is True
    assert payload["consistency"]["frame_rates_match"] is True
    assert payload["consistency"]["benchmark_matrix_complete"] is True
    assert payload["consistency"]["status_formats_nv12_only"] is True
    assert payload["installer_surface"]["status_has_supported_formats_field"] is True
    assert payload["installer_surface"]["parses_supported_frame_rates_from_payload"] is True
    assert payload["smoke_surface"]["exports_supported_formats"] is True
    assert payload["install_session_surface"]["exports_supported_frame_rates"] is True
    assert payload["validation_report_surface"]["exports_supported_formats"] is True
    assert payload["validation_session_surface"]["exports_validation_supported_formats"] is True
    assert payload["validation_session_surface"]["exports_effective_supported_frame_rates"] is True
    assert payload["benchmark_doc"]["profiles"] == ["1080p30", "1080p60", "4k30", "4k60", "720p30", "720p60"]
    assert payload["benchmark_doc"]["mentions_1080p60_cpu_target"] is True
    assert payload["consistency"]["installer_surface_preserves_capabilities"] is True
    assert payload["consistency"]["smoke_surface_preserves_capabilities"] is True
    assert payload["consistency"]["install_session_surface_preserves_capabilities"] is True
    assert payload["consistency"]["validation_report_surface_preserves_capabilities"] is True
    assert payload["consistency"]["validation_session_surface_preserves_capabilities"] is True
    assert payload["consistency"]["benchmark_doc_profiles_complete"] is True
    assert payload["consistency"]["all_checks_passed"] is True
