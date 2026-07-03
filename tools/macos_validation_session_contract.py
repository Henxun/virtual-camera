# SPDX-License-Identifier: Apache-2.0
"""Validation-session summary contract checks for the macOS virtual camera stack.

Validates that:
- the validation-session helper still emits the expected session-manifest summary
  surface for readiness and capability aggregation
- representative summary cases keep the expected priority / fallback behavior
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_SESSION_TOOL = ROOT / "tools" / "macos_validation_session.py"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_validation_session_module():
    spec = importlib.util.spec_from_file_location(
        "macos_validation_session_contract_target",
        VALIDATION_SESSION_TOOL,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load macOS validation-session helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_validation_session_contract(text: str) -> dict[str, bool]:
    return {
        "writes_session_manifest": 'session-manifest.json' in text,
        "exports_validation_status_start_ready": '"validation_status_start_ready"' in text,
        "exports_validation_status_start_blocker_code": '"validation_status_start_blocker_code"' in text,
        "exports_validation_shared_memory_name": '"validation_shared_memory_name"' in text,
        "exports_validation_mach_service_name": '"validation_mach_service_name"' in text,
        "exports_validation_ipc_transport": '"validation_ipc_transport"' in text,
        "exports_validation_demo_present": '"validation_demo_present"' in text,
        "exports_validation_demo_mode": '"validation_demo_mode"' in text,
        "exports_validation_demo_mode_supported": '"validation_demo_mode_supported"' in text,
        "exports_validation_demo_width": '"validation_demo_width"' in text,
        "exports_validation_demo_height": '"validation_demo_height"' in text,
        "exports_validation_demo_fps": '"validation_demo_fps"' in text,
        "exports_validation_demo_duration": '"validation_demo_duration"' in text,
        "exports_validation_demo_camera_name": '"validation_demo_camera_name"' in text,
        "exports_validation_demo_consumer_count": '"validation_demo_consumer_count"' in text,
        "exports_validation_demo_video_path": '"validation_demo_video_path"' in text,
        "exports_validation_demo_frame_source_kind": '"validation_demo_frame_source_kind"' in text,
        "exports_validation_demo_python_entrypoint_kind": '"validation_demo_python_entrypoint_kind"' in text,
        "exports_validation_demo_sdk_streamer_factory_used": '"validation_demo_sdk_streamer_factory_used"' in text,
        "exports_validation_demo_sdk_latest_provider_factory_used": '"validation_demo_sdk_latest_provider_factory_used"' in text,
        "exports_validation_demo_sdk_direct_push_used": '"validation_demo_sdk_direct_push_used"' in text,
        "exports_validation_benchmark_kind": '"validation_benchmark_kind"' in text,
        "exports_validation_benchmark_matrix_profiles": '"validation_benchmark_matrix_profiles"' in text,
        "exports_release_command_tools_exist": '"release_command_tools_exist"' in text,
        "exports_release_command_tools_signed": '"release_command_tools_signed"' in text,
        "exports_release_command_tools_universal2_ready": '"release_command_tools_universal2_ready"' in text,
        "exports_release_pkg_payload_appledouble_clean": '"release_pkg_payload_appledouble_clean"' in text,
        "exports_release_sync_ipc_tool_exists": '"release_sync_ipc_tool_exists"' in text,
        "exports_release_sync_ipc_tool_signed": '"release_sync_ipc_tool_signed"' in text,
        "exports_release_sync_ipc_tool_universal2_ready": '"release_sync_ipc_tool_universal2_ready"' in text,
        "exports_release_app_bundle_path": '"release_app_bundle_path"' in text,
        "exports_release_extension_bundle_path": '"release_extension_bundle_path"' in text,
        "exports_release_sync_ipc_tool_path": '"release_sync_ipc_tool_path"' in text,
        "exports_release_pkg_path": '"release_pkg_path"' in text,
        "exports_runtime_host_bundle_path": '"runtime_host_bundle_path"' in text,
        "exports_runtime_extension_bundle_path": '"runtime_extension_bundle_path"' in text,
        "exports_runtime_package_install_command": '"runtime_package_install_command"' in text,
        "exports_runtime_topology_kind": '"runtime_topology_kind"' in text,
        "exports_runtime_frame_path": '"runtime_frame_path"' in text,
        "exports_runtime_host_role": '"runtime_host_role"' in text,
        "exports_runtime_host_in_frame_hot_path": '"runtime_host_in_frame_hot_path"' in text,
        "exports_runtime_dedicated_host_daemon_required": '"runtime_dedicated_host_daemon_required"' in text,
        "exports_runtime_container_app_configured": '"runtime_container_app_configured"' in text,
        "exports_runtime_data_plane": '"runtime_data_plane"' in text,
        "exports_runtime_control_plane": '"runtime_control_plane"' in text,
        "exports_runtime_release_product_identity_consistent": '"runtime_release_product_identity_consistent"' in text,
        "exports_runtime_release_product_path_equal": '"runtime_release_product_path_equal"' in text,
        "exports_validation_validated_apps": '"validation_validated_apps"' in text,
        "exports_validation_passed_apps": '"validation_passed_apps"' in text,
        "exports_validation_failed_apps": '"validation_failed_apps"' in text,
        "exports_validation_pending_apps": '"validation_pending_apps"' in text,
        "exports_validation_skipped_apps": '"validation_skipped_apps"' in text,
        "exports_validation_install_present": '"validation_install_present"' in text,
        "exports_validation_install_success": '"validation_install_success"' in text,
        "exports_validation_install_phase": '"validation_install_phase"' in text,
        "exports_validation_install_start_ready": '"validation_install_start_ready"' in text,
        "exports_validation_install_start_blocker_code": '"validation_install_start_blocker_code"' in text,
        "exports_validation_install_shared_memory_name": '"validation_install_shared_memory_name"' in text,
        "exports_validation_install_mach_service_name": '"validation_install_mach_service_name"' in text,
        "exports_validation_install_ipc_transport": '"validation_install_ipc_transport"' in text,
        "exports_validation_install_ipc_probe_present": '"validation_install_ipc_probe_present"' in text,
        "exports_validation_install_ipc_ready": '"validation_install_ipc_ready"' in text,
        "exports_validation_install_ipc_environment_blocked": '"validation_install_ipc_environment_blocked"' in text,
        "exports_validation_install_ipc_direct_open_errno": '"validation_install_ipc_direct_open_errno"' in text,
        "exports_smoke_start_ready": '"smoke_start_ready"' in text,
        "exports_smoke_shared_memory_name": '"smoke_shared_memory_name"' in text,
        "exports_smoke_mach_service_name": '"smoke_mach_service_name"' in text,
        "exports_smoke_ipc_transport": '"smoke_ipc_transport"' in text,
        "exports_install_session_start_ready": '"install_session_start_ready"' in text,
        "exports_install_session_shared_memory_name": '"install_session_shared_memory_name"' in text,
        "exports_install_session_mach_service_name": '"install_session_mach_service_name"' in text,
        "exports_install_session_ipc_transport": '"install_session_ipc_transport"' in text,
        "exports_effective_start_ready": '"effective_start_ready"' in text,
        "exports_effective_start_blocker_code": '"effective_start_blocker_code"' in text,
        "exports_effective_shared_memory_name": '"effective_shared_memory_name"' in text,
        "exports_effective_mach_service_name": '"effective_mach_service_name"' in text,
        "exports_effective_ipc_transport": '"effective_ipc_transport"' in text,
        "exports_validation_supported_formats": '"validation_supported_formats"' in text,
        "exports_validation_devices": '"validation_devices"' in text,
        "exports_validation_all_devices": '"validation_all_devices"' in text,
        "exports_validation_device_prefix": '"validation_device_prefix"' in text,
        "exports_validation_install_supported_formats": '"validation_install_supported_formats"' in text,
        "exports_validation_install_status_devices": '"validation_install_status_devices"' in text,
        "exports_validation_install_status_all_devices": '"validation_install_status_all_devices"' in text,
        "exports_validation_install_device_prefix": '"validation_install_device_prefix"' in text,
        "exports_validation_passed_app_ids": '"validation_passed_app_ids"' in text,
        "exports_validation_reviewed_app_ids": '"validation_reviewed_app_ids"' in text,
        "exports_validation_failed_app_ids": '"validation_failed_app_ids"' in text,
        "exports_validation_pending_app_ids": '"validation_pending_app_ids"' in text,
        "exports_validation_skipped_app_ids": '"validation_skipped_app_ids"' in text,
        "exports_validation_unreviewed_app_ids": '"validation_unreviewed_app_ids"' in text,
        "exports_validation_observed_target_app_ids": '"validation_observed_target_app_ids"' in text,
        "exports_validation_missing_target_app_ids": '"validation_missing_target_app_ids"' in text,
        "exports_validation_unexpected_target_app_ids": '"validation_unexpected_target_app_ids"' in text,
        "exports_validation_target_app_ids_complete": '"validation_target_app_ids_complete"' in text,
        "exports_validation_app_matrix": '"validation_app_matrix"' in text,
        "exports_smoke_supported_formats": '"smoke_supported_formats"' in text,
        "exports_smoke_devices": '"smoke_devices"' in text,
        "exports_smoke_all_devices": '"smoke_all_devices"' in text,
        "exports_smoke_device_prefix": '"smoke_device_prefix"' in text,
        "exports_install_session_supported_formats": '"install_session_supported_formats"' in text,
        "exports_install_session_devices": '"install_session_devices"' in text,
        "exports_install_session_all_devices": '"install_session_all_devices"' in text,
        "exports_install_session_device_prefix": '"install_session_device_prefix"' in text,
        "exports_install_session_ipc_probe_present": '"install_session_ipc_probe_present"' in text,
        "exports_install_session_ipc_ready": '"install_session_ipc_ready"' in text,
        "exports_install_session_sync_ipc_success": '"install_session_sync_ipc_success"' in text,
        "exports_effective_devices": '"effective_devices"' in text,
        "exports_effective_all_devices": '"effective_all_devices"' in text,
        "exports_effective_device_prefix": '"effective_device_prefix"' in text,
        "exports_effective_supported_formats": '"effective_supported_formats"' in text,
        "exports_effective_supported_frame_rates": '"effective_supported_frame_rates"' in text,
        "exports_artifact_check_present": '"artifact_check_present"' in text,
        "exports_artifact_check_passed": '"artifact_check_passed"' in text,
        "defines_merge_artifact_check_summary": "def _merge_artifact_check_summary(" in text,
        "exports_acceptance_present": '"acceptance_present"' in text,
        "exports_acceptance_ready": '"acceptance_ready"' in text,
        "exports_acceptance_contract_present": '"acceptance_contract_present"' in text,
        "exports_acceptance_contract_passed": '"acceptance_contract_passed"' in text,
        "exports_acceptance_passed_count": '"acceptance_passed_count"' in text,
        "exports_acceptance_failed_count": '"acceptance_failed_count"' in text,
        "exports_acceptance_unknown_count": '"acceptance_unknown_count"' in text,
        "exports_acceptance_failed_criteria": '"acceptance_failed_criteria"' in text,
        "exports_acceptance_unknown_criteria": '"acceptance_unknown_criteria"' in text,
        "exports_acceptance_target_apps_gate": '"target_apps_all_passed"' in text,
        "exports_acceptance_system_camera_device_gate": '"system_camera_device_visible"' in text,
        "exports_acceptance_auto_install_gate": '"auto_install_ready"' in text,
        "exports_acceptance_signing_gate": '"signing_evidence_ready"' in text,
        "exports_acceptance_notarization_gate": '"notarization_tooling_ready"' in text,
        "exports_summary_report_present": '"summary_report_present"' in text,
        "exports_entrypoints_contract_present": '"entrypoints_contract_present"' in text,
        "exports_entrypoints_contract_passed": '"entrypoints_contract_passed"' in text,
        "exports_entrypoints_contract_surface_complete": '"entrypoints_contract_surface_complete"' in text,
        "exports_entrypoints_contract_demo_case_complete": '"entrypoints_contract_demo_case_complete"' in text,
        "exports_entrypoints_contract_cli_case_complete": '"entrypoints_contract_cli_case_complete"' in text,
        "exports_entrypoints_contract_desktop_case_complete": '"entrypoints_contract_desktop_case_complete"' in text,
        "defines_merge_entrypoints_contract_summary": "def _merge_entrypoints_contract_summary(" in text,
        "defines_merge_acceptance_summary": "def _merge_acceptance_summary(" in text,
        "defines_merge_acceptance_contract_summary": "def _merge_acceptance_contract_summary(" in text,
        "uses_pick_first_present": "def _pick_first_present" in text,
        "uses_pick_first_non_none": "def _pick_first_non_none" in text,
        "reads_validation_status_shared_memory_name": 'validation_status.get("shared_memory_name")' in text,
        "reads_validation_status_mach_service_name": 'validation_status.get("mach_service_name")' in text,
        "reads_validation_status_ipc_transport": 'validation_status.get("ipc_transport")' in text,
        "reads_validation_status_supported_formats": 'validation_status.get("supported_formats")' in text,
        "reads_validation_status_devices": 'validation_status.get("devices")' in text,
        "reads_validation_status_all_devices": 'validation_status.get("all_devices")' in text,
        "reads_validation_status_device_prefix": 'validation_status.get("device_prefix")' in text,
        "reads_validation_install_supported_formats": 'validation_install.get("supported_formats")' in text,
        "reads_validation_install_status_devices": 'validation_install.get("status_devices")' in text,
        "reads_validation_install_status_all_devices": 'validation_install.get("status_all_devices")' in text,
        "reads_validation_install_device_prefix": 'validation_install.get("device_prefix")' in text,
        "reads_validation_install_shared_memory_name": 'validation_install.get("shared_memory_name")' in text,
        "reads_validation_install_mach_service_name": 'validation_install.get("mach_service_name")' in text,
        "reads_validation_install_ipc_transport": 'validation_install.get("ipc_transport")' in text,
        "reads_validation_install_ipc_probe_present": 'validation_install.get("ipc_probe_present")' in text,
        "reads_validation_verification_targets": 'validation_payload.get("verification_targets")' in text,
        "reads_validation_demo_summary_fields": 'validation_summary.get("demo_mode")' in text,
        "reads_validation_demo_consumer_count": 'validation_summary.get("demo_consumer_count")' in text,
        "reads_validation_benchmark_summary_fields": 'validation_summary.get("benchmark_kind")' in text,
        "reads_release_summary_command_tools_exist": 'release_summary.get("command_tools_exist")' in text,
        "reads_release_summary_command_tools_signed": 'release_summary.get("command_tools_signed")' in text,
        "reads_release_summary_command_tools_universal2_ready": 'release_summary.get("command_tools_universal2_ready")' in text,
        "reads_release_summary_pkg_payload_appledouble_clean": 'release_summary.get("pkg_payload_appledouble_clean")' in text,
        "reads_release_summary_sync_ipc_tool_exists": 'release_summary.get("sync_ipc_tool_exists")' in text,
        "reads_release_summary_sync_ipc_tool_signed": 'release_summary.get("sync_ipc_tool_signed")' in text,
        "reads_release_summary_sync_ipc_tool_universal2_ready": 'release_summary.get("sync_ipc_tool_universal2_ready")' in text,
        "reads_validation_runtime_provenance_host_bundle": 'validation_runtime_provenance.get("host_bundle")' in text,
        "reads_validation_runtime_provenance_extension_bundle": 'validation_runtime_provenance.get("extension_bundle")' in text,
        "reads_validation_runtime_resolved_sync_ipc_tool": 'validation_runtime_resolved_assets.get("sync_ipc_tool")' in text,
        "reads_validation_runtime_resolved_pkg": 'validation_runtime_resolved_assets.get("pkg")' in text,
        "reads_validation_summary_runtime_topology_kind": 'validation_summary.get("runtime_topology_kind")' in text,
        "reads_validation_summary_runtime_frame_path": 'validation_summary.get("runtime_frame_path")' in text,
        "reads_validation_summary_runtime_host_role": 'validation_summary.get("runtime_host_role")' in text,
        "reads_validation_summary_runtime_host_in_frame_hot_path": 'validation_summary.get("runtime_host_in_frame_hot_path")' in text,
        "reads_validation_summary_runtime_dedicated_host_daemon_required": 'validation_summary.get("runtime_dedicated_host_daemon_required")' in text,
        "reads_validation_summary_runtime_container_app_configured": 'validation_summary.get("runtime_container_app_configured")' in text,
        "reads_validation_summary_runtime_data_plane": 'validation_summary.get("runtime_data_plane")' in text,
        "reads_validation_summary_runtime_control_plane": 'validation_summary.get("runtime_control_plane")' in text,
        "reads_validation_summary_runtime_release_product_identity_consistent": '"runtime_release_product_identity_consistent": validation_summary.get(' in text,
        "defines_validation_app_matrix_ids_with_result": 'def _validation_app_matrix_ids_with_result(' in text,
        "reads_smoke_status_shared_memory_name": 'smoke_status.get("shared_memory_name")' in text,
        "reads_smoke_status_mach_service_name": 'smoke_status.get("mach_service_name")' in text,
        "reads_smoke_status_ipc_transport": 'smoke_status.get("ipc_transport")' in text,
        "reads_smoke_status_supported_formats": 'smoke_status.get("supported_formats")' in text,
        "reads_smoke_status_devices": 'smoke_status.get("devices")' in text,
        "reads_smoke_status_all_devices": 'smoke_status.get("all_devices")' in text,
        "reads_smoke_status_device_prefix": 'smoke_status.get("device_prefix")' in text,
        "reads_install_session_post_status_shared_memory_name": 'install_session_post_status.get("shared_memory_name")' in text,
        "reads_install_session_post_status_mach_service_name": 'install_session_post_status.get("mach_service_name")' in text,
        "reads_install_session_post_status_ipc_transport": 'install_session_post_status.get("ipc_transport")' in text,
        "reads_install_session_post_status_supported_formats": 'install_session_post_status.get("supported_formats")' in text,
        "reads_install_session_post_status_devices": 'install_session_post_status.get("devices")' in text,
        "reads_install_session_post_status_all_devices": 'install_session_post_status.get("all_devices")' in text,
        "reads_install_session_post_status_device_prefix": 'install_session_post_status.get("device_prefix")' in text,
        "reads_install_session_post_status_ipc_probe_present": 'install_session_post_status.get("ipc_probe_present")' in text,
        "reads_install_session_sync_ipc_phase": 'install_session_sync_ipc.get("phase")' in text,
        "treats_errno_1_as_environment_blocked": "direct_open_errno in {1, 13}" in text,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def evaluate_summary_cases() -> list[dict[str, Any]]:
    module = _load_validation_session_module()
    build_summary = module._build_manifest_summary
    cases: list[dict[str, Any]] = []

    fixtures = [
        {
            "name": "validation_install_fallback_precedes_preinstall_status_when_smoke_and_install_session_missing",
            "validation_report": {
                "summary": {
                    "status_start_ready": False,
                    "status_start_blocker_code": "device_not_visible",
                    "install_present": True,
                    "install_success": True,
                    "install_phase": "installed_visible",
                    "install_start_ready": True,
                    "install_start_blocker_code": "ready",
                    "install_supported_formats": ["1920x1080@30/60 NV12"],
                    "install_supported_frame_rates": [30, 60],
                }
            },
            "smoke_report": {
                "status": {
                }
            },
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "effective_start_ready": True,
                "effective_start_blocker_code": "ready",
                "effective_supported_formats": ["1920x1080@30/60 NV12"],
                "effective_supported_frame_rates": [30, 60],
            },
        },
        {
            "name": "smoke_start_fallback_precedes_validation_install",
            "validation_report": {
                "summary": {
                    "status_start_ready": False,
                    "status_start_blocker_code": "not_installed",
                    "install_present": True,
                    "install_success": True,
                    "install_phase": "installed_visible",
                    "install_start_ready": True,
                    "install_start_blocker_code": "ready",
                }
            },
            "smoke_report": {
                "status": {
                    "start_ready": False,
                    "start_blocker_code": "device_not_visible",
                }
            },
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "effective_start_ready": False,
                "effective_start_blocker_code": "device_not_visible",
            },
        },
        {
            "name": "framebus_errno_1_blocks_effective_start_without_status_sources",
            "validation_report": {},
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {
                "transport": "iosurface_ring",
                "error": "shm_open(create) failed (errno=1)",
                "environment_blocked": True,
                "observed": {
                    "status": "producer_open_failed",
                    "direct_open_errno": 1,
                },
                "consistency": {
                    "all_checks_passed": False,
                    "environment_blocked": True,
                },
            },
            "status_binary_check_report": {},
            "expected": {
                "effective_start_ready": False,
                "effective_start_blocker_code": "ipc_environment_blocked",
            },
        },
        {
            "name": "install_session_capabilities_precede_smoke_and_validation",
            "validation_report": {
                "status": {
                    "supported_formats": ["1280x720@30/60 NV12"],
                    "supported_frame_rates": [30, 60],
                }
            },
            "smoke_report": {
                "status": {
                    "supported_formats": ["1920x1080@30/60 NV12"],
                    "supported_frame_rates": [30, 60],
                }
            },
            "install_session_report": {
                "post_status": {
                    "supported_formats": ["3840x2160@30/60 NV12"],
                    "supported_frame_rates": ["30", "60"],
                }
            },
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "effective_supported_formats": ["3840x2160@30/60 NV12"],
                "effective_supported_frame_rates": [30, 60],
            },
        },
        {
            "name": "install_session_device_visibility_precedes_smoke_and_validation",
            "validation_report": {
                "status": {
                    "devices": ["AKVC Validation"],
                    "all_devices": ["FaceTime HD Camera", "AKVC Validation"],
                    "device_prefix": "AK Virtual Camera",
                }
            },
            "smoke_report": {
                "status": {
                    "devices": [],
                    "all_devices": ["FaceTime HD Camera"],
                    "device_prefix": "AK Virtual Camera",
                }
            },
            "install_session_report": {
                "post_status": {
                    "devices": ["AKVC Session"],
                    "all_devices": ["FaceTime HD Camera", "AKVC Session"],
                    "device_prefix": "AK Virtual Camera",
                }
            },
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "effective_devices": ["AKVC Session"],
                "effective_all_devices": ["FaceTime HD Camera", "AKVC Session"],
                "effective_device_prefix": "AK Virtual Camera",
            },
        },
        {
            "name": "install_session_ipc_surfaces_to_manifest_summary",
            "validation_report": {},
            "smoke_report": {},
            "install_session_report": {
                "post_status": {
                    "shared_memory_name": "/akvc-install-session",
                    "mach_service_name": "com.akvc.install-session",
                    "ipc_transport": "shared_memory_ringbuffer",
                    "ipc_probe_present": True,
                    "ipc_ready": False,
                    "ipc_environment_blocked": True,
                    "ipc_direct_open_errno": 13,
                },
                "sync_ipc": {
                    "supported": True,
                    "success": True,
                    "phase": "sync_command_succeeded",
                    "shared_memory_name": "/akvc-install-session",
                    "ipc_transport": "shared_memory_ringbuffer",
                    "returncode": 0,
                },
            },
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "install_session_shared_memory_name": "/akvc-install-session",
                "install_session_mach_service_name": "com.akvc.install-session",
                "install_session_ipc_transport": "shared_memory_ringbuffer",
                "install_session_ipc_probe_present": True,
                "install_session_ipc_ready": False,
                "install_session_ipc_environment_blocked": True,
                "install_session_ipc_direct_open_errno": 13,
                "install_session_sync_ipc_present": True,
                "install_session_sync_ipc_supported": True,
                "install_session_sync_ipc_success": True,
                "install_session_sync_ipc_phase": "sync_command_succeeded",
                "install_session_sync_ipc_shared_memory_name": "/akvc-install-session",
                "install_session_sync_ipc_transport": "shared_memory_ringbuffer",
                "install_session_sync_ipc_returncode": 0,
            },
        },
        {
            "name": "effective_ipc_identity_prefers_install_session_then_smoke_then_validation",
            "validation_report": {
                "status": {
                    "shared_memory_name": "/akvc-validation",
                    "mach_service_name": "com.akvc.validation",
                    "ipc_transport": "status_only_transport",
                },
                "summary": {
                    "install_shared_memory_name": "/akvc-validation-install",
                    "install_mach_service_name": "com.akvc.validation.install",
                    "install_ipc_transport": "validation_install_transport",
                },
            },
            "smoke_report": {
                "status": {
                    "shared_memory_name": "/akvc-smoke",
                    "mach_service_name": "com.akvc.smoke",
                    "ipc_transport": "smoke_transport",
                }
            },
            "install_session_report": {
                "post_status": {
                    "shared_memory_name": "/akvc-install-session",
                    "mach_service_name": "com.akvc.install-session",
                    "ipc_transport": "install_session_transport",
                }
            },
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "effective_shared_memory_name": "/akvc-install-session",
                "effective_mach_service_name": "com.akvc.install-session",
                "effective_ipc_transport": "install_session_transport",
            },
        },
        {
            "name": "smoke_capabilities_fallback_when_install_session_missing",
            "validation_report": {
                "status": {
                    "supported_formats": ["1280x720@30/60 NV12"],
                    "supported_frame_rates": [30, 60],
                }
            },
            "smoke_report": {
                "status": {
                    "supported_formats": ["1920x1080@30/60 NV12"],
                    "supported_frame_rates": [30, 60],
                }
            },
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "effective_supported_formats": ["1920x1080@30/60 NV12"],
                "effective_supported_frame_rates": [30, 60],
            },
        },
        {
            "name": "validation_install_capabilities_fallback_when_smoke_and_install_session_missing",
            "validation_report": {
                "status": {
                    "supported_formats": ["1280x720@30/60 NV12"],
                    "supported_frame_rates": [30],
                },
                "summary": {
                    "install_present": True,
                    "install_success": True,
                    "install_phase": "installed_visible",
                    "install_shared_memory_name": "/akvc-validation-install",
                    "install_mach_service_name": "com.akvc.validation.install",
                    "install_ipc_transport": "validation_install_transport",
                    "install_supported_formats": ["1920x1080@30/60 NV12"],
                    "install_supported_frame_rates": [30, 60],
                },
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_install_shared_memory_name": "/akvc-validation-install",
                "validation_install_mach_service_name": "com.akvc.validation.install",
                "validation_install_ipc_transport": "validation_install_transport",
                "effective_shared_memory_name": "/akvc-validation-install",
                "effective_mach_service_name": "com.akvc.validation.install",
                "effective_ipc_transport": "validation_install_transport",
                "effective_supported_formats": ["1920x1080@30/60 NV12"],
                "effective_supported_frame_rates": [30, 60],
            },
        },
        {
            "name": "validation_install_ipc_fallback_surfaces_to_manifest_summary",
            "validation_report": {
                "summary": {
                    "install_present": True,
                    "install_success": True,
                    "install_phase": "installed_visible",
                    "install_shared_memory_name": "/akvc-validation-install",
                    "install_mach_service_name": "com.akvc.validation.install",
                    "install_ipc_transport": "validation_install_transport",
                    "install_ipc_probe_present": True,
                    "install_ipc_ready": False,
                    "install_ipc_environment_blocked": True,
                    "install_ipc_direct_open_errno": 13,
                },
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_install_shared_memory_name": "/akvc-validation-install",
                "validation_install_mach_service_name": "com.akvc.validation.install",
                "validation_install_ipc_transport": "validation_install_transport",
                "validation_install_ipc_probe_present": True,
                "validation_install_ipc_ready": False,
                "validation_install_ipc_environment_blocked": True,
                "validation_install_ipc_direct_open_errno": 13,
            },
        },
        {
            "name": "validation_report_app_result_ids_surface_to_manifest_summary",
            "validation_report": {
                "summary": {
                    "passed_app_ids": ["zoom", "obs"],
                    "reviewed_app_ids": ["obs", "teams", "zoom"],
                    "failed_app_ids": ["teams"],
                    "pending_app_ids": ["google_meet"],
                    "skipped_app_ids": ["quicktime"],
                    "unreviewed_app_ids": ["facetime"],
                    "observed_target_app_ids": ["google_meet", "obs", "quicktime", "teams", "zoom"],
                    "missing_target_app_ids": ["facetime"],
                    "unexpected_target_app_ids": [],
                    "target_app_ids_complete": False,
                }
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_passed_app_ids": ["zoom", "obs"],
                "validation_reviewed_app_ids": ["obs", "teams", "zoom"],
                "validation_failed_app_ids": ["teams"],
                "validation_pending_app_ids": ["google_meet"],
                "validation_skipped_app_ids": ["quicktime"],
                "validation_unreviewed_app_ids": ["facetime"],
                "validation_observed_target_app_ids": ["google_meet", "obs", "quicktime", "teams", "zoom"],
                "validation_missing_target_app_ids": ["facetime"],
                "validation_unexpected_target_app_ids": [],
                "validation_target_app_ids_complete": False,
            },
        },
        {
            "name": "validation_demo_summary_surfaces_to_manifest_summary",
            "validation_report": {
                "summary": {
                    "demo_present": True,
                    "demo_mode": "video-file",
                    "demo_mode_supported": True,
                    "demo_width": 1920,
                    "demo_height": 1080,
                    "demo_fps": 60.0,
                    "demo_duration": 5.0,
                    "demo_camera_name": "AKVC Demo",
                    "demo_consumer_count": 2,
                    "demo_video_path": "demo.mp4",
                    "demo_frame_source_kind": "opencv_video_file",
                    "demo_python_entrypoint_kind": "create_pyside6_streamer.start_video_file_stream",
                    "demo_sdk_streamer_factory_used": True,
                    "demo_sdk_latest_provider_factory_used": False,
                    "demo_sdk_direct_push_used": False,
                }
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_demo_present": True,
                "validation_demo_mode": "video-file",
                "validation_demo_mode_supported": True,
                "validation_demo_width": 1920,
                "validation_demo_height": 1080,
                "validation_demo_fps": 60.0,
                "validation_demo_duration": 5.0,
                "validation_demo_camera_name": "AKVC Demo",
                "validation_demo_consumer_count": 2,
                "validation_demo_video_path": "demo.mp4",
                "validation_demo_frame_source_kind": "opencv_video_file",
                "validation_demo_python_entrypoint_kind": "create_pyside6_streamer.start_video_file_stream",
                "validation_demo_sdk_streamer_factory_used": True,
                "validation_demo_sdk_latest_provider_factory_used": False,
                "validation_demo_sdk_direct_push_used": False,
            },
        },
        {
            "name": "validation_benchmark_matrix_surfaces_to_manifest_summary",
            "validation_report": {
                "summary": {
                    "benchmark_kind": "benchmark_matrix",
                    "benchmark_matrix_profiles": [
                        {
                            "profile_name": "720p30",
                            "width": 1280,
                            "height": 720,
                            "fps": 30.0,
                            "fps_target_met": True,
                            "cpu_target_applies": False,
                            "cpu_target_met": None,
                            "actual_fps": 29.8,
                            "cpu_percent": 3.1,
                            "avg_latency_ms": 0.7,
                        },
                        {
                            "profile_name": "1080p60",
                            "width": 1920,
                            "height": 1080,
                            "fps": 60.0,
                            "fps_target_met": True,
                            "cpu_target_applies": True,
                            "cpu_target_met": True,
                            "actual_fps": 59.6,
                            "cpu_percent": 8.4,
                            "avg_latency_ms": 1.1,
                        },
                    ],
                }
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_benchmark_kind": "benchmark_matrix",
                "validation_benchmark_matrix_profiles": [
                    {
                        "profile_name": "720p30",
                        "width": 1280,
                        "height": 720,
                        "fps": 30.0,
                        "fps_target_met": True,
                        "cpu_target_applies": False,
                        "cpu_target_met": None,
                        "actual_fps": 29.8,
                        "cpu_percent": 3.1,
                        "avg_latency_ms": 0.7,
                    },
                    {
                        "profile_name": "1080p60",
                        "width": 1920,
                        "height": 1080,
                        "fps": 60.0,
                        "fps_target_met": True,
                        "cpu_target_applies": True,
                        "cpu_target_met": True,
                        "actual_fps": 59.6,
                        "cpu_percent": 8.4,
                        "avg_latency_ms": 1.1,
                    },
                ],
            },
        },
        {
            "name": "release_diagnostics_runtime_tool_fields_surface_to_manifest_summary",
            "validation_report": {},
            "release_diagnostics_report": {
                "summary": {
                    "command_tools_exist": True,
                    "command_tools_signed": True,
                    "command_tools_universal2_ready": True,
                    "pkg_payload_appledouble_clean": True,
                    "sync_ipc_tool_exists": True,
                    "sync_ipc_tool_signed": True,
                    "sync_ipc_tool_universal2_ready": True,
                }
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "release_command_tools_exist": True,
                "release_command_tools_signed": True,
                "release_command_tools_universal2_ready": True,
                "release_pkg_payload_appledouble_clean": True,
                "release_sync_ipc_tool_exists": True,
                "release_sync_ipc_tool_signed": True,
                "release_sync_ipc_tool_universal2_ready": True,
            },
        },
        {
            "name": "runtime_release_product_identity_fields_surface_to_manifest_summary",
            "validation_report": {
                "summary": {
                    "release_app_bundle_path": "/Applications/Amaran Desktop.app",
                    "release_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                    "release_sync_ipc_tool_path": "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc",
                    "release_pkg_path": "/tmp/VirtualCamera.pkg",
                    "runtime_release_product_identity_consistent": True,
                    "runtime_release_product_path_equal": False,
                },
                "runtime_assets": {
                    "provenance": {
                        "host_bundle": "/Applications/Amaran Desktop.app",
                        "extension_bundle": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                        "package_install_command": [
                            "/usr/sbin/installer",
                            "-pkg",
                            "/tmp/VirtualCamera.pkg",
                            "-target",
                            "/",
                        ],
                    }
                },
            },
            "release_diagnostics_report": {},
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "release_app_bundle_path": "/Applications/Amaran Desktop.app",
                "release_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                "release_sync_ipc_tool_path": "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc",
                "release_pkg_path": "/tmp/VirtualCamera.pkg",
                "runtime_host_bundle_path": "/Applications/Amaran Desktop.app",
                "runtime_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                "runtime_package_install_command": [
                    "/usr/sbin/installer",
                    "-pkg",
                    "/tmp/VirtualCamera.pkg",
                    "-target",
                    "/",
                ],
                "runtime_release_product_identity_consistent": True,
                "runtime_release_product_path_equal": False,
            },
        },
        {
            "name": "runtime_topology_fields_surface_to_manifest_summary",
            "validation_report": {
                "summary": {
                    "runtime_topology_kind": "camera_extension_direct_framebus",
                    "runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
                    "runtime_host_role": "container_activation_command_bridge",
                    "runtime_host_in_frame_hot_path": False,
                    "runtime_dedicated_host_daemon_required": False,
                    "runtime_container_app_configured": True,
                    "runtime_data_plane": "shared_memory_ringbuffer",
                    "runtime_control_plane": "host_activation_plus_sync_ipc",
                }
            },
            "release_diagnostics_report": {},
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "runtime_topology_kind": "camera_extension_direct_framebus",
                "runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
                "runtime_host_role": "container_activation_command_bridge",
                "runtime_host_in_frame_hot_path": False,
                "runtime_dedicated_host_daemon_required": False,
                "runtime_container_app_configured": True,
                "runtime_data_plane": "shared_memory_ringbuffer",
                "runtime_control_plane": "host_activation_plus_sync_ipc",
            },
        },
        {
            "name": "validation_verification_targets_surface_to_manifest_summary",
            "validation_report": {
                "verification_targets": [
                    {
                        "id": "zoom",
                        "name": "Zoom",
                        "reviewed": True,
                        "validated": True,
                        "result": "pass",
                        "notes": "preview visible",
                        "ready": True,
                        "status": "ok",
                        "steps": ["Open Zoom > Settings > Video."],
                        "checks": ["Camera list shows AK Virtual Camera."],
                    },
                    {
                        "id": "teams",
                        "name": "Teams",
                        "reviewed": True,
                        "validated": False,
                        "result": "fail",
                        "notes": "device not shown",
                        "ready": True,
                        "status": "missing",
                        "steps": ["Open Teams > Settings > Devices."],
                        "checks": ["Device settings page shows AK Virtual Camera."],
                        "evidence": {
                            "device_listed": False,
                            "device_selected": False,
                            "preview_visible": False,
                            "screenshot": "",
                        },
                    },
                ]
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_app_matrix": {
                    "zoom": {
                        "name": "Zoom",
                        "reviewed": True,
                        "validated": True,
                        "result": "pass",
                        "notes": "preview visible",
                        "ready": True,
                        "status": "ok",
                        "steps": ["Open Zoom > Settings > Video."],
                        "checks": ["Camera list shows AK Virtual Camera."],
                    },
                    "teams": {
                        "name": "Teams",
                        "reviewed": True,
                        "validated": False,
                        "result": "fail",
                        "notes": "device not shown",
                        "ready": True,
                        "status": "missing",
                        "steps": ["Open Teams > Settings > Devices."],
                        "checks": ["Device settings page shows AK Virtual Camera."],
                        "evidence": {
                            "device_listed": False,
                            "device_selected": False,
                            "preview_visible": False,
                            "screenshot": "",
                        },
                    },
                }
            },
        },
        {
            "name": "validation_app_matrix_derives_counts_and_ids_when_summary_missing",
            "validation_report": {
                "verification_targets": [
                    {"id": "zoom", "reviewed": True, "validated": True, "result": "pass"},
                    {"id": "teams", "reviewed": True, "validated": False, "result": "fail"},
                    {"id": "google_meet", "reviewed": False, "validated": False, "result": "pending"},
                    {"id": "obs", "reviewed": True, "validated": False, "result": "skipped"},
                    {"id": "quicktime", "reviewed": False, "validated": False, "result": "pending"},
                ]
            },
            "smoke_report": {},
            "install_session_report": {},
            "framebus_roundtrip_report": {},
            "status_binary_check_report": {},
            "expected": {
                "validation_validated_apps": 3,
                "validation_passed_apps": 1,
                "validation_failed_apps": 1,
                "validation_pending_apps": 2,
                "validation_skipped_apps": 1,
                "validation_passed_app_ids": ["zoom"],
                "validation_reviewed_app_ids": ["obs", "teams", "zoom"],
                "validation_failed_app_ids": ["teams"],
                "validation_pending_app_ids": ["google_meet", "quicktime"],
                "validation_skipped_app_ids": ["obs"],
                "validation_unreviewed_app_ids": ["google_meet", "quicktime"],
                "validation_observed_target_app_ids": ["google_meet", "obs", "quicktime", "teams", "zoom"],
                "validation_missing_target_app_ids": ["facetime"],
                "validation_unexpected_target_app_ids": [],
                "validation_target_app_ids_complete": False,
            },
        },
    ]

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for fixture in fixtures:
            validation_report = tmpdir / f"{fixture['name']}-validation-report.json"
            release_diagnostics_report = tmpdir / f"{fixture['name']}-release-diagnostics.json"
            smoke_report = tmpdir / f"{fixture['name']}-smoke-report.json"
            install_session_report = tmpdir / f"{fixture['name']}-install-session-report.json"
            framebus_roundtrip_report = tmpdir / f"{fixture['name']}-framebus-roundtrip.json"
            status_binary_check_report = tmpdir / f"{fixture['name']}-status-binary-check.json"
            list_devices_binary_check_report = tmpdir / f"{fixture['name']}-list-devices-binary-check.json"

            if fixture["validation_report"]:
                _write_json(validation_report, fixture["validation_report"])
            if fixture.get("release_diagnostics_report"):
                _write_json(
                    release_diagnostics_report,
                    fixture["release_diagnostics_report"],
                )
            if fixture["smoke_report"]:
                _write_json(smoke_report, fixture["smoke_report"])
            if fixture["install_session_report"]:
                _write_json(install_session_report, fixture["install_session_report"])
            if fixture["framebus_roundtrip_report"]:
                _write_json(framebus_roundtrip_report, fixture["framebus_roundtrip_report"])
            if fixture["status_binary_check_report"]:
                _write_json(status_binary_check_report, fixture["status_binary_check_report"])

            actual = build_summary(
                validation_report=validation_report,
                release_diagnostics_report=release_diagnostics_report,
                smoke_report=smoke_report,
                install_session_report=install_session_report,
                framebus_roundtrip_report=framebus_roundtrip_report,
                status_binary_check_report=status_binary_check_report,
                list_devices_binary_check_report=list_devices_binary_check_report,
            )
            expected = dict(fixture["expected"])
            key_matches = {
                key: actual.get(key) == value
                for key, value in expected.items()
            }
            cases.append(
                {
                    "name": fixture["name"],
                    "expected": expected,
                    "actual": {key: actual.get(key) for key in expected},
                    "key_matches": key_matches,
                    "all_keys_match": all(key_matches.values()),
                }
            )

    return cases


def evaluate_acceptance_merge_cases() -> list[dict[str, Any]]:
    module = _load_validation_session_module()
    merge_acceptance_summary = module._merge_acceptance_summary
    cases: list[dict[str, Any]] = []

    fixtures = [
        {
            "name": "acceptance_summary_present_propagates_status_lists",
            "summary": {"effective_start_ready": True},
            "acceptance_payload": {
                "summary": {
                    "acceptance_ready": False,
                    "passed_count": 3,
                    "failed_count": 1,
                    "unknown_count": 2,
                    "failed_criteria": ["target_apps_all_passed"],
                    "unknown_criteria": ["benchmark_1080p60_cpu_target_met"],
                    "manual_app_validation_ready": False,
                    "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                    "manual_app_validation_unknown_criteria": [
                        "notarization_tooling_ready"
                    ],
                    "manual_app_validation_blockers": [
                        "system_camera_device_visible",
                        "notarization_tooling_ready",
                    ],
                },
                "criteria": [
                    {"name": "target_apps_all_passed", "status": "fail"},
                    {"name": "system_camera_device_visible", "status": "pass"},
                    {"name": "benchmark_matrix_complete", "status": "pass"},
                    {"name": "benchmark_fps_targets_met", "status": "pass"},
                    {"name": "auto_install_ready", "status": "pass"},
                    {"name": "signing_evidence_ready", "status": "pass"},
                    {"name": "notarization_tooling_ready", "status": "unknown"},
                    {"name": "sync_ipc_control_plane_ready", "status": "pass"},
                ],
            },
            "expected": {
                "acceptance_present": True,
                "acceptance_ready": False,
                "acceptance_passed_count": 3,
                "acceptance_failed_count": 1,
                "acceptance_unknown_count": 2,
                "acceptance_failed_criteria": ["target_apps_all_passed"],
                "acceptance_unknown_criteria": ["benchmark_1080p60_cpu_target_met"],
                "manual_app_validation_ready": False,
                "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                "manual_app_validation_unknown_criteria": ["notarization_tooling_ready"],
                "manual_app_validation_blockers": [
                    "system_camera_device_visible",
                    "notarization_tooling_ready",
                ],
                "target_apps_all_passed": "fail",
                "system_camera_device_visible": "pass",
                "benchmark_matrix_complete": "pass",
                "benchmark_fps_targets_met": "pass",
                "auto_install_ready": "pass",
                "signing_evidence_ready": "pass",
                "notarization_tooling_ready": "unknown",
                "sync_ipc_control_plane_ready": "pass",
            },
        },
        {
            "name": "acceptance_summary_missing_resets_fields_to_none",
            "summary": {"effective_start_ready": False},
            "acceptance_payload": None,
            "expected": {
                "acceptance_present": False,
                "acceptance_ready": None,
                "acceptance_passed_count": None,
                "acceptance_failed_count": None,
                "acceptance_unknown_count": None,
                "acceptance_failed_criteria": None,
                "acceptance_unknown_criteria": None,
                "manual_app_validation_ready": None,
                "manual_app_validation_failed_criteria": None,
                "manual_app_validation_unknown_criteria": None,
                "manual_app_validation_blockers": None,
                "target_apps_all_passed": None,
                "system_camera_device_visible": None,
                "benchmark_matrix_complete": None,
                "benchmark_fps_targets_met": None,
                "auto_install_ready": None,
                "sync_ipc_control_plane_ready": None,
            },
        },
    ]

    for fixture in fixtures:
        actual = merge_acceptance_summary(
            dict(fixture["summary"]),
            fixture["acceptance_payload"],
        )
        expected = dict(fixture["expected"])
        key_matches = {
            key: actual.get(key) == value
            for key, value in expected.items()
        }
        cases.append(
            {
                "name": fixture["name"],
                "expected": expected,
                "actual": {key: actual.get(key) for key in expected},
                "key_matches": key_matches,
                "all_keys_match": all(key_matches.values()),
            }
        )

    return cases


def evaluate_entrypoints_merge_cases() -> list[dict[str, Any]]:
    module = _load_validation_session_module()
    merge_entrypoints_summary = module._merge_entrypoints_contract_summary
    cases: list[dict[str, Any]] = []

    fixtures = [
        {
            "name": "entrypoints_contract_present_propagates_consistency_flags",
            "summary": {"effective_start_ready": True},
            "entrypoints_payload": {
                "consistency": {
                    "all_checks_passed": True,
                    "surface_complete": True,
                    "demo_case_complete": True,
                    "cli_case_complete": True,
                    "desktop_case_complete": True,
                }
            },
            "expected": {
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": True,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": True,
                "entrypoints_contract_desktop_case_complete": True,
            },
        },
        {
            "name": "entrypoints_contract_missing_resets_fields_to_none",
            "summary": {"effective_start_ready": False},
            "entrypoints_payload": None,
            "expected": {
                "entrypoints_contract_present": False,
                "entrypoints_contract_passed": None,
                "entrypoints_contract_surface_complete": None,
                "entrypoints_contract_demo_case_complete": None,
                "entrypoints_contract_cli_case_complete": None,
                "entrypoints_contract_desktop_case_complete": None,
            },
        },
    ]

    for fixture in fixtures:
        actual = merge_entrypoints_summary(
            dict(fixture["summary"]),
            fixture["entrypoints_payload"],
        )
        expected = dict(fixture["expected"])
        key_matches = {
            key: actual.get(key) == value
            for key, value in expected.items()
        }
        cases.append(
            {
                "name": fixture["name"],
                "expected": expected,
                "actual": {key: actual.get(key) for key in expected},
                "key_matches": key_matches,
                "all_keys_match": all(key_matches.values()),
            }
        )

    return cases


def evaluate_contract() -> dict[str, Any]:
    source = parse_validation_session_contract(_load_text(VALIDATION_SESSION_TOOL))
    summary_cases = evaluate_summary_cases()
    entrypoints_merge_cases = evaluate_entrypoints_merge_cases()
    acceptance_merge_cases = evaluate_acceptance_merge_cases()
    consistency = {
        "source_complete": all(bool(value) for value in source.values()),
        "summary_cases_match_expected": all(
            bool(item["all_keys_match"]) for item in summary_cases
        ),
        "entrypoints_merge_cases_match_expected": all(
            bool(item["all_keys_match"]) for item in entrypoints_merge_cases
        ),
        "acceptance_merge_cases_match_expected": all(
            bool(item["all_keys_match"]) for item in acceptance_merge_cases
        ),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "source": source,
        "summary_cases": summary_cases,
        "entrypoints_merge_cases": entrypoints_merge_cases,
        "acceptance_merge_cases": acceptance_merge_cases,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS validation-session contract checker"
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
        print("macOS validation-session contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
