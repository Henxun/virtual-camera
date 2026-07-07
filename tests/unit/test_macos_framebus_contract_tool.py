# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Frame Bus contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_framebus_contract.py"


def test_macos_framebus_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "akvc_protocol.h" in text
    assert "akvc_errors.h" in text
    assert "framebus_posix.c" in text
    assert "macos_shm.py" in text
    assert "macos_ipc.cpp" in text
    assert "AKVCCommandSupport.mm" in text
    assert "DemoControlService.mm" in text
    assert "ring_control_size_match" in text
    assert "frame_header_size_match" in text
    assert "consumer_count_tracking_present" in text
    assert "supports_named_open" in text
    assert "macos_descriptor_env_override_present" in text
    assert "host_persists_shm_override_before_activation" in text


def test_macos_framebus_contract_tool_reports_consistent_protocol() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["c_protocol"]["posix_shm_name"] == "/akvc-frames-v1"
    assert payload["python_protocol"]["ring_control_size"] == 128
    assert payload["python_protocol"]["frame_header_size"] == 80
    assert payload["consistency"]["magic_match"] is True
    assert payload["consistency"]["schema_version_match"] is True
    assert payload["consistency"]["default_slot_size_match"] is True
    assert payload["consistency"]["posix_shm_name_match"] is True
    assert payload["consistency"]["ring_control_size_match"] is True
    assert payload["consistency"]["frame_header_size_match"] is True
    assert payload["consistency"]["posix_consumer_checks_core_schema"] is True
    assert payload["consistency"]["consumer_count_tracking_present"] is True
    assert payload["consistency"]["posix_header_exports_core_api"] is True
    assert payload["macos_descriptor"]["exports_app_group_identifier_macro"] is True
    assert payload["macos_descriptor"]["exports_shared_state_dir_env_macro"] is True
    assert payload["macos_descriptor"]["exports_shared_state_dir_suffix_macro"] is True
    assert payload["macos_descriptor"]["exports_shm_name_env_macro"] is True
    assert payload["macos_descriptor"]["exports_shm_name_file_env_macro"] is True
    assert payload["macos_descriptor"]["reads_shm_name_env_override"] is True
    assert payload["macos_descriptor"]["reads_shm_name_file_env_override"] is True
    assert payload["macos_descriptor"]["reads_shared_state_dir_env_override"] is True
    assert payload["macos_descriptor"]["falls_back_to_private_tmp_shared_state_dir"] is True
    assert payload["macos_descriptor"]["reads_shm_name_from_file"] is True
    assert payload["host_persistence"]["exports_persistence_function"] is True
    assert payload["host_persistence"]["reads_host_shm_name_env"] is True
    assert payload["host_persistence"]["reads_host_shm_name_file_env"] is True
    assert payload["host_persistence"]["uses_default_shared_state_destination"] is True
    assert payload["host_persistence"]["creates_parent_directory"] is True
    assert payload["host_persistence"]["persists_utf8_newline_file"] is True
    assert payload["host_persistence"]["activation_path_persists_before_request"] is True
    assert payload["consistency"]["macos_descriptor_env_override_present"] is True
    assert payload["consistency"]["host_persists_shm_override_before_activation"] is True
    assert payload["consistency"]["all_checks_passed"] is True
