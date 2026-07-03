# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Python entrypoints contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_entrypoints_contract.py"


def test_macos_entrypoints_contract_tool_exists_and_references_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "pyside6_virtual_camera_demo.py" in text
    assert "macos_direct_push_demo.py" in text
    assert "akvc_cli" in text
    assert "akvc_app" in text
    assert "VirtualCamera" in text
    assert "inspect_installation" in text
    assert "stream_capabilities" in text
    assert "pyvirtualcam" in text
    assert "evaluate_demo_case" in text
    assert "evaluate_direct_push_demo_case" in text
    assert "evaluate_cli_snapshot_case" in text
    assert "evaluate_desktop_snapshot_case" in text
    assert "--output" in text


def test_macos_entrypoints_contract_tool_reports_unified_sdk_entrypoints(
    tmp_path,
) -> None:
    output = tmp_path / "macos-entrypoints-contract.json"

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

    assert payload["surface"]["demo_uses_sdk_virtual_camera"] is True
    assert payload["surface"]["demo_avoids_macos_specific_camera_import"] is True
    assert payload["surface"]["demo_avoids_pyvirtualcam_reference"] is True
    assert payload["surface"]["demo_prefers_sdk_streamer_factory"] is True
    assert payload["surface"]["demo_prefers_sdk_latest_provider_factory"] is True
    assert payload["surface"]["demo_uses_sdk_widget_push"] is True
    assert payload["surface"]["demo_uses_sdk_screen_push"] is True
    assert payload["surface"]["direct_push_demo_uses_sdk_virtual_camera"] is True
    assert payload["surface"]["direct_push_demo_avoids_macos_specific_camera_import"] is True
    assert payload["surface"]["direct_push_demo_avoids_pyvirtualcam_reference"] is True
    assert payload["surface"]["direct_push_demo_uses_push_frame"] is True
    assert payload["surface"]["direct_push_demo_declares_direct_push_mode"] is True
    assert payload["surface"]["cli_uses_sdk_virtual_camera"] is True
    assert payload["surface"]["cli_prefers_installation_snapshot"] is True
    assert payload["surface"]["cli_uses_install_extension_result"] is True
    assert payload["surface"]["cli_uses_sync_ipc_configuration_result"] is True
    assert payload["surface"]["desktop_uses_sdk_virtual_camera"] is True
    assert payload["surface"]["desktop_prefers_installation_snapshot"] is True
    assert payload["surface"]["desktop_uses_stream_capabilities"] is True
    assert payload["surface"]["desktop_avoids_macos_specific_camera_import"] is True
    assert payload["surface"]["desktop_avoids_pyvirtualcam_reference"] is True

    assert payload["demo_case"] == {
        "camera_started_with_name": True,
        "camera_closed_after_run": True,
        "demo_uses_sdk_streamer_factory": True,
        "demo_uses_sdk_widget_push": True,
        "demo_uses_sdk_screen_push": True,
        "demo_uses_sdk_latest_provider_factory": True,
        "streamer_started_provider_mode": True,
        "streamer_stopped_after_run": True,
        "report_keeps_consumer_count": True,
        "report_keeps_frame_source_kind": True,
    }
    assert payload["direct_push_demo_case"] == {
        "camera_started_with_name": True,
        "camera_closed_after_run": True,
        "push_frame_called_for_each_requested_frame": True,
        "report_declares_direct_push_mode": True,
        "report_declares_push_frame_entrypoint": True,
        "report_marks_sdk_direct_push_used": True,
        "report_keeps_backend_name": True,
        "report_keeps_using_direct_sender": True,
        "report_keeps_consumer_count": True,
        "report_keeps_requested_frame_count": True,
    }
    assert payload["cli_case"] == {
        "status_command_succeeded": True,
        "status_prefers_snapshot": True,
        "status_output_contains_phase": True,
        "status_output_contains_ipc_transport": True,
    }
    assert payload["desktop_case"] == {
        "desktop_prefers_snapshot": True,
        "desktop_reads_stream_capabilities": True,
        "desktop_status_ready": True,
        "desktop_status_has_formats": True,
    }

    assert payload["consistency"]["surface_complete"] is True
    assert payload["consistency"]["demo_case_complete"] is True
    assert payload["consistency"]["direct_push_demo_case_complete"] is True
    assert payload["consistency"]["cli_case_complete"] is True
    assert payload["consistency"]["desktop_case_complete"] is True
    assert payload["consistency"]["all_checks_passed"] is True
