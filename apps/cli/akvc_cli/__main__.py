# SPDX-License-Identifier: Apache-2.0
"""akvc CLI: register / unregister / status / doctor."""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
from pathlib import Path
from typing import Optional

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
    if issues:
        for i, msg in enumerate(issues, 1):
            print(f"[akvc] {i}. {msg}")
        return 1
    print("[akvc] all checks passed.")
    return 0


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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
