# SPDX-License-Identifier: Apache-2.0
"""Desktop facade coverage for macOS install status propagation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from akvc.platforms.macos.installer import (
    ExtensionReadiness,
    ExtensionInstallState,
    ExtensionRuntimeSnapshot,
    ExtensionStatus,
    InstallExtensionResult,
    ManualAppValidationSummary,
)
from akvc_app.services.facade import ServiceFacade


class FakeMacCamera:
    def __init__(
        self,
        *,
        status: ExtensionStatus,
        devices: list[str],
        install_result: InstallExtensionResult,
        supported_formats: tuple[str, ...] | None = None,
        supported_frame_rates: tuple[int, ...] | None = None,
    ) -> None:
        self._status = status
        self._devices = devices
        self._install_result = install_result
        self._supported_formats = supported_formats
        self._supported_frame_rates = supported_frame_rates
        self.status_calls = 0
        self.device_calls = 0
        self.install_calls = 0
        self.inspect_calls = 0
        self.capability_calls = 0

    def status(self) -> ExtensionStatus:
        self.status_calls += 1
        return self._status

    def enumerate_devices(self) -> list[str]:
        self.device_calls += 1
        return list(self._devices)

    def install_extension_result(self) -> InstallExtensionResult:
        self.install_calls += 1
        return self._install_result

    def stream_capabilities(self):
        self.capability_calls += 1
        supported_formats = (
            self._supported_formats
            if self._supported_formats is not None
            else tuple(self._status.supported_formats)
        )
        supported_frame_rates = (
            self._supported_frame_rates
            if self._supported_frame_rates is not None
            else tuple(self._status.supported_frame_rates)
        )
        return SimpleNamespace(
            supported_formats=supported_formats,
            supported_frame_rates=supported_frame_rates,
        )

    def inspect_installation(self) -> ExtensionRuntimeSnapshot:
        self.inspect_calls += 1
        return ExtensionRuntimeSnapshot(
            status=self._status,
            devices=list(self._devices),
            readiness=ExtensionReadiness(
                phase=(
                    "installed_visible"
                    if self._status.enabled and self._devices
                    else "pending_approval"
                    if self._status.approval_required
                    else "timeout_waiting_for_device"
                    if self._status.enabled
                    else ""
                ),
                ready=bool(self._status.enabled and self._devices),
                blocker_code=(
                    "ready"
                    if self._status.enabled and self._devices
                    else "approval_required"
                    if self._status.approval_required
                    else "device_not_visible"
                    if self._status.enabled
                    else "not_installed"
                ),
                message=(
                    "虚拟摄像头已安装并出现在系统设备列表中，可在 Zoom/Meet/OBS 中继续验证。"
                    if self._status.enabled and self._devices
                    else "需要在系统设置 > 隐私与安全性 中批准 AK Virtual Camera 扩展，批准后重新检查设备可见性。可使用 Open Settings 按钮快速打开系统设置。"
                    if self._status.approval_required
                    else "扩展状态已收敛，但系统视频设备列表里还没有出现虚拟摄像头。请重新打开目标应用并再次检查。必要时可先打开系统设置确认扩展状态。"
                    if self._status.enabled
                    else "虚拟摄像头尚未安装。"
                ),
                steps=["snapshot"],
                verification_targets=[{"id": "zoom", "ready": bool(self._status.enabled and self._devices)}],
            ),
        )

    def set_status(self, status: ExtensionStatus, devices: list[str]) -> None:
        self._status = status
        self._devices = list(devices)


class FakeProcess:
    def __init__(self, *, target, args, daemon: bool, name: str) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
        self.pid = 4321
        self._alive = False
        self.terminated = False

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        del timeout
        self._alive = False

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False


class FakeContext:
    def Queue(self, maxsize: int = 0):  # noqa: N802 - mirror multiprocessing API
        del maxsize
        return SimpleNamespace()

    def Process(self, *, target, args, daemon: bool, name: str):  # noqa: N802 - mirror multiprocessing API
        return FakeProcess(target=target, args=args, daemon=daemon, name=name)


def test_service_facade_poll_status_includes_macos_install_fields(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            approval_required=True,
            enabled=False,
            bundle_path="/Applications/AKVC.app",
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="pending_approval",
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALL_PENDING_APPROVAL),
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.poll_status()

    assert status.install_state == "install_pending_approval"
    assert status.install_phase == "pending_approval"
    assert status.install_devices == ["AK Virtual Camera"]
    assert status.approval_required is True
    assert status.install_enabled is False
    assert status.install_blocker_code == "approval_required"
    assert status.runtime_topology_kind == "camera_extension_direct_framebus"
    assert status.runtime_frame_path == "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app"
    assert status.runtime_host_role == "container_activation_command_bridge"
    assert status.runtime_host_in_frame_hot_path is False
    assert status.runtime_dedicated_host_daemon_required is False
    assert status.runtime_container_app_configured is True
    assert status.runtime_data_plane == "shared_memory_ringbuffer"
    assert status.runtime_control_plane == "host_activation_plus_sync_ipc"
    assert status.can_open_settings is True
    assert status.stream_start_ready is False
    assert "批准" in status.stream_start_message
    assert "批准" in status.install_message
    assert len(status.install_steps) == 3
    assert "Open Settings" in status.install_steps[0]
    assert len(status.verification_targets) == 6
    assert [target["id"] for target in status.verification_targets] == [
        "zoom",
        "teams",
        "google_meet",
        "obs",
        "quicktime",
        "facetime",
    ]
    assert all(target["ready"] is False for target in status.verification_targets)
    assert all("批准" in str(target["status"]) for target in status.verification_targets)


def test_service_facade_uses_current_app_bundle_as_macos_container(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}
    app_bundle = tmp_path / "Amaran Desktop.app"
    app_executable = app_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    app_executable.parent.mkdir(parents=True)
    app_executable.write_bytes(b"x")

    class FakeMacCamera:
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.sys.executable", str(app_executable), raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: FakeMacCamera(**kwargs))
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    ServiceFacade()

    assert observed["app_bundle"] == str(app_bundle)
    assert observed["app_executable"] == str(app_executable)


def test_service_facade_recheck_install_status_surfaces_manual_app_validation_summary(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
            devices=["AK Virtual Camera"],
            bundle_path="/Applications/AKVC.app",
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr(
        "akvc_app.services.facade.load_manual_app_validation_summary",
        lambda: ManualAppValidationSummary(
            present=True,
            ready=False,
            failed_criteria=["system_camera_device_visible"],
            unknown_criteria=["notarization_tooling_ready"],
            blockers=["system_camera_device_visible", "notarization_tooling_ready"],
            manifest_path="/tmp/session-manifest.json",
        ),
    )

    facade = ServiceFacade()
    status = facade.recheck_install_status()

    assert status.manual_app_validation_present is True
    assert status.manual_app_validation_ready is False
    assert status.manual_app_validation_failed_criteria == ["system_camera_device_visible"]
    assert status.manual_app_validation_failed_labels == ["系统已枚举到虚拟摄像头"]
    assert status.manual_app_validation_unknown_criteria == ["notarization_tooling_ready"]
    assert status.manual_app_validation_unknown_labels == ["公证工具链已就绪"]
    assert status.manual_app_validation_blockers == [
        "system_camera_device_visible",
        "notarization_tooling_ready",
    ]
    assert status.manual_app_validation_blocker_labels == [
        "系统已枚举到虚拟摄像头",
        "公证工具链已就绪",
    ]
    assert status.manual_app_validation_manifest_path == "/tmp/session-manifest.json"
    assert status.runtime_container_app_configured is True
    assert status.runtime_host_in_frame_hot_path is False


def test_service_facade_recheck_install_status_prefers_sdk_installation_snapshot(monkeypatch) -> None:
    class SnapshotOnlyMacCamera:
        def __init__(self) -> None:
            self.inspect_calls = 0
            self.capability_calls = 0

        def inspect_installation(self) -> ExtensionRuntimeSnapshot:
            self.inspect_calls += 1
            return ExtensionRuntimeSnapshot(
                status=ExtensionStatus(
                    state=ExtensionInstallState.INSTALLED,
                    enabled=True,
                    devices=["AK Virtual Camera"],
                    bundle_path="/Applications/AKVC.app",
                    ipc_probe_present=True,
                    ipc_ready=True,
                    ipc_transport="shared_memory_ringbuffer",
                ),
                devices=["AK Virtual Camera"],
                readiness=ExtensionReadiness(
                    phase="installed_visible",
                    ready=True,
                    blocker_code="ready",
                    message="虚拟摄像头已安装并出现在系统设备列表中，可在 Zoom/Meet/OBS 中继续验证。",
                    steps=["snapshot-ready"],
                    verification_targets=[{"id": "zoom", "ready": True, "status": "ok", "steps": []}],
                ),
            )

        def stream_capabilities(self):
            self.capability_calls += 1
            return SimpleNamespace(
                supported_formats=("1280x720@30/60 NV12", "1920x1080@30/60 NV12"),
                supported_frame_rates=(30, 60),
            )

        def status(self) -> ExtensionStatus:  # pragma: no cover - should not be used
            raise AssertionError("recheck_install_status should prefer inspect_installation()")

        def enumerate_devices(self) -> list[str]:  # pragma: no cover - should not be used
            raise AssertionError("recheck_install_status should prefer inspect_installation()")

        def install_extension_result(self):
            raise AssertionError("not used in this test")

    fake_camera = SnapshotOnlyMacCamera()

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.recheck_install_status()

    assert fake_camera.inspect_calls == 1
    assert fake_camera.capability_calls == 1
    assert status.install_state == "installed"
    assert status.install_phase == "installed_visible"
    assert status.stream_start_ready is True
    assert status.install_blocker_code == "ready"
    assert status.install_steps == ["snapshot-ready"]
    assert status.supported_formats == ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"]
    assert status.supported_frame_rates == [30, 60]
    assert status.ipc_transport == "shared_memory_ringbuffer"
    assert status.runtime_container_app_configured is True
    assert status.runtime_control_plane == "host_activation_plus_sync_ipc"


def test_service_facade_install_virtual_camera_captures_install_result(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.NOT_INSTALLED,
            approval_required=False,
            enabled=False,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
                bundle_path="/Applications/AKVC.app",
                supported_formats=["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
                supported_frame_rates=[30, 60],
                ipc_probe_present=True,
                ipc_ready=True,
                ipc_transport="shared_memory_ringbuffer",
                ipc_probe_path="/tmp/framebus-roundtrip.json",
            ),
            enumerated_devices=["AK Virtual Camera"],
        ),
        supported_formats=("1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"),
        supported_frame_rates=(30, 60),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.install_virtual_camera()

    assert status.install_state == "installed"
    assert status.install_phase == "installed_visible"
    assert status.install_devices == ["AK Virtual Camera"]
    assert status.install_enabled is True
    assert status.supported_formats == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert status.supported_frame_rates == [30, 60]
    assert status.ipc_probe_present is True
    assert status.ipc_ready is True
    assert status.ipc_transport == "shared_memory_ringbuffer"
    assert status.ipc_probe_path == "/tmp/framebus-roundtrip.json"
    assert status.install_blocker_code == "ready"
    assert status.can_open_settings is True
    assert status.stream_start_ready is True
    assert status.stream_start_message == ""
    assert "系统设备列表" in status.install_message
    assert status.runtime_topology_kind == "camera_extension_direct_framebus"
    assert status.runtime_container_app_configured is True
    assert status.runtime_host_in_frame_hot_path is False
    assert len(status.install_steps) == 3
    assert "Zoom" in status.install_steps[0]
    assert len(status.verification_targets) == 6
    assert all(target["ready"] is True for target in status.verification_targets)
    quicktime = next(target for target in status.verification_targets if target["id"] == "quicktime")
    assert "影片录制" in str(quicktime["steps"][0])
    assert "AK Virtual Camera" in str(quicktime["steps"][1])
    assert fake_camera.install_calls == 1


def test_service_facade_install_virtual_camera_keeps_start_blocked_when_stream_dependencies_missing(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.NOT_INSTALLED,
            approval_required=False,
            enabled=False,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
            ),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr(
        "akvc_app.services.facade._probe_stream_dependencies",
        lambda: (False, "桌面推流依赖缺失，请先安装 numpy / cv2 后再启动虚拟摄像头。"),
    )

    facade = ServiceFacade()
    status = facade.install_virtual_camera()

    assert status.install_phase == "installed_visible"
    assert status.stream_start_ready is False
    assert "numpy / cv2" in status.stream_start_message


def test_service_facade_install_virtual_camera_reports_pkg_install_failure(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.NOT_INSTALLED,
            approval_required=False,
            enabled=False,
        ),
        devices=[],
        install_result=InstallExtensionResult(
            success=False,
            phase="package_install_failed",
            state=ExtensionInstallState.INSTALL_FAILED,
            status=ExtensionStatus(
                state=ExtensionInstallState.INSTALL_FAILED,
                last_error="authentication failed",
            ),
            enumerated_devices=[],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.install_virtual_camera()

    assert status.install_state == "install_failed"
    assert status.install_phase == "package_install_failed"
    assert status.install_devices == []
    assert status.stream_start_ready is False
    assert "authentication failed" in status.install_message
    assert len(status.install_steps) == 3
    assert "AKVC_MACOS_PKG" in status.install_steps[0]


def test_service_facade_recheck_install_status_blocks_stream_when_ipc_environment_is_blocked(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ipc_direct_open_errno=13,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.recheck_install_status()

    assert status.install_phase == "installed_visible"
    assert status.install_devices == ["AK Virtual Camera"]
    assert status.ipc_probe_present is True
    assert status.ipc_ready is False
    assert status.ipc_environment_blocked is True
    assert status.ipc_direct_open_errno == 13
    assert status.install_blocker_code == "ipc_environment_blocked"
    assert status.stream_start_ready is False
    assert "IPC" in status.install_message
    assert "direct_open_errno=13" in status.install_message
    assert "framebus roundtrip" in status.install_steps[0]


def test_service_facade_recheck_install_status_surfaces_producer_side_ipc_blocker(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
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
            enumerated_devices=["AK Virtual Camera"],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.recheck_install_status()

    assert status.install_phase == "installed_visible"
    assert status.install_devices == ["AK Virtual Camera"]
    assert status.ipc_probe_present is True
    assert status.ipc_ready is False
    assert status.ipc_environment_blocked is True
    assert status.ipc_direct_open_errno == 1
    assert status.install_blocker_code == "ipc_environment_blocked"
    assert status.stream_start_ready is False
    assert "producer_open_failed" in status.install_message
    assert "direct_open_errno=1" in status.install_message
    assert "framebus roundtrip" in status.install_steps[0]


def test_service_facade_open_install_settings_uses_opener(monkeypatch) -> None:
    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr(
        "akvc_app.services.facade.VirtualCamera",
        lambda **kwargs: FakeMacCamera(
            status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
            devices=[],
            install_result=InstallExtensionResult(
                success=False,
                phase="pending_approval",
                state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
                status=ExtensionStatus(
                    state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
                    approval_required=True,
                ),
            ),
        ),
    )

    calls: list[str] = []
    facade = ServiceFacade(settings_opener=lambda: calls.append("open") or 0)

    assert facade.open_install_settings() is True
    assert calls == ["open"]


def test_service_facade_open_install_settings_rejects_non_macos(monkeypatch) -> None:
    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "win32", raising=False)
    monkeypatch.setattr(
        "akvc_app.services.facade._probe_stream_dependencies",
        lambda: (False, "桌面推流依赖缺失，请先安装 numpy / cv2 后再启动虚拟摄像头。"),
    )
    facade = ServiceFacade(settings_opener=lambda: 0)

    assert facade.open_install_settings() is False
    assert "macOS only" in (facade.poll_status().last_error or "")
    assert facade.poll_status().stream_start_ready is False
    assert "numpy / cv2" in (facade.poll_status().stream_start_message or "")


def test_service_facade_recheck_install_status_refreshes_latest_state(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            approval_required=True,
            enabled=False,
        ),
        devices=[],
        install_result=InstallExtensionResult(
            success=True,
            phase="pending_approval",
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALL_PENDING_APPROVAL),
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    first = facade.recheck_install_status()
    assert first.install_phase == "pending_approval"
    assert first.install_devices == []

    fake_camera.set_status(
        ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        ["AK Virtual Camera"],
    )

    second = facade.recheck_install_status()
    assert second.install_phase == "installed_visible"
    assert second.install_devices == ["AK Virtual Camera"]
    assert second.install_enabled is True
    assert all(target["ready"] is True for target in second.verification_targets)
    facetime = next(target for target in second.verification_targets if target["id"] == "facetime")
    assert "FaceTime" in str(facetime["steps"][0])


def test_service_facade_recheck_install_status_marks_waiting_for_device_when_enabled_without_devices(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
            all_devices=["FaceTime HD Camera"],
            device_prefix="AK Virtual Camera",
        ),
        devices=[],
        install_result=InstallExtensionResult(
            success=True,
            phase="timeout_waiting_for_device",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    status = facade.recheck_install_status()

    assert status.install_phase == "timeout_waiting_for_device"
    assert status.install_enabled is True
    assert status.install_devices == []
    assert status.install_all_devices == ["FaceTime HD Camera"]
    assert status.install_device_prefix == "AK Virtual Camera"
    assert status.stream_start_ready is False
    assert "还没有出现虚拟摄像头" in status.stream_start_message
    assert "AK Virtual Camera" in status.stream_start_message
    assert "FaceTime HD Camera" in status.stream_start_message
    assert "还没有出现虚拟摄像头" in status.install_message
    assert "AK Virtual Camera" in status.install_message
    assert "FaceTime HD Camera" in status.install_message
    assert all(target["ready"] is False for target in status.verification_targets)


def test_service_facade_poll_status_refreshes_stream_dependencies_when_probe_recovers(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )
    dependency_states = iter([
        (False, "桌面推流依赖缺失，请先安装 numpy / cv2 后再启动虚拟摄像头。"),
        (True, ""),
    ])

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr("akvc_app.services.facade._probe_stream_dependencies", lambda: next(dependency_states))

    facade = ServiceFacade()
    first = facade.poll_status()
    second = facade.poll_status()

    assert first.stream_start_ready is False
    assert "numpy / cv2" in first.stream_start_message
    assert second.install_phase == "installed_visible"
    assert second.stream_start_ready is True
    assert second.stream_start_message == ""


def test_service_facade_start_rejects_when_macos_camera_is_not_yet_visible(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        devices=[],
        install_result=InstallExtensionResult(
            success=True,
            phase="timeout_waiting_for_device",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    facade._state.selected_source_id = "pattern:colorbars"

    try:
        facade.start()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("start() should reject invisible macOS camera state")

    assert "还没有出现虚拟摄像头" in message
    assert facade.poll_status().running is False
    assert facade.poll_status().install_phase == "timeout_waiting_for_device"


def test_service_facade_start_allows_running_when_macos_camera_is_visible(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr("akvc_app.services.facade.mp.get_context", lambda method: FakeContext())

    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"
    facade.start()

    status = facade.poll_status()
    assert status.running is True
    assert status.install_phase == "installed_visible"
    assert status.install_devices == ["AK Virtual Camera"]
    assert status.stream_start_ready is True
    assert facade._proc is not None
    assert getattr(facade._proc, "pid", None) == 4321


def test_service_facade_start_rejects_when_macos_ipc_probe_is_blocked(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ipc_direct_open_errno=13,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])

    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"

    try:
        facade.start()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("start() should reject blocked macOS IPC state")

    assert "FrameBus" in message or "IPC" in message
    assert "direct_open_errno=13" in message
    assert facade.poll_status().running is False


def test_service_facade_start_reports_missing_worker_dependencies(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr(
        "akvc_app.services.facade._load_frame_worker_symbols",
        lambda: (_ for _ in ()).throw(ModuleNotFoundError("numpy")),
    )

    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"

    try:
        facade.start()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("start() should surface missing worker dependencies")

    assert "numpy" in message or "OpenCV" in message


def test_service_facade_recheck_install_status_can_clear_runtime_dependency_error(monkeypatch) -> None:
    fake_camera = FakeMacCamera(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            approval_required=False,
            enabled=True,
        ),
        devices=["AK Virtual Camera"],
        install_result=InstallExtensionResult(
            success=True,
            phase="installed_visible",
            state=ExtensionInstallState.INSTALLED,
            status=ExtensionStatus(state=ExtensionInstallState.INSTALLED, enabled=True),
            enumerated_devices=["AK Virtual Camera"],
        ),
    )
    dependency_states = iter([
        (False, "桌面推流依赖缺失，请先安装 numpy / cv2 后再启动虚拟摄像头。"),
        (True, ""),
    ])

    monkeypatch.setattr("akvc_app.services.facade.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc_app.services.facade.VirtualCamera", lambda **kwargs: fake_camera)
    monkeypatch.setattr("akvc_app.services.facade._list_usb_sources", lambda max_probe=4: [])
    monkeypatch.setattr("akvc_app.services.facade._probe_stream_dependencies", lambda: next(dependency_states))
    monkeypatch.setattr(
        "akvc_app.services.facade._load_frame_worker_symbols",
        lambda: (_ for _ in ()).throw(ModuleNotFoundError("numpy")),
    )

    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"

    try:
        facade.start()
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("start() should surface missing worker dependencies")

    recovered = facade.recheck_install_status()

    assert recovered.install_phase == "installed_visible"
    assert recovered.stream_start_ready is True
    assert recovered.stream_start_message == ""
