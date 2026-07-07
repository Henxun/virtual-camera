# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Camera Extension stream contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_stream_contract.py"


def test_macos_stream_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "AKVCFrameProvider.h" in text
    assert "AKVCFrameProvider.mm" in text
    assert "AKVCStreamSource.h" in text
    assert "AKVCStreamSource.mm" in text
    assert "AKVCSinkStreamSource.h" in text
    assert "AKVCSinkStreamSource.mm" in text
    assert "placeholder_on_no_producer_only" in text
    assert "drop_statuses_match_expected" in text
    assert "shared_memory_reload_supported" in text
    assert "sink_stream_consumes_client_buffers" in text


def test_macos_stream_contract_tool_reports_consistent_stream_behavior() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["frame_provider"]["supported_frame_rates"] == [30, 60]
    assert payload["frame_provider"]["supported_resolutions"] == [
        {"width": 1280, "height": 720},
        {"width": 1920, "height": 1080},
        {"width": 3840, "height": 2160},
    ]
    assert payload["frame_provider"]["placeholder_fill"] == {"y": 16, "uv": 128}
    assert payload["stream_source"]["drop_statuses"] == ["error", "timed_out", "torn"]
    assert payload["stream_source"]["placeholder_statuses"] == ["no_producer"]
    assert payload["frame_provider"]["reloads_shared_memory_name_from_descriptor"] is True
    assert payload["frame_provider"]["closes_reader_on_shared_memory_name_change"] is True
    assert payload["frame_provider"]["reload_change_marks_discontinuity"] is True
    assert payload["sink_stream"]["available_properties"] == sorted([
        "CMIOExtensionPropertyStreamActiveFormatIndex",
        "CMIOExtensionPropertyStreamFrameDuration",
        "CMIOExtensionPropertyStreamMaxFrameDuration",
        "CMIOExtensionPropertyStreamSinkBufferQueueSize",
        "CMIOExtensionPropertyStreamSinkBuffersRequiredForStartup",
        "CMIOExtensionPropertyStreamSinkBufferUnderrunCount",
        "CMIOExtensionPropertyStreamSinkEndOfData",
    ])
    assert payload["consistency"]["status_enum_complete"] is True
    assert payload["consistency"]["placeholder_on_no_producer_only"] is True
    assert payload["consistency"]["drop_statuses_match_expected"] is True
    assert payload["consistency"]["shared_memory_reload_supported"] is True
    assert payload["consistency"]["sink_stream_consumes_client_buffers"] is True
    assert payload["consistency"]["property_surface_complete"] is True
    assert payload["consistency"]["all_checks_passed"] is True
