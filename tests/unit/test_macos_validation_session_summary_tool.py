# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation-session summary helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_validation_session_summary.py"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_macos_validation_session_summary_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "session-manifest.json" in text
    assert "validation_passed_app_ids" in text
    assert "validation_install_phase" in text
    assert "validation_install_ipc_ready" in text
    assert "install_session_ipc_ready" in text
    assert "target_apps_all_passed" in text
    assert "system_camera_device_visible" in text
    assert "auto_install_ready" in text
    assert "macos_13_plus_declared" in text
    assert "universal2_ready" in text
    assert "release_packaging_ready" in text
    assert "pyside6_path_exercised" in text
    assert "python_entrypoints_consistent" in text
    assert "runtime_assets_packaged" in text
    assert "Runtime Asset Provenance" in text
    assert "runtime_host_bundle_path" in text
    assert "runtime_extension_bundle_path" in text
    assert "runtime_package_install_command" in text
    assert "Runtime Topology" in text
    assert "runtime_topology_kind" in text
    assert "runtime_frame_path" in text
    assert "runtime_host_role" in text
    assert "runtime_host_in_frame_hot_path" in text
    assert "runtime_dedicated_host_daemon_required" in text
    assert "runtime_data_plane" in text
    assert "runtime_control_plane" in text
    assert "release_app_bundle_path" in text
    assert "runtime_release_product_identity_consistent" in text
    assert "sync_ipc_control_plane_ready" in text
    assert "Control-plane prerequisites satisfied" in text
    assert "acceptance_contract_present" in text
    assert "acceptance_contract_passed" in text
    assert "manual_app_validation_ready" in text
    assert "manual_app_validation_blockers" in text
    assert "validation_app_matrix" in text
    assert "validation_demo_mode" in text
    assert "validation_demo_camera_name" in text
    assert "validation_demo_consumer_count" in text
    assert "validation_demo_frame_source_kind" in text
    assert "validation_demo_python_entrypoint_kind" in text
    assert "validation_demo_sdk_streamer_factory_used" in text
    assert "validation_demo_sdk_latest_provider_factory_used" in text
    assert "validation_demo_sdk_direct_push_used" in text
    assert "Direct Push Evidence" in text
    assert "Direct Sender Object Evidence" in text
    assert "direct_push_demo_backend_name" in text
    assert "direct_push_demo_using_direct_sender" in text
    assert "direct_push_demo_direct_sender_state" in text
    assert "direct_sender_object_demo_backend_name" in text
    assert "direct_sender_object_demo_helper_hot_path_used" in text
    assert "smoke_direct_sender_object_demo_present" in text
    assert "install_session_direct_sender_object_demo_present" in text
    assert "smoke_direct_push_demo_backend_name" in text
    assert "install_session_direct_push_demo_backend_name" in text
    assert "smoke_direct_push_demo_present" in text
    assert "install_session_direct_push_demo_present" in text
    assert "validation_benchmark_kind" in text
    assert "validation_benchmark_matrix_profiles" in text
    assert "benchmark_matrix_complete" in text
    assert "benchmark_fps_targets_met" in text
    assert "Profiles covered" in text
    assert "Required profile set complete" in text
    assert "validation_reviewed_app_ids" in text
    assert "validation_observed_target_app_ids" in text
    assert "validation_missing_target_app_ids" in text
    assert "validation_unexpected_target_app_ids" in text
    assert "validation_target_app_ids_complete" in text
    assert "validation_manual_validation_ready" in text
    assert "validation_manual_validation_complete" in text
    assert "validation_manual_validation_all_passed" in text
    assert "Validation Status" in text
    assert "effective_shared_memory_name" in text
    assert "validation_install_ipc_transport" in text
    assert "install_session_shared_memory_name" in text
    assert "install_session_install_command_notarization_missing" in text
    assert "install_session_system_extension_registered" in text
    assert "List-Devices Binary Check" in text
    assert "list_devices_binary_check_present" in text
    assert "Sync IPC Tool" in text
    assert "Python Entrypoints" in text
    assert "entrypoints_contract_present" in text
    assert "sdk_contract_present" in text
    assert "sdk_contract_passed" in text
    assert "sdk_contract_constructor_shape_aligned" in text
    assert "sdk_contract_direct_sender_exports_present" in text
    assert "PySide6 Demo" in text
    assert "Benchmark Matrix" in text
    assert "Target App Details" in text
    assert "Validated apps" in text
    assert "Passed apps" in text
    assert "acceptance_failed_criteria" in text
    assert "Acceptance Contract" in text
    assert "--manifest" in text
    assert "--output" in text


def test_macos_validation_session_summary_tool_renders_markdown_summary(tmp_path) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    acceptance_report = session_dir / "session-acceptance.json"
    acceptance_contract_report = session_dir / "session-acceptance-contract.json"
    output_md = session_dir / "session-summary.md"

    _write_json(
        acceptance_report,
        {
            "summary": {
                "failed_count": 1,
                "unknown_count": 1,
                "failed_criteria": ["target_apps_all_passed"],
                "unknown_criteria": ["benchmark_1080p60_cpu_target_met"],
                "manual_app_validation_ready": False,
                "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                "manual_app_validation_unknown_criteria": ["notarization_tooling_ready"],
                "manual_app_validation_blockers": [
                    "system_camera_device_visible",
                    "notarization_tooling_ready",
                ],
            },
            "criteria": [
                {"name": "macos_13_plus_declared", "status": "pass"},
                {"name": "universal2_ready", "status": "pass"},
                {"name": "release_packaging_ready", "status": "pass"},
                {"name": "pyside6_path_exercised", "status": "pass"},
                {"name": "python_entrypoints_consistent", "status": "pass"},
                {"name": "target_apps_all_passed", "status": "fail"},
                {"name": "system_camera_device_visible", "status": "pass"},
                {"name": "benchmark_matrix_complete", "status": "pass"},
                {"name": "benchmark_fps_targets_met", "status": "pass"},
                {"name": "benchmark_1080p60_cpu_target_met", "status": "unknown"},
                {"name": "auto_install_ready", "status": "pass"},
                {"name": "signing_evidence_ready", "status": "pass"},
                {"name": "notarization_tooling_ready", "status": "unknown"},
                {"name": "runtime_assets_packaged", "status": "pass"},
                {"name": "sync_ipc_control_plane_ready", "status": "pass"},
            ],
        },
    )
    _write_json(
        acceptance_contract_report,
        {
            "consistency": {
                "all_checks_passed": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(acceptance_report),
                "acceptance_contract_report": str(acceptance_contract_report),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "manual_template": str(session_dir / "manual-results.template.json"),
            },
            "summary": {
                "artifact_check_passed": True,
                "acceptance_ready": False,
                "manual_app_validation_ready": False,
                "acceptance_contract_present": True,
                "acceptance_contract_passed": True,
                "effective_start_ready": False,
                "effective_start_blocker_code": "device_not_visible",
                "effective_devices": [],
                "effective_all_devices": ["FaceTime HD Camera"],
                "effective_device_prefix": "AK Virtual Camera",
                "effective_shared_memory_name": "/akvc-effective",
                "effective_mach_service_name": "com.akvc.effective",
                "effective_ipc_transport": "shared_memory_ringbuffer",
                "validation_devices": ["AK Virtual Camera"],
                "validation_all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                "validation_device_prefix": "AK Virtual Camera",
                "validation_shared_memory_name": "/akvc-validation",
                "validation_mach_service_name": "com.akvc.validation",
                "validation_ipc_transport": "validation_transport",
                "effective_supported_formats": ["1920x1080@30/60 NV12"],
                "effective_supported_frame_rates": [30, 60],
                "validation_install_present": True,
                "validation_install_success": True,
                "validation_install_phase": "installed_visible",
                "validation_install_start_ready": True,
                "validation_install_start_blocker_code": "ready",
                "validation_install_status_devices": ["AK Virtual Camera"],
                "validation_install_status_all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                "validation_install_device_prefix": "AK Virtual Camera",
                "validation_install_shared_memory_name": "/akvc-install",
                "validation_install_mach_service_name": "com.akvc.install",
                "validation_install_ipc_transport": "install_transport",
                "validation_install_supported_formats": ["1920x1080@30/60 NV12"],
                "validation_install_supported_frame_rates": [30, 60],
                "validation_install_ipc_probe_present": True,
                "validation_install_ipc_ready": True,
                "validation_install_ipc_environment_blocked": False,
                "validation_install_ipc_direct_open_errno": 0,
                "install_session_present": True,
                "install_session_success": True,
                "install_session_start_ready": True,
                "install_session_start_blocker_code": "ready",
                "install_session_devices": [],
                "install_session_all_devices": ["FaceTime HD Camera"],
                "install_session_device_prefix": "AK Virtual Camera",
                "install_session_shared_memory_name": "/akvc-session",
                "install_session_mach_service_name": "com.akvc.session",
                "install_session_ipc_transport": "session_transport",
                "install_session_ipc_probe_present": True,
                "install_session_ipc_ready": True,
                "install_session_ipc_environment_blocked": False,
                "install_session_ipc_direct_open_errno": 0,
                "install_session_sync_ipc_present": True,
                "install_session_sync_ipc_supported": True,
                "install_session_sync_ipc_success": True,
                "install_session_sync_ipc_phase": "sync_command_succeeded",
                "install_session_sync_ipc_shared_memory_name": "/akvc-session",
                "install_session_sync_ipc_transport": "shared_memory_ringbuffer",
                "install_session_sync_ipc_returncode": 0,
                "release_sync_ipc_tool_exists": True,
                "release_sync_ipc_tool_signed": True,
                "release_sync_ipc_tool_universal2_ready": True,
                "runtime_host_bundle_configured": True,
                "runtime_host_executable_configured": True,
                "runtime_extension_bundle_derived": True,
                "runtime_package_install_command_present": True,
                "runtime_auto_install_package": True,
                "runtime_status_tool_path": "/tmp/akvc-macos-status",
                "runtime_install_tool_path": "/tmp/akvc-macos-install",
                "runtime_devices_tool_path": "/tmp/akvc-macos-list-devices",
                "runtime_uninstall_tool_path": "/tmp/akvc-macos-uninstall",
                "runtime_sync_ipc_tool_path": "/tmp/akvc-macos-sync-ipc",
                "runtime_pkg_path": "/tmp/VirtualCamera.pkg",
                "runtime_host_bundle_path": "/Applications/Amaran Desktop.app",
                "runtime_host_executable_path": "/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop",
                "runtime_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                "runtime_topology_kind": "camera_extension_direct_framebus",
                "runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
                "runtime_host_role": "container_activation_command_bridge",
                "runtime_host_in_frame_hot_path": False,
                "runtime_dedicated_host_daemon_required": False,
                "runtime_container_app_configured": True,
                "runtime_data_plane": "shared_memory_ringbuffer",
                "runtime_control_plane": "host_activation_plus_sync_ipc",
                "runtime_package_install_command": [
                    "/usr/sbin/installer",
                    "-pkg",
                    "/tmp/VirtualCamera.pkg",
                    "-target",
                    "/",
                ],
                "release_app_bundle_path": "/Applications/Amaran Desktop.app",
                "release_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                "release_sync_ipc_tool_path": "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc",
                "release_pkg_path": "/tmp/VirtualCamera.pkg",
                "runtime_release_product_identity_consistent": True,
                "runtime_release_product_path_equal": False,
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": True,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": True,
                "entrypoints_contract_desktop_case_complete": True,
                "sdk_contract_present": True,
                "sdk_contract_passed": True,
                "sdk_contract_constructor_shape_aligned": True,
                "sdk_contract_direct_sender_exports_present": True,
                "validation_demo_present": True,
                "validation_demo_mode": "latest-provider",
                "validation_demo_mode_supported": True,
                "validation_demo_width": 1920,
                "validation_demo_height": 1080,
                "validation_demo_fps": 60.0,
                "validation_demo_duration": 5.0,
                "validation_demo_camera_name": "AKVC Demo",
                "validation_demo_consumer_count": 2,
                "validation_demo_video_path": "demo.mp4",
                "validation_demo_frame_source_kind": "latest_frame_provider",
                "validation_demo_python_entrypoint_kind": "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream",
                "validation_demo_sdk_streamer_factory_used": True,
                "validation_demo_sdk_latest_provider_factory_used": True,
                "validation_demo_sdk_direct_push_used": False,
                "direct_push_demo_present": True,
                "direct_push_demo_mode": "direct-push",
                "direct_push_demo_python_entrypoint_kind": "push_frame",
                "direct_push_demo_sdk_direct_push_used": True,
                "direct_push_demo_backend_name": "direct_sender",
                "direct_push_demo_using_direct_sender": True,
                "direct_push_demo_direct_sender_attempted": True,
                "direct_push_demo_direct_sender_state": "active",
                "direct_push_demo_runtime_topology_kind": "camera_extension_direct_sender",
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": False,
                "direct_push_demo_runtime_data_plane": "cmio_sink_stream_direct",
                "direct_push_demo_runtime_control_plane": "host_activation_only",
                "direct_push_demo_direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "direct_push_demo_direct_sender_last_error": None,
                "direct_push_demo_runtime_snapshot_present": True,
                "direct_push_demo_runtime_snapshot_started": True,
                "direct_push_demo_runtime_snapshot_shared_memory_name": "/akvc-direct",
                "direct_push_demo_runtime_snapshot_last_frame_format_name": "BGRA32",
                "direct_push_demo_requested_frames": 12,
                "direct_push_demo_frames_sent": 12,
                "smoke_direct_push_demo_present": True,
                "smoke_direct_push_demo_attempted": True,
                "smoke_direct_push_demo_skipped": False,
                "smoke_direct_push_demo_python_entrypoint_kind": "push_frame",
                "smoke_direct_push_demo_backend_name": "direct_sender",
                "smoke_direct_push_demo_using_direct_sender": True,
                "smoke_direct_push_demo_direct_sender_attempted": True,
                "smoke_direct_push_demo_direct_sender_state": "active",
                "smoke_direct_push_demo_runtime_topology_kind": "camera_extension_direct_sender",
                "smoke_direct_push_demo_helper_hot_path_used": False,
                "smoke_direct_push_demo_shared_memory_fallback_used": False,
                "smoke_direct_push_demo_runtime_data_plane": "cmio_sink_stream_direct",
                "smoke_direct_push_demo_runtime_control_plane": "host_activation_only",
                "smoke_direct_push_demo_direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "smoke_direct_push_demo_direct_sender_last_error": None,
                "smoke_direct_push_demo_runtime_snapshot_present": True,
                "smoke_direct_push_demo_runtime_snapshot_started": True,
                "smoke_direct_push_demo_runtime_snapshot_shared_memory_name": "/akvc-smoke",
                "smoke_direct_push_demo_runtime_snapshot_last_frame_format_name": "BGRA32",
                "smoke_direct_push_demo_requested_frames": 9,
                "smoke_direct_push_demo_frames_sent": 9,
                "install_session_direct_push_demo_present": True,
                "install_session_direct_push_demo_attempted": False,
                "install_session_direct_push_demo_skipped": True,
                "install_session_direct_push_demo_skip_reason": "ipc_environment_blocked",
                "install_session_direct_push_demo_python_entrypoint_kind": "push_frame",
                "install_session_direct_push_demo_backend_name": "shared_memory",
                "install_session_direct_push_demo_using_direct_sender": False,
                "install_session_direct_push_demo_direct_sender_attempted": True,
                "install_session_direct_push_demo_direct_sender_state": "fallback_shared_memory",
                "install_session_direct_push_demo_runtime_topology_kind": "camera_extension_direct_framebus",
                "install_session_direct_push_demo_runtime_data_plane": "shared_memory_ringbuffer",
                "install_session_direct_push_demo_runtime_control_plane": "host_activation_plus_sync_ipc",
                "install_session_direct_push_demo_direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "install_session_direct_push_demo_direct_sender_last_error": "camera device not found: AKVC Direct",
                "install_session_direct_push_demo_runtime_snapshot_present": True,
                "install_session_direct_push_demo_runtime_snapshot_started": True,
                "install_session_direct_push_demo_runtime_snapshot_shared_memory_name": "/akvc-install",
                "install_session_direct_push_demo_runtime_snapshot_last_frame_format_name": "NV12",
                "install_session_direct_push_demo_requested_frames": 7,
                "install_session_direct_push_demo_frames_sent": 0,
                "direct_sender_object_demo_present": True,
                "direct_sender_object_demo_mode": "direct-sender-object",
                "direct_sender_object_demo_python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
                "direct_sender_object_demo_backend_name": "direct_sender_object",
                "direct_sender_object_demo_using_direct_sender": True,
                "direct_sender_object_demo_direct_sender_state": "active",
                "direct_sender_object_demo_runtime_topology_kind": "camera_extension_direct_sender_object",
                "direct_sender_object_demo_helper_hot_path_used": False,
                "direct_sender_object_demo_shared_memory_fallback_used": False,
                "direct_sender_object_demo_runtime_data_plane": "cmio_sink_stream_direct",
                "direct_sender_object_demo_runtime_control_plane": "system_extension_preinstalled",
                "direct_sender_object_demo_direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "direct_sender_object_demo_requested_frames": 6,
                "direct_sender_object_demo_frames_sent": 6,
                "smoke_direct_sender_object_demo_present": True,
                "smoke_direct_sender_object_demo_attempted": True,
                "smoke_direct_sender_object_demo_skipped": False,
                "smoke_direct_sender_object_demo_backend_name": "direct_sender_object",
                "smoke_direct_sender_object_demo_using_direct_sender": True,
                "smoke_direct_sender_object_demo_direct_sender_state": "active",
                "smoke_direct_sender_object_demo_runtime_topology_kind": "camera_extension_direct_sender_object",
                "smoke_direct_sender_object_demo_helper_hot_path_used": False,
                "smoke_direct_sender_object_demo_shared_memory_fallback_used": False,
                "smoke_direct_sender_object_demo_direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "smoke_direct_sender_object_demo_requested_frames": 5,
                "smoke_direct_sender_object_demo_frames_sent": 5,
                "install_session_direct_sender_object_demo_present": True,
                "install_session_direct_sender_object_demo_attempted": False,
                "install_session_direct_sender_object_demo_skipped": True,
                "install_session_direct_sender_object_demo_skip_reason": "ipc_environment_blocked",
                "install_session_direct_sender_object_demo_backend_name": "direct_sender_object",
                "install_session_direct_sender_object_demo_using_direct_sender": True,
                "install_session_direct_sender_object_demo_direct_sender_state": "inspected",
                "install_session_direct_sender_object_demo_runtime_topology_kind": "camera_extension_direct_sender_object",
                "install_session_direct_sender_object_demo_helper_hot_path_used": False,
                "install_session_direct_sender_object_demo_shared_memory_fallback_used": False,
                "install_session_direct_sender_object_demo_direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "install_session_direct_sender_object_demo_requested_frames": 4,
                "install_session_direct_sender_object_demo_frames_sent": 0,
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": True,
                "list_devices_binary_check_device_prefix": "AK Virtual Camera",
                "list_devices_binary_check_filtered_device_count": 1,
                "list_devices_binary_check_total_device_count": 3,
                "list_devices_binary_check_override_no_match_ok": True,
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
                "validation_passed_app_ids": ["zoom", "obs"],
                "validation_reviewed_app_ids": ["teams", "zoom", "obs"],
                "validation_failed_app_ids": ["teams"],
                "validation_pending_app_ids": ["google_meet"],
                "validation_skipped_app_ids": ["quicktime"],
                "validation_unreviewed_app_ids": ["facetime"],
                "validation_observed_target_app_ids": [
                    "google_meet",
                    "obs",
                    "quicktime",
                    "teams",
                    "zoom",
                ],
                "validation_missing_target_app_ids": ["facetime"],
                "validation_unexpected_target_app_ids": [],
                "validation_target_app_ids_complete": False,
                "validation_validated_apps": 3,
                "validation_passed_apps": 2,
                "validation_failed_apps": 1,
                "validation_pending_apps": 1,
                "validation_skipped_apps": 1,
                "validation_manual_validation_ready": True,
                "validation_manual_validation_complete": False,
                "validation_manual_validation_all_passed": False,
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
                        "evidence": {
                            "device_listed": True,
                            "device_selected": True,
                            "preview_visible": True,
                            "screenshot": "artifacts/zoom.png",
                        },
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
                },
                "acceptance_failed_criteria": ["target_apps_all_passed"],
                "acceptance_unknown_criteria": ["benchmark_1080p60_cpu_target_met"],
                "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                "manual_app_validation_unknown_criteria": ["notarization_tooling_ready"],
                "manual_app_validation_blockers": [
                    "system_camera_device_visible",
                    "notarization_tooling_ready",
                ],
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--output",
            str(output_md),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = output_md.read_text(encoding="utf-8")
    assert "# AKVC macOS Validation Session Summary" in rendered
    assert "- Acceptance ready: `no`" in rendered
    assert "- Manual app validation ready: `no`" in rendered
    assert "- Acceptance contract passed: `yes`" in rendered
    assert "- Effective start blocker: `device_not_visible`" in rendered
    assert "- Effective devices: `-`" in rendered
    assert "- Effective all devices: `FaceTime HD Camera`" in rendered
    assert "- Effective device prefix: `AK Virtual Camera`" in rendered
    assert "- Effective shared memory: `/akvc-effective`" in rendered
    assert "## Device Name Cohesion" in rendered
    assert "- Demo camera name matches effective prefix: `no`" in rendered
    assert "- Validation device prefix matches effective prefix: `yes`" in rendered
    assert "- Install snapshot device prefix matches effective prefix: `yes`" in rendered
    assert "- Install session device prefix matches effective prefix: `yes`" in rendered
    assert "- List-devices binary-check prefix matches effective prefix: `yes`" in rendered
    assert "## Validation Status" in rendered
    assert "- Devices: `AK Virtual Camera`" in rendered
    assert "- All devices: `FaceTime HD Camera, AK Virtual Camera`" in rendered
    assert "- Device prefix: `AK Virtual Camera`" in rendered
    assert "- Shared memory: `/akvc-validation`" in rendered
    assert "## Installation Snapshot" in rendered
    assert "- Status devices: `AK Virtual Camera`" in rendered
    assert "- Status all devices: `FaceTime HD Camera, AK Virtual Camera`" in rendered
    assert "- IPC transport: `install_transport`" in rendered
    assert "## Install Session" in rendered
    assert "- Session devices: `-`" in rendered
    assert "- Session all devices: `FaceTime HD Camera`" in rendered
    assert "- Session device prefix: `AK Virtual Camera`" in rendered
    assert "- Session shared memory: `/akvc-session`" in rendered
    assert "## List-Devices Binary Check" in rendered
    assert "## Runtime Topology" in rendered
    assert "- Topology kind: `camera_extension_direct_framebus`" in rendered
    assert "- Host in frame hot path: `no`" in rendered
    assert "- Dedicated host daemon required: `no`" in rendered
    assert "- Data plane: `shared_memory_ringbuffer`" in rendered
    assert "- Control plane: `host_activation_plus_sync_ipc`" in rendered
    assert "## Sync IPC Tool" in rendered
    assert "## Python Entrypoints" in rendered
    assert "- entrypoints_contract_report: `" in rendered
    assert "- sdk_contract_report: `" in rendered
    assert "## PySide6 Demo" in rendered
    assert "## Benchmark Matrix" in rendered
    assert "## Manual App Validation Readiness" in rendered
    assert "## Acceptance Gates" in rendered
    assert "## Acceptance Contract" in rendered
    assert "## Target App Details" in rendered
    assert "- Present: `yes`" in rendered
    assert "- Success: `yes`" in rendered
    assert "- Phase: `installed_visible`" in rendered
    assert "- IPC ready: `yes`" in rendered
    assert "- IPC environment blocked: `no`" in rendered
    assert "- Session present: `yes`" in rendered
    assert "- Session success: `yes`" in rendered
    assert "- Session IPC ready: `yes`" in rendered
    assert "- Exists: `yes`" in rendered
    assert "- Signed: `yes`" in rendered
    assert "- Universal2 ready: `yes`" in rendered
    assert "- Runtime sync present: `yes`" in rendered
    assert "- Runtime sync supported: `yes`" in rendered
    assert "- Runtime sync success: `yes`" in rendered
    assert "- Runtime sync phase: `sync_command_succeeded`" in rendered
    assert "- Runtime sync shared memory: `/akvc-session`" in rendered
    assert "- Runtime sync transport: `shared_memory_ringbuffer`" in rendered
    assert "- Control-plane prerequisites satisfied: `yes`" in rendered
    assert "- Present: `yes`" in rendered
    assert "- Passed: `yes`" in rendered
    assert "- Surface complete: `yes`" in rendered
    assert "- Demo case complete: `yes`" in rendered
    assert "- CLI case complete: `yes`" in rendered
    assert "- Desktop case complete: `yes`" in rendered
    assert "- SDK contract present: `yes`" in rendered
    assert "- SDK contract passed: `yes`" in rendered
    assert "- SDK constructor shape aligned: `yes`" in rendered
    assert "- SDK direct sender exports present: `yes`" in rendered
    assert "- Present: `yes`" in rendered
    assert "- Passed: `yes`" in rendered
    assert "- Device prefix: `AK Virtual Camera`" in rendered
    assert "- Filtered devices: `1`" in rendered
    assert "- Total devices: `3`" in rendered
    assert "- Override no-match OK: `yes`" in rendered
    assert "- Mode: `latest-provider`" in rendered
    assert "- Mode supported: `yes`" in rendered
    assert "- Width: `1920`" in rendered
    assert "- Height: `1080`" in rendered
    assert "- FPS: `60.0`" in rendered
    assert "- Duration: `5.0`" in rendered
    assert "- Camera name: `AKVC Demo`" in rendered
    assert "- Consumer count: `2`" in rendered
    assert "- Video path: `demo.mp4`" in rendered
    assert "- Frame source: `latest_frame_provider`" in rendered
    assert "- Python entrypoint: `create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream`" in rendered
    assert "- SDK streamer factory used: `yes`" in rendered
    assert "- SDK latest-provider factory used: `yes`" in rendered
    assert "- SDK direct push used: `no`" in rendered
    assert "## Direct Push Evidence" in rendered
    assert "- Session report present: `yes`" in rendered
    assert "- Session report mode: `direct-push`" in rendered
    assert "- Session report entrypoint: `push_frame`" in rendered
    assert "- Session report backend: `direct_sender`" in rendered
    assert "- Session report using direct sender: `yes`" in rendered
    assert "- Session report direct sender attempted: `yes`" in rendered
    assert "- Session report direct sender state: `active`" in rendered
    assert "- Session report topology kind: `camera_extension_direct_sender`" in rendered
    assert "- Session report host in frame hot path: `no`" in rendered
    assert "- Session report helper hot path used: `no`" in rendered
    assert "- Session report shared-memory fallback used: `no`" in rendered
    assert "- Session report data plane: `cmio_sink_stream_direct`" in rendered
    assert "- Session report control plane: `host_activation_only`" in rendered
    assert "- Session report direct sender library: `/tmp/libakvc-macos-direct-sender.dylib`" in rendered
    assert "- Session report direct sender error: `-`" in rendered
    assert "- Session report runtime snapshot present: `yes`" in rendered
    assert "- Session report runtime snapshot started: `yes`" in rendered
    assert "- Session report runtime snapshot shared memory: `/akvc-direct`" in rendered
    assert "- Session report runtime snapshot last frame format: `BGRA32`" in rendered
    assert "- Session report requested frames: `12`" in rendered
    assert "- Session report frames sent: `12`" in rendered
    assert "- Smoke direct-push present: `yes`" in rendered
    assert "- Smoke direct-push attempted: `yes`" in rendered
    assert "- Smoke direct-push skipped: `no`" in rendered
    assert "- Smoke direct-push backend: `direct_sender`" in rendered
    assert "- Smoke direct-push using direct sender: `yes`" in rendered
    assert "- Smoke direct-push direct sender attempted: `yes`" in rendered
    assert "- Smoke direct-push direct sender state: `active`" in rendered
    assert "- Smoke direct-push topology kind: `camera_extension_direct_sender`" in rendered
    assert "- Smoke direct-push helper hot path used: `no`" in rendered
    assert "- Smoke direct-push shared-memory fallback used: `no`" in rendered
    assert "- Smoke direct-push data plane: `cmio_sink_stream_direct`" in rendered
    assert "- Smoke direct-push control plane: `host_activation_only`" in rendered
    assert "- Smoke direct-push direct sender library: `/tmp/libakvc-macos-direct-sender.dylib`" in rendered
    assert "- Smoke direct-push direct sender error: `-`" in rendered
    assert "- Smoke direct-push runtime snapshot present: `yes`" in rendered
    assert "- Smoke direct-push runtime snapshot started: `yes`" in rendered
    assert "- Smoke direct-push runtime snapshot shared memory: `/akvc-smoke`" in rendered
    assert "- Smoke direct-push runtime snapshot last frame format: `BGRA32`" in rendered
    assert "- Smoke direct-push requested frames: `9`" in rendered
    assert "- Smoke direct-push frames sent: `9`" in rendered
    assert "- Install-session direct-push present: `yes`" in rendered
    assert "- Install-session direct-push attempted: `no`" in rendered
    assert "- Install-session direct-push skipped: `yes`" in rendered
    assert "- Install-session direct-push skip reason: `ipc_environment_blocked`" in rendered
    assert "- Install-session direct-push backend: `shared_memory`" in rendered
    assert "- Install-session direct-push using direct sender: `no`" in rendered
    assert "- Install-session direct-push direct sender attempted: `yes`" in rendered
    assert "- Install-session direct-push direct sender state: `fallback_shared_memory`" in rendered
    assert "- Install-session direct-push topology kind: `camera_extension_direct_framebus`" in rendered
    assert "- Install-session direct-push helper hot path used: `unknown`" in rendered
    assert "- Install-session direct-push shared-memory fallback used: `unknown`" in rendered
    assert "- Install-session direct-push data plane: `shared_memory_ringbuffer`" in rendered
    assert "- Install-session direct-push control plane: `host_activation_plus_sync_ipc`" in rendered
    assert "- Install-session direct-push direct sender library: `/tmp/libakvc-macos-direct-sender.dylib`" in rendered
    assert "- Install-session direct-push direct sender error: `camera device not found: AKVC Direct`" in rendered
    assert "- Install-session direct-push runtime snapshot present: `yes`" in rendered
    assert "- Install-session direct-push runtime snapshot started: `yes`" in rendered
    assert "- Install-session direct-push runtime snapshot shared memory: `/akvc-install`" in rendered
    assert "- Install-session direct-push runtime snapshot last frame format: `NV12`" in rendered
    assert "- Install-session direct-push requested frames: `7`" in rendered
    assert "- Install-session direct-push frames sent: `0`" in rendered
    assert "## Direct Sender Object Evidence" in rendered
    assert "- Session object report present: `yes`" in rendered
    assert "- Session object report mode: `direct-sender-object`" in rendered
    assert "- Session object report entrypoint: `MacDirectCameraSender.send(auto-open)`" in rendered
    assert "- Session object report backend: `direct_sender_object`" in rendered
    assert "- Session object report helper hot path used: `no`" in rendered
    assert "- Session object report shared-memory fallback used: `no`" in rendered
    assert "- Session object report requested frames: `6`" in rendered
    assert "- Session object report frames sent: `6`" in rendered
    assert "- Smoke object-demo present: `yes`" in rendered
    assert "- Smoke object-demo attempted: `yes`" in rendered
    assert "- Smoke object-demo skipped: `no`" in rendered
    assert "- Smoke object-demo backend: `direct_sender_object`" in rendered
    assert "- Smoke object-demo requested frames: `5`" in rendered
    assert "- Smoke object-demo frames sent: `5`" in rendered
    assert "- Install-session object-demo present: `yes`" in rendered
    assert "- Install-session object-demo attempted: `no`" in rendered
    assert "- Install-session object-demo skipped: `yes`" in rendered
    assert "- Install-session object-demo skip reason: `ipc_environment_blocked`" in rendered
    assert "- Install-session object-demo backend: `direct_sender_object`" in rendered
    assert "- Install-session object-demo direct sender state: `inspected`" in rendered
    assert "- Install-session object-demo requested frames: `4`" in rendered
    assert "- Install-session object-demo frames sent: `0`" in rendered
    assert "- Kind: `benchmark_matrix`" in rendered
    assert "- Profiles covered: `720p30, 1080p60`" in rendered
    assert "- Required profile set complete: `no`" in rendered
    assert "- Matrix complete gate: `pass`" in rendered
    assert "- FPS targets met: `pass`" in rendered
    assert "- 1080p60 CPU target met: `unknown`" in rendered
    assert "- 720p30: 1280x720@30.0 fps_target_met=`yes` cpu_target_applies=`no` cpu_target_met=`unknown` actual_fps=`29.8` cpu_percent=`3.1` avg_latency_ms=`0.7`" in rendered
    assert "- 1080p60: 1920x1080@60.0 fps_target_met=`yes` cpu_target_applies=`yes` cpu_target_met=`yes` actual_fps=`59.6` cpu_percent=`8.4` avg_latency_ms=`1.1`" in rendered
    assert "- Ready: `no`" in rendered
    assert "- Failed prerequisites: `系统已枚举到虚拟摄像头`" in rendered
    assert "- Unknown prerequisites: `公证工具链已就绪`" in rendered
    assert "- Combined blockers: `系统已枚举到虚拟摄像头, 公证工具链已就绪`" in rendered
    assert "- macOS 13+ declared: `pass`" in rendered
    assert "- Universal2 ready: `pass`" in rendered
    assert "- Release packaging ready: `pass`" in rendered
    assert "- PySide6 path exercised: `pass`" in rendered
    assert "- Python entrypoints consistent: `pass`" in rendered
    assert "- Target apps all passed: `fail`" in rendered
    assert "- System camera device visible: `pass`" in rendered
    assert "- Benchmark matrix complete: `pass`" in rendered
    assert "- Benchmark FPS targets met: `pass`" in rendered
    assert "- Auto install ready: `pass`" in rendered
    assert "- Signing evidence ready: `pass`" in rendered
    assert "- Notarization tooling ready: `unknown`" in rendered
    assert "- Runtime assets packaged: `pass`" in rendered
    assert "- Sync IPC control plane ready: `pass`" in rendered
    assert "- Passed: `zoom, obs`" in rendered
    assert "- Failed: `teams`" in rendered
    assert "- Pending: `google_meet`" in rendered
    assert "- Skipped: `quicktime`" in rendered
    assert "- Reviewed: `teams, zoom, obs`" in rendered
    assert "- Unreviewed: `facetime`" in rendered
    assert "- Observed target ids: `google_meet, obs, quicktime, teams, zoom`" in rendered
    assert "- Target id set complete: `no`" in rendered
    assert "- Missing target ids: `facetime`" in rendered
    assert "- Unexpected target ids: `-`" in rendered
    assert "- Validated apps: `3`" in rendered
    assert "- Passed apps: `2`" in rendered
    assert "- Failed apps: `1`" in rendered
    assert "- Pending apps: `1`" in rendered
    assert "- Skipped apps: `1`" in rendered
    assert "## Runtime Asset Provenance" in rendered
    assert "- Container app bundle path: `/Applications/Amaran Desktop.app`" in rendered
    assert "- Extension bundle path: `/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension`" in rendered
    assert "- Package install command: `/usr/sbin/installer -pkg /tmp/VirtualCamera.pkg -target /`" in rendered
    assert "- Release container app bundle path: `/Applications/Amaran Desktop.app`" in rendered
    assert "- Runtime/release product identity consistent: `yes`" in rendered
    assert "- Runtime/release product path equal: `no`" in rendered
    assert "- Manual validation ready: `yes`" in rendered
    assert "- Review complete: `no`" in rendered
    assert "- All target apps passed manually: `no`" in rendered
    assert "- teams (Teams): result=`fail` reviewed=`yes` validated=`no` ready=`yes` status=`missing` steps=`1` checks=`1` listed=`no` selected=`no` preview=`no` notes=`device not shown` first_step=`Open Teams > Settings > Devices.` first_check=`Device settings page shows AK Virtual Camera.`" in rendered
    assert "- zoom (Zoom): result=`pass` reviewed=`yes` validated=`yes` ready=`yes` status=`ok` steps=`1` checks=`1` listed=`yes` selected=`yes` preview=`yes` screenshot=`artifacts/zoom.png` notes=`preview visible` first_step=`Open Zoom > Settings > Video.` first_check=`Camera list shows AK Virtual Camera.`" in rendered
    assert "- Failed criteria: `target_apps_all_passed`" in rendered
    assert "- Unknown criteria: `benchmark_1080p60_cpu_target_met`" in rendered
    assert "- Present: `yes`" in rendered
    assert "- Passed: `yes`" in rendered
    assert "- acceptance_contract_report: `" in rendered


def test_macos_validation_session_summary_tool_falls_back_to_manifest_acceptance_gates(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    output_md = session_dir / "session-summary.md"

    _write_json(
        manifest,
        {
            "artifacts": {},
            "summary": {
                "acceptance_ready": False,
                "manual_app_validation_ready": False,
                "acceptance_contract_present": None,
                "acceptance_contract_passed": None,
                "acceptance_failed_count": 1,
                "acceptance_unknown_count": 2,
                "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                "manual_app_validation_unknown_criteria": ["benchmark_matrix_complete"],
                "manual_app_validation_blockers": [
                    "system_camera_device_visible",
                    "benchmark_matrix_complete",
                ],
                "macos_13_plus_declared": "pass",
                "universal2_ready": "pass",
                "release_packaging_ready": "pass",
                "pyside6_path_exercised": "pass",
                "python_entrypoints_consistent": "pass",
                "target_apps_all_passed": "fail",
                "system_camera_device_visible": "pass",
                "benchmark_matrix_complete": "fail",
                "benchmark_fps_targets_met": "unknown",
                "auto_install_ready": "pass",
                "signing_evidence_ready": "pass",
                "notarization_tooling_ready": "unknown",
                "benchmark_1080p60_cpu_target_met": "unknown",
                "runtime_assets_packaged": "pass",
                "sync_ipc_control_plane_ready": "pass",
                "release_sync_ipc_tool_exists": True,
                "release_sync_ipc_tool_signed": True,
                "release_sync_ipc_tool_universal2_ready": True,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--output",
            str(output_md),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = output_md.read_text(encoding="utf-8")
    assert "- macOS 13+ declared: `pass`" in rendered
    assert "- Manual app validation ready: `no`" in rendered
    assert "- Universal2 ready: `pass`" in rendered
    assert "- Target apps all passed: `fail`" in rendered
    assert "- System camera device visible: `pass`" in rendered
    assert "- Auto install ready: `pass`" in rendered
    assert "- Python entrypoints consistent: `pass`" in rendered
    assert "- Runtime assets packaged: `pass`" in rendered
    assert "- Sync IPC control plane ready: `pass`" in rendered
    assert "- Benchmark matrix complete: `fail`" in rendered
    assert "- Benchmark FPS targets met: `unknown`" in rendered
    assert "- Failed prerequisites: `系统已枚举到虚拟摄像头`" in rendered
    assert "- Unknown prerequisites: `性能矩阵完整`" in rendered
    assert "- Combined blockers: `系统已枚举到虚拟摄像头, 性能矩阵完整`" in rendered
    assert "- Control-plane prerequisites satisfied: `unknown`" in rendered
    assert "- Manual validation ready: `unknown`" in rendered
    assert "- Review complete: `unknown`" in rendered
    assert "- All target apps passed manually: `unknown`" in rendered
    assert "- Acceptance failed count: `1`" in rendered
    assert "- Acceptance unknown count: `2`" in rendered
    assert "- Acceptance contract passed: `unknown`" in rendered
    assert "## Acceptance Contract" in rendered
    assert "- Present: `unknown`" in rendered
    assert "- Passed: `unknown`" in rendered
    assert "- `-`" in rendered
    assert "- Observed target ids: `-`" in rendered
    assert "## PySide6 Demo" in rendered
    assert "- Mode: `-`" in rendered
    assert "- Frame source: `-`" in rendered


def test_macos_validation_session_summary_tool_derives_target_app_groups_from_app_matrix(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    output_md = session_dir / "session-summary.md"

    _write_json(
        manifest,
        {
            "artifacts": {},
            "summary": {
                "validation_app_matrix": {
                    "zoom": {
                        "name": "Zoom",
                        "reviewed": True,
                        "validated": True,
                        "result": "pass",
                        "notes": "preview visible",
                        "ready": True,
                        "status": "ok",
                    },
                    "teams": {
                        "name": "Teams",
                        "reviewed": True,
                        "validated": False,
                        "result": "fail",
                        "notes": "device missing",
                        "ready": True,
                        "status": "missing",
                    },
                    "google_meet": {
                        "name": "Google Meet",
                        "reviewed": True,
                        "validated": False,
                        "result": "pending",
                        "notes": "manual verification pending",
                        "ready": True,
                        "status": "pending",
                    },
                    "quicktime": {
                        "name": "QuickTime",
                        "reviewed": False,
                        "validated": False,
                        "result": "skipped",
                        "notes": "not yet reviewed",
                        "ready": True,
                        "status": "pending_review",
                    },
                },
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--output",
            str(output_md),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = output_md.read_text(encoding="utf-8")
    assert "- Validated apps: `3`" in rendered
    assert "- Passed apps: `1`" in rendered
    assert "- Failed apps: `1`" in rendered
    assert "- Pending apps: `1`" in rendered
    assert "- Skipped apps: `1`" in rendered
    assert "- Passed: `zoom`" in rendered
    assert "- Failed: `teams`" in rendered
    assert "- Pending: `google_meet`" in rendered
    assert "- Skipped: `quicktime`" in rendered
    assert "- Observed target ids: `-`" in rendered
    assert "- Unreviewed: `quicktime`" in rendered
