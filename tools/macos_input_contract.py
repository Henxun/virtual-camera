# SPDX-License-Identifier: Apache-2.0
"""Python input and PySide6 surface contract checks for macOS work.

This checker keeps the public input matrix and Qt-oriented helper surface
aligned with the documented macOS virtual camera requirements.

Referenced surfaces:
- camera-core/src/akvc/core/frame_input.py
- camera-core/src/akvc/integrations/pyside6.py
- camera-core/src/akvc/sdk/virtual_camera.py
- camera-core/src/akvc/platforms/macos/virtual_camera.py
- tools/pyside6_virtual_camera_demo.py
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FRAME_INPUT = ROOT / "camera-core" / "src" / "akvc" / "core" / "frame_input.py"
PYSIDE6 = ROOT / "camera-core" / "src" / "akvc" / "integrations" / "pyside6.py"
SDK_VIRTUAL_CAMERA = ROOT / "camera-core" / "src" / "akvc" / "sdk" / "virtual_camera.py"
MACOS_VIRTUAL_CAMERA = ROOT / "camera-core" / "src" / "akvc" / "platforms" / "macos" / "virtual_camera.py"
DEMO = ROOT / "tools" / "pyside6_virtual_camera_demo.py"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_public_methods(path: Path, class_name: str) -> list[str]:
    module = ast.parse(_read_text(path), filename=str(path))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return sorted(
                child.name
                for child in node.body
                if isinstance(child, ast.FunctionDef)
                and not child.name.startswith("_")
            )
    raise ValueError(f"class not found: {class_name}")


def parse_frame_input_contract(text: str) -> dict[str, Any]:
    supported = {
        "Frame": "isinstance(frame_input, Frame)" in text,
        "numpy.ndarray": "isinstance(frame_input, np.ndarray)" in text,
        "OpenCV Mat": "OpenCV Mat" in text,
        "QImage": '_looks_like_qimage(frame_input)' in text,
        "QPixmap": "toImage" in text,
    }
    ndarray_shapes = sorted(
        {
            "HxW" if "array.ndim == 2" in text else None,
            "HxWx3" if "array.shape[2] == 3" in text else None,
            "HxWx4" if "array.shape[2] == 4" in text else None,
        }
        - {None}
    )
    has_convert_fallback = "_convert_qimage_to_supported_format(image, prefer_bgra=prefer_bgra)" in text
    supports_bits_fallback = "else image.bits()" in text
    supported_qimage_formats = sorted(
        set(re.findall(r'"Format_([A-Za-z0-9_]+)"', _extract_tuple_block(text, "format_map = (", ")\n\n")))
    )
    return {
        "input_types": [name for name, present in sorted(supported.items()) if present],
        "ndarray_shapes": ndarray_shapes,
        "qimage_convert_fallback": has_convert_fallback,
        "qimage_bits_fallback": supports_bits_fallback,
        "qimage_formats": supported_qimage_formats,
    }


def _extract_tuple_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        end = len(text)
    return text[start:end]


def parse_pyside6_contract(text: str) -> dict[str, Any]:
    bridge_methods = _parse_public_methods(PYSIDE6, "PySide6VirtualCameraBridge")
    streamer_methods = _parse_public_methods(PYSIDE6, "PySide6VirtualCameraStreamer")

    surface = {
        "push_helpers": sorted(
            name
            for name in ("push_qimage", "push_qpixmap", "push_widget", "push_screen")
            if f"def {name}(" in text
        ),
        "provider_helpers": sorted(
            name
            for name in ("LatestFrameProvider", "OpenCVVideoFileProvider")
            if f"class {name}" in text
        ),
        "bridge_methods": sorted(
            name
            for name in bridge_methods
            if name in {"send_image", "send_pixmap", "send_widget", "send_screen"}
        ),
        "streamer_modes": sorted(
            mode
            for mode, method in (
                ("latest-provider", "start_latest_frame_stream"),
                ("provider", "start_provider_stream"),
                ("widget", "start_widget_stream"),
                ("screen", "start_screen_stream"),
                ("video-file", "start_video_file_stream"),
            )
            if method in streamer_methods
        ),
    }
    return surface


def parse_demo_contract(text: str) -> dict[str, Any]:
    match = re.search(
        r'parser\.add_argument\(\s*"--mode",\s*choices=\[([^\]]+)\]',
        text,
        re.S,
    )
    modes = sorted(re.findall(r'"([^"]+)"', match.group(1) if match else ""))
    return {
        "modes": modes,
        "supports_video_path": "--video-path" in text,
        "supports_report_json": "--report-json" in text,
    }


def parse_sdk_entry_contract(text: str) -> dict[str, Any]:
    return {
        "delegates_to_macos_backend": "self._mac_backend.push_frame(frame_input)" in text,
        "windows_path_coerces_frame_input": "_coerce_frame_input(frame_input)" in text,
        "send_aliases_push_frame": "self.push_frame(frame_input)" in text,
        "direct_pyside6_surface_present": all(
            marker in text
            for marker in (
                "def send_image(",
                "def send_pixmap(",
                "def send_widget(",
                "def send_screen(",
                "def create_pyside6_bridge(",
                "def create_latest_frame_provider(",
                "def create_pyside6_streamer(",
            )
        ),
        "direct_pyside6_helpers_wired": all(
            marker in text
            for marker in (
                "return _create_pyside6_bridge(self)",
                "_push_widget(self, widget)",
                "_push_screen(",
                "return _create_latest_frame_provider(repeat_last=repeat_last)",
                "return _create_pyside6_streamer(self, timer_factory=timer_factory)",
            )
        ),
        "installer_surface_present": all(
            marker in text
            for marker in (
                "def enumerate_devices(",
                "def status(",
                "def is_installed(",
                "def install_extension_result(",
                "def install_extension(",
                "def uninstall_extension_result(",
                "def uninstall_extension(",
                "def sync_ipc_configuration_result(",
                "def sync_ipc_configuration(",
            )
        ),
    }


def parse_macos_backend_entry_contract(text: str) -> dict[str, Any]:
    return {
        "coerces_frame_input": "_coerce_frame_input(frame_input)" in text,
        "coerces_direct_sender_frame_input": (
            "_coerce_direct_frame_input(frame_input)" in text
            and "if self._using_direct_sender" in text
        ),
        "send_aliases_push_frame": "self.push_frame(frame_input)" in text,
        "direct_pyside6_surface_present": all(
            marker in text
            for marker in (
                "def send_image(",
                "def send_pixmap(",
                "def send_widget(",
                "def send_screen(",
                "def create_pyside6_bridge(",
                "def create_latest_frame_provider(",
                "def create_pyside6_streamer(",
            )
        ),
        "direct_pyside6_helpers_wired": all(
            marker in text
            for marker in (
                "return _create_pyside6_bridge(self)",
                "_push_widget(self, widget)",
                "_push_screen(",
                "return _create_latest_frame_provider(repeat_last=repeat_last)",
                "return _create_pyside6_streamer(self, timer_factory=timer_factory)",
            )
        ),
        "installer_guard_before_start": (
            "_ensure_ready_to_start(require_ipc_ready=False)" in text
            and "_ensure_ready_to_start(require_ipc_ready=True)" in text
        ),
        "installer_surface_present": all(
            marker in text
            for marker in (
                "def enumerate_devices(",
                "def status(",
                "def is_installed(",
                "def install_extension_result(",
                "def install_extension(",
                "def uninstall_extension_result(",
                "def uninstall_extension(",
                "def sync_ipc_configuration_result(",
                "def sync_ipc_configuration(",
            )
        ),
    }


def evaluate_contract() -> dict[str, Any]:
    frame_input = parse_frame_input_contract(_read_text(FRAME_INPUT))
    pyside6 = parse_pyside6_contract(_read_text(PYSIDE6))
    sdk = parse_sdk_entry_contract(_read_text(SDK_VIRTUAL_CAMERA))
    mac_backend = parse_macos_backend_entry_contract(_read_text(MACOS_VIRTUAL_CAMERA))
    demo = parse_demo_contract(_read_text(DEMO))

    consistency = {
        "input_matrix_complete": frame_input["input_types"]
        == ["Frame", "OpenCV Mat", "QImage", "QPixmap", "numpy.ndarray"]
        and frame_input["ndarray_shapes"] == ["HxW", "HxWx3", "HxWx4"]
        and frame_input["qimage_convert_fallback"] is True
        and frame_input["qimage_bits_fallback"] is True,
        "bridge_surface_complete": pyside6["push_helpers"]
        == ["push_qimage", "push_qpixmap", "push_screen", "push_widget"]
        and pyside6["bridge_methods"]
        == ["send_image", "send_pixmap", "send_screen", "send_widget"],
        "streamer_surface_complete": pyside6["streamer_modes"]
        == ["latest-provider", "provider", "screen", "video-file", "widget"]
        and pyside6["provider_helpers"] == ["LatestFrameProvider", "OpenCVVideoFileProvider"],
        "sdk_entry_surface_complete": all(bool(value) for value in sdk.values()),
        "mac_backend_entry_surface_complete": all(bool(value) for value in mac_backend.values()),
        "demo_modes_complete": demo["modes"]
        == ["image", "latest-provider", "numpy-direct", "pixmap", "provider", "screen", "video-file", "widget"]
        and demo["supports_video_path"] is True
        and demo["supports_report_json"] is True,
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "frame_input": frame_input,
        "pyside6": pyside6,
        "sdk": sdk,
        "mac_backend": mac_backend,
        "demo": demo,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS Python input contract checker")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_contract()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    if not bool(payload["consistency"]["all_checks_passed"]):
        print("macOS Python input contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
