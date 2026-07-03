# SPDX-License-Identifier: Apache-2.0
"""macOS validation session helper.

Bootstraps a lab-validation directory by running the PySide6 demo, producer
benchmark, manual-template generation, and final validation report assembly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DEMO_TOOL = ROOT / "tools" / "pyside6_virtual_camera_demo.py"
DEFAULT_BENCHMARK_TOOL = ROOT / "tools" / "macos_benchmark.py"
DEFAULT_DIRECT_PUSH_DEMO_TOOL = ROOT / "tools" / "macos_direct_push_demo.py"
DEFAULT_DIRECT_SENDER_OBJECT_DEMO_TOOL = ROOT / "tools" / "macos_direct_sender_object_demo.py"
DEFAULT_PREFLIGHT_TOOL = ROOT / "tools" / "macos_toolchain_preflight.py"
DEFAULT_RELEASE_DIAGNOSTICS_TOOL = ROOT / "tools" / "macos_release_diagnostics.py"
DEFAULT_VALIDATION_REPORT_TOOL = ROOT / "tools" / "macos_validation_report.py"
DEFAULT_SMOKE_TOOL = ROOT / "tools" / "macos_smoke.py"
DEFAULT_INSTALL_SESSION_TOOL = ROOT / "tools" / "macos_install_session.py"
DEFAULT_FRAMEBUS_ROUNDTRIP_TOOL = ROOT / "tools" / "macos_framebus_roundtrip.py"
DEFAULT_STATUS_BINARY_CHECK_TOOL = ROOT / "tools" / "macos_status_binary_check.py"
DEFAULT_LIST_DEVICES_BINARY_CHECK_TOOL = ROOT / "tools" / "macos_list_devices_binary_check.py"
DEFAULT_ENTRYPOINTS_CONTRACT_TOOL = ROOT / "tools" / "macos_entrypoints_contract.py"
DEFAULT_SDK_CONTRACT_TOOL = ROOT / "tools" / "macos_sdk_contract.py"
DEFAULT_ARTIFACT_CHECK_TOOL = ROOT / "tools" / "macos_validation_session_artifact_check.py"
DEFAULT_ACCEPTANCE_TOOL = ROOT / "tools" / "macos_validation_session_acceptance.py"
DEFAULT_ACCEPTANCE_CONTRACT_TOOL = ROOT / "tools" / "macos_validation_session_acceptance_contract.py"
DEFAULT_SUMMARY_TOOL = ROOT / "tools" / "macos_validation_session_summary.py"
DEFAULT_CAMERA_NAME = "AK Virtual Camera"
EXPECTED_MANUAL_TEMPLATE_IDS = (
    "facetime",
    "google_meet",
    "obs",
    "quicktime",
    "teams",
    "zoom",
)
MANUAL_TEMPLATE_DISPLAY_NAMES = {
    "facetime": "FaceTime",
    "google_meet": "Google Meet",
    "obs": "OBS",
    "quicktime": "QuickTime",
    "teams": "Teams",
    "zoom": "Zoom",
}
ACCEPTANCE_GATE_NAMES = (
    "macos_13_plus_declared",
    "universal2_ready",
    "release_packaging_ready",
    "signing_evidence_ready",
    "notarization_tooling_ready",
    "pyside6_path_exercised",
    "python_entrypoints_consistent",
    "target_apps_all_passed",
    "system_camera_device_visible",
    "benchmark_matrix_complete",
    "benchmark_fps_targets_met",
    "benchmark_1080p60_cpu_target_met",
    "auto_install_ready",
    "artifact_replay_passed",
    "runtime_assets_packaged",
    "sync_ipc_control_plane_ready",
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _load_json_object(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_container_app_args(
    *,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
) -> tuple[str | None, str | None]:
    if app_bundle and host_bundle and app_bundle != host_bundle:
        raise ValueError("--app-bundle and --host-bundle cannot point at different macOS app bundles")
    if app_executable and host_executable and app_executable != host_executable:
        raise ValueError(
            "--app-executable and --host-executable cannot point at different macOS app executables"
        )
    return app_bundle or host_bundle, app_executable or host_executable


def _normalize_supported_formats(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


def _normalize_supported_frame_rates(value: object) -> list[int] | None:
    if not isinstance(value, list):
        return None
    normalized: list[int] = []
    for item in value:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [str(item) for item in value if item is not None]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_first_present(*values: list[object] | None) -> list[object] | None:
    for value in values:
        if value is not None:
            return value
    return None


def _pick_first_non_none(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_validation_app_matrix(value: object) -> dict[str, dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    matrix: dict[str, dict[str, object]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        app_id = item.get("id")
        if not isinstance(app_id, str) or not app_id:
            continue
        normalized_item: dict[str, object] = {
            "name": str(item.get("name", app_id)),
            "reviewed": bool(item.get("reviewed", False)),
            "validated": bool(item.get("validated", False)),
            "result": str(item.get("result", "")),
            "notes": str(item.get("notes", "")) if item.get("notes") is not None else "",
            "ready": bool(item.get("ready", False)),
            "status": str(item.get("status", "")) if item.get("status") is not None else "",
            "steps": [str(step) for step in item.get("steps", []) if step is not None],
            "checks": [str(check) for check in item.get("checks", []) if check is not None],
        }
        if isinstance(item.get("evidence"), dict):
            normalized_item["evidence"] = _normalize_manual_evidence(item.get("evidence"))
        matrix[app_id] = normalized_item
    return matrix or None


def _normalize_manual_evidence(value: object) -> dict[str, object]:
    evidence = value if isinstance(value, dict) else {}
    return {
        "device_listed": bool(evidence.get("device_listed", False)),
        "device_selected": bool(evidence.get("device_selected", False)),
        "preview_visible": bool(evidence.get("preview_visible", False)),
        "screenshot": str(evidence.get("screenshot", "")) if evidence.get("screenshot") is not None else "",
    }


def _validation_app_matrix_ids_with_result(
    matrix: dict[str, dict[str, object]] | None,
    result: str,
) -> list[str] | None:
    if not isinstance(matrix, dict):
        return None
    return sorted(
        app_id
        for app_id, item in matrix.items()
        if isinstance(item, dict) and str(item.get("result")) == result
    )


def _validation_app_matrix_unreviewed_ids(
    matrix: dict[str, dict[str, object]] | None,
) -> list[str] | None:
    if not isinstance(matrix, dict):
        return None
    return sorted(
        app_id
        for app_id, item in matrix.items()
        if isinstance(item, dict) and not bool(item.get("reviewed"))
    )


def _validation_app_matrix_reviewed_count(
    matrix: dict[str, dict[str, object]] | None,
) -> int | None:
    if not isinstance(matrix, dict):
        return None
    return sum(1 for item in matrix.values() if isinstance(item, dict) and bool(item.get("reviewed")))


def _normalize_benchmark_matrix_profiles(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        profile_name = item.get("profile_name")
        if not isinstance(profile_name, str) or not profile_name:
            profile = item.get("profile")
            if isinstance(profile, dict):
                profile_name = profile.get("name")
        if not isinstance(profile_name, str) or not profile_name:
            continue
        profile = item.get("profile")
        metrics = item.get("metrics")
        acceptance = item.get("acceptance")
        if not isinstance(profile, dict):
            profile = {}
        if not isinstance(metrics, dict):
            metrics = {}
        if not isinstance(acceptance, dict):
            acceptance = {}
        normalized.append(
            {
                "profile_name": profile_name,
                "width": _optional_int(item.get("width") if item.get("width") is not None else profile.get("width")),
                "height": _optional_int(item.get("height") if item.get("height") is not None else profile.get("height")),
                "fps": _optional_float(item.get("fps") if item.get("fps") is not None else profile.get("fps")),
                "fps_target_met": (
                    item.get("fps_target_met")
                    if item.get("fps_target_met") is not None
                    else acceptance.get("fps_target_met")
                ),
                "cpu_target_applies": (
                    item.get("cpu_target_applies")
                    if item.get("cpu_target_applies") is not None
                    else acceptance.get("cpu_target_applies")
                ),
                "cpu_target_met": (
                    item.get("cpu_target_met")
                    if item.get("cpu_target_met") is not None
                    else acceptance.get("cpu_target_met")
                ),
                "actual_fps": _optional_float(
                    item.get("actual_fps") if item.get("actual_fps") is not None else metrics.get("actual_fps")
                ),
                "cpu_percent": _optional_float(
                    item.get("cpu_percent") if item.get("cpu_percent") is not None else metrics.get("cpu_percent")
                ),
                "avg_latency_ms": _optional_float(
                    item.get("avg_latency_ms")
                    if item.get("avg_latency_ms") is not None
                    else metrics.get("avg_latency_ms")
                ),
            }
        )
    return normalized or None


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _sequence_length(value: object) -> int | None:
    if not isinstance(value, list):
        return None
    return len(value)


def _default_manual_template_entry(app_id: str, camera_name: str) -> dict[str, object]:
    app_name = MANUAL_TEMPLATE_DISPLAY_NAMES.get(app_id, app_id)
    return {
        "name": app_name,
        "ready": False,
        "status": f"待在 {app_name} 中验证 {camera_name}",
        "steps": [
            f"打开 {app_name} 的摄像头或视频设置界面。",
            f"选择 {camera_name} 作为输入摄像头。",
        ],
        "checks": [
            f"{app_name} 设备列表中出现 {camera_name}。",
            "预览窗口显示实时画面。",
        ],
        "evidence": {
            "device_listed": False,
            "device_selected": False,
            "preview_visible": False,
            "screenshot": "",
        },
        "validated": False,
        "result": "pending",
        "notes": "",
    }


def _normalize_manual_template_payload(
    payload: object,
    *,
    camera_name: str,
) -> dict[str, dict[str, object]]:
    source = payload if isinstance(payload, dict) else {}
    normalized: dict[str, dict[str, object]] = {}
    for app_id in EXPECTED_MANUAL_TEMPLATE_IDS:
        existing = source.get(app_id)
        item = dict(existing) if isinstance(existing, dict) else {}
        default = _default_manual_template_entry(app_id, camera_name)
        evidence = item.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}
        normalized[app_id] = {
            "name": _optional_string(item.get("name")) or str(default["name"]),
            "ready": bool(item.get("ready", default["ready"])),
            "status": _optional_string(item.get("status")) or str(default["status"]),
            "steps": (
                [str(step) for step in item.get("steps", []) if step is not None]
                if isinstance(item.get("steps"), list)
                else list(default["steps"])
            ),
            "checks": (
                [str(check) for check in item.get("checks", []) if check is not None]
                if isinstance(item.get("checks"), list)
                else list(default["checks"])
            ),
            "evidence": {
                "device_listed": bool(
                    evidence.get("device_listed", default["evidence"]["device_listed"])
                ),
                "device_selected": bool(
                    evidence.get("device_selected", default["evidence"]["device_selected"])
                ),
                "preview_visible": bool(
                    evidence.get("preview_visible", default["evidence"]["preview_visible"])
                ),
                "screenshot": _optional_string(evidence.get("screenshot"))
                or str(default["evidence"]["screenshot"]),
            },
            "validated": bool(item.get("validated", default["validated"])),
            "result": _optional_string(item.get("result")) or str(default["result"]),
            "notes": _optional_string(item.get("notes")) or str(default["notes"]),
        }
    return normalized


def _normalize_manual_template_file(path: Path, *, camera_name: str) -> None:
    existing = _load_json_object(path)
    normalized = _normalize_manual_template_payload(existing, camera_name=camera_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_direct_push_step(value: object) -> dict[str, object]:
    step = value if isinstance(value, dict) else {}
    payload = dict(step.get("payload", {})) if isinstance(step.get("payload"), dict) else {}
    probe_payload = (
        dict(step.get("probe_payload", {})) if isinstance(step.get("probe_payload"), dict) else {}
    )
    request = dict(step.get("request", {})) if isinstance(step.get("request"), dict) else {}
    effective_payload = payload or probe_payload
    runtime_snapshot = (
        dict(effective_payload.get("runtime_snapshot", {}))
        if isinstance(effective_payload.get("runtime_snapshot"), dict)
        else {}
    )
    snapshot = (
        dict(effective_payload.get("direct_sender_device_snapshot", {}))
        if isinstance(effective_payload.get("direct_sender_device_snapshot"), dict)
        else {}
    )
    if not snapshot and isinstance(effective_payload.get("device_snapshot"), dict):
        snapshot = dict(effective_payload.get("device_snapshot", {}))
    runtime_topology = (
        dict(effective_payload.get("runtime_topology", {}))
        if isinstance(effective_payload.get("runtime_topology"), dict)
        else (
            dict(runtime_snapshot.get("runtime_topology", {}))
            if isinstance(runtime_snapshot.get("runtime_topology"), dict)
            else {}
        )
    )
    request_snapshot = (
        dict(effective_payload.get("requested_camera_access_snapshot", {}))
        if isinstance(effective_payload.get("requested_camera_access_snapshot"), dict)
        else {}
    )
    return {
        "present": bool(step),
        "attempted": step.get("attempted"),
        "skipped": step.get("skipped"),
        "skip_reason": _optional_string(step.get("skip_reason")),
        "returncode": _optional_int(step.get("returncode")),
        "mode": _optional_string(effective_payload.get("mode")),
        "frame_source_kind": _optional_string(effective_payload.get("frame_source_kind")),
        "python_entrypoint_kind": _optional_string(effective_payload.get("python_entrypoint_kind")),
        "requested_frame_kind": _optional_string(
            effective_payload.get("requested_frame_kind") or request.get("requested_frame_kind")
        ),
        "requested_entrypoint": _optional_string(
            effective_payload.get("requested_entrypoint") or request.get("requested_entrypoint")
        ),
        "sdk_direct_push_used": effective_payload.get("sdk_direct_push_used"),
        "backend_name": _optional_string(
            effective_payload.get("backend_name") or runtime_snapshot.get("backend_name")
        ),
        "using_direct_sender": (
            effective_payload.get("using_direct_sender")
            if effective_payload.get("using_direct_sender") is not None
            else runtime_snapshot.get("using_direct_sender")
        ),
        "direct_sender_attempted": (
            effective_payload.get("direct_sender_attempted")
            if effective_payload.get("direct_sender_attempted") is not None
            else runtime_snapshot.get("direct_sender_attempted")
        ),
        "direct_sender_state": _optional_string(
            effective_payload.get("direct_sender_state") or runtime_snapshot.get("direct_sender_state")
        ),
        "runtime_topology_kind": _optional_string(
            effective_payload.get("runtime_topology_kind") or runtime_topology.get("runtime_topology_kind")
        ),
        "runtime_frame_path": _optional_string(
            effective_payload.get("runtime_frame_path") or runtime_topology.get("runtime_frame_path")
        ),
        "runtime_host_role": _optional_string(
            effective_payload.get("runtime_host_role") or runtime_topology.get("runtime_host_role")
        ),
        "runtime_host_in_frame_hot_path": (
            effective_payload.get("runtime_host_in_frame_hot_path")
            if effective_payload.get("runtime_host_in_frame_hot_path") is not None
            else runtime_topology.get("runtime_host_in_frame_hot_path")
        ),
        "runtime_dedicated_host_daemon_required": (
            effective_payload.get("runtime_dedicated_host_daemon_required")
            if effective_payload.get("runtime_dedicated_host_daemon_required") is not None
            else runtime_topology.get("runtime_dedicated_host_daemon_required")
        ),
        "runtime_container_app_configured": (
            effective_payload.get("runtime_container_app_configured")
            if effective_payload.get("runtime_container_app_configured") is not None
            else runtime_topology.get("runtime_container_app_configured")
        ),
        "runtime_data_plane": _optional_string(
            effective_payload.get("runtime_data_plane") or runtime_topology.get("runtime_data_plane")
        ),
        "runtime_control_plane": _optional_string(
            effective_payload.get("runtime_control_plane") or runtime_topology.get("runtime_control_plane")
        ),
        "direct_sender_target_name": _optional_string(
            effective_payload.get("direct_sender_target_name")
            or runtime_snapshot.get("direct_sender_target_name")
        ),
        "direct_sender_library_path": _optional_string(
            effective_payload.get("direct_sender_library_path")
            or runtime_snapshot.get("direct_sender_library_path")
        ),
        "direct_sender_last_error": _optional_string(
            effective_payload.get("direct_sender_last_error")
            or runtime_snapshot.get("direct_sender_last_error")
        ),
        "camera_name": _optional_string(
            effective_payload.get("camera_name") or runtime_snapshot.get("camera_name")
        ),
        "consumer_count": _optional_int(
            effective_payload.get("consumer_count")
            if effective_payload.get("consumer_count") is not None
            else runtime_snapshot.get("consumer_count")
        ),
        "requested_frames": _optional_int(effective_payload.get("requested_frames")),
        "frames_sent": _optional_int(effective_payload.get("frames_sent")),
        "direct_only": effective_payload.get("direct_only"),
        "probe_only": (
            effective_payload.get("probe_only")
            if effective_payload.get("probe_only") is not None
            else effective_payload.get("inspect_only")
        ),
        "allow_shared_memory_fallback": effective_payload.get(
            "allow_shared_memory_fallback",
            (
                request.get("allow_shared_memory_fallback")
                if request.get("allow_shared_memory_fallback") is not None
                else effective_payload.get("shared_memory_fallback_used")
            ),
        ),
        "requested_camera_access": effective_payload.get(
            "requested_camera_access",
            request.get("requested_camera_access"),
        ),
        "helper_hot_path_used": (
            effective_payload.get("helper_hot_path_used")
            if effective_payload.get("helper_hot_path_used") is not None
            else runtime_snapshot.get("helper_hot_path_used")
        ),
        "shared_memory_fallback_used": (
            effective_payload.get("shared_memory_fallback_used")
            if effective_payload.get("shared_memory_fallback_used") is not None
            else runtime_snapshot.get("shared_memory_fallback_used")
        ),
        "runtime_snapshot_present": bool(runtime_snapshot),
        "runtime_snapshot_started": (
            bool(runtime_snapshot.get("started"))
            if runtime_snapshot.get("started") is not None
            else None
        ),
        "runtime_snapshot_shared_memory_name": _optional_string(
            runtime_snapshot.get("shared_memory_name")
        ),
        "runtime_snapshot_last_frame_fourcc": _optional_int(
            runtime_snapshot.get("last_frame_fourcc")
        ),
        "runtime_snapshot_last_frame_format_name": _optional_string(
            runtime_snapshot.get("last_frame_format_name")
        ),
        "error": _optional_string(effective_payload.get("error")),
        "probe_payload_present": bool(probe_payload),
        "direct_sender_device_snapshot_present": bool(snapshot),
        "requested_camera_access_snapshot_present": bool(request_snapshot),
        "direct_sender_visible_all_devices": _normalize_string_list(snapshot.get("all_devices")),
        "direct_sender_visible_avfoundation_devices": _normalize_string_list(
            snapshot.get("avfoundation_devices")
        ),
        "direct_sender_visible_cmio_devices": _normalize_string_list(snapshot.get("cmio_devices")),
        "camera_access_status": _optional_string(snapshot.get("camera_access_status")),
        "camera_access_authorized": snapshot.get("camera_access_authorized"),
        "camera_access_denied": snapshot.get("camera_access_denied"),
        "camera_access_restricted": snapshot.get("camera_access_restricted"),
        "camera_access_not_determined": snapshot.get("camera_access_not_determined"),
        "environment_device_enumeration_empty": snapshot.get(
            "environment_device_enumeration_empty"
        ),
        "requested_camera_access_visible_all_devices": _normalize_string_list(
            request_snapshot.get("all_devices")
        ),
        "requested_camera_access_visible_avfoundation_devices": _normalize_string_list(
            request_snapshot.get("avfoundation_devices")
        ),
        "requested_camera_access_visible_cmio_devices": _normalize_string_list(
            request_snapshot.get("cmio_devices")
        ),
        "requested_camera_access_status": _optional_string(
            request_snapshot.get("camera_access_status")
        ),
        "requested_camera_access_authorized": request_snapshot.get("camera_access_authorized"),
        "requested_camera_access_denied": request_snapshot.get("camera_access_denied"),
        "requested_camera_access_restricted": request_snapshot.get("camera_access_restricted"),
        "requested_camera_access_not_determined": request_snapshot.get(
            "camera_access_not_determined"
        ),
        "requested_camera_access_environment_device_enumeration_empty": request_snapshot.get(
            "environment_device_enumeration_empty"
        ),
    }


def _has_runtime_topology_fields(payload: dict[str, object]) -> bool:
    return any(
        payload.get(key) is not None
        for key in (
            "runtime_topology_kind",
            "runtime_frame_path",
            "runtime_host_role",
            "runtime_host_in_frame_hot_path",
            "runtime_dedicated_host_daemon_required",
            "runtime_container_app_configured",
            "runtime_data_plane",
            "runtime_control_plane",
        )
    )


def _prefixed_direct_step_summary_fields(prefix: str, step: dict[str, object]) -> dict[str, object]:
    return {
        f"{prefix}_present": step.get("present"),
        f"{prefix}_attempted": step.get("attempted"),
        f"{prefix}_skipped": step.get("skipped"),
        f"{prefix}_skip_reason": step.get("skip_reason"),
        f"{prefix}_returncode": step.get("returncode"),
        f"{prefix}_mode": step.get("mode"),
        f"{prefix}_frame_source_kind": step.get("frame_source_kind"),
        f"{prefix}_python_entrypoint_kind": step.get("python_entrypoint_kind"),
        f"{prefix}_requested_frame_kind": step.get("requested_frame_kind"),
        f"{prefix}_requested_entrypoint": step.get("requested_entrypoint"),
        f"{prefix}_sdk_direct_push_used": step.get("sdk_direct_push_used"),
        f"{prefix}_backend_name": step.get("backend_name"),
        f"{prefix}_using_direct_sender": step.get("using_direct_sender"),
        f"{prefix}_direct_sender_attempted": step.get("direct_sender_attempted"),
        f"{prefix}_direct_sender_state": step.get("direct_sender_state"),
        f"{prefix}_runtime_topology_kind": step.get("runtime_topology_kind"),
        f"{prefix}_runtime_frame_path": step.get("runtime_frame_path"),
        f"{prefix}_runtime_host_role": step.get("runtime_host_role"),
        f"{prefix}_runtime_host_in_frame_hot_path": step.get("runtime_host_in_frame_hot_path"),
        f"{prefix}_runtime_dedicated_host_daemon_required": step.get(
            "runtime_dedicated_host_daemon_required"
        ),
        f"{prefix}_runtime_container_app_configured": step.get(
            "runtime_container_app_configured"
        ),
        f"{prefix}_runtime_data_plane": step.get("runtime_data_plane"),
        f"{prefix}_runtime_control_plane": step.get("runtime_control_plane"),
        f"{prefix}_direct_sender_target_name": step.get("direct_sender_target_name"),
        f"{prefix}_direct_sender_library_path": step.get("direct_sender_library_path"),
        f"{prefix}_direct_sender_last_error": step.get("direct_sender_last_error"),
        f"{prefix}_camera_name": step.get("camera_name"),
        f"{prefix}_consumer_count": step.get("consumer_count"),
        f"{prefix}_requested_frames": step.get("requested_frames"),
        f"{prefix}_frames_sent": step.get("frames_sent"),
        f"{prefix}_direct_only": step.get("direct_only"),
        f"{prefix}_probe_only": step.get("probe_only"),
        f"{prefix}_allow_shared_memory_fallback": step.get("allow_shared_memory_fallback"),
        f"{prefix}_requested_camera_access": step.get("requested_camera_access"),
        f"{prefix}_helper_hot_path_used": step.get("helper_hot_path_used"),
        f"{prefix}_shared_memory_fallback_used": step.get("shared_memory_fallback_used"),
        f"{prefix}_runtime_snapshot_present": step.get("runtime_snapshot_present"),
        f"{prefix}_runtime_snapshot_started": step.get("runtime_snapshot_started"),
        f"{prefix}_runtime_snapshot_shared_memory_name": step.get(
            "runtime_snapshot_shared_memory_name"
        ),
        f"{prefix}_runtime_snapshot_last_frame_fourcc": step.get(
            "runtime_snapshot_last_frame_fourcc"
        ),
        f"{prefix}_runtime_snapshot_last_frame_format_name": step.get(
            "runtime_snapshot_last_frame_format_name"
        ),
        f"{prefix}_error": step.get("error"),
        f"{prefix}_probe_payload_present": step.get("probe_payload_present"),
        f"{prefix}_direct_sender_device_snapshot_present": step.get(
            "direct_sender_device_snapshot_present"
        ),
        f"{prefix}_requested_camera_access_snapshot_present": step.get(
            "requested_camera_access_snapshot_present"
        ),
        f"{prefix}_camera_access_status": step.get("camera_access_status"),
        f"{prefix}_camera_access_authorized": step.get("camera_access_authorized"),
        f"{prefix}_camera_access_denied": step.get("camera_access_denied"),
        f"{prefix}_camera_access_restricted": step.get("camera_access_restricted"),
        f"{prefix}_camera_access_not_determined": step.get("camera_access_not_determined"),
        f"{prefix}_environment_device_enumeration_empty": step.get(
            "environment_device_enumeration_empty"
        ),
        f"{prefix}_visible_all_devices": step.get("direct_sender_visible_all_devices"),
        f"{prefix}_visible_avfoundation_devices": step.get(
            "direct_sender_visible_avfoundation_devices"
        ),
        f"{prefix}_visible_cmio_devices": step.get("direct_sender_visible_cmio_devices"),
        f"{prefix}_requested_camera_access_status": step.get("requested_camera_access_status"),
        f"{prefix}_requested_camera_access_authorized": step.get(
            "requested_camera_access_authorized"
        ),
        f"{prefix}_requested_camera_access_denied": step.get("requested_camera_access_denied"),
        f"{prefix}_requested_camera_access_restricted": step.get(
            "requested_camera_access_restricted"
        ),
        f"{prefix}_requested_camera_access_not_determined": step.get(
            "requested_camera_access_not_determined"
        ),
        f"{prefix}_requested_camera_access_environment_device_enumeration_empty": step.get(
            "requested_camera_access_environment_device_enumeration_empty"
        ),
        f"{prefix}_requested_camera_access_visible_all_devices": step.get(
            "requested_camera_access_visible_all_devices"
        ),
        f"{prefix}_requested_camera_access_visible_avfoundation_devices": step.get(
            "requested_camera_access_visible_avfoundation_devices"
        ),
        f"{prefix}_requested_camera_access_visible_cmio_devices": step.get(
            "requested_camera_access_visible_cmio_devices"
        ),
    }


def _probe_case_by_name(value: object, name: str) -> dict[str, object] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("name") == name:
            return item
    return None


def _merge_artifact_check_summary(
    summary: dict[str, object],
    artifact_check_payload: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(summary)
    if not isinstance(artifact_check_payload, dict):
        merged["artifact_check_present"] = False
        merged["artifact_check_passed"] = None
        return merged

    consistency = (
        dict(artifact_check_payload.get("consistency", {}))
        if isinstance(artifact_check_payload.get("consistency"), dict)
        else {}
    )
    merged["artifact_check_present"] = True
    merged["artifact_check_passed"] = consistency.get("all_checks_passed")
    return merged


def _merge_acceptance_summary(
    summary: dict[str, object],
    acceptance_payload: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(summary)
    if not isinstance(acceptance_payload, dict):
        merged["acceptance_present"] = False
        merged["acceptance_ready"] = None
        merged["acceptance_passed_count"] = None
        merged["acceptance_failed_count"] = None
        merged["acceptance_unknown_count"] = None
        merged["acceptance_failed_criteria"] = None
        merged["acceptance_unknown_criteria"] = None
        merged["manual_app_validation_ready"] = None
        merged["manual_app_validation_failed_criteria"] = None
        merged["manual_app_validation_unknown_criteria"] = None
        merged["manual_app_validation_blockers"] = None
        for gate_name in ACCEPTANCE_GATE_NAMES:
            merged[gate_name] = None
        return merged

    acceptance_summary = (
        dict(acceptance_payload.get("summary", {}))
        if isinstance(acceptance_payload.get("summary"), dict)
        else {}
    )
    criteria_payload = acceptance_payload.get("criteria")
    criteria_by_name: dict[str, dict[str, object]] = {}
    if isinstance(criteria_payload, list):
        for item in criteria_payload:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                criteria_by_name[name] = dict(item)
    merged["acceptance_present"] = True
    merged["acceptance_ready"] = acceptance_summary.get("acceptance_ready")
    merged["acceptance_passed_count"] = acceptance_summary.get("passed_count")
    merged["acceptance_failed_count"] = acceptance_summary.get("failed_count")
    merged["acceptance_unknown_count"] = acceptance_summary.get("unknown_count")
    merged["acceptance_failed_criteria"] = acceptance_summary.get("failed_criteria")
    merged["acceptance_unknown_criteria"] = acceptance_summary.get("unknown_criteria")
    merged["manual_app_validation_ready"] = acceptance_summary.get("manual_app_validation_ready")
    merged["manual_app_validation_failed_criteria"] = acceptance_summary.get(
        "manual_app_validation_failed_criteria"
    )
    merged["manual_app_validation_unknown_criteria"] = acceptance_summary.get(
        "manual_app_validation_unknown_criteria"
    )
    merged["manual_app_validation_blockers"] = acceptance_summary.get(
        "manual_app_validation_blockers"
    )
    for gate_name in ACCEPTANCE_GATE_NAMES:
        gate = criteria_by_name.get(gate_name, {})
        merged[gate_name] = gate.get("status") if gate else None
    return merged


def _merge_acceptance_contract_summary(
    summary: dict[str, object],
    acceptance_contract_payload: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(summary)
    if not isinstance(acceptance_contract_payload, dict):
        merged["acceptance_contract_present"] = False
        merged["acceptance_contract_passed"] = None
        return merged

    consistency = (
        dict(acceptance_contract_payload.get("consistency", {}))
        if isinstance(acceptance_contract_payload.get("consistency"), dict)
        else {}
    )
    merged["acceptance_contract_present"] = True
    merged["acceptance_contract_passed"] = consistency.get("all_checks_passed")
    return merged


def _merge_entrypoints_contract_summary(
    summary: dict[str, object],
    entrypoints_payload: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(summary)
    if not isinstance(entrypoints_payload, dict):
        merged["entrypoints_contract_present"] = False
        merged["entrypoints_contract_passed"] = None
        merged["entrypoints_contract_surface_complete"] = None
        merged["entrypoints_contract_demo_case_complete"] = None
        merged["entrypoints_contract_cli_case_complete"] = None
        merged["entrypoints_contract_desktop_case_complete"] = None
        return merged

    consistency = (
        dict(entrypoints_payload.get("consistency", {}))
        if isinstance(entrypoints_payload.get("consistency"), dict)
        else {}
    )
    merged["entrypoints_contract_present"] = True
    merged["entrypoints_contract_passed"] = consistency.get("all_checks_passed")
    merged["entrypoints_contract_surface_complete"] = consistency.get("surface_complete")
    merged["entrypoints_contract_demo_case_complete"] = consistency.get("demo_case_complete")
    merged["entrypoints_contract_cli_case_complete"] = consistency.get("cli_case_complete")
    merged["entrypoints_contract_desktop_case_complete"] = consistency.get("desktop_case_complete")
    return merged


def _merge_sdk_contract_summary(
    summary: dict[str, object],
    sdk_payload: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(summary)
    if not isinstance(sdk_payload, dict):
        merged["sdk_contract_present"] = False
        merged["sdk_contract_passed"] = None
        merged["sdk_contract_constructor_shape_aligned"] = None
        merged["sdk_contract_direct_sender_exports_present"] = None
        return merged

    consistency = (
        dict(sdk_payload.get("consistency", {}))
        if isinstance(sdk_payload.get("consistency"), dict)
        else {}
    )
    merged["sdk_contract_present"] = True
    merged["sdk_contract_passed"] = consistency.get("all_checks_passed")
    merged["sdk_contract_constructor_shape_aligned"] = consistency.get(
        "constructor_shape_aligned"
    )
    merged["sdk_contract_direct_sender_exports_present"] = consistency.get(
        "direct_sender_exports_present"
    )
    return merged


def _build_manifest_summary(
    *,
    validation_report: Path,
    release_diagnostics_report: Path,
    smoke_report: Path,
    install_session_report: Path,
    framebus_roundtrip_report: Path,
    direct_push_demo_report: Path | None = None,
    direct_sender_object_demo_report: Path | None = None,
    status_binary_check_report: Path,
    list_devices_binary_check_report: Path,
) -> dict[str, object]:
    validation_payload = _load_json_object(validation_report) or {}
    validation_status = (
        dict(validation_payload.get("status", {}))
        if isinstance(validation_payload.get("status"), dict)
        else {}
    )
    validation_runtime_assets = (
        dict(validation_payload.get("runtime_assets", {}))
        if isinstance(validation_payload.get("runtime_assets"), dict)
        else {}
    )
    validation_runtime_resolved_assets = (
        dict(validation_runtime_assets.get("resolved_assets", {}))
        if isinstance(validation_runtime_assets.get("resolved_assets"), dict)
        else {}
    )
    validation_runtime_provenance = (
        dict(validation_runtime_assets.get("provenance", {}))
        if isinstance(validation_runtime_assets.get("provenance"), dict)
        else {}
    )
    validation_runtime_summary = (
        dict(validation_runtime_assets.get("summary", {}))
        if isinstance(validation_runtime_assets.get("summary"), dict)
        else {}
    )
    validation_summary = (
        dict(validation_payload.get("summary", {}))
        if isinstance(validation_payload.get("summary"), dict)
        else {}
    )
    validation_benchmark = (
        dict(validation_payload.get("benchmark", {}))
        if isinstance(validation_payload.get("benchmark"), dict)
        else {}
    )
    release_diagnostics_payload = _load_json_object(release_diagnostics_report) or {}
    release_summary = (
        dict(release_diagnostics_payload.get("summary", {}))
        if isinstance(release_diagnostics_payload.get("summary"), dict)
        else {}
    )
    smoke_payload = _load_json_object(smoke_report) or {}
    smoke_status = dict(smoke_payload.get("status", {})) if isinstance(smoke_payload.get("status"), dict) else {}
    smoke_install = dict(smoke_payload.get("install", {})) if isinstance(smoke_payload.get("install"), dict) else {}
    smoke_direct_push = _normalize_direct_push_step(smoke_payload.get("direct_push_demo"))
    smoke_direct_sender_object = _normalize_direct_push_step(
        smoke_payload.get("direct_sender_object_demo")
    )
    install_session_payload = _load_json_object(install_session_report) or {}
    install_session_install = (
        dict(install_session_payload.get("install", {}))
        if isinstance(install_session_payload.get("install"), dict)
        else {}
    )
    install_session_post_status = (
        dict(install_session_payload.get("post_status", {}))
        if isinstance(install_session_payload.get("post_status"), dict)
        else {}
    )
    install_session_direct_push = _normalize_direct_push_step(
        install_session_payload.get("direct_push_demo")
    )
    install_session_direct_sender_object = _normalize_direct_push_step(
        install_session_payload.get("direct_sender_object_demo")
    )
    install_session_sync_ipc = (
        dict(install_session_payload.get("sync_ipc", {}))
        if isinstance(install_session_payload.get("sync_ipc"), dict)
        else {}
    )
    validation_supported_formats = _normalize_supported_formats(
        validation_status.get("supported_formats")
    )
    validation_supported_frame_rates = _normalize_supported_frame_rates(
        validation_status.get("supported_frame_rates")
    )
    validation_devices = _normalize_string_list(validation_status.get("devices"))
    validation_all_devices = _normalize_string_list(validation_status.get("all_devices"))
    validation_device_prefix = _optional_string(validation_status.get("device_prefix"))
    validation_shared_memory_name = _optional_string(
        validation_status.get("shared_memory_name")
        if validation_status.get("shared_memory_name") is not None
        else validation_summary.get("status_shared_memory_name")
    )
    validation_mach_service_name = _optional_string(
        validation_status.get("mach_service_name")
        if validation_status.get("mach_service_name") is not None
        else validation_summary.get("status_mach_service_name")
    )
    validation_ipc_transport = _optional_string(
        validation_status.get("ipc_transport")
        if validation_status.get("ipc_transport") is not None
        else validation_summary.get("status_ipc_transport")
    )
    validation_install = (
        dict(validation_payload.get("install", {}))
        if isinstance(validation_payload.get("install"), dict)
        else {}
    )
    validation_install_supported_formats = _normalize_supported_formats(
        validation_install.get("supported_formats")
        if validation_install.get("supported_formats") is not None
        else validation_summary.get("install_supported_formats")
    )
    validation_install_supported_frame_rates = _normalize_supported_frame_rates(
        validation_install.get("supported_frame_rates")
        if validation_install.get("supported_frame_rates") is not None
        else validation_summary.get("install_supported_frame_rates")
    )
    validation_install_status_devices = _normalize_string_list(validation_install.get("status_devices"))
    validation_install_status_all_devices = _normalize_string_list(validation_install.get("status_all_devices"))
    validation_install_device_prefix = _optional_string(validation_install.get("device_prefix"))
    validation_install_shared_memory_name = _optional_string(
        validation_install.get("shared_memory_name")
        if validation_install.get("shared_memory_name") is not None
        else validation_summary.get("install_shared_memory_name")
    )
    validation_install_mach_service_name = _optional_string(
        validation_install.get("mach_service_name")
        if validation_install.get("mach_service_name") is not None
        else validation_summary.get("install_mach_service_name")
    )
    validation_install_ipc_transport = _optional_string(
        validation_install.get("ipc_transport")
        if validation_install.get("ipc_transport") is not None
        else validation_summary.get("install_ipc_transport")
    )
    validation_install_ipc_probe_present = (
        validation_install.get("ipc_probe_present")
        if validation_install.get("ipc_probe_present") is not None
        else validation_summary.get("install_ipc_probe_present")
    )
    validation_install_ipc_ready = (
        validation_install.get("ipc_ready")
        if validation_install.get("ipc_ready") is not None
        else validation_summary.get("install_ipc_ready")
    )
    validation_install_ipc_environment_blocked = (
        validation_install.get("ipc_environment_blocked")
        if validation_install.get("ipc_environment_blocked") is not None
        else validation_summary.get("install_ipc_environment_blocked")
    )
    validation_install_ipc_direct_open_errno = (
        validation_install.get("ipc_direct_open_errno")
        if validation_install.get("ipc_direct_open_errno") is not None
        else validation_summary.get("install_ipc_direct_open_errno")
    )
    validation_passed_app_ids = _normalize_string_list(
        validation_summary.get("passed_app_ids")
    )
    validation_reviewed_app_ids = _normalize_string_list(
        validation_summary.get("reviewed_app_ids")
    )
    validation_failed_app_ids = _normalize_string_list(
        validation_summary.get("failed_app_ids")
    )
    validation_pending_app_ids = _normalize_string_list(
        validation_summary.get("pending_app_ids")
    )
    validation_skipped_app_ids = _normalize_string_list(
        validation_summary.get("skipped_app_ids")
    )
    validation_unreviewed_app_ids = _normalize_string_list(
        validation_summary.get("unreviewed_app_ids")
    )
    validation_observed_target_app_ids = _normalize_string_list(
        validation_summary.get("observed_target_app_ids")
    )
    validation_missing_target_app_ids = _normalize_string_list(
        validation_summary.get("missing_target_app_ids")
    )
    validation_unexpected_target_app_ids = _normalize_string_list(
        validation_summary.get("unexpected_target_app_ids")
    )
    validation_target_app_ids_complete = validation_summary.get("target_app_ids_complete")
    validation_app_matrix = _normalize_validation_app_matrix(
        validation_payload.get("verification_targets")
    )
    validation_demo_present = validation_summary.get("demo_present")
    validation_demo_mode = validation_summary.get("demo_mode")
    validation_demo_mode_supported = validation_summary.get("demo_mode_supported")
    validation_demo_width = validation_summary.get("demo_width")
    validation_demo_height = validation_summary.get("demo_height")
    validation_demo_fps = validation_summary.get("demo_fps")
    validation_demo_duration = validation_summary.get("demo_duration")
    validation_demo_camera_name = validation_summary.get("demo_camera_name")
    validation_demo_consumer_count = validation_summary.get("demo_consumer_count")
    validation_demo_video_path = validation_summary.get("demo_video_path")
    validation_demo_frame_source_kind = validation_summary.get("demo_frame_source_kind")
    validation_demo_python_entrypoint_kind = validation_summary.get("demo_python_entrypoint_kind")
    validation_demo_sdk_streamer_factory_used = validation_summary.get("demo_sdk_streamer_factory_used")
    validation_demo_sdk_latest_provider_factory_used = validation_summary.get("demo_sdk_latest_provider_factory_used")
    validation_demo_sdk_direct_push_used = validation_summary.get("demo_sdk_direct_push_used")
    validation_benchmark_kind = validation_summary.get("benchmark_kind")
    if not isinstance(validation_benchmark_kind, str) or not validation_benchmark_kind:
        raw_validation_benchmark_kind = validation_benchmark.get("kind")
        validation_benchmark_kind = (
            raw_validation_benchmark_kind
            if isinstance(raw_validation_benchmark_kind, str) and raw_validation_benchmark_kind
            else ("single" if validation_benchmark else None)
        )
    validation_benchmark_matrix_profiles = _normalize_benchmark_matrix_profiles(
        validation_summary.get("benchmark_matrix_profiles")
    )
    if validation_benchmark_matrix_profiles is None:
        validation_benchmark_matrix_profiles = _normalize_benchmark_matrix_profiles(
            validation_benchmark.get("results")
        )
    validation_validated_apps = validation_summary.get("validated_apps")
    if not isinstance(validation_validated_apps, int):
        validation_validated_apps = _validation_app_matrix_reviewed_count(validation_app_matrix)
    validation_passed_apps = validation_summary.get("passed_apps")
    if not isinstance(validation_passed_apps, int):
        derived = _validation_app_matrix_ids_with_result(validation_app_matrix, "pass")
        validation_passed_apps = len(derived) if derived is not None else None
    validation_failed_apps = validation_summary.get("failed_apps")
    if not isinstance(validation_failed_apps, int):
        derived = _validation_app_matrix_ids_with_result(validation_app_matrix, "fail")
        validation_failed_apps = len(derived) if derived is not None else None
    validation_pending_apps = validation_summary.get("pending_apps")
    if not isinstance(validation_pending_apps, int):
        derived = _validation_app_matrix_ids_with_result(validation_app_matrix, "pending")
        validation_pending_apps = len(derived) if derived is not None else None
    validation_skipped_apps = validation_summary.get("skipped_apps")
    if not isinstance(validation_skipped_apps, int):
        derived = _validation_app_matrix_ids_with_result(validation_app_matrix, "skipped")
        validation_skipped_apps = len(derived) if derived is not None else None
    if validation_passed_app_ids is None:
        validation_passed_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "pass")
    if validation_failed_app_ids is None:
        validation_failed_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "fail")
    if validation_pending_app_ids is None:
        validation_pending_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "pending")
    if validation_skipped_app_ids is None:
        validation_skipped_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "skipped")
    if validation_unreviewed_app_ids is None:
        validation_unreviewed_app_ids = _validation_app_matrix_unreviewed_ids(validation_app_matrix)
    if validation_reviewed_app_ids is None and isinstance(validation_app_matrix, dict):
        validation_reviewed_app_ids = sorted(
            app_id
            for app_id, item in validation_app_matrix.items()
            if isinstance(item, dict) and bool(item.get("reviewed"))
        )
    if validation_observed_target_app_ids is None and isinstance(validation_app_matrix, dict):
        validation_observed_target_app_ids = sorted(validation_app_matrix.keys())
    expected_target_ids = {"facetime", "google_meet", "obs", "quicktime", "teams", "zoom"}
    if validation_missing_target_app_ids is None and validation_observed_target_app_ids is not None:
        validation_missing_target_app_ids = sorted(
            expected_target_ids - set(validation_observed_target_app_ids)
        )
    if validation_unexpected_target_app_ids is None and validation_observed_target_app_ids is not None:
        validation_unexpected_target_app_ids = sorted(
            set(validation_observed_target_app_ids) - expected_target_ids
        )
    if validation_target_app_ids_complete is None and (
        validation_missing_target_app_ids is not None or validation_unexpected_target_app_ids is not None
    ):
        validation_target_app_ids_complete = not (
            validation_missing_target_app_ids or validation_unexpected_target_app_ids
        )
    smoke_supported_formats = _normalize_supported_formats(smoke_status.get("supported_formats"))
    smoke_supported_frame_rates = _normalize_supported_frame_rates(
        smoke_status.get("supported_frame_rates")
    )
    smoke_devices = _normalize_string_list(smoke_status.get("devices"))
    smoke_all_devices = _normalize_string_list(smoke_status.get("all_devices"))
    smoke_device_prefix = _optional_string(smoke_status.get("device_prefix"))
    smoke_shared_memory_name = _optional_string(smoke_status.get("shared_memory_name"))
    smoke_mach_service_name = _optional_string(smoke_status.get("mach_service_name"))
    smoke_ipc_transport = _optional_string(smoke_status.get("ipc_transport"))
    install_session_supported_formats = _normalize_supported_formats(
        install_session_post_status.get("supported_formats")
    )
    install_session_supported_frame_rates = _normalize_supported_frame_rates(
        install_session_post_status.get("supported_frame_rates")
    )
    install_session_devices = _normalize_string_list(install_session_post_status.get("devices"))
    install_session_all_devices = _normalize_string_list(install_session_post_status.get("all_devices"))
    install_session_device_prefix = _optional_string(install_session_post_status.get("device_prefix"))
    install_session_shared_memory_name = _optional_string(
        install_session_post_status.get("shared_memory_name")
    )
    install_session_mach_service_name = _optional_string(
        install_session_post_status.get("mach_service_name")
    )
    install_session_ipc_transport = _optional_string(
        install_session_post_status.get("ipc_transport")
    )
    framebus_payload = _load_json_object(framebus_roundtrip_report) or {}
    framebus_producer_kind = _optional_string(framebus_payload.get("producer_kind"))
    direct_push_demo_payload = (
        _load_json_object(direct_push_demo_report) if direct_push_demo_report is not None else None
    ) or {}
    direct_push_demo = _normalize_direct_push_step({"payload": direct_push_demo_payload})
    direct_sender_object_demo_payload = (
        _load_json_object(direct_sender_object_demo_report)
        if direct_sender_object_demo_report is not None
        else None
    ) or {}
    direct_sender_object_demo = _normalize_direct_push_step(
        {"payload": direct_sender_object_demo_payload}
        if direct_sender_object_demo_payload
        else {}
    )
    framebus_observed = (
        dict(framebus_payload.get("observed", {}))
        if isinstance(framebus_payload.get("observed"), dict)
        else {}
    )
    framebus_consistency = (
        dict(framebus_payload.get("consistency", {}))
        if isinstance(framebus_payload.get("consistency"), dict)
        else {}
    )
    status_binary_payload = _load_json_object(status_binary_check_report) or {}
    status_binary_consistency = (
        dict(status_binary_payload.get("consistency", {}))
        if isinstance(status_binary_payload.get("consistency"), dict)
        else {}
    )
    status_binary_result = (
        dict(status_binary_payload.get("payload", {}))
        if isinstance(status_binary_payload.get("payload"), dict)
        else {}
    )
    list_devices_binary_payload = _load_json_object(list_devices_binary_check_report) or {}
    list_devices_binary_consistency = (
        dict(list_devices_binary_payload.get("consistency", {}))
        if isinstance(list_devices_binary_payload.get("consistency"), dict)
        else {}
    )
    list_devices_binary_result = (
        dict(list_devices_binary_payload.get("payload", {}))
        if isinstance(list_devices_binary_payload.get("payload"), dict)
        else {}
    )
    override_prefix_case = _probe_case_by_name(
        list_devices_binary_payload.get("probe_cases"),
        "override_prefix_no_match",
    ) or {}
    override_prefix_case_consistency = (
        dict(override_prefix_case.get("consistency", {}))
        if isinstance(override_prefix_case.get("consistency"), dict)
        else {}
    )
    direct_open_errno = framebus_observed.get("direct_open_errno")
    if direct_open_errno is not None:
        try:
            direct_open_errno = int(direct_open_errno)
        except (TypeError, ValueError):
            direct_open_errno = None
    framebus_environment_blocked = bool(
        framebus_payload.get("environment_blocked")
        or framebus_consistency.get("environment_blocked")
        or direct_open_errno in {1, 13}
    )
    effective_start_ready = None
    effective_start_blocker_code = None
    for ready_value, blocker_code in (
        (
            smoke_status.get("start_ready"),
            smoke_status.get("start_blocker_code"),
        ),
        (
            install_session_post_status.get("start_ready"),
            install_session_post_status.get("start_blocker_code"),
        ),
        (
            validation_summary.get("install_start_ready"),
            validation_summary.get("install_start_blocker_code"),
        ),
        (
            validation_summary.get("status_start_ready"),
            validation_summary.get("status_start_blocker_code"),
        ),
    ):
        if ready_value is None and not blocker_code:
            continue
        effective_start_ready = ready_value
        effective_start_blocker_code = blocker_code
        break
    if effective_start_blocker_code is None:
        if status_binary_result.get("ipc_environment_blocked") is True or direct_open_errno in {1, 13}:
            effective_start_blocker_code = "ipc_environment_blocked"
            effective_start_ready = False
        elif framebus_consistency.get("all_checks_passed") is True:
            effective_start_blocker_code = "ready"
            effective_start_ready = True
    effective_supported_formats = _pick_first_present(
        install_session_supported_formats,
        smoke_supported_formats,
        validation_install_supported_formats,
        validation_supported_formats,
    )
    effective_supported_frame_rates = _pick_first_present(
        install_session_supported_frame_rates,
        smoke_supported_frame_rates,
        validation_install_supported_frame_rates,
        validation_supported_frame_rates,
    )
    effective_devices = _pick_first_present(
        install_session_devices,
        smoke_devices,
        validation_install_status_devices,
        validation_devices,
    )
    effective_all_devices = _pick_first_present(
        install_session_all_devices,
        smoke_all_devices,
        validation_install_status_all_devices,
        validation_all_devices,
    )
    effective_device_prefix = _optional_string(
        _pick_first_non_none(
            install_session_device_prefix,
            smoke_device_prefix,
            validation_install_device_prefix,
            validation_device_prefix,
        )
    )
    effective_shared_memory_name = _optional_string(
        _pick_first_non_none(
            install_session_shared_memory_name,
            smoke_shared_memory_name,
            validation_install_shared_memory_name,
            validation_shared_memory_name,
        )
    )
    effective_mach_service_name = _optional_string(
        _pick_first_non_none(
            install_session_mach_service_name,
            smoke_mach_service_name,
            validation_install_mach_service_name,
            validation_mach_service_name,
        )
    )
    effective_ipc_transport = _optional_string(
        _pick_first_non_none(
            install_session_ipc_transport,
            smoke_ipc_transport,
            validation_install_ipc_transport,
            validation_ipc_transport,
        )
    )
    runtime_topology_source = {}
    for candidate in (
        direct_push_demo,
        smoke_direct_push,
        install_session_direct_push,
    ):
        if _has_runtime_topology_fields(candidate):
            runtime_topology_source = candidate
            break
    runtime_data_plane = _optional_string(
        _pick_first_non_none(
            runtime_topology_source.get("runtime_data_plane"),
            validation_summary.get("runtime_data_plane"),
            install_session_sync_ipc.get("ipc_transport"),
            effective_ipc_transport,
            "shared_memory_ringbuffer",
        )
    )
    if runtime_data_plane is None:
        runtime_data_plane = "shared_memory_ringbuffer"
    runtime_topology_kind = _optional_string(
        _pick_first_non_none(
            runtime_topology_source.get("runtime_topology_kind"),
            validation_summary.get("runtime_topology_kind"),
            "camera_extension_direct_framebus",
        )
    )
    runtime_control_plane = _optional_string(
        _pick_first_non_none(
            runtime_topology_source.get("runtime_control_plane"),
            validation_summary.get("runtime_control_plane"),
            "host_activation_plus_sync_ipc",
        )
    )
    explicit_runtime_frame_path = _optional_string(
        _pick_first_non_none(
            runtime_topology_source.get("runtime_frame_path"),
            validation_summary.get("runtime_frame_path"),
        )
    )
    runtime_frame_path = _optional_string(
        _pick_first_non_none(
            explicit_runtime_frame_path,
            (
                "python_sdk -> shared_memory_ringbuffer -> camera_extension -> "
                "system_camera_device -> client_app"
            ),
        )
    )

    return {
        "validation_report_present": bool(validation_payload),
        "validation_report_summary": validation_summary or None,
        "validation_status_start_ready": validation_summary.get("status_start_ready"),
        "validation_status_start_blocker_code": validation_summary.get("status_start_blocker_code"),
        "validation_shared_memory_name": validation_shared_memory_name,
        "validation_mach_service_name": validation_mach_service_name,
        "validation_ipc_transport": validation_ipc_transport,
        "validation_demo_present": validation_demo_present,
        "validation_demo_mode": validation_demo_mode,
        "validation_demo_mode_supported": validation_demo_mode_supported,
        "validation_demo_width": validation_demo_width,
        "validation_demo_height": validation_demo_height,
        "validation_demo_fps": validation_demo_fps,
        "validation_demo_duration": validation_demo_duration,
        "validation_demo_camera_name": validation_demo_camera_name,
        "validation_demo_consumer_count": validation_demo_consumer_count,
        "validation_demo_video_path": validation_demo_video_path,
        "validation_demo_frame_source_kind": validation_demo_frame_source_kind,
        "validation_demo_python_entrypoint_kind": validation_demo_python_entrypoint_kind,
        "validation_demo_sdk_streamer_factory_used": validation_demo_sdk_streamer_factory_used,
        "validation_demo_sdk_latest_provider_factory_used": validation_demo_sdk_latest_provider_factory_used,
        "validation_demo_sdk_direct_push_used": validation_demo_sdk_direct_push_used,
        "validation_benchmark_kind": validation_benchmark_kind,
        "validation_benchmark_matrix_profiles": validation_benchmark_matrix_profiles,
        "validation_supported_formats": validation_supported_formats,
        "validation_supported_frame_rates": validation_supported_frame_rates,
        "validation_devices": validation_devices,
        "validation_all_devices": validation_all_devices,
        "validation_device_prefix": validation_device_prefix,
        "validation_validated_apps": validation_validated_apps,
        "validation_passed_apps": validation_passed_apps,
        "validation_failed_apps": validation_failed_apps,
        "validation_pending_apps": validation_pending_apps,
        "validation_skipped_apps": validation_skipped_apps,
        "validation_install_present": validation_summary.get("install_present"),
        "validation_install_success": validation_summary.get("install_success"),
        "validation_install_phase": validation_summary.get("install_phase"),
        "validation_install_start_ready": validation_summary.get("install_start_ready"),
        "validation_install_start_blocker_code": validation_summary.get("install_start_blocker_code"),
        "validation_install_shared_memory_name": validation_install_shared_memory_name,
        "validation_install_supported_formats": validation_install_supported_formats,
        "validation_install_supported_frame_rates": validation_install_supported_frame_rates,
        "validation_install_status_devices": validation_install_status_devices,
        "validation_install_status_all_devices": validation_install_status_all_devices,
        "validation_install_device_prefix": validation_install_device_prefix,
        "validation_install_mach_service_name": validation_install_mach_service_name,
        "validation_install_ipc_transport": validation_install_ipc_transport,
        "validation_install_ipc_probe_present": validation_install_ipc_probe_present,
        "validation_install_ipc_ready": validation_install_ipc_ready,
        "validation_install_ipc_environment_blocked": validation_install_ipc_environment_blocked,
        "validation_install_ipc_direct_open_errno": validation_install_ipc_direct_open_errno,
        "runtime_status_tool_path": _optional_string(validation_runtime_resolved_assets.get("status_tool")),
        "runtime_install_tool_path": _optional_string(validation_runtime_resolved_assets.get("install_tool")),
        "runtime_devices_tool_path": _optional_string(validation_runtime_resolved_assets.get("devices_tool")),
        "runtime_uninstall_tool_path": _optional_string(validation_runtime_resolved_assets.get("uninstall_tool")),
        "runtime_sync_ipc_tool_path": _optional_string(validation_runtime_resolved_assets.get("sync_ipc_tool")),
        "runtime_pkg_path": _optional_string(validation_runtime_resolved_assets.get("pkg")),
        "runtime_host_bundle_path": _optional_string(validation_runtime_provenance.get("host_bundle")),
        "runtime_host_executable_path": _optional_string(validation_runtime_provenance.get("host_executable")),
        "runtime_extension_bundle_path": _optional_string(validation_runtime_provenance.get("extension_bundle")),
        "runtime_package_install_command": (
            [str(item) for item in validation_runtime_provenance.get("package_install_command", []) if item is not None]
            if isinstance(validation_runtime_provenance.get("package_install_command"), list)
            else None
        ),
        "runtime_auto_install_package": validation_runtime_provenance.get("auto_install_package"),
        "runtime_host_bundle_configured": validation_runtime_summary.get("host_bundle_configured"),
        "runtime_host_executable_configured": validation_runtime_summary.get("host_executable_configured"),
        "runtime_extension_bundle_derived": validation_runtime_summary.get("extension_bundle_derived"),
        "runtime_package_install_command_present": validation_runtime_summary.get("package_install_command_present"),
        "runtime_topology_kind": runtime_topology_kind,
        "runtime_frame_path": runtime_frame_path,
        "runtime_host_role": _optional_string(
            _pick_first_non_none(
                runtime_topology_source.get("runtime_host_role"),
                validation_summary.get("runtime_host_role"),
                "container_activation_command_bridge",
            )
        ),
        "runtime_host_in_frame_hot_path": _pick_first_non_none(
            runtime_topology_source.get("runtime_host_in_frame_hot_path"),
            validation_summary.get("runtime_host_in_frame_hot_path"),
            False,
        ),
        "runtime_dedicated_host_daemon_required": _pick_first_non_none(
            runtime_topology_source.get("runtime_dedicated_host_daemon_required"),
            validation_summary.get("runtime_dedicated_host_daemon_required"),
            False,
        ),
        "runtime_container_app_configured": _pick_first_non_none(
            runtime_topology_source.get("runtime_container_app_configured"),
            validation_summary.get("runtime_container_app_configured"),
            validation_runtime_summary.get("host_bundle_configured"),
            _optional_string(validation_runtime_provenance.get("host_bundle")) is not None,
        ),
        "runtime_data_plane": runtime_data_plane,
        "runtime_control_plane": runtime_control_plane,
        "release_app_bundle_path": _optional_string(validation_summary.get("release_app_bundle_path")),
        "release_extension_bundle_path": _optional_string(validation_summary.get("release_extension_bundle_path")),
        "release_sync_ipc_tool_path": _optional_string(validation_summary.get("release_sync_ipc_tool_path")),
        "release_pkg_path": _optional_string(validation_summary.get("release_pkg_path")),
        "runtime_release_host_bundle_identity_consistent": validation_summary.get(
            "runtime_release_host_bundle_identity_consistent"
        ),
        "runtime_release_extension_bundle_identity_consistent": validation_summary.get(
            "runtime_release_extension_bundle_identity_consistent"
        ),
        "runtime_release_sync_ipc_tool_identity_consistent": validation_summary.get(
            "runtime_release_sync_ipc_tool_identity_consistent"
        ),
        "runtime_release_pkg_identity_consistent": validation_summary.get(
            "runtime_release_pkg_identity_consistent"
        ),
        "runtime_release_host_bundle_path_equal": validation_summary.get(
            "runtime_release_host_bundle_path_equal"
        ),
        "runtime_release_extension_bundle_path_equal": validation_summary.get(
            "runtime_release_extension_bundle_path_equal"
        ),
        "runtime_release_sync_ipc_tool_path_equal": validation_summary.get(
            "runtime_release_sync_ipc_tool_path_equal"
        ),
        "runtime_release_pkg_path_equal": validation_summary.get(
            "runtime_release_pkg_path_equal"
        ),
        "runtime_release_product_identity_consistent": validation_summary.get(
            "runtime_release_product_identity_consistent"
        ),
        "runtime_release_product_path_equal": validation_summary.get(
            "runtime_release_product_path_equal"
        ),
        "release_command_tools_exist": _pick_first_non_none(
            validation_summary.get("release_command_tools_exist"),
            release_summary.get("command_tools_exist"),
        ),
        "release_command_tools_signed": _pick_first_non_none(
            validation_summary.get("release_command_tools_signed"),
            release_summary.get("command_tools_signed"),
        ),
        "release_command_tools_universal2_ready": _pick_first_non_none(
            validation_summary.get("release_command_tools_universal2_ready"),
            release_summary.get("command_tools_universal2_ready"),
        ),
        "release_app_signed": _pick_first_non_none(
            validation_summary.get("release_app_signed"),
            release_summary.get("app_signed"),
        ),
        "release_app_gatekeeper_accepted": _pick_first_non_none(
            validation_summary.get("release_app_gatekeeper_accepted"),
            release_summary.get("app_gatekeeper_accepted"),
        ),
        "release_app_stapled": _pick_first_non_none(
            validation_summary.get("release_app_stapled"),
            release_summary.get("app_stapled"),
        ),
        "release_extension_signed": _pick_first_non_none(
            validation_summary.get("release_extension_signed"),
            release_summary.get("extension_signed"),
        ),
        "release_pkg_signed": _pick_first_non_none(
            validation_summary.get("release_pkg_signed"),
            release_summary.get("pkg_signed"),
        ),
        "release_pkg_gatekeeper_accepted": _pick_first_non_none(
            validation_summary.get("release_pkg_gatekeeper_accepted"),
            release_summary.get("pkg_gatekeeper_accepted"),
        ),
        "release_pkg_stapled": _pick_first_non_none(
            validation_summary.get("release_pkg_stapled"),
            release_summary.get("pkg_stapled"),
        ),
        "release_pkg_payload_appledouble_clean": _pick_first_non_none(
            validation_summary.get("release_pkg_payload_appledouble_clean"),
            release_summary.get("pkg_payload_appledouble_clean"),
        ),
        "release_sync_ipc_tool_exists": _pick_first_non_none(
            validation_summary.get("release_sync_ipc_tool_exists"),
            release_summary.get("sync_ipc_tool_exists"),
        ),
        "release_sync_ipc_tool_signed": _pick_first_non_none(
            validation_summary.get("release_sync_ipc_tool_signed"),
            release_summary.get("sync_ipc_tool_signed"),
        ),
        "release_sync_ipc_tool_universal2_ready": _pick_first_non_none(
            validation_summary.get("release_sync_ipc_tool_universal2_ready"),
            release_summary.get("sync_ipc_tool_universal2_ready"),
        ),
        "validation_passed_app_ids": validation_passed_app_ids,
        "validation_reviewed_app_ids": validation_reviewed_app_ids,
        "validation_failed_app_ids": validation_failed_app_ids,
        "validation_pending_app_ids": validation_pending_app_ids,
        "validation_skipped_app_ids": validation_skipped_app_ids,
        "validation_unreviewed_app_ids": validation_unreviewed_app_ids,
        "validation_observed_target_app_ids": validation_observed_target_app_ids,
        "validation_missing_target_app_ids": validation_missing_target_app_ids,
        "validation_unexpected_target_app_ids": validation_unexpected_target_app_ids,
        "validation_target_app_ids_complete": validation_target_app_ids_complete,
        "validation_manual_validation_ready": validation_summary.get("manual_validation_ready"),
        "validation_manual_validation_complete": validation_summary.get("manual_validation_complete"),
        "validation_manual_validation_all_passed": validation_summary.get("manual_validation_all_passed"),
        "validation_app_matrix": validation_app_matrix,
        "smoke_present": bool(smoke_payload),
        "smoke_install_success": smoke_install.get("success"),
        "smoke_ipc_environment_blocked": smoke_status.get("ipc_environment_blocked"),
        "smoke_ipc_direct_open_errno": smoke_status.get("ipc_direct_open_errno"),
        "smoke_start_ready": smoke_status.get("start_ready"),
        "smoke_start_blocker_code": smoke_status.get("start_blocker_code"),
        "smoke_devices": smoke_devices,
        "smoke_all_devices": smoke_all_devices,
        "smoke_device_prefix": smoke_device_prefix,
        "smoke_shared_memory_name": smoke_shared_memory_name,
        "smoke_supported_formats": smoke_supported_formats,
        "smoke_supported_frame_rates": smoke_supported_frame_rates,
        "smoke_mach_service_name": smoke_mach_service_name,
        "smoke_ipc_transport": smoke_ipc_transport,
        **_prefixed_direct_step_summary_fields(
            "smoke_direct_push_demo",
            smoke_direct_push,
        ),
        "smoke_direct_push_demo_present": smoke_direct_push.get("present"),
        "smoke_direct_push_demo_attempted": smoke_direct_push.get("attempted"),
        "smoke_direct_push_demo_skipped": smoke_direct_push.get("skipped"),
        "smoke_direct_push_demo_skip_reason": smoke_direct_push.get("skip_reason"),
        "smoke_direct_push_demo_returncode": smoke_direct_push.get("returncode"),
        "smoke_direct_push_demo_mode": smoke_direct_push.get("mode"),
        "smoke_direct_push_demo_frame_source_kind": smoke_direct_push.get("frame_source_kind"),
        "smoke_direct_push_demo_python_entrypoint_kind": smoke_direct_push.get(
            "python_entrypoint_kind"
        ),
        "smoke_direct_push_demo_sdk_direct_push_used": smoke_direct_push.get(
            "sdk_direct_push_used"
        ),
        "smoke_direct_push_demo_backend_name": smoke_direct_push.get("backend_name"),
        "smoke_direct_push_demo_using_direct_sender": smoke_direct_push.get("using_direct_sender"),
        "smoke_direct_push_demo_direct_sender_attempted": smoke_direct_push.get("direct_sender_attempted"),
        "smoke_direct_push_demo_direct_sender_state": smoke_direct_push.get("direct_sender_state"),
        "smoke_direct_push_demo_runtime_topology_kind": smoke_direct_push.get(
            "runtime_topology_kind"
        ),
        "smoke_direct_push_demo_runtime_frame_path": smoke_direct_push.get(
            "runtime_frame_path"
        ),
        "smoke_direct_push_demo_runtime_host_role": smoke_direct_push.get(
            "runtime_host_role"
        ),
        "smoke_direct_push_demo_runtime_host_in_frame_hot_path": smoke_direct_push.get(
            "runtime_host_in_frame_hot_path"
        ),
        "smoke_direct_push_demo_helper_hot_path_used": smoke_direct_push.get(
            "helper_hot_path_used"
        ),
        "smoke_direct_push_demo_shared_memory_fallback_used": smoke_direct_push.get(
            "shared_memory_fallback_used"
        ),
        "smoke_direct_push_demo_runtime_dedicated_host_daemon_required": smoke_direct_push.get(
            "runtime_dedicated_host_daemon_required"
        ),
        "smoke_direct_push_demo_runtime_container_app_configured": smoke_direct_push.get(
            "runtime_container_app_configured"
        ),
        "smoke_direct_push_demo_runtime_data_plane": smoke_direct_push.get(
            "runtime_data_plane"
        ),
        "smoke_direct_push_demo_runtime_control_plane": smoke_direct_push.get(
            "runtime_control_plane"
        ),
        "smoke_direct_push_demo_direct_sender_target_name": smoke_direct_push.get(
            "direct_sender_target_name"
        ),
        "smoke_direct_push_demo_direct_sender_library_path": smoke_direct_push.get("direct_sender_library_path"),
        "smoke_direct_push_demo_direct_sender_last_error": smoke_direct_push.get("direct_sender_last_error"),
        "smoke_direct_push_demo_camera_name": smoke_direct_push.get("camera_name"),
        "smoke_direct_push_demo_consumer_count": smoke_direct_push.get("consumer_count"),
        "smoke_direct_push_demo_requested_frames": smoke_direct_push.get("requested_frames"),
        "smoke_direct_push_demo_frames_sent": smoke_direct_push.get("frames_sent"),
        "smoke_direct_push_demo_direct_only": smoke_direct_push.get("direct_only"),
        "smoke_direct_push_demo_probe_only": smoke_direct_push.get("probe_only"),
        "smoke_direct_push_demo_requested_camera_access": smoke_direct_push.get(
            "requested_camera_access"
        ),
        "smoke_direct_push_demo_error": smoke_direct_push.get("error"),
        "smoke_direct_push_demo_probe_payload_present": smoke_direct_push.get("probe_payload_present"),
        "smoke_direct_push_demo_direct_sender_device_snapshot_present": smoke_direct_push.get(
            "direct_sender_device_snapshot_present"
        ),
        "smoke_direct_push_demo_requested_camera_access_snapshot_present": smoke_direct_push.get(
            "requested_camera_access_snapshot_present"
        ),
        "smoke_direct_push_demo_camera_access_status": smoke_direct_push.get("camera_access_status"),
        "smoke_direct_push_demo_camera_access_authorized": smoke_direct_push.get(
            "camera_access_authorized"
        ),
        "smoke_direct_push_demo_camera_access_denied": smoke_direct_push.get("camera_access_denied"),
        "smoke_direct_push_demo_camera_access_restricted": smoke_direct_push.get(
            "camera_access_restricted"
        ),
        "smoke_direct_push_demo_camera_access_not_determined": smoke_direct_push.get(
            "camera_access_not_determined"
        ),
        "smoke_direct_push_demo_environment_device_enumeration_empty": smoke_direct_push.get(
            "environment_device_enumeration_empty"
        ),
        "smoke_direct_push_demo_visible_all_devices": smoke_direct_push.get(
            "direct_sender_visible_all_devices"
        ),
        "smoke_direct_push_demo_visible_avfoundation_devices": smoke_direct_push.get(
            "direct_sender_visible_avfoundation_devices"
        ),
        "smoke_direct_push_demo_visible_cmio_devices": smoke_direct_push.get(
            "direct_sender_visible_cmio_devices"
        ),
        "smoke_direct_push_demo_requested_camera_access_status": smoke_direct_push.get(
            "requested_camera_access_status"
        ),
        "smoke_direct_push_demo_requested_camera_access_authorized": smoke_direct_push.get(
            "requested_camera_access_authorized"
        ),
        "smoke_direct_push_demo_requested_camera_access_denied": smoke_direct_push.get(
            "requested_camera_access_denied"
        ),
        "smoke_direct_push_demo_requested_camera_access_restricted": smoke_direct_push.get(
            "requested_camera_access_restricted"
        ),
        "smoke_direct_push_demo_requested_camera_access_not_determined": smoke_direct_push.get(
            "requested_camera_access_not_determined"
        ),
        "smoke_direct_push_demo_requested_camera_access_environment_device_enumeration_empty": smoke_direct_push.get(
            "requested_camera_access_environment_device_enumeration_empty"
        ),
        "smoke_direct_push_demo_requested_camera_access_visible_all_devices": smoke_direct_push.get(
            "requested_camera_access_visible_all_devices"
        ),
        "smoke_direct_push_demo_requested_camera_access_visible_avfoundation_devices": smoke_direct_push.get(
            "requested_camera_access_visible_avfoundation_devices"
        ),
        "smoke_direct_push_demo_requested_camera_access_visible_cmio_devices": smoke_direct_push.get(
            "requested_camera_access_visible_cmio_devices"
        ),
        **_prefixed_direct_step_summary_fields(
            "smoke_direct_sender_object_demo",
            smoke_direct_sender_object,
        ),
        "install_session_present": bool(install_session_payload),
        "install_session_success": install_session_install.get("success"),
        "install_session_ipc_probe_present": install_session_post_status.get("ipc_probe_present"),
        "install_session_ipc_ready": install_session_post_status.get("ipc_ready"),
        "install_session_ipc_environment_blocked": install_session_post_status.get("ipc_environment_blocked"),
        "install_session_ipc_direct_open_errno": install_session_post_status.get("ipc_direct_open_errno"),
        "install_session_start_ready": install_session_post_status.get("start_ready"),
        "install_session_start_blocker_code": install_session_post_status.get("start_blocker_code"),
        "install_session_host_signature": _optional_string(install_session_post_status.get("host_signature")),
        "install_session_host_team_identifier": _optional_string(install_session_post_status.get("host_team_identifier")),
        "install_session_host_codesign_summary": _optional_string(install_session_post_status.get("host_codesign_summary")),
        "install_session_host_gatekeeper_allowed": install_session_post_status.get("host_gatekeeper_allowed"),
        "install_session_host_gatekeeper_summary": _optional_string(install_session_post_status.get("host_gatekeeper_summary")),
        "install_session_host_distribution_summary": _optional_string(install_session_post_status.get("host_distribution_summary")),
        "install_session_host_notarization_missing": install_session_post_status.get("host_notarization_missing"),
        "install_session_install_command_notarization_missing": install_session_post_status.get(
            "install_command_notarization_missing"
        ),
        "install_session_system_extension_registered": install_session_post_status.get(
            "system_extension_registered"
        ),
        "install_session_devices": install_session_devices,
        "install_session_all_devices": install_session_all_devices,
        "install_session_device_prefix": install_session_device_prefix,
        "install_session_shared_memory_name": install_session_shared_memory_name,
        "install_session_supported_formats": install_session_supported_formats,
        "install_session_supported_frame_rates": install_session_supported_frame_rates,
        "install_session_mach_service_name": install_session_mach_service_name,
        "install_session_ipc_transport": install_session_ipc_transport,
        "install_session_sync_ipc_present": bool(install_session_sync_ipc),
        "install_session_sync_ipc_supported": install_session_sync_ipc.get("supported"),
        "install_session_sync_ipc_success": install_session_sync_ipc.get("success"),
        "install_session_sync_ipc_phase": _optional_string(install_session_sync_ipc.get("phase")),
        "install_session_sync_ipc_shared_memory_name": _optional_string(
            install_session_sync_ipc.get("shared_memory_name")
        ),
        "install_session_sync_ipc_transport": _optional_string(
            install_session_sync_ipc.get("ipc_transport")
        ),
        "install_session_sync_ipc_returncode": install_session_sync_ipc.get("returncode"),
        **_prefixed_direct_step_summary_fields(
            "install_session_direct_push_demo",
            install_session_direct_push,
        ),
        "install_session_direct_push_demo_present": install_session_direct_push.get("present"),
        "install_session_direct_push_demo_attempted": install_session_direct_push.get("attempted"),
        "install_session_direct_push_demo_skipped": install_session_direct_push.get("skipped"),
        "install_session_direct_push_demo_skip_reason": install_session_direct_push.get(
            "skip_reason"
        ),
        "install_session_direct_push_demo_returncode": install_session_direct_push.get("returncode"),
        "install_session_direct_push_demo_mode": install_session_direct_push.get("mode"),
        "install_session_direct_push_demo_frame_source_kind": install_session_direct_push.get(
            "frame_source_kind"
        ),
        "install_session_direct_push_demo_python_entrypoint_kind": install_session_direct_push.get(
            "python_entrypoint_kind"
        ),
        "install_session_direct_push_demo_sdk_direct_push_used": install_session_direct_push.get(
            "sdk_direct_push_used"
        ),
        "install_session_direct_push_demo_backend_name": install_session_direct_push.get(
            "backend_name"
        ),
        "install_session_direct_push_demo_using_direct_sender": install_session_direct_push.get(
            "using_direct_sender"
        ),
        "install_session_direct_push_demo_direct_sender_attempted": install_session_direct_push.get(
            "direct_sender_attempted"
        ),
        "install_session_direct_push_demo_direct_sender_state": install_session_direct_push.get(
            "direct_sender_state"
        ),
        "install_session_direct_push_demo_runtime_topology_kind": install_session_direct_push.get(
            "runtime_topology_kind"
        ),
        "install_session_direct_push_demo_runtime_frame_path": install_session_direct_push.get(
            "runtime_frame_path"
        ),
        "install_session_direct_push_demo_runtime_host_role": install_session_direct_push.get(
            "runtime_host_role"
        ),
        "install_session_direct_push_demo_runtime_host_in_frame_hot_path": install_session_direct_push.get(
            "runtime_host_in_frame_hot_path"
        ),
        "install_session_direct_push_demo_helper_hot_path_used": install_session_direct_push.get(
            "helper_hot_path_used"
        ),
        "install_session_direct_push_demo_shared_memory_fallback_used": install_session_direct_push.get(
            "shared_memory_fallback_used"
        ),
        "install_session_direct_push_demo_runtime_dedicated_host_daemon_required": install_session_direct_push.get(
            "runtime_dedicated_host_daemon_required"
        ),
        "install_session_direct_push_demo_runtime_container_app_configured": install_session_direct_push.get(
            "runtime_container_app_configured"
        ),
        "install_session_direct_push_demo_runtime_data_plane": install_session_direct_push.get(
            "runtime_data_plane"
        ),
        "install_session_direct_push_demo_runtime_control_plane": install_session_direct_push.get(
            "runtime_control_plane"
        ),
        "install_session_direct_push_demo_direct_sender_target_name": install_session_direct_push.get(
            "direct_sender_target_name"
        ),
        "install_session_direct_push_demo_direct_sender_library_path": install_session_direct_push.get(
            "direct_sender_library_path"
        ),
        "install_session_direct_push_demo_direct_sender_last_error": install_session_direct_push.get(
            "direct_sender_last_error"
        ),
        "install_session_direct_push_demo_camera_name": install_session_direct_push.get(
            "camera_name"
        ),
        "install_session_direct_push_demo_consumer_count": install_session_direct_push.get(
            "consumer_count"
        ),
        "install_session_direct_push_demo_requested_frames": install_session_direct_push.get(
            "requested_frames"
        ),
        "install_session_direct_push_demo_frames_sent": install_session_direct_push.get(
            "frames_sent"
        ),
        "install_session_direct_push_demo_direct_only": install_session_direct_push.get("direct_only"),
        "install_session_direct_push_demo_probe_only": install_session_direct_push.get("probe_only"),
        "install_session_direct_push_demo_requested_camera_access": install_session_direct_push.get(
            "requested_camera_access"
        ),
        "install_session_direct_push_demo_error": install_session_direct_push.get("error"),
        "install_session_direct_push_demo_probe_payload_present": install_session_direct_push.get(
            "probe_payload_present"
        ),
        "install_session_direct_push_demo_direct_sender_device_snapshot_present": install_session_direct_push.get(
            "direct_sender_device_snapshot_present"
        ),
        "install_session_direct_push_demo_requested_camera_access_snapshot_present": install_session_direct_push.get(
            "requested_camera_access_snapshot_present"
        ),
        "install_session_direct_push_demo_camera_access_status": install_session_direct_push.get(
            "camera_access_status"
        ),
        "install_session_direct_push_demo_camera_access_authorized": install_session_direct_push.get(
            "camera_access_authorized"
        ),
        "install_session_direct_push_demo_camera_access_denied": install_session_direct_push.get(
            "camera_access_denied"
        ),
        "install_session_direct_push_demo_camera_access_restricted": install_session_direct_push.get(
            "camera_access_restricted"
        ),
        "install_session_direct_push_demo_camera_access_not_determined": install_session_direct_push.get(
            "camera_access_not_determined"
        ),
        "install_session_direct_push_demo_environment_device_enumeration_empty": install_session_direct_push.get(
            "environment_device_enumeration_empty"
        ),
        "install_session_direct_push_demo_visible_all_devices": install_session_direct_push.get(
            "direct_sender_visible_all_devices"
        ),
        "install_session_direct_push_demo_visible_avfoundation_devices": install_session_direct_push.get(
            "direct_sender_visible_avfoundation_devices"
        ),
        "install_session_direct_push_demo_visible_cmio_devices": install_session_direct_push.get(
            "direct_sender_visible_cmio_devices"
        ),
        "install_session_direct_push_demo_requested_camera_access_status": install_session_direct_push.get(
            "requested_camera_access_status"
        ),
        "install_session_direct_push_demo_requested_camera_access_authorized": install_session_direct_push.get(
            "requested_camera_access_authorized"
        ),
        "install_session_direct_push_demo_requested_camera_access_denied": install_session_direct_push.get(
            "requested_camera_access_denied"
        ),
        "install_session_direct_push_demo_requested_camera_access_restricted": install_session_direct_push.get(
            "requested_camera_access_restricted"
        ),
        "install_session_direct_push_demo_requested_camera_access_not_determined": install_session_direct_push.get(
            "requested_camera_access_not_determined"
        ),
        "install_session_direct_push_demo_requested_camera_access_environment_device_enumeration_empty": install_session_direct_push.get(
            "requested_camera_access_environment_device_enumeration_empty"
        ),
        "install_session_direct_push_demo_requested_camera_access_visible_all_devices": install_session_direct_push.get(
            "requested_camera_access_visible_all_devices"
        ),
        "install_session_direct_push_demo_requested_camera_access_visible_avfoundation_devices": install_session_direct_push.get(
            "requested_camera_access_visible_avfoundation_devices"
        ),
        "install_session_direct_push_demo_requested_camera_access_visible_cmio_devices": install_session_direct_push.get(
            "requested_camera_access_visible_cmio_devices"
        ),
        **_prefixed_direct_step_summary_fields(
            "direct_push_demo",
            direct_push_demo,
        ),
        **_prefixed_direct_step_summary_fields(
            "install_session_direct_sender_object_demo",
            install_session_direct_sender_object,
        ),
        "framebus_roundtrip_present": bool(framebus_payload),
        "framebus_roundtrip_producer_kind": framebus_producer_kind,
        "framebus_roundtrip_passed": framebus_consistency.get("all_checks_passed"),
        "framebus_roundtrip_environment_blocked": framebus_environment_blocked,
        "framebus_roundtrip_direct_open_errno": direct_open_errno,
        "direct_push_demo_present": bool(direct_push_demo_payload),
        "direct_push_demo_mode": _optional_string(direct_push_demo_payload.get("mode")),
        "direct_push_demo_frame_source_kind": _optional_string(direct_push_demo_payload.get("frame_source_kind")),
        "direct_push_demo_python_entrypoint_kind": _optional_string(
            direct_push_demo_payload.get("python_entrypoint_kind")
        ),
        "direct_push_demo_requested_frame_kind": _optional_string(
            direct_push_demo_payload.get("requested_frame_kind")
        ),
        "direct_push_demo_requested_entrypoint": _optional_string(
            direct_push_demo_payload.get("requested_entrypoint")
        ),
        "direct_push_demo_sdk_direct_push_used": direct_push_demo_payload.get("sdk_direct_push_used"),
        "direct_push_demo_backend_name": _optional_string(direct_push_demo_payload.get("backend_name")),
        "direct_push_demo_using_direct_sender": direct_push_demo_payload.get("using_direct_sender"),
        "direct_push_demo_direct_sender_attempted": direct_push_demo_payload.get("direct_sender_attempted"),
        "direct_push_demo_direct_sender_state": _optional_string(
            direct_push_demo_payload.get("direct_sender_state")
        ),
        "direct_push_demo_runtime_topology_kind": _optional_string(
            direct_push_demo_payload.get("runtime_topology_kind")
        ),
        "direct_push_demo_runtime_frame_path": _optional_string(
            direct_push_demo_payload.get("runtime_frame_path")
        ),
        "direct_push_demo_runtime_host_role": _optional_string(
            direct_push_demo_payload.get("runtime_host_role")
        ),
        "direct_push_demo_runtime_host_in_frame_hot_path": direct_push_demo_payload.get(
            "runtime_host_in_frame_hot_path"
        ),
        "direct_push_demo_helper_hot_path_used": direct_push_demo_payload.get(
            "helper_hot_path_used"
        ),
        "direct_push_demo_shared_memory_fallback_used": direct_push_demo_payload.get(
            "shared_memory_fallback_used"
        ),
        "direct_push_demo_runtime_dedicated_host_daemon_required": direct_push_demo_payload.get(
            "runtime_dedicated_host_daemon_required"
        ),
        "direct_push_demo_runtime_container_app_configured": direct_push_demo_payload.get(
            "runtime_container_app_configured"
        ),
        "direct_push_demo_runtime_data_plane": _optional_string(
            direct_push_demo_payload.get("runtime_data_plane")
        ),
        "direct_push_demo_runtime_control_plane": _optional_string(
            direct_push_demo_payload.get("runtime_control_plane")
        ),
        "direct_push_demo_direct_sender_target_name": _optional_string(
            direct_push_demo_payload.get("direct_sender_target_name")
        ),
        "direct_push_demo_direct_sender_library_path": _optional_string(
            direct_push_demo_payload.get("direct_sender_library_path")
        ),
        "direct_push_demo_direct_sender_last_error": _optional_string(
            direct_push_demo_payload.get("direct_sender_last_error")
        ),
        "direct_push_demo_camera_name": _optional_string(direct_push_demo_payload.get("camera_name")),
        "direct_push_demo_consumer_count": _optional_int(direct_push_demo_payload.get("consumer_count")),
        "direct_push_demo_requested_frames": _optional_int(direct_push_demo_payload.get("requested_frames")),
        "direct_push_demo_frames_sent": _optional_int(direct_push_demo_payload.get("frames_sent")),
        "direct_push_demo_direct_only": direct_push_demo_payload.get("direct_only"),
        "direct_push_demo_probe_only": direct_push_demo_payload.get("probe_only"),
        "direct_push_demo_allow_shared_memory_fallback": direct_push_demo_payload.get(
            "allow_shared_memory_fallback",
            None
            if direct_push_demo_payload.get("direct_only") is None
            else not bool(direct_push_demo_payload.get("direct_only")),
        ),
        "direct_push_demo_requested_camera_access": direct_push_demo_payload.get(
            "requested_camera_access"
        ),
        "direct_push_demo_error": _optional_string(direct_push_demo_payload.get("error")),
        "direct_push_demo_direct_sender_device_snapshot_present": isinstance(
            direct_push_demo_payload.get("direct_sender_device_snapshot"),
            dict,
        ),
        "direct_push_demo_requested_camera_access_snapshot_present": isinstance(
            direct_push_demo_payload.get("requested_camera_access_snapshot"),
            dict,
        ),
        "direct_push_demo_camera_access_status": _optional_string(
            (
                direct_push_demo_payload.get("direct_sender_device_snapshot", {})
                if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
                else {}
            ).get("camera_access_status")
        ),
        "direct_push_demo_camera_access_authorized": (
            direct_push_demo_payload.get("direct_sender_device_snapshot", {})
            if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
            else {}
        ).get("camera_access_authorized"),
        "direct_push_demo_camera_access_denied": (
            direct_push_demo_payload.get("direct_sender_device_snapshot", {})
            if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
            else {}
        ).get("camera_access_denied"),
        "direct_push_demo_camera_access_restricted": (
            direct_push_demo_payload.get("direct_sender_device_snapshot", {})
            if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
            else {}
        ).get("camera_access_restricted"),
        "direct_push_demo_camera_access_not_determined": (
            direct_push_demo_payload.get("direct_sender_device_snapshot", {})
            if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
            else {}
        ).get("camera_access_not_determined"),
        "direct_push_demo_environment_device_enumeration_empty": (
            direct_push_demo_payload.get("direct_sender_device_snapshot", {})
            if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
            else {}
        ).get("environment_device_enumeration_empty"),
        "direct_push_demo_visible_all_devices": _normalize_string_list(
            (
                direct_push_demo_payload.get("direct_sender_device_snapshot", {})
                if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
                else {}
            ).get("all_devices")
        ),
        "direct_push_demo_visible_avfoundation_devices": _normalize_string_list(
            (
                direct_push_demo_payload.get("direct_sender_device_snapshot", {})
                if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
                else {}
            ).get("avfoundation_devices")
        ),
        "direct_push_demo_visible_cmio_devices": _normalize_string_list(
            (
                direct_push_demo_payload.get("direct_sender_device_snapshot", {})
                if isinstance(direct_push_demo_payload.get("direct_sender_device_snapshot"), dict)
                else {}
            ).get("cmio_devices")
        ),
        "direct_push_demo_requested_camera_access_status": _optional_string(
            (
                direct_push_demo_payload.get("requested_camera_access_snapshot", {})
                if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
                else {}
            ).get("camera_access_status")
        ),
        "direct_push_demo_requested_camera_access_authorized": (
            direct_push_demo_payload.get("requested_camera_access_snapshot", {})
            if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
            else {}
        ).get("camera_access_authorized"),
        "direct_push_demo_requested_camera_access_denied": (
            direct_push_demo_payload.get("requested_camera_access_snapshot", {})
            if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
            else {}
        ).get("camera_access_denied"),
        "direct_push_demo_requested_camera_access_restricted": (
            direct_push_demo_payload.get("requested_camera_access_snapshot", {})
            if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
            else {}
        ).get("camera_access_restricted"),
        "direct_push_demo_requested_camera_access_not_determined": (
            direct_push_demo_payload.get("requested_camera_access_snapshot", {})
            if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
            else {}
        ).get("camera_access_not_determined"),
        "direct_push_demo_requested_camera_access_environment_device_enumeration_empty": (
            direct_push_demo_payload.get("requested_camera_access_snapshot", {})
            if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
            else {}
        ).get("environment_device_enumeration_empty"),
        "direct_push_demo_requested_camera_access_visible_all_devices": _normalize_string_list(
            (
                direct_push_demo_payload.get("requested_camera_access_snapshot", {})
                if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
                else {}
            ).get("all_devices")
        ),
        "direct_push_demo_requested_camera_access_visible_avfoundation_devices": _normalize_string_list(
            (
                direct_push_demo_payload.get("requested_camera_access_snapshot", {})
                if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
                else {}
            ).get("avfoundation_devices")
        ),
        "direct_push_demo_requested_camera_access_visible_cmio_devices": _normalize_string_list(
            (
                direct_push_demo_payload.get("requested_camera_access_snapshot", {})
                if isinstance(direct_push_demo_payload.get("requested_camera_access_snapshot"), dict)
                else {}
            ).get("cmio_devices")
        ),
        **_prefixed_direct_step_summary_fields(
            "direct_sender_object_demo",
            direct_sender_object_demo,
        ),
        "status_binary_check_present": bool(status_binary_payload),
        "status_binary_check_passed": status_binary_consistency.get("all_checks_passed"),
        "status_binary_check_ipc_environment_blocked": status_binary_result.get("ipc_environment_blocked"),
        "status_binary_check_ipc_direct_open_errno": status_binary_result.get("ipc_direct_open_errno"),
        "list_devices_binary_check_present": bool(list_devices_binary_payload),
        "list_devices_binary_check_passed": list_devices_binary_consistency.get("all_checks_passed"),
        "list_devices_binary_check_device_prefix": _optional_string(list_devices_binary_result.get("device_prefix")),
        "list_devices_binary_check_filtered_device_count": _sequence_length(list_devices_binary_result.get("devices")),
        "list_devices_binary_check_total_device_count": _sequence_length(list_devices_binary_result.get("all_devices")),
        "list_devices_binary_check_override_no_match_ok": override_prefix_case_consistency.get("all_checks_passed"),
        "effective_start_ready": effective_start_ready,
        "effective_start_blocker_code": effective_start_blocker_code,
        "effective_devices": effective_devices,
        "effective_all_devices": effective_all_devices,
        "effective_device_prefix": effective_device_prefix,
        "effective_shared_memory_name": effective_shared_memory_name,
        "effective_supported_formats": effective_supported_formats,
        "effective_supported_frame_rates": effective_supported_frame_rates,
        "effective_mach_service_name": effective_mach_service_name,
        "effective_ipc_transport": effective_ipc_transport,
    }


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_manifest_from_existing(path: Path) -> dict[str, object]:
    existing = _load_json_object(path)
    if existing is None:
        return {
            "artifacts": {},
            "steps": {},
            "summary": {},
        }
    artifacts = dict(existing.get("artifacts", {})) if isinstance(existing.get("artifacts"), dict) else {}
    steps = dict(existing.get("steps", {})) if isinstance(existing.get("steps"), dict) else {}
    summary = dict(existing.get("summary", {})) if isinstance(existing.get("summary"), dict) else {}
    return {
        "artifacts": artifacts,
        "steps": steps,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS validation session helper")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--status-tool")
    parser.add_argument("--list-devices-tool")
    parser.add_argument("--install-tool")
    parser.add_argument("--uninstall-tool")
    parser.add_argument("--sync-ipc-tool")
    parser.add_argument("--app-bundle")
    parser.add_argument("--app-executable")
    parser.add_argument("--host-bundle")
    parser.add_argument("--host-executable")
    parser.add_argument("--direct-sender-library")
    parser.add_argument("--pkg-path")
    parser.add_argument("--installer-executable")
    parser.add_argument("--disable-auto-package", action="store_true")
    parser.add_argument("--manual-results")
    parser.add_argument("--reuse-existing-artifacts", action="store_true")
    parser.add_argument("--smoke-tool", default=str(DEFAULT_SMOKE_TOOL))
    parser.add_argument("--install-session-tool", default=str(DEFAULT_INSTALL_SESSION_TOOL))
    parser.add_argument("--framebus-roundtrip-tool", default=str(DEFAULT_FRAMEBUS_ROUNDTRIP_TOOL))
    parser.add_argument(
        "--framebus-producer-kind",
        choices=["shm-sink", "mac-virtual-camera"],
        default="mac-virtual-camera",
    )
    parser.add_argument("--direct-push-demo-tool", default=str(DEFAULT_DIRECT_PUSH_DEMO_TOOL))
    parser.add_argument("--direct-push-frames", type=int)
    parser.add_argument("--direct-push-frame-kind")
    parser.add_argument("--direct-push-entrypoint")
    parser.add_argument("--direct-push-allow-shared-memory-fallback", action="store_true")
    parser.add_argument("--direct-push-request-camera-access", action="store_true")
    parser.add_argument(
        "--direct-sender-object-demo-tool",
        default=str(DEFAULT_DIRECT_SENDER_OBJECT_DEMO_TOOL),
    )
    parser.add_argument("--direct-sender-object-frames", type=int)
    parser.add_argument("--direct-sender-object-frame-kind")
    parser.add_argument("--direct-sender-object-request-camera-access", action="store_true")
    parser.add_argument("--status-binary-check-tool", default=str(DEFAULT_STATUS_BINARY_CHECK_TOOL))
    parser.add_argument("--list-devices-binary-check-tool", default=str(DEFAULT_LIST_DEVICES_BINARY_CHECK_TOOL))
    parser.add_argument("--entrypoints-contract-tool", default=str(DEFAULT_ENTRYPOINTS_CONTRACT_TOOL))
    parser.add_argument("--sdk-contract-tool", default=str(DEFAULT_SDK_CONTRACT_TOOL))
    parser.add_argument("--artifact-check-tool", default=str(DEFAULT_ARTIFACT_CHECK_TOOL))
    parser.add_argument("--acceptance-tool", default=str(DEFAULT_ACCEPTANCE_TOOL))
    parser.add_argument("--acceptance-contract-tool", default=str(DEFAULT_ACCEPTANCE_CONTRACT_TOOL))
    parser.add_argument("--summary-tool", default=str(DEFAULT_SUMMARY_TOOL))
    parser.add_argument("--demo-tool", default=str(DEFAULT_DEMO_TOOL))
    parser.add_argument("--benchmark-tool", default=str(DEFAULT_BENCHMARK_TOOL))
    parser.add_argument("--preflight-tool", default=str(DEFAULT_PREFLIGHT_TOOL))
    parser.add_argument("--release-diagnostics-tool", default=str(DEFAULT_RELEASE_DIAGNOSTICS_TOOL))
    parser.add_argument("--validation-report-tool", default=str(DEFAULT_VALIDATION_REPORT_TOOL))
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--skip-release-diagnostics", action="store_true")
    parser.add_argument("--skip-demo", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--run-install", action="store_true")
    parser.add_argument("--run-uninstall", action="store_true")
    parser.add_argument("--run-install-session", action="store_true")
    parser.add_argument("--run-framebus-roundtrip", action="store_true")
    parser.add_argument("--run-direct-push-demo", action="store_true")
    parser.add_argument("--run-direct-sender-object-demo", action="store_true")
    parser.add_argument("--run-status-binary-check", action="store_true")
    parser.add_argument("--run-list-devices-binary-check", action="store_true")
    parser.add_argument("--benchmark-profile", choices=["720p30", "720p60", "1080p30", "1080p60", "4k30", "4k60"])
    parser.add_argument("--benchmark-matrix", action="store_true")
    parser.add_argument("--benchmark-warmup", type=float, default=1.0)
    parser.add_argument(
        "--mode",
        choices=["numpy-direct", "provider", "latest-provider", "image", "pixmap", "widget", "screen", "video-file"],
        default="provider",
    )
    parser.add_argument("--video-path")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--name", default="AK Virtual Camera")
    args = parser.parse_args(argv)

    if not args.skip_demo and args.mode == "video-file" and not args.video_path:
        parser.error("video-file mode requires --video-path unless --skip-demo is set")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight_report = output_dir / "preflight.json"
    release_diagnostics_report = output_dir / "release-diagnostics.json"
    demo_report = output_dir / "demo-report.json"
    benchmark_report = output_dir / ("benchmark-matrix.json" if args.benchmark_matrix else "benchmark.json")
    manual_template = output_dir / "manual-results.template.json"
    validation_report = output_dir / "validation-report.json"
    smoke_report = output_dir / "smoke-report.json"
    install_session_report = output_dir / "install-session-report.json"
    framebus_roundtrip_report = output_dir / "framebus-roundtrip.json"
    direct_push_demo_report = output_dir / "direct-push-report.json"
    direct_sender_object_demo_report = output_dir / "direct-sender-object-report.json"
    status_binary_check_report = output_dir / "status-binary-check.json"
    list_devices_binary_check_report = output_dir / "list-devices-binary-check.json"
    entrypoints_contract_report = output_dir / "entrypoints-contract.json"
    sdk_contract_report = output_dir / "sdk-contract.json"
    artifact_check_report = output_dir / "session-manifest-check.json"
    acceptance_report = output_dir / "session-acceptance.json"
    acceptance_contract_report = output_dir / "session-acceptance-contract.json"
    summary_report = output_dir / "session-summary.md"
    try:
        app_bundle, app_executable = _resolve_container_app_args(
            app_bundle=args.app_bundle,
            app_executable=args.app_executable,
            host_bundle=args.host_bundle,
            host_executable=args.host_executable,
        )
    except ValueError as exc:
        parser.error(str(exc))

    manifest_path = output_dir / "session-manifest.json"

    manifest: dict[str, object] = (
        _seed_manifest_from_existing(manifest_path)
        if args.reuse_existing_artifacts
        else {"artifacts": {}, "steps": {}, "summary": {}}
    )
    manifest["artifacts"] = {
        **(dict(manifest.get("artifacts", {})) if isinstance(manifest.get("artifacts"), dict) else {}),
        "preflight_report": str(preflight_report),
        "release_diagnostics_report": str(release_diagnostics_report),
        "demo_report": str(demo_report),
        "benchmark_report": str(benchmark_report),
        "manual_template": str(manual_template),
        "validation_report": str(validation_report),
        "smoke_report": str(smoke_report),
        "install_session_report": str(install_session_report),
        "framebus_roundtrip_report": str(framebus_roundtrip_report),
        "direct_push_demo_report": str(direct_push_demo_report),
        "direct_sender_object_demo_report": str(direct_sender_object_demo_report),
        "status_binary_check_report": str(status_binary_check_report),
        "list_devices_binary_check_report": str(list_devices_binary_check_report),
        "entrypoints_contract_report": str(entrypoints_contract_report),
        "sdk_contract_report": str(sdk_contract_report),
        "artifact_check_report": str(artifact_check_report),
        "acceptance_report": str(acceptance_report),
        "acceptance_contract_report": str(acceptance_contract_report),
        "summary_report": str(summary_report),
    }
    manifest["steps"] = dict(manifest.get("steps", {})) if isinstance(manifest.get("steps"), dict) else {}
    manifest["summary"] = dict(manifest.get("summary", {})) if isinstance(manifest.get("summary"), dict) else {}

    preflight_generated = args.reuse_existing_artifacts and preflight_report.is_file()
    if not args.skip_preflight:
        cmd = [
            sys.executable,
            str(Path(args.preflight_tool)),
            "--output",
            str(preflight_report),
        ]
        completed = _run(cmd)
        manifest["steps"]["preflight"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode
        preflight_generated = preflight_report.is_file()

    release_diagnostics_generated = args.reuse_existing_artifacts and release_diagnostics_report.is_file()
    if not args.skip_release_diagnostics:
        cmd = [
            sys.executable,
            str(Path(args.release_diagnostics_tool)),
            "--output",
            str(release_diagnostics_report),
        ]
        if app_bundle:
            app_bundle_path = Path(app_bundle)
            cmd.extend(["--app-bundle", str(app_bundle_path)])
            cmd.extend([
                "--extension-bundle",
                str(
                    app_bundle_path
                    / "Contents"
                    / "Library"
                    / "SystemExtensions"
                    / "com.sidus.amaran-desktop.cameraextension.systemextension"
                ),
            ])
        if args.sync_ipc_tool:
            cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
        if args.pkg_path:
            cmd.extend(["--pkg-path", str(args.pkg_path)])
        completed = _run(cmd)
        manifest["steps"]["release_diagnostics"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode
        release_diagnostics_generated = release_diagnostics_report.is_file()

    demo_generated = args.reuse_existing_artifacts and demo_report.is_file()
    if not args.skip_demo:
        cmd = [
            sys.executable,
            str(Path(args.demo_tool)),
            "--mode", args.mode,
            "--width", str(args.width),
            "--height", str(args.height),
            "--fps", str(args.fps),
            "--duration", str(args.duration),
            "--name", args.name,
            "--report-json", str(demo_report),
        ]
        if args.video_path:
            cmd.extend(["--video-path", str(args.video_path)])
        if app_bundle:
            cmd.extend(["--app-bundle", str(app_bundle)])
        if app_executable:
            cmd.extend(["--app-executable", str(app_executable)])
        if args.direct_sender_library:
            cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
        completed = _run(cmd)
        manifest["steps"]["demo"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode
        demo_generated = demo_report.is_file()

    benchmark_generated = args.reuse_existing_artifacts and benchmark_report.is_file()
    if not args.skip_benchmark:
        cmd = [sys.executable, str(Path(args.benchmark_tool))]
        if args.benchmark_matrix:
            cmd.append("--matrix")
        elif args.benchmark_profile:
            cmd.extend(["--profile", args.benchmark_profile])
        else:
            cmd.extend([
                "--width", str(args.width),
                "--height", str(args.height),
                "--fps", str(args.fps),
            ])
        cmd.extend([
            "--duration", str(args.duration),
            "--warmup", str(args.benchmark_warmup),
            "--output", str(benchmark_report),
        ])
        completed = _run(cmd)
        manifest["steps"]["benchmark"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode
        benchmark_generated = benchmark_report.is_file()

    framebus_roundtrip_generated = args.reuse_existing_artifacts and framebus_roundtrip_report.is_file()
    if args.run_framebus_roundtrip:
        cmd = [
            sys.executable,
            str(Path(args.framebus_roundtrip_tool)),
            "--width", str(args.width),
            "--height", str(args.height),
            "--producer-kind", str(args.framebus_producer_kind),
            "--output", str(framebus_roundtrip_report),
        ]
        completed = _run(cmd)
        manifest["steps"]["framebus_roundtrip"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        framebus_roundtrip_generated = framebus_roundtrip_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    direct_push_demo_generated = args.reuse_existing_artifacts and direct_push_demo_report.is_file()
    if args.run_direct_push_demo:
        cmd = [
            sys.executable,
            str(Path(args.direct_push_demo_tool)),
            "--width", str(args.width),
            "--height", str(args.height),
            "--fps", str(args.fps),
            "--duration", str(args.duration),
            "--name", args.name,
            "--report-json", str(direct_push_demo_report),
        ]
        if app_bundle:
            cmd.extend(["--app-bundle", str(app_bundle)])
        if app_executable:
            cmd.extend(["--app-executable", str(app_executable)])
        if args.direct_sender_library:
            cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
        if args.direct_push_frames is not None:
            cmd.extend(["--frames", str(args.direct_push_frames)])
        if args.direct_push_frame_kind:
            cmd.extend(["--frame-kind", str(args.direct_push_frame_kind)])
        if args.direct_push_entrypoint:
            cmd.extend(["--entrypoint", str(args.direct_push_entrypoint)])
        if args.direct_push_allow_shared_memory_fallback:
            cmd.append("--allow-shared-memory-fallback")
        if args.direct_push_request_camera_access:
            cmd.append("--request-camera-access")
        completed = _run(cmd)
        manifest["steps"]["direct_push_demo"] = {
            "request": {
                "requested_frames": args.direct_push_frames,
                "requested_frame_kind": args.direct_push_frame_kind,
                "requested_entrypoint": args.direct_push_entrypoint,
                "allow_shared_memory_fallback": bool(
                    args.direct_push_allow_shared_memory_fallback
                ),
                "requested_camera_access": bool(args.direct_push_request_camera_access),
            },
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        direct_push_demo_generated = direct_push_demo_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    direct_sender_object_demo_generated = (
        args.reuse_existing_artifacts and direct_sender_object_demo_report.is_file()
    )
    if args.run_direct_sender_object_demo:
        cmd = [
            sys.executable,
            str(Path(args.direct_sender_object_demo_tool)),
            "--width", str(args.width),
            "--height", str(args.height),
            "--fps", str(args.fps),
            "--name", args.name,
            "--report-json", str(direct_sender_object_demo_report),
        ]
        if args.direct_sender_library:
            cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
        if args.direct_sender_object_frames is not None:
            cmd.extend(["--frames", str(args.direct_sender_object_frames)])
        if args.direct_sender_object_frame_kind:
            cmd.extend(["--frame-kind", str(args.direct_sender_object_frame_kind)])
        if args.direct_sender_object_request_camera_access:
            cmd.append("--request-camera-access")
        completed = _run(cmd)
        manifest["steps"]["direct_sender_object_demo"] = {
            "request": {
                "requested_frames": args.direct_sender_object_frames,
                "requested_frame_kind": args.direct_sender_object_frame_kind,
                "requested_camera_access": bool(args.direct_sender_object_request_camera_access),
            },
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        direct_sender_object_demo_generated = direct_sender_object_demo_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    status_binary_check_generated = args.reuse_existing_artifacts and status_binary_check_report.is_file()
    if args.run_status_binary_check:
        cmd = [
            sys.executable,
            str(Path(args.status_binary_check_tool)),
            "--output", str(status_binary_check_report),
        ]
        if args.status_tool:
            cmd.extend(["--status-tool", str(args.status_tool)])
        completed = _run(cmd)
        manifest["steps"]["status_binary_check"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        status_binary_check_generated = status_binary_check_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    list_devices_binary_check_generated = (
        args.reuse_existing_artifacts and list_devices_binary_check_report.is_file()
    )
    if args.run_list_devices_binary_check:
        cmd = [
            sys.executable,
            str(Path(args.list_devices_binary_check_tool)),
            "--output", str(list_devices_binary_check_report),
        ]
        if args.list_devices_tool:
            cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
        if args.name != DEFAULT_CAMERA_NAME:
            cmd.extend(["--expected-prefix", args.name])
        completed = _run(cmd)
        manifest["steps"]["list_devices_binary_check"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        list_devices_binary_check_generated = list_devices_binary_check_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    smoke_generated = args.reuse_existing_artifacts and smoke_report.is_file()
    if args.run_install or args.run_uninstall:
        cmd = [
            sys.executable,
            str(Path(args.smoke_tool)),
            "--output", str(smoke_report),
        ]
        if args.status_tool:
            cmd.extend(["--status-tool", str(args.status_tool)])
        if args.list_devices_tool:
            cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
        if args.install_tool:
            cmd.extend(["--install-tool", str(args.install_tool)])
        if args.uninstall_tool:
            cmd.extend(["--uninstall-tool", str(args.uninstall_tool)])
        if args.sync_ipc_tool:
            cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
        if app_bundle:
            cmd.extend(["--app-bundle", str(app_bundle)])
        if app_executable:
            cmd.extend(["--app-executable", str(app_executable)])
        if args.pkg_path:
            cmd.extend(["--pkg-path", str(args.pkg_path)])
        if args.installer_executable:
            cmd.extend(["--installer-executable", str(args.installer_executable)])
        if args.disable_auto_package:
            cmd.append("--disable-auto-package")
        if framebus_roundtrip_generated:
            cmd.extend(["--framebus-roundtrip-json", str(framebus_roundtrip_report)])
        if args.run_install:
            cmd.append("--run-install")
        if args.run_uninstall:
            cmd.append("--run-uninstall")
        if args.direct_sender_library:
            cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
        if args.direct_sender_object_demo_tool:
            cmd.extend(["--direct-sender-object-demo-tool", str(args.direct_sender_object_demo_tool)])
        if args.direct_sender_object_frames is not None:
            cmd.extend(["--direct-sender-object-frames", str(args.direct_sender_object_frames)])
        if args.direct_sender_object_frame_kind:
            cmd.extend(["--direct-sender-object-frame-kind", str(args.direct_sender_object_frame_kind)])
        if args.direct_sender_object_request_camera_access:
            cmd.append("--direct-sender-object-request-camera-access")
        if args.run_direct_sender_object_demo:
            cmd.append("--run-direct-sender-object-demo")
        completed = _run(cmd)
        manifest["steps"]["smoke"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        smoke_generated = smoke_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    install_session_generated = args.reuse_existing_artifacts and install_session_report.is_file()
    if args.run_install_session:
        cmd = [
            sys.executable,
            str(Path(args.install_session_tool)),
            "--output", str(install_session_report),
        ]
        if args.status_tool:
            cmd.extend(["--status-tool", str(args.status_tool)])
        if args.install_tool:
            cmd.extend(["--install-tool", str(args.install_tool)])
        if args.list_devices_tool:
            cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
        if args.uninstall_tool:
            cmd.extend(["--uninstall-tool", str(args.uninstall_tool)])
        if args.sync_ipc_tool:
            cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
        if app_bundle:
            cmd.extend(["--app-bundle", str(app_bundle)])
        if app_executable:
            cmd.extend(["--app-executable", str(app_executable)])
        if args.pkg_path:
            cmd.extend(["--pkg-path", str(args.pkg_path)])
        if args.installer_executable:
            cmd.extend(["--installer-executable", str(args.installer_executable)])
        if args.disable_auto_package:
            cmd.append("--disable-auto-package")
        if framebus_roundtrip_generated:
            cmd.extend(["--framebus-roundtrip-json", str(framebus_roundtrip_report)])
        if args.run_uninstall:
            cmd.append("--run-uninstall")
        if args.direct_sender_library:
            cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
        if args.direct_sender_object_demo_tool:
            cmd.extend(["--direct-sender-object-demo-tool", str(args.direct_sender_object_demo_tool)])
        if args.direct_sender_object_frames is not None:
            cmd.extend(["--direct-sender-object-frames", str(args.direct_sender_object_frames)])
        if args.direct_sender_object_frame_kind:
            cmd.extend(["--direct-sender-object-frame-kind", str(args.direct_sender_object_frame_kind)])
        if args.direct_sender_object_request_camera_access:
            cmd.append("--direct-sender-object-request-camera-access")
        if args.run_direct_sender_object_demo:
            cmd.append("--run-direct-sender-object-demo")
        completed = _run(cmd)
        manifest["steps"]["install_session"] = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _write_manifest(manifest_path, manifest)
        install_session_generated = install_session_report.is_file()
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or "")
            return completed.returncode

    cmd = [sys.executable, str(Path(args.validation_report_tool))]
    if args.status_tool:
        cmd.extend(["--status-tool", args.status_tool])
    if args.list_devices_tool:
        cmd.extend(["--list-devices-tool", args.list_devices_tool])
    if args.install_tool:
        cmd.extend(["--install-tool", args.install_tool])
    if args.uninstall_tool:
        cmd.extend(["--uninstall-tool", args.uninstall_tool])
    if args.sync_ipc_tool:
        cmd.extend(["--sync-ipc-tool", args.sync_ipc_tool])
    if app_bundle:
        cmd.extend(["--app-bundle", app_bundle])
    if app_executable:
        cmd.extend(["--app-executable", app_executable])
    if args.pkg_path:
        cmd.extend(["--pkg-path", args.pkg_path])
    if args.installer_executable:
        cmd.extend(["--installer-executable", args.installer_executable])
    if args.disable_auto_package:
        cmd.append("--disable-auto-package")
    if preflight_generated:
        cmd.extend(["--preflight-json", str(preflight_report)])
    if release_diagnostics_generated:
        cmd.extend(["--release-diagnostics-json", str(release_diagnostics_report)])
    if install_session_generated:
        cmd.extend(["--install-session-json", str(install_session_report)])
    if smoke_generated:
        cmd.extend(["--smoke-json", str(smoke_report)])
    if framebus_roundtrip_generated:
        cmd.extend(["--framebus-roundtrip-json", str(framebus_roundtrip_report)])
    if status_binary_check_generated:
        cmd.extend(["--status-binary-check-json", str(status_binary_check_report)])
    if list_devices_binary_check_generated:
        cmd.extend(["--list-devices-binary-check-json", str(list_devices_binary_check_report)])
    if demo_generated:
        cmd.extend(["--demo-json", str(demo_report)])
    if benchmark_generated:
        cmd.extend(["--benchmark-json", str(benchmark_report)])
    if args.manual_results:
        cmd.extend(["--manual-results", args.manual_results])
    if args.run_install and not smoke_generated:
        cmd.append("--run-install")
    cmd.extend([
        "--write-manual-template", str(manual_template),
        "--output", str(validation_report),
    ])
    completed = _run(cmd)
    manifest["steps"]["validation_report"] = {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    manifest["summary"] = _build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=release_diagnostics_report,
        smoke_report=smoke_report,
        install_session_report=install_session_report,
        framebus_roundtrip_report=framebus_roundtrip_report,
        direct_push_demo_report=direct_push_demo_report if direct_push_demo_generated else None,
        direct_sender_object_demo_report=(
            direct_sender_object_demo_report if direct_sender_object_demo_generated else None
        ),
        status_binary_check_report=status_binary_check_report,
        list_devices_binary_check_report=list_devices_binary_check_report,
    )
    _write_manifest(manifest_path, manifest)
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or "")
        return completed.returncode
    if manual_template.is_file():
        _normalize_manual_template_file(
            manual_template,
            camera_name=args.name,
        )

    entrypoints_contract_cmd = [
        sys.executable,
        str(Path(args.entrypoints_contract_tool)),
        "--output", str(entrypoints_contract_report),
    ]
    entrypoints_contract_completed = _run(entrypoints_contract_cmd)
    manifest["steps"]["entrypoints_contract"] = {
        "command": entrypoints_contract_cmd,
        "returncode": entrypoints_contract_completed.returncode,
        "stdout": entrypoints_contract_completed.stdout,
        "stderr": entrypoints_contract_completed.stderr,
    }
    entrypoints_contract_payload = _load_json_object(entrypoints_contract_report)
    manifest["summary"] = _merge_entrypoints_contract_summary(
        manifest["summary"],
        entrypoints_contract_payload,
    )
    _write_manifest(manifest_path, manifest)
    if entrypoints_contract_completed.returncode != 0:
        sys.stderr.write(entrypoints_contract_completed.stderr or "")
        return entrypoints_contract_completed.returncode

    sdk_contract_cmd = [
        sys.executable,
        str(Path(args.sdk_contract_tool)),
        "--output", str(sdk_contract_report),
    ]
    sdk_contract_completed = _run(sdk_contract_cmd)
    manifest["steps"]["sdk_contract"] = {
        "command": sdk_contract_cmd,
        "returncode": sdk_contract_completed.returncode,
        "stdout": sdk_contract_completed.stdout,
        "stderr": sdk_contract_completed.stderr,
    }
    sdk_contract_payload = _load_json_object(sdk_contract_report)
    manifest["summary"] = _merge_sdk_contract_summary(
        manifest["summary"],
        sdk_contract_payload,
    )
    _write_manifest(manifest_path, manifest)
    if sdk_contract_completed.returncode != 0:
        sys.stderr.write(sdk_contract_completed.stderr or "")
        return sdk_contract_completed.returncode

    artifact_check_payload: dict[str, object] | None = None
    artifact_check_cmd = [
        sys.executable,
        str(Path(args.artifact_check_tool)),
        "--manifest", str(manifest_path),
        "--require-existing-artifacts",
        "--output", str(artifact_check_report),
    ]
    artifact_check_completed = _run(artifact_check_cmd)
    manifest["steps"]["artifact_check"] = {
        "command": artifact_check_cmd,
        "returncode": artifact_check_completed.returncode,
        "stdout": artifact_check_completed.stdout,
        "stderr": artifact_check_completed.stderr,
    }
    artifact_check_payload = _load_json_object(artifact_check_report)
    manifest["summary"] = _merge_artifact_check_summary(
        manifest["summary"],
        artifact_check_payload,
    )
    _write_manifest(manifest_path, manifest)

    acceptance_cmd = [
        sys.executable,
        str(Path(args.acceptance_tool)),
        "--manifest", str(manifest_path),
        "--output", str(acceptance_report),
    ]
    acceptance_completed = _run(acceptance_cmd)
    manifest["steps"]["acceptance"] = {
        "command": acceptance_cmd,
        "returncode": acceptance_completed.returncode,
        "stdout": acceptance_completed.stdout,
        "stderr": acceptance_completed.stderr,
    }
    acceptance_payload = _load_json_object(acceptance_report)
    manifest["summary"] = _merge_acceptance_summary(
        manifest["summary"],
        acceptance_payload,
    )
    _write_manifest(manifest_path, manifest)

    acceptance_contract_cmd = [
        sys.executable,
        str(Path(args.acceptance_contract_tool)),
        "--output", str(acceptance_contract_report),
    ]
    acceptance_contract_completed = _run(acceptance_contract_cmd)
    manifest["steps"]["acceptance_contract"] = {
        "command": acceptance_contract_cmd,
        "returncode": acceptance_contract_completed.returncode,
        "stdout": acceptance_contract_completed.stdout,
        "stderr": acceptance_contract_completed.stderr,
    }
    acceptance_contract_payload = _load_json_object(acceptance_contract_report)
    manifest["summary"] = _merge_acceptance_contract_summary(
        manifest["summary"],
        acceptance_contract_payload,
    )
    _write_manifest(manifest_path, manifest)

    summary_cmd = [
        sys.executable,
        str(Path(args.summary_tool)),
        "--manifest", str(manifest_path),
        "--output", str(summary_report),
    ]
    summary_completed = _run(summary_cmd)
    manifest["steps"]["summary"] = {
        "command": summary_cmd,
        "returncode": summary_completed.returncode,
        "stdout": summary_completed.stdout,
        "stderr": summary_completed.stderr,
    }
    manifest["summary"]["summary_report_present"] = summary_report.is_file()
    _write_manifest(manifest_path, manifest)
    if summary_completed.returncode != 0:
        sys.stderr.write(summary_completed.stderr or "")
        return summary_completed.returncode

    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
