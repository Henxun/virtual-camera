# SPDX-License-Identifier: Apache-2.0
"""macOS validation report helper.

Collects installation/device state, optional install convergence data,
optional producer benchmark results, and optional manual app-validation
outcomes into a single JSON artifact for lab runs and release verification.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.platforms.macos.installer import (  # noqa: E402
    DefaultMacInstallerService,
    inspect_extension,
    inspect_install_result,
)
from akvc.platforms.macos.ipc import apply_camera_name_override  # noqa: E402
from akvc.runtime import (  # noqa: E402
    find_macos_direct_sender_library,
    find_macos_install_tool,
    find_macos_list_devices_tool,
    find_macos_pkg,
    find_macos_status_tool,
    find_macos_sync_ipc_tool,
    find_macos_uninstall_tool,
)

ALLOWED_MANUAL_RESULT_IDS = {
    "zoom",
    "teams",
    "google_meet",
    "obs",
    "quicktime",
    "facetime",
}
EXPECTED_TARGET_APP_IDS = sorted(ALLOWED_MANUAL_RESULT_IDS)
ALLOWED_MANUAL_RESULT_VALUES = {"pass", "fail", "pending", "skipped"}
MANUAL_EVIDENCE_FIELDS = (
    "device_listed",
    "device_selected",
    "preview_visible",
    "screenshot",
)
PACKAGED_MACOS_RUNTIME_DIR = ROOT / "camera-core" / "src" / "akvc" / "_runtime" / "macos"
PACKAGED_MACOS_RUNTIME_ASSETS = (
    "akvc-macos-status",
    "akvc-macos-install",
    "akvc-macos-uninstall",
    "akvc-macos-list-devices",
    "akvc-macos-sync-ipc",
    "libakvc-macos-direct-sender.dylib",
    "VirtualCamera.pkg",
)
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


def _runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _load_json_file(path: str | None) -> Any | None:
    if not path:
        return None
    payload_path = Path(path)
    if not payload_path.is_file():
        raise FileNotFoundError(payload_path)
    return json.loads(payload_path.read_text(encoding="utf-8"))


def _manual_results_map(payload: Any) -> dict[str, dict[str, Any]]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("manual results JSON must be an object keyed by app id")
    result: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        normalized_key = str(key)
        if normalized_key not in ALLOWED_MANUAL_RESULT_IDS:
            raise ValueError(f"unknown manual results key: {normalized_key}")
        if not isinstance(value, dict):
            raise ValueError("manual results entries must be objects")
        item = dict(value)
        manual_result = str(item.get("result", "pending"))
        if manual_result not in ALLOWED_MANUAL_RESULT_VALUES:
            raise ValueError(
                f"invalid manual result for {normalized_key}: {manual_result}"
            )
        if "validated" in item and not isinstance(item.get("validated"), bool):
            raise ValueError(
                f"manual result validated flag must be bool for {normalized_key}"
            )
        if "notes" in item and item.get("notes") is not None and not isinstance(item.get("notes"), str):
            raise ValueError(
                f"manual result notes must be string for {normalized_key}"
            )
        if "evidence" in item:
            evidence = item.get("evidence")
            if not isinstance(evidence, dict):
                raise ValueError(
                    f"manual result evidence must be object for {normalized_key}"
                )
            for field in MANUAL_EVIDENCE_FIELDS[:3]:
                if field in evidence and not isinstance(evidence.get(field), bool):
                    raise ValueError(
                        f"manual result evidence.{field} must be bool for {normalized_key}"
                    )
            if "screenshot" in evidence and evidence.get("screenshot") is not None and not isinstance(evidence.get("screenshot"), str):
                raise ValueError(
                    f"manual result evidence.screenshot must be string for {normalized_key}"
                )
        result[normalized_key] = item
    return result


def _manual_evidence(extra: dict[str, Any]) -> dict[str, object]:
    evidence = extra.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    return {
        "device_listed": bool(evidence.get("device_listed", False)),
        "device_selected": bool(evidence.get("device_selected", False)),
        "preview_visible": bool(evidence.get("preview_visible", False)),
        "screenshot": str(evidence.get("screenshot", "")) if evidence.get("screenshot") is not None else "",
    }


def _merge_manual_results(
    verification_targets: list[dict[str, object]],
    manual_results: dict[str, dict[str, Any]],
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    for target in verification_targets:
        item = dict(target)
        extra = manual_results.get(str(item.get("id")), {})
        item["reviewed"] = str(item.get("id")) in manual_results
        item["validated"] = bool(extra.get("validated", False))
        item["result"] = str(extra.get("result", "pending"))
        item["notes"] = str(extra.get("notes", "")) if extra.get("notes") is not None else ""
        item["evidence"] = _manual_evidence(extra)
        merged.append(item)
    return merged


def build_manual_results_template(
    verification_targets: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    template: dict[str, dict[str, object]] = {}
    for item in verification_targets:
        key = str(item.get("id"))
        template[key] = {
            "name": str(item.get("name", key)),
            "ready": bool(item.get("ready", False)),
            "status": str(item.get("status", "")),
            "steps": list(item.get("steps") or []),
            "checks": list(item.get("checks") or []),
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
    return template


def _target_ids_with_result(
    verification_targets: list[dict[str, object]],
    result: str,
) -> list[str]:
    return [
        str(item.get("id"))
        for item in verification_targets
        if str(item.get("result")) == result and item.get("id")
    ]


def _unreviewed_target_ids(
    verification_targets: list[dict[str, object]],
) -> list[str]:
    return [
        str(item.get("id"))
        for item in verification_targets
        if not bool(item.get("reviewed")) and item.get("id")
    ]


def _reviewed_target_ids(
    verification_targets: list[dict[str, object]],
) -> list[str]:
    return sorted(
        str(item.get("id"))
        for item in verification_targets
        if bool(item.get("reviewed")) and item.get("id")
    )


def _target_ids_missing_preview_evidence(
    verification_targets: list[dict[str, object]],
) -> list[str]:
    missing: list[str] = []
    for item in verification_targets:
        if str(item.get("result")) != "pass":
            continue
        evidence = item.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}
        if (
            evidence.get("device_listed") is not True
            or evidence.get("device_selected") is not True
            or evidence.get("preview_visible") is not True
        ):
            app_id = item.get("id")
            if app_id:
                missing.append(str(app_id))
    return sorted(missing)


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


def _all_true_or_false_or_none(*values: object) -> bool | None:
    if values and all(value is True for value in values):
        return True
    if any(value is False for value in values):
        return False
    return None


def _pick_first_non_none(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _extract_runtime_topology(payload: dict[str, Any] | None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    runtime_snapshot = (
        dict(payload.get("runtime_snapshot", {}))
        if isinstance(payload.get("runtime_snapshot"), dict)
        else {}
    )
    runtime_topology = (
        dict(payload.get("runtime_topology", {}))
        if isinstance(payload.get("runtime_topology"), dict)
        else (
            dict(runtime_snapshot.get("runtime_topology", {}))
            if isinstance(runtime_snapshot.get("runtime_topology"), dict)
            else {}
        )
    )
    extracted: dict[str, object] = {}
    for key in (
        "runtime_topology_kind",
        "runtime_frame_path",
        "runtime_host_role",
        "runtime_host_in_frame_hot_path",
        "runtime_dedicated_host_daemon_required",
        "runtime_container_app_configured",
        "runtime_data_plane",
        "runtime_control_plane",
    ):
        value = payload.get(key)
        if value is None:
            value = runtime_topology.get(key)
        if value is not None:
            extracted[key] = value
    if extracted:
        return extracted
    if (
        payload.get("using_direct_sender") is True
        or payload.get("backend_name") == "direct_sender"
        or runtime_snapshot.get("using_direct_sender") is True
        or runtime_snapshot.get("backend_name") == "direct_sender"
    ):
        return {
            "runtime_topology_kind": "camera_extension_direct_sender",
            "runtime_frame_path": (
                "python_sdk -> cmio_sink_stream_direct -> camera_extension -> "
                "system_camera_device -> client_app"
            ),
            "runtime_host_role": "container_activation_command_bridge",
            "runtime_host_in_frame_hot_path": False,
            "runtime_dedicated_host_daemon_required": False,
            "runtime_container_app_configured": True,
            "runtime_data_plane": "cmio_sink_stream_direct",
            "runtime_control_plane": "host_activation_only",
        }
    return {}


def _normalized_path_string(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def _path_name_consistent(left: object, right: object) -> bool | None:
    left_path = _normalized_path_string(left)
    right_path = _normalized_path_string(right)
    if left_path is None or right_path is None:
        return None
    return Path(left_path).name == Path(right_path).name


def _path_equal(left: object, right: object) -> bool | None:
    left_path = _normalized_path_string(left)
    right_path = _normalized_path_string(right)
    if left_path is None or right_path is None:
        return None
    return left_path == right_path


def _blocked_flags_clear(*values: object) -> bool | None:
    known = [value for value in values if isinstance(value, bool)]
    if any(value is True for value in known):
        return False
    if known:
        return True
    return None


def _normalize_benchmark_matrix_profiles(
    benchmark_payload: dict[str, Any] | None,
) -> list[dict[str, object]] | None:
    if not isinstance(benchmark_payload, dict):
        return None
    if str(benchmark_payload.get("kind")) != "benchmark_matrix":
        return None
    results = benchmark_payload.get("results")
    if not isinstance(results, list):
        return None

    normalized: list[dict[str, object]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        profile = item.get("profile")
        acceptance = item.get("acceptance")
        metrics = item.get("metrics")
        if not isinstance(profile, dict):
            profile = {}
        if not isinstance(acceptance, dict):
            acceptance = {}
        if not isinstance(metrics, dict):
            metrics = {}
        profile_name = profile.get("name")
        if not isinstance(profile_name, str) or not profile_name:
            continue
        normalized.append(
            {
                "profile_name": profile_name,
                "width": _optional_int(profile.get("width")),
                "height": _optional_int(profile.get("height")),
                "fps": _optional_float(profile.get("fps")),
                "fps_target_met": acceptance.get("fps_target_met"),
                "cpu_target_applies": acceptance.get("cpu_target_applies"),
                "cpu_target_met": acceptance.get("cpu_target_met"),
                "actual_fps": _optional_float(metrics.get("actual_fps")),
                "cpu_percent": _optional_float(metrics.get("cpu_percent")),
                "avg_latency_ms": _optional_float(metrics.get("avg_latency_ms")),
            }
        )
    return normalized or None


def _build_summary(
    *,
    state: str,
    enabled: bool,
    approval_required: bool,
    enumerated_devices: list[str],
    readiness_payload: dict[str, Any],
    verification_targets: list[dict[str, object]],
    benchmark_payload: dict[str, Any] | None,
    demo_payload: dict[str, Any] | None,
    preflight_payload: dict[str, Any] | None,
    release_diagnostics_payload: dict[str, Any] | None,
    runtime_assets_payload: dict[str, Any] | None,
    install_session_payload: dict[str, Any] | None,
    smoke_payload: dict[str, Any] | None,
    framebus_roundtrip_payload: dict[str, Any] | None,
    status_binary_check_payload: dict[str, Any] | None,
    list_devices_binary_check_payload: dict[str, Any] | None = None,
    status_payload: dict[str, Any] | None = None,
    install_payload: dict[str, Any] | None = None,
) -> dict[str, object]:
    validated_apps = sum(1 for item in verification_targets if bool(item.get("reviewed")))
    passed_apps = sum(1 for item in verification_targets if str(item.get("result")) == "pass")
    failed_apps = sum(1 for item in verification_targets if str(item.get("result")) == "fail")
    pending_apps = sum(1 for item in verification_targets if str(item.get("result")) == "pending")
    skipped_apps = sum(1 for item in verification_targets if str(item.get("result")) == "skipped")
    passed_app_ids = _target_ids_with_result(verification_targets, "pass")
    reviewed_app_ids = _reviewed_target_ids(verification_targets)
    failed_app_ids = _target_ids_with_result(verification_targets, "fail")
    pending_app_ids = _target_ids_with_result(verification_targets, "pending")
    skipped_app_ids = _target_ids_with_result(verification_targets, "skipped")
    unreviewed_app_ids = _unreviewed_target_ids(verification_targets)
    missing_evidence_app_ids = _target_ids_missing_preview_evidence(verification_targets)
    observed_target_app_ids = sorted(
        str(item.get("id"))
        for item in verification_targets
        if item.get("id")
    )
    missing_target_app_ids = sorted(
        set(EXPECTED_TARGET_APP_IDS) - set(observed_target_app_ids)
    )
    unexpected_target_app_ids = sorted(
        set(observed_target_app_ids) - set(EXPECTED_TARGET_APP_IDS)
    )
    target_app_ids_complete = not missing_target_app_ids and not unexpected_target_app_ids
    benchmark_acceptance = None
    benchmark_kind = None
    benchmark_matrix_profiles = None
    if isinstance(benchmark_payload, dict):
        raw_benchmark_kind = benchmark_payload.get("kind")
        if isinstance(raw_benchmark_kind, str) and raw_benchmark_kind:
            benchmark_kind = raw_benchmark_kind
        else:
            benchmark_kind = "single"
        if isinstance(benchmark_payload.get("acceptance"), dict):
            benchmark_acceptance = benchmark_payload.get("acceptance")
        elif (
            str(benchmark_payload.get("kind")) == "benchmark_matrix"
            and isinstance(benchmark_payload.get("summary"), dict)
            and isinstance(benchmark_payload["summary"].get("benchmark_acceptance"), dict)
        ):
            benchmark_acceptance = benchmark_payload["summary"]["benchmark_acceptance"]
        benchmark_matrix_profiles = _normalize_benchmark_matrix_profiles(benchmark_payload)
    runtime_summary = (
        dict(runtime_assets_payload.get("summary", {}))
        if isinstance(runtime_assets_payload, dict)
        and isinstance(runtime_assets_payload.get("summary"), dict)
        else {}
    )
    runtime_resolved_assets = (
        dict(runtime_assets_payload.get("resolved_assets", {}))
        if isinstance(runtime_assets_payload, dict)
        and isinstance(runtime_assets_payload.get("resolved_assets"), dict)
        else {}
    )
    runtime_provenance = (
        dict(runtime_assets_payload.get("provenance", {}))
        if isinstance(runtime_assets_payload, dict)
        and isinstance(runtime_assets_payload.get("provenance"), dict)
        else {}
    )
    release_summary = (
        dict(release_diagnostics_payload.get("summary", {}))
        if isinstance(release_diagnostics_payload, dict)
        and isinstance(release_diagnostics_payload.get("summary"), dict)
        else {}
    )
    release_artifacts = (
        dict(release_diagnostics_payload.get("artifacts", {}))
        if isinstance(release_diagnostics_payload, dict)
        and isinstance(release_diagnostics_payload.get("artifacts"), dict)
        else {}
    )
    release_app_bundle = (
        dict(release_artifacts.get("app_bundle", {}))
        if isinstance(release_artifacts.get("app_bundle"), dict)
        else {}
    )
    release_extension_bundle = (
        dict(release_artifacts.get("extension_bundle", {}))
        if isinstance(release_artifacts.get("extension_bundle"), dict)
        else {}
    )
    release_sync_ipc_tool = (
        dict(release_artifacts.get("sync_ipc_tool", {}))
        if isinstance(release_artifacts.get("sync_ipc_tool"), dict)
        else {}
    )
    release_pkg = (
        dict(release_artifacts.get("pkg", {}))
        if isinstance(release_artifacts.get("pkg"), dict)
        else {}
    )
    release_app_bundle_path = release_app_bundle.get("path")
    release_extension_bundle_path = release_extension_bundle.get("path")
    release_sync_ipc_tool_path = release_sync_ipc_tool.get("path")
    release_pkg_path = release_pkg.get("path")
    runtime_host_bundle_path = runtime_provenance.get("host_bundle")
    runtime_extension_bundle_path = runtime_provenance.get("extension_bundle")
    runtime_sync_ipc_tool_path = runtime_resolved_assets.get("sync_ipc_tool")
    runtime_pkg_path = runtime_resolved_assets.get("pkg")
    runtime_release_host_bundle_identity_consistent = _path_name_consistent(
        runtime_host_bundle_path,
        release_app_bundle_path,
    )
    runtime_release_extension_bundle_identity_consistent = _path_name_consistent(
        runtime_extension_bundle_path,
        release_extension_bundle_path,
    )
    runtime_release_sync_ipc_tool_identity_consistent = _path_name_consistent(
        runtime_sync_ipc_tool_path,
        release_sync_ipc_tool_path,
    )
    runtime_release_pkg_identity_consistent = _path_name_consistent(
        runtime_pkg_path,
        release_pkg_path,
    )
    runtime_release_host_bundle_path_equal = _path_equal(
        runtime_host_bundle_path,
        release_app_bundle_path,
    )
    runtime_release_extension_bundle_path_equal = _path_equal(
        runtime_extension_bundle_path,
        release_extension_bundle_path,
    )
    runtime_release_sync_ipc_tool_path_equal = _path_equal(
        runtime_sync_ipc_tool_path,
        release_sync_ipc_tool_path,
    )
    runtime_release_pkg_path_equal = _path_equal(
        runtime_pkg_path,
        release_pkg_path,
    )
    runtime_release_product_identity_consistent = _all_true_or_false_or_none(
        runtime_release_host_bundle_identity_consistent,
        runtime_release_extension_bundle_identity_consistent,
        runtime_release_sync_ipc_tool_identity_consistent,
        runtime_release_pkg_identity_consistent,
    )
    runtime_release_product_path_equal = _all_true_or_false_or_none(
        runtime_release_host_bundle_path_equal,
        runtime_release_extension_bundle_path_equal,
        runtime_release_sync_ipc_tool_path_equal,
        runtime_release_pkg_path_equal,
    )
    status_result = (
        dict(status_payload)
        if isinstance(status_payload, dict)
        else {}
    )
    install_result = (
        dict(install_payload)
        if isinstance(install_payload, dict)
        else {}
    )
    install_session_install = (
        install_session_payload.get("install")
        if isinstance(install_session_payload, dict) and isinstance(install_session_payload.get("install"), dict)
        else {}
    )
    install_session_post_status = (
        install_session_payload.get("post_status")
        if isinstance(install_session_payload, dict)
        and isinstance(install_session_payload.get("post_status"), dict)
        else {}
    )
    install_session_sync_ipc = (
        install_session_payload.get("sync_ipc")
        if isinstance(install_session_payload, dict)
        and isinstance(install_session_payload.get("sync_ipc"), dict)
        else {}
    )
    install_session_uninstall = (
        install_session_payload.get("uninstall")
        if isinstance(install_session_payload, dict) and isinstance(install_session_payload.get("uninstall"), dict)
        else {}
    )
    install_smoke = smoke_payload.get("install") if isinstance(smoke_payload, dict) and isinstance(smoke_payload.get("install"), dict) else {}
    uninstall_smoke = smoke_payload.get("uninstall") if isinstance(smoke_payload, dict) and isinstance(smoke_payload.get("uninstall"), dict) else {}
    install_session_uninstall_success = (
        install_session_uninstall.get("success")
        if isinstance(install_session_uninstall.get("success"), bool)
        else (
            install_session_uninstall.get("returncode") == 0
            if install_session_uninstall
            else None
        )
    )
    smoke_uninstall_success = (
        uninstall_smoke.get("success")
        if isinstance(uninstall_smoke.get("success"), bool)
        else (
            uninstall_smoke.get("returncode") == 0
            if uninstall_smoke
            else None
        )
    )
    framebus_consistency = (
        dict(framebus_roundtrip_payload.get("consistency", {}))
        if isinstance(framebus_roundtrip_payload, dict)
        and isinstance(framebus_roundtrip_payload.get("consistency"), dict)
        else {}
    )
    framebus_observed = (
        dict(framebus_roundtrip_payload.get("observed", {}))
        if isinstance(framebus_roundtrip_payload, dict)
        and isinstance(framebus_roundtrip_payload.get("observed"), dict)
        else {}
    )
    framebus_producer = (
        dict(framebus_roundtrip_payload.get("producer_control", {}))
        if isinstance(framebus_roundtrip_payload, dict)
        and isinstance(framebus_roundtrip_payload.get("producer_control"), dict)
        else {}
    )
    status_binary_consistency = (
        dict(status_binary_check_payload.get("consistency", {}))
        if isinstance(status_binary_check_payload, dict)
        and isinstance(status_binary_check_payload.get("consistency"), dict)
        else {}
    )
    status_binary_payload = (
        dict(status_binary_check_payload.get("payload", {}))
        if isinstance(status_binary_check_payload, dict)
        and isinstance(status_binary_check_payload.get("payload"), dict)
        else {}
    )
    list_devices_binary_consistency = (
        dict(list_devices_binary_check_payload.get("consistency", {}))
        if isinstance(list_devices_binary_check_payload, dict)
        and isinstance(list_devices_binary_check_payload.get("consistency"), dict)
        else {}
    )
    list_devices_binary_result = (
        dict(list_devices_binary_check_payload.get("result", {}))
        if isinstance(list_devices_binary_check_payload, dict)
        and isinstance(list_devices_binary_check_payload.get("result"), dict)
        else (
            dict(list_devices_binary_check_payload.get("payload", {}))
            if isinstance(list_devices_binary_check_payload, dict)
            and isinstance(list_devices_binary_check_payload.get("payload"), dict)
            else {}
        )
    )
    probe_cases = (
        list_devices_binary_check_payload.get("probe_cases")
        if isinstance(list_devices_binary_check_payload, dict)
        and isinstance(list_devices_binary_check_payload.get("probe_cases"), list)
        else []
    )
    override_prefix_case = (
        dict(list_devices_binary_check_payload.get("override_prefix_case", {}))
        if isinstance(list_devices_binary_check_payload, dict)
        and isinstance(list_devices_binary_check_payload.get("override_prefix_case"), dict)
        else next(
            (
                dict(case)
                for case in probe_cases
                if isinstance(case, dict) and case.get("name") == "override_prefix_no_match"
            ),
            {},
        )
    )
    override_prefix_case_consistency = (
        dict(override_prefix_case.get("consistency", {}))
        if isinstance(override_prefix_case.get("consistency"), dict)
        else {}
    )
    framebus_direct_open_errno = framebus_observed.get("direct_open_errno")
    if framebus_direct_open_errno is not None:
        try:
            framebus_direct_open_errno = int(framebus_direct_open_errno)
        except (TypeError, ValueError):
            framebus_direct_open_errno = None
    framebus_environment_blocked = bool(
        isinstance(framebus_roundtrip_payload, dict)
        and (
            framebus_roundtrip_payload.get("environment_blocked")
            or framebus_consistency.get("environment_blocked")
            or framebus_direct_open_errno in {1, 13}
        )
    )
    demo_mode = None
    demo_width = None
    demo_height = None
    demo_fps = None
    demo_duration = None
    demo_camera_name = None
    demo_consumer_count = None
    demo_video_path = None
    demo_mode_supported = None
    demo_frame_source_kind = None
    demo_python_entrypoint_kind = None
    demo_sdk_streamer_factory_used = None
    demo_sdk_latest_provider_factory_used = None
    demo_sdk_direct_push_used = None
    demo_runtime_snapshot_present = False
    demo_runtime_snapshot_started = None
    demo_shared_memory_name = None
    demo_last_frame_format_name = None
    if isinstance(demo_payload, dict):
        runtime_snapshot = (
            dict(demo_payload.get("runtime_snapshot", {}))
            if isinstance(demo_payload.get("runtime_snapshot"), dict)
            else {}
        )
        demo_runtime_snapshot_present = bool(runtime_snapshot)
        if runtime_snapshot.get("started") is not None:
            demo_runtime_snapshot_started = bool(runtime_snapshot.get("started"))
        raw_mode = demo_payload.get("mode")
        if isinstance(raw_mode, str) and raw_mode:
            demo_mode = raw_mode
            demo_mode_supported = raw_mode in ALLOWED_DEMO_MODES
        raw_frame_source_kind = demo_payload.get("frame_source_kind")
        if isinstance(raw_frame_source_kind, str) and raw_frame_source_kind:
            demo_frame_source_kind = raw_frame_source_kind
        raw_python_entrypoint_kind = demo_payload.get("python_entrypoint_kind")
        if isinstance(raw_python_entrypoint_kind, str) and raw_python_entrypoint_kind:
            demo_python_entrypoint_kind = raw_python_entrypoint_kind
        raw_sdk_streamer_factory_used = demo_payload.get("sdk_streamer_factory_used")
        if isinstance(raw_sdk_streamer_factory_used, bool):
            demo_sdk_streamer_factory_used = raw_sdk_streamer_factory_used
        raw_sdk_latest_provider_factory_used = demo_payload.get("sdk_latest_provider_factory_used")
        if isinstance(raw_sdk_latest_provider_factory_used, bool):
            demo_sdk_latest_provider_factory_used = raw_sdk_latest_provider_factory_used
        raw_sdk_direct_push_used = demo_payload.get("sdk_direct_push_used")
        if isinstance(raw_sdk_direct_push_used, bool):
            demo_sdk_direct_push_used = raw_sdk_direct_push_used
        raw_width = demo_payload.get("width")
        if raw_width is not None:
            try:
                demo_width = int(raw_width)
            except (TypeError, ValueError):
                demo_width = None
        raw_height = demo_payload.get("height")
        if raw_height is not None:
            try:
                demo_height = int(raw_height)
            except (TypeError, ValueError):
                demo_height = None
        raw_fps = demo_payload.get("fps")
        if raw_fps is not None:
            try:
                demo_fps = float(raw_fps)
            except (TypeError, ValueError):
                demo_fps = None
        raw_duration = demo_payload.get("duration")
        if raw_duration is not None:
            try:
                demo_duration = float(raw_duration)
            except (TypeError, ValueError):
                demo_duration = None
        raw_camera_name = demo_payload.get("camera_name")
        if isinstance(raw_camera_name, str) and raw_camera_name:
            demo_camera_name = raw_camera_name
        elif isinstance(runtime_snapshot.get("camera_name"), str) and runtime_snapshot.get("camera_name"):
            demo_camera_name = str(runtime_snapshot.get("camera_name"))
        raw_consumer_count = demo_payload.get("consumer_count")
        if raw_consumer_count is not None:
            try:
                demo_consumer_count = int(raw_consumer_count)
            except (TypeError, ValueError):
                demo_consumer_count = None
        elif runtime_snapshot.get("consumer_count") is not None:
            try:
                demo_consumer_count = int(runtime_snapshot.get("consumer_count"))
            except (TypeError, ValueError):
                demo_consumer_count = None
        raw_video_path = demo_payload.get("video_path")
        if isinstance(raw_video_path, str) and raw_video_path:
            demo_video_path = raw_video_path
        raw_shared_memory_name = runtime_snapshot.get("shared_memory_name")
        if isinstance(raw_shared_memory_name, str) and raw_shared_memory_name:
            demo_shared_memory_name = raw_shared_memory_name
        raw_last_frame_format_name = runtime_snapshot.get("last_frame_format_name")
        if isinstance(raw_last_frame_format_name, str) and raw_last_frame_format_name:
            demo_last_frame_format_name = raw_last_frame_format_name
    status_start_ready = readiness_payload.get("ready")
    status_start_blocker_code = readiness_payload.get("blocker_code")
    status_blocker_ready = (
        True
        if status_start_blocker_code == "ready"
        else False
        if isinstance(status_start_blocker_code, str) and status_start_blocker_code
        else None
    )
    install_session_sync_ipc_ready = (
        _all_true_or_false_or_none(
            True if install_session_sync_ipc else None,
            install_session_sync_ipc.get("supported"),
            install_session_sync_ipc.get("success"),
        )
        if isinstance(install_session_payload, dict)
        else None
    )
    ipc_blockers_clear = _blocked_flags_clear(
        install_session_post_status.get("ipc_environment_blocked"),
        framebus_environment_blocked,
        status_binary_payload.get("ipc_environment_blocked"),
    )
    manual_validation_ready = _all_true_or_false_or_none(
        status_start_ready,
        status_blocker_ready,
        bool(enumerated_devices),
        ipc_blockers_clear,
        install_session_sync_ipc_ready,
    )
    manual_validation_complete = (
        target_app_ids_complete
        and not unreviewed_app_ids
        and len(reviewed_app_ids) == len(EXPECTED_TARGET_APP_IDS)
    )
    manual_validation_all_passed = (
        manual_validation_complete
        and passed_apps == len(EXPECTED_TARGET_APP_IDS)
        and failed_apps == 0
        and pending_apps == 0
        and skipped_apps == 0
        and not missing_evidence_app_ids
    )
    demo_runtime_topology = _extract_runtime_topology(demo_payload)
    runtime_data_plane = _pick_first_non_none(
        demo_runtime_topology.get("runtime_data_plane"),
        install_session_sync_ipc.get("ipc_transport"),
        install_session_post_status.get("ipc_transport"),
        status_result.get("ipc_transport"),
        install_result.get("ipc_transport"),
        "shared_memory_ringbuffer",
    )
    if not isinstance(runtime_data_plane, str) or not runtime_data_plane:
        runtime_data_plane = "shared_memory_ringbuffer"
    runtime_control_plane = _pick_first_non_none(
        demo_runtime_topology.get("runtime_control_plane"),
        "host_activation_plus_sync_ipc",
    )
    runtime_topology_kind = _pick_first_non_none(
        demo_runtime_topology.get("runtime_topology_kind"),
        "camera_extension_direct_framebus",
    )
    runtime_frame_path = (
        demo_runtime_topology.get("runtime_frame_path")
        or (
            f"python_sdk -> {runtime_data_plane} -> camera_extension -> "
            "system_camera_device -> client_app"
        )
    )
    return {
        "state": state,
        "enabled": bool(enabled),
        "approval_required": bool(approval_required),
        "device_visible": bool(enumerated_devices),
        "status_readiness_phase": readiness_payload.get("phase"),
        "status_start_ready": status_start_ready,
        "status_start_blocker_code": status_start_blocker_code,
        "status_shared_memory_name": status_result.get("shared_memory_name"),
        "status_mach_service_name": status_result.get("mach_service_name"),
        "status_ipc_transport": status_result.get("ipc_transport"),
        "status_install_command_notarization_missing": status_result.get(
            "install_command_notarization_missing"
        ),
        "status_system_extension_registered": status_result.get("system_extension_registered"),
        "enumerated_devices_count": len(enumerated_devices),
        "validated_apps": validated_apps,
        "passed_apps": passed_apps,
        "failed_apps": failed_apps,
        "pending_apps": pending_apps,
        "skipped_apps": skipped_apps,
        "passed_app_ids": passed_app_ids,
        "reviewed_app_ids": reviewed_app_ids,
        "failed_app_ids": failed_app_ids,
        "pending_app_ids": pending_app_ids,
        "skipped_app_ids": skipped_app_ids,
        "unreviewed_app_ids": unreviewed_app_ids,
        "observed_target_app_ids": observed_target_app_ids,
        "missing_target_app_ids": missing_target_app_ids,
        "unexpected_target_app_ids": unexpected_target_app_ids,
        "target_app_ids_complete": target_app_ids_complete,
        "manual_validation_ready": manual_validation_ready,
        "manual_validation_complete": manual_validation_complete,
        "manual_validation_all_passed": manual_validation_all_passed,
        "manual_validation_missing_evidence_app_ids": missing_evidence_app_ids,
        "benchmark_present": isinstance(benchmark_payload, dict),
        "benchmark_kind": benchmark_kind,
        "benchmark_acceptance": benchmark_acceptance,
        "benchmark_matrix_profiles": benchmark_matrix_profiles,
        "demo_present": isinstance(demo_payload, dict),
        "demo_mode": demo_mode,
        "demo_mode_supported": demo_mode_supported,
        "demo_width": demo_width,
        "demo_height": demo_height,
        "demo_fps": demo_fps,
        "demo_duration": demo_duration,
        "demo_camera_name": demo_camera_name,
        "demo_consumer_count": demo_consumer_count,
        "demo_video_path": demo_video_path,
        "demo_frame_source_kind": demo_frame_source_kind,
        "demo_python_entrypoint_kind": demo_python_entrypoint_kind,
        "demo_sdk_streamer_factory_used": demo_sdk_streamer_factory_used,
        "demo_sdk_latest_provider_factory_used": demo_sdk_latest_provider_factory_used,
        "demo_sdk_direct_push_used": demo_sdk_direct_push_used,
        "demo_runtime_snapshot_present": demo_runtime_snapshot_present,
        "demo_runtime_snapshot_started": demo_runtime_snapshot_started,
        "demo_shared_memory_name": demo_shared_memory_name,
        "demo_last_frame_format_name": demo_last_frame_format_name,
        "preflight_present": isinstance(preflight_payload, dict),
        "preflight_readiness": (
            dict(preflight_payload.get("readiness", {}))
            if isinstance(preflight_payload, dict)
            and isinstance(preflight_payload.get("readiness"), dict)
            else None
        ),
        "release_diagnostics_present": isinstance(release_diagnostics_payload, dict),
        "release_artifacts_present": (
            bool(release_summary.get("release_artifacts_present"))
            if release_summary
            else None
        ),
        "release_universal2_ready": (
            bool(release_summary.get("universal2_ready"))
            if release_summary
            else None
        ),
        "release_app_signed": (
            bool(release_summary.get("app_signed"))
            if release_summary
            else None
        ),
        "release_app_gatekeeper_accepted": release_summary.get("app_gatekeeper_accepted"),
        "release_app_stapled": release_summary.get("app_stapled"),
        "release_extension_signed": (
            bool(release_summary.get("extension_signed"))
            if release_summary
            else None
        ),
        "release_command_tools_exist": release_summary.get("command_tools_exist"),
        "release_command_tools_signed": release_summary.get("command_tools_signed"),
        "release_command_tools_universal2_ready": release_summary.get("command_tools_universal2_ready"),
        "release_sync_ipc_tool_exists": release_summary.get("sync_ipc_tool_exists"),
        "release_sync_ipc_tool_signed": release_summary.get("sync_ipc_tool_signed"),
        "release_sync_ipc_tool_universal2_ready": release_summary.get("sync_ipc_tool_universal2_ready"),
        "release_pkg_signed": release_summary.get("pkg_signed"),
        "release_pkg_gatekeeper_accepted": release_summary.get("pkg_gatekeeper_accepted"),
        "release_pkg_stapled": release_summary.get("pkg_stapled"),
        "release_pkg_install_location_expected": release_summary.get("pkg_install_location_expected"),
        "release_pkg_identifier_expected": release_summary.get("pkg_identifier_expected"),
        "release_pkg_includes_extension_payload": release_summary.get("pkg_includes_extension_payload"),
        "release_pkg_payload_appledouble_clean": release_summary.get("pkg_payload_appledouble_clean"),
        "release_host_bundle_identifier_expected": release_summary.get("host_bundle_identifier_expected"),
        "release_extension_bundle_identifier_expected": release_summary.get("extension_bundle_identifier_expected"),
        "release_minimum_system_version_expected": release_summary.get("minimum_system_version_expected"),
        "release_host_embeds_extension_bundle": release_summary.get("host_embeds_extension_bundle"),
        "release_app_bundle_path": release_app_bundle_path,
        "release_extension_bundle_path": release_extension_bundle_path,
        "release_sync_ipc_tool_path": release_sync_ipc_tool_path,
        "release_pkg_path": release_pkg_path,
        "runtime_status_tool_resolved": runtime_summary.get("status_tool_resolved"),
        "runtime_install_tool_resolved": runtime_summary.get("install_tool_resolved"),
        "runtime_devices_tool_resolved": runtime_summary.get("devices_tool_resolved"),
        "runtime_uninstall_tool_resolved": runtime_summary.get("uninstall_tool_resolved"),
        "runtime_sync_ipc_tool_resolved": runtime_summary.get("sync_ipc_tool_resolved"),
        "runtime_pkg_resolved": runtime_summary.get("pkg_resolved"),
        "runtime_packaged_assets_present": runtime_summary.get("packaged_assets_present"),
        "runtime_packaged_tools_present": runtime_summary.get("packaged_tools_present"),
        "runtime_packaged_pkg_present": runtime_summary.get("packaged_pkg_present"),
        "runtime_release_host_bundle_identity_consistent": runtime_release_host_bundle_identity_consistent,
        "runtime_release_extension_bundle_identity_consistent": runtime_release_extension_bundle_identity_consistent,
        "runtime_release_sync_ipc_tool_identity_consistent": runtime_release_sync_ipc_tool_identity_consistent,
        "runtime_release_pkg_identity_consistent": runtime_release_pkg_identity_consistent,
        "runtime_release_host_bundle_path_equal": runtime_release_host_bundle_path_equal,
        "runtime_release_extension_bundle_path_equal": runtime_release_extension_bundle_path_equal,
        "runtime_release_sync_ipc_tool_path_equal": runtime_release_sync_ipc_tool_path_equal,
        "runtime_release_pkg_path_equal": runtime_release_pkg_path_equal,
        "runtime_release_product_identity_consistent": runtime_release_product_identity_consistent,
        "runtime_release_product_path_equal": runtime_release_product_path_equal,
        "runtime_topology_kind": runtime_topology_kind,
        "runtime_frame_path": runtime_frame_path,
        "runtime_host_role": _pick_first_non_none(
            demo_runtime_topology.get("runtime_host_role"),
            "container_activation_command_bridge",
        ),
        "runtime_host_in_frame_hot_path": _pick_first_non_none(
            demo_runtime_topology.get("runtime_host_in_frame_hot_path"),
            False,
        ),
        "runtime_dedicated_host_daemon_required": _pick_first_non_none(
            demo_runtime_topology.get("runtime_dedicated_host_daemon_required"),
            False,
        ),
        "runtime_container_app_configured": _pick_first_non_none(
            demo_runtime_topology.get("runtime_container_app_configured"),
            runtime_summary.get("host_bundle_configured"),
            runtime_host_bundle_path is not None,
        ),
        "runtime_data_plane": runtime_data_plane,
        "runtime_control_plane": runtime_control_plane,
        "install_present": isinstance(install_payload, dict),
        "install_success": install_result.get("success"),
        "install_phase": install_result.get("phase"),
        "install_start_ready": install_result.get("start_ready"),
        "install_start_blocker_code": install_result.get("start_blocker_code"),
        "install_shared_memory_name": install_result.get("shared_memory_name"),
        "install_supported_formats": install_result.get("supported_formats"),
        "install_supported_frame_rates": install_result.get("supported_frame_rates"),
        "install_mach_service_name": install_result.get("mach_service_name"),
        "install_ipc_transport": install_result.get("ipc_transport"),
        "install_ipc_probe_present": install_result.get("ipc_probe_present"),
        "install_ipc_ready": install_result.get("ipc_ready"),
        "install_ipc_environment_blocked": install_result.get("ipc_environment_blocked"),
        "install_ipc_direct_open_errno": install_result.get("ipc_direct_open_errno"),
        "install_session_present": isinstance(install_session_payload, dict),
        "install_session_success": install_session_install.get("success"),
        "install_session_uninstall_success": install_session_uninstall_success,
        "install_session_uninstall_phase": install_session_uninstall.get("phase"),
        "install_session_uninstall_state": install_session_uninstall.get("state"),
        "install_session_ipc_probe_present": install_session_post_status.get("ipc_probe_present"),
        "install_session_ipc_ready": install_session_post_status.get("ipc_ready"),
        "install_session_ipc_environment_blocked": install_session_post_status.get("ipc_environment_blocked"),
        "install_session_ipc_direct_open_errno": install_session_post_status.get("ipc_direct_open_errno"),
        "install_session_sync_ipc_present": bool(install_session_sync_ipc),
        "install_session_sync_ipc_supported": install_session_sync_ipc.get("supported"),
        "install_session_sync_ipc_success": install_session_sync_ipc.get("success"),
        "install_session_sync_ipc_phase": install_session_sync_ipc.get("phase"),
        "install_session_sync_ipc_shared_memory_name": install_session_sync_ipc.get("shared_memory_name"),
        "install_session_sync_ipc_transport": install_session_sync_ipc.get("ipc_transport"),
        "install_session_sync_ipc_returncode": install_session_sync_ipc.get("returncode"),
        "smoke_present": isinstance(smoke_payload, dict),
        "smoke_install_success": install_smoke.get("success"),
        "smoke_uninstall_success": smoke_uninstall_success,
        "smoke_uninstall_phase": uninstall_smoke.get("phase"),
        "smoke_uninstall_state": uninstall_smoke.get("state"),
        "framebus_roundtrip_present": isinstance(framebus_roundtrip_payload, dict),
        "framebus_roundtrip_passed": framebus_consistency.get("all_checks_passed"),
        "framebus_roundtrip_status_ok": framebus_consistency.get("status_ok"),
        "framebus_roundtrip_direct_open_errno": framebus_direct_open_errno,
        "framebus_roundtrip_environment_blocked": framebus_environment_blocked,
        "framebus_roundtrip_producer_seq": framebus_producer.get("producer_seq"),
        "framebus_roundtrip_producer_initialized": (
            int(framebus_producer.get("producer_seq", 0)) > 0
            if framebus_producer
            else None
        ),
        "status_binary_check_present": isinstance(status_binary_check_payload, dict),
        "status_binary_check_passed": status_binary_consistency.get("all_checks_passed"),
        "status_binary_check_ipc_keys_present": status_binary_consistency.get("ipc_keys_present"),
        "status_binary_check_ipc_environment_blocked": status_binary_payload.get("ipc_environment_blocked"),
        "status_binary_check_ipc_direct_open_errno": status_binary_payload.get("ipc_direct_open_errno"),
        "list_devices_binary_check_present": isinstance(list_devices_binary_check_payload, dict),
        "list_devices_binary_check_passed": list_devices_binary_consistency.get("all_checks_passed"),
        "list_devices_binary_check_device_prefix": list_devices_binary_result.get("device_prefix"),
        "list_devices_binary_check_filtered_device_count": (
            len(list_devices_binary_result.get("devices"))
            if isinstance(list_devices_binary_result.get("devices"), list)
            else None
        ),
        "list_devices_binary_check_total_device_count": (
            len(list_devices_binary_result.get("all_devices"))
            if isinstance(list_devices_binary_result.get("all_devices"), list)
            else None
        ),
        "list_devices_binary_check_override_no_match_ok": override_prefix_case_consistency.get("all_checks_passed"),
    }


def _runtime_assets_snapshot(
    *,
    status_tool: Path | None,
    install_tool: Path | None,
    devices_tool: Path | None,
    uninstall_tool: Path | None = None,
    sync_ipc_tool: Path | None = None,
    direct_sender_library: Path | None = None,
    pkg_path: Path | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    package_install_command: list[str] | None = None,
    auto_install_package: bool = True,
) -> dict[str, object]:
    if uninstall_tool is None:
        uninstall_tool = find_macos_uninstall_tool()
    if sync_ipc_tool is None:
        sync_ipc_tool = find_macos_sync_ipc_tool()
    if direct_sender_library is None:
        direct_sender_library = find_macos_direct_sender_library()
    if pkg_path is None:
        pkg_path = find_macos_pkg()
    packaged_assets = {
        name: (PACKAGED_MACOS_RUNTIME_DIR / name).is_file()
        for name in PACKAGED_MACOS_RUNTIME_ASSETS
    }
    resolved_assets = {
        "status_tool": str(status_tool) if status_tool is not None else None,
        "install_tool": str(install_tool) if install_tool is not None else None,
        "devices_tool": str(devices_tool) if devices_tool is not None else None,
        "uninstall_tool": str(uninstall_tool) if uninstall_tool is not None else None,
        "sync_ipc_tool": str(sync_ipc_tool) if sync_ipc_tool is not None else None,
        "direct_sender_library": (
            str(direct_sender_library) if direct_sender_library is not None else None
        ),
        "pkg": str(pkg_path) if pkg_path is not None else None,
    }
    resolved_app_bundle = app_bundle or host_bundle
    resolved_app_executable = app_executable or host_executable
    host_bundle_path = str(Path(resolved_app_bundle)) if resolved_app_bundle else None
    host_executable_path = str(Path(resolved_app_executable)) if resolved_app_executable else None
    extension_bundle_path = (
        str(
            Path(resolved_app_bundle)
            / "Contents"
            / "Library"
            / "SystemExtensions"
            / "com.sidus.amaran-desktop.cameraextension.systemextension"
        )
        if resolved_app_bundle
        else None
    )
    provenance = {
        "host_bundle": host_bundle_path,
        "host_executable": host_executable_path,
        "extension_bundle": extension_bundle_path,
        "package_install_command": list(package_install_command) if package_install_command is not None else None,
        "auto_install_package": bool(auto_install_package),
    }
    return {
        "packaged_runtime_dir": str(PACKAGED_MACOS_RUNTIME_DIR),
        "packaged_assets": packaged_assets,
        "resolved_assets": resolved_assets,
        "provenance": provenance,
        "summary": {
            "status_tool_resolved": status_tool is not None,
            "install_tool_resolved": install_tool is not None,
            "devices_tool_resolved": devices_tool is not None,
            "uninstall_tool_resolved": uninstall_tool is not None,
            "sync_ipc_tool_resolved": sync_ipc_tool is not None,
            "direct_sender_library_resolved": direct_sender_library is not None,
            "pkg_resolved": pkg_path is not None,
            "host_bundle_configured": host_bundle_path is not None,
            "host_executable_configured": host_executable_path is not None,
            "extension_bundle_derived": extension_bundle_path is not None,
            "package_install_command_present": package_install_command is not None,
            "auto_install_package": bool(auto_install_package),
            "packaged_assets_present": all(packaged_assets.values()),
            "packaged_tools_present": all(
                packaged_assets[name]
                for name in (
                    "akvc-macos-status",
                    "akvc-macos-install",
                    "akvc-macos-uninstall",
                    "akvc-macos-list-devices",
                    "akvc-macos-sync-ipc",
                    "libakvc-macos-direct-sender.dylib",
                )
            ),
            "packaged_pkg_present": packaged_assets["VirtualCamera.pkg"],
        },
    }


def generate_validation_report(
    *,
    status_command: list[str] | None,
    devices_command: list[str] | None,
    install_command: list[str] | None = None,
    uninstall_tool: Path | None = None,
    sync_ipc_tool: Path | None = None,
    pkg_path: Path | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    package_install_command: list[str] | None = None,
    auto_install_package: bool = True,
    benchmark_payload: dict[str, Any] | None = None,
    demo_payload: dict[str, Any] | None = None,
    preflight_payload: dict[str, Any] | None = None,
    release_diagnostics_payload: dict[str, Any] | None = None,
    manual_results_payload: Any | None = None,
    install_session_payload: dict[str, Any] | None = None,
    smoke_payload: dict[str, Any] | None = None,
    framebus_roundtrip_payload: dict[str, Any] | None = None,
    status_binary_check_payload: dict[str, Any] | None = None,
    list_devices_binary_check_payload: dict[str, Any] | None = None,
    run_install: bool = False,
) -> dict[str, object]:
    svc = DefaultMacInstallerService(
        status_tool=str(Path(status_command[0])) if status_command else None,
        install_tool=str(Path(install_command[0])) if install_command else None,
        devices_tool=str(Path(devices_command[0])) if devices_command else None,
        uninstall_tool=str(uninstall_tool) if uninstall_tool is not None else None,
        sync_ipc_tool=str(sync_ipc_tool) if sync_ipc_tool is not None else None,
        package_path=str(pkg_path) if pkg_path is not None else None,
        app_bundle=app_bundle or host_bundle,
        app_executable=app_executable or host_executable,
        package_install_command=package_install_command,
        auto_install_package=auto_install_package,
        runner=_runner,
    )
    snapshot = inspect_extension(svc)
    status = snapshot.status
    enumerated_devices = list(snapshot.devices)
    readiness = snapshot.readiness
    verification_targets = list(readiness.verification_targets)
    manual_results = _manual_results_map(manual_results_payload)
    verification_targets = _merge_manual_results(verification_targets, manual_results)
    runtime_assets_payload = _runtime_assets_snapshot(
        status_tool=Path(status_command[0]) if status_command else None,
        install_tool=Path(install_command[0]) if install_command else None,
        devices_tool=Path(devices_command[0]) if devices_command else None,
        uninstall_tool=uninstall_tool,
        sync_ipc_tool=sync_ipc_tool,
        pkg_path=pkg_path,
        app_bundle=app_bundle,
        app_executable=app_executable,
        host_bundle=host_bundle,
        host_executable=host_executable,
        package_install_command=package_install_command,
        auto_install_package=auto_install_package,
    )

    install_payload: dict[str, object] | None = None
    if run_install and install_command is not None:
        result = svc.install_extension_result()
        install_snapshot = inspect_install_result(result)
        install_readiness = install_snapshot.readiness
        install_payload = {
            "success": result.success,
            "phase": result.phase,
            "state": result.state.value,
            "status_devices": result.status.devices,
            "status_all_devices": result.status.all_devices,
            "device_prefix": result.status.device_prefix,
            "enumerated_devices": install_snapshot.devices,
            "approval_required": result.status.approval_required,
            "enabled": result.status.enabled,
            "needs_reboot": result.status.needs_reboot,
            "bundle_path": result.status.bundle_path,
            "extension_identifier": result.status.extension_identifier,
            "host_gatekeeper_allowed": result.status.host_gatekeeper_allowed,
            "host_gatekeeper_summary": result.status.host_gatekeeper_summary,
            "host_distribution_summary": result.status.host_distribution_summary,
            "host_notarization_missing": result.status.host_notarization_missing,
            "install_command_path": result.status.install_command_path,
            "install_command_signature": result.status.install_command_signature,
            "install_command_team_identifier": result.status.install_command_team_identifier,
            "install_command_codesign_summary": result.status.install_command_codesign_summary,
            "install_command_gatekeeper_allowed": result.status.install_command_gatekeeper_allowed,
            "install_command_gatekeeper_summary": result.status.install_command_gatekeeper_summary,
            "install_command_distribution_summary": result.status.install_command_distribution_summary,
            "install_command_notarization_missing": result.status.install_command_notarization_missing,
            "system_extension_registered": result.status.system_extension_registered,
            "system_extension_registry_summary": result.status.system_extension_registry_summary,
            "shared_memory_name": result.status.shared_memory_name,
            "supported_formats": result.status.supported_formats,
            "supported_frame_rates": result.status.supported_frame_rates,
            "mach_service_name": result.status.mach_service_name,
            "ipc_transport": result.status.ipc_transport,
            "ipc_probe_present": result.status.ipc_probe_present,
            "ipc_ready": result.status.ipc_ready,
            "ipc_environment_blocked": result.status.ipc_environment_blocked,
            "ipc_last_error": result.status.ipc_last_error,
            "ipc_probe_path": result.status.ipc_probe_path,
            "ipc_direct_open_errno": result.status.ipc_direct_open_errno,
            "start_ready": install_readiness.ready,
            "start_blocker_code": install_readiness.blocker_code,
            "start_message": install_readiness.message,
            "start_steps": list(install_readiness.steps),
            "verification_targets": list(install_readiness.verification_targets),
            "last_error": result.status.last_error,
            "returncode": result.install_returncode,
            "stdout": result.install_stdout or "",
            "stderr": result.install_stderr or "",
        }

    return {
        "status": {
            "state": status.state.value,
            "devices": status.devices,
            "all_devices": status.all_devices,
            "device_prefix": status.device_prefix,
            "enumerated_devices": enumerated_devices,
            "enabled": status.enabled,
            "approval_required": status.approval_required,
            "needs_reboot": status.needs_reboot,
            "bundle_path": status.bundle_path,
            "extension_identifier": status.extension_identifier,
            "host_gatekeeper_allowed": status.host_gatekeeper_allowed,
            "host_gatekeeper_summary": status.host_gatekeeper_summary,
            "host_distribution_summary": status.host_distribution_summary,
            "host_notarization_missing": status.host_notarization_missing,
            "install_command_path": status.install_command_path,
            "install_command_signature": status.install_command_signature,
            "install_command_team_identifier": status.install_command_team_identifier,
            "install_command_codesign_summary": status.install_command_codesign_summary,
            "install_command_gatekeeper_allowed": status.install_command_gatekeeper_allowed,
            "install_command_gatekeeper_summary": status.install_command_gatekeeper_summary,
            "install_command_distribution_summary": status.install_command_distribution_summary,
            "install_command_notarization_missing": status.install_command_notarization_missing,
            "system_extension_registered": status.system_extension_registered,
            "system_extension_registry_summary": status.system_extension_registry_summary,
            "shared_memory_name": status.shared_memory_name,
            "supported_formats": status.supported_formats,
            "supported_frame_rates": status.supported_frame_rates,
            "mach_service_name": status.mach_service_name,
            "ipc_transport": status.ipc_transport,
            "last_error": status.last_error,
        },
        "install": install_payload,
        "preflight": preflight_payload,
        "release_diagnostics": release_diagnostics_payload,
        "runtime_assets": runtime_assets_payload,
        "install_session": install_session_payload,
        "smoke": smoke_payload,
        "framebus_roundtrip": framebus_roundtrip_payload,
        "status_binary_check": status_binary_check_payload,
        "list_devices_binary_check": list_devices_binary_check_payload,
        "benchmark": benchmark_payload,
        "demo": demo_payload,
        "readiness": {
            "phase": readiness.phase,
            "ready": readiness.ready,
            "blocker_code": readiness.blocker_code,
            "message": readiness.message,
            "steps": list(readiness.steps),
        },
        "verification_targets": verification_targets,
        "summary": _build_summary(
            state=status.state.value,
            enabled=status.enabled,
            approval_required=status.approval_required,
            enumerated_devices=enumerated_devices,
            readiness_payload={
                "phase": readiness.phase,
                "ready": readiness.ready,
                "blocker_code": readiness.blocker_code,
            },
            verification_targets=verification_targets,
            benchmark_payload=benchmark_payload,
            demo_payload=demo_payload,
            preflight_payload=preflight_payload,
            release_diagnostics_payload=release_diagnostics_payload,
            runtime_assets_payload=runtime_assets_payload,
            status_payload={
                "shared_memory_name": status.shared_memory_name,
                "mach_service_name": status.mach_service_name,
                "ipc_transport": status.ipc_transport,
            },
            install_payload=install_payload,
            install_session_payload=install_session_payload,
            smoke_payload=smoke_payload,
            framebus_roundtrip_payload=framebus_roundtrip_payload,
            status_binary_check_payload=status_binary_check_payload,
            list_devices_binary_check_payload=list_devices_binary_check_payload,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS validation report helper")
    parser.add_argument("--name", default="AK Virtual Camera")
    parser.add_argument("--status-tool")
    parser.add_argument("--list-devices-tool")
    parser.add_argument("--install-tool")
    parser.add_argument("--uninstall-tool")
    parser.add_argument("--sync-ipc-tool")
    parser.add_argument("--app-bundle")
    parser.add_argument("--app-executable")
    parser.add_argument("--host-bundle")
    parser.add_argument("--host-executable")
    parser.add_argument("--pkg-path")
    parser.add_argument("--installer-executable")
    parser.add_argument("--disable-auto-package", action="store_true")
    parser.add_argument("--preflight-json")
    parser.add_argument("--release-diagnostics-json")
    parser.add_argument("--install-session-json")
    parser.add_argument("--smoke-json")
    parser.add_argument("--framebus-roundtrip-json")
    parser.add_argument("--status-binary-check-json")
    parser.add_argument("--list-devices-binary-check-json")
    parser.add_argument("--benchmark-json")
    parser.add_argument("--demo-json")
    parser.add_argument("--manual-results")
    parser.add_argument("--write-manual-template")
    parser.add_argument("--run-install", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        apply_camera_name_override(args.name)
    except ValueError as exc:
        parser.error(str(exc))
    if args.app_bundle and args.host_bundle and args.app_bundle != args.host_bundle:
        parser.error("--app-bundle and --host-bundle cannot point at different macOS app bundles")
    if (
        args.app_executable
        and args.host_executable
        and args.app_executable != args.host_executable
    ):
        parser.error(
            "--app-executable and --host-executable cannot point at different macOS app executables"
        )

    status_tool = find_macos_status_tool(args.status_tool)
    if status_tool is None:
        print("status tool not found", file=sys.stderr)
        return 2

    list_devices_tool = find_macos_list_devices_tool(args.list_devices_tool)
    install_tool = find_macos_install_tool(args.install_tool)
    uninstall_tool = find_macos_uninstall_tool(args.uninstall_tool)
    sync_ipc_tool = find_macos_sync_ipc_tool(args.sync_ipc_tool)
    pkg_path = find_macos_pkg(args.pkg_path)
    package_install_command: list[str] | None = None
    if args.installer_executable:
        package_install_command = [str(args.installer_executable)]
        if args.pkg_path:
            package_install_command.extend(["-pkg", str(args.pkg_path), "-target", "/"])

    try:
        benchmark_payload = _load_json_file(args.benchmark_json)
        if benchmark_payload is not None and not isinstance(benchmark_payload, dict):
            raise ValueError("benchmark JSON must be an object")
        demo_payload = _load_json_file(args.demo_json)
        if demo_payload is not None and not isinstance(demo_payload, dict):
            raise ValueError("demo JSON must be an object")
        preflight_payload = _load_json_file(args.preflight_json)
        if preflight_payload is not None and not isinstance(preflight_payload, dict):
            raise ValueError("preflight JSON must be an object")
        release_diagnostics_payload = _load_json_file(args.release_diagnostics_json)
        if release_diagnostics_payload is not None and not isinstance(release_diagnostics_payload, dict):
            raise ValueError("release diagnostics JSON must be an object")
        install_session_payload = _load_json_file(args.install_session_json)
        if install_session_payload is not None and not isinstance(install_session_payload, dict):
            raise ValueError("install session JSON must be an object")
        smoke_payload = _load_json_file(args.smoke_json)
        if smoke_payload is not None and not isinstance(smoke_payload, dict):
            raise ValueError("smoke JSON must be an object")
        framebus_roundtrip_payload = _load_json_file(args.framebus_roundtrip_json)
        if framebus_roundtrip_payload is not None and not isinstance(framebus_roundtrip_payload, dict):
            raise ValueError("framebus roundtrip JSON must be an object")
        status_binary_check_payload = _load_json_file(args.status_binary_check_json)
        if status_binary_check_payload is not None and not isinstance(status_binary_check_payload, dict):
            raise ValueError("status binary check JSON must be an object")
        list_devices_binary_check_payload = _load_json_file(args.list_devices_binary_check_json)
        if list_devices_binary_check_payload is not None and not isinstance(list_devices_binary_check_payload, dict):
            raise ValueError("list devices binary check JSON must be an object")
        manual_results_payload = _load_json_file(args.manual_results)
        payload = generate_validation_report(
            status_command=[str(status_tool)],
            devices_command=[str(list_devices_tool)] if list_devices_tool is not None else None,
            install_command=[str(install_tool)] if install_tool is not None else None,
            uninstall_tool=uninstall_tool,
            sync_ipc_tool=sync_ipc_tool,
            pkg_path=pkg_path,
            app_bundle=args.app_bundle,
            app_executable=args.app_executable,
            host_bundle=args.host_bundle,
            host_executable=args.host_executable,
            package_install_command=package_install_command,
            auto_install_package=not args.disable_auto_package,
            benchmark_payload=benchmark_payload,
            demo_payload=demo_payload,
            preflight_payload=preflight_payload,
            release_diagnostics_payload=release_diagnostics_payload,
            install_session_payload=install_session_payload,
            smoke_payload=smoke_payload,
            framebus_roundtrip_payload=framebus_roundtrip_payload,
            status_binary_check_payload=status_binary_check_payload,
            list_devices_binary_check_payload=list_devices_binary_check_payload,
            manual_results_payload=manual_results_payload,
            run_install=bool(args.run_install),
        )
        payload["requested_camera_name"] = args.name
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.write_manual_template:
        template_payload = build_manual_results_template(payload["verification_targets"])
        template_path = Path(args.write_manual_template)
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(
            json.dumps(template_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
