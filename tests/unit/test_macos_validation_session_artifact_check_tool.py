# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation-session artifact replay helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_validation_session_artifact_check.py"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _manual_template_payload() -> dict[str, object]:
    def entry(name: str) -> dict[str, object]:
        return {
            "checks": [
                f"{name} 能看到 AK Virtual Camera。",
                f"{name} 切换到 AK Virtual Camera 后能看到实时画面。",
            ],
            "name": name,
            "notes": "",
            "ready": True,
            "result": "pending",
            "status": "ready",
            "steps": [
                f"打开 {name} 的视频设备设置。",
                "选择 AK Virtual Camera。",
            ],
            "validated": False,
        }

    return {
        "facetime": entry("FaceTime"),
        "google_meet": entry("Google Meet"),
        "obs": entry("OBS"),
        "quicktime": entry("QuickTime"),
        "teams": entry("Teams"),
        "zoom": entry("Zoom"),
    }


def _benchmark_matrix_payload() -> dict[str, object]:
    return {
        "kind": "benchmark_matrix",
        "profiles": ["720p30", "720p60", "1080p30", "1080p60", "4k30", "4k60"],
        "results": [
            {
                "profile": {"name": "720p30", "width": 1280, "height": 720, "fps": 30.0},
                "scenario": {"width": 1280, "height": 720, "fps": 30.0},
                "metrics": {"actual_fps": 29.9, "cpu_percent": 3.2, "avg_latency_ms": 0.8},
                "acceptance": {
                    "fps_target_met": True,
                    "cpu_target_applies": False,
                    "cpu_target_met": None,
                },
            },
            {
                "profile": {"name": "720p60", "width": 1280, "height": 720, "fps": 60.0},
                "scenario": {"width": 1280, "height": 720, "fps": 60.0},
                "metrics": {"actual_fps": 59.4, "cpu_percent": 4.5, "avg_latency_ms": 0.9},
                "acceptance": {
                    "fps_target_met": True,
                    "cpu_target_applies": False,
                    "cpu_target_met": None,
                },
            },
            {
                "profile": {"name": "1080p30", "width": 1920, "height": 1080, "fps": 30.0},
                "scenario": {"width": 1920, "height": 1080, "fps": 30.0},
                "metrics": {"actual_fps": 29.7, "cpu_percent": 5.1, "avg_latency_ms": 1.0},
                "acceptance": {
                    "fps_target_met": True,
                    "cpu_target_applies": False,
                    "cpu_target_met": None,
                },
            },
            {
                "profile": {"name": "1080p60", "width": 1920, "height": 1080, "fps": 60.0},
                "scenario": {"width": 1920, "height": 1080, "fps": 60.0},
                "metrics": {"actual_fps": 59.6, "cpu_percent": 8.4, "avg_latency_ms": 1.1},
                "acceptance": {
                    "fps_target_met": True,
                    "cpu_target_applies": True,
                    "cpu_target_met": True,
                },
            },
            {
                "profile": {"name": "4k30", "width": 3840, "height": 2160, "fps": 30.0},
                "scenario": {"width": 3840, "height": 2160, "fps": 30.0},
                "metrics": {"actual_fps": 29.5, "cpu_percent": 7.9, "avg_latency_ms": 1.5},
                "acceptance": {
                    "fps_target_met": True,
                    "cpu_target_applies": False,
                    "cpu_target_met": None,
                },
            },
            {
                "profile": {"name": "4k60", "width": 3840, "height": 2160, "fps": 60.0},
                "scenario": {"width": 3840, "height": 2160, "fps": 60.0},
                "metrics": {"actual_fps": 59.0, "cpu_percent": 9.7, "avg_latency_ms": 1.9},
                "acceptance": {
                    "fps_target_met": True,
                    "cpu_target_applies": False,
                    "cpu_target_met": None,
                },
            },
        ],
    }


def _benchmark_matrix_profiles_summary() -> list[dict[str, object]]:
    return [
        {
            "profile_name": "720p30",
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 29.9,
            "cpu_percent": 3.2,
            "avg_latency_ms": 0.8,
        },
        {
            "profile_name": "720p60",
            "width": 1280,
            "height": 720,
            "fps": 60.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 59.4,
            "cpu_percent": 4.5,
            "avg_latency_ms": 0.9,
        },
        {
            "profile_name": "1080p30",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 29.7,
            "cpu_percent": 5.1,
            "avg_latency_ms": 1.0,
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
        {
            "profile_name": "4k30",
            "width": 3840,
            "height": 2160,
            "fps": 30.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 29.5,
            "cpu_percent": 7.9,
            "avg_latency_ms": 1.5,
        },
        {
            "profile_name": "4k60",
            "width": 3840,
            "height": 2160,
            "fps": 60.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 59.0,
            "cpu_percent": 9.7,
            "avg_latency_ms": 1.9,
        },
    ]


def test_macos_validation_session_artifact_check_tool_exists_and_declares_expected_options() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "session-manifest.json" in text
    assert "effective_supported_formats" in text
    assert "list_devices_binary_check_report" in text
    assert "list_devices_binary_check_present" in text
    assert "release_sync_ipc_tool_exists" in text
    assert "install_session_sync_ipc_present" in text
    assert "install_session_sync_ipc_success" in text
    assert "sync_ipc_control_plane_ready" in text
    assert "entrypoints_contract_report" in text
    assert "entrypoints_contract_present" in text
    assert "sdk_contract_report" in text
    assert "sdk_contract_present" in text
    assert "sdk_contract_passed" in text
    assert "validation_reviewed_app_ids" in text
    assert "validation_missing_target_app_ids" in text
    assert "validation_unexpected_target_app_ids" in text
    assert "validation_target_app_ids_complete" in text
    assert "acceptance_contract_report" in text
    assert "acceptance_contract_present" in text
    assert "acceptance_contract_passed" in text
    assert "manual_template_surface" in text
    assert "manual_template_surface_complete" in text
    assert "check_lists_present" in text
    assert "step_lists_present" in text
    assert "benchmark_artifact_surface" in text
    assert "validation_benchmark_kind" in text
    assert "validation_benchmark_matrix_profiles" in text
    assert "benchmark_1080p60_cpu_target_met" in text
    assert "benchmark_gate_statuses_match_artifact_when_present" in text
    assert "summary_report" in text
    assert "session-summary.md" in text
    assert "--manifest" in text
    assert "--require-existing-artifacts" in text
    assert "--output" in text


def test_macos_validation_session_artifact_check_tool_accepts_consistent_manifest(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "manual-results.template.json", _manual_template_payload())
    _write_json(session_dir / "validation-report.json", {"summary": {"passed_apps": 0}})
    _write_json(session_dir / "benchmark.json", _benchmark_matrix_payload())
    _write_json(session_dir / "smoke-report.json", {"status": {"start_ready": True}})
    _write_json(session_dir / "install-session-report.json", {"post_status": {"start_ready": True}})
    _write_json(
        session_dir / "list-devices-binary-check.json",
        {"consistency": {"all_checks_passed": True}},
    )
    _write_json(session_dir / "session-manifest-check.json", {"consistency": {"all_checks_passed": True}})
    _write_json(session_dir / "session-acceptance.json", {"summary": {"acceptance_ready": False}})
    _write_json(session_dir / "session-acceptance-contract.json", {"consistency": {"all_checks_passed": True}})
    _write_json(session_dir / "entrypoints-contract.json", {"consistency": {"all_checks_passed": True}})
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
    (session_dir / "session-summary.md").write_text("# summary\n", encoding="utf-8")

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
                "list_devices_binary_check_report": str(session_dir / "list-devices-binary-check.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
                "acceptance_contract_report": str(session_dir / "session-acceptance-contract.json"),
                "summary_report": str(session_dir / "session-summary.md"),
            },
            "steps": {
                "benchmark": {"returncode": 0},
                "validation_report": {"returncode": 0},
                "smoke": {"returncode": 0},
                "install_session": {"returncode": 0},
                "entrypoints_contract": {"returncode": 0},
                "sdk_contract": {"returncode": 0},
                "artifact_check": {"returncode": 0},
                "acceptance": {"returncode": 0},
                "acceptance_contract": {"returncode": 0},
                "summary": {"returncode": 0},
            },
            "summary": {
                "validation_report_present": True,
                "smoke_present": True,
                "install_session_present": True,
                "framebus_roundtrip_present": False,
                "status_binary_check_present": False,
                "list_devices_binary_check_present": True,
                "list_devices_binary_check_passed": True,
                "list_devices_binary_check_device_prefix": "AK Virtual Camera",
                "list_devices_binary_check_filtered_device_count": 1,
                "list_devices_binary_check_total_device_count": 2,
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
                "acceptance_present": True,
                "acceptance_ready": False,
                "acceptance_contract_present": True,
                "acceptance_contract_passed": True,
                "target_apps_all_passed": "fail",
                "system_camera_device_visible": "pass",
                "auto_install_ready": "pass",
                "signing_evidence_ready": "pass",
                "notarization_tooling_ready": "unknown",
                "runtime_assets_packaged": "pass",
                "sync_ipc_control_plane_ready": "pass",
                "summary_report_present": True,
                "effective_start_ready": True,
                "effective_start_blocker_code": "ready",
                "release_sync_ipc_tool_exists": True,
                "release_sync_ipc_tool_signed": True,
                "release_sync_ipc_tool_universal2_ready": True,
                "validation_shared_memory_name": "/akvc-validation",
                "validation_mach_service_name": "com.akvc.validation",
                "validation_ipc_transport": "validation_transport",
                "validation_benchmark_kind": "benchmark_matrix",
                "validation_benchmark_matrix_profiles": _benchmark_matrix_profiles_summary(),
                "benchmark_matrix_complete": "pass",
                "benchmark_fps_targets_met": "pass",
                "benchmark_1080p60_cpu_target_met": "pass",
                "smoke_shared_memory_name": "/akvc-smoke",
                "smoke_mach_service_name": "com.akvc.smoke",
                "smoke_ipc_transport": "smoke_transport",
                "install_session_shared_memory_name": "/akvc-install-session",
                "install_session_mach_service_name": "com.akvc.install-session",
                "install_session_ipc_transport": "install_session_transport",
                "install_session_sync_ipc_present": True,
                "install_session_sync_ipc_supported": True,
                "install_session_sync_ipc_success": True,
                "install_session_sync_ipc_phase": "sync_command_succeeded",
                "install_session_sync_ipc_shared_memory_name": "/akvc-install-session",
                "install_session_sync_ipc_transport": "shared_memory_ringbuffer",
                "install_session_sync_ipc_returncode": 0,
                "effective_shared_memory_name": "/akvc-install-session",
                "effective_mach_service_name": "com.akvc.install-session",
                "effective_ipc_transport": "install_session_transport",
                "validation_supported_formats": ["1280x720@30/60 NV12"],
                "validation_reviewed_app_ids": ["zoom"],
                "validation_unreviewed_app_ids": ["teams"],
                "validation_observed_target_app_ids": ["teams", "zoom"],
                "validation_missing_target_app_ids": ["facetime", "google_meet", "obs", "quicktime"],
                "validation_unexpected_target_app_ids": [],
                "validation_target_app_ids_complete": False,
                "smoke_supported_formats": ["1920x1080@30/60 NV12"],
                "install_session_supported_formats": ["3840x2160@30/60 NV12"],
                "effective_supported_formats": ["3840x2160@30/60 NV12"],
                "validation_supported_frame_rates": [30, 60],
                "smoke_supported_frame_rates": [30, 60],
                "install_session_supported_frame_rates": [30, 60],
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
            "--require-existing-artifacts",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["consistency"]["artifact_surface_complete"] is True
    assert payload["consistency"]["manual_template_surface_complete"] is True
    assert payload["consistency"]["summary_surface_complete"] is True
    assert payload["consistency"]["existing_artifacts_match_expected"] is True
    assert payload["consistency"]["all_checks_passed"] is True
    assert payload["existing_artifact_checks"]["acceptance_contract_report"] is True
    assert payload["existing_artifact_checks"]["benchmark_report"] is True
    assert payload["existing_artifact_checks"]["entrypoints_contract_report"] is True
    assert payload["existing_artifact_checks"]["sdk_contract_report"] is True
    assert payload["existing_artifact_checks"]["summary_report"] is True
    assert payload["benchmark_artifact_surface"]["present"] is True
    assert payload["benchmark_artifact_surface"]["kind"] == "benchmark_matrix"
    assert payload["manual_template_surface"]["ids_complete"] is True
    assert payload["manual_template_surface"]["shape_complete"] is True
    assert payload["manual_template_surface"]["check_lists_present"] is True
    assert payload["manual_template_surface"]["step_lists_present"] is True
    assert payload["summary_surface"]["summary_report_field_typed_when_present"] is True
    assert payload["summary_surface"]["benchmark_fields_typed_when_present"] is True
    assert payload["summary_surface"]["benchmark_kind_consistent_with_profiles"] is True
    assert payload["summary_surface"]["benchmark_profile_names_unique_when_present"] is True
    assert payload["summary_surface"]["benchmark_1080p60_profile_consistent_when_present"] is True
    assert payload["summary_surface"]["benchmark_artifact_matches_summary_when_present"] is True
    assert payload["summary_surface"]["benchmark_gate_statuses_match_artifact_when_present"] is True
    assert payload["summary_surface"]["entrypoints_contract_fields_typed_when_present"] is True
    assert payload["summary_surface"]["sdk_contract_fields_typed_when_present"] is True
    assert payload["summary_surface"]["target_app_identity_fields_typed_when_present"] is True
    assert payload["summary_surface"]["release_sync_ipc_fields_typed_when_present"] is True
    assert payload["summary_surface"]["install_session_sync_ipc_fields_typed_when_present"] is True
    assert payload["summary_surface"]["acceptance_gate_fields_typed_when_present"] is True
    assert payload["summary_surface"]["sync_ipc_gate_consistent_with_runtime_sync"] is True
    assert payload["summary_surface"]["acceptance_contract_fields_typed_when_present"] is True
    assert payload["summary_surface"]["has_effective_ipc_identity_fields"] is True
    assert payload["summary_surface"]["ipc_identity_fields_typed"] is True
    assert payload["summary_snapshot"]["effective_shared_memory_name"] == "/akvc-install-session"
    assert payload["summary_snapshot"]["release_sync_ipc_tool_exists"] is True
    assert payload["summary_snapshot"]["sync_ipc_control_plane_ready"] == "pass"
    assert payload["summary_snapshot"]["install_session_sync_ipc_success"] is True
    assert payload["summary_snapshot"]["install_session_sync_ipc_phase"] == "sync_command_succeeded"
    assert payload["summary_snapshot"]["validation_benchmark_kind"] == "benchmark_matrix"
    assert payload["summary_snapshot"]["benchmark_matrix_complete"] == "pass"
    assert payload["summary_snapshot"]["benchmark_1080p60_cpu_target_met"] == "pass"
    assert payload["summary_snapshot"]["entrypoints_contract_passed"] is True
    assert payload["summary_snapshot"]["sdk_contract_passed"] is True
    assert payload["summary_snapshot"]["acceptance_contract_passed"] is True
    assert payload["summary_snapshot"]["validation_reviewed_app_ids"] == ["zoom"]
    assert payload["summary_snapshot"]["validation_missing_target_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
    ]
    assert payload["summary_snapshot"]["validation_target_app_ids_complete"] is False
    assert payload["summary_snapshot"]["effective_supported_formats"] == [
        "3840x2160@30/60 NV12"
    ]


def test_macos_validation_session_artifact_check_tool_rejects_missing_required_artifact(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "manual-results.template.json", _manual_template_payload())

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
                "list_devices_binary_check_report": str(session_dir / "list-devices-binary-check.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
                "acceptance_contract_report": str(session_dir / "session-acceptance-contract.json"),
                "summary_report": str(session_dir / "session-summary.md"),
            },
            "steps": {
                "validation_report": {"returncode": 0},
                "artifact_check": {"returncode": 0},
                "acceptance": {"returncode": 0},
                "acceptance_contract": {"returncode": 0},
                "summary": {"returncode": 0},
            },
            "summary": {
                "validation_report_present": True,
                "smoke_present": False,
                "install_session_present": False,
                "framebus_roundtrip_present": False,
                "status_binary_check_present": False,
                "list_devices_binary_check_present": "bad",
                "list_devices_binary_check_passed": "bad",
                "list_devices_binary_check_device_prefix": 123,
                "list_devices_binary_check_filtered_device_count": "bad",
                "list_devices_binary_check_total_device_count": "bad",
                "list_devices_binary_check_override_no_match_ok": "bad",
                "entrypoints_contract_present": True,
                "entrypoints_contract_passed": "bad",
                "entrypoints_contract_surface_complete": 1,
                "entrypoints_contract_demo_case_complete": [],
                "entrypoints_contract_cli_case_complete": "bad",
                "entrypoints_contract_desktop_case_complete": {"bad": True},
                "validation_reviewed_app_ids": "bad",
                "validation_unreviewed_app_ids": 1,
                "validation_observed_target_app_ids": {"bad": True},
                "validation_missing_target_app_ids": [1],
                "validation_unexpected_target_app_ids": False,
                "validation_target_app_ids_complete": "bad",
                "artifact_check_present": True,
                "artifact_check_passed": "bad",
                "acceptance_present": True,
                "acceptance_ready": "bad",
                "acceptance_contract_present": "bad",
                "acceptance_contract_passed": "bad",
                "target_apps_all_passed": True,
                "system_camera_device_visible": ["bad"],
                "auto_install_ready": ["bad"],
                "signing_evidence_ready": 123,
                "notarization_tooling_ready": False,
                "runtime_assets_packaged": {"bad": True},
                "sync_ipc_control_plane_ready": "pass",
                "summary_report_present": "bad",
                "effective_start_ready": False,
                "effective_start_blocker_code": "ready",
                "validation_benchmark_kind": "single",
                "validation_benchmark_matrix_profiles": [{"profile_name": "1080p60"}],
                "benchmark_matrix_complete": False,
                "benchmark_fps_targets_met": True,
                "benchmark_1080p60_cpu_target_met": [],
                "release_sync_ipc_tool_exists": "bad",
                "release_sync_ipc_tool_signed": 1,
                "release_sync_ipc_tool_universal2_ready": [],
                "install_session_sync_ipc_present": "bad",
                "install_session_sync_ipc_supported": 1,
                "install_session_sync_ipc_success": [],
                "install_session_sync_ipc_phase": 123,
                "install_session_sync_ipc_shared_memory_name": False,
                "install_session_sync_ipc_transport": ["bad"],
                "install_session_sync_ipc_returncode": "bad",
                "effective_shared_memory_name": 123,
                "effective_mach_service_name": ["bad"],
                "effective_ipc_transport": False,
                "validation_supported_formats": ["1280x720@30/60 NV12"],
                "smoke_supported_formats": None,
                "install_session_supported_formats": None,
                "effective_supported_formats": ["bad-format"],
                "validation_supported_frame_rates": [30, 60],
                "smoke_supported_frame_rates": None,
                "install_session_supported_frame_rates": None,
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
            "--require-existing-artifacts",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3
    payload = json.loads(completed.stdout)
    assert payload["consistency"]["existing_artifacts_match_expected"] is False
    assert payload["consistency"]["summary_surface_complete"] is False
    assert payload["summary_surface"]["effective_ready_consistent_with_blocker"] is False
    assert payload["summary_surface"]["has_effective_ipc_identity_fields"] is True
    assert payload["summary_surface"]["ipc_identity_fields_typed"] is False
    assert payload["summary_surface"]["capability_values_allowed"] is False
    assert payload["summary_surface"]["artifact_check_fields_typed_when_present"] is False
    assert payload["summary_surface"]["acceptance_fields_typed_when_present"] is False
    assert payload["summary_surface"]["acceptance_contract_fields_typed_when_present"] is False
    assert payload["summary_surface"]["release_sync_ipc_fields_typed_when_present"] is False
    assert payload["summary_surface"]["install_session_sync_ipc_fields_typed_when_present"] is False
    assert payload["summary_surface"]["acceptance_gate_fields_typed_when_present"] is False
    assert payload["summary_surface"]["sync_ipc_gate_consistent_with_runtime_sync"] is False
    assert payload["summary_surface"]["list_devices_binary_check_fields_typed_when_present"] is False
    assert payload["summary_surface"]["summary_report_field_typed_when_present"] is False
    assert payload["summary_surface"]["benchmark_fields_typed_when_present"] is False
    assert payload["summary_surface"]["benchmark_kind_consistent_with_profiles"] is False
    assert payload["summary_surface"]["entrypoints_contract_fields_typed_when_present"] is False
    assert payload["summary_surface"]["target_app_identity_fields_typed_when_present"] is False


def test_macos_validation_session_artifact_check_tool_rejects_benchmark_summary_mismatch(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "manual-results.template.json", _manual_template_payload())
    _write_json(session_dir / "validation-report.json", {"summary": {"passed_apps": 0}})
    _write_json(session_dir / "benchmark.json", _benchmark_matrix_payload())

    mismatched_profiles = _benchmark_matrix_profiles_summary()
    mismatched_profiles[3] = {
        **mismatched_profiles[3],
        "cpu_target_met": False,
        "cpu_percent": 12.4,
    }

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
                "list_devices_binary_check_report": str(session_dir / "list-devices-binary-check.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
                "acceptance_contract_report": str(session_dir / "session-acceptance-contract.json"),
                "summary_report": str(session_dir / "session-summary.md"),
            },
            "steps": {
                "benchmark": {"returncode": 0},
                "validation_report": {"returncode": 0},
            },
            "summary": {
                "validation_report_present": True,
                "smoke_present": False,
                "install_session_present": False,
                "framebus_roundtrip_present": False,
                "status_binary_check_present": False,
                "list_devices_binary_check_present": False,
                "effective_start_ready": False,
                "effective_start_blocker_code": "pending",
                "validation_benchmark_kind": "benchmark_matrix",
                "validation_benchmark_matrix_profiles": mismatched_profiles,
                "benchmark_matrix_complete": "pass",
                "benchmark_fps_targets_met": "pass",
                "benchmark_1080p60_cpu_target_met": "pass",
                "validation_supported_formats": ["1280x720@30/60 NV12"],
                "smoke_supported_formats": None,
                "install_session_supported_formats": None,
                "effective_supported_formats": ["1280x720@30/60 NV12"],
                "validation_supported_frame_rates": [30, 60],
                "smoke_supported_frame_rates": None,
                "install_session_supported_frame_rates": None,
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
            "--require-existing-artifacts",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3, completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["summary_surface"]["benchmark_fields_typed_when_present"] is True
    assert payload["summary_surface"]["benchmark_artifact_matches_summary_when_present"] is False
    assert payload["summary_surface"]["benchmark_gate_statuses_match_artifact_when_present"] is True
    assert payload["consistency"]["summary_surface_complete"] is False


def test_macos_validation_session_artifact_check_tool_rejects_benchmark_gate_status_mismatch(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(session_dir / "manual-results.template.json", _manual_template_payload())
    _write_json(session_dir / "validation-report.json", {"summary": {"passed_apps": 0}})
    _write_json(session_dir / "benchmark.json", _benchmark_matrix_payload())

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
                "list_devices_binary_check_report": str(session_dir / "list-devices-binary-check.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
                "acceptance_contract_report": str(session_dir / "session-acceptance-contract.json"),
                "summary_report": str(session_dir / "session-summary.md"),
            },
            "steps": {
                "benchmark": {"returncode": 0},
                "validation_report": {"returncode": 0},
            },
            "summary": {
                "validation_report_present": True,
                "smoke_present": False,
                "install_session_present": False,
                "framebus_roundtrip_present": False,
                "status_binary_check_present": False,
                "list_devices_binary_check_present": False,
                "effective_start_ready": False,
                "effective_start_blocker_code": "pending",
                "validation_benchmark_kind": "benchmark_matrix",
                "validation_benchmark_matrix_profiles": _benchmark_matrix_profiles_summary(),
                "benchmark_matrix_complete": "fail",
                "benchmark_fps_targets_met": "pass",
                "benchmark_1080p60_cpu_target_met": "pass",
                "validation_supported_formats": ["1280x720@30/60 NV12"],
                "smoke_supported_formats": None,
                "install_session_supported_formats": None,
                "effective_supported_formats": ["1280x720@30/60 NV12"],
                "validation_supported_frame_rates": [30, 60],
                "smoke_supported_frame_rates": None,
                "install_session_supported_frame_rates": None,
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
            "--require-existing-artifacts",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3, completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["summary_surface"]["benchmark_artifact_matches_summary_when_present"] is True
    assert payload["summary_surface"]["benchmark_gate_statuses_match_artifact_when_present"] is False
    assert payload["consistency"]["summary_surface_complete"] is False


def test_macos_validation_session_artifact_check_tool_rejects_degraded_manual_template(
    tmp_path,
) -> None:
    session_dir = tmp_path / "session"
    manifest = session_dir / "session-manifest.json"
    _write_json(
        session_dir / "manual-results.template.json",
        {
            "zoom": {
                "name": "Zoom",
                "notes": "",
                "ready": True,
                "result": "pending",
                "status": "ready",
                "steps": ["打开 Zoom。"],
                "validated": False,
            }
        },
    )
    _write_json(session_dir / "validation-report.json", {"summary": {"passed_apps": 0}})

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
                "list_devices_binary_check_report": str(session_dir / "list-devices-binary-check.json"),
                "entrypoints_contract_report": str(session_dir / "entrypoints-contract.json"),
                "sdk_contract_report": str(session_dir / "sdk-contract.json"),
                "artifact_check_report": str(session_dir / "session-manifest-check.json"),
                "acceptance_report": str(session_dir / "session-acceptance.json"),
                "acceptance_contract_report": str(session_dir / "session-acceptance-contract.json"),
                "summary_report": str(session_dir / "session-summary.md"),
            },
            "steps": {
                "validation_report": {"returncode": 0},
            },
            "summary": {
                "validation_report_present": True,
                "smoke_present": False,
                "install_session_present": False,
                "framebus_roundtrip_present": False,
                "status_binary_check_present": False,
                "list_devices_binary_check_present": False,
                "effective_start_ready": False,
                "effective_start_blocker_code": "pending",
                "validation_supported_formats": ["1280x720@30/60 NV12"],
                "smoke_supported_formats": None,
                "install_session_supported_formats": None,
                "effective_supported_formats": ["1280x720@30/60 NV12"],
                "validation_supported_frame_rates": [30, 60],
                "smoke_supported_frame_rates": None,
                "install_session_supported_frame_rates": None,
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

    assert completed.returncode == 3, completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["consistency"]["manual_template_surface_complete"] is False
    assert payload["manual_template_surface"]["ids_complete"] is False
    assert payload["manual_template_surface"]["shape_complete"] is False
    assert payload["manual_template_surface"]["check_lists_present"] is False
