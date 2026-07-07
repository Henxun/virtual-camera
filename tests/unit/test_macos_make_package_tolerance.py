# SPDX-License-Identifier: Apache-2.0
"""Unit tests for macOS packaging tolerance paths in tools.make."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from tools import make as make_tool


def test_cmd_package_macos_tolerates_headless_dmg_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_tool.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(make_tool, "cmd_build_macos", lambda args: 0)
    monkeypatch.setattr(make_tool, "_effective_macos_sign_identity", lambda: None)

    pkg_path = tmp_path / "VirtualCamera.pkg"
    zip_path = tmp_path / "VirtualCamera.zip"
    monkeypatch.setattr(make_tool, "MACOS_PKG", pkg_path)
    monkeypatch.setattr(make_tool, "MACOS_DMG", tmp_path / "VirtualCamera.dmg")
    monkeypatch.setattr(make_tool, "MACOS_ZIP", zip_path)

    calls: list[tuple[str, bool]] = []

    def fake_run(script: Path, *, env=None, args=None, capture_output=False):
        calls.append((script.name, capture_output))
        if script == make_tool.MACOS_BUILD_PKG_SCRIPT:
            pkg_path.write_text("pkg", encoding="utf-8")
            return subprocess.CompletedProcess([script.name], 0, "", "")
        if script == make_tool.MACOS_BUILD_DMG_SCRIPT:
            return subprocess.CompletedProcess(
                [script.name],
                1,
                "",
                "hdiutil: create failed - device not configured\n",
            )
        if script == make_tool.MACOS_BUILD_ZIP_SCRIPT:
            zip_path.write_text("zip", encoding="utf-8")
            return subprocess.CompletedProcess([script.name], 0, "", "")
        raise AssertionError(script)

    monkeypatch.setattr(make_tool, "_run_macos_script_result", fake_run)

    rc = make_tool.cmd_package_macos(argparse.Namespace(skip_build=True))

    assert rc == 0
    assert pkg_path.is_file()
    assert zip_path.is_file()
    assert calls == [
        ("build_pkg.sh", False),
        ("build_dmg.sh", True),
        ("build_zip.sh", False),
    ]


def test_cmd_package_macos_fails_on_non_headless_dmg_error(monkeypatch) -> None:
    monkeypatch.setattr(make_tool.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(make_tool, "cmd_build_macos", lambda args: 0)
    monkeypatch.setattr(make_tool, "_effective_macos_sign_identity", lambda: None)

    def fake_run(script: Path, *, env=None, args=None, capture_output=False):
        if script == make_tool.MACOS_BUILD_PKG_SCRIPT:
            return subprocess.CompletedProcess([script.name], 0, "", "")
        if script == make_tool.MACOS_BUILD_DMG_SCRIPT:
            return subprocess.CompletedProcess([script.name], 7, "", "unexpected dmg failure\n")
        raise AssertionError(script)

    monkeypatch.setattr(make_tool, "_run_macos_script_result", fake_run)

    rc = make_tool.cmd_package_macos(argparse.Namespace(skip_build=True))

    assert rc == 7


def test_cmd_package_macos_can_sync_runtime_assets(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_tool.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(make_tool, "cmd_build_macos", lambda args: 0)
    monkeypatch.setattr(make_tool, "_effective_macos_sign_identity", lambda: None)

    pkg_path = tmp_path / "VirtualCamera.pkg"
    zip_path = tmp_path / "VirtualCamera.zip"
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(make_tool, "MACOS_PKG", pkg_path)
    monkeypatch.setattr(make_tool, "MACOS_DMG", tmp_path / "VirtualCamera.dmg")
    monkeypatch.setattr(make_tool, "MACOS_ZIP", zip_path)
    monkeypatch.setattr(make_tool, "MACOS_RUNTIME_DIR", runtime_dir)

    sync_calls: list[bool] = []

    def fake_run(script: Path, *, env=None, args=None, capture_output=False):
        if script == make_tool.MACOS_BUILD_PKG_SCRIPT:
            pkg_path.write_text("pkg", encoding="utf-8")
            return subprocess.CompletedProcess([script.name], 0, "", "")
        if script == make_tool.MACOS_BUILD_DMG_SCRIPT:
            return subprocess.CompletedProcess(
                [script.name],
                1,
                "",
                "hdiutil: create failed - device not configured\n",
            )
        if script == make_tool.MACOS_BUILD_ZIP_SCRIPT:
            zip_path.write_text("zip", encoding="utf-8")
            return subprocess.CompletedProcess([script.name], 0, "", "")
        raise AssertionError(script)

    def fake_sync(*, require_pkg: bool) -> int:
        sync_calls.append(require_pkg)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(make_tool, "_run_macos_script_result", fake_run)
    monkeypatch.setattr(make_tool, "_sync_macos_runtime_assets", fake_sync)

    rc = make_tool.cmd_package_macos(argparse.Namespace(skip_build=True, sync_runtime=True))

    assert rc == 0
    assert sync_calls == [True]


def test_cmd_package_macos_auto_signs_when_identity_is_detected(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_tool.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(make_tool, "cmd_build_macos", lambda args: 0)
    monkeypatch.setattr(
        make_tool,
        "_effective_macos_sign_identity",
        lambda: "Developer ID Application: Example",
    )

    pkg_path = tmp_path / "VirtualCamera.pkg"
    zip_path = tmp_path / "VirtualCamera.zip"
    monkeypatch.setattr(make_tool, "MACOS_PKG", pkg_path)
    monkeypatch.setattr(make_tool, "MACOS_DMG", tmp_path / "VirtualCamera.dmg")
    monkeypatch.setattr(make_tool, "MACOS_ZIP", zip_path)

    calls: list[str] = []

    def fake_sign(args: argparse.Namespace) -> int:
        del args
        calls.append("sign")
        return 0

    def fake_run(script: Path, *, env=None, args=None, capture_output=False):
        del env, args, capture_output
        calls.append(script.name)
        if script == make_tool.MACOS_BUILD_PKG_SCRIPT:
            pkg_path.write_text("pkg", encoding="utf-8")
            return subprocess.CompletedProcess([script.name], 0, "", "")
        if script == make_tool.MACOS_BUILD_DMG_SCRIPT:
            return subprocess.CompletedProcess(
                [script.name],
                1,
                "",
                "hdiutil: create failed - device not configured\n",
            )
        if script == make_tool.MACOS_BUILD_ZIP_SCRIPT:
            zip_path.write_text("zip", encoding="utf-8")
            return subprocess.CompletedProcess([script.name], 0, "", "")
        raise AssertionError(script)

    monkeypatch.setattr(make_tool, "cmd_sign_macos", fake_sign)
    monkeypatch.setattr(make_tool, "_run_macos_script_result", fake_run)

    rc = make_tool.cmd_package_macos(argparse.Namespace(skip_build=True))

    assert rc == 0
    assert calls == ["sign", "build_pkg.sh", "build_dmg.sh", "build_zip.sh"]


def test_cmd_build_macos_tolerates_namespace_without_python_flag(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_tool.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(make_tool, "_require_tool", lambda tool: tool)
    monkeypatch.setattr(make_tool, "_macos_effective_archs", lambda args: "arm64 x86_64")
    monkeypatch.setattr(make_tool, "_macos_effective_deployment_target", lambda args: "13.0")
    monkeypatch.setattr(make_tool, "MACOS_ROOT", tmp_path)
    monkeypatch.setattr(make_tool, "MACOS_BUILD", tmp_path / "build")
    monkeypatch.setattr(make_tool, "MACOS_EXT_BUNDLE", tmp_path / "build" / "com.sidus.amaran-desktop.cameraextension.systemextension")
    monkeypatch.setattr(make_tool, "MACOS_STATUS_TOOL", tmp_path / "build" / "akvc-macos-status")
    monkeypatch.setattr(make_tool, "MACOS_INSTALL_TOOL", tmp_path / "build" / "akvc-macos-install")

    proj = tmp_path / "akvc-macos.xcodeproj"
    proj.mkdir(parents=True, exist_ok=True)

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs) -> int:
        del kwargs
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    rc = make_tool.cmd_build_macos(argparse.Namespace())

    assert rc == 0
    assert calls == [
        [
            "xcodebuild",
            "-project",
            str(proj),
            "-scheme",
            "akvc-macos-all",
            "-configuration",
            "Release",
            "-derivedDataPath",
            str(tmp_path / "build"),
            "ARCHS=arm64 x86_64",
            "ONLY_ACTIVE_ARCH=NO",
            "MACOSX_DEPLOYMENT_TARGET=13.0",
            "build",
            "CODE_SIGNING_ALLOWED=NO",
            "CODE_SIGNING_REQUIRED=NO",
            "CODE_SIGN_IDENTITY=",
            "DEVELOPMENT_TEAM=",
            "PROVISIONING_PROFILE=",
            "PROVISIONING_PROFILE_SPECIFIER=",
        ]
    ]
