# SPDX-License-Identifier: Apache-2.0
"""akvc CLI: register / unregister / status / doctor."""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from akvc.helper_service import (
    DEFAULT_PERSISTENT_LOG,
    DEFAULT_TASK_NAME,
    HelperService,
)
from akvc.runtime import find_dshow_dll

CLSID = "{8E14549A-DB61-4309-AFA1-3578E927E933}"

def _load_macos_cli_bindings():
    from akvc.sdk.virtual_camera import VirtualCamera
    from akvc.platforms.macos.installer import (
        describe_manual_app_validation_gates,
        describe_runtime_topology,
        evaluate_extension_readiness,
        infer_extension_phase,
        inspect_install_result,
        load_manual_app_validation_summary,
        open_macos_install_settings,
    )

    return {
        "VirtualCamera": VirtualCamera,
        "describe_manual_app_validation_gates": describe_manual_app_validation_gates,
        "describe_runtime_topology": describe_runtime_topology,
        "evaluate_extension_readiness": evaluate_extension_readiness,
        "infer_extension_phase": infer_extension_phase,
        "inspect_install_result": inspect_install_result,
        "load_manual_app_validation_summary": load_manual_app_validation_summary,
        "open_macos_install_settings": open_macos_install_settings,
    }




def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _print_key_values(payload: dict) -> None:
    for key, value in payload.items():
        if isinstance(value, list) and all(not isinstance(item, dict) for item in value):
            rendered = ", ".join(str(item) for item in value) if value else "(none)"
        elif isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            rendered = value
        print(f"[akvc] {key}: {rendered}")


def _merge_manual_app_validation_payload(payload: dict) -> None:
    bindings = _load_macos_cli_bindings()
    summary = bindings["load_manual_app_validation_summary"]()
    failed_labels = bindings["describe_manual_app_validation_gates"](summary.failed_criteria)
    unknown_labels = bindings["describe_manual_app_validation_gates"](summary.unknown_criteria)
    blocker_labels = bindings["describe_manual_app_validation_gates"](summary.blockers)
    payload["manual_app_validation_present"] = summary.present
    payload["manual_app_validation_ready"] = summary.ready
    payload["manual_app_validation_failed_criteria"] = failed_labels
    payload["manual_app_validation_unknown_criteria"] = unknown_labels
    payload["manual_app_validation_blockers"] = blocker_labels
    payload["manual_app_validation_failed_criteria_ids"] = list(summary.failed_criteria)
    payload["manual_app_validation_unknown_criteria_ids"] = list(summary.unknown_criteria)
    payload["manual_app_validation_blocker_ids"] = list(summary.blockers)
    payload["manual_app_validation_manifest_path"] = summary.manifest_path


def _merge_runtime_topology_payload(payload: dict, status) -> None:
    bindings = _load_macos_cli_bindings()
    payload.update(bindings["describe_runtime_topology"](status))


def _resolve_macos_container_app_overrides(args: argparse.Namespace) -> tuple[str | None, str | None]:
    app_bundle = getattr(args, "app_bundle", None)
    app_executable = getattr(args, "app_executable", None)
    host_bundle = getattr(args, "host_bundle", None)
    host_executable = getattr(args, "host_executable", None)
    if app_bundle and host_bundle and app_bundle != host_bundle:
        raise ValueError("--app-bundle and --host-bundle cannot point at different macOS app bundles")
    if app_executable and host_executable and app_executable != host_executable:
        raise ValueError(
            "--app-executable and --host-executable cannot point at different macOS app executables"
        )
    resolved_bundle = app_bundle or host_bundle
    resolved_executable = app_executable or host_executable
    if resolved_bundle and resolved_executable:
        raise ValueError("--app-bundle/--host-bundle and --app-executable/--host-executable are mutually exclusive")
    return resolved_bundle, resolved_executable


def _macos_virtual_camera_kwargs(args: argparse.Namespace) -> dict[str, object]:
    app_bundle, app_executable = _resolve_macos_container_app_overrides(args)
    kwargs: dict[str, object] = {}
    if app_bundle:
        kwargs["app_bundle"] = app_bundle
    if app_executable:
        kwargs["app_executable"] = app_executable
    return kwargs


def _is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _find_dll() -> Optional[Path]:
    """Locate akvc-dshow.dll for packaged installs and dev builds."""
    return find_dshow_dll()


def _read_inproc_path() -> Optional[str]:
    """Read HKCR\\CLSID\\{...}\\InprocServer32 default value."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        key_path = rf"CLSID\{CLSID}\InprocServer32"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path) as k:
            val, _ = winreg.QueryValueEx(k, None)
            return val
    except FileNotFoundError:
        return None


def cmd_register(args: argparse.Namespace) -> int:
    dll = Path(args.dll) if args.dll else _find_dll()
    if dll is None or not dll.is_file():
        print(f"[akvc] cannot find akvc-dshow.dll. Pass --dll PATH.", file=sys.stderr)
        return 2
    if not _is_admin():
        print("[akvc] register requires Administrator. Re-run from elevated shell.", file=sys.stderr)
        return 3
    print(f"[akvc] regsvr32 /s {dll}")
    rc = subprocess.call(["regsvr32", "/s", str(dll)])
    if rc != 0:
        print(f"[akvc] regsvr32 returned {rc}", file=sys.stderr)
    else:
        print("[akvc] registered.")
    return rc


def cmd_unregister(args: argparse.Namespace) -> int:
    registered = _read_inproc_path()
    dll = Path(args.dll) if args.dll else _find_dll()
    if dll is None and registered:
        dll = Path(registered)

    if not _is_admin():
        print("[akvc] unregister requires Administrator.", file=sys.stderr)
        return 3

    helper = HelperService()
    helper_ok = helper.ensure_running(task_name=DEFAULT_TASK_NAME)
    mf_ok = False
    if helper_ok:
        mf_ok = helper.unregister_mf()
        if mf_ok:
            print("[akvc] MF virtual camera removed or already absent.")
        else:
            print("[akvc] failed to remove MF virtual camera.", file=sys.stderr)
    else:
        print(f"[akvc] {helper.last_error_message or 'failed to start helper for MF unregister.'}", file=sys.stderr)

    dshow_ok = False
    if registered:
        target = Path(registered)
        print(f"[akvc] regsvr32 /u /s {target}")
        dshow_rc = subprocess.call(["regsvr32", "/u", "/s", str(target)])
        if dshow_rc != 0:
            print(f"[akvc] regsvr32 returned {dshow_rc}", file=sys.stderr)
        else:
            print("[akvc] DShow filter unregistered.")
            dshow_ok = True
    elif dll is not None and dll.is_file():
        print("[akvc] DShow filter already absent.")
        dshow_ok = True
    else:
        print("[akvc] DShow filter already absent and no DLL lookup was needed.")
        dshow_ok = True

    return 0 if mf_ok and dshow_ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    if sys.platform == "darwin":
        bindings = _load_macos_cli_bindings()
        VirtualCamera = bindings["VirtualCamera"]
        infer_extension_phase = bindings["infer_extension_phase"]
        evaluate_extension_readiness = bindings["evaluate_extension_readiness"]
        try:
            camera = VirtualCamera(**_macos_virtual_camera_kwargs(args))
        except ValueError as exc:
            print(f"[akvc] {exc}", file=sys.stderr)
            return 2
        snapshot_factory = getattr(camera, "inspect_installation", None)
        if callable(snapshot_factory):
            snapshot = snapshot_factory()
            status = snapshot.status
            devices = list(snapshot.devices)
            phase = snapshot.readiness.phase
            readiness = snapshot.readiness
        else:
            status = camera.status()
            devices = camera.enumerate_devices()
            phase = infer_extension_phase(
                approval_required=bool(status.approval_required),
                enabled=bool(status.enabled),
                devices=devices,
            )
            readiness = evaluate_extension_readiness(
                status=status,
                devices=devices,
                phase=phase,
            )
        payload = {
            "state": status.state.value,
            "phase": phase,
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
            "shared_memory_name": status.shared_memory_name,
            "mach_service_name": status.mach_service_name,
            "ipc_transport": status.ipc_transport,
            "ipc_probe_present": status.ipc_probe_present,
            "ipc_ready": status.ipc_ready,
            "ipc_environment_blocked": status.ipc_environment_blocked,
            "ipc_last_error": status.ipc_last_error,
            "ipc_probe_path": status.ipc_probe_path,
            "ipc_direct_open_errno": status.ipc_direct_open_errno,
            "devices": devices,
            "status_devices": status.devices,
            "status_all_devices": status.all_devices,
            "device_prefix": status.device_prefix,
            "start_ready": readiness.ready,
            "start_blocker_code": readiness.blocker_code,
            "start_message": readiness.message,
            "start_steps": readiness.steps,
            "verification_targets": readiness.verification_targets,
            "last_error": status.last_error,
        }
        _merge_runtime_topology_payload(payload, status)
        _merge_manual_app_validation_payload(payload)
        if getattr(args, "json", False):
            _print_json(payload)
        else:
            _print_key_values(payload)
        return 0

    print(f"[akvc] CLSID:      {CLSID}")
    path = _read_inproc_path()
    print(f"[akvc] Inproc DLL: {path or '(not registered)'}")
    found = _find_dll()
    print(f"[akvc] Build DLL:  {found or '(not built)'}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        print("[akvc] install is macOS only.", file=sys.stderr)
        return 2

    try:
        bindings = _load_macos_cli_bindings()
        VirtualCamera = bindings["VirtualCamera"]
        inspect_install_result = bindings["inspect_install_result"]
        camera = VirtualCamera(**_macos_virtual_camera_kwargs(args))
    except ValueError as exc:
        print(f"[akvc] {exc}", file=sys.stderr)
        return 2
    result = camera.install_extension_result()
    assert result is not None
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
        "shared_memory_name": result.status.shared_memory_name,
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
        "start_steps": readiness.steps,
        "verification_targets": readiness.verification_targets,
        "last_error": result.status.last_error,
        "returncode": result.install_returncode,
        "stdout": result.install_stdout,
        "stderr": result.install_stderr,
    }
    _merge_runtime_topology_payload(payload, result.status)
    _merge_manual_app_validation_payload(payload)
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_key_values(payload)
    return 0 if result.success else 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        print("[akvc] uninstall is macOS only.", file=sys.stderr)
        return 2

    try:
        bindings = _load_macos_cli_bindings()
        VirtualCamera = bindings["VirtualCamera"]
        inspect_install_result = bindings["inspect_install_result"]
        camera = VirtualCamera(**_macos_virtual_camera_kwargs(args))
    except ValueError as exc:
        print(f"[akvc] {exc}", file=sys.stderr)
        return 2
    result = camera.uninstall_extension_result()
    if result is None:
        print("[akvc] macOS uninstall result unavailable.", file=sys.stderr)
        return 2

    payload = {
        "success": result.success,
        "phase": result.phase,
        "state": result.state.value,
        "status_devices": result.status.devices,
        "status_all_devices": result.status.all_devices,
        "device_prefix": result.status.device_prefix,
        "enumerated_devices": result.enumerated_devices,
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
        "shared_memory_name": result.status.shared_memory_name,
        "mach_service_name": result.status.mach_service_name,
        "ipc_transport": result.status.ipc_transport,
        "last_error": result.status.last_error,
        "returncode": result.uninstall_returncode,
        "stdout": result.uninstall_stdout,
        "stderr": result.uninstall_stderr,
    }
    _merge_runtime_topology_payload(payload, result.status)
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_key_values(payload)
    return 0 if result.success else 1


def cmd_sync_ipc(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        print("[akvc] sync-ipc is macOS only.", file=sys.stderr)
        return 2

    try:
        bindings = _load_macos_cli_bindings()
        VirtualCamera = bindings["VirtualCamera"]
        camera = VirtualCamera(**_macos_virtual_camera_kwargs(args))
    except ValueError as exc:
        print(f"[akvc] {exc}", file=sys.stderr)
        return 2
    sync_result = camera.sync_ipc_configuration_result(args.shared_memory_name)
    if sync_result is None:
        print("[akvc] macOS IPC sync result unavailable.", file=sys.stderr)
        return 2

    payload = {
        "supported": sync_result.supported,
        "success": sync_result.success,
        "phase": sync_result.phase,
        "shared_memory_name": sync_result.shared_memory_name,
        "ipc_transport": sync_result.ipc_transport,
        "last_error": sync_result.last_error,
        "returncode": sync_result.returncode,
        "stdout": sync_result.stdout,
        "stderr": sync_result.stderr,
    }
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_key_values(payload)
    if not sync_result.supported:
        return 2
    return 0 if sync_result.success else 1


def cmd_open_settings(args: argparse.Namespace) -> int:
    del args
    if sys.platform != "darwin":
        print("[akvc] open-settings is macOS only.", file=sys.stderr)
        return 2
    rc = _load_macos_cli_bindings()["open_macos_install_settings"]()
    if rc == 0:
        print("[akvc] opened System Settings.")
        return 0
    print(f"[akvc] failed to open System Settings (rc={rc})", file=sys.stderr)
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    issues: list[str] = []
    if sys.platform != "win32":
        print("[akvc] not running on Windows; skipping checks.")
        return 0
    if not _read_inproc_path():
        issues.append("Filter is not registered (run: akvc register).")
    if not _find_dll():
        issues.append("Cannot locate built DLL (run: python tools/make.py build).")
    helper = HelperService()
    helper_status = helper.scheduled_task_status()
    if not helper_status.get("installed"):
        issues.append("Persistent helper is not installed (run: akvc helper install).")
    if issues:
        for i, msg in enumerate(issues, 1):
            print(f"[akvc] {i}. {msg}")
        return 1
    print("[akvc] all checks passed.")
    return 0


def cmd_helper_install(args: argparse.Namespace) -> int:
    helper = HelperService(helper_exe=args.exe)
    ok = helper.install_autostart(task_name=args.task_name, log_path=args.log)
    if not ok:
        print(f"[akvc] {helper.last_error_message or 'failed to install helper autostart.'}", file=sys.stderr)
        return 1
    print(f"[akvc] installed helper task {args.task_name}.")
    return 0


def cmd_helper_uninstall(args: argparse.Namespace) -> int:
    helper = HelperService()
    ok = helper.uninstall_autostart(task_name=args.task_name)
    if not ok:
        print(f"[akvc] {helper.last_error_message or 'failed to uninstall helper autostart.'}", file=sys.stderr)
        return 1
    print(f"[akvc] uninstalled helper task {args.task_name}.")
    return 0


def cmd_helper_start(args: argparse.Namespace) -> int:
    helper = HelperService(helper_exe=args.exe)
    ok = helper.start_installed(task_name=args.task_name) if args.installed_only else helper.ensure_running(task_name=args.task_name)
    if not ok:
        print(f"[akvc] {helper.last_error_message or 'failed to start helper.'}", file=sys.stderr)
        return 1
    print(f"[akvc] helper reachable on {helper.scheduled_task_status(args.task_name).get('task_name', args.task_name)}.")
    return 0


def cmd_helper_register_mf(args: argparse.Namespace) -> int:
    helper = HelperService(helper_exe=args.exe)
    if not helper.ensure_running(task_name=args.task_name):
        print(f"[akvc] {helper.last_error_message or 'failed to start helper.'}", file=sys.stderr)
        return 1
    ok = helper.register_mf(name=args.name)
    if not ok:
        print("[akvc] failed to register MF virtual camera.", file=sys.stderr)
        return 1
    print(f"[akvc] MF virtual camera registered as {args.name}.")
    return 0


def cmd_helper_stop(args: argparse.Namespace) -> int:
    helper = HelperService()
    helper.stop()
    print("[akvc] helper stop requested.")
    return 0


def cmd_helper_status(args: argparse.Namespace) -> int:
    helper = HelperService()
    task = helper.scheduled_task_status(args.task_name)
    runtime = helper.status()
    print(f"[akvc] Helper task:     {task.get('task_name', args.task_name)}")
    print(f"[akvc] Installed:       {bool(task.get('installed'))}")
    print(f"[akvc] Pipe reachable:  {bool(task.get('pipe_reachable'))}")
    if runtime is None:
        print("[akvc] Runtime status:  (helper not responding)")
    else:
        print(f"[akvc] Helper PID:      {runtime.get('pid')}")
        print(f"[akvc] Heartbeat 100ns: {runtime.get('heartbeat_100ns')}")
        print(f"[akvc] Producer seq:    {runtime.get('producer_seq')}")
    return 0 if task.get("installed") or task.get("pipe_reachable") else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="akvc", description="AK Virtual Camera CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_reg = sub.add_parser("register", help="Register the DShow filter")
    p_reg.add_argument("--dll", help="Path to akvc-dshow.dll")
    p_reg.set_defaults(func=cmd_register)

    p_unreg = sub.add_parser("unregister", help="Unregister the DShow filter")
    p_unreg.add_argument("--dll", help="Path to akvc-dshow.dll")
    p_unreg.set_defaults(func=cmd_unregister)

    p_stat = sub.add_parser("status", help="Show registration + build status")
    p_stat.add_argument("--json", action="store_true", help="Emit JSON output")
    p_stat.add_argument("--app-bundle", help="Explicit macOS container app bundle to inspect")
    p_stat.add_argument("--app-executable", help="Explicit macOS container app executable to inspect")
    p_stat.add_argument("--host-bundle", help="Legacy alias for --app-bundle")
    p_stat.add_argument("--host-executable", help="Legacy alias for --app-executable")
    p_stat.set_defaults(func=cmd_status)

    p_install = sub.add_parser("install", help="Install / activate the virtual camera on macOS")
    p_install.add_argument("--json", action="store_true", help="Emit JSON output")
    p_install.add_argument("--app-bundle", help="Explicit macOS container app bundle to install/activate")
    p_install.add_argument("--app-executable", help="Explicit macOS container app executable to install/activate")
    p_install.add_argument("--host-bundle", help="Legacy alias for --app-bundle")
    p_install.add_argument("--host-executable", help="Legacy alias for --app-executable")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Uninstall / deactivate the virtual camera on macOS")
    p_uninstall.add_argument("--json", action="store_true", help="Emit JSON output")
    p_uninstall.add_argument("--app-bundle", help="Explicit macOS container app bundle to uninstall/deactivate")
    p_uninstall.add_argument("--app-executable", help="Explicit macOS container app executable to uninstall/deactivate")
    p_uninstall.add_argument("--host-bundle", help="Legacy alias for --app-bundle")
    p_uninstall.add_argument("--host-executable", help="Legacy alias for --app-executable")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_sync = sub.add_parser("sync-ipc", help="Sync macOS virtual camera IPC configuration")
    p_sync.add_argument("--json", action="store_true", help="Emit JSON output")
    p_sync.add_argument("--shared-memory-name", help="Override shared memory name before syncing")
    p_sync.add_argument("--app-bundle", help="Explicit macOS container app bundle to target for IPC sync")
    p_sync.add_argument("--app-executable", help="Explicit macOS container app executable to target for IPC sync")
    p_sync.add_argument("--host-bundle", help="Legacy alias for --app-bundle")
    p_sync.add_argument("--host-executable", help="Legacy alias for --app-executable")
    p_sync.set_defaults(func=cmd_sync_ipc)

    p_open_settings = sub.add_parser(
        "open-settings",
        help="Open the relevant macOS System Settings page for Camera Extension approval",
    )
    p_open_settings.set_defaults(func=cmd_open_settings)

    p_doc = sub.add_parser("doctor", help="Self-check")
    p_doc.set_defaults(func=cmd_doctor)

    p_helper = sub.add_parser("helper", help="Manage the persistent MF helper")
    helper_sub = p_helper.add_subparsers(dest="helper_cmd", required=True)

    p_helper_install = helper_sub.add_parser("install", help="Install helper autostart")
    p_helper_install.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_install.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Scheduled task name")
    p_helper_install.add_argument("--log", default=DEFAULT_PERSISTENT_LOG, help="Persistent helper log path")
    p_helper_install.set_defaults(func=cmd_helper_install)

    p_helper_uninstall = helper_sub.add_parser("uninstall", help="Remove helper autostart")
    p_helper_uninstall.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Scheduled task name")
    p_helper_uninstall.set_defaults(func=cmd_helper_uninstall)

    p_helper_start = helper_sub.add_parser("start", help="Start the helper process only (does not register the MF camera)")
    p_helper_start.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_start.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Scheduled task name")
    p_helper_start.add_argument("--installed-only", action="store_true", help="Only use the installed task")
    p_helper_start.set_defaults(func=cmd_helper_start)

    p_helper_register_mf = helper_sub.add_parser("register-mf", help="Register or repair the MF virtual camera via the helper")
    p_helper_register_mf.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_register_mf.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Scheduled task name")
    p_helper_register_mf.add_argument("--name", default="AK Virtual Camera", help="MF virtual camera friendly name")
    p_helper_register_mf.set_defaults(func=cmd_helper_register_mf)

    p_helper_stop = helper_sub.add_parser("stop", help="Stop the running helper")
    p_helper_stop.set_defaults(func=cmd_helper_stop)

    p_helper_status = helper_sub.add_parser("status", help="Show helper install and runtime status")
    p_helper_status.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Scheduled task name")
    p_helper_status.set_defaults(func=cmd_helper_status)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
