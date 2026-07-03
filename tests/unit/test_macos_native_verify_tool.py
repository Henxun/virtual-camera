# SPDX-License-Identifier: Apache-2.0
"""Checks for the native verification helper."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macos_native_verify_tool_exists_and_covers_native_checks() -> None:
    script = ROOT / "tools" / "macos_native_verify.py"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "plutil" in text
    assert "clang++" in text
    assert "macos_build_contract.py" in text
    assert "macos_distribution_contract.py" in text
    assert "macos_ci_artifact_contract.py" in text
    assert "macos_delivery_gate_contract.py" in text
    assert "macos_signing_pipeline_contract.py" in text
    assert "macos_capability_contract.py" in text
    assert "macos_topology_contract.py" in text
    assert "macos_readiness_contract.py" in text
    assert "macos_status_contract.py" in text
    assert "macos_validation_session_contract.py" in text
    assert "macos_validation_session_acceptance_contract.py" in text
    assert "macos_validation_session_summary_contract.py" in text
    assert "macos_framebus_contract.py" in text
    assert "macos_entrypoints_contract.py" in text
    assert "macos_sdk_contract.py" in text
    assert "macos_stream_contract.py" in text
    assert "framebus_posix.c" in text
    assert "framebus_consumer_probe.c" in text
    assert "AKVCCommandSupport.mm" in text
    assert "AKVCSystemExtensionSupport.mm" in text
    assert "akvc_macos_status.mm" in text
    assert "akvc_macos_list_devices.mm" in text
    assert "akvc_macos_sync_ipc.mm" in text
