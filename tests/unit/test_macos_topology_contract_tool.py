# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Camera Extension topology contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_topology_contract.py"


def test_macos_topology_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "AKVCProviderSource.h" in text
    assert "AKVCProviderSource.mm" in text
    assert "AKVCDeviceSource.h" in text
    assert "AKVCDeviceSource.mm" in text
    assert "graph_bootstrap_complete" in text
    assert "system_registration_complete" in text
    assert "ipc_wiring_complete" in text
    assert "supports_runtime_device_name_override" in text
    assert "extension_hot_path_bypasses_host" in text


def test_macos_topology_contract_tool_reports_consistent_camera_extension_graph() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["provider"]["default_provider_name"] == "AK Virtual Camera"
    assert payload["provider"]["default_manufacturer"] == "AKVC"
    assert payload["provider"]["default_legacy_device_id"] == "com.akvc.camera.device"
    assert payload["provider"]["supports_runtime_device_name_override"] is True
    assert payload["provider"]["source_stream_localized_name"] == "AKVC Stream"
    assert payload["provider"]["sink_stream_localized_name"] == "AKVC Sink Stream"
    assert payload["provider"]["stream_directions"] == [
        "CMIOExtensionStreamDirectionSource",
        "CMIOExtensionStreamDirectionSink",
    ]
    assert payload["provider"]["stream_clock_types"] == [
        "CMIOExtensionStreamClockTypeHostTime",
        "CMIOExtensionStreamClockTypeHostTime",
    ]
    assert payload["device"]["model"] == "AKVC CMIO Camera Extension"
    assert payload["device"]["default_input_capable"] is True
    assert payload["device"]["default_output_capable"] is False
    assert payload["consistency"]["provider_surface_complete"] is True
    assert payload["consistency"]["device_surface_complete"] is True
    assert payload["consistency"]["graph_bootstrap_complete"] is True
    assert payload["consistency"]["system_registration_complete"] is True
    assert payload["consistency"]["ipc_wiring_complete"] is True
    assert payload["consistency"]["extension_hot_path_bypasses_host"] is True
    assert payload["consistency"]["all_checks_passed"] is True
