# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation-session acceptance helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_validation_session_acceptance.py"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _passing_app_matrix() -> dict[str, dict[str, object]]:
    return {
        app_id: {
            "name": app_id,
            "reviewed": True,
            "validated": True,
            "result": "pass",
            "ready": True,
            "status": "ok",
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


def test_macos_validation_session_acceptance_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "session-manifest.json" in text
    assert "acceptance_ready" in text
    assert "manual_app_validation_ready" in text
    assert "manual_app_validation_blockers" in text
    assert "target_apps_all_passed" in text
    assert "EXPECTED_APP_IDS" in text
    assert 'summary.get("validation_observed_target_app_ids")' in text
    assert 'summary.get("validation_missing_target_app_ids")' in text
    assert 'summary.get("validation_unexpected_target_app_ids")' in text
    assert "benchmark_matrix_complete" in text
    assert "benchmark_1080p60_cpu_target_met" in text
    assert "system_camera_device_visible" in text
    assert "list_devices_binary_check_passed" in text
    assert "sync_ipc_control_plane_ready" in text
    assert "python_direct_runtime_ready" in text
    assert "python_entrypoints_consistent" in text
    assert "DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES" in text
    assert "pure_direct_runtime" in text
    assert "entrypoints_contract_report" in text
    assert "sdk_contract_report" in text
    assert "sdk_contract_passed" in text
    assert "sdk_contract_direct_sender_exports_present" in text
    assert 'release_summary.get("universal2_ready")' in text
    assert "_all_true_or_false_or_none" in text
    assert "--manifest" in text
    assert "--output" in text


def test_macos_validation_session_acceptance_tool_reports_complete_acceptance(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "release_minimum_system_version_expected": True,
                "release_universal2_ready": True,
                "release_artifacts_present": True,
                "release_pkg_includes_extension_payload": True,
                "release_pkg_payload_appledouble_clean": True,
                "release_host_embeds_extension_bundle": True,
                "release_app_signed": True,
                "release_extension_signed": True,
                "release_pkg_signed": True,
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
    )
    _write_json(
        session_dir / "preflight.json",
        {"readiness": {"can_notarize": True, "can_staple": True}},
    )
    _write_json(
        session_dir / "benchmark.json",
        {
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
    )
    _write_json(
        session_dir / "release-diagnostics.json",
        {
            "summary": {
                "command_tools_signed": True,
                "sync_ipc_tool_exists": True,
                "sync_ipc_tool_signed": True,
                "sync_ipc_tool_universal2_ready": True,
                "app_gatekeeper_accepted": True,
                "app_stapled": True,
                "pkg_gatekeeper_accepted": True,
                "pkg_stapled": True,
            }
        },
    )
    _write_json(
        session_dir / "entrypoints-contract.json",
        {
            "consistency": {
                "all_checks_passed": True,
                "surface_complete": True,
                "demo_case_complete": True,
                "cli_case_complete": True,
                "desktop_case_complete": True,
            }
        },
    )
    _write_json(
        session_dir / "sdk-contract.json",
        {
            "consistency": {
                "all_checks_passed": True,
                "constructor_shape_aligned": True,
                "direct_sender_exports_present": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "preflight_report": str(session_dir / "preflight.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
                "demo_report": str(session_dir / "demo-report.json"),
                "benchmark_report": str(session_dir / "benchmark.json"),
                "manual_template": str(session_dir / "manual-results.template.json"),
                "validation_report": str(session_dir / "validation-report.json"),
                "smoke_report": str(session_dir / "smoke-report.json"),
                "install_session_report": str(session_dir / "install-session-report.json"),
                "framebus_roundtrip_report": str(session_dir / "framebus-roundtrip.json"),
                "status_binary_check_report": str(session_dir / "status-binary-check.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
            },
            "steps": {"validation_report": {"returncode": 0}},
            "summary": {
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
                "install_session_sync_ipc_shared_memory_name": "/akvc-install-session",
                "install_session_sync_ipc_transport": "shared_memory_ringbuffer",
                "runtime_release_product_identity_consistent": True,
                "runtime_release_product_path_equal": False,
                "runtime_host_bundle_path": "/Applications/Amaran Desktop.app",
                "runtime_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                "runtime_sync_ipc_tool_path": "/tmp/runtime/akvc-macos-sync-ipc",
                "runtime_pkg_path": "/tmp/VirtualCamera.pkg",
                "release_app_bundle_path": "/Applications/Amaran Desktop.app",
                "release_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                "release_sync_ipc_tool_path": "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc",
                "release_pkg_path": "/tmp/VirtualCamera.pkg",
                "effective_device_prefix": "AK Virtual Camera",
                "validation_device_prefix": "AK Virtual Camera",
                "validation_install_device_prefix": "AK Virtual Camera",
                "install_session_device_prefix": "AK Virtual Camera",
                "validation_demo_camera_name": "AK Virtual Camera",
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": True,
                "list_devices_binary_check_device_prefix": "AK Virtual Camera",
                "list_devices_binary_check_filtered_device_count": 1,
                "list_devices_binary_check_total_device_count": 3,
                "list_devices_binary_check_override_no_match_ok": True,
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
                "artifact_check_present": True,
                "artifact_check_passed": True,
                "direct_push_demo_returncode": 0,
                "direct_push_demo_using_direct_sender": True,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": False,
                "direct_push_demo_direct_only": True,
                "direct_push_demo_allow_shared_memory_fallback": False,
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_runtime_dedicated_host_daemon_required": False,
                "direct_push_demo_runtime_data_plane": "cmio_sink_stream_direct",
                "direct_push_demo_runtime_control_plane": "host_activation_only",
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["summary"]["acceptance_ready"] is True
    assert payload["summary"]["manual_app_validation_ready"] is True
    assert payload["summary"]["manual_app_validation_blockers"] == []
    assert payload["summary"]["failed_count"] == 0
    assert payload["summary"]["unknown_count"] == 0
    target_apps = next(
        item for item in payload["criteria"] if item["name"] == "target_apps_all_passed"
    )
    assert target_apps["evidence"]["expected_target_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
        "zoom",
    ]
    assert target_apps["evidence"]["passed_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
        "zoom",
    ]
    assert target_apps["evidence"]["failed_app_ids"] == []
    assert target_apps["evidence"]["pending_app_ids"] == []
    assert target_apps["evidence"]["unreviewed_app_ids"] == []
    assert target_apps["evidence"]["missing_target_app_ids"] == []
    assert target_apps["evidence"]["unexpected_target_app_ids"] == []
    assert target_apps["evidence"]["target_app_missing_evidence_ids"] == []
    auto_install = next(
        item for item in payload["criteria"] if item["name"] == "auto_install_ready"
    )
    assert auto_install["status"] == "pass"
    assert auto_install["evidence"]["install_session_ipc_probe_present"] is True
    assert auto_install["evidence"]["install_session_ipc_ready"] is True
    device_visible = next(
        item for item in payload["criteria"] if item["name"] == "system_camera_device_visible"
    )
    assert device_visible["status"] == "pass"
    assert device_visible["evidence"]["effective_device_prefix"] == "AK Virtual Camera"
    assert device_visible["evidence"]["validation_demo_camera_name"] == "AK Virtual Camera"
    assert device_visible["evidence"]["demo_camera_name_matches_effective_prefix"] is True
    assert device_visible["evidence"]["validation_device_prefix_matches_effective_prefix"] is True
    assert device_visible["evidence"]["validation_install_device_prefix_matches_effective_prefix"] is True
    assert device_visible["evidence"]["install_session_device_prefix_matches_effective_prefix"] is True
    assert device_visible["evidence"]["list_devices_binary_check_device_prefix_matches_effective_prefix"] is True
    assert device_visible["evidence"]["list_devices_binary_check_present"] is True
    assert device_visible["evidence"]["list_devices_binary_check_passed"] is True
    assert device_visible["evidence"]["list_devices_binary_check_filtered_device_count"] == 1
    assert device_visible["evidence"]["list_devices_binary_check_device_prefix"] == "AK Virtual Camera"
    benchmark_matrix = next(
        item for item in payload["criteria"] if item["name"] == "benchmark_matrix_complete"
    )
    assert benchmark_matrix["status"] == "pass"
    assert benchmark_matrix["evidence"]["expected_benchmark_profiles"] == [
        "720p30",
        "720p60",
        "1080p30",
        "1080p60",
        "4k30",
        "4k60",
    ]
    assert benchmark_matrix["evidence"]["benchmark_acceptance"]["required_profiles_present"] is True
    pyside6 = next(
        item for item in payload["criteria"] if item["name"] == "pyside6_path_exercised"
    )
    assert pyside6["status"] == "pass"
    assert pyside6["evidence"]["demo_mode"] == "latest-provider"
    assert pyside6["evidence"]["demo_mode_supported"] is True
    assert pyside6["evidence"]["demo_frame_source_kind"] == "latest_frame_provider"
    assert pyside6["evidence"]["expected_frame_source_kind"] == "latest_frame_provider"
    assert pyside6["evidence"]["frame_source_supported"] is True
    direct_runtime = next(
        item for item in payload["criteria"] if item["name"] == "python_direct_runtime_ready"
    )
    assert direct_runtime["status"] == "pass"
    assert direct_runtime["evidence"]["selected_source"] == "direct_push_demo"
    assert direct_runtime["evidence"]["selected_candidate"]["pure_direct_runtime"] is True
    entrypoints = next(
        item for item in payload["criteria"] if item["name"] == "python_entrypoints_consistent"
    )
    assert entrypoints["status"] == "pass"
    assert entrypoints["evidence"]["entrypoints_contract_present"] is True
    assert entrypoints["evidence"]["entrypoints_contract_passed"] is True
    assert entrypoints["evidence"]["entrypoints_contract_surface_complete"] is True
    assert entrypoints["evidence"]["entrypoints_contract_demo_case_complete"] is True
    assert entrypoints["evidence"]["entrypoints_contract_cli_case_complete"] is True
    assert entrypoints["evidence"]["entrypoints_contract_desktop_case_complete"] is True
    assert entrypoints["evidence"]["sdk_contract_present"] is True
    assert entrypoints["evidence"]["sdk_contract_passed"] is True
    assert entrypoints["evidence"]["sdk_contract_constructor_shape_aligned"] is True
    assert entrypoints["evidence"]["sdk_contract_direct_sender_exports_present"] is True
    sync_ipc = next(
        item for item in payload["criteria"] if item["name"] == "sync_ipc_control_plane_ready"
    )
    assert sync_ipc["status"] == "pass"
    assert sync_ipc["critical"] is False
    assert sync_ipc["evidence"]["release_sync_ipc_tool_exists"] is True
    assert sync_ipc["evidence"]["release_sync_ipc_tool_signed"] is True
    assert sync_ipc["evidence"]["release_sync_ipc_tool_universal2_ready"] is True
    assert sync_ipc["evidence"]["install_session_sync_ipc_present"] is True
    assert sync_ipc["evidence"]["install_session_sync_ipc_supported"] is True
    assert sync_ipc["evidence"]["install_session_sync_ipc_success"] is True
    assert sync_ipc["evidence"]["install_session_sync_ipc_phase"] == "sync_command_succeeded"
    release_packaging = next(
        item for item in payload["criteria"] if item["name"] == "release_packaging_ready"
    )
    assert release_packaging["status"] == "pass"
    assert release_packaging["evidence"]["release_pkg_payload_appledouble_clean"] is True
    assert release_packaging["evidence"]["runtime_release_product_identity_consistent"] is True
    assert release_packaging["evidence"]["runtime_release_product_path_equal"] is False
    assert release_packaging["evidence"]["pkg_payload_appledouble_clean"] is None


def test_macos_validation_session_acceptance_tool_accepts_qimage_direct_demo_mode(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "demo_present": True,
                "demo_mode": "image",
                "demo_mode_supported": True,
                "demo_frame_source_kind": "qimage_direct",
            }
        },
    )
    _write_json(
        session_dir / "demo-report.json",
        {"mode": "image", "frame_source_kind": "qimage_direct"},
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "demo_report": str(session_dir / "demo-report.json"),
            },
            "summary": {},
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    pyside6 = next(
        item for item in payload["criteria"] if item["name"] == "pyside6_path_exercised"
    )
    assert pyside6["status"] == "pass"
    assert pyside6["evidence"]["demo_mode"] == "image"
    assert pyside6["evidence"]["demo_mode_supported"] is True
    assert pyside6["evidence"]["demo_frame_source_kind"] == "qimage_direct"
    assert pyside6["evidence"]["expected_frame_source_kind"] == "qimage_direct"
    assert pyside6["evidence"]["frame_source_supported"] is True


def test_macos_validation_session_acceptance_tool_accepts_numpy_direct_demo_mode(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "demo_present": True,
                "demo_mode": "numpy-direct",
                "demo_mode_supported": True,
                "demo_frame_source_kind": "numpy_direct",
            }
        },
    )
    _write_json(
        session_dir / "demo-report.json",
        {"mode": "numpy-direct", "frame_source_kind": "numpy_direct"},
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "demo_report": str(session_dir / "demo-report.json"),
            },
            "summary": {},
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    pyside6 = next(
        item for item in payload["criteria"] if item["name"] == "pyside6_path_exercised"
    )
    assert pyside6["status"] == "pass"
    assert pyside6["evidence"]["demo_mode"] == "numpy-direct"
    assert pyside6["evidence"]["demo_mode_supported"] is True
    assert pyside6["evidence"]["demo_frame_source_kind"] == "numpy_direct"
    assert pyside6["evidence"]["expected_frame_source_kind"] == "numpy_direct"
    assert pyside6["evidence"]["frame_source_supported"] is True


def test_macos_validation_session_acceptance_tool_fails_when_runtime_and_release_products_diverge(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "release_minimum_system_version_expected": True,
                "release_universal2_ready": True,
                "release_artifacts_present": True,
                "release_pkg_includes_extension_payload": True,
                "release_pkg_payload_appledouble_clean": True,
                "release_host_embeds_extension_bundle": True,
                "release_app_signed": True,
                "release_extension_signed": True,
                "release_pkg_signed": True,
                "runtime_packaged_assets_present": True,
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
            }
        },
    )
    _write_json(
        session_dir / "preflight.json",
        {"readiness": {"can_notarize": True, "can_staple": True}},
    )
    _write_json(
        session_dir / "benchmark.json",
        {
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
    )
    _write_json(
        session_dir / "entrypoints-contract.json",
        {
            "consistency": {
                "all_checks_passed": True,
                "surface_complete": True,
                "demo_case_complete": True,
                "cli_case_complete": True,
                "desktop_case_complete": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "preflight_report": str(session_dir / "preflight.json"),
                "benchmark_report": str(session_dir / "benchmark.json"),
                "validation_report": str(session_dir / "validation-report.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
            },
            "summary": {
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
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": True,
                "list_devices_binary_check_filtered_device_count": 1,
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
                "runtime_release_product_identity_consistent": False,
                "runtime_release_product_path_equal": False,
                "runtime_host_bundle_path": "/Applications/Other.app",
                "release_app_bundle_path": "/Applications/Amaran Desktop.app",
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["summary"]["acceptance_ready"] is False
    assert "release_packaging_ready" in payload["summary"]["failed_criteria"]
    release_packaging = next(
        item for item in payload["criteria"] if item["name"] == "release_packaging_ready"
    )
    assert release_packaging["status"] == "fail"
    assert release_packaging["evidence"]["runtime_release_product_identity_consistent"] is False
    assert release_packaging["evidence"]["runtime_host_bundle_path"] == "/Applications/Other.app"
    assert (
        release_packaging["evidence"]["release_app_bundle_path"]
        == "/Applications/Amaran Desktop.app"
    )


def test_macos_validation_session_acceptance_tool_reports_missing_evidence(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "validated_apps": 1,
                "passed_apps": 0,
                "failed_app_ids": ["zoom"],
                "pending_app_ids": ["teams", "google_meet", "obs", "quicktime", "facetime"],
                "skipped_app_ids": [],
                "unreviewed_app_ids": ["google_meet", "obs", "quicktime", "teams"],
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "preflight_report": str(session_dir / "preflight.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
                "demo_report": str(session_dir / "demo-report.json"),
                "benchmark_report": str(session_dir / "benchmark.json"),
                "manual_template": str(session_dir / "manual-results.template.json"),
                "validation_report": str(session_dir / "validation-report.json"),
                "smoke_report": str(session_dir / "smoke-report.json"),
                "install_session_report": str(session_dir / "install-session-report.json"),
                "framebus_roundtrip_report": str(session_dir / "framebus-roundtrip.json"),
                "status_binary_check_report": str(session_dir / "status-binary-check.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
            },
            "steps": {"validation_report": {"returncode": 0}},
            "summary": {
                "effective_supported_formats": ["1280x720@30/60 NV12"],
                "effective_supported_frame_rates": [30],
                "artifact_check_present": True,
                "artifact_check_passed": False,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["summary"]["acceptance_ready"] is False
    assert payload["summary"]["manual_app_validation_ready"] is False
    assert "artifact_replay_passed" in payload["summary"]["manual_app_validation_failed_criteria"]
    assert "python_direct_runtime_ready" in payload["summary"]["manual_app_validation_unknown_criteria"]
    assert "python_entrypoints_consistent" in payload["summary"]["manual_app_validation_unknown_criteria"]
    assert "system_camera_device_visible" in payload["summary"]["manual_app_validation_unknown_criteria"]
    assert "artifact_replay_passed" in payload["summary"]["failed_criteria"]
    assert "target_apps_all_passed" in payload["summary"]["failed_criteria"]
    assert "benchmark_matrix_complete" in payload["summary"]["unknown_criteria"]
    assert "benchmark_1080p60_cpu_target_met" in payload["summary"]["unknown_criteria"]
    assert "python_direct_runtime_ready" in payload["summary"]["unknown_criteria"]
    assert "python_entrypoints_consistent" in payload["summary"]["unknown_criteria"]
    assert "system_camera_device_visible" in payload["summary"]["unknown_criteria"]
    assert "sync_ipc_control_plane_ready" in payload["summary"]["unknown_criteria"]
    target_apps = next(
        item for item in payload["criteria"] if item["name"] == "target_apps_all_passed"
    )
    assert target_apps["evidence"]["failed_app_ids"] == ["zoom"]
    assert target_apps["evidence"]["pending_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
    ]
    assert "fail=zoom" in str(target_apps["note"])
    assert "pending=facetime,google_meet,obs,quicktime,teams" in str(target_apps["note"])
    sync_ipc = next(
        item for item in payload["criteria"] if item["name"] == "sync_ipc_control_plane_ready"
    )
    assert sync_ipc["status"] == "unknown"
    assert sync_ipc["critical"] is False


def test_macos_validation_session_acceptance_tool_fails_when_list_devices_check_saw_no_camera(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
            },
            "summary": {
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
                "list_devices_binary_check_override_no_match_ok": True,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "system_camera_device_visible" in payload["summary"]["failed_criteria"]
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "system_camera_device_visible"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["effective_device_prefix"] == "AKVC Demo"
    assert criterion["evidence"]["validation_demo_camera_name"] == "AKVC Demo"
    assert criterion["evidence"]["demo_camera_name_matches_effective_prefix"] is True
    assert criterion["evidence"]["list_devices_binary_check_present"] is True
    assert criterion["evidence"]["list_devices_binary_check_passed"] is False
    assert criterion["evidence"]["list_devices_binary_check_filtered_device_count"] == 0
    assert "akvc-macos-list-devices" in str(criterion["note"])
    assert "AKVC Demo" in str(criterion["note"])


def test_macos_validation_session_acceptance_tool_fails_when_direct_push_uses_fallback(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "demo_present": True,
                "demo_mode": "latest-provider",
                "demo_mode_supported": True,
                "demo_frame_source_kind": "latest_frame_provider",
                "runtime_packaged_assets_present": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
            },
            "summary": {
                "direct_push_demo_returncode": 0,
                "direct_push_demo_using_direct_sender": False,
                "direct_push_demo_helper_hot_path_used": False,
                "direct_push_demo_shared_memory_fallback_used": True,
                "direct_push_demo_direct_only": False,
                "direct_push_demo_allow_shared_memory_fallback": True,
                "direct_push_demo_runtime_host_in_frame_hot_path": False,
                "direct_push_demo_runtime_dedicated_host_daemon_required": False,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "python_direct_runtime_ready" in payload["summary"]["failed_criteria"]
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "python_direct_runtime_ready"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["selected_candidate"]["pure_direct_runtime"] is False
    assert "direct-push-demo --require-direct-runtime" in str(criterion["note"])


def test_macos_validation_session_acceptance_tool_fails_when_benchmark_matrix_is_incomplete(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "release_minimum_system_version_expected": True,
                "release_universal2_ready": True,
                "release_artifacts_present": True,
                "release_pkg_includes_extension_payload": True,
                "release_pkg_payload_appledouble_clean": True,
                "release_host_embeds_extension_bundle": True,
                "release_app_signed": True,
                "release_extension_signed": True,
                "release_pkg_signed": True,
                "demo_present": True,
                "demo_mode": "latest-provider",
                "demo_mode_supported": True,
                "demo_frame_source_kind": "latest_frame_provider",
                "runtime_packaged_assets_present": True,
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
    )
    _write_json(
        session_dir / "preflight.json",
        {"readiness": {"can_notarize": True, "can_staple": True}},
    )
    _write_json(
        session_dir / "benchmark.json",
        {
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
    )
    _write_json(
        session_dir / "release-diagnostics.json",
        {
            "summary": {
                "sync_ipc_tool_exists": True,
                "sync_ipc_tool_signed": True,
                "sync_ipc_tool_universal2_ready": True,
            }
        },
    )
    _write_json(
        session_dir / "entrypoints-contract.json",
        {
            "consistency": {
                "all_checks_passed": True,
                "surface_complete": True,
                "demo_case_complete": True,
                "cli_case_complete": True,
                "desktop_case_complete": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "preflight_report": str(session_dir / "preflight.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
                "benchmark_report": str(session_dir / "benchmark.json"),
                "validation_report": str(session_dir / "validation-report.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
            },
            "summary": {
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
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["summary"]["acceptance_ready"] is False
    assert payload["summary"]["manual_app_validation_ready"] is True
    assert "benchmark_matrix_complete" in payload["summary"]["failed_criteria"]
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "benchmark_matrix_complete"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["benchmark_acceptance"]["missing_required_profiles"] == [
        "4k60",
        "720p60",
        "1080p30",
    ]
    assert "missing=4k60,720p60,1080p30" in str(criterion["note"])


def test_macos_validation_session_acceptance_tool_keeps_target_apps_unknown_when_only_counts_exist(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "validated_apps": 6,
                "passed_apps": 6,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
            },
            "summary": {},
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "target_apps_all_passed" in payload["summary"]["unknown_criteria"]
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "target_apps_all_passed"
    )
    assert criterion["status"] == "unknown"
    assert criterion["evidence"]["validated_apps"] == 6
    assert criterion["evidence"]["passed_apps"] == 6
    assert criterion["evidence"]["observed_target_app_ids"] == []
    assert criterion["evidence"]["missing_target_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
        "zoom",
    ]


def test_macos_validation_session_acceptance_tool_prefers_explicit_target_identity_fields(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
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
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
            },
            "summary": {
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
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "target_apps_all_passed"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["observed_target_app_ids"] == [
        "obs",
        "quicktime",
        "teams",
        "zoom",
    ]
    assert criterion["evidence"]["missing_target_app_ids"] == [
        "facetime",
        "google_meet",
    ]
    assert criterion["evidence"]["unexpected_target_app_ids"] == []
    assert "missing=facetime,google_meet" in str(criterion["note"])


def test_macos_validation_session_acceptance_tool_fails_when_passed_apps_lack_preview_evidence(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    incomplete_matrix = _passing_app_matrix()
    incomplete_matrix["zoom"]["evidence"] = {
        "device_listed": True,
        "device_selected": True,
        "preview_visible": False,
        "screenshot": "",
    }
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "validated_apps": 6,
                "passed_apps": 6,
                "validation_app_matrix": incomplete_matrix,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
            },
            "summary": {},
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "target_apps_all_passed"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["target_app_missing_evidence_ids"] == ["zoom"]
    assert "missing_evidence=zoom" in str(criterion["note"])


def test_macos_validation_session_acceptance_tool_fails_when_entrypoints_contract_is_incomplete(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        session_dir / "entrypoints-contract.json",
        {
            "consistency": {
                "all_checks_passed": False,
                "surface_complete": True,
                "demo_case_complete": True,
                "cli_case_complete": False,
                "desktop_case_complete": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
            },
            "summary": {
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": False,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": False,
                "entrypoints_contract_desktop_case_complete": True,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "python_entrypoints_consistent" in payload["summary"]["failed_criteria"]
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "python_entrypoints_consistent"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["entrypoints_contract_cli_case_complete"] is False
    assert criterion["evidence"]["entrypoints_contract_desktop_case_complete"] is True


def test_macos_validation_session_acceptance_tool_fails_when_sdk_contract_is_incomplete(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        session_dir / "entrypoints-contract.json",
        {
            "consistency": {
                "all_checks_passed": True,
                "surface_complete": True,
                "demo_case_complete": True,
                "cli_case_complete": True,
                "desktop_case_complete": True,
            }
        },
    )
    _write_json(
        session_dir / "sdk-contract.json",
        {
            "consistency": {
                "all_checks_passed": False,
                "constructor_shape_aligned": True,
                "direct_sender_exports_present": False,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
            },
            "summary": {
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": True,
                "entrypoints_contract_surface_complete": True,
                "entrypoints_contract_demo_case_complete": True,
                "entrypoints_contract_cli_case_complete": True,
                "entrypoints_contract_desktop_case_complete": True,
                "sdk_contract_present": True,
                "sdk_contract_passed": False,
                "sdk_contract_constructor_shape_aligned": True,
                "sdk_contract_direct_sender_exports_present": False,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "python_entrypoints_consistent" in payload["summary"]["failed_criteria"]
    criterion = next(
        item for item in payload["criteria"] if item["name"] == "python_entrypoints_consistent"
    )
    assert criterion["status"] == "fail"
    assert criterion["evidence"]["sdk_contract_passed"] is False
    assert criterion["evidence"]["sdk_contract_constructor_shape_aligned"] is True
    assert criterion["evidence"]["sdk_contract_direct_sender_exports_present"] is False


def test_macos_validation_session_acceptance_tool_falls_back_to_release_diagnostics_for_release_gates(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        session_dir / "release-diagnostics.json",
        {
            "summary": {
                "minimum_system_version_expected": True,
                "universal2_ready": True,
                "release_artifacts_present": True,
                "pkg_includes_extension_payload": True,
                "pkg_payload_appledouble_clean": True,
                "host_embeds_extension_bundle": True,
                "app_signed": True,
                "extension_signed": True,
                "pkg_signed": True,
                "sync_ipc_tool_exists": True,
                "sync_ipc_tool_signed": True,
                "sync_ipc_tool_universal2_ready": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
            },
            "summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "artifact_check_present": True,
                "artifact_check_passed": True,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    criteria = {item["name"]: item for item in payload["criteria"]}
    assert criteria["macos_13_plus_declared"]["status"] == "pass"
    assert criteria["universal2_ready"]["status"] == "pass"
    assert criteria["release_packaging_ready"]["status"] == "pass"
    assert criteria["signing_evidence_ready"]["status"] == "pass"
    assert criteria["notarization_tooling_ready"]["status"] == "pass"
    assert criteria["sync_ipc_control_plane_ready"]["status"] == "pass"
    assert criteria["universal2_ready"]["evidence"]["universal2_ready"] is True
    assert criteria["release_packaging_ready"]["evidence"]["pkg_payload_appledouble_clean"] is True
    assert criteria["signing_evidence_ready"]["evidence"]["app_signed"] is True
    assert criteria["notarization_tooling_ready"]["evidence"]["app_gatekeeper_accepted"] is True
    assert criteria["notarization_tooling_ready"]["evidence"]["pkg_stapled"] is True


def test_macos_validation_session_acceptance_tool_keeps_partial_release_evidence_unknown(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        session_dir / "release-diagnostics.json",
        {
            "summary": {
                "release_artifacts_present": True,
                "pkg_includes_extension_payload": True,
                "pkg_payload_appledouble_clean": None,
                "host_embeds_extension_bundle": None,
                "app_signed": True,
                "extension_signed": None,
                "pkg_signed": True,
                "app_gatekeeper_accepted": None,
                "app_stapled": None,
                "pkg_gatekeeper_accepted": None,
                "pkg_stapled": None,
                "sync_ipc_tool_exists": True,
                "sync_ipc_tool_signed": None,
                "sync_ipc_tool_universal2_ready": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
            },
            "summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
                "artifact_check_present": True,
                "artifact_check_passed": True,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    criteria = {item["name"]: item for item in payload["criteria"]}
    assert criteria["release_packaging_ready"]["status"] == "unknown"
    assert criteria["signing_evidence_ready"]["status"] == "unknown"
    assert criteria["sync_ipc_control_plane_ready"]["status"] == "unknown"


def test_macos_validation_session_acceptance_tool_fails_notarization_gate_on_release_artifact_policy_failure(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "release_app_signed": True,
                "release_extension_signed": True,
                "release_pkg_signed": True,
            }
        },
    )
    _write_json(
        session_dir / "preflight.json",
        {"readiness": {"can_notarize": True, "can_staple": True}},
    )
    _write_json(
        session_dir / "release-diagnostics.json",
        {
            "summary": {
                "app_gatekeeper_accepted": False,
                "app_stapled": False,
                "pkg_gatekeeper_accepted": True,
                "pkg_stapled": True,
            }
        },
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "preflight_report": str(session_dir / "preflight.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
            },
            "summary": {
                "effective_supported_formats": [
                    "1280x720@30/60 NV12",
                    "1920x1080@30/60 NV12",
                    "3840x2160@30/60 NV12",
                ],
                "effective_supported_frame_rates": [30, 60],
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    criteria = {item["name"]: item for item in payload["criteria"]}
    assert criteria["signing_evidence_ready"]["status"] == "pass"
    assert criteria["notarization_tooling_ready"]["status"] == "fail"
    assert criteria["notarization_tooling_ready"]["evidence"]["app_gatekeeper_accepted"] is False
    assert criteria["notarization_tooling_ready"]["evidence"]["app_stapled"] is False


def test_macos_validation_session_acceptance_tool_fails_auto_install_when_ipc_blocked(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
            },
            "summary": {
                "install_session_present": True,
                "install_session_success": True,
                "install_session_start_ready": False,
                "install_session_start_blocker_code": "ipc_environment_blocked",
                "install_session_ipc_probe_present": True,
                "install_session_ipc_ready": False,
                "install_session_ipc_environment_blocked": True,
                "install_session_ipc_direct_open_errno": 13,
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "auto_install_ready" in payload["summary"]["failed_criteria"]
    assert "auto_install_ready" in payload["summary"]["manual_app_validation_failed_criteria"]
    auto_install = next(
        item for item in payload["criteria"] if item["name"] == "auto_install_ready"
    )
    assert auto_install["status"] == "fail"
    assert auto_install["evidence"]["install_session_ipc_environment_blocked"] is True
    assert auto_install["evidence"]["install_session_ipc_direct_open_errno"] == 13


def test_macos_validation_session_acceptance_tool_fails_sync_ipc_gate_when_runtime_sync_failed(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "release-diagnostics.json",
        {
            "summary": {
                "sync_ipc_tool_exists": True,
                "sync_ipc_tool_signed": True,
                "sync_ipc_tool_universal2_ready": True,
            }
        },
    )
    _write_json(session_dir / "validation-report.json", {"summary": {}})
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "release_diagnostics_report": str(session_dir / "release-diagnostics.json"),
            },
            "summary": {
                "install_session_sync_ipc_present": True,
                "install_session_sync_ipc_supported": True,
                "install_session_sync_ipc_success": False,
                "install_session_sync_ipc_phase": "sync_command_failed",
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    criteria = {item["name"]: item for item in payload["criteria"]}
    assert criteria["sync_ipc_control_plane_ready"]["status"] == "fail"
    assert criteria["sync_ipc_control_plane_ready"]["evidence"]["install_session_sync_ipc_success"] is False


def test_macos_validation_session_acceptance_tool_fails_pyside6_when_demo_mode_is_unsupported(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "demo_present": True,
                "demo_mode": "broken-mode",
                "demo_mode_supported": False,
                "demo_frame_source_kind": "mystery_source",
            }
        },
    )
    _write_json(
        session_dir / "demo-report.json",
        {"mode": "broken-mode", "frame_source_kind": "mystery_source"},
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "demo_report": str(session_dir / "demo-report.json"),
            },
            "summary": {},
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    pyside6 = next(
        item for item in payload["criteria"] if item["name"] == "pyside6_path_exercised"
    )
    assert pyside6["status"] == "fail"
    assert pyside6["evidence"]["demo_mode"] == "broken-mode"
    assert pyside6["evidence"]["demo_mode_supported"] is False
    assert pyside6["evidence"]["demo_frame_source_kind"] == "mystery_source"
    assert pyside6["evidence"]["expected_frame_source_kind"] is None
    assert pyside6["evidence"]["frame_source_supported"] is None


def test_macos_validation_session_acceptance_tool_fails_pyside6_when_frame_source_mismatches_mode(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "validation-report.json",
        {
            "summary": {
                "demo_present": True,
                "demo_mode": "video-file",
                "demo_mode_supported": True,
                "demo_frame_source_kind": "widget_grab",
            }
        },
    )
    _write_json(
        session_dir / "demo-report.json",
        {"mode": "video-file", "frame_source_kind": "widget_grab"},
    )
    _write_json(
        manifest,
        {
            "artifacts": {
                "validation_report": str(session_dir / "validation-report.json"),
                "demo_report": str(session_dir / "demo-report.json"),
            },
            "summary": {},
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    pyside6 = next(
        item for item in payload["criteria"] if item["name"] == "pyside6_path_exercised"
    )
    assert pyside6["status"] == "fail"
    assert pyside6["evidence"]["demo_mode"] == "video-file"
    assert pyside6["evidence"]["demo_mode_supported"] is True
    assert pyside6["evidence"]["demo_frame_source_kind"] == "widget_grab"
    assert pyside6["evidence"]["expected_frame_source_kind"] == "opencv_video_file"
    assert pyside6["evidence"]["frame_source_supported"] is False
