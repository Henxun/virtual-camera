# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Python input/PySide6 contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_input_contract.py"


def test_macos_input_contract_tool_exists_and_references_expected_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "frame_input.py" in text
    assert "integrations/pyside6.py" in text
    assert "sdk/virtual_camera.py" in text
    assert "platforms/macos/virtual_camera.py" in text
    assert "pyside6_virtual_camera_demo.py" in text
    assert "input_matrix_complete" in text
    assert "demo_modes_complete" in text


def test_macos_input_contract_tool_reports_expected_input_surface() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["frame_input"]["input_types"] == [
        "Frame",
        "OpenCV Mat",
        "QImage",
        "QPixmap",
        "numpy.ndarray",
    ]
    assert payload["frame_input"]["ndarray_shapes"] == ["HxW", "HxWx3", "HxWx4"]
    assert payload["frame_input"]["qimage_formats"] == [
        "ARGB32",
        "ARGB32_Premultiplied",
        "Alpha8",
        "BGR888",
        "BGRA8888",
        "BGRA8888_Premultiplied",
        "Grayscale8",
        "Indexed8",
        "RGB32",
        "RGB888",
        "RGBA8888",
        "RGBA8888_Premultiplied",
        "RGBX8888",
    ]
    assert payload["pyside6"]["bridge_methods"] == [
        "send_image",
        "send_pixmap",
        "send_screen",
        "send_widget",
    ]
    assert payload["pyside6"]["streamer_modes"] == [
        "latest-provider",
        "provider",
        "screen",
        "video-file",
        "widget",
    ]
    assert payload["pyside6"]["provider_helpers"] == [
        "LatestFrameProvider",
        "OpenCVVideoFileProvider",
    ]
    assert payload["sdk"]["delegates_to_macos_backend"] is True
    assert payload["sdk"]["windows_path_coerces_frame_input"] is True
    assert payload["sdk"]["send_aliases_push_frame"] is True
    assert payload["sdk"]["direct_pyside6_surface_present"] is True
    assert payload["sdk"]["direct_pyside6_helpers_wired"] is True
    assert payload["sdk"]["installer_surface_present"] is True
    assert payload["mac_backend"]["coerces_frame_input"] is True
    assert payload["mac_backend"]["coerces_direct_sender_frame_input"] is True
    assert payload["mac_backend"]["send_aliases_push_frame"] is True
    assert payload["mac_backend"]["direct_pyside6_surface_present"] is True
    assert payload["mac_backend"]["direct_pyside6_helpers_wired"] is True
    assert payload["mac_backend"]["installer_guard_before_start"] is True
    assert payload["mac_backend"]["installer_surface_present"] is True
    assert payload["demo"]["modes"] == [
        "image",
        "latest-provider",
        "numpy-direct",
        "pixmap",
        "provider",
        "screen",
        "video-file",
        "widget",
    ]
    assert payload["consistency"]["input_matrix_complete"] is True
    assert payload["consistency"]["bridge_surface_complete"] is True
    assert payload["consistency"]["streamer_surface_complete"] is True
    assert payload["consistency"]["sdk_entry_surface_complete"] is True
    assert payload["consistency"]["mac_backend_entry_surface_complete"] is True
    assert payload["consistency"]["demo_modes_complete"] is True
    assert payload["consistency"]["all_checks_passed"] is True
