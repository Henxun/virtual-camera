# SPDX-License-Identifier: Apache-2.0
"""Build-artifact check for the macOS status tool binary."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.runtime import find_macos_status_tool

FIXTURE_CASES = [
    {
        "name": "consumer_open_failed_errno_13",
        "payload": {
            "observed": {
                "status": "open_failed",
                "direct_open_errno": 13,
            },
            "consistency": {
                "all_checks_passed": False,
            },
        },
        "expected_errno": 13,
        "expected_transport": "shared_memory_ringbuffer",
        "expected_error_fragments": ["open_failed", "direct_open_errno=13"],
    },
    {
        "name": "producer_open_failed_errno_1",
        "payload": {
            "transport": "iosurface_ring",
            "environment_blocked": True,
            "error": "shm_open(create) failed (errno=1)",
            "observed": {
                "status": "producer_open_failed",
                "direct_open_errno": 1,
            },
            "consistency": {
                "all_checks_passed": False,
                "environment_blocked": True,
            },
        },
        "expected_errno": 1,
        "expected_transport": "iosurface_ring",
        "expected_error_fragments": ["producer_open_failed", "direct_open_errno=1"],
    },
]


def _load_json_object(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _run_fixture_case(
    *,
    status_tool: Path,
    case_name: str,
    fixture_payload: dict[str, Any],
    expected_errno: int,
    expected_transport: str,
    expected_error_fragments: list[str],
    temp_dir: Path,
) -> dict[str, Any]:
    report_path = temp_dir / f"{case_name}.framebus-roundtrip.json"
    report_path.write_text(json.dumps(fixture_payload), encoding="utf-8")
    env = {
        **os.environ,
        "AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON": str(report_path),
    }
    completed = subprocess.run(
        [str(status_tool)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    stdout = (completed.stdout or "").strip()
    payload = _load_json_object(stdout) if stdout else None
    ipc_keys = (
        "ipc_transport",
        "ipc_probe_present",
        "ipc_ready",
        "ipc_environment_blocked",
        "ipc_last_error",
        "ipc_probe_path",
        "ipc_direct_open_errno",
    )
    key_presence = {
        key: isinstance(payload, dict) and key in payload
        for key in ipc_keys
    }
    ipc_last_error = str(payload.get("ipc_last_error") or "") if isinstance(payload, dict) else ""
    consistency = {
        "command_succeeded": completed.returncode == 0,
        "returned_json_object": isinstance(payload, dict),
        "ipc_keys_present": all(key_presence.values()),
        "ipc_probe_present_true": isinstance(payload, dict) and payload.get("ipc_probe_present") is True,
        "ipc_ready_false_for_blocked_fixture": isinstance(payload, dict) and payload.get("ipc_ready") is False,
        "ipc_environment_blocked_true": isinstance(payload, dict) and payload.get("ipc_environment_blocked") is True,
        "ipc_direct_open_errno_matches_fixture": isinstance(payload, dict)
        and payload.get("ipc_direct_open_errno") == expected_errno,
        "ipc_probe_path_matches_fixture": isinstance(payload, dict) and payload.get("ipc_probe_path") == str(report_path),
        "ipc_transport_matches_fixture": isinstance(payload, dict) and payload.get("ipc_transport") == expected_transport,
        "ipc_last_error_mentions_fixture": isinstance(payload, dict)
        and all(fragment in ipc_last_error for fragment in expected_error_fragments),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "name": case_name,
        "status_tool": str(status_tool),
        "fixture_report_path": str(report_path),
        "fixture_payload": fixture_payload,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": (completed.stderr or "").strip(),
        "payload": payload,
        "key_presence": key_presence,
        "consistency": consistency,
    }


def run_status_binary_check(*, status_tool: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="akvc-status-binary-") as td:
        temp_dir = Path(td)
        fixture_cases = [
            _run_fixture_case(
                status_tool=status_tool,
                case_name=str(case["name"]),
                fixture_payload=dict(case["payload"]),
                expected_errno=int(case["expected_errno"]),
                expected_transport=str(case["expected_transport"]),
                expected_error_fragments=list(case["expected_error_fragments"]),
                temp_dir=temp_dir,
            )
            for case in FIXTURE_CASES
        ]
        primary_case = fixture_cases[0]
        aggregate_keys = (
            "command_succeeded",
            "returned_json_object",
            "ipc_keys_present",
            "ipc_probe_present_true",
            "ipc_ready_false_for_blocked_fixture",
            "ipc_environment_blocked_true",
            "ipc_direct_open_errno_matches_fixture",
            "ipc_probe_path_matches_fixture",
            "ipc_transport_matches_fixture",
            "ipc_last_error_mentions_fixture",
        )
        consistency = {
            "fixture_case_count": len(fixture_cases),
            "all_fixture_cases_passed": all(
                bool(case["consistency"]["all_checks_passed"]) for case in fixture_cases
            ),
        }
        consistency.update(
            {
                key: all(bool(case["consistency"].get(key)) for case in fixture_cases)
                for key in aggregate_keys
            }
        )
        consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
        return {
            "status_tool": str(status_tool),
            "fixture_case_name": primary_case["name"],
            "fixture_report_path": primary_case["fixture_report_path"],
            "fixture_payload": primary_case["fixture_payload"],
            "returncode": primary_case["returncode"],
            "stdout": primary_case["stdout"],
            "stderr": primary_case["stderr"],
            "payload": primary_case["payload"],
            "key_presence": primary_case["key_presence"],
            "consistency": consistency,
            "fixture_cases": fixture_cases,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS built status-tool checker")
    parser.add_argument("--status-tool")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        print("[macos-status-binary-check] requires macOS", file=sys.stderr)
        return 1

    status_tool = find_macos_status_tool(args.status_tool)
    if status_tool is None or not status_tool.is_file():
        print("[macos-status-binary-check] status tool not found", file=sys.stderr)
        return 2

    payload = run_status_binary_check(status_tool=status_tool)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    if not bool(payload["consistency"]["all_checks_passed"]):
        print("macOS status binary check failed", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
