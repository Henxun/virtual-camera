# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation-session contract helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_validation_session_contract.py"


def test_macos_validation_session_contract_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "macos_validation_session.py" in text
    assert "validation_install_fallback_precedes_preinstall_status_when_smoke_and_install_session_missing" in text
    assert "smoke_start_fallback_precedes_validation_install" in text
    assert "framebus_errno_1_blocks_effective_start_without_status_sources" in text
    assert "install_session_capabilities_precede_smoke_and_validation" in text
    assert "install_session_ipc_surfaces_to_manifest_summary" in text
    assert "effective_ipc_identity_prefers_install_session_then_smoke_then_validation" in text
    assert "smoke_capabilities_fallback_when_install_session_missing" in text
    assert "validation_install_capabilities_fallback_when_smoke_and_install_session_missing" in text
    assert "exports_effective_shared_memory_name" in text
    assert "exports_validation_install_ipc_transport" in text
    assert "reads_install_session_post_status_shared_memory_name" in text
    assert "exports_validation_install_ipc_probe_present" in text
    assert "exports_validation_install_ipc_ready" in text
    assert "exports_validation_install_ipc_environment_blocked" in text
    assert "exports_validation_install_ipc_direct_open_errno" in text
    assert "artifact_check_present" in text
    assert "artifact_check_passed" in text
    assert "acceptance_present" in text
    assert "acceptance_ready" in text
    assert "acceptance_contract_present" in text
    assert "acceptance_contract_passed" in text
    assert "acceptance_passed_count" in text
    assert "acceptance_failed_count" in text
    assert "acceptance_unknown_count" in text
    assert "summary_report_present" in text
    assert "entrypoints_contract_present" in text
    assert "entrypoints_contract_passed" in text
    assert "entrypoints_contract_present_propagates_consistency_flags" in text
    assert "entrypoints_contract_missing_resets_fields_to_none" in text
    assert "defines_merge_acceptance_contract_summary" in text
    assert "acceptance_failed_criteria" in text
    assert "acceptance_unknown_criteria" in text
    assert "acceptance_summary_present_propagates_status_lists" in text
    assert "acceptance_summary_missing_resets_fields_to_none" in text
    assert "exports_acceptance_system_camera_device_gate" in text
    assert "system_camera_device_visible" in text
    assert "validation_demo_summary_surfaces_to_manifest_summary" in text
    assert "exports_validation_demo_python_entrypoint_kind" in text
    assert "exports_validation_demo_sdk_streamer_factory_used" in text
    assert "exports_validation_demo_sdk_latest_provider_factory_used" in text
    assert "exports_validation_demo_sdk_direct_push_used" in text
    assert "validation_benchmark_matrix_surfaces_to_manifest_summary" in text
    assert "release_diagnostics_runtime_tool_fields_surface_to_manifest_summary" in text
    assert "install_session_device_visibility_precedes_smoke_and_validation" in text
    assert "exports_validation_devices" in text
    assert "exports_validation_all_devices" in text
    assert "exports_validation_device_prefix" in text
    assert "exports_validation_install_status_devices" in text
    assert "exports_validation_install_status_all_devices" in text
    assert "exports_validation_install_device_prefix" in text
    assert "exports_smoke_devices" in text
    assert "exports_smoke_all_devices" in text
    assert "exports_smoke_device_prefix" in text
    assert "exports_install_session_devices" in text
    assert "exports_install_session_all_devices" in text
    assert "exports_install_session_device_prefix" in text
    assert "exports_effective_devices" in text
    assert "exports_effective_all_devices" in text
    assert "exports_effective_device_prefix" in text
    assert "effective_supported_formats" in text
    assert "exports_install_session_ipc_probe_present" in text
    assert "exports_install_session_ipc_ready" in text
    assert "validation_report_app_result_ids_surface_to_manifest_summary" in text
    assert "validation_verification_targets_surface_to_manifest_summary" in text
    assert "validation_app_matrix_derives_counts_and_ids_when_summary_missing" in text
    assert "validation_passed_app_ids" in text
    assert "validation_reviewed_app_ids" in text
    assert "validation_failed_app_ids" in text
    assert "validation_app_matrix" in text
    assert '"steps": ["Open Zoom > Settings > Video."]' in text
    assert '"checks": ["Camera list shows AK Virtual Camera."]' in text
    assert "validation_validated_apps" in text
    assert "validation_missing_target_app_ids" in text
    assert "validation_unexpected_target_app_ids" in text
    assert "validation_target_app_ids_complete" in text
    assert "release_sync_ipc_tool_exists" in text
    assert "release_command_tools_signed" in text
    assert "release_pkg_payload_appledouble_clean" in text
    assert "release_app_bundle_path" in text
    assert "runtime_host_bundle_path" in text
    assert "runtime_topology_kind" in text
    assert "runtime_frame_path" in text
    assert "runtime_host_role" in text
    assert "runtime_host_in_frame_hot_path" in text
    assert "runtime_dedicated_host_daemon_required" in text
    assert "runtime_container_app_configured" in text
    assert "runtime_data_plane" in text
    assert "runtime_control_plane" in text
    assert "runtime_release_product_identity_consistent" in text
    assert 'release_summary.get("command_tools_signed")' in text
    assert 'release_summary.get("sync_ipc_tool_exists")' in text
    assert 'validation_runtime_provenance.get("host_bundle")' in text
    assert 'validation_summary.get("runtime_topology_kind")' in text
    assert "sync_ipc_control_plane_ready" in text
    assert "install_session_sync_ipc_success" in text
    assert "--output" in text


def test_macos_validation_session_contract_tool_reports_expected_summary_behavior(
    tmp_path,
) -> None:
    output = tmp_path / "validation-session-contract.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["consistency"]["source_complete"] is True
    assert payload["consistency"]["summary_cases_match_expected"] is True
    assert payload["consistency"]["entrypoints_merge_cases_match_expected"] is True
    assert payload["consistency"]["acceptance_merge_cases_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True

    cases = {item["name"]: item for item in payload["summary_cases"]}
    assert cases["validation_install_fallback_precedes_preinstall_status_when_smoke_and_install_session_missing"]["actual"] == {
        "effective_start_blocker_code": "ready",
        "effective_start_ready": True,
        "effective_supported_formats": ["1920x1080@30/60 NV12"],
        "effective_supported_frame_rates": [30, 60],
    }
    assert cases["smoke_start_fallback_precedes_validation_install"]["actual"] == {
        "effective_start_blocker_code": "device_not_visible",
        "effective_start_ready": False,
    }
    assert cases["framebus_errno_1_blocks_effective_start_without_status_sources"]["actual"] == {
        "effective_start_blocker_code": "ipc_environment_blocked",
        "effective_start_ready": False,
    }
    assert cases["install_session_capabilities_precede_smoke_and_validation"]["actual"] == {
        "effective_supported_formats": ["3840x2160@30/60 NV12"],
        "effective_supported_frame_rates": [30, 60],
    }
    assert cases["install_session_device_visibility_precedes_smoke_and_validation"]["actual"] == {
        "effective_devices": ["AKVC Session"],
        "effective_all_devices": ["FaceTime HD Camera", "AKVC Session"],
        "effective_device_prefix": "AK Virtual Camera",
    }
    assert cases["install_session_ipc_surfaces_to_manifest_summary"]["actual"] == {
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
    }
    assert cases["effective_ipc_identity_prefers_install_session_then_smoke_then_validation"]["actual"] == {
        "effective_shared_memory_name": "/akvc-install-session",
        "effective_mach_service_name": "com.akvc.install-session",
        "effective_ipc_transport": "install_session_transport",
    }
    assert cases["smoke_capabilities_fallback_when_install_session_missing"]["actual"] == {
        "effective_supported_formats": ["1920x1080@30/60 NV12"],
        "effective_supported_frame_rates": [30, 60],
    }
    assert cases["validation_install_capabilities_fallback_when_smoke_and_install_session_missing"]["actual"] == {
        "validation_install_shared_memory_name": "/akvc-validation-install",
        "validation_install_mach_service_name": "com.akvc.validation.install",
        "validation_install_ipc_transport": "validation_install_transport",
        "effective_shared_memory_name": "/akvc-validation-install",
        "effective_mach_service_name": "com.akvc.validation.install",
        "effective_ipc_transport": "validation_install_transport",
        "effective_supported_formats": ["1920x1080@30/60 NV12"],
        "effective_supported_frame_rates": [30, 60],
    }
    assert cases["validation_install_ipc_fallback_surfaces_to_manifest_summary"]["actual"] == {
        "validation_install_shared_memory_name": "/akvc-validation-install",
        "validation_install_mach_service_name": "com.akvc.validation.install",
        "validation_install_ipc_transport": "validation_install_transport",
        "validation_install_ipc_probe_present": True,
        "validation_install_ipc_ready": False,
        "validation_install_ipc_environment_blocked": True,
        "validation_install_ipc_direct_open_errno": 13,
    }
    assert cases["validation_report_app_result_ids_surface_to_manifest_summary"]["actual"] == {
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
    }
    assert cases["validation_verification_targets_surface_to_manifest_summary"]["actual"] == {
        "validation_app_matrix": {
            "zoom": {
                "checks": ["Camera list shows AK Virtual Camera."],
                "name": "Zoom",
                "notes": "preview visible",
                "ready": True,
                "result": "pass",
                "reviewed": True,
                "status": "ok",
                "steps": ["Open Zoom > Settings > Video."],
                "validated": True,
            },
            "teams": {
                "checks": ["Device settings page shows AK Virtual Camera."],
                "evidence": {
                    "device_listed": False,
                    "device_selected": False,
                    "preview_visible": False,
                    "screenshot": "",
                },
                "name": "Teams",
                "notes": "device not shown",
                "ready": True,
                "result": "fail",
                "reviewed": True,
                "status": "missing",
                "steps": ["Open Teams > Settings > Devices."],
                "validated": False,
            },
        }
    }
    assert cases["validation_demo_summary_surfaces_to_manifest_summary"]["actual"] == {
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
    }
    assert cases["validation_benchmark_matrix_surfaces_to_manifest_summary"]["actual"] == {
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
    }
    assert cases["release_diagnostics_runtime_tool_fields_surface_to_manifest_summary"]["actual"] == {
        "release_command_tools_exist": True,
        "release_command_tools_signed": True,
        "release_command_tools_universal2_ready": True,
        "release_pkg_payload_appledouble_clean": True,
        "release_sync_ipc_tool_exists": True,
        "release_sync_ipc_tool_signed": True,
        "release_sync_ipc_tool_universal2_ready": True,
    }
    assert cases["runtime_release_product_identity_fields_surface_to_manifest_summary"]["actual"] == {
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
    }
    assert cases["runtime_topology_fields_surface_to_manifest_summary"]["actual"] == {
        "runtime_topology_kind": "camera_extension_direct_framebus",
        "runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
        "runtime_host_role": "container_activation_command_bridge",
        "runtime_host_in_frame_hot_path": False,
        "runtime_dedicated_host_daemon_required": False,
        "runtime_container_app_configured": True,
        "runtime_data_plane": "shared_memory_ringbuffer",
        "runtime_control_plane": "host_activation_plus_sync_ipc",
    }
    assert cases["validation_app_matrix_derives_counts_and_ids_when_summary_missing"]["actual"] == {
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
    }

    acceptance_cases = {
        item["name"]: item for item in payload["acceptance_merge_cases"]
    }
    entrypoints_cases = {
        item["name"]: item for item in payload["entrypoints_merge_cases"]
    }
    assert entrypoints_cases["entrypoints_contract_present_propagates_consistency_flags"]["actual"] == {
        "entrypoints_contract_present": True,
        "entrypoints_contract_passed": True,
        "entrypoints_contract_surface_complete": True,
        "entrypoints_contract_demo_case_complete": True,
        "entrypoints_contract_cli_case_complete": True,
        "entrypoints_contract_desktop_case_complete": True,
    }
    assert entrypoints_cases["entrypoints_contract_missing_resets_fields_to_none"]["actual"] == {
        "entrypoints_contract_present": False,
        "entrypoints_contract_passed": None,
        "entrypoints_contract_surface_complete": None,
        "entrypoints_contract_demo_case_complete": None,
        "entrypoints_contract_cli_case_complete": None,
        "entrypoints_contract_desktop_case_complete": None,
    }
    assert acceptance_cases["acceptance_summary_present_propagates_status_lists"]["actual"] == {
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
    }
    assert acceptance_cases["acceptance_summary_missing_resets_fields_to_none"]["actual"] == {
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
    }
