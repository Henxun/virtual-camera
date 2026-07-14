# SPDX-License-Identifier: Apache-2.0
"""Compatibility CLI shim for AKVC status/doctor/register flows."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

CLSID = "{8E14549A-DB61-4309-AFA1-3578E927E933}"
HELPER_PIPE = r"\\.\pipe\akvc-helper-ctrl"


def _is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _find_dshow_dll() -> Optional[Path]:
    env = os.environ.get("AKVC_DSHOW_DLL")
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate

    repo = _repo_root()
    candidates = [
        repo / "build" / "bin" / "dshow" / "Release" / "akvc-dshow.dll",
        repo / "build" / "bin" / "Release" / "akvc-dshow.dll",
        repo / "build" / "bin" / "akvc-dshow.dll",
        Path(r"C:\Program Files\AKVC\bin\akvc-dshow.dll"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None




def _find_helper_exe(path: str | None = None) -> Optional[Path]:
    if path:
        candidate = Path(path)
        if candidate.is_file():
            return candidate

    env = os.environ.get("AKVC_HELPER_EXE")
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate

    repo = _repo_root()
    candidates = [
        repo / "build" / "bin" / "Release" / "akvc_helper.exe",
        repo / "build" / "bin" / "akvc_helper.exe",
        repo / "akvc" / "_runtime" / "windows" / "akvc_helper.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _read_inproc_path() -> Optional[str]:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{CLSID}\InprocServer32") as key:
            value, _ = winreg.QueryValueEx(key, None)
            return str(value)
    except FileNotFoundError:
        return None


def _helper_pipe_reachable(timeout_ms: int = 250) -> bool:
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32
    kernel32.WaitNamedPipeW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    kernel32.WaitNamedPipeW.restype = ctypes.c_int
    return bool(kernel32.WaitNamedPipeW(HELPER_PIPE, timeout_ms))


def _run_make_command(*args: str) -> int:
    repo = _repo_root()
    cmd = [sys.executable, str(repo / "tools" / "make.py"), *args]
    return int(subprocess.call(cmd, cwd=str(repo)))

def cmd_register(args: argparse.Namespace) -> int:
    dll = Path(args.dll) if args.dll else _find_dshow_dll()
    if dll is None or not dll.is_file():
        print("[akvc] cannot find akvc-dshow.dll. Pass --dll PATH.", file=sys.stderr)
        return 2
    if not _is_admin():
        print("[akvc] register requires Administrator. Re-run from elevated shell.", file=sys.stderr)
        return 3
    print(f"[akvc] regsvr32 /s {dll}")
    rc = subprocess.call(["regsvr32", "/s", str(dll)])
    if rc == 0:
        print("[akvc] registered.")
    else:
        print(f"[akvc] regsvr32 returned {rc}", file=sys.stderr)
    return int(rc)


def cmd_unregister(args: argparse.Namespace) -> int:
    dll = Path(args.dll) if args.dll else _find_dshow_dll()
    if dll is None:
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
    if rc == 0:
        print("[akvc] unregistered.")
    else:
        print(f"[akvc] regsvr32 returned {rc}", file=sys.stderr)
    return int(rc)






def cmd_status(args: argparse.Namespace) -> int:
    print(f"[akvc] CLSID:      {CLSID}")
    print(f"[akvc] Inproc DLL: {_read_inproc_path() or '(not registered)'}")
    print(f"[akvc] Build DLL:  {_find_dshow_dll() or '(not built)'}")
    print(f"[akvc] Helper EXE: {_find_helper_exe() or '(not found)'}")
    print(f"[akvc] Helper pipe reachable: {'yes' if _helper_pipe_reachable() else 'no'}")
    return 0


def cmd_helper_status(args: argparse.Namespace) -> int:
    helper = _find_helper_exe(getattr(args, 'exe', None))
    print(f"[akvc] Helper EXE: {helper or '(not found)'}")
    print(f"[akvc] Helper pipe reachable: {'yes' if _helper_pipe_reachable() else 'no'}")
    return 0 if helper is not None else 1


def cmd_helper_install(args: argparse.Namespace) -> int:
    helper = _find_helper_exe(getattr(args, 'exe', None))
    if helper is None:
        print("[akvc] cannot find akvc_helper.exe. Pass --exe PATH.", file=sys.stderr)
        return 2
    print(f"[akvc] helper install prepared: {helper}")
    return 0


def cmd_helper_start(args: argparse.Namespace) -> int:
    helper = _find_helper_exe(getattr(args, 'exe', None))
    if helper is None:
        print("[akvc] cannot find akvc_helper.exe. Pass --exe PATH.", file=sys.stderr)
        return 2
    if _helper_pipe_reachable():
        print("[akvc] helper already running.")
        return 0
    creation_flags = 0x08000000 if sys.platform == 'win32' else 0
    log_path = Path(os.environ.get("TEMP", str(Path.home()))) / "akvc-helper-cli.log"
    try:
        subprocess.Popen(
            [str(helper), "--persistent", "true", "--log", str(log_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except Exception as exc:
        print(f"[akvc] failed to start helper: {exc}", file=sys.stderr)
        return 1

    deadline = time.time() + 8.0
    while time.time() < deadline:
        if _helper_pipe_reachable():
            print(f"[akvc] helper running. log={log_path}")
            return 0
        time.sleep(0.1)
    print(f"[akvc] helper did not expose control pipe in time. log={log_path}", file=sys.stderr)
    return 1


def cmd_helper_register_mf(args: argparse.Namespace) -> int:
    if not _helper_pipe_reachable():
        print("[akvc] helper pipe not reachable. Run `akvc helper start` first.", file=sys.stderr)
        return 1
    return _run_make_command('register-mf', '--name', args.name)

def cmd_doctor(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("[akvc] not running on Windows; skipping checks.")
        return 0

    issues: list[str] = []
    if not _read_inproc_path():
        issues.append("Filter is not registered (run: akvc register).")
    if not _find_dshow_dll():
        issues.append("Cannot locate built DLL (run: python tools/make.py build).")
    if not _find_helper_exe():
        issues.append("Cannot locate akvc_helper.exe (install virtual-camera/apps/desktop runtime assets).")
    if issues:
        for index, issue in enumerate(issues, 1):
            print(f"[akvc] {index}. {issue}")
        return 1
    print("[akvc] all checks passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="akvc", description="AK Virtual Camera compatibility CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_reg = sub.add_parser("register", help="Register the DShow filter")
    p_reg.add_argument("--dll", help="Path to akvc-dshow.dll")
    p_reg.set_defaults(func=cmd_register)

    p_unreg = sub.add_parser("unregister", help="Unregister the DShow filter")
    p_unreg.add_argument("--dll", help="Path to akvc-dshow.dll")
    p_unreg.set_defaults(func=cmd_unregister)

    p_status = sub.add_parser("status", help="Show compatibility runtime status")
    p_status.set_defaults(func=cmd_status)

    p_doctor = sub.add_parser("doctor", help="Run compatibility self-checks")
    p_doctor.set_defaults(func=cmd_doctor)

    p_helper = sub.add_parser("helper", help="Manage the AKVC helper runtime")
    helper_sub = p_helper.add_subparsers(dest="helper_cmd", required=True)

    p_helper_status = helper_sub.add_parser("status", help="Show helper runtime state")
    p_helper_status.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_status.set_defaults(func=cmd_helper_status)

    p_helper_install = helper_sub.add_parser("install", help="Validate helper install surface")
    p_helper_install.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_install.set_defaults(func=cmd_helper_install)

    p_helper_start = helper_sub.add_parser("start", help="Start helper and wait for control pipe")
    p_helper_start.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_start.set_defaults(func=cmd_helper_start)

    p_helper_register_mf = helper_sub.add_parser("register-mf", help="Register/repair MF virtual camera")
    p_helper_register_mf.add_argument("--exe", help="Path to akvc_helper.exe")
    p_helper_register_mf.add_argument("--name", default="AK Virtual Camera", help="Friendly camera name")
    p_helper_register_mf.set_defaults(func=cmd_helper_register_mf)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
