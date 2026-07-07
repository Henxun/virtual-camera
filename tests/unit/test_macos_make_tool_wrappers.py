# SPDX-License-Identifier: Apache-2.0
"""Wrapper coverage for macOS helper entrypoints in tools.make."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools import make as make_tool


def test_cmd_notarize_macos_forwards_release_artifact_overrides(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    seen: list[tuple[Path, dict[str, str] | None, list[str] | None]] = []

    def fake_run_script(script, *, env=None, args=None) -> int:
        seen.append((script, env, args))
        return 0

    monkeypatch.setattr(make_tool, "_run_macos_script", fake_run_script)

    args = argparse.Namespace(
        app_bundle=tmp_path / "Amaran Desktop.app",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        dmg_path=tmp_path / "VirtualCamera.dmg",
        zip_path=tmp_path / "VirtualCamera.zip",
        targets="app,pkg",
    )

    rc = make_tool.cmd_notarize_macos(args)

    assert rc == 0
    assert seen == [
        (
            make_tool.MACOS_NOTARIZE_SCRIPT,
            {
                "APP_BUNDLE": str(args.app_bundle),
                "PKG_PATH": str(args.pkg_path),
                "DMG_PATH": str(args.dmg_path),
                "ZIP_PATH": str(args.zip_path),
                "NOTARIZE_TARGETS": "app,pkg",
            },
            None,
        )
    ]


def test_cmd_staple_macos_forwards_release_artifact_overrides(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    seen: list[tuple[Path, dict[str, str] | None, list[str] | None]] = []

    def fake_run_script(script, *, env=None, args=None) -> int:
        seen.append((script, env, args))
        return 0

    monkeypatch.setattr(make_tool, "_run_macos_script", fake_run_script)

    args = argparse.Namespace(
        app_bundle=tmp_path / "Amaran Desktop.app",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        dmg_path=tmp_path / "VirtualCamera.dmg",
        zip_path=None,
        targets="app,pkg",
    )

    rc = make_tool.cmd_staple_macos(args)

    assert rc == 0
    assert seen == [
        (
            make_tool.MACOS_STAPLE_SCRIPT,
            {
                "APP_BUNDLE": str(args.app_bundle),
                "PKG_PATH": str(args.pkg_path),
                "DMG_PATH": str(args.dmg_path),
                "STAPLE_TARGETS": "app,pkg",
            },
            None,
        )
    ]


def test_cmd_validation_report_macos_forwards_runtime_and_install_session_artifacts(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        name="AKVC Demo",
        status_tool=tmp_path / "akvc-macos-status",
        list_devices_tool=tmp_path / "akvc-macos-list-devices",
        install_tool=tmp_path / "akvc-macos-install",
        preflight_json=tmp_path / "preflight.json",
        release_diagnostics_json=tmp_path / "release-diagnostics.json",
        install_session_json=tmp_path / "install-session.json",
        smoke_json=tmp_path / "smoke.json",
        framebus_roundtrip_json=tmp_path / "framebus-roundtrip.json",
        status_binary_check_json=tmp_path / "status-binary-check.json",
        list_devices_binary_check_json=tmp_path / "list-devices-binary-check.json",
        benchmark_json=tmp_path / "benchmark.json",
        demo_json=tmp_path / "demo.json",
        manual_results=tmp_path / "manual-results.json",
        write_manual_template=tmp_path / "manual-template.json",
        run_install=True,
        output=tmp_path / "validation-report.json",
    )

    rc = make_tool.cmd_validation_report_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_REPORT_SCRIPT),
                "--name",
                "AKVC Demo",
                "--status-tool",
                str(args.status_tool),
                "--list-devices-tool",
                str(args.list_devices_tool),
                "--install-tool",
                str(args.install_tool),
                "--preflight-json",
                str(args.preflight_json),
                "--release-diagnostics-json",
                str(args.release_diagnostics_json),
                "--install-session-json",
                str(args.install_session_json),
                "--smoke-json",
                str(args.smoke_json),
                "--framebus-roundtrip-json",
                str(args.framebus_roundtrip_json),
                "--status-binary-check-json",
                str(args.status_binary_check_json),
                "--list-devices-binary-check-json",
                str(args.list_devices_binary_check_json),
                "--benchmark-json",
                str(args.benchmark_json),
                "--demo-json",
                str(args.demo_json),
                "--manual-results",
                str(args.manual_results),
                "--write-manual-template",
                str(args.write_manual_template),
                "--run-install",
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_validation_session_macos_forwards_install_session_controls(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        output_dir=tmp_path / "session",
        benchmark_warmup=1.5,
        mode="video-file",
        width=1920,
        height=1080,
        fps=60.0,
        duration=8.0,
        name="AKVC Session",
        benchmark_profile="1080p60",
        benchmark_matrix=True,
        video_path=tmp_path / "demo.mp4",
        status_tool=tmp_path / "akvc-macos-status",
        list_devices_tool=tmp_path / "akvc-macos-list-devices",
        install_tool=tmp_path / "akvc-macos-install",
        uninstall_tool=tmp_path / "akvc-macos-uninstall",
        sync_ipc_tool=tmp_path / "akvc-macos-sync-ipc",
        host_bundle=tmp_path / "Applications" / "Amaran Desktop.app",
        host_executable=tmp_path / "Applications" / "Amaran Desktop.app" / "Contents" / "MacOS" / "Amaran Desktop",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        installer_executable=tmp_path / "fake-installer",
        disable_auto_package=True,
        manual_results=tmp_path / "manual-results.json",
        reuse_existing_artifacts=True,
        preflight_tool=tmp_path / "preflight.py",
        release_diagnostics_tool=tmp_path / "release-diagnostics.py",
        smoke_tool=tmp_path / "smoke.py",
        install_session_tool=tmp_path / "install-session.py",
        framebus_roundtrip_tool=tmp_path / "framebus-roundtrip.py",
        framebus_producer_kind="mac-virtual-camera",
        direct_push_demo_tool=tmp_path / "direct-push-demo.py",
        direct_push_frames=12,
        direct_push_frame_kind="qimage-bgra",
        direct_push_entrypoint="send-widget",
        direct_push_allow_shared_memory_fallback=True,
        direct_push_request_camera_access=True,
        direct_sender_object_demo_tool=tmp_path / "direct-sender-object-demo.py",
        direct_sender_object_frames=5,
        direct_sender_object_frame_kind="bytes-bgr",
        direct_sender_object_request_camera_access=True,
        direct_sender_library=tmp_path / "libakvc-macos-direct-sender.dylib",
        status_binary_check_tool=tmp_path / "status-binary-check.py",
        list_devices_binary_check_tool=tmp_path / "list-devices-binary-check.py",
        artifact_check_tool=tmp_path / "artifact-check.py",
        acceptance_tool=tmp_path / "acceptance.py",
        summary_tool=tmp_path / "summary.py",
        demo_tool=tmp_path / "demo-tool.py",
        benchmark_tool=tmp_path / "benchmark.py",
        validation_report_tool=tmp_path / "report.py",
        skip_demo=True,
        skip_preflight=True,
        skip_release_diagnostics=True,
        skip_benchmark=True,
        run_install=True,
        run_uninstall=True,
        run_install_session=True,
        run_framebus_roundtrip=True,
        run_direct_push_demo=True,
        run_direct_sender_object_demo=True,
        run_status_binary_check=True,
        run_list_devices_binary_check=True,
    )

    rc = make_tool.cmd_validation_session_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_SESSION_SCRIPT),
                "--output-dir",
                str(args.output_dir),
                "--benchmark-warmup",
                "1.5",
                "--mode",
                "video-file",
                "--width",
                "1920",
                "--height",
                "1080",
                "--fps",
                "60.0",
                "--duration",
                "8.0",
                "--name",
                "AKVC Session",
                "--benchmark-profile",
                "1080p60",
                "--benchmark-matrix",
                "--video-path",
                str(args.video_path),
                "--status-tool",
                str(args.status_tool),
                "--list-devices-tool",
                str(args.list_devices_tool),
                "--install-tool",
                str(args.install_tool),
                "--uninstall-tool",
                str(args.uninstall_tool),
                "--sync-ipc-tool",
                str(args.sync_ipc_tool),
                "--app-bundle",
                str(args.host_bundle),
                "--app-executable",
                str(args.host_executable),
                "--direct-sender-library",
                str(args.direct_sender_library),
                "--pkg-path",
                str(args.pkg_path),
                "--installer-executable",
                str(args.installer_executable),
                "--disable-auto-package",
                "--manual-results",
                str(args.manual_results),
                "--reuse-existing-artifacts",
                "--preflight-tool",
                str(args.preflight_tool),
                "--release-diagnostics-tool",
                str(args.release_diagnostics_tool),
                "--smoke-tool",
                str(args.smoke_tool),
                "--install-session-tool",
                str(args.install_session_tool),
                "--framebus-roundtrip-tool",
                str(args.framebus_roundtrip_tool),
                "--framebus-producer-kind",
                "mac-virtual-camera",
                "--direct-push-demo-tool",
                str(args.direct_push_demo_tool),
                "--direct-push-frames",
                "12",
                "--direct-push-frame-kind",
                "qimage-bgra",
                "--direct-push-entrypoint",
                "send-widget",
                "--direct-push-allow-shared-memory-fallback",
                "--direct-push-request-camera-access",
                "--direct-sender-object-demo-tool",
                str(args.direct_sender_object_demo_tool),
                "--direct-sender-object-frames",
                "5",
                "--direct-sender-object-frame-kind",
                "bytes-bgr",
                "--direct-sender-object-request-camera-access",
                "--status-binary-check-tool",
                str(args.status_binary_check_tool),
                "--list-devices-binary-check-tool",
                str(args.list_devices_binary_check_tool),
                "--artifact-check-tool",
                str(args.artifact_check_tool),
                "--acceptance-tool",
                str(args.acceptance_tool),
                "--summary-tool",
                str(args.summary_tool),
                "--demo-tool",
                str(args.demo_tool),
                "--benchmark-tool",
                str(args.benchmark_tool),
                "--validation-report-tool",
                str(args.validation_report_tool),
                "--skip-demo",
                "--skip-preflight",
                "--skip-release-diagnostics",
                "--skip-benchmark",
                "--run-install",
                "--run-uninstall",
                "--run-install-session",
                "--run-framebus-roundtrip",
                "--run-direct-push-demo",
                "--run-direct-sender-object-demo",
                "--run-status-binary-check",
                "--run-list-devices-binary-check",
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_validation_report_macos_forwards_host_runtime_overrides(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        name="AKVC Demo",
        status_tool=tmp_path / "akvc-macos-status",
        list_devices_tool=tmp_path / "akvc-macos-list-devices",
        install_tool=tmp_path / "akvc-macos-install",
        uninstall_tool=tmp_path / "akvc-macos-uninstall",
        sync_ipc_tool=tmp_path / "akvc-macos-sync-ipc",
        host_bundle=tmp_path / "Applications" / "Amaran Desktop.app",
        host_executable=tmp_path / "Applications" / "Amaran Desktop.app" / "Contents" / "MacOS" / "Amaran Desktop",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        installer_executable=tmp_path / "fake-installer",
        disable_auto_package=True,
        preflight_json=tmp_path / "preflight.json",
        release_diagnostics_json=tmp_path / "release-diagnostics.json",
        install_session_json=tmp_path / "install-session.json",
        smoke_json=tmp_path / "smoke.json",
        framebus_roundtrip_json=tmp_path / "framebus-roundtrip.json",
        status_binary_check_json=tmp_path / "status-binary-check.json",
        list_devices_binary_check_json=tmp_path / "list-devices-binary-check.json",
        benchmark_json=tmp_path / "benchmark.json",
        demo_json=tmp_path / "demo.json",
        manual_results=tmp_path / "manual-results.json",
        write_manual_template=tmp_path / "manual-results.template.json",
        run_install=True,
        output=tmp_path / "validation-report.json",
    )

    rc = make_tool.cmd_validation_report_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_REPORT_SCRIPT),
                "--name",
                "AKVC Demo",
                "--status-tool",
                str(args.status_tool),
                "--list-devices-tool",
                str(args.list_devices_tool),
                "--install-tool",
                str(args.install_tool),
                "--uninstall-tool",
                str(args.uninstall_tool),
                "--sync-ipc-tool",
                str(args.sync_ipc_tool),
                "--app-bundle",
                str(args.host_bundle),
                "--app-executable",
                str(args.host_executable),
                "--pkg-path",
                str(args.pkg_path),
                "--installer-executable",
                str(args.installer_executable),
                "--disable-auto-package",
                "--preflight-json",
                str(args.preflight_json),
                "--release-diagnostics-json",
                str(args.release_diagnostics_json),
                "--install-session-json",
                str(args.install_session_json),
                "--smoke-json",
                str(args.smoke_json),
                "--framebus-roundtrip-json",
                str(args.framebus_roundtrip_json),
                "--status-binary-check-json",
                str(args.status_binary_check_json),
                "--list-devices-binary-check-json",
                str(args.list_devices_binary_check_json),
                "--benchmark-json",
                str(args.benchmark_json),
                "--demo-json",
                str(args.demo_json),
                "--manual-results",
                str(args.manual_results),
                "--write-manual-template",
                str(args.write_manual_template),
                "--run-install",
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_validation_session_artifact_check_macos_forwards_manifest_controls(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        manifest=tmp_path / "session" / "session-manifest.json",
        require_existing_artifacts=True,
        output=tmp_path / "session" / "session-manifest-check.json",
    )

    rc = make_tool.cmd_validation_session_artifact_check_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_SESSION_ARTIFACT_CHECK_SCRIPT),
                "--manifest",
                str(args.manifest),
                "--require-existing-artifacts",
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_validation_session_acceptance_macos_forwards_manifest_controls(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        manifest=tmp_path / "session" / "session-manifest.json",
        output=tmp_path / "session" / "session-acceptance.json",
    )

    rc = make_tool.cmd_validation_session_acceptance_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_SESSION_ACCEPTANCE_SCRIPT),
                "--manifest",
                str(args.manifest),
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_validation_session_acceptance_contract_macos_forwards_output_control(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        output=tmp_path / "session" / "session-acceptance-contract.json",
    )

    rc = make_tool.cmd_validation_session_acceptance_contract_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_SESSION_ACCEPTANCE_CONTRACT_SCRIPT),
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_validation_session_summary_macos_forwards_manifest_controls(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        manifest=tmp_path / "session" / "session-manifest.json",
        output=tmp_path / "session" / "session-summary.md",
    )

    rc = make_tool.cmd_validation_session_summary_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_VALIDATION_SESSION_SUMMARY_SCRIPT),
                "--manifest",
                str(args.manifest),
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_list_devices_binary_check_macos_forwards_tool_and_output(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        list_devices_tool=tmp_path / "akvc-macos-list-devices",
        expected_prefix="AKVC Demo",
        output=tmp_path / "list-devices-binary-check.json",
    )

    rc = make_tool.cmd_list_devices_binary_check_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_LIST_DEVICES_BINARY_CHECK_SCRIPT),
                "--list-devices-tool",
                str(args.list_devices_tool),
                "--expected-prefix",
                "AKVC Demo",
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_install_session_macos_forwards_pkg_and_host_controls(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        name="AKVC Demo",
        status_tool=tmp_path / "akvc-macos-status",
        install_tool=tmp_path / "akvc-macos-install",
        list_devices_tool=tmp_path / "akvc-macos-list-devices",
        uninstall_tool=tmp_path / "akvc-macos-uninstall",
        sync_ipc_tool=tmp_path / "akvc-macos-sync-ipc",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        host_bundle=tmp_path / "Applications" / "Amaran Desktop.app",
        host_executable=tmp_path / "Applications" / "Amaran Desktop.app" / "Contents" / "MacOS" / "Amaran Desktop",
        installer_executable=tmp_path / "fake-installer",
        framebus_roundtrip_json=tmp_path / "framebus-roundtrip.json",
        direct_push_demo_tool=tmp_path / "direct-push-demo.py",
        direct_push_frames=7,
        direct_push_frame_kind="qimage-bgra",
        direct_push_entrypoint="send-widget",
        direct_push_allow_shared_memory_fallback=True,
        direct_push_request_camera_access=True,
        direct_sender_object_demo_tool=tmp_path / "direct-sender-object-demo.py",
        direct_sender_object_frames=4,
        direct_sender_object_frame_kind="bytes-bgra",
        direct_sender_object_request_camera_access=True,
        direct_sender_library=tmp_path / "libakvc-macos-direct-sender.dylib",
        run_direct_push_demo=True,
        run_direct_sender_object_demo=True,
        disable_auto_package=True,
        run_uninstall=True,
        status_poll_attempts=12,
        poll_interval_seconds=0.25,
        output=tmp_path / "install-session.json",
    )

    rc = make_tool.cmd_install_session_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_INSTALL_SESSION_SCRIPT),
                "--name",
                "AKVC Demo",
                "--status-tool",
                str(args.status_tool),
                "--install-tool",
                str(args.install_tool),
                "--list-devices-tool",
                str(args.list_devices_tool),
                "--uninstall-tool",
                str(args.uninstall_tool),
                "--sync-ipc-tool",
                str(args.sync_ipc_tool),
                "--pkg-path",
                str(args.pkg_path),
                "--app-bundle",
                str(args.host_bundle),
                "--app-executable",
                str(args.host_executable),
                "--direct-sender-library",
                str(args.direct_sender_library),
                "--installer-executable",
                str(args.installer_executable),
                "--framebus-roundtrip-json",
                str(args.framebus_roundtrip_json),
                "--direct-push-demo-tool",
                str(args.direct_push_demo_tool),
                "--direct-push-frames",
                "7",
                "--direct-push-frame-kind",
                "qimage-bgra",
                "--direct-push-entrypoint",
                "send-widget",
                "--direct-push-allow-shared-memory-fallback",
                "--direct-push-request-camera-access",
                "--direct-sender-object-demo-tool",
                str(args.direct_sender_object_demo_tool),
                "--direct-sender-object-frames",
                "4",
                "--direct-sender-object-frame-kind",
                "bytes-bgra",
                "--direct-sender-object-request-camera-access",
                "--disable-auto-package",
                "--run-uninstall",
                "--run-direct-push-demo",
                "--run-direct-sender-object-demo",
                "--status-poll-attempts",
                "12",
                "--poll-interval-seconds",
                "0.25",
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_build_macos_tolerates_missing_python_flag(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_require_tool", lambda tool: tool)
    monkeypatch.setattr(make_tool, "MACOS_ROOT", tmp_path)
    monkeypatch.setattr(make_tool, "MACOS_BUILD", tmp_path / "build")

    project = tmp_path / "akvc-macos.xcodeproj"
    project.mkdir()

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        del cwd, env
        calls.append(cmd)
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        archs=None,
        deployment_target=None,
    )

    rc = make_tool.cmd_build_macos(args)

    assert rc == 0
    assert len(calls) == 1
    assert calls[0][0] == "xcodebuild"


def test_cmd_build_macos_regenerates_xcodeproj_when_project_spec_is_newer(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_require_tool", lambda tool: tool)
    monkeypatch.setattr(make_tool, "MACOS_ROOT", tmp_path)
    monkeypatch.setattr(make_tool, "MACOS_BUILD", tmp_path / "build")

    project = tmp_path / "akvc-macos.xcodeproj"
    project.mkdir()
    project_file = project / "project.pbxproj"
    project_file.write_text("// generated\n", encoding="utf-8")

    spec = tmp_path / "project.yml"
    spec.write_text("name: akvc-macos\n", encoding="utf-8")

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        del cwd, env
        calls.append(cmd)
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        archs=None,
        deployment_target=None,
    )

    rc = make_tool.cmd_build_macos(args)

    assert rc == 0
    assert len(calls) == 2
    assert calls[0][:3] == ["xcodegen", "generate", "--spec"]
    assert calls[0][3] == str(spec)
    assert calls[1][0] == "xcodebuild"


def test_cmd_release_diagnostics_macos_forwards_sync_ipc_tool(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        app_bundle=tmp_path / "Amaran Desktop.app",
        extension_bundle=tmp_path / "com.sidus.amaran-desktop.cameraextension.systemextension",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        dmg_path=tmp_path / "VirtualCamera.dmg",
        zip_path=tmp_path / "VirtualCamera.zip",
        sync_ipc_tool=tmp_path / "akvc-macos-sync-ipc",
        output=tmp_path / "release-diagnostics.json",
    )

    rc = make_tool.cmd_release_diagnostics_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_RELEASE_DIAGNOSTICS_SCRIPT),
                "--app-bundle",
                str(args.app_bundle),
                "--extension-bundle",
                str(args.extension_bundle),
                "--pkg-path",
                str(args.pkg_path),
                "--dmg-path",
                str(args.dmg_path),
                "--zip-path",
                str(args.zip_path),
                "--sync-ipc-tool",
                str(args.sync_ipc_tool),
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_smoke_macos_forwards_runtime_overrides_and_framebus_roundtrip_json(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        name="AKVC Demo",
        status_tool=tmp_path / "akvc-macos-status",
        install_tool=tmp_path / "akvc-macos-install",
        list_devices_tool=tmp_path / "akvc-macos-list-devices",
        uninstall_tool=tmp_path / "akvc-macos-uninstall",
        sync_ipc_tool=tmp_path / "akvc-macos-sync-ipc",
        pkg_path=tmp_path / "VirtualCamera.pkg",
        host_bundle=tmp_path / "Applications" / "Amaran Desktop.app",
        host_executable=tmp_path / "Applications" / "Amaran Desktop.app" / "Contents" / "MacOS" / "Amaran Desktop",
        installer_executable=tmp_path / "fake-installer",
        disable_auto_package=True,
        run_install=True,
        run_uninstall=False,
        direct_push_demo_tool=tmp_path / "direct-push-demo.py",
        direct_push_frames=9,
        direct_push_frame_kind="qimage-bgra",
        direct_push_entrypoint="send-screen",
        direct_push_allow_shared_memory_fallback=True,
        direct_push_request_camera_access=True,
        direct_sender_object_demo_tool=tmp_path / "direct-sender-object-demo.py",
        direct_sender_object_frames=3,
        direct_sender_object_frame_kind="numpy-direct",
        direct_sender_object_request_camera_access=True,
        direct_sender_library=tmp_path / "libakvc-macos-direct-sender.dylib",
        run_direct_push_demo=True,
        run_direct_sender_object_demo=True,
        framebus_roundtrip_json=tmp_path / "framebus-roundtrip.json",
        output=tmp_path / "smoke-report.json",
    )

    rc = make_tool.cmd_smoke_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_SMOKE_SCRIPT),
                "--name",
                "AKVC Demo",
                "--status-tool",
                str(args.status_tool),
                "--install-tool",
                str(args.install_tool),
                "--list-devices-tool",
                str(args.list_devices_tool),
                "--uninstall-tool",
                str(args.uninstall_tool),
                "--sync-ipc-tool",
                str(args.sync_ipc_tool),
                "--pkg-path",
                str(args.pkg_path),
                "--app-bundle",
                str(args.host_bundle),
                "--app-executable",
                str(args.host_executable),
                "--direct-sender-library",
                str(args.direct_sender_library),
                "--installer-executable",
                str(args.installer_executable),
                "--direct-push-demo-tool",
                str(args.direct_push_demo_tool),
                "--direct-push-frames",
                "9",
                "--direct-push-frame-kind",
                "qimage-bgra",
                "--direct-push-entrypoint",
                "send-screen",
                "--direct-push-allow-shared-memory-fallback",
                "--direct-push-request-camera-access",
                "--direct-sender-object-demo-tool",
                str(args.direct_sender_object_demo_tool),
                "--direct-sender-object-frames",
                "3",
                "--direct-sender-object-frame-kind",
                "numpy-direct",
                "--direct-sender-object-request-camera-access",
                "--disable-auto-package",
                "--run-install",
                "--run-direct-push-demo",
                "--run-direct-sender-object-demo",
                "--framebus-roundtrip-json",
                str(args.framebus_roundtrip_json),
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_direct_push_demo_macos_forwards_demo_arguments(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []
    demo_script = tmp_path / "macos_direct_push_demo.py"
    demo_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})
    monkeypatch.setattr(make_tool, "MACOS_DIRECT_PUSH_DEMO_SCRIPT", demo_script)

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        width=1920,
        height=1080,
        fps=60.0,
        duration=1.5,
        frames=90,
        name="AKVC Direct",
        host_bundle=tmp_path / "Applications" / "Amaran Desktop.app",
        host_executable=None,
        direct_sender_library=tmp_path / "libakvc-macos-direct-sender.dylib",
        frame_kind="qimage-bgra",
        entrypoint="send-widget",
        allow_shared_memory_fallback=True,
        request_camera_access=True,
        require_direct_runtime=True,
        probe_only=True,
        output=tmp_path / "direct-push-report.json",
    )

    rc = make_tool.cmd_direct_push_demo_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_DIRECT_PUSH_DEMO_SCRIPT),
                "--width",
                "1920",
                "--height",
                "1080",
                "--fps",
                "60.0",
                "--duration",
                "1.5",
                "--name",
                "AKVC Direct",
                "--app-bundle",
                str(args.host_bundle),
                "--direct-sender-library",
                str(args.direct_sender_library),
                "--frame-kind",
                "qimage-bgra",
                "--entrypoint",
                "send-widget",
                "--allow-shared-memory-fallback",
                "--request-camera-access",
                "--require-direct-runtime",
                "--probe-only",
                "--frames",
                "90",
                "--report-json",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_direct_push_demo_macos_rejects_conflicting_host_arguments(monkeypatch, tmp_path, capsys) -> None:
    demo_script = tmp_path / "macos_direct_push_demo.py"
    demo_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "MACOS_DIRECT_PUSH_DEMO_SCRIPT", demo_script)

    args = argparse.Namespace(
        width=1280,
        height=720,
        fps=30.0,
        duration=3.0,
        frames=None,
        name="AK Virtual Camera",
        host_bundle=tmp_path / "Applications" / "Amaran Desktop.app",
        host_executable=tmp_path / "Applications" / "Amaran Desktop.app" / "Contents" / "MacOS" / "Amaran Desktop",
        direct_sender_library=None,
        frame_kind=None,
        entrypoint=None,
        allow_shared_memory_fallback=False,
        request_camera_access=False,
        require_direct_runtime=False,
        probe_only=False,
        output=None,
    )

    rc = make_tool.cmd_direct_push_demo_macos(args)

    assert rc == 2
    assert (
        "--app-bundle/--host-bundle and --app-executable/--host-executable are mutually exclusive"
        in capsys.readouterr().err
    )


def test_cmd_direct_sender_object_demo_macos_forwards_demo_arguments(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []
    demo_script = tmp_path / "macos_direct_sender_object_demo.py"
    demo_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})
    monkeypatch.setattr(make_tool, "MACOS_DIRECT_SENDER_OBJECT_DEMO_SCRIPT", demo_script)

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        width=1920,
        height=1080,
        fps=60.0,
        frames=90,
        name="AKVC Direct",
        direct_sender_library=tmp_path / "libakvc-macos-direct-sender.dylib",
        frame_kind="bytes-bgra",
        request_camera_access=True,
        probe_only=True,
        output=tmp_path / "direct-sender-object-report.json",
    )

    rc = make_tool.cmd_direct_sender_object_demo_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_DIRECT_SENDER_OBJECT_DEMO_SCRIPT),
                "--width",
                "1920",
                "--height",
                "1080",
                "--fps",
                "60.0",
                "--name",
                "AKVC Direct",
                "--direct-sender-library",
                str(args.direct_sender_library),
                "--frame-kind",
                "bytes-bgra",
                "--request-camera-access",
                "--inspect-only",
                "--frames",
                "90",
                "--report-json",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]


def test_cmd_framebus_roundtrip_macos_forwards_probe_controls(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    monkeypatch.setattr(make_tool, "_check_macos", lambda: None)
    monkeypatch.setattr(make_tool, "_macos_script_env", lambda: {"AKVC_TEST_ENV": "1"})

    def fake_run(cmd: list[str], *, cwd=None, env=None) -> int:
        calls.append((cmd, cwd, env))
        return 0

    monkeypatch.setattr(make_tool, "_run", fake_run)

    args = argparse.Namespace(
        width=1920,
        height=1080,
        compiler="/usr/bin/clang",
        binary=tmp_path / "framebus_consumer_probe",
        skip_compile=True,
        attempts=12,
        sleep_ms=40,
        flags=2,
        producer_kind="mac-virtual-camera",
        output=tmp_path / "framebus-roundtrip.json",
    )

    rc = make_tool.cmd_framebus_roundtrip_macos(args)

    assert rc == 0
    assert calls == [
        (
            [
                make_tool.sys.executable,
                str(make_tool.MACOS_FRAMEBUS_ROUNDTRIP_SCRIPT),
                "--width",
                "1920",
                "--height",
                "1080",
                "--attempts",
                "12",
                "--sleep-ms",
                "40",
                "--flags",
                "2",
                "--producer-kind",
                "mac-virtual-camera",
                "--compiler",
                "/usr/bin/clang",
                "--binary",
                str(args.binary),
                "--skip-compile",
                "--output",
                str(args.output),
            ],
            make_tool.ROOT,
            {"AKVC_TEST_ENV": "1"},
        )
    ]
