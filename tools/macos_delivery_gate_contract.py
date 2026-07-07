# SPDX-License-Identifier: Apache-2.0
"""Contract checks for macOS delivery/installation acceptance gates.

This tool keeps the release-gate semantics in
``macos_validation_session_acceptance.py`` stable around:
- release diagnostics fallback for packaging/signing/system-version evidence
- exact target-app identity evidence for the six required client applications
- system camera device visibility using akvc-macos-list-devices evidence
- tri-state handling for partial evidence
- install-session based auto-install readiness
- sync-ipc control-plane readiness requiring both packaged tooling and runtime sync evidence
- preflight-based notarization/staple readiness
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_TOOL = ROOT / "tools" / "macos_validation_session_acceptance.py"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_acceptance_module():
    spec = importlib.util.spec_from_file_location(
        "macos_delivery_gate_contract_target",
        ACCEPTANCE_TOOL,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load macOS validation-session acceptance helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_delivery_gate_surface(text: str) -> dict[str, bool]:
    return {
        "defines_preferred_summary_value": "def _preferred_summary_value(" in text,
        "defines_tri_state_gate_helper": "def _all_true_or_false_or_none(" in text,
        "release_gate_reads_release_summary_minimum_system_version": 'release_summary.get("minimum_system_version_expected")' in text,
        "release_gate_reads_release_summary_universal2": 'release_summary.get("universal2_ready")' in text,
        "release_gate_reads_release_summary_payload": 'release_summary.get("pkg_includes_extension_payload")' in text,
        "release_gate_reads_release_summary_appledouble_clean": 'release_summary.get("pkg_payload_appledouble_clean")' in text,
        "release_gate_reads_release_summary_embedded_extension": 'release_summary.get("host_embeds_extension_bundle")' in text,
        "release_gate_reads_release_summary_app_signed": 'release_summary.get("app_signed")' in text,
        "release_gate_reads_release_summary_extension_signed": 'release_summary.get("extension_signed")' in text,
        "release_gate_reads_release_summary_command_tools_signed": 'release_summary.get("command_tools_signed")' in text,
        "release_gate_reads_release_summary_pkg_signed": 'release_summary.get("pkg_signed")' in text,
        "target_apps_define_expected_ids": "EXPECTED_APP_IDS" in text,
        "target_apps_read_validation_passed_ids": 'summary.get("validation_passed_app_ids")' in text,
        "target_apps_read_validation_failed_ids": 'summary.get("validation_failed_app_ids")' in text,
        "target_apps_read_validation_pending_ids": 'summary.get("validation_pending_app_ids")' in text,
        "target_apps_read_validation_skipped_ids": 'summary.get("validation_skipped_app_ids")' in text,
        "target_apps_read_validation_unreviewed_ids": 'summary.get("validation_unreviewed_app_ids")' in text,
        "target_apps_read_validation_observed_ids": 'summary.get("validation_observed_target_app_ids")' in text,
        "target_apps_read_validation_missing_ids": 'summary.get("validation_missing_target_app_ids")' in text,
        "target_apps_read_validation_unexpected_ids": 'summary.get("validation_unexpected_target_app_ids")' in text,
        "target_apps_compute_observed_ids": '"observed_target_app_ids": observed_target_app_ids' in text,
        "target_apps_compute_missing_ids": '"missing_target_app_ids": missing_target_app_ids' in text,
        "target_apps_compute_unexpected_ids": '"unexpected_target_app_ids": unexpected_target_app_ids' in text,
        "target_apps_require_preview_evidence": '"target_app_missing_evidence_ids"' in text
        and '"preview_visible"' in text,
        "auto_install_uses_install_session_success": 'summary.get("install_session_success")' in text,
        "auto_install_uses_install_session_ipc_ready": 'install_session_ipc_ready is not True' in text,
        "auto_install_uses_install_session_environment_blocked": 'install_session_ipc_environment_blocked is not True' in text,
        "sync_gate_reads_release_sync_ipc_tool_exists": 'summary.get("release_sync_ipc_tool_exists")' in text,
        "sync_gate_reads_release_sync_ipc_tool_signed": 'summary.get("release_sync_ipc_tool_signed")' in text,
        "sync_gate_reads_release_sync_ipc_tool_universal2_ready": 'summary.get("release_sync_ipc_tool_universal2_ready")' in text,
        "sync_gate_reads_install_session_sync_ipc_present": 'summary.get("install_session_sync_ipc_present")' in text,
        "sync_gate_reads_install_session_sync_ipc_supported": 'summary.get("install_session_sync_ipc_supported")' in text,
        "sync_gate_reads_install_session_sync_ipc_success": 'summary.get("install_session_sync_ipc_success")' in text,
        "system_camera_gate_reads_list_devices_check_passed": '"list_devices_binary_check_passed"' in text,
        "system_camera_gate_reads_filtered_device_count": '"list_devices_binary_check_filtered_device_count"' in text,
        "notarization_uses_can_notarize": 'preflight_readiness.get("can_notarize")' in text,
        "notarization_uses_can_staple": 'preflight_readiness.get("can_staple")' in text,
        "exports_release_packaging_gate": '"release_packaging_ready"' in text,
        "exports_signing_gate": '"signing_evidence_ready"' in text,
        "exports_notarization_gate": '"notarization_tooling_ready"' in text,
        "exports_auto_install_gate": '"auto_install_ready"' in text,
        "exports_sync_ipc_gate": '"sync_ipc_control_plane_ready"' in text,
        "exports_system_camera_device_gate": '"system_camera_device_visible"' in text,
        "exports_target_apps_gate": '"target_apps_all_passed"' in text,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _passing_app_matrix() -> dict[str, dict[str, Any]]:
    return {
        app_id: {
            "reviewed": True,
            "validated": True,
            "result": "pass",
            "ready": True,
            "evidence": {
                "device_listed": True,
                "device_selected": True,
                "preview_visible": True,
                "screenshot": f"artifacts/{app_id}.png",
            },
        }
        for app_id in [
            "facetime",
            "google_meet",
            "obs",
            "quicktime",
            "teams",
            "zoom",
        ]
    }


def evaluate_gate_cases() -> list[dict[str, Any]]:
    module = _load_acceptance_module()
    evaluate_acceptance = module.evaluate_acceptance
    cases: list[dict[str, Any]] = []

    fixtures = [
        {
            "name": "release_diagnostics_fallback_and_install_session_yield_all_delivery_gates_pass",
            "validation_payload": {"summary": {}},
            "preflight_payload": {"readiness": {"can_notarize": True, "can_staple": True}},
            "release_payload": {
                "summary": {
                    "minimum_system_version_expected": True,
                    "universal2_ready": True,
                    "release_artifacts_present": True,
                    "pkg_includes_extension_payload": True,
                    "pkg_payload_appledouble_clean": True,
                    "host_embeds_extension_bundle": True,
                    "app_signed": True,
                    "extension_signed": True,
                    "command_tools_signed": True,
                    "pkg_signed": True,
                    "sync_ipc_tool_exists": True,
                    "sync_ipc_tool_signed": True,
                    "sync_ipc_tool_universal2_ready": True,
                }
            },
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "install_session_present": True,
                "install_session_success": True,
                "install_session_start_ready": True,
                "install_session_start_blocker_code": "ready",
                "install_session_ipc_probe_present": True,
                "install_session_ipc_ready": True,
                "install_session_ipc_environment_blocked": False,
                "install_session_sync_ipc_present": True,
                "install_session_sync_ipc_supported": True,
                "install_session_sync_ipc_success": True,
                "install_session_sync_ipc_phase": "sync_command_succeeded",
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": True,
                "list_devices_binary_check_device_prefix": "AK Virtual Camera",
                "list_devices_binary_check_filtered_device_count": 1,
                "list_devices_binary_check_total_device_count": 2,
                "list_devices_binary_check_override_no_match_ok": True,
                "artifact_check_present": True,
                "artifact_check_passed": True,
            },
            "expected": {
                "macos_13_plus_declared": "pass",
                "universal2_ready": "pass",
                "release_packaging_ready": "pass",
                "signing_evidence_ready": "pass",
                "notarization_tooling_ready": "pass",
                "system_camera_device_visible": "pass",
                "auto_install_ready": "pass",
                "sync_ipc_control_plane_ready": "pass",
            },
        },
        {
            "name": "partial_release_evidence_and_partial_notarization_keep_unknown",
            "validation_payload": {"summary": {}},
            "preflight_payload": {"readiness": {"can_notarize": True, "can_staple": None}},
            "release_payload": {
                "summary": {
                    "minimum_system_version_expected": True,
                    "universal2_ready": None,
                    "release_artifacts_present": True,
                    "pkg_includes_extension_payload": True,
                    "pkg_payload_appledouble_clean": None,
                    "host_embeds_extension_bundle": None,
                    "app_signed": True,
                    "extension_signed": None,
                    "pkg_signed": True,
                }
            },
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "artifact_check_present": True,
                "artifact_check_passed": True,
            },
            "expected": {
                "macos_13_plus_declared": "pass",
                "universal2_ready": "unknown",
                "release_packaging_ready": "unknown",
                "signing_evidence_ready": "unknown",
                "notarization_tooling_ready": "unknown",
                "system_camera_device_visible": "unknown",
                "auto_install_ready": "unknown",
                "sync_ipc_control_plane_ready": "unknown",
            },
        },
        {
            "name": "blocked_install_session_and_missing_signature_fail_delivery_gates",
            "validation_payload": {
                "summary": {
                    "release_app_signed": False,
                    "release_extension_signed": True,
                    "release_pkg_signed": True,
                    "release_sync_ipc_tool_exists": True,
                    "release_sync_ipc_tool_signed": True,
                    "release_sync_ipc_tool_universal2_ready": True,
                }
            },
            "preflight_payload": {"readiness": {"can_notarize": False, "can_staple": True}},
            "release_payload": {"summary": {}},
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "install_session_present": True,
                "install_session_success": True,
                "install_session_start_ready": False,
                "install_session_start_blocker_code": "ipc_environment_blocked",
                "install_session_ipc_probe_present": True,
                "install_session_ipc_ready": False,
                "install_session_ipc_environment_blocked": True,
                "install_session_sync_ipc_present": True,
                "install_session_sync_ipc_supported": True,
                "install_session_sync_ipc_success": False,
                "install_session_sync_ipc_phase": "sync_command_failed",
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": False,
                "list_devices_binary_check_device_prefix": "AK Virtual Camera",
                "list_devices_binary_check_filtered_device_count": 0,
                "list_devices_binary_check_total_device_count": 2,
                "list_devices_binary_check_override_no_match_ok": True,
                "artifact_check_present": True,
                "artifact_check_passed": True,
            },
            "expected": {
                "signing_evidence_ready": "fail",
                "notarization_tooling_ready": "fail",
                "system_camera_device_visible": "fail",
                "auto_install_ready": "fail",
                "sync_ipc_control_plane_ready": "fail",
            },
        },
        {
            "name": "exact_target_app_ids_all_pass_yield_target_apps_gate_pass",
            "validation_payload": {
                "summary": {
                    "validated_apps": 6,
                    "passed_apps": 6,
                    "passed_app_ids": [
                        "facetime",
                        "google_meet",
                        "obs",
                        "quicktime",
                        "teams",
                        "zoom",
                    ],
                    "failed_app_ids": [],
                    "pending_app_ids": [],
                    "skipped_app_ids": [],
                    "unreviewed_app_ids": [],
                    "validation_app_matrix": _passing_app_matrix(),
                }
            },
            "preflight_payload": {"readiness": {}},
            "release_payload": {"summary": {}},
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
            },
            "expected": {
                "target_apps_all_passed": "pass",
            },
        },
        {
            "name": "target_app_counts_without_exact_ids_keep_gate_unknown",
            "validation_payload": {
                "summary": {
                    "validated_apps": 6,
                    "passed_apps": 6,
                }
            },
            "preflight_payload": {"readiness": {}},
            "release_payload": {"summary": {}},
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
            },
            "expected": {
                "target_apps_all_passed": "unknown",
            },
        },
        {
            "name": "missing_or_unexpected_target_ids_fail_target_apps_gate",
            "validation_payload": {
                "summary": {
                    "validated_apps": 6,
                    "passed_apps": 5,
                    "passed_app_ids": [
                        "google_meet",
                        "obs",
                        "quicktime",
                        "teams",
                        "zoom",
                    ],
                    "failed_app_ids": [],
                    "pending_app_ids": [],
                    "skipped_app_ids": [],
                    "unreviewed_app_ids": [],
                    "observed_target_app_ids": [
                        "google_meet",
                        "obs",
                        "quicktime",
                        "teams",
                        "unexpected_app",
                        "zoom",
                    ],
                    "missing_target_app_ids": ["facetime"],
                    "unexpected_target_app_ids": ["unexpected_app"],
                    "target_app_ids_complete": False,
                }
            },
            "preflight_payload": {"readiness": {}},
            "release_payload": {"summary": {}},
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "validation_observed_target_app_ids": [
                    "google_meet",
                    "obs",
                    "quicktime",
                    "teams",
                    "unexpected_app",
                    "zoom",
                ],
                "validation_missing_target_app_ids": ["facetime"],
                "validation_unexpected_target_app_ids": ["unexpected_app"],
                "validation_target_app_ids_complete": False,
            },
            "expected": {
                "target_apps_all_passed": "fail",
            },
        },
        {
            "name": "manifest_target_identity_fields_override_validation_summary_for_target_gate",
            "validation_payload": {
                "summary": {
                    "validated_apps": 6,
                    "passed_apps": 6,
                    "passed_app_ids": [
                        "facetime",
                        "google_meet",
                        "obs",
                        "quicktime",
                        "teams",
                        "zoom",
                    ],
                    "failed_app_ids": [],
                    "pending_app_ids": [],
                    "skipped_app_ids": [],
                    "unreviewed_app_ids": [],
                    "observed_target_app_ids": [
                        "facetime",
                        "google_meet",
                        "obs",
                        "quicktime",
                        "teams",
                        "zoom",
                    ],
                    "missing_target_app_ids": [],
                    "unexpected_target_app_ids": [],
                }
            },
            "preflight_payload": {"readiness": {}},
            "release_payload": {"summary": {}},
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "validation_passed_app_ids": [
                    "facetime",
                    "google_meet",
                    "obs",
                    "quicktime",
                    "teams",
                    "zoom",
                ],
                "validation_failed_app_ids": [],
                "validation_pending_app_ids": [],
                "validation_skipped_app_ids": [],
                "validation_unreviewed_app_ids": [],
                "validation_observed_target_app_ids": [
                    "obs",
                    "quicktime",
                    "teams",
                    "zoom",
                ],
                "validation_missing_target_app_ids": ["facetime", "google_meet"],
                "validation_unexpected_target_app_ids": [],
            },
            "expected": {
                "target_apps_all_passed": "fail",
            },
        },
    ]

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for fixture in fixtures:
            manifest = tmpdir / f"{fixture['name']}-session-manifest.json"
            validation_report = tmpdir / f"{fixture['name']}-validation-report.json"
            preflight_report = tmpdir / f"{fixture['name']}-preflight.json"
            release_report = tmpdir / f"{fixture['name']}-release-diagnostics.json"

            _write_json(validation_report, fixture["validation_payload"])
            _write_json(preflight_report, fixture["preflight_payload"])
            _write_json(release_report, fixture["release_payload"])
            _write_json(
                manifest,
                {
                    "artifacts": {
                        "validation_report": str(validation_report),
                        "preflight_report": str(preflight_report),
                        "release_diagnostics_report": str(release_report),
                    },
                    "summary": fixture["manifest_summary"],
                },
            )
            payload = evaluate_acceptance(manifest)
            criteria_map = {
                str(item["name"]): str(item["status"])
                for item in payload.get("criteria", [])
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            expected = dict(fixture["expected"])
            key_matches = {
                key: criteria_map.get(key) == value
                for key, value in expected.items()
            }
            cases.append(
                {
                    "name": fixture["name"],
                    "expected": expected,
                    "actual": {key: criteria_map.get(key) for key in expected},
                    "key_matches": key_matches,
                    "all_keys_match": all(key_matches.values()),
                }
            )

    return cases


def evaluate_contract() -> dict[str, Any]:
    source = parse_delivery_gate_surface(_load_text(ACCEPTANCE_TOOL))
    gate_cases = evaluate_gate_cases()
    consistency = {
        "source_complete": all(bool(value) for value in source.values()),
        "gate_cases_match_expected": all(
            bool(item["all_keys_match"]) for item in gate_cases
        ),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "source": source,
        "gate_cases": gate_cases,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS delivery gate contract checker"
    )
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
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
