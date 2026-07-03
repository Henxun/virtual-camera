# SPDX-License-Identifier: Apache-2.0
"""macOS virtual camera smoke validation helper.

This script is intentionally lightweight so it can run on developer machines,
CI runners, or notarization staging hosts. It focuses on install/status
plumbing and tool discovery; camera-app compatibility validation remains a
manual or lab-driven step for now.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECT_PUSH_DEMO_TOOL = ROOT / "tools" / "macos_direct_push_demo.py"
DEFAULT_DIRECT_SENDER_OBJECT_DEMO_TOOL = ROOT / "tools" / "macos_direct_sender_object_demo.py"
sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.platforms.macos.installer import (  # noqa: E402
    DefaultMacInstallerService,
    inspect_extension,
    inspect_install_result,
    build_runtime_snapshot,
)
from akvc.platforms.macos.ipc import apply_camera_name_override  # noqa: E402
from akvc.runtime import (  # noqa: E402
    find_macos_install_tool,
    find_macos_list_devices_tool,
    find_macos_status_tool,
    find_macos_uninstall_tool,
)


def _runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _tool_path(kind: str, explicit: str | None) -> Path | None:
    if kind == "status":
        return find_macos_status_tool(explicit)
    if kind == "install":
        return find_macos_install_tool(explicit)
    if kind == "list-devices":
        return find_macos_list_devices_tool(explicit)
    if kind == "uninstall":
        return find_macos_uninstall_tool(explicit)
    raise ValueError(kind)


def _print_payload(title: str, payload: dict) -> None:
    print(f"[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


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


def _direct_push_request_config(
    *,
    frames: int | None,
    frame_kind: str | None,
    entrypoint: str | None,
    allow_shared_memory_fallback: bool,
    request_camera_access: bool,
) -> dict[str, object]:
    return {
        "requested_frames": frames,
        "requested_frame_kind": frame_kind,
        "requested_entrypoint": entrypoint,
        "allow_shared_memory_fallback": bool(allow_shared_memory_fallback),
        "requested_camera_access": bool(request_camera_access),
    }


def _run_direct_push_demo(
    *,
    demo_tool: Path,
    name: str,
    frames: int | None,
    frame_kind: str | None = None,
    entrypoint: str | None = None,
    allow_shared_memory_fallback: bool = False,
    request_camera_access: bool = False,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    direct_sender_library: str | None = None,
) -> dict[str, object]:
    request_config = _direct_push_request_config(
        frames=frames,
        frame_kind=frame_kind,
        entrypoint=entrypoint,
        allow_shared_memory_fallback=allow_shared_memory_fallback,
        request_camera_access=request_camera_access,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        report_json = Path(tmpdir) / "direct-push-report.json"
        cmd = [
            sys.executable,
            str(demo_tool),
            "--name",
            name,
            "--report-json",
            str(report_json),
        ]
        if request_camera_access:
            cmd.append("--request-camera-access")
        if app_bundle:
            cmd.extend(["--app-bundle", str(app_bundle)])
        if app_executable:
            cmd.extend(["--app-executable", str(app_executable)])
        if direct_sender_library:
            cmd.extend(["--direct-sender-library", str(direct_sender_library)])
        if frames is not None:
            cmd.extend(["--frames", str(frames)])
        if frame_kind:
            cmd.extend(["--frame-kind", str(frame_kind)])
        if entrypoint:
            cmd.extend(["--entrypoint", str(entrypoint)])
        if allow_shared_memory_fallback:
            cmd.append("--allow-shared-memory-fallback")
        completed = _runner(cmd)
        payload = _load_json_object(report_json)
        probe_payload = None
        if completed.returncode != 0 and payload is None:
            probe_report_json = Path(tmpdir) / "direct-push-probe-report.json"
            probe_cmd = [
                sys.executable,
                str(demo_tool),
                "--name",
                name,
                "--probe-only",
                "--report-json",
                str(probe_report_json),
            ]
            if request_camera_access:
                probe_cmd.append("--request-camera-access")
            if app_bundle:
                probe_cmd.extend(["--app-bundle", str(app_bundle)])
            if app_executable:
                probe_cmd.extend(["--app-executable", str(app_executable)])
            if direct_sender_library:
                probe_cmd.extend(["--direct-sender-library", str(direct_sender_library)])
            if frame_kind:
                probe_cmd.extend(["--frame-kind", str(frame_kind)])
            if entrypoint:
                probe_cmd.extend(["--entrypoint", str(entrypoint)])
            if allow_shared_memory_fallback:
                probe_cmd.append("--allow-shared-memory-fallback")
            probe_completed = _runner(probe_cmd)
            probe_payload = _load_json_object(probe_report_json)
            if probe_payload is None:
                probe_payload = {
                    "mode": "direct-push",
                    "probe_only": True,
                    "camera_name": name,
                    "probe_command_returncode": probe_completed.returncode,
                }
            if payload is None:
                payload = probe_payload
        return {
            "attempted": True,
            "skipped": False,
            "request": request_config,
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "payload": payload,
            "probe_payload": probe_payload,
        }


def _direct_sender_object_request_config(
    *,
    frames: int | None,
    frame_kind: str | None,
    request_camera_access: bool,
) -> dict[str, object]:
    return {
        "requested_frames": frames,
        "requested_frame_kind": frame_kind,
        "requested_camera_access": bool(request_camera_access),
    }


def _run_direct_sender_object_demo(
    *,
    demo_tool: Path,
    name: str,
    frames: int | None,
    frame_kind: str | None = None,
    request_camera_access: bool = False,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    direct_sender_library: str | None = None,
) -> dict[str, object]:
    request_config = _direct_sender_object_request_config(
        frames=frames,
        frame_kind=frame_kind,
        request_camera_access=request_camera_access,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        report_json = Path(tmpdir) / "direct-sender-object-report.json"
        cmd = [
            sys.executable,
            str(demo_tool),
            "--name",
            name,
            "--report-json",
            str(report_json),
        ]
        if request_camera_access:
            cmd.append("--request-camera-access")
        if app_bundle:
            cmd.extend(["--app-bundle", str(app_bundle)])
        if app_executable:
            cmd.extend(["--app-executable", str(app_executable)])
        if direct_sender_library:
            cmd.extend(["--direct-sender-library", str(direct_sender_library)])
        if frames is not None:
            cmd.extend(["--frames", str(frames)])
        if frame_kind:
            cmd.extend(["--frame-kind", str(frame_kind)])
        completed = _runner(cmd)
        payload = _load_json_object(report_json)
        probe_payload = None
        if completed.returncode != 0 and payload is None:
            probe_report_json = Path(tmpdir) / "direct-sender-object-probe-report.json"
            probe_cmd = [
                sys.executable,
                str(demo_tool),
                "--name",
                name,
                "--inspect-only",
                "--report-json",
                str(probe_report_json),
            ]
            if request_camera_access:
                probe_cmd.append("--request-camera-access")
            if app_bundle:
                probe_cmd.extend(["--app-bundle", str(app_bundle)])
            if app_executable:
                probe_cmd.extend(["--app-executable", str(app_executable)])
            if direct_sender_library:
                probe_cmd.extend(["--direct-sender-library", str(direct_sender_library)])
            if frame_kind:
                probe_cmd.extend(["--frame-kind", str(frame_kind)])
            probe_completed = _runner(probe_cmd)
            probe_payload = _load_json_object(probe_report_json)
            if probe_payload is None:
                probe_payload = {
                    "mode": "direct-sender-object",
                    "inspect_only": True,
                    "camera_name": name,
                    "probe_command_returncode": probe_completed.returncode,
                }
            if payload is None:
                payload = probe_payload
        return {
            "attempted": True,
            "skipped": False,
            "request": request_config,
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "payload": payload,
            "probe_payload": probe_payload,
        }


def _status_payload(svc: CommandMacInstallerService) -> dict[str, object]:
    snapshot = inspect_extension(svc)
    status = snapshot.status
    enumerated_devices = snapshot.devices
    phase = snapshot.readiness.phase
    readiness = snapshot.readiness
    return {
        "state": status.state.value,
        "phase": phase,
        "devices": status.devices,
        "all_devices": status.all_devices,
        "device_prefix": status.device_prefix,
        "enumerated_devices": enumerated_devices,
        "enabled": status.enabled,
        "approval_required": status.approval_required,
        "needs_reboot": status.needs_reboot,
        "bundle_path": status.bundle_path,
        "host_signature": status.host_signature,
        "host_team_identifier": status.host_team_identifier,
        "host_codesign_summary": status.host_codesign_summary,
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
        "extension_identifier": status.extension_identifier,
        "shared_memory_name": status.shared_memory_name,
        "supported_formats": status.supported_formats,
        "supported_frame_rates": status.supported_frame_rates,
        "mach_service_name": status.mach_service_name,
        "ipc_transport": status.ipc_transport,
        "ipc_probe_present": status.ipc_probe_present,
        "ipc_ready": status.ipc_ready,
        "ipc_environment_blocked": status.ipc_environment_blocked,
        "ipc_last_error": status.ipc_last_error,
        "ipc_probe_path": status.ipc_probe_path,
        "ipc_direct_open_errno": status.ipc_direct_open_errno,
        "start_ready": readiness.ready,
        "start_blocker_code": readiness.blocker_code,
        "start_message": readiness.message,
        "start_steps": list(readiness.steps),
        "verification_targets": list(readiness.verification_targets),
        "last_error": status.last_error,
    }


def _uninstall_payload(result) -> dict[str, object]:
    snapshot = build_runtime_snapshot(
        status=result.status,
        devices=list(result.enumerated_devices),
        phase=result.phase,
    )
    readiness = snapshot.readiness
    return {
        "success": result.success,
        "phase": result.phase,
        "state": result.state.value,
        "status_devices": result.status.devices,
        "status_all_devices": result.status.all_devices,
        "device_prefix": result.status.device_prefix,
        "enumerated_devices": list(result.enumerated_devices),
        "approval_required": result.status.approval_required,
        "enabled": result.status.enabled,
        "needs_reboot": result.status.needs_reboot,
        "bundle_path": result.status.bundle_path,
        "host_signature": result.status.host_signature,
        "host_team_identifier": result.status.host_team_identifier,
        "host_codesign_summary": result.status.host_codesign_summary,
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
        "extension_identifier": result.status.extension_identifier,
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
        "start_ready": readiness.ready,
        "start_blocker_code": readiness.blocker_code,
        "start_message": readiness.message,
        "start_steps": list(readiness.steps),
        "verification_targets": list(readiness.verification_targets),
        "last_error": result.status.last_error,
        "returncode": result.uninstall_returncode,
        "stdout": result.uninstall_stdout or "",
        "stderr": result.uninstall_stderr or "",
    }


def _payload_from_snapshot(snapshot) -> dict[str, object]:
    status = snapshot.status
    readiness = snapshot.readiness
    return {
        "state": status.state.value,
        "phase": readiness.phase,
        "devices": status.devices,
        "all_devices": status.all_devices,
        "device_prefix": status.device_prefix,
        "enumerated_devices": list(snapshot.devices),
        "enabled": status.enabled,
        "approval_required": status.approval_required,
        "needs_reboot": status.needs_reboot,
        "bundle_path": status.bundle_path,
        "host_signature": status.host_signature,
        "host_team_identifier": status.host_team_identifier,
        "host_codesign_summary": status.host_codesign_summary,
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
        "extension_identifier": status.extension_identifier,
        "shared_memory_name": status.shared_memory_name,
        "supported_formats": status.supported_formats,
        "supported_frame_rates": status.supported_frame_rates,
        "mach_service_name": status.mach_service_name,
        "ipc_transport": status.ipc_transport,
        "ipc_probe_present": status.ipc_probe_present,
        "ipc_ready": status.ipc_ready,
        "ipc_environment_blocked": status.ipc_environment_blocked,
        "ipc_last_error": status.ipc_last_error,
        "ipc_probe_path": status.ipc_probe_path,
        "ipc_direct_open_errno": status.ipc_direct_open_errno,
        "start_ready": readiness.ready,
        "start_blocker_code": readiness.blocker_code,
        "start_message": readiness.message,
        "start_steps": list(readiness.steps),
        "verification_targets": list(readiness.verification_targets),
        "last_error": status.last_error,
    }


def _effective_status_after_install_payload(svc: DefaultMacInstallerService, result) -> dict[str, object]:
    current_status = _status_payload(svc)
    if (
        result.phase == "pending_approval"
        and current_status.get("phase") != "pending_approval"
        and current_status.get("start_ready") is not True
        and current_status.get("start_blocker_code") in {"waiting_for_install", "unknown", None}
    ):
        return _payload_from_snapshot(inspect_install_result(result))
    if (
        current_status.get("phase") == "timeout_waiting_for_install"
        and result.phase == "pending_approval"
    ):
        return _payload_from_snapshot(inspect_install_result(result))
    return current_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS smoke validator")
    parser.add_argument("--name", default="AK Virtual Camera")
    parser.add_argument("--status-tool")
    parser.add_argument("--install-tool")
    parser.add_argument("--list-devices-tool")
    parser.add_argument("--uninstall-tool")
    parser.add_argument("--sync-ipc-tool")
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
    parser.add_argument("--pkg-path")
    parser.add_argument("--app-bundle")
    parser.add_argument("--app-executable")
    parser.add_argument("--host-bundle")
    parser.add_argument("--host-executable")
    parser.add_argument("--direct-sender-library")
    parser.add_argument("--installer-executable")
    parser.add_argument("--disable-auto-package", action="store_true")
    parser.add_argument("--framebus-roundtrip-json")
    parser.add_argument("--run-install", action="store_true")
    parser.add_argument("--run-uninstall", action="store_true")
    parser.add_argument("--run-direct-push-demo", action="store_true")
    parser.add_argument("--run-direct-sender-object-demo", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        apply_camera_name_override(args.name)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        app_bundle, app_executable = _resolve_container_app_args(
            app_bundle=args.app_bundle,
            app_executable=args.app_executable,
            host_bundle=args.host_bundle,
            host_executable=args.host_executable,
        )
    except ValueError as exc:
        parser.error(str(exc))

    status_tool = _tool_path("status", args.status_tool)
    install_tool = _tool_path("install", args.install_tool)
    list_devices_tool = _tool_path("list-devices", args.list_devices_tool)
    uninstall_tool = _tool_path("uninstall", args.uninstall_tool)

    if status_tool is None:
        print("status tool not found", file=sys.stderr)
        return 2

    package_install_command: list[str] | None = None
    if args.installer_executable:
        package_install_command = [str(args.installer_executable)]
        if args.pkg_path:
            package_install_command.extend(["-pkg", str(args.pkg_path), "-target", "/"])

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool) if install_tool is not None else None,
        uninstall_tool=str(uninstall_tool) if uninstall_tool is not None else None,
        devices_tool=str(list_devices_tool) if list_devices_tool is not None else None,
        sync_ipc_tool=args.sync_ipc_tool,
        package_path=args.pkg_path,
        app_bundle=app_bundle,
        app_executable=app_executable,
        package_install_command=package_install_command,
        auto_install_package=not args.disable_auto_package,
        framebus_roundtrip_json=args.framebus_roundtrip_json,
        runner=_runner,
    )

    report: dict[str, object] = {
        "requested_camera_name": args.name,
        "status": _status_payload(svc),
        "install": None,
        "status_after_install": None,
        "uninstall": None,
        "status_after_uninstall": None,
        "direct_push_demo": None,
        "direct_sender_object_demo": None,
    }
    _print_payload("status", dict(report["status"]))

    exit_code = 0
    if args.run_install:
        result = svc.install_extension_result()
        snapshot = inspect_install_result(result)
        readiness = snapshot.readiness
        payload = {
            "success": result.success,
            "phase": result.phase,
            "state": result.state.value,
            "status_devices": result.status.devices,
            "status_all_devices": result.status.all_devices,
            "device_prefix": result.status.device_prefix,
            "enumerated_devices": snapshot.devices,
            "approval_required": result.status.approval_required,
            "enabled": result.status.enabled,
            "needs_reboot": result.status.needs_reboot,
            "bundle_path": result.status.bundle_path,
        "host_signature": result.status.host_signature,
        "host_team_identifier": result.status.host_team_identifier,
        "host_codesign_summary": result.status.host_codesign_summary,
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
        "extension_identifier": result.status.extension_identifier,
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
            "start_ready": readiness.ready,
            "start_blocker_code": readiness.blocker_code,
            "start_message": readiness.message,
            "start_steps": list(readiness.steps),
            "verification_targets": list(readiness.verification_targets),
            "last_error": result.status.last_error,
            "returncode": result.install_returncode,
            "stdout": result.install_stdout or "",
            "stderr": result.install_stderr or "",
        }
        report["install"] = payload
        _print_payload("install", payload)
        if not result.success:
            exit_code = max(exit_code, 1)
        status_after_install = _effective_status_after_install_payload(svc, result)
        report["status_after_install"] = status_after_install
        _print_payload("status_after_install", status_after_install)

    if args.run_uninstall:
        if uninstall_tool is None:
            print("uninstall tool not found", file=sys.stderr)
            exit_code = 2
        else:
            result = svc.uninstall_extension_result()
            payload = _uninstall_payload(result)
            report["uninstall"] = payload
            _print_payload("uninstall", payload)
            if not result.success:
                exit_code = max(exit_code, 1)
            status_after_uninstall = _status_payload(svc)
            report["status_after_uninstall"] = status_after_uninstall
            _print_payload("status_after_uninstall", status_after_uninstall)

    if args.run_direct_push_demo:
        direct_push_tool = Path(args.direct_push_demo_tool)
        active_status = (
            report["status_after_install"]
            if isinstance(report.get("status_after_install"), dict)
            else report["status"]
        )
        start_ready = (
            active_status.get("start_ready") is True
            if isinstance(active_status, dict)
            else False
        )
        if not start_ready:
            report["direct_push_demo"] = {
                "attempted": False,
                "skipped": True,
                "skip_reason": (
                    active_status.get("start_blocker_code")
                    if isinstance(active_status, dict)
                    else "start_not_ready"
                ),
                "request": _direct_push_request_config(
                    frames=args.direct_push_frames,
                    frame_kind=args.direct_push_frame_kind,
                    entrypoint=args.direct_push_entrypoint,
                    allow_shared_memory_fallback=bool(
                        args.direct_push_allow_shared_memory_fallback
                    ),
                    request_camera_access=bool(args.direct_push_request_camera_access),
                ),
            }
        elif not direct_push_tool.is_file():
            print(f"direct push demo tool not found: {direct_push_tool}", file=sys.stderr)
            return 2
        else:
            direct_push_payload = _run_direct_push_demo(
                demo_tool=direct_push_tool,
                name=args.name,
                frames=args.direct_push_frames,
                frame_kind=args.direct_push_frame_kind,
                entrypoint=args.direct_push_entrypoint,
                allow_shared_memory_fallback=bool(args.direct_push_allow_shared_memory_fallback),
                request_camera_access=bool(args.direct_push_request_camera_access),
                app_bundle=app_bundle,
                app_executable=app_executable,
                direct_sender_library=args.direct_sender_library,
            )
            report["direct_push_demo"] = direct_push_payload
            _print_payload("direct_push_demo", direct_push_payload)
            if int(direct_push_payload["returncode"]) != 0:
                exit_code = max(exit_code, 1)

    if args.run_direct_sender_object_demo:
        direct_sender_object_tool = Path(args.direct_sender_object_demo_tool)
        active_status = (
            report["status_after_install"]
            if isinstance(report.get("status_after_install"), dict)
            else report["status"]
        )
        start_ready = (
            active_status.get("start_ready") is True
            if isinstance(active_status, dict)
            else False
        )
        if not start_ready:
            report["direct_sender_object_demo"] = {
                "attempted": False,
                "skipped": True,
                "skip_reason": (
                    active_status.get("start_blocker_code")
                    if isinstance(active_status, dict)
                    else "start_not_ready"
                ),
                "request": _direct_sender_object_request_config(
                    frames=args.direct_sender_object_frames,
                    frame_kind=args.direct_sender_object_frame_kind,
                    request_camera_access=bool(args.direct_sender_object_request_camera_access),
                ),
            }
        elif not direct_sender_object_tool.is_file():
            print(
                f"direct sender object demo tool not found: {direct_sender_object_tool}",
                file=sys.stderr,
            )
            return 2
        else:
            direct_sender_object_payload = _run_direct_sender_object_demo(
                demo_tool=direct_sender_object_tool,
                name=args.name,
                frames=args.direct_sender_object_frames,
                frame_kind=args.direct_sender_object_frame_kind,
                request_camera_access=bool(args.direct_sender_object_request_camera_access),
                app_bundle=app_bundle,
                app_executable=app_executable,
                direct_sender_library=args.direct_sender_library,
            )
            report["direct_sender_object_demo"] = direct_sender_object_payload
            _print_payload("direct_sender_object_demo", direct_sender_object_payload)
            if int(direct_sender_object_payload["returncode"]) != 0:
                exit_code = max(exit_code, 1)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
