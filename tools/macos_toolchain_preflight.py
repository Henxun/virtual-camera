# SPDX-License-Identifier: Apache-2.0
"""Preflight checks for the macOS native build/sign/package toolchain."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run_capture(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "available": False,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    combined = "\n".join(
        part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
    )
    available = completed.returncode == 0 or "Usage:" in combined or "usage:" in combined
    return {
        "available": available,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _tool_status(name: str, *, version_command: list[str] | None = None) -> dict[str, Any]:
    path = _which(name)
    payload = {
        "name": name,
        "path": path,
        "present": path is not None,
    }
    if version_command is not None:
        payload["probe"] = _run_capture(version_command)
    return payload


def _xcrun_tool_status(name: str) -> dict[str, Any]:
    probe = _run_capture(["xcrun", "--find", name])
    path = probe["stdout"] if probe["available"] and probe["stdout"] else None
    return {
        "name": name,
        "path": path,
        "present": bool(path),
        "probe": probe,
    }


def _detect_identity(prefix: str, *, policy: str) -> str | None:
    probe = _run_capture(["security", "find-identity", "-v", "-p", policy])
    if not probe["available"]:
        return None
    combined = "\n".join(
        part for part in (str(probe.get("stdout", "")), str(probe.get("stderr", ""))) if part
    )
    needle = prefix.lower()
    for raw_line in combined.splitlines():
        line = raw_line.strip()
        if needle not in line.lower():
            continue
        parts = line.split('"')
        for index in range(1, len(parts), 2):
            candidate = parts[index].strip()
            if candidate.lower().startswith(needle):
                return candidate
    return None


def evaluate_preflight() -> dict[str, Any]:
    build_tools = {
        "xcodebuild": _tool_status("xcodebuild", version_command=["xcodebuild", "-version"]),
        "xcodegen": _tool_status("xcodegen", version_command=["xcodegen", "--version"]),
    }
    packaging_tools = {
        "pkgbuild": _tool_status("pkgbuild", version_command=["pkgbuild", "--help"]),
        "productsign": _tool_status("productsign", version_command=["productsign", "--help"]),
        "zip": _tool_status("zip", version_command=["zip", "-v"]),
        "hdiutil": _tool_status("hdiutil", version_command=["hdiutil", "help"]),
    }
    signing_tools = {
        "codesign": _tool_status("codesign", version_command=["codesign", "-h"]),
        "notarytool": _xcrun_tool_status("notarytool"),
        "stapler": _xcrun_tool_status("stapler"),
    }
    detected_sign_identity = _detect_identity("Developer ID Application:", policy="codesigning")
    detected_productsign_identity = _detect_identity("Developer ID Installer:", policy="basic")
    environment = {
        "sign_identity_present": bool(os.environ.get("SIGN_IDENTITY")),
        "sign_identity_auto_detected": bool(detected_sign_identity),
        "sign_identity_effective": bool(os.environ.get("SIGN_IDENTITY") or detected_sign_identity),
        "productsign_identity_present": bool(os.environ.get("PRODUCTSIGN_IDENTITY")),
        "productsign_identity_auto_detected": bool(detected_productsign_identity),
        "productsign_identity_effective": bool(
            os.environ.get("PRODUCTSIGN_IDENTITY") or detected_productsign_identity
        ),
        "notary_profile_present": bool(os.environ.get("NOTARY_PROFILE")),
    }
    readiness = {
        "can_generate_project": bool(build_tools["xcodebuild"]["present"] and build_tools["xcodegen"]["present"]),
        "can_build_native": bool(build_tools["xcodebuild"]["present"]),
        "can_package": all(bool(packaging_tools[key]["present"]) for key in ("pkgbuild", "zip", "hdiutil")),
        "can_sign": bool(signing_tools["codesign"]["present"] and environment["sign_identity_effective"]),
        "can_notarize": bool(signing_tools["notarytool"]["present"] and environment["notary_profile_present"]),
        "can_staple": bool(signing_tools["stapler"]["present"]),
    }
    return {
        "platform": {
            "sys_platform": sys.platform,
            "cwd": str(ROOT),
        },
        "build_tools": build_tools,
        "packaging_tools": packaging_tools,
        "signing_tools": signing_tools,
        "environment": environment,
        "readiness": readiness,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS toolchain preflight helper")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_preflight()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
