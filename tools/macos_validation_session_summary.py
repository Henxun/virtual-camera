# SPDX-License-Identifier: Apache-2.0
"""Reader-friendly summary for macOS validation-session artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "build" / "macos" / "session" / "session-manifest.json"
CAMERA_CORE_SRC = ROOT / "camera-core" / "src"
EXPECTED_BENCHMARK_PROFILE_NAMES = (
    "720p30",
    "720p60",
    "1080p30",
    "1080p60",
    "4k30",
    "4k60",
)

if str(CAMERA_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CAMERA_CORE_SRC))

try:
    from akvc.platforms.macos.installer import describe_manual_app_validation_gates
except Exception:  # pragma: no cover - fallback keeps summary helper usable in partial envs
    def describe_manual_app_validation_gates(gate_names: object) -> list[str]:
        if not isinstance(gate_names, list):
            return []
        return [str(name) for name in gate_names if str(name)]


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _stringify_list(value: object) -> str:
    if not isinstance(value, list):
        return "-"
    normalized = [str(item) for item in value if item not in (None, "")]
    return ", ".join(normalized) if normalized else "-"


def _stringify_command(value: object) -> str:
    if not isinstance(value, list):
        return "-"
    normalized = [str(item) for item in value if item not in (None, "")]
    return " ".join(normalized) if normalized else "-"


def _stringify_manual_app_validation_gates(value: object) -> str:
    if not isinstance(value, list):
        return "-"
    labels = describe_manual_app_validation_gates(value)
    return _stringify_list(labels)


def _bool_label(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _all_true_or_false_or_none(*values: object) -> bool | None:
    if values and all(value is True for value in values):
        return True
    if any(value is False for value in values):
        return False
    return None


def _sync_ipc_gate_prerequisites(summary: dict[str, Any]) -> bool | None:
    return _all_true_or_false_or_none(
        summary.get("release_sync_ipc_tool_exists"),
        summary.get("release_sync_ipc_tool_signed"),
        summary.get("release_sync_ipc_tool_universal2_ready"),
        summary.get("install_session_sync_ipc_present"),
        summary.get("install_session_sync_ipc_supported"),
        summary.get("install_session_sync_ipc_success"),
    )


def _artifacts_from_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in artifacts.items()
        if isinstance(value, str) and value
    }


def _acceptance_criteria_map(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in criteria:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            result[name] = dict(item)
    return result


def _acceptance_gate_status(
    summary: dict[str, Any],
    acceptance_criteria: dict[str, dict[str, Any]],
    name: str,
) -> str:
    criterion = acceptance_criteria.get(name, {})
    if isinstance(criterion, dict):
        status = criterion.get("status")
        if isinstance(status, str) and status:
            return status
    value = summary.get(name)
    return str(value) if isinstance(value, str) and value else "unknown"


def _validation_app_matrix_lines(summary: dict[str, Any]) -> list[str]:
    matrix = summary.get("validation_app_matrix")
    if not isinstance(matrix, dict) or not matrix:
        return ["- `-`"]
    lines: list[str] = []
    for app_id in sorted(str(key) for key in matrix):
        item = matrix.get(app_id)
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", app_id))
        result = str(item.get("result", "-") or "-")
        reviewed = _bool_label(item.get("reviewed"))
        validated = _bool_label(item.get("validated"))
        ready = _bool_label(item.get("ready"))
        status = str(item.get("status", "-") or "-")
        notes = str(item.get("notes", "") or "")
        steps = item.get("steps") if isinstance(item.get("steps"), list) else []
        checks = item.get("checks") if isinstance(item.get("checks"), list) else []
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        device_listed = _bool_label(evidence.get("device_listed"))
        device_selected = _bool_label(evidence.get("device_selected"))
        preview_visible = _bool_label(evidence.get("preview_visible"))
        screenshot = str(evidence.get("screenshot", "") or "")
        first_step = str(steps[0]) if steps else ""
        first_check = str(checks[0]) if checks else ""
        line = (
            f"- {app_id} ({name}): result=`{result}` reviewed=`{reviewed}` "
            f"validated=`{validated}` ready=`{ready}` status=`{status}` "
            f"steps=`{len(steps)}` checks=`{len(checks)}` "
            f"listed=`{device_listed}` selected=`{device_selected}` preview=`{preview_visible}`"
        )
        if screenshot:
            line += f" screenshot=`{screenshot}`"
        if notes:
            line += f" notes=`{notes}`"
        if first_step:
            line += f" first_step=`{first_step}`"
        if first_check:
            line += f" first_check=`{first_check}`"
        lines.append(line)
    return lines or ["- `-`"]


def _validation_app_matrix(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    matrix = summary.get("validation_app_matrix")
    if not isinstance(matrix, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for app_id, item in matrix.items():
        if isinstance(app_id, str) and app_id and isinstance(item, dict):
            normalized[app_id] = item
    return normalized


def _validation_app_ids_with_result(summary: dict[str, Any], result: str) -> list[str]:
    matrix = _validation_app_matrix(summary)
    return sorted(
        app_id
        for app_id, item in matrix.items()
        if str(item.get("result", "") or "") == result
    )


def _validation_unreviewed_app_ids(summary: dict[str, Any]) -> list[str]:
    matrix = _validation_app_matrix(summary)
    return sorted(
        app_id for app_id, item in matrix.items() if item.get("reviewed") is False
    )


def _validation_reviewed_app_ids(summary: dict[str, Any]) -> list[str]:
    matrix = _validation_app_matrix(summary)
    return sorted(
        app_id for app_id, item in matrix.items() if item.get("reviewed") is True
    )


def _validation_reviewed_app_count(summary: dict[str, Any]) -> int:
    matrix = _validation_app_matrix(summary)
    return sum(1 for item in matrix.values() if item.get("reviewed") is True)


def _summary_app_list(summary: dict[str, Any], key: str, fallback: list[str]) -> list[str]:
    value = summary.get(key)
    if isinstance(value, list):
        return value
    return fallback


def _summary_app_count(summary: dict[str, Any], key: str, fallback: int | None) -> int | None:
    value = summary.get(key)
    if isinstance(value, int):
        return value
    return fallback


def _summary_float(summary: dict[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _benchmark_matrix_profiles(summary: dict[str, Any]) -> list[dict[str, Any]]:
    value = summary.get("validation_benchmark_matrix_profiles")
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        profile_name = item.get("profile_name")
        if isinstance(profile_name, str) and profile_name:
            normalized.append(item)
    return normalized


def _number_label(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _matches_expected_name(expected: object, observed: object) -> bool | None:
    expected_text = str(expected).strip() if expected not in (None, "") else ""
    observed_text = str(observed).strip() if observed not in (None, "") else ""
    if not expected_text or not observed_text:
        return None
    return expected_text == observed_text


def _benchmark_matrix_profile_lines(summary: dict[str, Any]) -> list[str]:
    profiles = _benchmark_matrix_profiles(summary)
    if not profiles:
        return []
    lines: list[str] = []
    for item in profiles:
        profile_name = str(item.get("profile_name"))
        width = _number_label(item.get("width"))
        height = _number_label(item.get("height"))
        fps = _number_label(item.get("fps"))
        fps_target_met = _bool_label(item.get("fps_target_met"))
        cpu_target_applies = _bool_label(item.get("cpu_target_applies"))
        cpu_target_met = _bool_label(item.get("cpu_target_met"))
        actual_fps = _number_label(item.get("actual_fps"))
        cpu_percent = _number_label(item.get("cpu_percent"))
        avg_latency_ms = _number_label(item.get("avg_latency_ms"))
        lines.append(
            f"- {profile_name}: {width}x{height}@{fps} fps_target_met=`{fps_target_met}` "
            f"cpu_target_applies=`{cpu_target_applies}` cpu_target_met=`{cpu_target_met}` "
            f"actual_fps=`{actual_fps}` cpu_percent=`{cpu_percent}` avg_latency_ms=`{avg_latency_ms}`"
        )
    return lines


def _benchmark_profile_names(summary: dict[str, Any]) -> list[str]:
    return [
        str(item.get("profile_name"))
        for item in _benchmark_matrix_profiles(summary)
        if isinstance(item.get("profile_name"), str) and item.get("profile_name")
    ]


def _benchmark_matrix_complete_label(summary: dict[str, Any]) -> str:
    names = set(_benchmark_profile_names(summary))
    if not names:
        return "unknown"
    return "yes" if names == set(EXPECTED_BENCHMARK_PROFILE_NAMES) else "no"


def render_summary(manifest_path: Path) -> str:
    manifest = _load_json_object(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)

    artifacts = _artifacts_from_manifest(manifest)
    summary = (
        dict(manifest.get("summary", {}))
        if isinstance(manifest.get("summary"), dict)
        else {}
    )
    acceptance_payload = _load_json_object(Path(artifacts["acceptance_report"])) if "acceptance_report" in artifacts else None
    acceptance_summary = (
        dict(acceptance_payload.get("summary", {}))
        if isinstance(acceptance_payload, dict) and isinstance(acceptance_payload.get("summary"), dict)
        else {}
    )
    acceptance_criteria = _acceptance_criteria_map(acceptance_payload)

    app_detail_lines = _validation_app_matrix_lines(summary)
    passed_app_ids = _summary_app_list(
        summary,
        "validation_passed_app_ids",
        _validation_app_ids_with_result(summary, "pass"),
    )
    failed_app_ids = _summary_app_list(
        summary,
        "validation_failed_app_ids",
        _validation_app_ids_with_result(summary, "fail"),
    )
    pending_app_ids = _summary_app_list(
        summary,
        "validation_pending_app_ids",
        _validation_app_ids_with_result(summary, "pending"),
    )
    skipped_app_ids = _summary_app_list(
        summary,
        "validation_skipped_app_ids",
        _validation_app_ids_with_result(summary, "skipped"),
    )
    reviewed_app_ids = _summary_app_list(
        summary,
        "validation_reviewed_app_ids",
        _validation_reviewed_app_ids(summary),
    )
    unreviewed_app_ids = _summary_app_list(
        summary,
        "validation_unreviewed_app_ids",
        _validation_unreviewed_app_ids(summary),
    )
    missing_target_app_ids = _summary_app_list(
        summary,
        "validation_missing_target_app_ids",
        [],
    )
    observed_target_app_ids = _summary_app_list(
        summary,
        "validation_observed_target_app_ids",
        [],
    )
    unexpected_target_app_ids = _summary_app_list(
        summary,
        "validation_unexpected_target_app_ids",
        [],
    )
    target_app_ids_complete = summary.get("validation_target_app_ids_complete")
    validated_apps = _summary_app_count(
        summary,
        "validation_validated_apps",
        _validation_reviewed_app_count(summary) if _validation_app_matrix(summary) else None,
    )
    passed_apps = _summary_app_count(
        summary,
        "validation_passed_apps",
        len(passed_app_ids) if _validation_app_matrix(summary) else None,
    )
    failed_apps = _summary_app_count(
        summary,
        "validation_failed_apps",
        len(failed_app_ids) if _validation_app_matrix(summary) else None,
    )
    pending_apps = _summary_app_count(
        summary,
        "validation_pending_apps",
        len(pending_app_ids) if _validation_app_matrix(summary) else None,
    )
    skipped_apps = _summary_app_count(
        summary,
        "validation_skipped_apps",
        len(skipped_app_ids) if _validation_app_matrix(summary) else None,
    )
    demo_fps = _summary_float(summary, "validation_demo_fps")
    demo_duration = _summary_float(summary, "validation_demo_duration")
    benchmark_matrix_lines = _benchmark_matrix_profile_lines(summary)
    benchmark_profile_names = _benchmark_profile_names(summary)
    benchmark_matrix_complete = _benchmark_matrix_complete_label(summary)
    sync_ipc_gate_prerequisites = _sync_ipc_gate_prerequisites(summary)
    effective_device_prefix = summary.get("effective_device_prefix")
    device_name_alignment = {
        "demo_camera_name_matches_effective_prefix": _matches_expected_name(
            effective_device_prefix,
            summary.get("validation_demo_camera_name"),
        ),
        "validation_device_prefix_matches_effective_prefix": _matches_expected_name(
            effective_device_prefix,
            summary.get("validation_device_prefix"),
        ),
        "validation_install_device_prefix_matches_effective_prefix": _matches_expected_name(
            effective_device_prefix,
            summary.get("validation_install_device_prefix"),
        ),
        "install_session_device_prefix_matches_effective_prefix": _matches_expected_name(
            effective_device_prefix,
            summary.get("install_session_device_prefix"),
        ),
        "list_devices_binary_check_prefix_matches_effective_prefix": _matches_expected_name(
            effective_device_prefix,
            summary.get("list_devices_binary_check_device_prefix"),
        ),
    }

    lines = [
        "# AKVC macOS Validation Session Summary",
        "",
        f"- Manifest: `{manifest_path}`",
        f"- Artifact check passed: `{_bool_label(summary.get('artifact_check_passed'))}`",
        f"- Acceptance ready: `{_bool_label(summary.get('acceptance_ready'))}`",
        f"- Manual app validation ready: `{_bool_label(summary.get('manual_app_validation_ready'))}`",
        f"- Acceptance contract passed: `{_bool_label(summary.get('acceptance_contract_passed'))}`",
        f"- Effective start ready: `{_bool_label(summary.get('effective_start_ready'))}`",
        f"- Effective start blocker: `{summary.get('effective_start_blocker_code') or '-'}`",
        f"- Effective devices: `{_stringify_list(summary.get('effective_devices'))}`",
        f"- Effective all devices: `{_stringify_list(summary.get('effective_all_devices'))}`",
        f"- Effective device prefix: `{effective_device_prefix or '-'}`",
        f"- Effective shared memory: `{summary.get('effective_shared_memory_name') or '-'}`",
        f"- Effective mach service: `{summary.get('effective_mach_service_name') or '-'}`",
        f"- Effective IPC transport: `{summary.get('effective_ipc_transport') or '-'}`",
        f"- Effective formats: `{_stringify_list(summary.get('effective_supported_formats'))}`",
        f"- Effective frame rates: `{_stringify_list(summary.get('effective_supported_frame_rates'))}`",
        "",
        "## Device Name Cohesion",
        "",
        f"- Demo camera name matches effective prefix: `{_bool_label(device_name_alignment['demo_camera_name_matches_effective_prefix'])}`",
        f"- Validation device prefix matches effective prefix: `{_bool_label(device_name_alignment['validation_device_prefix_matches_effective_prefix'])}`",
        f"- Install snapshot device prefix matches effective prefix: `{_bool_label(device_name_alignment['validation_install_device_prefix_matches_effective_prefix'])}`",
        f"- Install session device prefix matches effective prefix: `{_bool_label(device_name_alignment['install_session_device_prefix_matches_effective_prefix'])}`",
        f"- List-devices binary-check prefix matches effective prefix: `{_bool_label(device_name_alignment['list_devices_binary_check_prefix_matches_effective_prefix'])}`",
        "",
        "## Validation Status",
        "",
        f"- Start ready: `{_bool_label(summary.get('validation_status_start_ready'))}`",
        f"- Start blocker: `{summary.get('validation_status_start_blocker_code') or '-'}`",
        f"- Devices: `{_stringify_list(summary.get('validation_devices'))}`",
        f"- All devices: `{_stringify_list(summary.get('validation_all_devices'))}`",
        f"- Device prefix: `{summary.get('validation_device_prefix') or '-'}`",
        f"- Shared memory: `{summary.get('validation_shared_memory_name') or '-'}`",
        f"- Mach service: `{summary.get('validation_mach_service_name') or '-'}`",
        f"- IPC transport: `{summary.get('validation_ipc_transport') or '-'}`",
        f"- Formats: `{_stringify_list(summary.get('validation_supported_formats'))}`",
        f"- Frame rates: `{_stringify_list(summary.get('validation_supported_frame_rates'))}`",
        "",
        "## Installation Snapshot",
        "",
        f"- Present: `{_bool_label(summary.get('validation_install_present'))}`",
        f"- Success: `{_bool_label(summary.get('validation_install_success'))}`",
        f"- Phase: `{summary.get('validation_install_phase') or '-'}`",
        f"- Start ready: `{_bool_label(summary.get('validation_install_start_ready'))}`",
        f"- Start blocker: `{summary.get('validation_install_start_blocker_code') or '-'}`",
        f"- Status devices: `{_stringify_list(summary.get('validation_install_status_devices'))}`",
        f"- Status all devices: `{_stringify_list(summary.get('validation_install_status_all_devices'))}`",
        f"- Device prefix: `{summary.get('validation_install_device_prefix') or '-'}`",
        f"- Shared memory: `{summary.get('validation_install_shared_memory_name') or '-'}`",
        f"- Mach service: `{summary.get('validation_install_mach_service_name') or '-'}`",
        f"- IPC transport: `{summary.get('validation_install_ipc_transport') or '-'}`",
        f"- Formats: `{_stringify_list(summary.get('validation_install_supported_formats'))}`",
        f"- Frame rates: `{_stringify_list(summary.get('validation_install_supported_frame_rates'))}`",
        f"- IPC probe present: `{_bool_label(summary.get('validation_install_ipc_probe_present'))}`",
        f"- IPC ready: `{_bool_label(summary.get('validation_install_ipc_ready'))}`",
        f"- IPC environment blocked: `{_bool_label(summary.get('validation_install_ipc_environment_blocked'))}`",
        f"- IPC direct open errno: `{summary.get('validation_install_ipc_direct_open_errno') if summary.get('validation_install_ipc_direct_open_errno') is not None else '-'}`",
        "",
        "## Install Session",
        "",
        f"- Session present: `{_bool_label(summary.get('install_session_present'))}`",
        f"- Session success: `{_bool_label(summary.get('install_session_success'))}`",
        f"- Session start ready: `{_bool_label(summary.get('install_session_start_ready'))}`",
        f"- Session start blocker: `{summary.get('install_session_start_blocker_code') or '-'}`",
        f"- Session devices: `{_stringify_list(summary.get('install_session_devices'))}`",
        f"- Session all devices: `{_stringify_list(summary.get('install_session_all_devices'))}`",
        f"- Session device prefix: `{summary.get('install_session_device_prefix') or '-'}`",
        f"- Session shared memory: `{summary.get('install_session_shared_memory_name') or '-'}`",
        f"- Session mach service: `{summary.get('install_session_mach_service_name') or '-'}`",
        f"- Session IPC transport: `{summary.get('install_session_ipc_transport') or '-'}`",
        f"- Session IPC probe present: `{_bool_label(summary.get('install_session_ipc_probe_present'))}`",
        f"- Session IPC ready: `{_bool_label(summary.get('install_session_ipc_ready'))}`",
        f"- Session IPC environment blocked: `{_bool_label(summary.get('install_session_ipc_environment_blocked'))}`",
        f"- Session IPC direct open errno: `{summary.get('install_session_ipc_direct_open_errno') if summary.get('install_session_ipc_direct_open_errno') is not None else '-'}`",
        f"- Session host signature: `{summary.get('install_session_host_signature') or '-'}`",
        f"- Session host team id: `{summary.get('install_session_host_team_identifier') or '-'}`",
        f"- Session host Gatekeeper allowed: `{_bool_label(summary.get('install_session_host_gatekeeper_allowed'))}`",
        f"- Session host notarization missing: `{_bool_label(summary.get('install_session_host_notarization_missing'))}`",
        f"- Session install command notarization missing: `{_bool_label(summary.get('install_session_install_command_notarization_missing'))}`",
        f"- Session system extension registered: `{_bool_label(summary.get('install_session_system_extension_registered'))}`",
        f"- Session host Gatekeeper summary: `{summary.get('install_session_host_gatekeeper_summary') or '-'}`",
        f"- Session host distribution summary: `{summary.get('install_session_host_distribution_summary') or '-'}`",
        f"- Session formats: `{_stringify_list(summary.get('install_session_supported_formats'))}`",
        f"- Session frame rates: `{_stringify_list(summary.get('install_session_supported_frame_rates'))}`",
        "",
        "## List-Devices Binary Check",
        "",
        f"- Present: `{_bool_label(summary.get('list_devices_binary_check_present'))}`",
        f"- Passed: `{_bool_label(summary.get('list_devices_binary_check_passed'))}`",
        f"- Device prefix: `{summary.get('list_devices_binary_check_device_prefix') or '-'}`",
        f"- Filtered devices: `{summary.get('list_devices_binary_check_filtered_device_count') if summary.get('list_devices_binary_check_filtered_device_count') is not None else '-'}`",
        f"- Total devices: `{summary.get('list_devices_binary_check_total_device_count') if summary.get('list_devices_binary_check_total_device_count') is not None else '-'}`",
        f"- Override no-match OK: `{_bool_label(summary.get('list_devices_binary_check_override_no_match_ok'))}`",
        "",
        "## Runtime Command Tools",
        "",
        f"- All tools exist: `{_bool_label(summary.get('release_command_tools_exist'))}`",
        f"- All tools signed: `{_bool_label(summary.get('release_command_tools_signed'))}`",
        f"- All tools universal2 ready: `{_bool_label(summary.get('release_command_tools_universal2_ready'))}`",
        f"- App signed: `{_bool_label(summary.get('release_app_signed'))}`",
        f"- App Gatekeeper accepted: `{_bool_label(summary.get('release_app_gatekeeper_accepted'))}`",
        f"- App stapled: `{_bool_label(summary.get('release_app_stapled'))}`",
        f"- Extension signed: `{_bool_label(summary.get('release_extension_signed'))}`",
        f"- PKG signed: `{_bool_label(summary.get('release_pkg_signed'))}`",
        f"- PKG Gatekeeper accepted: `{_bool_label(summary.get('release_pkg_gatekeeper_accepted'))}`",
        f"- PKG stapled: `{_bool_label(summary.get('release_pkg_stapled'))}`",
        f"- PKG payload AppleDouble clean: `{_bool_label(summary.get('release_pkg_payload_appledouble_clean'))}`",
        "",
        "## Runtime Asset Provenance",
        "",
        f"- Host bundle configured: `{_bool_label(summary.get('runtime_host_bundle_configured'))}`",
        f"- Host executable configured: `{_bool_label(summary.get('runtime_host_executable_configured'))}`",
        f"- Extension bundle derived: `{_bool_label(summary.get('runtime_extension_bundle_derived'))}`",
        f"- Package install command present: `{_bool_label(summary.get('runtime_package_install_command_present'))}`",
        f"- Auto package install enabled: `{_bool_label(summary.get('runtime_auto_install_package'))}`",
        f"- Status tool path: `{summary.get('runtime_status_tool_path') or '-'}`",
        f"- Install tool path: `{summary.get('runtime_install_tool_path') or '-'}`",
        f"- Devices tool path: `{summary.get('runtime_devices_tool_path') or '-'}`",
        f"- Uninstall tool path: `{summary.get('runtime_uninstall_tool_path') or '-'}`",
        f"- Sync IPC tool path: `{summary.get('runtime_sync_ipc_tool_path') or '-'}`",
        f"- PKG path: `{summary.get('runtime_pkg_path') or '-'}`",
        f"- Container app bundle path: `{summary.get('runtime_host_bundle_path') or '-'}`",
        f"- Container app executable path: `{summary.get('runtime_host_executable_path') or '-'}`",
        f"- Extension bundle path: `{summary.get('runtime_extension_bundle_path') or '-'}`",
        f"- Package install command: `{_stringify_command(summary.get('runtime_package_install_command'))}`",
        f"- Release container app bundle path: `{summary.get('release_app_bundle_path') or '-'}`",
        f"- Release extension bundle path: `{summary.get('release_extension_bundle_path') or '-'}`",
        f"- Release sync IPC tool path: `{summary.get('release_sync_ipc_tool_path') or '-'}`",
        f"- Release PKG path: `{summary.get('release_pkg_path') or '-'}`",
        f"- Runtime/release product identity consistent: `{_bool_label(summary.get('runtime_release_product_identity_consistent'))}`",
        f"- Runtime/release product path equal: `{_bool_label(summary.get('runtime_release_product_path_equal'))}`",
        "",
        "## Runtime Topology",
        "",
        f"- Topology kind: `{summary.get('runtime_topology_kind') or '-'}`",
        f"- Frame path: `{summary.get('runtime_frame_path') or '-'}`",
        f"- Host role: `{summary.get('runtime_host_role') or '-'}`",
        f"- Host in frame hot path: `{_bool_label(summary.get('runtime_host_in_frame_hot_path'))}`",
        f"- Dedicated host daemon required: `{_bool_label(summary.get('runtime_dedicated_host_daemon_required'))}`",
        f"- Container app configured: `{_bool_label(summary.get('runtime_container_app_configured'))}`",
        f"- Data plane: `{summary.get('runtime_data_plane') or '-'}`",
        f"- Control plane: `{summary.get('runtime_control_plane') or '-'}`",
        "",
        "## Sync IPC Tool",
        "",
        f"- Exists: `{_bool_label(summary.get('release_sync_ipc_tool_exists'))}`",
        f"- Signed: `{_bool_label(summary.get('release_sync_ipc_tool_signed'))}`",
        f"- Universal2 ready: `{_bool_label(summary.get('release_sync_ipc_tool_universal2_ready'))}`",
        f"- Runtime sync present: `{_bool_label(summary.get('install_session_sync_ipc_present'))}`",
        f"- Runtime sync supported: `{_bool_label(summary.get('install_session_sync_ipc_supported'))}`",
        f"- Runtime sync success: `{_bool_label(summary.get('install_session_sync_ipc_success'))}`",
        f"- Runtime sync phase: `{summary.get('install_session_sync_ipc_phase') or '-'}`",
        f"- Runtime sync shared memory: `{summary.get('install_session_sync_ipc_shared_memory_name') or '-'}`",
        f"- Runtime sync transport: `{summary.get('install_session_sync_ipc_transport') or '-'}`",
        f"- Runtime sync returncode: `{summary.get('install_session_sync_ipc_returncode') if summary.get('install_session_sync_ipc_returncode') is not None else '-'}`",
        f"- Control-plane prerequisites satisfied: `{_bool_label(sync_ipc_gate_prerequisites)}`",
        "",
        "## Python Entrypoints",
        "",
        f"- Present: `{_bool_label(summary.get('entrypoints_contract_present'))}`",
        f"- Passed: `{_bool_label(summary.get('entrypoints_contract_passed'))}`",
        f"- Surface complete: `{_bool_label(summary.get('entrypoints_contract_surface_complete'))}`",
        f"- Demo case complete: `{_bool_label(summary.get('entrypoints_contract_demo_case_complete'))}`",
        f"- CLI case complete: `{_bool_label(summary.get('entrypoints_contract_cli_case_complete'))}`",
        f"- Desktop case complete: `{_bool_label(summary.get('entrypoints_contract_desktop_case_complete'))}`",
        f"- SDK contract present: `{_bool_label(summary.get('sdk_contract_present'))}`",
        f"- SDK contract passed: `{_bool_label(summary.get('sdk_contract_passed'))}`",
        f"- SDK constructor shape aligned: `{_bool_label(summary.get('sdk_contract_constructor_shape_aligned'))}`",
        f"- SDK direct sender exports present: `{_bool_label(summary.get('sdk_contract_direct_sender_exports_present'))}`",
        "",
        "## PySide6 Demo",
        "",
        f"- Present: `{_bool_label(summary.get('validation_demo_present'))}`",
        f"- Mode: `{summary.get('validation_demo_mode') or '-'}`",
        f"- Mode supported: `{_bool_label(summary.get('validation_demo_mode_supported'))}`",
        f"- Width: `{summary.get('validation_demo_width') if summary.get('validation_demo_width') is not None else '-'}`",
        f"- Height: `{summary.get('validation_demo_height') if summary.get('validation_demo_height') is not None else '-'}`",
        f"- FPS: `{demo_fps if demo_fps is not None else '-'}`",
        f"- Duration: `{demo_duration if demo_duration is not None else '-'}`",
        f"- Camera name: `{summary.get('validation_demo_camera_name') or '-'}`",
        f"- Consumer count: `{summary.get('validation_demo_consumer_count') if summary.get('validation_demo_consumer_count') is not None else '-'}`",
        f"- Video path: `{summary.get('validation_demo_video_path') or '-'}`",
        f"- Frame source: `{summary.get('validation_demo_frame_source_kind') or '-'}`",
        f"- Python entrypoint: `{summary.get('validation_demo_python_entrypoint_kind') or '-'}`",
        f"- SDK streamer factory used: `{_bool_label(summary.get('validation_demo_sdk_streamer_factory_used'))}`",
        f"- SDK latest-provider factory used: `{_bool_label(summary.get('validation_demo_sdk_latest_provider_factory_used'))}`",
        f"- SDK direct push used: `{_bool_label(summary.get('validation_demo_sdk_direct_push_used'))}`",
        "",
        "## Direct Push Evidence",
        "",
        f"- Session report present: `{_bool_label(summary.get('direct_push_demo_present'))}`",
        f"- Session report mode: `{summary.get('direct_push_demo_mode') or '-'}`",
        f"- Session report entrypoint: `{summary.get('direct_push_demo_python_entrypoint_kind') or '-'}`",
        f"- Session report direct push used: `{_bool_label(summary.get('direct_push_demo_sdk_direct_push_used'))}`",
        f"- Session report backend: `{summary.get('direct_push_demo_backend_name') or '-'}`",
        f"- Session report using direct sender: `{_bool_label(summary.get('direct_push_demo_using_direct_sender'))}`",
        f"- Session report direct sender attempted: `{_bool_label(summary.get('direct_push_demo_direct_sender_attempted'))}`",
        f"- Session report direct sender state: `{summary.get('direct_push_demo_direct_sender_state') or '-'}`",
        f"- Session report topology kind: `{summary.get('direct_push_demo_runtime_topology_kind') or '-'}`",
        f"- Session report host in frame hot path: `{_bool_label(summary.get('direct_push_demo_runtime_host_in_frame_hot_path'))}`",
        f"- Session report helper hot path used: `{_bool_label(summary.get('direct_push_demo_helper_hot_path_used'))}`",
        f"- Session report shared-memory fallback used: `{_bool_label(summary.get('direct_push_demo_shared_memory_fallback_used'))}`",
        f"- Session report data plane: `{summary.get('direct_push_demo_runtime_data_plane') or '-'}`",
        f"- Session report control plane: `{summary.get('direct_push_demo_runtime_control_plane') or '-'}`",
        f"- Session report direct sender library: `{summary.get('direct_push_demo_direct_sender_library_path') or '-'}`",
        f"- Session report direct sender error: `{summary.get('direct_push_demo_direct_sender_last_error') or '-'}`",
        f"- Session report runtime snapshot present: `{_bool_label(summary.get('direct_push_demo_runtime_snapshot_present'))}`",
        f"- Session report runtime snapshot started: `{_bool_label(summary.get('direct_push_demo_runtime_snapshot_started'))}`",
        f"- Session report runtime snapshot shared memory: `{summary.get('direct_push_demo_runtime_snapshot_shared_memory_name') or '-'}`",
        f"- Session report runtime snapshot last frame format: `{summary.get('direct_push_demo_runtime_snapshot_last_frame_format_name') or '-'}`",
        f"- Session report requested frames: `{summary.get('direct_push_demo_requested_frames') if summary.get('direct_push_demo_requested_frames') is not None else '-'}`",
        f"- Session report frames sent: `{summary.get('direct_push_demo_frames_sent') if summary.get('direct_push_demo_frames_sent') is not None else '-'}`",
        f"- Smoke direct-push present: `{_bool_label(summary.get('smoke_direct_push_demo_present'))}`",
        f"- Smoke direct-push attempted: `{_bool_label(summary.get('smoke_direct_push_demo_attempted'))}`",
        f"- Smoke direct-push skipped: `{_bool_label(summary.get('smoke_direct_push_demo_skipped'))}`",
        f"- Smoke direct-push skip reason: `{summary.get('smoke_direct_push_demo_skip_reason') or '-'}`",
        f"- Smoke direct-push entrypoint: `{summary.get('smoke_direct_push_demo_python_entrypoint_kind') or '-'}`",
        f"- Smoke direct-push backend: `{summary.get('smoke_direct_push_demo_backend_name') or '-'}`",
        f"- Smoke direct-push using direct sender: `{_bool_label(summary.get('smoke_direct_push_demo_using_direct_sender'))}`",
        f"- Smoke direct-push direct sender attempted: `{_bool_label(summary.get('smoke_direct_push_demo_direct_sender_attempted'))}`",
        f"- Smoke direct-push direct sender state: `{summary.get('smoke_direct_push_demo_direct_sender_state') or '-'}`",
        f"- Smoke direct-push topology kind: `{summary.get('smoke_direct_push_demo_runtime_topology_kind') or '-'}`",
        f"- Smoke direct-push helper hot path used: `{_bool_label(summary.get('smoke_direct_push_demo_helper_hot_path_used'))}`",
        f"- Smoke direct-push shared-memory fallback used: `{_bool_label(summary.get('smoke_direct_push_demo_shared_memory_fallback_used'))}`",
        f"- Smoke direct-push data plane: `{summary.get('smoke_direct_push_demo_runtime_data_plane') or '-'}`",
        f"- Smoke direct-push control plane: `{summary.get('smoke_direct_push_demo_runtime_control_plane') or '-'}`",
        f"- Smoke direct-push direct sender library: `{summary.get('smoke_direct_push_demo_direct_sender_library_path') or '-'}`",
        f"- Smoke direct-push direct sender error: `{summary.get('smoke_direct_push_demo_direct_sender_last_error') or '-'}`",
        f"- Smoke direct-push runtime snapshot present: `{_bool_label(summary.get('smoke_direct_push_demo_runtime_snapshot_present'))}`",
        f"- Smoke direct-push runtime snapshot started: `{_bool_label(summary.get('smoke_direct_push_demo_runtime_snapshot_started'))}`",
        f"- Smoke direct-push runtime snapshot shared memory: `{summary.get('smoke_direct_push_demo_runtime_snapshot_shared_memory_name') or '-'}`",
        f"- Smoke direct-push runtime snapshot last frame format: `{summary.get('smoke_direct_push_demo_runtime_snapshot_last_frame_format_name') or '-'}`",
        f"- Smoke direct-push requested frames: `{summary.get('smoke_direct_push_demo_requested_frames') if summary.get('smoke_direct_push_demo_requested_frames') is not None else '-'}`",
        f"- Smoke direct-push frames sent: `{summary.get('smoke_direct_push_demo_frames_sent') if summary.get('smoke_direct_push_demo_frames_sent') is not None else '-'}`",
        f"- Install-session direct-push present: `{_bool_label(summary.get('install_session_direct_push_demo_present'))}`",
        f"- Install-session direct-push attempted: `{_bool_label(summary.get('install_session_direct_push_demo_attempted'))}`",
        f"- Install-session direct-push skipped: `{_bool_label(summary.get('install_session_direct_push_demo_skipped'))}`",
        f"- Install-session direct-push skip reason: `{summary.get('install_session_direct_push_demo_skip_reason') or '-'}`",
        f"- Install-session direct-push entrypoint: `{summary.get('install_session_direct_push_demo_python_entrypoint_kind') or '-'}`",
        f"- Install-session direct-push backend: `{summary.get('install_session_direct_push_demo_backend_name') or '-'}`",
        f"- Install-session direct-push using direct sender: `{_bool_label(summary.get('install_session_direct_push_demo_using_direct_sender'))}`",
        f"- Install-session direct-push direct sender attempted: `{_bool_label(summary.get('install_session_direct_push_demo_direct_sender_attempted'))}`",
        f"- Install-session direct-push direct sender state: `{summary.get('install_session_direct_push_demo_direct_sender_state') or '-'}`",
        f"- Install-session direct-push topology kind: `{summary.get('install_session_direct_push_demo_runtime_topology_kind') or '-'}`",
        f"- Install-session direct-push helper hot path used: `{_bool_label(summary.get('install_session_direct_push_demo_helper_hot_path_used'))}`",
        f"- Install-session direct-push shared-memory fallback used: `{_bool_label(summary.get('install_session_direct_push_demo_shared_memory_fallback_used'))}`",
        f"- Install-session direct-push data plane: `{summary.get('install_session_direct_push_demo_runtime_data_plane') or '-'}`",
        f"- Install-session direct-push control plane: `{summary.get('install_session_direct_push_demo_runtime_control_plane') or '-'}`",
        f"- Install-session direct-push direct sender library: `{summary.get('install_session_direct_push_demo_direct_sender_library_path') or '-'}`",
        f"- Install-session direct-push direct sender error: `{summary.get('install_session_direct_push_demo_direct_sender_last_error') or '-'}`",
        f"- Install-session direct-push runtime snapshot present: `{_bool_label(summary.get('install_session_direct_push_demo_runtime_snapshot_present'))}`",
        f"- Install-session direct-push runtime snapshot started: `{_bool_label(summary.get('install_session_direct_push_demo_runtime_snapshot_started'))}`",
        f"- Install-session direct-push runtime snapshot shared memory: `{summary.get('install_session_direct_push_demo_runtime_snapshot_shared_memory_name') or '-'}`",
        f"- Install-session direct-push runtime snapshot last frame format: `{summary.get('install_session_direct_push_demo_runtime_snapshot_last_frame_format_name') or '-'}`",
        f"- Install-session direct-push requested frames: `{summary.get('install_session_direct_push_demo_requested_frames') if summary.get('install_session_direct_push_demo_requested_frames') is not None else '-'}`",
        f"- Install-session direct-push frames sent: `{summary.get('install_session_direct_push_demo_frames_sent') if summary.get('install_session_direct_push_demo_frames_sent') is not None else '-'}`",
        "",
        "## Direct Sender Object Evidence",
        "",
        f"- Session object report present: `{_bool_label(summary.get('direct_sender_object_demo_present'))}`",
        f"- Session object report mode: `{summary.get('direct_sender_object_demo_mode') or '-'}`",
        f"- Session object report entrypoint: `{summary.get('direct_sender_object_demo_python_entrypoint_kind') or '-'}`",
        f"- Session object report backend: `{summary.get('direct_sender_object_demo_backend_name') or '-'}`",
        f"- Session object report using direct sender: `{_bool_label(summary.get('direct_sender_object_demo_using_direct_sender'))}`",
        f"- Session object report direct sender state: `{summary.get('direct_sender_object_demo_direct_sender_state') or '-'}`",
        f"- Session object report topology kind: `{summary.get('direct_sender_object_demo_runtime_topology_kind') or '-'}`",
        f"- Session object report helper hot path used: `{_bool_label(summary.get('direct_sender_object_demo_helper_hot_path_used'))}`",
        f"- Session object report shared-memory fallback used: `{_bool_label(summary.get('direct_sender_object_demo_shared_memory_fallback_used'))}`",
        f"- Session object report data plane: `{summary.get('direct_sender_object_demo_runtime_data_plane') or '-'}`",
        f"- Session object report control plane: `{summary.get('direct_sender_object_demo_runtime_control_plane') or '-'}`",
        f"- Session object report direct sender library: `{summary.get('direct_sender_object_demo_direct_sender_library_path') or '-'}`",
        f"- Session object report requested frames: `{summary.get('direct_sender_object_demo_requested_frames') if summary.get('direct_sender_object_demo_requested_frames') is not None else '-'}`",
        f"- Session object report frames sent: `{summary.get('direct_sender_object_demo_frames_sent') if summary.get('direct_sender_object_demo_frames_sent') is not None else '-'}`",
        f"- Smoke object-demo present: `{_bool_label(summary.get('smoke_direct_sender_object_demo_present'))}`",
        f"- Smoke object-demo attempted: `{_bool_label(summary.get('smoke_direct_sender_object_demo_attempted'))}`",
        f"- Smoke object-demo skipped: `{_bool_label(summary.get('smoke_direct_sender_object_demo_skipped'))}`",
        f"- Smoke object-demo skip reason: `{summary.get('smoke_direct_sender_object_demo_skip_reason') or '-'}`",
        f"- Smoke object-demo backend: `{summary.get('smoke_direct_sender_object_demo_backend_name') or '-'}`",
        f"- Smoke object-demo using direct sender: `{_bool_label(summary.get('smoke_direct_sender_object_demo_using_direct_sender'))}`",
        f"- Smoke object-demo direct sender state: `{summary.get('smoke_direct_sender_object_demo_direct_sender_state') or '-'}`",
        f"- Smoke object-demo topology kind: `{summary.get('smoke_direct_sender_object_demo_runtime_topology_kind') or '-'}`",
        f"- Smoke object-demo helper hot path used: `{_bool_label(summary.get('smoke_direct_sender_object_demo_helper_hot_path_used'))}`",
        f"- Smoke object-demo shared-memory fallback used: `{_bool_label(summary.get('smoke_direct_sender_object_demo_shared_memory_fallback_used'))}`",
        f"- Smoke object-demo direct sender library: `{summary.get('smoke_direct_sender_object_demo_direct_sender_library_path') or '-'}`",
        f"- Smoke object-demo requested frames: `{summary.get('smoke_direct_sender_object_demo_requested_frames') if summary.get('smoke_direct_sender_object_demo_requested_frames') is not None else '-'}`",
        f"- Smoke object-demo frames sent: `{summary.get('smoke_direct_sender_object_demo_frames_sent') if summary.get('smoke_direct_sender_object_demo_frames_sent') is not None else '-'}`",
        f"- Install-session object-demo present: `{_bool_label(summary.get('install_session_direct_sender_object_demo_present'))}`",
        f"- Install-session object-demo attempted: `{_bool_label(summary.get('install_session_direct_sender_object_demo_attempted'))}`",
        f"- Install-session object-demo skipped: `{_bool_label(summary.get('install_session_direct_sender_object_demo_skipped'))}`",
        f"- Install-session object-demo skip reason: `{summary.get('install_session_direct_sender_object_demo_skip_reason') or '-'}`",
        f"- Install-session object-demo backend: `{summary.get('install_session_direct_sender_object_demo_backend_name') or '-'}`",
        f"- Install-session object-demo using direct sender: `{_bool_label(summary.get('install_session_direct_sender_object_demo_using_direct_sender'))}`",
        f"- Install-session object-demo direct sender state: `{summary.get('install_session_direct_sender_object_demo_direct_sender_state') or '-'}`",
        f"- Install-session object-demo topology kind: `{summary.get('install_session_direct_sender_object_demo_runtime_topology_kind') or '-'}`",
        f"- Install-session object-demo helper hot path used: `{_bool_label(summary.get('install_session_direct_sender_object_demo_helper_hot_path_used'))}`",
        f"- Install-session object-demo shared-memory fallback used: `{_bool_label(summary.get('install_session_direct_sender_object_demo_shared_memory_fallback_used'))}`",
        f"- Install-session object-demo direct sender library: `{summary.get('install_session_direct_sender_object_demo_direct_sender_library_path') or '-'}`",
        f"- Install-session object-demo requested frames: `{summary.get('install_session_direct_sender_object_demo_requested_frames') if summary.get('install_session_direct_sender_object_demo_requested_frames') is not None else '-'}`",
        f"- Install-session object-demo frames sent: `{summary.get('install_session_direct_sender_object_demo_frames_sent') if summary.get('install_session_direct_sender_object_demo_frames_sent') is not None else '-'}`",
        "",
    ]

    if benchmark_matrix_lines:
        lines.extend([
            "## Benchmark Matrix",
            "",
            f"- Kind: `{summary.get('validation_benchmark_kind') or '-'}`",
            f"- Profiles covered: `{_stringify_list(benchmark_profile_names)}`",
            f"- Required profile set complete: `{benchmark_matrix_complete}`",
            f"- Matrix complete gate: `{_acceptance_gate_status(summary, acceptance_criteria, 'benchmark_matrix_complete')}`",
            f"- FPS targets met: `{_acceptance_gate_status(summary, acceptance_criteria, 'benchmark_fps_targets_met')}`",
            f"- 1080p60 CPU target met: `{_acceptance_gate_status(summary, acceptance_criteria, 'benchmark_1080p60_cpu_target_met')}`",
            "",
            *benchmark_matrix_lines,
            "",
        ])

    lines.extend([
        "## Target Apps",
        "",
        f"- Validated apps: `{validated_apps if validated_apps is not None else '-'}`",
        f"- Passed apps: `{passed_apps if passed_apps is not None else '-'}`",
        f"- Failed apps: `{failed_apps if failed_apps is not None else '-'}`",
        f"- Pending apps: `{pending_apps if pending_apps is not None else '-'}`",
        f"- Skipped apps: `{skipped_apps if skipped_apps is not None else '-'}`",
        f"- Manual validation ready: `{_bool_label(summary.get('validation_manual_validation_ready'))}`",
        f"- Review complete: `{_bool_label(summary.get('validation_manual_validation_complete'))}`",
        f"- All target apps passed manually: `{_bool_label(summary.get('validation_manual_validation_all_passed'))}`",
        f"- Passed: `{_stringify_list(passed_app_ids)}`",
        f"- Failed: `{_stringify_list(failed_app_ids)}`",
        f"- Pending: `{_stringify_list(pending_app_ids)}`",
        f"- Skipped: `{_stringify_list(skipped_app_ids)}`",
        f"- Reviewed: `{_stringify_list(reviewed_app_ids)}`",
        f"- Unreviewed: `{_stringify_list(unreviewed_app_ids)}`",
        f"- Observed target ids: `{_stringify_list(observed_target_app_ids)}`",
        f"- Target id set complete: `{_bool_label(target_app_ids_complete)}`",
        f"- Missing target ids: `{_stringify_list(missing_target_app_ids)}`",
        f"- Unexpected target ids: `{_stringify_list(unexpected_target_app_ids)}`",
        "",
        "## Target App Details",
        "",
        *app_detail_lines,
        "",
        "## Manual App Validation Readiness",
        "",
        f"- Ready: `{_bool_label(summary.get('manual_app_validation_ready'))}`",
        f"- Failed prerequisites: `{_stringify_manual_app_validation_gates(summary.get('manual_app_validation_failed_criteria'))}`",
        f"- Unknown prerequisites: `{_stringify_manual_app_validation_gates(summary.get('manual_app_validation_unknown_criteria'))}`",
        f"- Combined blockers: `{_stringify_manual_app_validation_gates(summary.get('manual_app_validation_blockers'))}`",
        "",
        "## Acceptance Gates",
        "",
        f"- macOS 13+ declared: `{_acceptance_gate_status(summary, acceptance_criteria, 'macos_13_plus_declared')}`",
        f"- Universal2 ready: `{_acceptance_gate_status(summary, acceptance_criteria, 'universal2_ready')}`",
        f"- Release packaging ready: `{_acceptance_gate_status(summary, acceptance_criteria, 'release_packaging_ready')}`",
        f"- PySide6 path exercised: `{_acceptance_gate_status(summary, acceptance_criteria, 'pyside6_path_exercised')}`",
        f"- Python entrypoints consistent: `{_acceptance_gate_status(summary, acceptance_criteria, 'python_entrypoints_consistent')}`",
        f"- Target apps all passed: `{_acceptance_gate_status(summary, acceptance_criteria, 'target_apps_all_passed')}`",
        f"- System camera device visible: `{_acceptance_gate_status(summary, acceptance_criteria, 'system_camera_device_visible')}`",
        f"- Benchmark matrix complete: `{_acceptance_gate_status(summary, acceptance_criteria, 'benchmark_matrix_complete')}`",
        f"- Benchmark FPS targets met: `{_acceptance_gate_status(summary, acceptance_criteria, 'benchmark_fps_targets_met')}`",
        f"- Auto install ready: `{_acceptance_gate_status(summary, acceptance_criteria, 'auto_install_ready')}`",
        f"- Signing evidence ready: `{_acceptance_gate_status(summary, acceptance_criteria, 'signing_evidence_ready')}`",
        f"- Notarization tooling ready: `{_acceptance_gate_status(summary, acceptance_criteria, 'notarization_tooling_ready')}`",
        f"- 1080p60 CPU target met: `{_acceptance_gate_status(summary, acceptance_criteria, 'benchmark_1080p60_cpu_target_met')}`",
        f"- Runtime assets packaged: `{_acceptance_gate_status(summary, acceptance_criteria, 'runtime_assets_packaged')}`",
        f"- Sync IPC control plane ready: `{_acceptance_gate_status(summary, acceptance_criteria, 'sync_ipc_control_plane_ready')}`",
        "",
        "## Acceptance",
        "",
        f"- Failed criteria: `{_stringify_list(summary.get('acceptance_failed_criteria'))}`",
        f"- Unknown criteria: `{_stringify_list(summary.get('acceptance_unknown_criteria'))}`",
        f"- Acceptance failed count: `{acceptance_summary.get('failed_count', summary.get('acceptance_failed_count', '-'))}`",
        f"- Acceptance unknown count: `{acceptance_summary.get('unknown_count', summary.get('acceptance_unknown_count', '-'))}`",
        "",
        "## Acceptance Contract",
        "",
        f"- Present: `{_bool_label(summary.get('acceptance_contract_present'))}`",
        f"- Passed: `{_bool_label(summary.get('acceptance_contract_passed'))}`",
        "",
        "## Artifacts",
        "",
    ])

    for key in (
        "validation_report",
        "artifact_check_report",
        "acceptance_report",
        "acceptance_contract_report",
        "list_devices_binary_check_report",
        "entrypoints_contract_report",
        "sdk_contract_report",
        "manual_template",
    ):
        if key in artifacts:
            lines.append(f"- {key}: `{artifacts[key]}`")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS validation-session Markdown summary helper"
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"validation-session manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    rendered = render_summary(manifest_path)
    print(rendered, end="")
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
