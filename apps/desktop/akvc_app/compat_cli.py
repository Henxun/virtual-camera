# SPDX-License-Identifier: Apache-2.0
"""Compatibility CLI shim for AKVC status/doctor/register flows."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

CLSID = "{8E14549A-DB61-4309-AFA1-3578E927E933}"


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
        repo / "build" / "bin" / "Release" / "akvc-dshow.dll",
        repo / "build" / "bin" / "akvc-dshow.dll",
        Path(r"C:\Program Files\AKVC\bin\akvc-dshow.dll"),
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
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("[akvc] not running on Windows; skipping checks.")
        return 0

    issues: list[str] = []
    if not _read_inproc_path():
        issues.append("Filter is not registered (run: akvc register).")
    if not _find_dshow_dll():
        issues.append("Cannot locate built DLL (run: python tools/make.py build).")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
