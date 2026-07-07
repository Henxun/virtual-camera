# SPDX-License-Identifier: Apache-2.0
"""Executable checks for the macOS uninstall helper."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "installer" / "macos" / "uninstall.sh"


def test_macos_uninstall_script_uses_current_and_legacy_tool_locations() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert 'source "${ROOT}/installer/macos/common.sh"' in text
    assert 'akvc_autodetect_container_app_bundle "/Applications"' in text
    assert "build/macos/Build/Products/Release/akvc-macos-uninstall" in text
    assert "build/macos/bin/akvc-macos-uninstall" in text
    assert 'APP_PATH}" != "/"' in text


def test_macos_uninstall_script_invokes_tool_and_removes_app(tmp_path) -> None:
    if sys.platform != "darwin":
        return

    app_path = tmp_path / "Applications" / "Amaran Desktop.app"
    app_path.mkdir(parents=True, exist_ok=True)

    marker = tmp_path / "uninstall-invoked.txt"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    uninstall_tool.write_text(
        "#!/usr/bin/env bash\n"
        f"echo invoked > '{marker}'\n",
        encoding="utf-8",
    )
    uninstall_tool.chmod(
        uninstall_tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    completed = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(ROOT),
        env={
            **os.environ,
            "APP_PATH": str(app_path),
            "UNINSTALL_TOOL": str(uninstall_tool),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert marker.is_file()
    assert not app_path.exists()


def test_macos_uninstall_script_does_not_remove_root_path(tmp_path) -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'APP_PATH}" != "/"' in text
