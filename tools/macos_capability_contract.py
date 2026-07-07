# SPDX-License-Identifier: Apache-2.0
"""Consistency checks for the macOS virtual camera capability contract.

This tool keeps the native Camera Extension capabilities, control-bridge status payload,
and benchmark profile matrix aligned around the same resolution / frame-rate
surface so support claims do not silently drift apart.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FRAME_PROVIDER_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCFrameProvider.mm"
COMMAND_SUPPORT_MM = ROOT / "virtualcam" / "macos" / "control_bridge" / "AKVCCommandSupport.mm"
INSTALLER = ROOT / "camera-core" / "src" / "akvc" / "platforms" / "macos" / "installer.py"
SMOKE_TOOL = ROOT / "tools" / "macos_smoke.py"
INSTALL_SESSION_TOOL = ROOT / "tools" / "macos_install_session.py"
VALIDATION_REPORT_TOOL = ROOT / "tools" / "macos_validation_report.py"
VALIDATION_SESSION_TOOL = ROOT / "tools" / "macos_validation_session.py"
BENCHMARK_TOOL = ROOT / "tools" / "macos_benchmark.py"
BENCHMARK_DOC = ROOT / "docs" / "benchmark" / "macos_virtual_camera_benchmark.md"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frame_provider_capabilities(text: str) -> dict[str, Any]:
    resolutions = sorted(
        {
            (int(width), int(height))
            for width, height in re.findall(r"NSMakeSize\((\d+),\s*(\d+)\)", text)
        }
    )
    frame_rates = sorted(
        {
            int(rate)
            for rate in re.findall(r"CMTimeMake\(1,\s*(\d+)\)", text)
        }
    )
    return {
        "resolutions": [
            {"width": width, "height": height}
            for width, height in resolutions
        ],
        "frame_rates": frame_rates,
    }


def parse_status_capabilities(text: str) -> dict[str, Any]:
    formats = re.findall(r'@"(\d+)x(\d+)@([0-9/]+)\s+([A-Z0-9]+)"', text)
    resolutions = sorted(
        {
            (int(width), int(height))
            for width, height, _rates, _pixel_format in formats
        }
    )
    frame_rates = sorted(
        {
            int(rate)
            for rate in re.findall(r"@(\d+)", _extract_supported_frame_rates_block(text))
        }
    )
    format_strings = [
        f"{int(width)}x{int(height)}@{rates} {pixel_format}"
        for width, height, rates, pixel_format in formats
    ]
    return {
        "supported_formats": format_strings,
        "resolutions": [
            {"width": width, "height": height}
            for width, height in resolutions
        ],
        "frame_rates": frame_rates,
    }


def _extract_supported_frame_rates_block(text: str) -> str:
    match = re.search(r'@"supported_frame_rates":\s*@\[(.*?)\]', text, re.DOTALL)
    return match.group(1) if match else ""


def load_benchmark_profiles() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("macos_benchmark_contract", BENCHMARK_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load macOS benchmark tool module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profiles = []
    for item in getattr(module, "DEFAULT_BENCHMARK_PROFILES", {}).values():
        profiles.append(
            {
                "name": str(item["name"]),
                "width": int(item["width"]),
                "height": int(item["height"]),
                "fps": float(item["fps"]),
            }
        )
    profiles.sort(key=lambda item: (item["width"], item["height"], item["fps"]))
    return profiles


def parse_capability_surface(text: str) -> dict[str, Any]:
    return {
        "exports_supported_formats": '"supported_formats"' in text and "supported_formats" in text,
        "exports_supported_frame_rates": '"supported_frame_rates"' in text and "supported_frame_rates" in text,
    }


def parse_validation_session_capability_surface(text: str) -> dict[str, Any]:
    return {
        "reads_validation_status_supported_formats": 'validation_status.get("supported_formats")' in text,
        "reads_validation_status_supported_frame_rates": 'validation_status.get("supported_frame_rates")' in text,
        "reads_smoke_status_supported_formats": 'smoke_status.get("supported_formats")' in text,
        "reads_smoke_status_supported_frame_rates": 'smoke_status.get("supported_frame_rates")' in text,
        "reads_install_session_post_status_supported_formats": 'install_session_post_status.get("supported_formats")' in text,
        "reads_install_session_post_status_supported_frame_rates": 'install_session_post_status.get("supported_frame_rates")' in text,
        "exports_validation_supported_formats": '"validation_supported_formats"' in text,
        "exports_validation_supported_frame_rates": '"validation_supported_frame_rates"' in text,
        "exports_smoke_supported_formats": '"smoke_supported_formats"' in text,
        "exports_smoke_supported_frame_rates": '"smoke_supported_frame_rates"' in text,
        "exports_install_session_supported_formats": '"install_session_supported_formats"' in text,
        "exports_install_session_supported_frame_rates": '"install_session_supported_frame_rates"' in text,
        "exports_effective_supported_formats": '"effective_supported_formats"' in text,
        "exports_effective_supported_frame_rates": '"effective_supported_frame_rates"' in text,
    }


def parse_installer_capability_surface(text: str) -> dict[str, Any]:
    return {
        "status_has_supported_formats_field": "supported_formats: list[str]" in text,
        "status_has_supported_frame_rates_field": "supported_frame_rates: list[int]" in text,
        "parses_supported_formats_from_payload": 'supported_formats=list(payload.get("supported_formats") or [])' in text,
        "parses_supported_frame_rates_from_payload": 'supported_frame_rates=[int(value) for value in (payload.get("supported_frame_rates") or [])]' in text,
    }


def parse_benchmark_doc_contract(
    text: str,
    benchmark_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_text = text.lower()
    profile_names = sorted(
        str(item["name"])
        for item in benchmark_profiles
        if f"`{str(item['name']).lower()}`" in normalized_text
    )
    return {
        "profiles": profile_names,
        "mentions_1080p60_cpu_target": "`1080p60`" in normalized_text and "cpu `<10%`" in normalized_text,
    }


def evaluate_contract() -> dict[str, Any]:
    frame_provider = parse_frame_provider_capabilities(_load_text(FRAME_PROVIDER_MM))
    status_payload = parse_status_capabilities(_load_text(COMMAND_SUPPORT_MM))
    installer_surface = parse_installer_capability_surface(_load_text(INSTALLER))
    smoke_surface = parse_capability_surface(_load_text(SMOKE_TOOL))
    install_session_surface = parse_capability_surface(_load_text(INSTALL_SESSION_TOOL))
    validation_report_surface = parse_capability_surface(_load_text(VALIDATION_REPORT_TOOL))
    validation_session_surface = parse_validation_session_capability_surface(
        _load_text(VALIDATION_SESSION_TOOL)
    )
    benchmark_profiles = load_benchmark_profiles()
    benchmark_doc = parse_benchmark_doc_contract(_load_text(BENCHMARK_DOC), benchmark_profiles)

    native_resolution_set = {
        (int(item["width"]), int(item["height"]))
        for item in frame_provider["resolutions"]
    }
    status_resolution_set = {
        (int(item["width"]), int(item["height"]))
        for item in status_payload["resolutions"]
    }
    native_frame_rate_set = {int(item) for item in frame_provider["frame_rates"]}
    status_frame_rate_set = {int(item) for item in status_payload["frame_rates"]}
    benchmark_triplets = {
        (int(item["width"]), int(item["height"]), int(round(float(item["fps"]))))
        for item in benchmark_profiles
    }
    expected_triplets = {
        (width, height, rate)
        for width, height in native_resolution_set
        for rate in native_frame_rate_set
    }

    consistency = {
        "resolutions_match": native_resolution_set == status_resolution_set,
        "frame_rates_match": native_frame_rate_set == status_frame_rate_set,
        "benchmark_matrix_complete": benchmark_triplets == expected_triplets,
        "status_formats_nv12_only": all(item.endswith("NV12") for item in status_payload["supported_formats"]),
        "installer_surface_preserves_capabilities": all(bool(value) for value in installer_surface.values()),
        "smoke_surface_preserves_capabilities": all(bool(value) for value in smoke_surface.values()),
        "install_session_surface_preserves_capabilities": all(bool(value) for value in install_session_surface.values()),
        "validation_report_surface_preserves_capabilities": all(bool(value) for value in validation_report_surface.values()),
        "validation_session_surface_preserves_capabilities": all(
            bool(value) for value in validation_session_surface.values()
        ),
        "benchmark_doc_profiles_complete": benchmark_doc["profiles"] == sorted(
            str(item["name"]) for item in benchmark_profiles
        )
        and benchmark_doc["mentions_1080p60_cpu_target"] is True,
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "frame_provider": frame_provider,
        "status_payload": status_payload,
        "installer_surface": installer_surface,
        "smoke_surface": smoke_surface,
        "install_session_surface": install_session_surface,
        "validation_report_surface": validation_report_surface,
        "validation_session_surface": validation_session_surface,
        "benchmark_profiles": benchmark_profiles,
        "benchmark_doc": benchmark_doc,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS capability contract checker")
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
        print("macOS capability contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
