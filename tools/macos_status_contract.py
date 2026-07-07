# SPDX-License-Identifier: Apache-2.0
"""Status/IPC contract checks for the macOS virtual camera stack.

Validates that:
- the native status source advertises the expected roundtrip-report merge hooks
- the Python installer merge behavior matches the expected ipc_* semantics
  for representative FrameBus probe outcomes
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMMAND_SUPPORT_MM = ROOT / "virtualcam" / "macos" / "control_bridge" / "AKVCCommandSupport.mm"

sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.platforms.macos.installer import ExtensionStatus, _merge_framebus_roundtrip_status  # noqa: E402


STATUS_KEYS = (
    "ipc_transport",
    "ipc_probe_present",
    "ipc_ready",
    "ipc_environment_blocked",
    "ipc_last_error",
    "ipc_probe_path",
    "ipc_direct_open_errno",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_native_status_contract(text: str) -> dict[str, bool]:
    return {
        "exports_ipc_transport": '@"ipc_transport"' in text,
        "exports_ipc_probe_present": '@"ipc_probe_present"' in text,
        "exports_ipc_ready": '@"ipc_ready"' in text,
        "exports_ipc_environment_blocked": '@"ipc_environment_blocked"' in text,
        "exports_ipc_last_error": '@"ipc_last_error"' in text,
        "exports_ipc_probe_path": '@"ipc_probe_path"' in text,
        "exports_ipc_direct_open_errno": '@"ipc_direct_open_errno"' in text,
        "reads_roundtrip_env": "AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON" in text,
        "searches_build_roundtrip_path": "build/macos/framebus-roundtrip.json" in text,
        "searches_session_roundtrip_path": "build/macos/session/framebus-roundtrip.json" in text,
        "searches_validation_roundtrip_path": "build/macos/validation/framebus-roundtrip.json" in text,
        "marks_unreadable_report": "framebus roundtrip report is unreadable" in text,
        "uses_consistency_all_checks": 'consistency[@"all_checks_passed"]' in text,
        "uses_observed_status_fallback": 'observed[@"status"]' in text,
        "treats_errno_1_as_environment_blocked": "code == 1" in text,
        "treats_errno_13_as_environment_blocked": "code == 13" in text,
        "composes_ipc_last_error": 'direct_open_errno=%@' in text and "componentsJoinedByString" in text,
    }


def _base_status() -> ExtensionStatus:
    return ExtensionStatus(ipc_transport="shared_memory_ringbuffer")


def _snapshot(status: ExtensionStatus) -> dict[str, Any]:
    return {key: getattr(status, key) for key in STATUS_KEYS}


def _expected_status_for_fixture(
    *,
    report_path: str | None,
    payload: dict[str, Any] | None,
    unreadable: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ipc_transport": "shared_memory_ringbuffer",
        "ipc_probe_present": False,
        "ipc_ready": None,
        "ipc_environment_blocked": False,
        "ipc_last_error": None,
        "ipc_probe_path": None,
        "ipc_direct_open_errno": None,
    }
    if report_path is None:
        return result

    result["ipc_probe_present"] = True
    result["ipc_probe_path"] = report_path
    if unreadable or payload is None:
        result["ipc_ready"] = False
        result["ipc_last_error"] = "framebus roundtrip report is unreadable"
        return result

    observed = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}
    consistency = payload.get("consistency") if isinstance(payload.get("consistency"), dict) else {}
    direct_open_errno = observed.get("direct_open_errno")
    if direct_open_errno is not None:
        try:
            direct_open_errno = int(direct_open_errno)
        except (TypeError, ValueError):
            direct_open_errno = None
    result["ipc_direct_open_errno"] = direct_open_errno

    all_checks_passed = consistency.get("all_checks_passed")
    observed_status = observed.get("status")
    if isinstance(all_checks_passed, bool):
        result["ipc_ready"] = all_checks_passed
    elif isinstance(observed_status, str) and observed_status:
        result["ipc_ready"] = observed_status == "ok"

    environment_blocked = bool(
        payload.get("environment_blocked")
        or consistency.get("environment_blocked")
        or direct_open_errno in {1, 13}
    )
    result["ipc_environment_blocked"] = environment_blocked

    transport = payload.get("transport")
    if isinstance(transport, str) and transport:
        result["ipc_transport"] = transport

    error_parts: list[str] = []
    top_level_error = payload.get("error")
    if isinstance(top_level_error, str) and top_level_error:
        error_parts.append(top_level_error)
    if isinstance(observed_status, str) and observed_status and observed_status != "ok":
        error_parts.append(f"probe status={observed_status}")
    if direct_open_errno is not None:
        error_parts.append(f"direct_open_errno={direct_open_errno}")
    if error_parts:
        result["ipc_last_error"] = "; ".join(error_parts)
    return result


def _python_status_for_fixture(
    *,
    report_path: Path | None,
    content: str | None,
) -> dict[str, Any]:
    base = _base_status()
    if report_path is None:
        return _snapshot(base)
    if content is not None:
        report_path.write_text(content, encoding="utf-8")
    merged = _merge_framebus_roundtrip_status(base, report_path)
    return _snapshot(merged)


def evaluate_fixture_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = [
        {
            "name": "no_report",
            "content": None,
            "payload": None,
            "unreadable": False,
        },
        {
            "name": "invalid_report",
            "content": "{",
            "payload": None,
            "unreadable": True,
        },
        {
            "name": "successful_probe",
            "content": json.dumps(
                {
                    "transport": "shared_memory_ringbuffer",
                    "observed": {"status": "ok"},
                    "consistency": {"all_checks_passed": True},
                }
            ),
            "payload": {
                "transport": "shared_memory_ringbuffer",
                "observed": {"status": "ok"},
                "consistency": {"all_checks_passed": True},
            },
            "unreadable": False,
        },
        {
            "name": "open_failed_errno_13",
            "content": json.dumps(
                {
                    "observed": {"status": "open_failed", "direct_open_errno": 13},
                    "consistency": {"all_checks_passed": False},
                }
            ),
            "payload": {
                "observed": {"status": "open_failed", "direct_open_errno": 13},
                "consistency": {"all_checks_passed": False},
            },
            "unreadable": False,
        },
        {
            "name": "producer_open_failed_errno_1",
            "content": json.dumps(
                {
                    "transport": "iosurface_ring",
                    "error": "shm_open(create) failed (errno=1)",
                    "environment_blocked": True,
                    "observed": {"status": "producer_open_failed", "direct_open_errno": "1"},
                    "consistency": {"all_checks_passed": False, "environment_blocked": True},
                }
            ),
            "payload": {
                "transport": "iosurface_ring",
                "error": "shm_open(create) failed (errno=1)",
                "environment_blocked": True,
                "observed": {"status": "producer_open_failed", "direct_open_errno": "1"},
                "consistency": {"all_checks_passed": False, "environment_blocked": True},
            },
            "unreadable": False,
        },
        {
            "name": "consistency_marks_environment_blocked",
            "content": json.dumps(
                {
                    "observed": {"status": "timed_out"},
                    "consistency": {"all_checks_passed": False, "environment_blocked": True},
                }
            ),
            "payload": {
                "observed": {"status": "timed_out"},
                "consistency": {"all_checks_passed": False, "environment_blocked": True},
            },
            "unreadable": False,
        },
    ]

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for fixture in fixtures:
            report_path = None if fixture["name"] == "no_report" else tmpdir / f"{fixture['name']}.json"
            actual = _python_status_for_fixture(
                report_path=report_path,
                content=fixture["content"],
            )
            expected = _expected_status_for_fixture(
                report_path=str(report_path) if report_path is not None else None,
                payload=fixture["payload"],
                unreadable=bool(fixture["unreadable"]),
            )
            key_matches = {key: actual.get(key) == expected.get(key) for key in STATUS_KEYS}
            cases.append(
                {
                    "name": fixture["name"],
                    "expected": expected,
                    "actual_python_merge": actual,
                    "key_matches": key_matches,
                    "all_keys_match": all(key_matches.values()),
                }
            )
    return cases


def evaluate_contract() -> dict[str, Any]:
    native_source = parse_native_status_contract(_read_text(COMMAND_SUPPORT_MM))
    fixture_cases = evaluate_fixture_cases()
    consistency = {
        "native_source_complete": all(native_source.values()),
        "python_fixture_behaviors_match_expected": all(
            bool(case["all_keys_match"]) for case in fixture_cases
        ),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "native_source": native_source,
        "fixture_cases": fixture_cases,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS status/IPC contract checker")
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
        print("macOS status contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
