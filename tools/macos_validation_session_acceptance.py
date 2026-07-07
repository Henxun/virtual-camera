# SPDX-License-Identifier: Apache-2.0
"""Acceptance summary helper for macOS validation-session artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "build" / "macos" / "session" / "session-manifest.json"
EXPECTED_FORMATS = {
    "1280x720@30/60 NV12",
    "1920x1080@30/60 NV12",
    "3840x2160@30/60 NV12",
}
EXPECTED_FRAME_RATES = {30, 60}
EXPECTED_APP_IDS = [
    "facetime",
    "google_meet",
    "obs",
    "quicktime",
    "teams",
    "zoom",
]
EXPECTED_APP_COUNT = 6
ALLOWED_DEMO_MODES = {
    "numpy-direct",
    "provider",
    "latest-provider",
    "image",
    "pixmap",
    "widget",
    "screen",
    "video-file",
}
DEMO_MODE_TO_FRAME_SOURCE_KIND = {
    "numpy-direct": "numpy_direct",
    "provider": "callable_provider",
    "latest-provider": "latest_frame_provider",
    "image": "qimage_direct",
    "pixmap": "qpixmap_direct",
    "widget": "widget_grab",
    "screen": "screen_grab",
    "video-file": "opencv_video_file",
}
EXPECTED_BENCHMARK_PROFILES = [
    "720p30",
    "720p60",
    "1080p30",
    "1080p60",
    "4k30",
    "4k60",
]
MANUAL_APP_VALIDATION_GATE_NAMES = (
    "macos_13_plus_declared",
    "universal2_ready",
    "release_packaging_ready",
    "signing_evidence_ready",
    "notarization_tooling_ready",
    "pyside6_path_exercised",
    "python_direct_runtime_ready",
    "python_entrypoints_consistent",
    "system_camera_device_visible",
    "auto_install_ready",
    "artifact_replay_passed",
    "runtime_assets_packaged",
)
DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES = (
    "direct_push_demo",
    "smoke_direct_push_demo",
    "install_session_direct_push_demo",
)


def _app_matrix_note(
    app_matrix_value: bool | None,
    *,
    exact_id_evidence_present: bool,
    missing_target_app_ids: list[str] | None,
    unexpected_target_app_ids: list[str] | None,
    failed_app_ids: list[str] | None,
    pending_app_ids: list[str] | None,
    skipped_app_ids: list[str] | None,
    unreviewed_app_ids: list[str] | None,
    target_app_missing_evidence_ids: list[str] | None = None,
) -> str | None:
    if app_matrix_value is True:
        return None
    if app_matrix_value is None:
        if not exact_id_evidence_present:
            return "缺少六个目标应用的精确 app id 证据，当前只有计数或不完整摘要，尚不能证明指定应用集合全部通过。"
        gaps: list[str] = []
        missing = [str(item) for item in (missing_target_app_ids or []) if item]
        unexpected = [str(item) for item in (unexpected_target_app_ids or []) if item]
        if missing:
            gaps.append(f"missing={','.join(missing)}")
        if unexpected:
            gaps.append(f"unexpected={','.join(unexpected)}")
        if gaps:
            return "缺少完整指定应用集合证据：" + "; ".join(gaps) + "。"
        return "缺少完整人工应用验收结果，尚不能证明六个目标应用全部通过。"

    gaps: list[str] = []
    missing = [str(item) for item in (missing_target_app_ids or []) if item]
    unexpected = [str(item) for item in (unexpected_target_app_ids or []) if item]
    missing_evidence = [str(item) for item in (target_app_missing_evidence_ids or []) if item]
    if missing:
        gaps.append(f"missing={','.join(missing)}")
    if unexpected:
        gaps.append(f"unexpected={','.join(unexpected)}")
    if missing_evidence:
        gaps.append(f"missing_evidence={','.join(missing_evidence)}")
    for label, values in (
        ("fail", failed_app_ids),
        ("pending", pending_app_ids),
        ("skipped", skipped_app_ids),
        ("unreviewed", unreviewed_app_ids),
    ):
        normalized = [str(item) for item in (values or []) if item]
        if normalized:
            gaps.append(f"{label}={','.join(normalized)}")
    if gaps:
        return (
            "当前会话未证明 Zoom/Teams/Google Meet/OBS/QuickTime/FaceTime 六个目标应用全部通过："
            + "; ".join(gaps)
            + "。"
        )
    return "当前会话未证明 Zoom/Teams/Google Meet/OBS/QuickTime/FaceTime 六个目标应用全部通过。"


def _benchmark_matrix_note(benchmark_acceptance: dict[str, Any] | None) -> str | None:
    if not isinstance(benchmark_acceptance, dict):
        return "缺少完整 benchmark matrix 证据，尚不能证明 720p/1080p/4K 与 30/60fps 六档场景都已覆盖。"

    required_present = benchmark_acceptance.get("required_profiles_present")
    missing = [str(item) for item in (benchmark_acceptance.get("missing_required_profiles") or []) if item]
    unexpected = [str(item) for item in (benchmark_acceptance.get("unexpected_profiles") or []) if item]

    if required_present is True and not missing and not unexpected:
        return None

    gaps: list[str] = []
    if missing:
        gaps.append("missing=" + ",".join(missing))
    if unexpected:
        gaps.append("unexpected=" + ",".join(unexpected))
    if gaps:
        return "当前会话未覆盖完整 benchmark matrix：" + "; ".join(gaps) + "。"
    return "当前会话未覆盖完整 benchmark matrix。"


def _normalize_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return sorted(str(item) for item in value if isinstance(item, str) and item)


def _validation_app_matrix(summary: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    matrix = summary.get("validation_app_matrix")
    if not isinstance(matrix, dict):
        return None
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in matrix.items():
        if isinstance(key, str) and key and isinstance(value, dict):
            item = dict(value)
            item["evidence"] = _normalize_manual_evidence(item.get("evidence"))
            normalized[key] = item
    return normalized or None


def _normalize_manual_evidence(value: Any) -> dict[str, Any]:
    evidence = value if isinstance(value, dict) else {}
    return {
        "device_listed": bool(evidence.get("device_listed", False)),
        "device_selected": bool(evidence.get("device_selected", False)),
        "preview_visible": bool(evidence.get("preview_visible", False)),
        "screenshot": str(evidence.get("screenshot", "")) if evidence.get("screenshot") is not None else "",
    }


def _validation_app_matrix_missing_evidence_ids(
    matrix: dict[str, dict[str, Any]] | None,
) -> list[str] | None:
    if not isinstance(matrix, dict):
        return None
    missing: list[str] = []
    for app_id, item in matrix.items():
        if not isinstance(item, dict) or str(item.get("result")) != "pass":
            continue
        evidence = _normalize_manual_evidence(item.get("evidence"))
        if (
            evidence.get("device_listed") is not True
            or evidence.get("device_selected") is not True
            or evidence.get("preview_visible") is not True
        ):
            missing.append(str(app_id))
    return sorted(missing)


def _validation_app_matrix_ids_with_result(
    matrix: dict[str, dict[str, Any]] | None,
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
    matrix: dict[str, dict[str, Any]] | None,
) -> list[str] | None:
    if not isinstance(matrix, dict):
        return None
    return sorted(
        app_id
        for app_id, item in matrix.items()
        if isinstance(item, dict) and not bool(item.get("reviewed"))
    )


def _direct_runtime_candidate(summary: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    keys = (
        "using_direct_sender",
        "helper_hot_path_used",
        "shared_memory_fallback_used",
        "direct_only",
        "allow_shared_memory_fallback",
        "runtime_host_in_frame_hot_path",
        "runtime_dedicated_host_daemon_required",
        "runtime_data_plane",
        "runtime_control_plane",
        "camera_name",
        "returncode",
        "error",
    )
    candidate = {key: summary.get(f"{prefix}_{key}") for key in keys}
    if not any(value is not None for value in candidate.values()):
        return None
    candidate["source"] = prefix
    candidate["pure_direct_runtime"] = (
        candidate.get("using_direct_sender") is True
        and candidate.get("helper_hot_path_used") is False
        and candidate.get("shared_memory_fallback_used") is False
        and candidate.get("allow_shared_memory_fallback") is not True
        and candidate.get("direct_only") is not False
        and candidate.get("runtime_host_in_frame_hot_path") is not True
        and candidate.get("runtime_dedicated_host_daemon_required") is not True
    )
    return candidate


def _direct_runtime_assessment(summary: dict[str, Any]) -> tuple[bool | None, dict[str, Any]]:
    candidates = [
        candidate
        for prefix in DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES
        if (candidate := _direct_runtime_candidate(summary, prefix)) is not None
    ]
    evidence = {
        "sources_checked": list(DIRECT_PUSH_RUNTIME_SUMMARY_PREFIXES),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    if not candidates:
        return None, evidence
    for candidate in candidates:
        if candidate.get("pure_direct_runtime") is True:
            evidence["selected_source"] = candidate.get("source")
            evidence["selected_candidate"] = candidate
            return True, evidence
    evidence["selected_source"] = candidates[0].get("source")
    evidence["selected_candidate"] = candidates[0]
    return False, evidence


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _artifact_payload(manifest: dict[str, Any], key: str) -> dict[str, Any] | None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    value = artifacts.get(key)
    if not isinstance(value, str) or not value:
        return None
    return _load_json_object(Path(value))


def _criterion(
    name: str,
    *,
    status: str,
    evidence: dict[str, Any] | None = None,
    note: str | None = None,
    critical: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "critical": critical,
        "evidence": evidence or {},
        "note": note,
    }


def _status_from_bool(
    name: str,
    value: bool | None,
    *,
    evidence: dict[str, Any] | None = None,
    unknown_note: str,
    fail_note: str,
    critical: bool = True,
) -> dict[str, Any]:
    if value is True:
        return _criterion(name, status="pass", evidence=evidence, critical=critical)
    if value is False:
        return _criterion(
            name,
            status="fail",
            evidence=evidence,
            note=fail_note,
            critical=critical,
        )
    return _criterion(
        name,
        status="unknown",
        evidence=evidence,
        note=unknown_note,
        critical=critical,
    )


def _preferred_summary_value(
    primary: dict[str, Any],
    primary_key: str,
    fallback: dict[str, Any],
    fallback_key: str,
) -> Any:
    if primary_key in primary:
        return primary.get(primary_key)
    return fallback.get(fallback_key)


def _all_true_or_false_or_none(*values: bool | None) -> bool | None:
    if any(value is False for value in values):
        return False
    if values and all(value is True for value in values):
        return True
    return None


def _any_true_without_false_or_none(*values: bool | None) -> bool | None:
    if any(value is False for value in values):
        return False
    if any(value is True for value in values):
        return True
    return None


def _normalize_nonempty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _name_match(expected: object, observed: object) -> bool | None:
    expected_text = _normalize_nonempty_string(expected)
    observed_text = _normalize_nonempty_string(observed)
    if expected_text is None or observed_text is None:
        return None
    return expected_text == observed_text


def _tighten_gate_with_optional_consistency(
    base_value: bool | None,
    consistency_value: bool | None,
) -> bool | None:
    if base_value is False or consistency_value is False:
        return False
    if base_value is True:
        return True
    return None


def _system_camera_device_visible_from_list_devices(
    *,
    present: Any,
    passed: Any,
    filtered_device_count: Any,
) -> bool | None:
    if present is not True:
        return None
    if passed is False:
        return False
    if passed is True:
        if filtered_device_count is None:
            return True
        try:
            return int(filtered_device_count) > 0
        except (TypeError, ValueError):
            return True
    return None


def evaluate_acceptance(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json_object(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)

    summary = dict(manifest.get("summary", {})) if isinstance(manifest.get("summary"), dict) else {}
    validation_report = _artifact_payload(manifest, "validation_report") or {}
    validation_summary = (
        dict(validation_report.get("summary", {}))
        if isinstance(validation_report.get("summary"), dict)
        else {}
    )
    preflight = _artifact_payload(manifest, "preflight_report") or {}
    preflight_readiness = (
        dict(preflight.get("readiness", {}))
        if isinstance(preflight.get("readiness"), dict)
        else {}
    )
    release_diagnostics = _artifact_payload(manifest, "release_diagnostics_report") or {}
    release_summary = (
        dict(release_diagnostics.get("summary", {}))
        if isinstance(release_diagnostics.get("summary"), dict)
        else {}
    )
    demo_payload = _artifact_payload(manifest, "demo_report") or {}
    benchmark_payload = _artifact_payload(manifest, "benchmark_report") or {}
    benchmark_summary = (
        dict(benchmark_payload.get("summary", {}))
        if isinstance(benchmark_payload.get("summary"), dict)
        else {}
    )
    entrypoints_contract = _artifact_payload(manifest, "entrypoints_contract_report") or {}
    entrypoints_consistency = (
        dict(entrypoints_contract.get("consistency", {}))
        if isinstance(entrypoints_contract.get("consistency"), dict)
        else {}
    )
    sdk_contract = _artifact_payload(manifest, "sdk_contract_report") or {}
    sdk_consistency = (
        dict(sdk_contract.get("consistency", {}))
        if isinstance(sdk_contract.get("consistency"), dict)
        else {}
    )
    benchmark_acceptance = (
        dict(benchmark_summary.get("benchmark_acceptance", {}))
        if isinstance(benchmark_summary.get("benchmark_acceptance"), dict)
        else {}
    )
    resolved_demo_mode = validation_summary.get("demo_mode")
    if not isinstance(resolved_demo_mode, str) or not resolved_demo_mode:
        resolved_demo_mode = demo_payload.get("mode") if isinstance(demo_payload.get("mode"), str) else None
    demo_mode_supported = validation_summary.get("demo_mode_supported")
    if demo_mode_supported is None and isinstance(resolved_demo_mode, str):
        demo_mode_supported = resolved_demo_mode in ALLOWED_DEMO_MODES
    resolved_frame_source_kind = validation_summary.get("demo_frame_source_kind")
    if not isinstance(resolved_frame_source_kind, str) or not resolved_frame_source_kind:
        raw_demo_frame_source_kind = demo_payload.get("frame_source_kind")
        resolved_frame_source_kind = (
            raw_demo_frame_source_kind if isinstance(raw_demo_frame_source_kind, str) else None
        )
    expected_frame_source_kind = (
        DEMO_MODE_TO_FRAME_SOURCE_KIND.get(resolved_demo_mode)
        if isinstance(resolved_demo_mode, str)
        else None
    )
    frame_source_supported: bool | None = None
    if expected_frame_source_kind is not None:
        if isinstance(resolved_frame_source_kind, str) and resolved_frame_source_kind:
            frame_source_supported = resolved_frame_source_kind == expected_frame_source_kind

    effective_formats = summary.get("effective_supported_formats")
    effective_frame_rates = summary.get("effective_supported_frame_rates")
    capability_pass = (
        isinstance(effective_formats, list)
        and set(str(item) for item in effective_formats) == EXPECTED_FORMATS
        and isinstance(effective_frame_rates, list)
        and set(int(item) for item in effective_frame_rates) == EXPECTED_FRAME_RATES
    )
    install_session_present = summary.get("install_session_present")
    install_session_start_ready = summary.get("install_session_start_ready")
    if install_session_start_ready is None:
        install_session_start_ready = summary.get("effective_start_ready")
    install_session_start_blocker_code = summary.get("install_session_start_blocker_code")
    if not install_session_start_blocker_code:
        install_session_start_blocker_code = summary.get("effective_start_blocker_code")
    install_session_ipc_probe_present = summary.get("install_session_ipc_probe_present")
    install_session_ipc_ready = summary.get("install_session_ipc_ready")
    install_session_ipc_environment_blocked = summary.get("install_session_ipc_environment_blocked")
    install_session_sync_ipc_present = summary.get("install_session_sync_ipc_present")
    install_session_sync_ipc_supported = summary.get("install_session_sync_ipc_supported")
    install_session_sync_ipc_success = summary.get("install_session_sync_ipc_success")
    install_session_sync_ipc_phase = summary.get("install_session_sync_ipc_phase")
    list_devices_binary_check_present = (
        summary.get("list_devices_binary_check_present")
        if "list_devices_binary_check_present" in summary
        else validation_summary.get("list_devices_binary_check_present")
    )
    list_devices_binary_check_passed = (
        summary.get("list_devices_binary_check_passed")
        if "list_devices_binary_check_passed" in summary
        else validation_summary.get("list_devices_binary_check_passed")
    )
    list_devices_binary_check_device_prefix = (
        summary.get("list_devices_binary_check_device_prefix")
        if "list_devices_binary_check_device_prefix" in summary
        else validation_summary.get("list_devices_binary_check_device_prefix")
    )
    list_devices_binary_check_filtered_device_count = (
        summary.get("list_devices_binary_check_filtered_device_count")
        if "list_devices_binary_check_filtered_device_count" in summary
        else validation_summary.get("list_devices_binary_check_filtered_device_count")
    )
    list_devices_binary_check_total_device_count = (
        summary.get("list_devices_binary_check_total_device_count")
        if "list_devices_binary_check_total_device_count" in summary
        else validation_summary.get("list_devices_binary_check_total_device_count")
    )
    list_devices_binary_check_override_no_match_ok = (
        summary.get("list_devices_binary_check_override_no_match_ok")
        if "list_devices_binary_check_override_no_match_ok" in summary
        else validation_summary.get("list_devices_binary_check_override_no_match_ok")
    )
    effective_device_prefix = (
        summary.get("effective_device_prefix")
        if "effective_device_prefix" in summary
        else validation_summary.get("effective_device_prefix")
    )
    validation_device_prefix = (
        summary.get("validation_device_prefix")
        if "validation_device_prefix" in summary
        else validation_summary.get("validation_device_prefix")
    )
    validation_install_device_prefix = (
        summary.get("validation_install_device_prefix")
        if "validation_install_device_prefix" in summary
        else validation_summary.get("validation_install_device_prefix")
    )
    install_session_device_prefix = (
        summary.get("install_session_device_prefix")
        if "install_session_device_prefix" in summary
        else validation_summary.get("install_session_device_prefix")
    )
    validation_demo_camera_name = (
        summary.get("validation_demo_camera_name")
        if "validation_demo_camera_name" in summary
        else validation_summary.get("demo_camera_name")
    )
    system_camera_device_visible_value = _system_camera_device_visible_from_list_devices(
        present=list_devices_binary_check_present,
        passed=list_devices_binary_check_passed,
        filtered_device_count=list_devices_binary_check_filtered_device_count,
    )
    release_minimum_system_version_expected = _preferred_summary_value(
        validation_summary,
        "release_minimum_system_version_expected",
        release_summary,
        "minimum_system_version_expected",
    )
    release_universal2_ready = _preferred_summary_value(
        validation_summary,
        "release_universal2_ready",
        release_summary,
        "universal2_ready",
    )
    release_artifacts_present = _preferred_summary_value(
        validation_summary,
        "release_artifacts_present",
        release_summary,
        "release_artifacts_present",
    )
    release_pkg_includes_extension_payload = _preferred_summary_value(
        validation_summary,
        "release_pkg_includes_extension_payload",
        release_summary,
        "pkg_includes_extension_payload",
    )
    release_pkg_payload_appledouble_clean = _preferred_summary_value(
        validation_summary,
        "release_pkg_payload_appledouble_clean",
        release_summary,
        "pkg_payload_appledouble_clean",
    )
    release_host_embeds_extension_bundle = _preferred_summary_value(
        validation_summary,
        "release_host_embeds_extension_bundle",
        release_summary,
        "host_embeds_extension_bundle",
    )
    release_app_signed = _preferred_summary_value(
        validation_summary,
        "release_app_signed",
        release_summary,
        "app_signed",
    )
    release_extension_signed = _preferred_summary_value(
        validation_summary,
        "release_extension_signed",
        release_summary,
        "extension_signed",
    )
    release_command_tools_signed = _preferred_summary_value(
        validation_summary,
        "release_command_tools_signed",
        release_summary,
        "command_tools_signed",
    )
    release_pkg_signed = _preferred_summary_value(
        validation_summary,
        "release_pkg_signed",
        release_summary,
        "pkg_signed",
    )
    release_app_gatekeeper_accepted = _preferred_summary_value(
        validation_summary,
        "release_app_gatekeeper_accepted",
        release_summary,
        "app_gatekeeper_accepted",
    )
    release_app_stapled = _preferred_summary_value(
        validation_summary,
        "release_app_stapled",
        release_summary,
        "app_stapled",
    )
    release_pkg_gatekeeper_accepted = _preferred_summary_value(
        validation_summary,
        "release_pkg_gatekeeper_accepted",
        release_summary,
        "pkg_gatekeeper_accepted",
    )
    release_pkg_stapled = _preferred_summary_value(
        validation_summary,
        "release_pkg_stapled",
        release_summary,
        "pkg_stapled",
    )
    release_sync_ipc_tool_exists = (
        summary.get("release_sync_ipc_tool_exists")
        if "release_sync_ipc_tool_exists" in summary
        else release_summary.get("sync_ipc_tool_exists")
    )
    release_sync_ipc_tool_signed = (
        summary.get("release_sync_ipc_tool_signed")
        if "release_sync_ipc_tool_signed" in summary
        else release_summary.get("sync_ipc_tool_signed")
    )
    release_sync_ipc_tool_universal2_ready = (
        summary.get("release_sync_ipc_tool_universal2_ready")
        if "release_sync_ipc_tool_universal2_ready" in summary
        else release_summary.get("sync_ipc_tool_universal2_ready")
    )
    runtime_release_product_identity_consistent = (
        summary.get("runtime_release_product_identity_consistent")
        if "runtime_release_product_identity_consistent" in summary
        else validation_summary.get("runtime_release_product_identity_consistent")
    )
    runtime_release_product_path_equal = (
        summary.get("runtime_release_product_path_equal")
        if "runtime_release_product_path_equal" in summary
        else validation_summary.get("runtime_release_product_path_equal")
    )
    runtime_host_bundle_path = (
        summary.get("runtime_host_bundle_path")
        if "runtime_host_bundle_path" in summary
        else validation_summary.get("runtime_host_bundle_path")
    )
    runtime_extension_bundle_path = (
        summary.get("runtime_extension_bundle_path")
        if "runtime_extension_bundle_path" in summary
        else validation_summary.get("runtime_extension_bundle_path")
    )
    runtime_sync_ipc_tool_path = (
        summary.get("runtime_sync_ipc_tool_path")
        if "runtime_sync_ipc_tool_path" in summary
        else validation_summary.get("runtime_sync_ipc_tool_path")
    )
    runtime_pkg_path = (
        summary.get("runtime_pkg_path")
        if "runtime_pkg_path" in summary
        else validation_summary.get("runtime_pkg_path")
    )
    release_app_bundle_path = (
        summary.get("release_app_bundle_path")
        if "release_app_bundle_path" in summary
        else validation_summary.get("release_app_bundle_path")
    )
    release_extension_bundle_path = (
        summary.get("release_extension_bundle_path")
        if "release_extension_bundle_path" in summary
        else validation_summary.get("release_extension_bundle_path")
    )
    release_sync_ipc_tool_path = (
        summary.get("release_sync_ipc_tool_path")
        if "release_sync_ipc_tool_path" in summary
        else validation_summary.get("release_sync_ipc_tool_path")
    )
    release_pkg_path = (
        summary.get("release_pkg_path")
        if "release_pkg_path" in summary
        else validation_summary.get("release_pkg_path")
    )
    entrypoints_contract_present = (
        summary.get("entrypoints_contract_present")
        if "entrypoints_contract_present" in summary
        else (True if entrypoints_contract else None)
    )
    entrypoints_contract_passed = (
        summary.get("entrypoints_contract_passed")
        if "entrypoints_contract_passed" in summary
        else entrypoints_consistency.get("all_checks_passed")
    )
    entrypoints_contract_surface_complete = (
        summary.get("entrypoints_contract_surface_complete")
        if "entrypoints_contract_surface_complete" in summary
        else entrypoints_consistency.get("surface_complete")
    )
    entrypoints_contract_demo_case_complete = (
        summary.get("entrypoints_contract_demo_case_complete")
        if "entrypoints_contract_demo_case_complete" in summary
        else entrypoints_consistency.get("demo_case_complete")
    )
    entrypoints_contract_cli_case_complete = (
        summary.get("entrypoints_contract_cli_case_complete")
        if "entrypoints_contract_cli_case_complete" in summary
        else entrypoints_consistency.get("cli_case_complete")
    )
    entrypoints_contract_desktop_case_complete = (
        summary.get("entrypoints_contract_desktop_case_complete")
        if "entrypoints_contract_desktop_case_complete" in summary
        else entrypoints_consistency.get("desktop_case_complete")
    )
    sdk_contract_present = (
        summary.get("sdk_contract_present")
        if "sdk_contract_present" in summary
        else (True if sdk_contract else None)
    )
    sdk_contract_passed = (
        summary.get("sdk_contract_passed")
        if "sdk_contract_passed" in summary
        else sdk_consistency.get("all_checks_passed")
    )
    sdk_contract_constructor_shape_aligned = (
        summary.get("sdk_contract_constructor_shape_aligned")
        if "sdk_contract_constructor_shape_aligned" in summary
        else sdk_consistency.get("constructor_shape_aligned")
    )
    sdk_contract_direct_sender_exports_present = (
        summary.get("sdk_contract_direct_sender_exports_present")
        if "sdk_contract_direct_sender_exports_present" in summary
        else sdk_consistency.get("direct_sender_exports_present")
    )
    python_entrypoints_consistent_value = (
        True
        if all(
            value is True
            for value in (
                entrypoints_contract_passed,
                entrypoints_contract_surface_complete,
                entrypoints_contract_demo_case_complete,
                entrypoints_contract_cli_case_complete,
                entrypoints_contract_desktop_case_complete,
                sdk_contract_passed,
                sdk_contract_constructor_shape_aligned,
                sdk_contract_direct_sender_exports_present,
            )
        )
        else False
        if any(
            value is False
            for value in (
                entrypoints_contract_passed,
                entrypoints_contract_surface_complete,
                entrypoints_contract_demo_case_complete,
                entrypoints_contract_cli_case_complete,
                entrypoints_contract_desktop_case_complete,
                sdk_contract_passed,
                sdk_contract_constructor_shape_aligned,
                sdk_contract_direct_sender_exports_present,
            )
        )
        else None
    )
    python_direct_runtime_value, python_direct_runtime_evidence = _direct_runtime_assessment(
        summary
    )
    auto_install_value: bool | None
    if install_session_present is not True:
        auto_install_value = None
    else:
        auto_install_value = (
            bool(summary.get("install_session_success"))
            and install_session_start_ready is True
            and install_session_start_blocker_code == "ready"
            and install_session_ipc_environment_blocked is not True
            and not (
                install_session_ipc_probe_present is True
                and install_session_ipc_ready is not True
            )
        )
    validation_app_matrix = _validation_app_matrix(summary)
    if validation_app_matrix is None:
        validation_app_matrix = _validation_app_matrix(validation_summary)
    app_count = summary.get("validation_validated_apps")
    if app_count is None:
        app_count = validation_summary.get("validated_apps")
    passed_apps = summary.get("validation_passed_apps")
    if passed_apps is None:
        passed_apps = validation_summary.get("passed_apps")
    passed_app_ids = _normalize_string_list(summary.get("validation_passed_app_ids"))
    if passed_app_ids is None:
        passed_app_ids = _normalize_string_list(validation_summary.get("passed_app_ids"))
    if passed_app_ids is None:
        passed_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "pass")
    failed_app_ids = _normalize_string_list(summary.get("validation_failed_app_ids"))
    if failed_app_ids is None:
        failed_app_ids = _normalize_string_list(validation_summary.get("failed_app_ids"))
    if failed_app_ids is None:
        failed_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "fail")
    pending_app_ids = _normalize_string_list(summary.get("validation_pending_app_ids"))
    if pending_app_ids is None:
        pending_app_ids = _normalize_string_list(validation_summary.get("pending_app_ids"))
    if pending_app_ids is None:
        pending_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "pending")
    skipped_app_ids = _normalize_string_list(summary.get("validation_skipped_app_ids"))
    if skipped_app_ids is None:
        skipped_app_ids = _normalize_string_list(validation_summary.get("skipped_app_ids"))
    if skipped_app_ids is None:
        skipped_app_ids = _validation_app_matrix_ids_with_result(validation_app_matrix, "skipped")
    unreviewed_app_ids = _normalize_string_list(summary.get("validation_unreviewed_app_ids"))
    if unreviewed_app_ids is None:
        unreviewed_app_ids = _normalize_string_list(validation_summary.get("unreviewed_app_ids"))
    if unreviewed_app_ids is None:
        unreviewed_app_ids = _validation_app_matrix_unreviewed_ids(validation_app_matrix)
    observed_target_app_ids = _normalize_string_list(
        summary.get("validation_observed_target_app_ids")
    )
    if observed_target_app_ids is None:
        observed_target_app_ids = _normalize_string_list(
            validation_summary.get("observed_target_app_ids")
        )
    if observed_target_app_ids is None:
        observed_target_app_ids = sorted(
            set(passed_app_ids or [])
            | set(failed_app_ids or [])
            | set(pending_app_ids or [])
            | set(skipped_app_ids or [])
            | set(unreviewed_app_ids or [])
            | (set(validation_app_matrix.keys()) if isinstance(validation_app_matrix, dict) else set())
        )
    missing_target_app_ids = _normalize_string_list(
        summary.get("validation_missing_target_app_ids")
    )
    if missing_target_app_ids is None:
        missing_target_app_ids = _normalize_string_list(
            validation_summary.get("missing_target_app_ids")
        )
    if missing_target_app_ids is None:
        missing_target_app_ids = sorted(
            set(EXPECTED_APP_IDS) - set(observed_target_app_ids)
        )
    unexpected_target_app_ids = _normalize_string_list(
        summary.get("validation_unexpected_target_app_ids")
    )
    if unexpected_target_app_ids is None:
        unexpected_target_app_ids = _normalize_string_list(
            validation_summary.get("unexpected_target_app_ids")
        )
    if unexpected_target_app_ids is None:
        unexpected_target_app_ids = sorted(
            set(observed_target_app_ids) - set(EXPECTED_APP_IDS)
        )
    target_app_missing_evidence_ids = (
        _validation_app_matrix_missing_evidence_ids(validation_app_matrix)
        if isinstance(validation_app_matrix, dict)
        else EXPECTED_APP_IDS
    )
    exact_target_id_evidence_present = bool(
        isinstance(validation_app_matrix, dict)
        or passed_app_ids is not None
        or failed_app_ids is not None
        or pending_app_ids is not None
        or skipped_app_ids is not None
        or unreviewed_app_ids is not None
        or "validation_observed_target_app_ids" in summary
        or "validation_missing_target_app_ids" in summary
        or "validation_unexpected_target_app_ids" in summary
        or "observed_target_app_ids" in validation_summary
        or "missing_target_app_ids" in validation_summary
        or "unexpected_target_app_ids" in validation_summary
    )
    app_matrix_value: bool | None
    if not exact_target_id_evidence_present:
        app_matrix_value = None
    elif missing_target_app_ids:
        app_matrix_value = False
    elif unexpected_target_app_ids:
        app_matrix_value = False
    elif target_app_missing_evidence_ids:
        app_matrix_value = False
    elif (failed_app_ids or pending_app_ids or skipped_app_ids or unreviewed_app_ids):
        app_matrix_value = False
    elif passed_app_ids is not None:
        app_matrix_value = sorted(passed_app_ids) == EXPECTED_APP_IDS
    else:
        app_matrix_value = None

    criteria = [
        _status_from_bool(
            "macos_13_plus_declared",
            release_minimum_system_version_expected,
            evidence={
                "release_minimum_system_version_expected": release_minimum_system_version_expected,
                "minimum_system_version_expected": release_summary.get("minimum_system_version_expected"),
            },
            unknown_note="缺少最低系统版本证据，尚不能证明 macOS 13+ 声明保持一致。",
            fail_note="当前会话未证明 Host/Extension 的最低系统版本保持在 macOS 13.0。",
        ),
        _status_from_bool(
            "universal2_ready",
            release_universal2_ready,
            evidence={
                "release_universal2_ready": release_universal2_ready,
                "universal2_ready": release_summary.get("universal2_ready"),
            },
            unknown_note="缺少 universal2 证据，尚不能确认 arm64 + x86_64 双架构产物已就绪。",
            fail_note="当前会话未证明 universal2 产物已就绪。",
        ),
        _status_from_bool(
            "release_packaging_ready",
            _tighten_gate_with_optional_consistency(
                _all_true_or_false_or_none(
                    release_artifacts_present,
                    release_pkg_includes_extension_payload,
                    release_pkg_payload_appledouble_clean,
                    release_host_embeds_extension_bundle,
                ),
                runtime_release_product_identity_consistent,
            ),
            evidence={
                "release_artifacts_present": release_artifacts_present,
                "release_pkg_includes_extension_payload": release_pkg_includes_extension_payload,
                "release_pkg_payload_appledouble_clean": release_pkg_payload_appledouble_clean,
                "release_host_embeds_extension_bundle": release_host_embeds_extension_bundle,
                "pkg_includes_extension_payload": release_summary.get("pkg_includes_extension_payload"),
                "pkg_payload_appledouble_clean": release_summary.get("pkg_payload_appledouble_clean"),
                "host_embeds_extension_bundle": release_summary.get("host_embeds_extension_bundle"),
                "runtime_release_product_identity_consistent": runtime_release_product_identity_consistent,
                "runtime_release_product_path_equal": runtime_release_product_path_equal,
                "runtime_host_bundle_path": runtime_host_bundle_path,
                "runtime_extension_bundle_path": runtime_extension_bundle_path,
                "runtime_sync_ipc_tool_path": runtime_sync_ipc_tool_path,
                "runtime_pkg_path": runtime_pkg_path,
                "release_app_bundle_path": release_app_bundle_path,
                "release_extension_bundle_path": release_extension_bundle_path,
                "release_sync_ipc_tool_path": release_sync_ipc_tool_path,
                "release_pkg_path": release_pkg_path,
            },
            unknown_note="缺少 release packaging 证据，尚不能证明 pkg/host/extension 交付结构完整且 payload 清洁。",
            fail_note=(
                "当前会话未证明 pkg 与 host/extension 交付结构完整，或 runtime 验收路径与 "
                "release-diagnostics 指向的产品集不一致。"
            ),
        ),
        _status_from_bool(
            "signing_evidence_ready",
            _all_true_or_false_or_none(
                release_app_signed,
                release_extension_signed,
                release_command_tools_signed,
                release_pkg_signed,
            ),
            evidence={
                "release_app_signed": release_app_signed,
                "release_extension_signed": release_extension_signed,
                "release_command_tools_signed": release_command_tools_signed,
                "release_pkg_signed": release_pkg_signed,
                "app_signed": release_summary.get("app_signed"),
                "extension_signed": release_summary.get("extension_signed"),
                "command_tools_signed": release_summary.get("command_tools_signed"),
                "pkg_signed": release_summary.get("pkg_signed"),
            },
            unknown_note="缺少签名证据，尚不能证明 Host/Extension/runtime tools/pkg 已签名。",
            fail_note="当前会话未证明 Host/Extension/runtime tools/pkg 已全部签名。",
        ),
        _status_from_bool(
            "notarization_tooling_ready",
            _any_true_without_false_or_none(
                _all_true_or_false_or_none(
                    preflight_readiness.get("can_notarize"),
                    preflight_readiness.get("can_staple"),
                )
                if preflight_readiness
                else None,
                _all_true_or_false_or_none(
                    release_app_gatekeeper_accepted,
                    release_app_stapled,
                    release_pkg_gatekeeper_accepted,
                    release_pkg_stapled,
                ),
            ),
            evidence={
                "can_notarize": preflight_readiness.get("can_notarize"),
                "can_staple": preflight_readiness.get("can_staple"),
                "release_app_gatekeeper_accepted": release_app_gatekeeper_accepted,
                "release_app_stapled": release_app_stapled,
                "release_pkg_gatekeeper_accepted": release_pkg_gatekeeper_accepted,
                "release_pkg_stapled": release_pkg_stapled,
                "app_gatekeeper_accepted": release_summary.get("app_gatekeeper_accepted"),
                "app_stapled": release_summary.get("app_stapled"),
                "pkg_gatekeeper_accepted": release_summary.get("pkg_gatekeeper_accepted"),
                "pkg_stapled": release_summary.get("pkg_stapled"),
            },
            unknown_note=(
                "缺少完整 preflight 或 release 公证证据，尚不能判断 notarytool/stapler 是否就绪，"
                "也尚不能证明宿主 app / pkg 已通过 Gatekeeper 与 stapler validate。"
            ),
            fail_note=(
                "当前会话未证明公证/Staple 工具链与 release 产物公证状态同时就绪，"
                "或宿主 app / pkg 尚未通过 Gatekeeper / stapler validate。"
            ),
        ),
        _status_from_bool(
            "pyside6_path_exercised",
            (
                True
                if validation_summary.get("demo_present") is True
                and demo_mode_supported is True
                and frame_source_supported is True
                else False
                if validation_summary.get("demo_present") is False
                or demo_mode_supported is False
                or frame_source_supported is False
                else None
            ),
            evidence={
                "demo_present": validation_summary.get("demo_present"),
                "demo_artifact_loaded": bool(demo_payload),
                "demo_mode": resolved_demo_mode,
                "demo_mode_supported": demo_mode_supported,
                "demo_frame_source_kind": resolved_frame_source_kind,
                "expected_frame_source_kind": expected_frame_source_kind,
                "frame_source_supported": frame_source_supported,
            },
            unknown_note="缺少完整 PySide6 demo 证据，尚不能证明 PySide6 直推路径已被本次会话覆盖。",
            fail_note=(
                "当前会话未证明 Python/PySide6 demo 使用了受支持的 numpy-direct/provider/"
                "latest-provider/image/pixmap/widget/screen/video-file 模式，或其 frame_source_kind 与模式不匹配。"
            ),
        ),
        _status_from_bool(
            "python_direct_runtime_ready",
            python_direct_runtime_value,
            evidence=python_direct_runtime_evidence,
            unknown_note=(
                "缺少 direct-push 纯直连证据，尚不能证明 Python VirtualCamera 已在无 helper 热路径、"
                "无 shared-memory fallback 的前提下直接把帧送入 Camera Extension。"
            ),
            fail_note=(
                "当前会话未证明 Python VirtualCamera 走的是纯 direct sender 热路径；"
                "请优先运行 `python3 tools/make.py direct-push-demo --require-direct-runtime` 复核。"
            ),
        ),
        _status_from_bool(
            "python_entrypoints_consistent",
            python_entrypoints_consistent_value,
            evidence={
                "entrypoints_contract_present": entrypoints_contract_present,
                "entrypoints_contract_passed": entrypoints_contract_passed,
                "entrypoints_contract_surface_complete": entrypoints_contract_surface_complete,
                "entrypoints_contract_demo_case_complete": entrypoints_contract_demo_case_complete,
                "entrypoints_contract_cli_case_complete": entrypoints_contract_cli_case_complete,
                "entrypoints_contract_desktop_case_complete": entrypoints_contract_desktop_case_complete,
                "sdk_contract_present": sdk_contract_present,
                "sdk_contract_passed": sdk_contract_passed,
                "sdk_contract_constructor_shape_aligned": sdk_contract_constructor_shape_aligned,
                "sdk_contract_direct_sender_exports_present": (
                    sdk_contract_direct_sender_exports_present
                ),
            },
            unknown_note=(
                "缺少统一 Python 入口 contract 证据，尚不能证明 PySide6 demo/direct-push demo/"
                "CLI/desktop 仍共同走统一 VirtualCamera 入口，且 SDK direct sender 导出面仍完整。"
            ),
            fail_note=(
                "当前会话未证明 PySide6 demo/direct-push demo/CLI/desktop 四条入口链仍共同走统一 "
                "VirtualCamera 入口，或 SDK direct sender 导出面 / 构造签名 contract 存在缺口。"
            ),
        ),
        _criterion(
            "target_apps_all_passed",
            status=(
                "pass"
                if app_matrix_value is True
                else "fail"
                if app_matrix_value is False
                else "unknown"
            ),
            evidence={
                "validated_apps": app_count,
                "passed_apps": passed_apps,
                "expected_target_app_ids": EXPECTED_APP_IDS,
                "observed_target_app_ids": observed_target_app_ids,
                "passed_app_ids": passed_app_ids,
                "failed_app_ids": failed_app_ids,
                "pending_app_ids": pending_app_ids,
                "skipped_app_ids": skipped_app_ids,
                "unreviewed_app_ids": unreviewed_app_ids,
                "missing_target_app_ids": missing_target_app_ids,
                "unexpected_target_app_ids": unexpected_target_app_ids,
                "target_app_missing_evidence_ids": target_app_missing_evidence_ids,
                "expected_app_count": EXPECTED_APP_COUNT,
            },
            note=_app_matrix_note(
                app_matrix_value,
                exact_id_evidence_present=exact_target_id_evidence_present,
                missing_target_app_ids=missing_target_app_ids,
                unexpected_target_app_ids=unexpected_target_app_ids,
                failed_app_ids=failed_app_ids if isinstance(failed_app_ids, list) else None,
                pending_app_ids=pending_app_ids if isinstance(pending_app_ids, list) else None,
                skipped_app_ids=skipped_app_ids if isinstance(skipped_app_ids, list) else None,
                unreviewed_app_ids=unreviewed_app_ids if isinstance(unreviewed_app_ids, list) else None,
                target_app_missing_evidence_ids=(
                    target_app_missing_evidence_ids
                    if isinstance(target_app_missing_evidence_ids, list)
                    else None
                ),
            ),
        ),
        _criterion(
            "capability_matrix_declared",
            status="pass" if capability_pass else "fail",
            evidence={
                "effective_supported_formats": effective_formats,
                "effective_supported_frame_rates": effective_frame_rates,
            },
            note=None if capability_pass else "当前会话未同时声明 720p/1080p/4K 与 30/60fps 全能力矩阵。",
        ),
        _criterion(
            "benchmark_matrix_complete",
            status=(
                "pass"
                if benchmark_acceptance and benchmark_acceptance.get("required_profiles_present") is True
                else "fail"
                if benchmark_acceptance
                else "unknown"
            ),
            evidence={
                "expected_benchmark_profiles": EXPECTED_BENCHMARK_PROFILES,
                "benchmark_acceptance": benchmark_acceptance or None,
            },
            note=_benchmark_matrix_note(benchmark_acceptance),
        ),
        _status_from_bool(
            "benchmark_fps_targets_met",
            benchmark_acceptance.get("all_fps_targets_met")
            if benchmark_acceptance
            else None,
            evidence={"benchmark_acceptance": benchmark_acceptance or None},
            unknown_note="缺少 benchmark matrix 证据，尚不能判断各基准场景 FPS 目标是否达标。",
            fail_note="当前会话未证明 benchmark matrix 的 FPS 目标全部达标。",
        ),
        _status_from_bool(
            "benchmark_1080p60_cpu_target_met",
            benchmark_acceptance.get("1080p60_cpu_target_met")
            if benchmark_acceptance
            else None,
            evidence={"benchmark_acceptance": benchmark_acceptance or None},
            unknown_note="缺少 1080p60 benchmark 证据，尚不能证明 CPU <10%。",
            fail_note="当前会话未证明 1080p60 CPU <10%。",
        ),
        _status_from_bool(
            "auto_install_ready",
            auto_install_value,
            evidence={
                "install_session_present": install_session_present,
                "install_session_success": summary.get("install_session_success"),
                "install_session_start_ready": install_session_start_ready,
                "install_session_start_blocker_code": install_session_start_blocker_code,
                "install_session_ipc_probe_present": install_session_ipc_probe_present,
                "install_session_ipc_ready": install_session_ipc_ready,
                "install_session_ipc_environment_blocked": install_session_ipc_environment_blocked,
                "install_session_ipc_direct_open_errno": summary.get("install_session_ipc_direct_open_errno"),
            },
            unknown_note="本次会话未覆盖 install-session，尚不能证明自动安装后已可开始推流。",
            fail_note="当前会话未证明自动安装成功、设备已可见且 install-session 的 IPC 检查已就绪。",
        ),
        _status_from_bool(
            "system_camera_device_visible",
            system_camera_device_visible_value,
            evidence={
                "effective_device_prefix": effective_device_prefix,
                "validation_device_prefix": validation_device_prefix,
                "validation_install_device_prefix": validation_install_device_prefix,
                "install_session_device_prefix": install_session_device_prefix,
                "validation_demo_camera_name": validation_demo_camera_name,
                "demo_camera_name_matches_effective_prefix": _name_match(
                    effective_device_prefix,
                    validation_demo_camera_name,
                ),
                "validation_device_prefix_matches_effective_prefix": _name_match(
                    effective_device_prefix,
                    validation_device_prefix,
                ),
                "validation_install_device_prefix_matches_effective_prefix": _name_match(
                    effective_device_prefix,
                    validation_install_device_prefix,
                ),
                "install_session_device_prefix_matches_effective_prefix": _name_match(
                    effective_device_prefix,
                    install_session_device_prefix,
                ),
                "list_devices_binary_check_device_prefix_matches_effective_prefix": _name_match(
                    effective_device_prefix,
                    list_devices_binary_check_device_prefix,
                ),
                "list_devices_binary_check_present": list_devices_binary_check_present,
                "list_devices_binary_check_passed": list_devices_binary_check_passed,
                "list_devices_binary_check_device_prefix": list_devices_binary_check_device_prefix,
                "list_devices_binary_check_filtered_device_count": list_devices_binary_check_filtered_device_count,
                "list_devices_binary_check_total_device_count": list_devices_binary_check_total_device_count,
                "list_devices_binary_check_override_no_match_ok": list_devices_binary_check_override_no_match_ok,
            },
            unknown_note=(
                "缺少 akvc-macos-list-devices 证据，尚不能证明系统视频设备枚举中已出现 "
                f"{_normalize_nonempty_string(effective_device_prefix) or '目标虚拟摄像头'}。"
            ),
            fail_note=(
                "akvc-macos-list-devices 本次未枚举到匹配的 "
                f"{_normalize_nonempty_string(effective_device_prefix) or '目标虚拟摄像头'}，"
                "尚不能进入人工应用验收。"
            ),
        ),
        _status_from_bool(
            "artifact_replay_passed",
            summary.get("artifact_check_passed"),
            evidence={
                "artifact_check_present": summary.get("artifact_check_present"),
                "artifact_check_passed": summary.get("artifact_check_passed"),
            },
            unknown_note="缺少 artifact replay 证据，尚不能证明 session manifest 真实工件自洽。",
            fail_note="当前会话的 session manifest / 子工件回放检查未通过。",
        ),
        _status_from_bool(
            "runtime_assets_packaged",
            validation_summary.get("runtime_packaged_assets_present"),
            evidence={"runtime_packaged_assets_present": validation_summary.get("runtime_packaged_assets_present")},
            unknown_note="缺少 runtime 资产证据，尚不能证明 Python 分发态已携带 macOS runtime 资源。",
            fail_note="当前会话未证明 Python 分发态 runtime 资产已完整同步。",
        ),
        _status_from_bool(
            "sync_ipc_control_plane_ready",
            _all_true_or_false_or_none(
                release_sync_ipc_tool_exists,
                release_sync_ipc_tool_signed,
                release_sync_ipc_tool_universal2_ready,
                install_session_sync_ipc_present,
                install_session_sync_ipc_supported,
                install_session_sync_ipc_success,
            ),
            evidence={
                "release_sync_ipc_tool_exists": release_sync_ipc_tool_exists,
                "release_sync_ipc_tool_signed": release_sync_ipc_tool_signed,
                "release_sync_ipc_tool_universal2_ready": release_sync_ipc_tool_universal2_ready,
                "install_session_sync_ipc_present": install_session_sync_ipc_present,
                "install_session_sync_ipc_supported": install_session_sync_ipc_supported,
                "install_session_sync_ipc_success": install_session_sync_ipc_success,
                "install_session_sync_ipc_phase": install_session_sync_ipc_phase,
            },
            unknown_note="缺少 sync-ipc 控制面证据，尚不能判断显式 IPC 配置同步工具是否已分发且被当前安装会话成功执行。",
            fail_note="当前会话未证明 akvc-macos-sync-ipc 已存在、已签名、满足 universal2 且已在 install-session 中成功完成显式同步。",
            critical=False,
        ),
    ]

    passed = [item["name"] for item in criteria if item["status"] == "pass"]
    failed = [item["name"] for item in criteria if item["status"] == "fail"]
    unknown = [item["name"] for item in criteria if item["status"] == "unknown"]
    critical_failed = [item["name"] for item in criteria if item["critical"] and item["status"] == "fail"]
    critical_unknown = [item["name"] for item in criteria if item["critical"] and item["status"] == "unknown"]
    manual_app_validation_failed = [
        item["name"]
        for item in criteria
        if item["name"] in MANUAL_APP_VALIDATION_GATE_NAMES and item["status"] == "fail"
    ]
    manual_app_validation_unknown = [
        item["name"]
        for item in criteria
        if item["name"] in MANUAL_APP_VALIDATION_GATE_NAMES and item["status"] == "unknown"
    ]
    manual_app_validation_blockers = (
        manual_app_validation_failed + manual_app_validation_unknown
    )

    acceptance_ready = not critical_failed and not critical_unknown
    manual_app_validation_ready = (
        not manual_app_validation_failed and not manual_app_validation_unknown
    )

    return {
        "manifest_path": str(manifest_path),
        "criteria": criteria,
        "summary": {
            "criterion_count": len(criteria),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "unknown_count": len(unknown),
            "passed_criteria": passed,
            "failed_criteria": failed,
            "unknown_criteria": unknown,
            "acceptance_ready": acceptance_ready,
            "critical_failed_criteria": critical_failed,
            "critical_unknown_criteria": critical_unknown,
            "manual_app_validation_ready": manual_app_validation_ready,
            "manual_app_validation_failed_criteria": manual_app_validation_failed,
            "manual_app_validation_unknown_criteria": manual_app_validation_unknown,
            "manual_app_validation_blockers": manual_app_validation_blockers,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS validation-session acceptance summary helper"
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"validation-session manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    payload = evaluate_acceptance(manifest_path)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
