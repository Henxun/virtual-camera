# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS toolchain preflight helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_toolchain_preflight.py"


def test_macos_toolchain_preflight_tool_exists_and_references_expected_tools() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "xcodebuild" in text
    assert "xcodegen" in text
    assert "pkgbuild" in text
    assert "productsign" in text
    assert "notarytool" in text
    assert "stapler" in text
    assert '"pkgbuild", "--help"' in text
    assert '"productsign", "--help"' in text
    assert '"hdiutil", "help"' in text
    assert '"codesign", "-h"' in text
    assert '"security", "find-identity"' in text
    assert "can_generate_project" in text
    assert "can_notarize" in text
    assert "sign_identity_effective" in text
    assert "productsign_identity_effective" in text


def test_macos_toolchain_preflight_tool_reports_expected_sections() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "platform" in payload
    assert "build_tools" in payload
    assert "packaging_tools" in payload
    assert "signing_tools" in payload
    assert "environment" in payload
    assert "readiness" in payload
    assert "xcodebuild" in payload["build_tools"]
    assert "xcodegen" in payload["build_tools"]
    assert "pkgbuild" in payload["packaging_tools"]
    assert "codesign" in payload["signing_tools"]
    assert "notarytool" in payload["signing_tools"]
    assert "can_generate_project" in payload["readiness"]
    assert "can_build_native" in payload["readiness"]
    assert "can_package" in payload["readiness"]
    assert "sign_identity_effective" in payload["environment"]
    assert "productsign_identity_effective" in payload["environment"]
