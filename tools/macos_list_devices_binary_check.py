# SPDX-License-Identifier: Apache-2.0
"""Build-artifact check for the macOS list-devices tool binary."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.platforms.macos.ipc import DEFAULT_CAMERA_NAME, read_camera_name_override
from akvc.runtime import find_macos_list_devices_tool

OVERRIDE_NO_MATCH_PREFIX = "__AKVC_BINARY_CHECK_NO_MATCH__"


def _load_json_object(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        normalized.append(item)
    return normalized


def _resolve_expected_prefix(expected_prefix: str | None) -> str:
    normalized = str(expected_prefix).strip() if expected_prefix is not None else ""
    if normalized:
        return normalized
    persisted = read_camera_name_override()
    if persisted:
        return persisted
    return DEFAULT_CAMERA_NAME


def _run_probe_case(
    *,
    list_devices_tool: Path,
    case_name: str,
    expected_prefix: str,
    override_prefix: str | None,
) -> dict[str, Any]:
    env = dict(os.environ)
    if override_prefix is None:
        env.pop("AKVC_DEVICE_PREFIX", None)
    else:
        env["AKVC_DEVICE_PREFIX"] = override_prefix

    completed = subprocess.run(
        [str(list_devices_tool)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    stdout = (completed.stdout or "").strip()
    payload = _load_json_object(stdout) if stdout else None
    devices = _string_list(payload.get("devices")) if isinstance(payload, dict) else None
    all_devices = _string_list(payload.get("all_devices")) if isinstance(payload, dict) else None
    device_prefix = payload.get("device_prefix") if isinstance(payload, dict) else None

    consistency = {
        "command_succeeded": completed.returncode == 0,
        "returned_json_object": isinstance(payload, dict),
        "devices_is_string_list": devices is not None,
        "all_devices_is_string_list": all_devices is not None,
        "device_prefix_is_string": isinstance(device_prefix, str),
        "device_prefix_matches_expected": device_prefix == expected_prefix,
        "filtered_subset_of_all_devices": (
            devices is not None and all_devices is not None and set(devices).issubset(set(all_devices))
        ),
        "filtered_devices_match_prefix": (
            devices is not None and all(name.startswith(expected_prefix) for name in devices)
        ),
    }
    if override_prefix is not None:
        consistency["override_prefix_returns_empty_devices"] = devices == []
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "name": case_name,
        "list_devices_tool": str(list_devices_tool),
        "expected_prefix": expected_prefix,
        "override_prefix": override_prefix,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": (completed.stderr or "").strip(),
        "payload": payload,
        "consistency": consistency,
    }


def run_list_devices_binary_check(*, list_devices_tool: Path, expected_prefix: str | None = None) -> dict[str, Any]:
    resolved_expected_prefix = _resolve_expected_prefix(expected_prefix)
    probe_cases = [
        _run_probe_case(
            list_devices_tool=list_devices_tool,
            case_name="default_prefix",
            expected_prefix=resolved_expected_prefix,
            override_prefix=None,
        ),
        _run_probe_case(
            list_devices_tool=list_devices_tool,
            case_name="override_prefix_no_match",
            expected_prefix=OVERRIDE_NO_MATCH_PREFIX,
            override_prefix=OVERRIDE_NO_MATCH_PREFIX,
        ),
    ]
    primary = probe_cases[0]
    aggregate = {
        "probe_case_count": len(probe_cases),
        "command_succeeded": all(bool(case["consistency"]["command_succeeded"]) for case in probe_cases),
        "json_shape_valid": all(
            bool(case["consistency"]["returned_json_object"])
            and bool(case["consistency"]["devices_is_string_list"])
            and bool(case["consistency"]["all_devices_is_string_list"])
            and bool(case["consistency"]["device_prefix_is_string"])
            for case in probe_cases
        ),
        "default_prefix_case_passed": bool(probe_cases[0]["consistency"]["all_checks_passed"]),
        "override_prefix_case_passed": bool(probe_cases[1]["consistency"]["all_checks_passed"]),
    }
    aggregate["all_checks_passed"] = all(bool(value) for value in aggregate.values())
    return {
        "list_devices_tool": str(list_devices_tool),
        "expected_prefix": resolved_expected_prefix,
        "returncode": primary["returncode"],
        "stdout": primary["stdout"],
        "stderr": primary["stderr"],
        "payload": primary["payload"],
        "consistency": aggregate,
        "probe_cases": probe_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS built list-devices tool checker")
    parser.add_argument("--list-devices-tool")
    parser.add_argument("--expected-prefix")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        print("[macos-list-devices-binary-check] requires macOS", file=sys.stderr)
        return 1

    list_devices_tool = find_macos_list_devices_tool(args.list_devices_tool)
    if list_devices_tool is None or not list_devices_tool.is_file():
        print("[macos-list-devices-binary-check] list-devices tool not found", file=sys.stderr)
        return 2

    payload = run_list_devices_binary_check(
        list_devices_tool=list_devices_tool,
        expected_prefix=args.expected_prefix,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    if not bool(payload["consistency"]["all_checks_passed"]):
        print("macOS list-devices binary check failed", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
