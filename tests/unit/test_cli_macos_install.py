# SPDX-License-Identifier: Apache-2.0
"""CLI coverage for macOS install/status flows."""

from __future__ import annotations

import argparse
import contextlib
import io

from akvc.platforms.macos.installer import (
    ExtensionReadiness,
    ExtensionInstallState,
    ExtensionRuntimeSnapshot,
    ExtensionStatus,
    InstallExtensionResult,
    ManualAppValidationSummary,
    SyncIPCConfigurationResult,
    UninstallExtensionResult,
)

from akvc_cli import __main__ as cli


class FakeMacCamera:
    def __init__(
        self,
        *,
        status: ExtensionStatus,
        devices: list[str],
        install_result: InstallExtensionResult,
        uninstall_result: UninstallExtensionResult | None = None,
    ) -> None:
        self._status = status
        self._devices = devices
        self._install_result = install_result
        self._uninstall_result = uninstall_result or UninstallExtensionResult(
            success=True,
            phase="uninstalled",
            state=ExtensionInstallState.NOT_INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
        )
        self.sync_calls: list[str | None] = []

    def status(self) -> ExtensionStatus:
        return self._status

    def enumerate_devices(self) -> list[str]:
        return list(self._devices)

    def install_extension_result(self) -> InstallExtensionResult:
        return self._install_result

    def uninstall_extension_result(self) -> UninstallExtensionResult:
        return self._uninstall_result

    def sync_ipc_configuration_result(self, shared_memory_name: str | None = None) -> SyncIPCConfigurationResult:
        self.sync_calls.append(shared_memory_name)
        return SyncIPCConfigurationResult(
            supported=True,
            success=True,
            phase="sync_command_succeeded",
            shared_memory_name=shared_memory_name or self._status.shared_memory_name or "/akvc-frames-v1",
            ipc_transport=self._status.ipc_transport,
        )

    def inspect_installation(self) -> ExtensionRuntimeSnapshot:
        devices = list(self._devices)
        phase = (
            "installed_visible"
            if self._status.enabled and devices
            else "pending_approval"
            if self._status.approval_required
            else "timeout_waiting_for_device"
            if self._status.enabled
            else ""
        )
        blocker_code = (
            "ready"
            if self._status.enabled and devices
            else "approval_required"
            if self._status.approval_required
            else "device_not_visible"
            if self._status.enabled
            else "not_installed"
        )
        message = (
            "虚拟摄像头已安装并出现在系统设备列表中，可在 Zoom/Meet/OBS 中继续验证。"
            if blocker_code == "ready"
            else "需要在系统设置 > 隐私与安全性 中批准 AK Virtual Camera 扩展，批准后重新检查设备可见性。可使用 Open Settings 按钮快速打开系统设置。"
            if blocker_code == "approval_required"
            else "扩展状态已收敛，但系统视频设备列表里还没有出现虚拟摄像头。请重新打开目标应用并再次检查。必要时可先打开系统设置确认扩展状态。"
            if blocker_code == "device_not_visible"
            else "虚拟摄像头尚未安装。"
        )
        targets = [
            {"id": "zoom", "name": "Zoom", "ready": blocker_code in {"ready", "ipc_environment_blocked", "ipc_not_ready"}, "status": "ok", "steps": []},
            {"id": "teams", "name": "Teams", "ready": blocker_code in {"ready", "ipc_environment_blocked", "ipc_not_ready"}, "status": "ok", "steps": []},
            {"id": "google_meet", "name": "Google Meet", "ready": blocker_code in {"ready", "ipc_environment_blocked", "ipc_not_ready"}, "status": "ok", "steps": []},
            {"id": "obs", "name": "OBS", "ready": blocker_code in {"ready", "ipc_environment_blocked", "ipc_not_ready"}, "status": "ok", "steps": []},
            {"id": "quicktime", "name": "QuickTime", "ready": blocker_code in {"ready", "ipc_environment_blocked", "ipc_not_ready"}, "status": "ok", "steps": []},
            {"id": "facetime", "name": "FaceTime", "ready": blocker_code in {"ready", "ipc_environment_blocked", "ipc_not_ready"}, "status": "ok", "steps": []},
        ]
        if blocker_code == "approval_required":
            for target in targets:
                target["ready"] = False
                target["status"] = "等待在系统设置中批准扩展"
        elif blocker_code == "device_not_visible":
            for target in targets:
                target["ready"] = False
                target["status"] = "等待系统枚举摄像头设备"
        elif blocker_code == "not_installed":
            for target in targets:
                target["ready"] = False
                target["status"] = "尚未安装"
        return ExtensionRuntimeSnapshot(
            status=self._status,
            devices=devices,
            readiness=ExtensionReadiness(
                phase=phase,
                ready=blocker_code == "ready",
                blocker_code=blocker_code,
                message=message,
                steps=["step-1", "step-2"],
                verification_targets=targets,
            ),
        )


def test_cmd_status_reports_macos_extension_state(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            approval_required=True,
            bundle_path="/Applications/AKVC.app",
            host_signature="adhoc",
            host_codesign_summary="Signature=adhoc; TeamIdentifier=not set",
            host_gatekeeper_allowed=False,
            host_gatekeeper_summary="/Applications/AKVC.app: rejected; origin=Apple Development: Demo",
            host_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            host_notarization_missing=True,
            shared_memory_name="/akvc-frames-v1",
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ipc_direct_open_errno=13,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="pending_approval",
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALL_PENDING_APPROVAL),
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr(
        cli,
        "load_manual_app_validation_summary",
        lambda: ManualAppValidationSummary(
            present=True,
            ready=False,
            failed_criteria=["system_camera_device_visible"],
            unknown_criteria=["notarization_tooling_ready"],
            blockers=["system_camera_device_visible", "notarization_tooling_ready"],
            manifest_path="/tmp/session-manifest.json",
        ),
    )

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_status(argparse.Namespace(json=False))

    output = stdout.getvalue()
    assert rc == 0
    assert "state: install_pending_approval" in output
    assert "phase: pending_approval" in output
    assert "approval_required: True" in output
    assert "devices: AK Virtual Camera" in output
    assert "/Applications/AKVC.app" in output
    assert "host_signature: adhoc" in output
    assert "host_codesign_summary: Signature=adhoc; TeamIdentifier=not set" in output
    assert "host_gatekeeper_allowed: False" in output
    assert "host_distribution_summary: Notary Ticket Missing; Severity=Fatal" in output
    assert "host_notarization_missing: True" in output
    assert "ipc_environment_blocked: True" in output
    assert "ipc_direct_open_errno: 13" in output
    assert "start_blocker_code: approval_required" in output
    assert "runtime_topology_kind: camera_extension_direct_framebus" in output
    assert "runtime_host_role: container_activation_command_bridge" in output
    assert "runtime_host_in_frame_hot_path: False" in output
    assert "runtime_dedicated_host_daemon_required: False" in output
    assert "runtime_container_app_configured: True" in output
    assert "runtime_control_plane: host_activation_plus_sync_ipc" in output
    assert "manual_app_validation_present: True" in output
    assert "manual_app_validation_ready: False" in output
    assert "manual_app_validation_blockers: 系统已枚举到虚拟摄像头, 公证工具链已就绪" in output
    assert "manual_app_validation_blocker_ids: system_camera_device_visible, notarization_tooling_ready" in output
    assert "verification_targets:" in output
    assert "Zoom" in output
    assert "QuickTime" in output


def test_cmd_status_reports_waiting_for_device_when_extension_enabled_but_not_visible(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        devices=[],
        install_result=InstallExtensionResult(
            success=False,
            phase="timeout_waiting_for_device",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_status(argparse.Namespace(json=True))

    output = stdout.getvalue()
    assert rc == 0
    assert '"phase": "timeout_waiting_for_device"' in output
    assert '"enabled": true' in output
    assert '"start_blocker_code": "device_not_visible"' in output
    assert '"status": "等待系统枚举摄像头设备"' in output


def test_cmd_status_reports_macos_producer_side_ipc_blocker(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
            bundle_path="/Applications/AKVC.app",
            shared_memory_name="/akvc-frames-v1",
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
            ipc_direct_open_errno=1,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_status(argparse.Namespace(json=False))

    output = stdout.getvalue()
    assert rc == 0
    assert "phase: installed_visible" in output
    assert "ipc_environment_blocked: True" in output
    assert "ipc_direct_open_errno: 1" in output
    assert "start_blocker_code: ready" in output
    assert "producer_open_failed" in output


def test_cmd_status_prefers_sdk_installation_snapshot_when_available(monkeypatch) -> None:
    class SnapshotOnlyCamera:
        def inspect_installation(self) -> ExtensionRuntimeSnapshot:
            return ExtensionRuntimeSnapshot(
                status=ExtensionStatus(
                    state=ExtensionInstallState.INSTALLED,
                    enabled=True,
                    devices=["AK Virtual Camera"],
                    bundle_path="/Applications/AKVC.app",
                    ipc_transport="shared_memory_ringbuffer",
                ),
                devices=["AK Virtual Camera"],
                readiness=ExtensionReadiness(
                    phase="installed_visible",
                    ready=True,
                    blocker_code="ready",
                    message="ready",
                    steps=["snapshot-step"],
                    verification_targets=[{"id": "zoom", "name": "Zoom", "ready": True, "status": "ok", "steps": []}],
                ),
            )

        def status(self):  # pragma: no cover - should not be called
            raise AssertionError("cmd_status should prefer inspect_installation()")

        def enumerate_devices(self):  # pragma: no cover - should not be called
            raise AssertionError("cmd_status should prefer inspect_installation()")

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: SnapshotOnlyCamera())

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_status(argparse.Namespace(json=True))

    output = stdout.getvalue()
    assert rc == 0
    assert '"phase": "installed_visible"' in output
    assert '"start_blocker_code": "ready"' in output
    assert '"ipc_transport": "shared_memory_ringbuffer"' in output
    assert '"runtime_topology_kind": "camera_extension_direct_framebus"' in output
    assert '"runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app"' in output
    assert '"runtime_host_role": "container_activation_command_bridge"' in output
    assert '"runtime_container_app_configured": true' in output


def test_cmd_install_reports_macos_install_phase(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
                bundle_path="/Applications/AKVC.app",
            ),
            enumerated_devices=["AK Virtual Camera"],
            install_returncode=0,
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_install(argparse.Namespace(json=False))

    output = stdout.getvalue()
    assert rc == 0
    assert "success: True" in output
    assert "phase: installed_visible" in output
    assert "state: installed" in output
    assert "enumerated_devices: AK Virtual Camera" in output
    assert "start_blocker_code: ready" in output
    assert "runtime_topology_kind: camera_extension_direct_framebus" in output
    assert "runtime_host_role: container_activation_command_bridge" in output
    assert "runtime_container_app_configured: True" in output
    assert "verification_targets:" in output
    assert "Google Meet" in output


def test_cmd_install_reports_json_payload_for_macos(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
        devices=[],
        install_result=InstallExtensionResult(
            success=False,
            phase="timeout_waiting_for_device",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                bundle_path="/Applications/AKVC.app",
                last_error="device not visible yet",
                ipc_probe_present=True,
                ipc_ready=False,
                ipc_environment_blocked=True,
                ipc_last_error="probe status=open_failed; direct_open_errno=13",
                ipc_direct_open_errno=13,
            ),
            enumerated_devices=[],
            install_returncode=0,
            install_stdout="ok",
            install_stderr="",
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr(
        cli,
        "load_manual_app_validation_summary",
        lambda: ManualAppValidationSummary(
            present=True,
            ready=False,
            failed_criteria=["system_camera_device_visible"],
            unknown_criteria=[],
            blockers=["system_camera_device_visible"],
            manifest_path="/tmp/session-manifest.json",
        ),
    )

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_install(argparse.Namespace(json=True))

    output = stdout.getvalue()
    assert rc == 1
    assert '"phase": "timeout_waiting_for_device"' in output
    assert '"last_error": "device not visible yet"' in output
    assert '"ipc_environment_blocked": true' in output
    assert '"ipc_direct_open_errno": 13' in output
    assert '"start_blocker_code": "device_not_visible"' in output
    assert '"runtime_topology_kind": "camera_extension_direct_framebus"' in output
    assert '"runtime_host_in_frame_hot_path": false' in output
    assert '"runtime_dedicated_host_daemon_required": false' in output
    assert '"runtime_container_app_configured": true' in output
    assert '"manual_app_validation_present": true' in output
    assert '"manual_app_validation_ready": false' in output
    assert '"manual_app_validation_blockers": [' in output
    assert '"系统已枚举到虚拟摄像头"' in output
    assert '"manual_app_validation_blocker_ids": [' in output


def test_cmd_status_maps_legacy_host_bundle_to_container_app_arg(monkeypatch) -> None:
    observed = {}
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            bundle_path="/Applications/Amaran Desktop.app",
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    def factory(**kwargs):
        observed.update(kwargs)
        return fake_camera

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", factory)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_status(
            argparse.Namespace(
                json=True,
                app_bundle=None,
                app_executable=None,
                host_bundle="/Applications/Amaran Desktop.app",
                host_executable=None,
            )
        )

    assert rc == 0
    assert observed == {"app_bundle": "/Applications/Amaran Desktop.app"}


def test_cmd_install_rejects_conflicting_explicit_host_paths(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.cmd_install(
            argparse.Namespace(
                json=False,
                app_bundle=None,
                app_executable=None,
                host_bundle="/Applications/Amaran Desktop.app",
                host_executable="/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop",
            )
    )

    assert rc == 2
    assert "mutually exclusive" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_cmd_install_reports_host_notarization_blocker_for_macos(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
        devices=[],
        install_result=InstallExtensionResult(
            success=False,
            phase="install_failed",
            state=ExtensionInstallState.INSTALL_FAILED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALL_FAILED,
                bundle_path="/Applications/Amaran Desktop.app",
                last_error="killed by launch policy",
                host_signature="Apple Development",
                host_team_identifier="XP3H66JF79",
                host_codesign_summary="Signature=Apple Development; TeamIdentifier=XP3H66JF79",
                host_gatekeeper_allowed=False,
                host_gatekeeper_summary=(
                    "/Applications/Amaran Desktop.app: rejected; "
                    "origin=Apple Development: Choshim Wei (53CY9ZZ74X)"
                ),
                host_distribution_summary="Notary Ticket Missing; Severity=Fatal",
                host_notarization_missing=True,
            ),
            enumerated_devices=[],
            install_returncode=0,
            install_stdout="ok",
            install_stderr="",
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_install(argparse.Namespace(json=True))

    output = stdout.getvalue()
    assert rc == 1
    assert '"host_gatekeeper_allowed": false' in output
    assert '"host_distribution_summary": "Notary Ticket Missing; Severity=Fatal"' in output
    assert '"host_notarization_missing": true' in output
    assert '"start_blocker_code": "host_notarization_missing"' in output
    assert "Developer ID Application" in output


def test_cmd_install_reports_install_command_notarization_blocker_for_macos(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
        devices=[],
        install_result=InstallExtensionResult(
            success=False,
            phase="install_failed",
            state=ExtensionInstallState.INSTALL_FAILED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALL_FAILED,
                bundle_path="/Applications/Amaran Desktop.app",
                last_error="killed by launch policy",
                install_command_path="/tmp/akvc-macos-install",
                install_command_signature="Developer ID Application",
                install_command_team_identifier="XP3H66JF79",
                install_command_codesign_summary="Signature=Developer ID Application; TeamIdentifier=XP3H66JF79",
                install_command_gatekeeper_allowed=False,
                install_command_gatekeeper_summary=(
                    "/tmp/akvc-macos-install: rejected; "
                    "source=Unnotarized Developer ID; "
                    "origin=Developer ID Application: Sidus Link Ltd. (XP3H66JF79)"
                ),
                install_command_distribution_summary="Notary Ticket Missing; Severity=Fatal",
                install_command_notarization_missing=True,
            ),
            enumerated_devices=[],
            install_returncode=0,
            install_stdout="ok",
            install_stderr="",
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_install(argparse.Namespace(json=True))

    output = stdout.getvalue()
    assert rc == 1
    assert '"install_command_path": "/tmp/akvc-macos-install"' in output
    assert '"install_command_notarization_missing": true' in output
    assert '"start_blocker_code": "install_command_notarization_missing"' in output
    assert "Developer ID Application" in output


def test_cmd_install_reports_system_extension_registry_state_for_macos(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
        devices=[],
        install_result=InstallExtensionResult(
            success=False,
            phase="install_failed",
            state=ExtensionInstallState.INSTALL_FAILED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALL_FAILED,
                extension_identifier="com.sidus.amaran-desktop.cameraextension",
                last_error="system extension status query timed out",
                system_extension_registered=False,
            ),
            enumerated_devices=[],
            install_returncode=0,
            install_stdout="ok",
            install_stderr="",
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_install(argparse.Namespace(json=True))

    output = stdout.getvalue()
    assert rc == 1
    assert '"system_extension_registered": false' in output
    assert '"start_blocker_code": "system_extension_not_registered"' in output


def test_cmd_install_rejects_non_macos_platform(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "platform", "win32", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.cmd_install(argparse.Namespace(json=False))

    assert rc == 2
    assert "macOS only" in stderr.getvalue()


def test_cmd_uninstall_reports_macos_uninstall_phase(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            bundle_path="/Applications/AKVC.app",
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
        uninstall_result=UninstallExtensionResult(
            success=True,
            phase="uninstalled",
            state=ExtensionInstallState.NOT_INSTALLED,
            status=ExtensionStatus(
                state=ExtensionInstallState.NOT_INSTALLED,
                enabled=False,
                bundle_path="/Applications/AKVC.app",
            ),
            enumerated_devices=[],
            uninstall_returncode=0,
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_uninstall(argparse.Namespace(json=False))

    output = stdout.getvalue()
    assert rc == 0
    assert "success: True" in output
    assert "phase: uninstalled" in output
    assert "state: not_installed" in output
    assert "/Applications/AKVC.app" in output


def test_cmd_uninstall_rejects_non_macos_platform(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "platform", "linux", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.cmd_uninstall(argparse.Namespace(json=False))

    assert rc == 2
    assert "macOS only" in stderr.getvalue()


def test_cmd_sync_ipc_reports_json_payload_for_macos(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            shared_memory_name="/akvc-frames-v1",
            ipc_transport="shared_memory_ringbuffer",
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(cli, "VirtualCamera", lambda **kwargs: fake_camera)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_sync_ipc(argparse.Namespace(json=True, shared_memory_name="/akvc-custom"))

    output = stdout.getvalue()
    assert rc == 0
    assert fake_camera.sync_calls == ["/akvc-custom"]
    assert '"supported": true' in output
    assert '"success": true' in output
    assert '"phase": "sync_command_succeeded"' in output
    assert '"shared_memory_name": "/akvc-custom"' in output


def test_cmd_sync_ipc_rejects_non_macos_platform(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "platform", "linux", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.cmd_sync_ipc(argparse.Namespace(json=False, shared_memory_name=None))

    assert rc == 2
    assert "macOS only" in stderr.getvalue()


def test_cmd_open_settings_reports_success(monkeypatch) -> None:
    monkeypatch.setattr(cli, "open_macos_install_settings", lambda: 0)
    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.cmd_open_settings(argparse.Namespace())

    assert rc == 0
    assert "opened System Settings" in stdout.getvalue()


def test_cmd_open_settings_rejects_non_macos_platform(monkeypatch) -> None:
    monkeypatch.setattr(cli, "open_macos_install_settings", lambda: 2)
    monkeypatch.setattr(cli.sys, "platform", "linux", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.cmd_open_settings(argparse.Namespace())

    assert rc == 2
    assert "macOS only" in stderr.getvalue()


def test_cmd_open_settings_reports_failure_on_macos(monkeypatch) -> None:
    monkeypatch.setattr(cli, "open_macos_install_settings", lambda: 5)
    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = cli.cmd_open_settings(argparse.Namespace())

    assert rc == 1
    assert "failed to open System Settings (rc=5)" in stderr.getvalue()
