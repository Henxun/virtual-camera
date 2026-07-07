# SPDX-License-Identifier: Apache-2.0
"""Validation-session artifact replay checks for the macOS virtual camera stack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "build" / "macos" / "session" / "session-manifest.json"

REQUIRED_ARTIFACT_SUFFIXES = {
    "preflight_report": "preflight.json",
    "release_diagnostics_report": "release-diagnostics.json",
    "demo_report": "demo-report.json",
    "benchmark_report": "benchmark.json",
    "manual_template": "manual-results.template.json",
    "validation_report": "validation-report.json",
    "smoke_report": "smoke-report.json",
    "install_session_report": "install-session-report.json",
    "framebus_roundtrip_report": "framebus-roundtrip.json",
    "status_binary_check_report": "status-binary-check.json",
    "list_devices_binary_check_report": "list-devices-binary-check.json",
    "entrypoints_contract_report": "entrypoints-contract.json",
    "sdk_contract_report": "sdk-contract.json",
    "artifact_check_report": "session-manifest-check.json",
    "acceptance_report": "session-acceptance.json",
    "acceptance_contract_report": "session-acceptance-contract.json",
    "summary_report": "session-summary.md",
}
EXPECTED_MANUAL_TEMPLATE_IDS = (
    "facetime",
    "google_meet",
    "obs",
    "quicktime",
    "teams",
    "zoom",
)
EXPECTED_MANUAL_TEMPLATE_FIELDS = (
    "checks",
    "evidence",
    "name",
    "notes",
    "ready",
    "result",
    "status",
    "steps",
    "validated",
)
EXPECTED_BENCHMARK_MATRIX_PROFILE_NAMES = (
    "720p30",
    "720p60",
    "1080p30",
    "1080p60",
    "4k30",
    "4k60",
)

STEP_TO_ARTIFACT_KEY = {
    "preflight": "preflight_report",
    "release_diagnostics": "release_diagnostics_report",
    "demo": "demo_report",
    "benchmark": "benchmark_report",
    "validation_report": "validation_report",
    "smoke": "smoke_report",
    "install_session": "install_session_report",
    "framebus_roundtrip": "framebus_roundtrip_report",
    "status_binary_check": "status_binary_check_report",
    "list_devices_binary_check": "list_devices_binary_check_report",
    "entrypoints_contract": "entrypoints_contract_report",
    "sdk_contract": "sdk_contract_report",
    "acceptance_contract": "acceptance_contract_report",
    "summary": "summary_report",
}

ALLOWED_FORMATS = {
    "1280x720@30/60 NV12",
    "1920x1080@30/60 NV12",
    "3840x2160@30/60 NV12",
}
ALLOWED_FRAME_RATES = {30, 60}
SUMMARY_FORMAT_KEYS = (
    "validation_supported_formats",
    "smoke_supported_formats",
    "install_session_supported_formats",
    "effective_supported_formats",
)
SUMMARY_FRAME_RATE_KEYS = (
    "validation_supported_frame_rates",
    "smoke_supported_frame_rates",
    "install_session_supported_frame_rates",
    "effective_supported_frame_rates",
)
SUMMARY_IPC_STRING_KEYS = (
    "validation_shared_memory_name",
    "validation_mach_service_name",
    "validation_ipc_transport",
    "validation_install_shared_memory_name",
    "validation_install_mach_service_name",
    "validation_install_ipc_transport",
    "smoke_shared_memory_name",
    "smoke_mach_service_name",
    "smoke_ipc_transport",
    "install_session_shared_memory_name",
    "install_session_mach_service_name",
    "install_session_ipc_transport",
    "effective_shared_memory_name",
    "effective_mach_service_name",
    "effective_ipc_transport",
)
SUMMARY_RELEASE_SYNC_IPC_BOOL_KEYS = (
    "release_sync_ipc_tool_exists",
    "release_sync_ipc_tool_signed",
    "release_sync_ipc_tool_universal2_ready",
)
SUMMARY_INSTALL_SESSION_SYNC_IPC_BOOL_KEYS = (
    "install_session_sync_ipc_present",
    "install_session_sync_ipc_supported",
    "install_session_sync_ipc_success",
)
SUMMARY_INSTALL_SESSION_SYNC_IPC_STRING_KEYS = (
    "install_session_sync_ipc_phase",
    "install_session_sync_ipc_shared_memory_name",
    "install_session_sync_ipc_transport",
)
SUMMARY_ACCEPTANCE_GATE_KEYS = (
    "target_apps_all_passed",
    "system_camera_device_visible",
    "benchmark_matrix_complete",
    "auto_install_ready",
    "signing_evidence_ready",
    "notarization_tooling_ready",
    "runtime_assets_packaged",
    "sync_ipc_control_plane_ready",
)
SUMMARY_BENCHMARK_GATE_KEYS = (
    "benchmark_fps_targets_met",
    "benchmark_1080p60_cpu_target_met",
)
SUMMARY_ENTRYPOINTS_BOOL_KEYS = (
    "entrypoints_contract_passed",
    "entrypoints_contract_surface_complete",
    "entrypoints_contract_demo_case_complete",
    "entrypoints_contract_cli_case_complete",
    "entrypoints_contract_desktop_case_complete",
)
SUMMARY_SDK_CONTRACT_BOOL_KEYS = (
    "sdk_contract_passed",
    "sdk_contract_constructor_shape_aligned",
    "sdk_contract_direct_sender_exports_present",
)
SUMMARY_TARGET_APP_LIST_KEYS = (
    "validation_reviewed_app_ids",
    "validation_unreviewed_app_ids",
    "validation_observed_target_app_ids",
    "validation_missing_target_app_ids",
    "validation_unexpected_target_app_ids",
)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest JSON must be an object")
    return payload


def _is_bool_or_none(value: object) -> bool:
    return value is None or isinstance(value, bool)


def _is_str_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_string_list_or_none(value: object) -> bool:
    return value is None or (
        isinstance(value, list) and all(isinstance(item, str) for item in value)
    )


def _is_int_list_or_none(value: object) -> bool:
    return value is None or (
        isinstance(value, list) and all(isinstance(item, int) for item in value)
    )


def _is_int_or_none(value: object) -> bool:
    return value is None or isinstance(value, int)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _artifact_path_exists(
    manifest_path: Path,
    value: object,
) -> bool:
    if not isinstance(value, str) or not value:
        return False
    artifact_path = Path(value)
    if not artifact_path.is_absolute():
        artifact_path = (manifest_path.parent / artifact_path).resolve()
    return artifact_path.is_file()


def _resolve_artifact_path(manifest_path: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    artifact_path = Path(value)
    if not artifact_path.is_absolute():
        artifact_path = (manifest_path.parent / artifact_path).resolve()
    return artifact_path


def _load_optional_json_object(manifest_path: Path, value: object) -> dict[str, Any] | None:
    artifact_path = _resolve_artifact_path(manifest_path, value)
    if artifact_path is None or not artifact_path.is_file():
        return None
    try:
        return _load_json_object(artifact_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _normalize_benchmark_matrix_profiles(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, list):
        return None

    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        profile = dict(item.get("profile", {})) if isinstance(item.get("profile"), dict) else {}
        scenario = dict(item.get("scenario", {})) if isinstance(item.get("scenario"), dict) else {}
        acceptance = dict(item.get("acceptance", {})) if isinstance(item.get("acceptance"), dict) else {}
        metrics = dict(item.get("metrics", {})) if isinstance(item.get("metrics"), dict) else {}

        profile_name = item.get("profile_name", profile.get("name"))
        width = item.get("width", profile.get("width", scenario.get("width")))
        height = item.get("height", profile.get("height", scenario.get("height")))
        fps = item.get("fps", profile.get("fps", scenario.get("fps")))
        fps_target_met = item.get("fps_target_met", acceptance.get("fps_target_met"))
        cpu_target_applies = item.get("cpu_target_applies", acceptance.get("cpu_target_applies"))
        cpu_target_met = item.get("cpu_target_met", acceptance.get("cpu_target_met"))
        actual_fps = item.get("actual_fps", metrics.get("actual_fps"))
        cpu_percent = item.get("cpu_percent", metrics.get("cpu_percent"))
        avg_latency_ms = item.get("avg_latency_ms", metrics.get("avg_latency_ms"))

        if not isinstance(profile_name, str) or not profile_name:
            return None
        if not isinstance(width, int) or isinstance(width, bool):
            return None
        if not isinstance(height, int) or isinstance(height, bool):
            return None
        if not _is_number(fps):
            return None
        if not isinstance(fps_target_met, bool):
            return None
        if not isinstance(cpu_target_applies, bool):
            return None
        if cpu_target_met is not None and not isinstance(cpu_target_met, bool):
            return None
        if not _is_number(actual_fps):
            return None
        if not _is_number(cpu_percent):
            return None
        if not _is_number(avg_latency_ms):
            return None

        normalized.append(
            {
                "profile_name": profile_name,
                "width": width,
                "height": height,
                "fps": float(fps),
                "fps_target_met": fps_target_met,
                "cpu_target_applies": cpu_target_applies,
                "cpu_target_met": cpu_target_met,
                "actual_fps": float(actual_fps),
                "cpu_percent": float(cpu_percent),
                "avg_latency_ms": float(avg_latency_ms),
            }
        )
    return normalized


def _benchmark_artifact_surface(
    manifest_path: Path,
    value: object,
) -> dict[str, Any]:
    payload = _load_optional_json_object(manifest_path, value)
    if payload is None:
        return {
            "present": False,
            "kind": None,
            "matrix_profiles": None,
        }

    raw_kind = payload.get("kind")
    if isinstance(raw_kind, str) and raw_kind:
        kind = raw_kind
    else:
        kind = "single" if {"scenario", "metrics", "acceptance"}.issubset(payload.keys()) else None

    matrix_profiles = None
    if kind == "benchmark_matrix":
        matrix_profiles = _normalize_benchmark_matrix_profiles(payload.get("results"))

    return {
        "present": True,
        "kind": kind,
        "matrix_profiles": matrix_profiles,
    }


def _expected_benchmark_gate_statuses(
    profiles: list[dict[str, object]] | None,
) -> dict[str, str] | None:
    if profiles is None:
        return None

    observed_profile_names = {
        str(item.get("profile_name"))
        for item in profiles
        if isinstance(item.get("profile_name"), str) and item.get("profile_name")
    }
    benchmark_matrix_complete = "pass" if observed_profile_names == set(
        EXPECTED_BENCHMARK_MATRIX_PROFILE_NAMES
    ) else "fail"
    benchmark_fps_targets_met = "pass" if all(
        item.get("fps_target_met") is True for item in profiles
    ) else "fail"
    cpu_status = "fail"
    for item in profiles:
        if item.get("profile_name") == "1080p60":
            cpu_status = "pass" if item.get("cpu_target_met") is True else "fail"
            break
    return {
        "benchmark_matrix_complete": benchmark_matrix_complete,
        "benchmark_fps_targets_met": benchmark_fps_targets_met,
        "benchmark_1080p60_cpu_target_met": cpu_status,
    }


def _manual_template_surface(manifest_path: Path, value: object) -> dict[str, Any]:
    artifact_path = _resolve_artifact_path(manifest_path, value)
    if artifact_path is None or not artifact_path.is_file():
        return {
            "present": False,
            "ids_complete": False,
            "shape_complete": False,
            "check_lists_present": False,
            "step_lists_present": False,
        }

    payload = _load_json_object(artifact_path)
    ids_complete = sorted(str(key) for key in payload) == list(EXPECTED_MANUAL_TEMPLATE_IDS)
    shape_complete = True
    check_lists_present = True
    step_lists_present = True
    for entry in payload.values():
        if not isinstance(entry, dict):
            shape_complete = False
            check_lists_present = False
            step_lists_present = False
            continue
        if tuple(sorted(str(key) for key in entry.keys())) != EXPECTED_MANUAL_TEMPLATE_FIELDS:
            shape_complete = False
        if not isinstance(entry.get("checks"), list) or not entry.get("checks") or not all(
            isinstance(item, str) for item in entry.get("checks", [])
        ):
            check_lists_present = False
        if not isinstance(entry.get("steps"), list) or not entry.get("steps") or not all(
            isinstance(item, str) for item in entry.get("steps", [])
        ):
            step_lists_present = False
    return {
        "present": True,
        "ids_complete": ids_complete,
        "shape_complete": shape_complete,
        "check_lists_present": check_lists_present,
        "step_lists_present": step_lists_present,
    }


def evaluate_artifact(
    manifest_path: Path,
    *,
    require_existing_artifacts: bool,
) -> dict[str, Any]:
    payload = _load_json_object(manifest_path)
    artifacts = payload.get("artifacts")
    steps = payload.get("steps")
    summary = payload.get("summary")

    artifacts_dict = dict(artifacts) if isinstance(artifacts, dict) else {}
    steps_dict = dict(steps) if isinstance(steps, dict) else {}
    summary_dict = dict(summary) if isinstance(summary, dict) else {}

    artifact_surface = {
        "has_artifacts_object": isinstance(artifacts, dict),
        "has_steps_object": isinstance(steps, dict),
        "has_summary_object": isinstance(summary, dict),
        "has_required_artifact_keys": all(
            key in artifacts_dict for key in REQUIRED_ARTIFACT_SUFFIXES
        ),
        "artifact_suffixes_match_expected": all(
            isinstance(artifacts_dict.get(key), str)
            and str(artifacts_dict.get(key)).endswith(suffix)
            for key, suffix in REQUIRED_ARTIFACT_SUFFIXES.items()
        ),
    }

    required_existing_artifacts = {"manual_template", "validation_report"}
    for step_name, artifact_key in STEP_TO_ARTIFACT_KEY.items():
        if step_name in steps_dict:
            required_existing_artifacts.add(artifact_key)
    if "artifact_check" in steps_dict or summary_dict.get("artifact_check_present") is True:
        required_existing_artifacts.add("artifact_check_report")
    if "acceptance" in steps_dict or summary_dict.get("acceptance_present") is True:
        required_existing_artifacts.add("acceptance_report")
    if "acceptance_contract" in steps_dict or summary_dict.get("acceptance_contract_present") is True:
        required_existing_artifacts.add("acceptance_contract_report")
    existing_artifact_checks = {
        key: _artifact_path_exists(manifest_path, artifacts_dict.get(key))
        for key in sorted(required_existing_artifacts)
    }
    manual_template_surface = _manual_template_surface(
        manifest_path,
        artifacts_dict.get("manual_template"),
    )
    benchmark_artifact_surface = _benchmark_artifact_surface(
        manifest_path,
        artifacts_dict.get("benchmark_report"),
    )
    summary_benchmark_profiles = _normalize_benchmark_matrix_profiles(
        summary_dict.get("validation_benchmark_matrix_profiles")
    )
    expected_benchmark_gate_statuses = _expected_benchmark_gate_statuses(
        benchmark_artifact_surface.get("matrix_profiles")
    )

    summary_surface = {
        "has_present_flags": all(
            key in summary_dict
            for key in (
                "validation_report_present",
                "smoke_present",
                "install_session_present",
                "framebus_roundtrip_present",
                "status_binary_check_present",
                "list_devices_binary_check_present",
            )
        ),
        "present_flags_are_bool": all(
            isinstance(summary_dict.get(key), bool)
            for key in (
                "validation_report_present",
                "smoke_present",
                "install_session_present",
                "framebus_roundtrip_present",
                "status_binary_check_present",
                "list_devices_binary_check_present",
            )
        ),
        "has_effective_start_fields": all(
            key in summary_dict
            for key in ("effective_start_ready", "effective_start_blocker_code")
        ),
        "effective_start_fields_typed": _is_bool_or_none(summary_dict.get("effective_start_ready"))
        and _is_str_or_none(summary_dict.get("effective_start_blocker_code")),
        "has_effective_capability_fields": all(
            key in summary_dict
            for key in ("effective_supported_formats", "effective_supported_frame_rates")
        ),
        "has_effective_ipc_identity_fields": all(
            key in summary_dict
            for key in (
                "effective_shared_memory_name",
                "effective_mach_service_name",
                "effective_ipc_transport",
            )
        ),
        "capability_fields_typed": all(
            _is_string_list_or_none(summary_dict.get(key))
            for key in SUMMARY_FORMAT_KEYS
        )
        and all(
            _is_int_list_or_none(summary_dict.get(key))
            for key in SUMMARY_FRAME_RATE_KEYS
        ),
        "ipc_identity_fields_typed": all(
            _is_str_or_none(summary_dict.get(key))
            for key in SUMMARY_IPC_STRING_KEYS
        ),
        "capability_values_allowed": all(
            summary_dict.get(key) is None
            or set(summary_dict.get(key)).issubset(ALLOWED_FORMATS)
            for key in SUMMARY_FORMAT_KEYS
        )
        and all(
            summary_dict.get(key) is None
            or set(summary_dict.get(key)).issubset(ALLOWED_FRAME_RATES)
            for key in SUMMARY_FRAME_RATE_KEYS
        ),
        "effective_ready_consistent_with_blocker": (
            summary_dict.get("effective_start_blocker_code") not in {"ready", "ipc_environment_blocked"}
            or (
                summary_dict.get("effective_start_blocker_code") == "ready"
                and summary_dict.get("effective_start_ready") is True
            )
            or (
                summary_dict.get("effective_start_blocker_code") == "ipc_environment_blocked"
                and summary_dict.get("effective_start_ready") is False
            )
        ),
        "artifact_check_fields_typed_when_present": (
            ("artifact_check_present" not in summary_dict or isinstance(summary_dict.get("artifact_check_present"), bool))
            and ("artifact_check_passed" not in summary_dict or _is_bool_or_none(summary_dict.get("artifact_check_passed")))
        ),
        "acceptance_fields_typed_when_present": (
            ("acceptance_present" not in summary_dict or isinstance(summary_dict.get("acceptance_present"), bool))
            and ("acceptance_ready" not in summary_dict or _is_bool_or_none(summary_dict.get("acceptance_ready")))
        ),
        "acceptance_contract_fields_typed_when_present": (
            ("acceptance_contract_present" not in summary_dict or isinstance(summary_dict.get("acceptance_contract_present"), bool))
            and (
                "acceptance_contract_passed" not in summary_dict
                or _is_bool_or_none(summary_dict.get("acceptance_contract_passed"))
            )
        ),
        "list_devices_binary_check_fields_typed_when_present": (
            ("list_devices_binary_check_passed" not in summary_dict or _is_bool_or_none(summary_dict.get("list_devices_binary_check_passed")))
            and ("list_devices_binary_check_device_prefix" not in summary_dict or _is_str_or_none(summary_dict.get("list_devices_binary_check_device_prefix")))
            and ("list_devices_binary_check_filtered_device_count" not in summary_dict or _is_int_or_none(summary_dict.get("list_devices_binary_check_filtered_device_count")))
            and ("list_devices_binary_check_total_device_count" not in summary_dict or _is_int_or_none(summary_dict.get("list_devices_binary_check_total_device_count")))
            and ("list_devices_binary_check_override_no_match_ok" not in summary_dict or _is_bool_or_none(summary_dict.get("list_devices_binary_check_override_no_match_ok")))
        ),
        "summary_report_field_typed_when_present": (
            "summary_report_present" not in summary_dict
            or isinstance(summary_dict.get("summary_report_present"), bool)
        ),
        "benchmark_fields_typed_when_present": (
            ("validation_benchmark_kind" not in summary_dict or _is_str_or_none(summary_dict.get("validation_benchmark_kind")))
            and (
                "validation_benchmark_matrix_profiles" not in summary_dict
                or summary_dict.get("validation_benchmark_matrix_profiles") is None
                or summary_benchmark_profiles is not None
            )
            and all(
                summary_dict.get(key) is None or isinstance(summary_dict.get(key), str)
                for key in SUMMARY_BENCHMARK_GATE_KEYS
            )
        ),
        "benchmark_kind_consistent_with_profiles": (
            summary_dict.get("validation_benchmark_kind") != "benchmark_matrix"
            or summary_benchmark_profiles is not None
        )
        and (
            summary_benchmark_profiles is None
            or summary_dict.get("validation_benchmark_kind") == "benchmark_matrix"
        ),
        "benchmark_profile_names_unique_when_present": (
            summary_benchmark_profiles is None
            or len(
                {
                    str(item.get("profile_name"))
                    for item in summary_benchmark_profiles
                }
            )
            == len(summary_benchmark_profiles)
        ),
        "benchmark_1080p60_profile_consistent_when_present": (
            summary_benchmark_profiles is None
            or all(
                item.get("profile_name") != "1080p60"
                or (
                    item.get("width") == 1920
                    and item.get("height") == 1080
                    and item.get("fps") == 60.0
                    and item.get("cpu_target_applies") is True
                )
                for item in summary_benchmark_profiles
            )
        ),
        "benchmark_artifact_matches_summary_when_present": (
            benchmark_artifact_surface.get("present") is not True
            or (
                summary_dict.get("validation_benchmark_kind") == benchmark_artifact_surface.get("kind")
                and (
                    benchmark_artifact_surface.get("kind") != "benchmark_matrix"
                    or summary_benchmark_profiles == benchmark_artifact_surface.get("matrix_profiles")
                )
            )
        ),
        "benchmark_gate_statuses_match_artifact_when_present": (
            expected_benchmark_gate_statuses is None
            or all(
                summary_dict.get(key) in {None, expected_benchmark_gate_statuses[key]}
                for key in SUMMARY_BENCHMARK_GATE_KEYS
            )
        ),
        "entrypoints_contract_fields_typed_when_present": (
            ("entrypoints_contract_present" not in summary_dict or isinstance(summary_dict.get("entrypoints_contract_present"), bool))
            and all(
                _is_bool_or_none(summary_dict.get(key))
                for key in SUMMARY_ENTRYPOINTS_BOOL_KEYS
            )
        ),
        "sdk_contract_fields_typed_when_present": (
            ("sdk_contract_present" not in summary_dict or isinstance(summary_dict.get("sdk_contract_present"), bool))
            and all(
                _is_bool_or_none(summary_dict.get(key))
                for key in SUMMARY_SDK_CONTRACT_BOOL_KEYS
            )
        ),
        "target_app_identity_fields_typed_when_present": all(
            _is_string_list_or_none(summary_dict.get(key))
            for key in SUMMARY_TARGET_APP_LIST_KEYS
        )
        and (
            "validation_target_app_ids_complete" not in summary_dict
            or _is_bool_or_none(summary_dict.get("validation_target_app_ids_complete"))
        ),
        "release_sync_ipc_fields_typed_when_present": all(
            _is_bool_or_none(summary_dict.get(key))
            for key in SUMMARY_RELEASE_SYNC_IPC_BOOL_KEYS
        ),
        "install_session_sync_ipc_fields_typed_when_present": all(
            _is_bool_or_none(summary_dict.get(key))
            for key in SUMMARY_INSTALL_SESSION_SYNC_IPC_BOOL_KEYS
        )
        and all(
            _is_str_or_none(summary_dict.get(key))
            for key in SUMMARY_INSTALL_SESSION_SYNC_IPC_STRING_KEYS
        )
        and (
            "install_session_sync_ipc_returncode" not in summary_dict
            or _is_int_or_none(summary_dict.get("install_session_sync_ipc_returncode"))
        ),
        "acceptance_gate_fields_typed_when_present": all(
            summary_dict.get(key) is None or isinstance(summary_dict.get(key), str)
            for key in SUMMARY_ACCEPTANCE_GATE_KEYS
        ),
        "sync_ipc_gate_consistent_with_runtime_sync": (
            summary_dict.get("sync_ipc_control_plane_ready") != "pass"
            or (
                summary_dict.get("install_session_sync_ipc_present") is True
                and summary_dict.get("install_session_sync_ipc_supported") is True
                and summary_dict.get("install_session_sync_ipc_success") is True
            )
        ),
    }

    consistency = {
        "artifact_surface_complete": all(bool(value) for value in artifact_surface.values()),
        "manual_template_surface_complete": all(bool(value) for value in manual_template_surface.values()),
        "summary_surface_complete": all(bool(value) for value in summary_surface.values()),
        "existing_artifacts_match_expected": (
            all(bool(value) for value in existing_artifact_checks.values())
            if require_existing_artifacts
            else True
        ),
    }
    consistency["all_checks_passed"] = all(
        bool(value) for value in consistency.values()
    )

    return {
        "manifest_path": str(manifest_path),
        "artifact_surface": artifact_surface,
        "existing_artifact_checks": existing_artifact_checks,
        "benchmark_artifact_surface": benchmark_artifact_surface,
        "manual_template_surface": manual_template_surface,
        "summary_surface": summary_surface,
        "summary_snapshot": {
            key: summary_dict.get(key)
            for key in (
                "effective_start_ready",
                "effective_start_blocker_code",
                "effective_shared_memory_name",
                "effective_mach_service_name",
                "effective_ipc_transport",
                "effective_supported_formats",
                "effective_supported_frame_rates",
                "release_sync_ipc_tool_exists",
                "release_sync_ipc_tool_signed",
                "release_sync_ipc_tool_universal2_ready",
                "sync_ipc_control_plane_ready",
                "validation_shared_memory_name",
                "validation_mach_service_name",
                "validation_ipc_transport",
                "validation_benchmark_kind",
                "validation_benchmark_matrix_profiles",
                "validation_supported_formats",
                "validation_reviewed_app_ids",
                "validation_unreviewed_app_ids",
                "validation_observed_target_app_ids",
                "validation_missing_target_app_ids",
                "validation_unexpected_target_app_ids",
                "validation_target_app_ids_complete",
                "benchmark_matrix_complete",
                "benchmark_fps_targets_met",
                "benchmark_1080p60_cpu_target_met",
                "smoke_shared_memory_name",
                "smoke_mach_service_name",
                "smoke_ipc_transport",
                "smoke_supported_formats",
                "install_session_shared_memory_name",
                "install_session_mach_service_name",
                "install_session_ipc_transport",
                "install_session_supported_formats",
                "install_session_sync_ipc_present",
                "install_session_sync_ipc_supported",
                "install_session_sync_ipc_success",
                "install_session_sync_ipc_phase",
                "install_session_sync_ipc_shared_memory_name",
                "install_session_sync_ipc_transport",
                "install_session_sync_ipc_returncode",
                "list_devices_binary_check_device_prefix",
                "list_devices_binary_check_filtered_device_count",
                "list_devices_binary_check_total_device_count",
                "entrypoints_contract_present",
                "entrypoints_contract_passed",
                "entrypoints_contract_surface_complete",
                "entrypoints_contract_demo_case_complete",
                "entrypoints_contract_cli_case_complete",
                "entrypoints_contract_desktop_case_complete",
                "sdk_contract_present",
                "sdk_contract_passed",
                "sdk_contract_constructor_shape_aligned",
                "sdk_contract_direct_sender_exports_present",
                "acceptance_contract_present",
                "acceptance_contract_passed",
            )
        },
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS validation-session artifact replay checker"
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--require-existing-artifacts", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"validation-session manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    payload = evaluate_artifact(
        manifest_path,
        require_existing_artifacts=bool(args.require_existing_artifacts),
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    if not bool(payload["consistency"]["all_checks_passed"]):
        print("macOS validation-session artifact replay mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
