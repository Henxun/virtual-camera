# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Python SDK contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_sdk_contract.py"


def test_macos_sdk_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "TOP_LEVEL_AKVC" in text
    assert "SDK_INIT" in text
    assert "SDK_VIRTUAL_CAMERA" in text
    assert "MACOS_VIRTUAL_CAMERA" in text
    assert '"virtual_camera.py"' in text
    assert '"__init__.py"' in text
    assert "shared_lifecycle_methods_complete" in text
    assert "inspect_installation_signature_match" in text
    assert "ipc_descriptor_signature_match" in text
    assert "stream_capabilities_signature_match" in text
    assert "readiness_signature_match" in text
    assert "status_signature_match" in text
    assert "direct_only" in text
    assert "direct_sender_library" in text
    assert "direct_sender_exports_present" in text
    assert "helper_exe" in text
    assert "host_bundle" in text
    assert "host_executable" in text
    assert "send_widget_signature_match" in text
    assert "create_pyside6_bridge_signature_match" in text
    assert "create_pyside6_streamer_signature_match" in text
    assert "direct_sender_readiness_signature_match" in text
    assert "sync_ipc_configuration_signature_match" in text
    assert "context_manager_complete" in text


def test_macos_sdk_contract_tool_reports_aligned_python_api() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["top_level_akvc"]["__all__"] == [
        "VirtualCamera",
        "MacDirectCameraSender",
        "DirectSenderError",
        "create_direct_sender",
        "__version__",
    ]
    assert payload["sdk_init"]["__all__"] == [
        "VirtualCamera",
        "MacDirectCameraSender",
        "DirectSenderError",
        "create_direct_sender",
    ]
    assert payload["virtual_camera"]["shared_methods"] == [
        "close",
        "create_latest_frame_provider",
        "create_pyside6_bridge",
        "create_pyside6_streamer",
        "direct_sender_readiness",
        "enumerate_devices",
        "inspect_installation",
        "install_extension",
        "install_extension_result",
        "ipc_descriptor",
        "is_installed",
        "push_frame",
        "readiness",
        "send",
        "send_image",
        "send_pixmap",
        "send_screen",
        "send_widget",
        "shutdown",
        "start",
        "status",
        "stop",
        "stream_capabilities",
        "sync_ipc_configuration",
        "sync_ipc_configuration_result",
        "uninstall_extension",
        "uninstall_extension_result",
    ]
    assert payload["mac_virtual_camera"]["shared_methods"] == payload["virtual_camera"]["shared_methods"]
    assert payload["virtual_camera"]["shared_properties"] == ["consumer_count", "started"]
    assert payload["mac_virtual_camera"]["shared_properties"] == ["consumer_count", "started"]
    assert payload["consistency"]["shared_lifecycle_methods_complete"] is True
    assert payload["consistency"]["shared_pyside6_methods_complete"] is True
    assert payload["consistency"]["shared_installer_methods_complete"] is True
    assert payload["consistency"]["shared_properties_complete"] is True
    assert payload["consistency"]["start_signature_match"] is True
    assert payload["consistency"]["send_signature_match"] is True
    assert payload["consistency"]["send_image_signature_match"] is True
    assert payload["consistency"]["send_pixmap_signature_match"] is True
    assert payload["consistency"]["send_widget_signature_match"] is True
    assert payload["consistency"]["send_screen_signature_match"] is True
    assert payload["consistency"]["create_pyside6_bridge_signature_match"] is True
    assert payload["consistency"]["create_latest_frame_provider_signature_match"] is True
    assert payload["consistency"]["create_pyside6_streamer_signature_match"] is True
    assert payload["consistency"]["enumerate_devices_signature_match"] is True
    assert payload["consistency"]["direct_sender_readiness_signature_match"] is True
    assert payload["consistency"]["status_signature_match"] is True
    assert payload["consistency"]["readiness_signature_match"] is True
    assert payload["consistency"]["inspect_installation_signature_match"] is True
    assert payload["consistency"]["ipc_descriptor_signature_match"] is True
    assert payload["consistency"]["stream_capabilities_signature_match"] is True
    assert payload["consistency"]["is_installed_signature_match"] is True
    assert payload["consistency"]["install_extension_result_signature_match"] is True
    assert payload["consistency"]["install_extension_signature_match"] is True
    assert payload["consistency"]["uninstall_extension_result_signature_match"] is True
    assert payload["consistency"]["uninstall_extension_signature_match"] is True
    assert payload["consistency"]["sync_ipc_configuration_signature_match"] is True
    assert payload["consistency"]["sync_ipc_configuration_result_signature_match"] is True
    assert payload["consistency"]["constructor_shape_aligned"] is True
    assert payload["consistency"]["direct_sender_exports_present"] is True
    assert payload["consistency"]["context_manager_complete"] is True
    assert payload["consistency"]["all_checks_passed"] is True
