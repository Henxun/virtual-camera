# SPDX-License-Identifier: Apache-2.0
"""Contract checks for the macOS validation-session acceptance helper."""

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
        "macos_validation_session_acceptance_contract_target",
        ACCEPTANCE_TOOL,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load macOS validation-session acceptance helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_acceptance_contract(text: str) -> dict[str, bool]:
    return {
        "defines_expected_app_ids": "EXPECTED_APP_IDS" in text,
        "defines_demo_mode_mapping": "DEMO_MODE_TO_FRAME_SOURCE_KIND" in text,
        "reads_validation_passed_app_ids": 'summary.get("validation_passed_app_ids")' in text,
        "reads_validation_failed_app_ids": 'summary.get("validation_failed_app_ids")' in text,
        "reads_validation_pending_app_ids": 'summary.get("validation_pending_app_ids")' in text,
        "reads_validation_skipped_app_ids": 'summary.get("validation_skipped_app_ids")' in text,
        "reads_validation_unreviewed_app_ids": 'summary.get("validation_unreviewed_app_ids")' in text,
        "reads_validation_observed_target_app_ids": 'summary.get("validation_observed_target_app_ids")' in text,
        "reads_validation_missing_target_app_ids": 'summary.get("validation_missing_target_app_ids")' in text,
        "reads_validation_unexpected_target_app_ids": 'summary.get("validation_unexpected_target_app_ids")' in text,
        "fallbacks_to_validation_report_observed_ids": 'validation_summary.get("observed_target_app_ids")' in text,
        "uses_entrypoints_contract_report": '"entrypoints_contract_report"' in text,
        "uses_release_diagnostics_report": '"release_diagnostics_report"' in text,
        "uses_benchmark_report": '"benchmark_report"' in text,
        "defines_expected_benchmark_profiles": "EXPECTED_BENCHMARK_PROFILES" in text,
        "exports_target_apps_gate": '"target_apps_all_passed"' in text,
        "exports_benchmark_matrix_gate": '"benchmark_matrix_complete"' in text,
        "exports_manual_app_validation_ready": '"manual_app_validation_ready"' in text,
        "exports_manual_app_validation_blockers": '"manual_app_validation_blockers"' in text,
        "exports_pyside6_gate": '"pyside6_path_exercised"' in text,
        "exports_python_direct_runtime_gate": '"python_direct_runtime_ready"' in text,
        "exports_python_entrypoints_gate": '"python_entrypoints_consistent"' in text,
        "exports_system_camera_device_gate": '"system_camera_device_visible"' in text,
        "exports_sync_ipc_gate": '"sync_ipc_control_plane_ready"' in text,
        "reads_direct_push_demo_using_direct_sender": (
            "DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES" in text
            and '"using_direct_sender"' in text
            and 'summary.get(f"{prefix}_{key}")' in text
        ),
        "reads_direct_push_demo_helper_hot_path_used": (
            "DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES" in text
            and '"helper_hot_path_used"' in text
            and 'summary.get(f"{prefix}_{key}")' in text
        ),
        "reads_direct_push_demo_shared_memory_fallback_used": (
            "DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES" in text
            and '"shared_memory_fallback_used"' in text
            and 'summary.get(f"{prefix}_{key}")' in text
        ),
        "reads_effective_device_prefix": '"effective_device_prefix"' in text,
        "reads_validation_demo_camera_name": '"validation_demo_camera_name"' in text,
        "exports_device_name_match_evidence": '"demo_camera_name_matches_effective_prefix"' in text
        and '"list_devices_binary_check_device_prefix_matches_effective_prefix"' in text,
        "reads_list_devices_binary_check_passed": '"list_devices_binary_check_passed"' in text,
        "reads_list_devices_binary_check_filtered_device_count": '"list_devices_binary_check_filtered_device_count"' in text,
        "reads_benchmark_required_profiles_present": 'benchmark_acceptance.get("required_profiles_present")' in text,
        "reads_benchmark_missing_required_profiles": 'benchmark_acceptance.get("missing_required_profiles")' in text,
        "reads_install_session_sync_ipc_present": 'summary.get("install_session_sync_ipc_present")' in text,
        "reads_install_session_sync_ipc_success": 'summary.get("install_session_sync_ipc_success")' in text,
        "reads_release_command_tools_signed": 'release_summary.get("command_tools_signed")' in text,
        "reads_release_pkg_payload_appledouble_clean": 'release_summary.get("pkg_payload_appledouble_clean")' in text,
        "reads_runtime_release_product_identity_consistent": '"runtime_release_product_identity_consistent"' in text,
        "exports_signing_command_tools_evidence": '"release_command_tools_signed"' in text
        and '"command_tools_signed"' in text,
        "reads_target_app_evidence": '"device_listed"' in text
        and '"device_selected"' in text
        and '"preview_visible"' in text,
        "reports_missing_target_app_evidence": '"target_app_missing_evidence_ids"' in text,
        "missing_target_ids_fail_gate": "elif missing_target_app_ids:" in text,
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


def _passing_sdk_contract() -> dict[str, Any]:
    return {
        "consistency": {
            "all_checks_passed": True,
            "constructor_shape_aligned": True,
            "direct_sender_exports_present": True,
        }
    }


def evaluate_cases() -> list[dict[str, Any]]:
    module = _load_acceptance_module()
    evaluate_acceptance = module.evaluate_acceptance
    cases: list[dict[str, Any]] = []

    fixtures = [
        {
            "name": "complete_acceptance_passes_key_gates",
            "validation_payload": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "latest-provider",
                    "demo_mode_supported": True,
                    "demo_frame_source_kind": "latest_frame_provider",
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
                    "runtime_packaged_assets_present": True,
                }
            },
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
            "benchmark_payload": {
                "summary": {
                    "benchmark_acceptance": {
                        "required_profile_count": 6,
                        "required_profiles_present": True,
                        "missing_required_profiles": [],
                        "unexpected_profiles": [],
                        "all_fps_targets_met": True,
                        "1080p60_cpu_target_met": True,
                    }
                }
            },
            "entrypoints_payload": {
                "consistency": {
                    "all_checks_passed": True,
                    "surface_complete": True,
                    "demo_case_complete": True,
                    "cli_case_complete": True,
                    "desktop_case_complete": True,
                }
            },
            "sdk_contract_payload": _passing_sdk_contract(),
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "effective_device_prefix": "AK Virtual Camera",
                "validation_device_prefix": "AK Virtual Camera",
                "validation_install_device_prefix": "AK Virtual Camera",
                "install_session_device_prefix": "AK Virtual Camera",
                "validation_demo_camera_name": "AK Virtual Camera",
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
                "list_devices_binary_check_total_device_count": 3,
                "list_devices_binary_check_override_no_match_ok": True,
                "artifact_check_present": True,
                "artifact_check_passed": True,
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": True,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": True,
                "entrypoints_contract_desktop_case_complete": True,
                "direct_push_demo_returncode": 0,
                "direct_push_demo_using_direct_sender": True,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": False,
                "direct_push_demo_direct_only": True,
                "direct_push_demo_allow_shared_memory_fallback": False,
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_runtime_dedicated_host_daemon_required": False,
            },
            "expected": {
                "acceptance_ready": True,
                "manual_app_validation_ready": True,
                "manual_app_validation_blockers": [],
                "target_apps_all_passed": "pass",
                "benchmark_matrix_complete": "pass",
                "pyside6_path_exercised": "pass",
                "python_direct_runtime_ready": "pass",
                "python_entrypoints_consistent": "pass",
                "system_camera_device_visible": "pass",
                "sync_ipc_control_plane_ready": "pass",
            },
        },
        {
            "name": "incomplete_benchmark_matrix_fails_matrix_gate",
            "validation_payload": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "latest-provider",
                    "demo_mode_supported": True,
                    "demo_frame_source_kind": "latest_frame_provider",
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
                    "runtime_packaged_assets_present": True,
                }
            },
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
            "benchmark_payload": {
                "summary": {
                    "benchmark_acceptance": {
                        "required_profile_count": 6,
                        "required_profiles_present": False,
                        "missing_required_profiles": ["4k60", "720p60", "1080p30"],
                        "unexpected_profiles": [],
                        "all_fps_targets_met": True,
                        "1080p60_cpu_target_met": True,
                    }
                }
            },
            "entrypoints_payload": {
                "consistency": {
                    "all_checks_passed": True,
                    "surface_complete": True,
                    "demo_case_complete": True,
                    "cli_case_complete": True,
                    "desktop_case_complete": True,
                }
            },
            "sdk_contract_payload": _passing_sdk_contract(),
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "effective_device_prefix": "AK Virtual Camera",
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
                "list_devices_binary_check_total_device_count": 3,
                "list_devices_binary_check_override_no_match_ok": True,
                "artifact_check_present": True,
                "artifact_check_passed": True,
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": True,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": True,
                "entrypoints_contract_desktop_case_complete": True,
                "direct_push_demo_returncode": 0,
                "direct_push_demo_using_direct_sender": True,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": False,
                "direct_push_demo_direct_only": True,
                "direct_push_demo_allow_shared_memory_fallback": False,
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_runtime_dedicated_host_daemon_required": False,
            },
            "expected": {
                "acceptance_ready": False,
                "manual_app_validation_ready": True,
                "manual_app_validation_blockers": [],
                "benchmark_matrix_complete": "fail",
                "benchmark_fps_targets_met": "pass",
                "benchmark_1080p60_cpu_target_met": "pass",
            },
        },
        {
            "name": "only_counts_keep_target_apps_unknown",
            "validation_payload": {
                "summary": {
                    "validated_apps": 6,
                    "passed_apps": 6,
                }
            },
            "manifest_summary": {},
            "expected": {
                "acceptance_ready": False,
                "target_apps_all_passed": "unknown",
            },
        },
        {
            "name": "manifest_identity_fields_override_validation_summary_and_fail_target_gate",
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
            "manifest_summary": {
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
                "acceptance_ready": False,
                "target_apps_all_passed": "fail",
            },
        },
        {
            "name": "missing_entrypoints_contract_and_benchmark_keep_gates_unknown",
            "validation_payload": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "latest-provider",
                    "demo_mode_supported": True,
                    "demo_frame_source_kind": "latest_frame_provider",
                }
            },
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
            },
            "expected": {
                "acceptance_ready": False,
                "manual_app_validation_ready": False,
                "manual_app_validation_blockers": [
                    "macos_13_plus_declared",
                    "universal2_ready",
                    "release_packaging_ready",
                    "signing_evidence_ready",
                    "notarization_tooling_ready",
                    "python_direct_runtime_ready",
                    "python_entrypoints_consistent",
                    "auto_install_ready",
                    "system_camera_device_visible",
                    "artifact_replay_passed",
                    "runtime_assets_packaged",
                ],
                "benchmark_matrix_complete": "unknown",
                "python_entrypoints_consistent": "unknown",
                "benchmark_1080p60_cpu_target_met": "unknown",
            },
        },
        {
            "name": "runtime_release_product_mismatch_fails_release_packaging_gate",
            "validation_payload": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "latest-provider",
                    "demo_mode_supported": True,
                    "demo_frame_source_kind": "latest_frame_provider",
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
                    "runtime_packaged_assets_present": True,
                }
            },
            "preflight_payload": {"readiness": {"can_notarize": True, "can_staple": True}},
            "benchmark_payload": {
                "summary": {
                    "benchmark_acceptance": {
                        "required_profile_count": 6,
                        "required_profiles_present": True,
                        "missing_required_profiles": [],
                        "unexpected_profiles": [],
                        "all_fps_targets_met": True,
                        "1080p60_cpu_target_met": True,
                    }
                }
            },
            "entrypoints_payload": {
                "consistency": {
                    "all_checks_passed": True,
                    "surface_complete": True,
                    "demo_case_complete": True,
                    "cli_case_complete": True,
                    "desktop_case_complete": True,
                }
            },
            "sdk_contract_payload": _passing_sdk_contract(),
            "manifest_summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "effective_device_prefix": "AKVC Demo",
                "validation_device_prefix": "AKVC Demo",
                "validation_install_device_prefix": "AKVC Demo",
                "install_session_device_prefix": "AKVC Demo",
                "validation_demo_camera_name": "AKVC Demo",
                "install_session_present": True,
                "install_session_success": True,
                "install_session_start_ready": True,
                "install_session_start_blocker_code": "ready",
                "install_session_ipc_probe_present": True,
                "install_session_ipc_ready": True,
                "install_session_ipc_environment_blocked": False,
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": False,
                "list_devices_binary_check_device_prefix": "AKVC Demo",
                "list_devices_binary_check_filtered_device_count": 0,
                "artifact_check_present": True,
                "artifact_check_passed": True,
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": True,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": True,
                "entrypoints_contract_desktop_case_complete": True,
                "direct_push_demo_returncode": 0,
                "direct_push_demo_using_direct_sender": True,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": False,
                "direct_push_demo_direct_only": True,
                "direct_push_demo_allow_shared_memory_fallback": False,
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_runtime_dedicated_host_daemon_required": False,
                "release_artifacts_present": True,
                "release_pkg_includes_extension_payload": True,
                "release_pkg_payload_appledouble_clean": True,
                "release_host_embeds_extension_bundle": True,
                "runtime_release_product_identity_consistent": False,
            },
            "expected": {
                "acceptance_ready": False,
                "release_packaging_ready": "fail",
            },
        },
        {
            "name": "custom_device_name_visibility_failure_keeps_runtime_name_in_evidence",
            "validation_payload": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "provider",
                    "demo_mode_supported": True,
                    "demo_frame_source_kind": "callable_provider",
                    "runtime_packaged_assets_present": True,
                }
            },
            "manifest_summary": {
                "effective_device_prefix": "AKVC Demo",
                "validation_device_prefix": "AKVC Demo",
                "validation_install_device_prefix": "AKVC Demo",
                "install_session_device_prefix": "AKVC Demo",
                "validation_demo_camera_name": "AKVC Demo",
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": False,
                "list_devices_binary_check_device_prefix": "AKVC Demo",
                "list_devices_binary_check_filtered_device_count": 0,
                "list_devices_binary_check_total_device_count": 2,
            },
            "expected": {
                "acceptance_ready": False,
                "system_camera_device_visible": "fail",
            },
        },
        {
            "name": "shared_memory_fallback_fails_python_direct_runtime_gate",
            "validation_payload": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "latest-provider",
                    "demo_mode_supported": True,
                    "demo_frame_source_kind": "latest_frame_provider",
                    "runtime_packaged_assets_present": True,
                }
            },
            "manifest_summary": {
                "direct_push_demo_returncode": 0,
                "direct_push_demo_using_direct_sender": False,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": True,
                "direct_push_demo_direct_only": False,
                "direct_push_demo_allow_shared_memory_fallback": True,
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_runtime_dedicated_host_daemon_required": False,
            },
            "expected": {
                "acceptance_ready": False,
                "python_direct_runtime_ready": "fail",
            },
        },
    ]

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for fixture in fixtures:
            manifest = tmpdir / f"{fixture['name']}-session-manifest.json"
            artifacts: dict[str, str] = {}

            validation_report = tmpdir / f"{fixture['name']}-validation-report.json"
            _write_json(validation_report, fixture.get("validation_payload", {"summary": {}}))
            artifacts["validation_report"] = str(validation_report)

            if "preflight_payload" in fixture:
                preflight_report = tmpdir / f"{fixture['name']}-preflight.json"
                _write_json(preflight_report, fixture["preflight_payload"])
                artifacts["preflight_report"] = str(preflight_report)

            if "release_payload" in fixture:
                release_report = tmpdir / f"{fixture['name']}-release-diagnostics.json"
                _write_json(release_report, fixture["release_payload"])
                artifacts["release_diagnostics_report"] = str(release_report)

            if "benchmark_payload" in fixture:
                benchmark_report = tmpdir / f"{fixture['name']}-benchmark.json"
                _write_json(benchmark_report, fixture["benchmark_payload"])
                artifacts["benchmark_report"] = str(benchmark_report)

            if "entrypoints_payload" in fixture:
                entrypoints_report = tmpdir / f"{fixture['name']}-entrypoints-contract.json"
                _write_json(entrypoints_report, fixture["entrypoints_payload"])
                artifacts["entrypoints_contract_report"] = str(entrypoints_report)

            if "sdk_contract_payload" in fixture:
                sdk_contract_report = tmpdir / f"{fixture['name']}-sdk-contract.json"
                _write_json(sdk_contract_report, fixture["sdk_contract_payload"])
                artifacts["sdk_contract_report"] = str(sdk_contract_report)

            _write_json(
                manifest,
                {
                    "artifacts": artifacts,
                    "summary": fixture.get("manifest_summary", {}),
                },
            )

            payload = evaluate_acceptance(manifest)
            summary = payload.get("summary", {})
            criteria_map = {
                str(item["name"]): str(item["status"])
                for item in payload.get("criteria", [])
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            actual = {
                "acceptance_ready": bool(summary.get("acceptance_ready")),
            }
            for key in fixture["expected"]:
                if key == "acceptance_ready":
                    continue
                if key.startswith("manual_app_validation_"):
                    actual[key] = summary.get(key)
                    continue
                actual[key] = criteria_map.get(key)
            expected = dict(fixture["expected"])
            key_matches = {key: actual.get(key) == value for key, value in expected.items()}
            cases.append(
                {
                    "name": fixture["name"],
                    "expected": expected,
                    "actual": actual,
                    "key_matches": key_matches,
                    "all_keys_match": all(key_matches.values()),
                }
            )
            if fixture["name"] == "custom_device_name_visibility_failure_keeps_runtime_name_in_evidence":
                criteria_by_name = {
                    str(item["name"]): item
                    for item in payload.get("criteria", [])
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                }
                criterion = criteria_by_name["system_camera_device_visible"]
                evidence = dict(criterion.get("evidence", {}))
                cases[-1]["custom_device_name_evidence"] = {
                    "effective_device_prefix": evidence.get("effective_device_prefix"),
                    "validation_demo_camera_name": evidence.get("validation_demo_camera_name"),
                    "demo_camera_name_matches_effective_prefix": evidence.get("demo_camera_name_matches_effective_prefix"),
                    "list_devices_binary_check_device_prefix_matches_effective_prefix": evidence.get(
                        "list_devices_binary_check_device_prefix_matches_effective_prefix"
                    ),
                    "note_contains_runtime_name": "AKVC Demo" in str(criterion.get("note") or ""),
                }

    return cases


def evaluate_contract() -> dict[str, Any]:
    source = parse_acceptance_contract(_load_text(ACCEPTANCE_TOOL))
    cases = evaluate_cases()
    consistency = {
        "source_complete": all(bool(value) for value in source.values()),
        "cases_match_expected": all(bool(item["all_keys_match"]) for item in cases),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "source": source,
        "cases": cases,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS validation-session acceptance contract checker"
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
