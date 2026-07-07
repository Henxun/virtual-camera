# SPDX-License-Identifier: Apache-2.0
"""Focused tests for macOS install result APIs without numpy dependency."""

from __future__ import annotations

from dataclasses import dataclass

from akvc.platforms.macos.installer import (
    ExtensionInstallState,
    ExtensionStatus,
    InstallExtensionResult,
    SyncIPCConfigurationResult,
    UninstallExtensionResult,
)
from akvc.platforms.macos.virtual_camera import MacVirtualCamera
from akvc.sdk.virtual_camera import VirtualCamera


@dataclass
class FakeInstallerWithResult:
    result: InstallExtensionResult
    uninstall_result: UninstallExtensionResult | None = None
    result_calls: int = 0
    install_calls: int = 0
    uninstall_result_calls: int = 0
    uninstall_calls: int = 0
    sync_calls: list[str] | None = None

    def status(self) -> ExtensionStatus:
        return self.result.status

    def extension_state(self) -> ExtensionInstallState:
        return self.result.state

    def install_extension_result(self) -> InstallExtensionResult:
        self.result_calls += 1
        return self.result

    def install_extension(self) -> bool:
        self.install_calls += 1
        return self.result.success

    def uninstall_extension_result(self) -> UninstallExtensionResult:
        self.uninstall_result_calls += 1
        if self.uninstall_result is None:
            raise AssertionError("uninstall_result not configured")
        return self.uninstall_result

    def uninstall_extension(self) -> bool:
        self.uninstall_calls += 1
        return bool(self.uninstall_result and self.uninstall_result.success)

    def enumerate_devices(self) -> list[str]:
        return list(self.result.enumerated_devices)

    def sync_ipc_configuration_result(self, shared_memory_name: str) -> SyncIPCConfigurationResult:
        if self.sync_calls is None:
            self.sync_calls = []
        self.sync_calls.append(shared_memory_name)
        return SyncIPCConfigurationResult(
            supported=True,
            success=True,
            phase="sync_command_succeeded",
            shared_memory_name=shared_memory_name,
        )


@dataclass
class FakeLegacyInstaller:
    success: bool
    status_value: ExtensionStatus
    devices: list[str]
    install_calls: int = 0
    uninstall_calls: int = 0
    device_calls: int = 0

    def status(self) -> ExtensionStatus:
        return self.status_value

    def extension_state(self) -> ExtensionInstallState:
        return self.status_value.state

    def install_extension(self) -> bool:
        self.install_calls += 1
        return self.success

    def enumerate_devices(self) -> list[str]:
        self.device_calls += 1
        return list(self.devices)

    def uninstall_extension(self) -> bool:
        self.uninstall_calls += 1
        return False


def test_macos_virtual_camera_exposes_install_extension_result() -> None:
    result = InstallExtensionResult(
        success=True,
        phase="installed_visible",
        state=ExtensionInstallState.INSTALLED,
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
            enabled=True,
        ),
        enumerated_devices=["AK Virtual Camera"],
        install_returncode=0,
    )
    installer = FakeInstallerWithResult(result=result)

    cam = MacVirtualCamera(installer=installer)

    observed = cam.install_extension_result()

    assert observed == result
    assert cam.install_extension() is True
    assert installer.result_calls == 2
    assert installer.install_calls == 0


def test_macos_virtual_camera_wraps_legacy_installer_result_shape() -> None:
    installer = FakeLegacyInstaller(
        success=False,
        status_value=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            last_error="legacy install failed",
        ),
        devices=[],
    )

    cam = MacVirtualCamera(installer=installer)
    result = cam.install_extension_result()

    assert result.success is False
    assert result.phase == "legacy_failed"
    assert result.state is ExtensionInstallState.INSTALL_FAILED
    assert result.status.last_error == "legacy install failed"
    assert result.enumerated_devices == []
    assert installer.install_calls == 1
    assert installer.device_calls == 1


def test_sdk_virtual_camera_exposes_install_extension_result_on_macos(monkeypatch) -> None:
    expected = InstallExtensionResult(
        success=True,
        phase="pending_approval",
        state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            approval_required=True,
        ),
    )

    class FakeMacBackend:
        started = False
        consumer_count = 0

        def install_extension_result(self):
            return expected

        def install_extension(self) -> bool:
            return expected.success

        def uninstall_extension_result(self):
            return UninstallExtensionResult(
                success=True,
                phase="uninstalled",
                state=ExtensionInstallState.NOT_INSTALLED,
                status=ExtensionStatus(state=ExtensionInstallState.NOT_INSTALLED),
            )

        def uninstall_extension(self) -> bool:
            return True

        def sync_ipc_configuration_result(self, shared_memory_name: str | None = None):
            return SyncIPCConfigurationResult(
                supported=True,
                success=True,
                phase="sync_command_succeeded",
                shared_memory_name=shared_memory_name or "/akvc-frames-v1",
            )

        def sync_ipc_configuration(self, shared_memory_name: str | None = None) -> bool:
            del shared_memory_name
            return True

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend()),
    )

    vc = VirtualCamera()

    assert vc.install_extension_result() == expected
    assert vc.install_extension() is True
    assert vc.uninstall_extension_result().phase == "uninstalled"
    assert vc.uninstall_extension() is True
    assert vc.sync_ipc_configuration() is True
    assert vc.sync_ipc_configuration_result().phase == "sync_command_succeeded"


def test_macos_virtual_camera_exposes_sync_ipc_configuration_result() -> None:
    result = InstallExtensionResult(
        success=True,
        phase="installed_visible",
        state=ExtensionInstallState.INSTALLED,
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
            enabled=True,
        ),
        enumerated_devices=["AK Virtual Camera"],
    )
    installer = FakeInstallerWithResult(result=result, sync_calls=[])

    cam = MacVirtualCamera(installer=installer)
    sync_result = cam.sync_ipc_configuration_result("/akvc-custom")

    assert sync_result.supported is True
    assert sync_result.success is True
    assert sync_result.shared_memory_name == "/akvc-custom"
    assert installer.sync_calls == ["/akvc-custom"]
    assert cam.sync_ipc_configuration("/akvc-custom") is True


def test_sdk_virtual_camera_install_extension_result_is_none_off_macos(monkeypatch) -> None:
    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "linux", raising=False)

    vc = VirtualCamera()

    assert vc.enumerate_devices() == []
    assert vc.status() is None
    assert vc.readiness() is None
    assert vc.inspect_installation() is None
    assert vc.ipc_descriptor() is None
    assert vc.stream_capabilities() is None
    assert vc.install_extension_result() is None
    assert vc.install_extension() is False
    assert vc.uninstall_extension_result() is None
    assert vc.uninstall_extension() is False
    assert vc.sync_ipc_configuration_result() is None
    assert vc.sync_ipc_configuration() is False


def test_macos_virtual_camera_exposes_uninstall_extension_result() -> None:
    install_result = InstallExtensionResult(
        success=True,
        phase="installed_visible",
        state=ExtensionInstallState.INSTALLED,
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
            enabled=True,
        ),
        enumerated_devices=["AK Virtual Camera"],
    )
    uninstall_result = UninstallExtensionResult(
        success=True,
        phase="uninstalled",
        state=ExtensionInstallState.NOT_INSTALLED,
        status=ExtensionStatus(
            state=ExtensionInstallState.NOT_INSTALLED,
            devices=[],
            enabled=False,
        ),
        enumerated_devices=[],
        uninstall_returncode=0,
    )
    installer = FakeInstallerWithResult(
        result=install_result,
        uninstall_result=uninstall_result,
    )

    cam = MacVirtualCamera(installer=installer)

    observed = cam.uninstall_extension_result()

    assert observed == uninstall_result
    assert cam.uninstall_extension() is True
    assert installer.uninstall_result_calls == 2
    assert installer.uninstall_calls == 0
