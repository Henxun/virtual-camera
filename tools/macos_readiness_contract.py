# SPDX-License-Identifier: Apache-2.0
"""Readiness/blocker contract checks for the macOS virtual camera stack.

Validates that:
- the Python installer bridge still exposes the shared readiness helpers
- phase inference keeps the expected approval/device visibility priority
- readiness evaluation keeps the expected blocker precedence for representative
  install/IPC states
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PY = ROOT / "camera-core" / "src" / "akvc" / "platforms" / "macos" / "installer.py"

sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.platforms.macos.installer import (  # noqa: E402
    ExtensionInstallState,
    ExtensionStatus,
    evaluate_extension_readiness,
    infer_extension_phase,
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_readiness_contract(text: str) -> dict[str, bool]:
    return {
        "defines_extension_readiness_dataclass": "class ExtensionReadiness" in text,
        "defines_infer_extension_phase": "def infer_extension_phase(" in text,
        "defines_evaluate_extension_readiness": "def evaluate_extension_readiness(" in text,
        "uses_approval_required_blocker": 'blocker_code = "approval_required"' in text,
        "uses_ipc_environment_blocked_blocker": 'blocker_code = "ipc_environment_blocked"' in text,
        "uses_ipc_not_ready_blocker": 'blocker_code = "ipc_not_ready"' in text,
        "uses_device_not_visible_blocker": 'blocker_code = "device_not_visible"' in text,
        "uses_package_install_failed_blocker": 'blocker_code = "package_install_failed"' in text,
        "uses_install_failed_blocker": 'blocker_code = "install_failed"' in text,
        "uses_not_installed_blocker": 'blocker_code = "not_installed"' in text,
        "uses_ready_blocker": 'blocker_code = "ready"' in text,
        "approval_precedes_ipc_blocker": (
            "if resolved_phase == \"pending_approval\" or status.approval_required:" in text
            and "elif ipc_blocker_active:" in text
        ),
        "stale_ipc_guard_present": (
            "ipc_blocker_active = bool(" in text
            and "resolved_phase == \"installed_visible\"" in text
            and "status.enabled and visible_devices" in text
        ),
        "returns_verification_targets": "verification_targets=build_verification_targets(" in text,
    }


def evaluate_phase_cases() -> list[dict[str, Any]]:
    cases = [
        {
            "name": "visible_device",
            "kwargs": {
                "approval_required": False,
                "enabled": True,
                "devices": ["AK Virtual Camera"],
            },
            "expected_phase": "installed_visible",
        },
        {
            "name": "pending_approval",
            "kwargs": {
                "approval_required": True,
                "enabled": False,
                "devices": [],
            },
            "expected_phase": "pending_approval",
        },
        {
            "name": "enabled_without_device",
            "kwargs": {
                "approval_required": False,
                "enabled": True,
                "devices": [],
            },
            "expected_phase": "timeout_waiting_for_device",
        },
        {
            "name": "not_installed",
            "kwargs": {
                "approval_required": False,
                "enabled": False,
                "devices": [],
            },
            "expected_phase": "",
        },
    ]
    results: list[dict[str, Any]] = []
    for case in cases:
        actual = infer_extension_phase(**case["kwargs"])
        results.append(
            {
                "name": case["name"],
                "expected_phase": case["expected_phase"],
                "actual_phase": actual,
                "matches": actual == case["expected_phase"],
            }
        )
    return results


def evaluate_readiness_cases() -> list[dict[str, Any]]:
    cases = [
        {
            "name": "ready_visible_device",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
            ),
            "devices": ["AK Virtual Camera"],
            "phase": "installed_visible",
            "expected": {
                "ready": True,
                "blocker_code": "ready",
                "message_contains": "系统设备列表",
                "verification_targets_ready": True,
            },
        },
        {
            "name": "approval_overrides_stale_ipc",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
                approval_required=True,
                enabled=False,
                ipc_probe_present=True,
                ipc_ready=False,
                ipc_environment_blocked=True,
                ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ),
            "devices": ["AK Virtual Camera"],
            "phase": "pending_approval",
            "expected": {
                "ready": False,
                "blocker_code": "approval_required",
                "message_contains": "批准",
                "verification_targets_ready": False,
            },
        },
        {
            "name": "stale_ipc_does_not_override_not_installed",
            "status": ExtensionStatus(
                state=ExtensionInstallState.NOT_INSTALLED,
                enabled=False,
                ipc_probe_present=True,
                ipc_ready=False,
                ipc_environment_blocked=True,
                ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ),
            "devices": [],
            "phase": "",
            "expected": {
                "ready": False,
                "blocker_code": "not_installed",
                "message_contains": "尚未安装",
                "verification_targets_ready": False,
            },
        },
        {
            "name": "device_not_visible",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
            ),
            "devices": [],
            "phase": "timeout_waiting_for_device",
            "expected": {
                "ready": False,
                "blocker_code": "device_not_visible",
                "message_contains": "还没有出现虚拟摄像头",
                "verification_targets_ready": False,
            },
        },
        {
            "name": "ipc_environment_blocked",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
                ipc_probe_present=True,
                ipc_ready=False,
                ipc_environment_blocked=True,
                ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ),
            "devices": ["AK Virtual Camera"],
            "phase": "installed_visible",
            "expected": {
                "ready": False,
                "blocker_code": "ipc_environment_blocked",
                "message_contains": "direct_open_errno=13",
                "verification_targets_ready": True,
            },
        },
        {
            "name": "ipc_not_ready",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
                ipc_probe_present=True,
                ipc_ready=False,
                ipc_environment_blocked=False,
                ipc_last_error="probe status=timed_out",
            ),
            "devices": ["AK Virtual Camera"],
            "phase": "installed_visible",
            "expected": {
                "ready": False,
                "blocker_code": "ipc_not_ready",
                "message_contains": "FrameBus IPC 自检尚未通过",
                "verification_targets_ready": True,
            },
        },
        {
            "name": "package_install_failed",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALL_FAILED,
                last_error="authentication failed",
            ),
            "devices": [],
            "phase": "package_install_failed",
            "expected": {
                "ready": False,
                "blocker_code": "package_install_failed",
                "message_contains": "authentication failed",
                "verification_targets_ready": False,
            },
        },
        {
            "name": "generic_install_failed",
            "status": ExtensionStatus(
                state=ExtensionInstallState.INSTALL_FAILED,
                last_error="container app executable missing",
            ),
            "devices": [],
            "phase": "install_failed",
            "expected": {
                "ready": False,
                "blocker_code": "install_failed",
                "message_contains": "container app executable missing",
                "verification_targets_ready": False,
            },
        },
    ]

    results: list[dict[str, Any]] = []
    for case in cases:
        readiness = evaluate_extension_readiness(
            status=case["status"],
            devices=case["devices"],
            phase=case["phase"],
        )
        expected = case["expected"]
        targets_ready = all(bool(item.get("ready")) for item in readiness.verification_targets)
        checks = {
            "ready_matches": readiness.ready == expected["ready"],
            "blocker_code_matches": readiness.blocker_code == expected["blocker_code"],
            "message_contains_expected_text": expected["message_contains"] in readiness.message,
            "verification_targets_ready_matches": targets_ready == expected["verification_targets_ready"],
        }
        results.append(
            {
                "name": case["name"],
                "expected": expected,
                "actual": {
                    "phase": readiness.phase,
                    "ready": readiness.ready,
                    "blocker_code": readiness.blocker_code,
                    "message": readiness.message,
                    "steps": list(readiness.steps),
                    "verification_targets_ready": targets_ready,
                },
                "checks": checks,
                "all_checks_passed": all(checks.values()),
            }
        )
    return results


def evaluate_contract() -> dict[str, Any]:
    source_checks = parse_readiness_contract(_read_text(INSTALLER_PY))
    phase_cases = evaluate_phase_cases()
    readiness_cases = evaluate_readiness_cases()
    return {
        "source": source_checks,
        "phase_cases": phase_cases,
        "readiness_cases": readiness_cases,
        "consistency": {
            "source_complete": all(source_checks.values()),
            "phase_cases_match_expected": all(case["matches"] for case in phase_cases),
            "readiness_cases_match_expected": all(case["all_checks_passed"] for case in readiness_cases),
            "all_checks_passed": (
                all(source_checks.values())
                and all(case["matches"] for case in phase_cases)
                and all(case["all_checks_passed"] for case in readiness_cases)
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS readiness contract helper")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_contract()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if payload["consistency"]["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
