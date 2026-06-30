# SPDX-License-Identifier: Apache-2.0
"""akvc CLI: register / unregister / status / doctor."""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
from pathlib import Path
from typing import Optional

from akvc.core.helper.client import DEFAULT_PERSISTENT_LOG, DEFAULT_TASK_NAME, HelperService
from akvc.runtime import find_dshow_dll

CLSID = "{8E14549A-DB61-4309-AFA1-3578E927E933}"
FRIENDLY_NAME = "AK Virtual Camera"


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
    dll = Path(args.dll) if args.dll else _find_dll()
    if dll is None:
        # Try registered path
        registered = _read_inproc_path()
        if registered:
            dll = Path(registered)
    if dll is None or not dll.is_file():
        print("[akvc] cannot find akvc-dshow.dll. Pass --dll PATH.", file=sys.stderr)
        return 2
    if not _is_admin():
        print("[akvc] unregister requires Administrator.", file=sys.stderr)
        return 3
    print(f"[akvc] regsvr32 /u /s {dll}")
    rc = subprocess.call(["regsvr32", "/u", "/s", str(dll)])
    if rc != 0:
        print(f"[akvc] regsvr32 returned {rc}", file=sys.stderr)
    else:
        print("[akvc] unregistered.")
    return rc


def cmd_status(args: argparse.Namespace) -> int:
    print(f"[akvc] CLSID:      {CLSID}")
    path = _read_inproc_path()
    print(f"[akvc] Inproc DLL: {path or '(not registered)'}")
    found = _find_dll()
    print(f"[akvc] Build DLL:  {found or '(not built)'}")
    return 0


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
    p_stat.set_defaults(func=cmd_status)

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

    p_helper_start = helper_sub.add_parser("start", help="Start helper or installed task")
    p_helper_start.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_start.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="Scheduled task name")
    p_helper_start.add_argument("--installed-only", action="store_true", help="Only use the installed task")
    p_helper_start.set_defaults(func=cmd_helper_start)

    p_helper_register_mf = helper_sub.add_parser("register-mf", help="Register the MF virtual camera via the helper")
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
