# SPDX-License-Identifier: Apache-2.0
"""macOS virtual camera backend tests."""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from akvc.core.frame import FourCC

from akvc.platforms.macos import virtual_camera as macos_virtual_camera_module
from akvc.platforms.macos.virtual_camera import (
    ExtensionInstallState,
    MacVirtualCamera,
)
from akvc.platforms.macos.installer import ExtensionStatus, SyncIPCConfigurationResult
from akvc.platforms.macos.ipc import MacIPCDescriptor, MacStreamCapabilities


class FakeSink:
    def __init__(self, *, shared_memory_name: str | None = None) -> None:
        self.open_calls = 0
        self.close_calls = 0
        self.published = []
        self.consumer_count = 2
        self.shared_memory_name = shared_memory_name

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def publish(self, frame) -> None:
        self.published.append(frame)


class FakePipeline:
    def __init__(self) -> None:
        self.frames = []

    def process(self, frame):
        self.frames.append(frame)
        return frame


class FakeDirectSender:
    def __init__(
        self,
        *,
        fail_open: bool = False,
        open_error: str = "direct sender open failed",
        fail_names: set[str] | None = None,
        available_names: list[str] | None = None,
        available_snapshot: dict[str, object] | None = None,
        request_access_names: list[str] | None = None,
        request_access_snapshot: dict[str, object] | None = None,
    ) -> None:
        self.fail_open = fail_open
        self.open_error = open_error
        self.fail_names = {str(name) for name in (fail_names or set())}
        self.available_names = list(available_names or [])
        self.available_snapshot_payload = dict(available_snapshot or {})
        self.request_access_names = (
            None if request_access_names is None else list(request_access_names)
        )
        self.request_access_snapshot_payload = (
            None if request_access_snapshot is None else dict(request_access_snapshot)
        )
        self.available_device_names_calls = 0
        self.open_calls: list[str] = []
        self.close_calls = 0
        self.published = []
        self.consumer_count = 4
        self.request_camera_access_calls = 0

    def available_device_names(self) -> list[str]:
        self.available_device_names_calls += 1
        return list(self.available_names)

    def available_device_snapshot(self) -> dict[str, object]:
        payload = dict(self.available_snapshot_payload)
        payload.setdefault("all_devices", list(self.available_names))
        payload.setdefault("environment_device_enumeration_empty", len(self.available_names) == 0)
        return payload

    def open(self, *, name: str) -> None:
        self.open_calls.append(name)
        if self.fail_open or name in self.fail_names:
            raise RuntimeError(self.open_error)

    def request_camera_access(self) -> dict[str, object]:
        self.request_camera_access_calls += 1
        if self.request_access_names is not None:
            self.available_names = list(self.request_access_names)
        if self.request_access_snapshot_payload is not None:
            self.available_snapshot_payload = dict(self.request_access_snapshot_payload)
        payload = dict(self.available_snapshot_payload)
        payload.setdefault("all_devices", list(self.available_names))
        payload.setdefault("environment_device_enumeration_empty", len(self.available_names) == 0)
        return payload

    def publish(self, frame) -> None:
        self.published.append(frame)

    def close(self) -> None:
        self.close_calls += 1


class FakeBits(bytearray):
    def setsize(self, size: int) -> None:
        self._size = size

    def asstring(self, size: int) -> bytes:
        return bytes(self[:size])


class FakeQImage:
    class Format:
        Format_BGR888 = 1
        Format_BGRA8888 = 2
        Format_Grayscale8 = 3

    def __init__(self, width: int, height: int, payload: bytes, *, fmt: int | None = None) -> None:
        self._width = width
        self._height = height
        self._payload = payload
        self._format = self.Format.Format_BGR888 if fmt is None else fmt

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def bytesPerLine(self) -> int:
        if self._format == self.Format.Format_BGRA8888:
            return self._width * 4
        return self._width * 3

    def format(self) -> int:
        return self._format

    def constBits(self) -> FakeBits:
        return FakeBits(self._payload)


class FakeQPixmap:
    def __init__(self, image: FakeQImage) -> None:
        self._image = image

    def toImage(self) -> FakeQImage:
        return self._image


class FakeWidget:
    def __init__(self, grabbed) -> None:
        self._grabbed = grabbed

    def grab(self):
        return self._grabbed


class FakeScreen:
    def __init__(self, grabbed) -> None:
        self._grabbed = grabbed
        self.calls: list[tuple[int, int, int, int, int]] = []

    def grabWindow(self, window: int, x: int, y: int, width: int, height: int):
        self.calls.append((window, x, y, width, height))
        return self._grabbed


@dataclass
class FakeInstaller:
    state: ExtensionInstallState = ExtensionInstallState.NOT_INSTALLED
    devices: list[str] | None = None
    all_devices: list[str] | None = None
    device_prefix: str | None = None
    approval_required: bool = False
    enabled: bool | None = None
    ipc_probe_present: bool = False
    ipc_ready: bool | None = None
    ipc_environment_blocked: bool = False
    ipc_last_error: str | None = None
    ipc_direct_open_errno: int | None = None
    system_extension_registered: bool | None = None
    install_calls: int = 0
    uninstall_calls: int = 0
    state_calls: int = 0
    device_calls: int = 0
    sync_calls: list[str] = field(default_factory=list)
    sync_supported: bool = False
    sync_success: bool = True
    sync_last_error: str | None = None
    sync_promotes_ipc_ready: bool = False
    sync_result_shared_memory_name: str | None = None
    uninstall_success: bool | None = None

    def extension_state(self) -> ExtensionInstallState:
        self.state_calls += 1
        return self.state

    def install_extension(self) -> bool:
        self.install_calls += 1
        return self.state is not ExtensionInstallState.INSTALL_FAILED

    def uninstall_extension(self) -> bool:
        self.uninstall_calls += 1
        success = self.uninstall_success
        if success is None:
            success = self.state is not ExtensionInstallState.INSTALL_FAILED
        if success:
            self.state = ExtensionInstallState.NOT_INSTALLED
            self.devices = []
            self.enabled = False
        return bool(success)

    def enumerate_devices(self) -> list[str]:
        self.device_calls += 1
        return list(self.devices or [])

    def status(self) -> ExtensionStatus:
        enabled = self.state is ExtensionInstallState.INSTALLED if self.enabled is None else self.enabled
        return ExtensionStatus(
            state=self.state,
            devices=list(self.devices or []),
            all_devices=list(self.all_devices or []),
            device_prefix=self.device_prefix,
            enabled=enabled,
            approval_required=self.approval_required,
            ipc_probe_present=self.ipc_probe_present,
            ipc_ready=self.ipc_ready,
            ipc_environment_blocked=self.ipc_environment_blocked,
            ipc_last_error=self.ipc_last_error,
            ipc_direct_open_errno=self.ipc_direct_open_errno,
            system_extension_registered=self.system_extension_registered,
        )

    def sync_ipc_configuration_result(self, shared_memory_name: str) -> SyncIPCConfigurationResult:
        self.sync_calls.append(shared_memory_name)
        if self.sync_success and self.sync_promotes_ipc_ready:
            self.ipc_probe_present = True
            self.ipc_ready = True
            self.ipc_environment_blocked = False
            self.ipc_last_error = None
            self.ipc_direct_open_errno = None
        return SyncIPCConfigurationResult(
            supported=self.sync_supported,
            success=self.sync_success,
            phase="sync_command_succeeded" if self.sync_success else "sync_command_failed",
            shared_memory_name=self.sync_result_shared_memory_name or shared_memory_name,
            last_error=self.sync_last_error,
        )


class ExplodingInstaller(FakeInstaller):
    def status(self) -> ExtensionStatus:
        raise AssertionError("status() should not be used when direct sender can enumerate devices")

    def enumerate_devices(self) -> list[str]:
        raise AssertionError(
            "enumerate_devices() should not be used when direct sender can enumerate devices"
        )


def test_macos_virtual_camera_start_push_and_close() -> None:
    sink = FakeSink()
    pipeline = FakePipeline()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )

    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=installer,
    )
    cam.start()
    assert cam.backend_name == "shared_memory"
    assert cam.using_direct_sender is False
    assert cam.helper_hot_path_used is False
    assert cam.shared_memory_fallback_used is True
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "fallback_shared_memory"
    assert cam.direct_sender_last_error
    cam.push_frame(np.zeros((8, 10, 3), dtype=np.uint8))
    cam.close()
    cam.close()

    assert sink.open_calls == 1
    assert sink.close_calls == 1
    assert len(pipeline.frames) == 1
    assert len(sink.published) == 1
    assert cam.started is False


def test_macos_virtual_camera_prefers_direct_sender_when_available() -> None:
    direct_sender = FakeDirectSender()
    sink = FakeSink()
    observed = {}
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )

    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        direct_sender_library="/tmp/libakvc-macos-direct-sender.dylib",
        direct_sender_factory=lambda **kwargs: observed.update(kwargs) or direct_sender,
        pipeline=FakePipeline(),
        installer=installer,
    )

    cam.start(name="AKVC Direct")
    assert cam.backend_name == "direct_sender"
    assert cam.using_direct_sender is True
    assert cam.helper_hot_path_used is False
    assert cam.shared_memory_fallback_used is False
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "active"
    assert cam.direct_sender_target_name == "AKVC Direct"
    assert cam.direct_sender_last_error is None
    assert cam.direct_sender_library_path == "/tmp/libakvc-macos-direct-sender.dylib"
    cam.push_frame(np.zeros((8, 10, 3), dtype=np.uint8))
    cam.close()

    assert direct_sender.open_calls == ["AKVC Direct"]
    assert observed["camera_name"] == "AKVC Direct"
    assert observed["library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert len(direct_sender.published) == 1
    assert direct_sender.close_calls == 1
    assert sink.open_calls == 0
    assert installer.sync_calls == []
    assert cam.started is False


def test_macos_virtual_camera_direct_sender_success_does_not_create_default_installer(
    monkeypatch,
) -> None:
    direct_sender = FakeDirectSender()
    created = []

    def fail_factory(**kwargs):
        created.append(kwargs)
        raise AssertionError("default installer should not be created")

    monkeypatch.setattr(
        macos_virtual_camera_module,
        "_create_default_installer_from_app_config",
        fail_factory,
    )

    cam = MacVirtualCamera(
        direct_only=True,
        direct_sender_factory=lambda **kwargs: direct_sender,
    )

    cam.start(name="AKVC Direct")
    topology = cam.runtime_topology()
    cam.close()

    assert created == []
    assert direct_sender.open_calls == ["AKVC Direct"]
    assert topology["runtime_topology_kind"] == "camera_extension_direct_sender"


def test_macos_virtual_camera_runtime_topology_reports_direct_sender_data_plane() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
        host_bundle="/Applications/Amaran Desktop.app",
    )

    cam.start(name="AKVC Direct")
    topology = cam.runtime_topology()

    assert topology["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert topology["runtime_host_in_frame_hot_path"] is False
    assert topology["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert topology["runtime_control_plane"] == "host_activation_only"
    assert topology["runtime_container_app_configured"] is True


def test_macos_virtual_camera_runtime_topology_preserves_shared_memory_fallback_contract() -> None:
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        ipc_probe_present=True,
        ipc_ready=True,
        sync_supported=True,
    )
    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: FakeSink(),
        installer=installer,
        direct_sender_factory=None,
        host_bundle="/Applications/Amaran Desktop.app",
    )

    topology = cam.runtime_topology()

    assert topology["runtime_topology_kind"] == "camera_extension_direct_framebus"
    assert topology["runtime_host_in_frame_hot_path"] is False
    assert topology["runtime_data_plane"] == "shared_memory_ringbuffer"
    assert topology["runtime_control_plane"] == "host_activation_plus_sync_ipc"


def test_macos_virtual_camera_runtime_snapshot_reports_shared_memory_backend() -> None:
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        all_devices=["AK Virtual Camera", "FaceTime HD Camera"],
        device_prefix="AK Virtual Camera",
        ipc_probe_present=True,
        ipc_ready=True,
        sync_supported=True,
    )
    sink = FakeSink(shared_memory_name="/akvc-demo-runtime")
    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        installer=installer,
        direct_sender_factory=None,
        host_bundle="/Applications/Amaran Desktop.app",
    )

    cam.start(name="AK Virtual Camera")
    snapshot = cam.runtime_snapshot()

    assert snapshot["started"] is True
    assert snapshot["camera_name"] == "AK Virtual Camera"
    assert snapshot["backend_name"] == "shared_memory"
    assert snapshot["using_direct_sender"] is False
    assert snapshot["shared_memory_fallback_used"] is True
    assert snapshot["shared_memory_name"] == "/akvc-demo-runtime"
    assert snapshot["consumer_count"] == 2
    assert snapshot["runtime_topology"]["runtime_topology_kind"] == "camera_extension_direct_framebus"
    assert snapshot["ipc_descriptor"]["framebus"]["shared_memory_name"] == "/akvc-frames-v1"
    assert snapshot["stream_capabilities"]["supported_frame_rates"] == [30, 60]
    assert snapshot["status"]["state"] == "installed"
    assert snapshot["status"]["device_prefix"] == "AK Virtual Camera"


def test_macos_virtual_camera_runtime_snapshot_reports_direct_sender_backend() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        all_devices=["AK Virtual Camera"],
        device_prefix="AK Virtual Camera",
    )
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
        host_bundle="/Applications/Amaran Desktop.app",
    )

    cam.start(name="AKVC Direct")
    cam.push_frame(np.zeros((8, 10, 3), dtype=np.uint8))
    snapshot = cam.runtime_snapshot()

    assert snapshot["started"] is True
    assert snapshot["camera_name"] == "AKVC Direct"
    assert snapshot["backend_name"] == "direct_sender"
    assert snapshot["using_direct_sender"] is True
    assert snapshot["direct_sender_state"] == "active"
    assert snapshot["direct_sender_target_name"] == "AKVC Direct"
    assert snapshot["shared_memory_fallback_used"] is False
    assert snapshot["runtime_topology"]["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert snapshot["last_frame_fourcc"] == cam.last_frame_fourcc
    assert snapshot["last_frame_format_name"] == cam.last_frame_format_name
    assert snapshot["status"]["state"] == "installed"
    assert snapshot["status"]["devices"] == ["AK Virtual Camera"]


def test_macos_virtual_camera_direct_sender_can_restart_after_stop() -> None:
    created_senders: list[FakeDirectSender] = []
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )

    def build_sender(**kwargs):
        del kwargs
        sender = FakeDirectSender()
        created_senders.append(sender)
        return sender

    cam = MacVirtualCamera(
        direct_sender_factory=build_sender,
        installer=installer,
    )

    cam.start(name="AKVC Direct")
    cam.push_frame(np.zeros((8, 10, 3), dtype=np.uint8))
    cam.stop()
    cam.start(name="AKVC Direct")
    cam.push_frame(np.zeros((8, 10, 3), dtype=np.uint8))
    cam.close()

    assert len(created_senders) == 2
    assert created_senders[0].open_calls == ["AKVC Direct"]
    assert created_senders[1].open_calls == ["AKVC Direct"]
    assert len(created_senders[0].published) == 1
    assert len(created_senders[1].published) == 1
    assert created_senders[0].close_calls == 1
    assert created_senders[1].close_calls == 1
    assert cam.started is False


def test_macos_virtual_camera_direct_sender_bypasses_ipc_probe_requirement() -> None:
    direct_sender = FakeDirectSender()
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        ipc_probe_present=True,
        ipc_ready=False,
        ipc_environment_blocked=True,
        ipc_last_error="probe status=open_failed; direct_open_errno=13",
        ipc_direct_open_errno=13,
    )

    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        direct_sender_factory=lambda **kwargs: direct_sender,
        pipeline=FakePipeline(),
        installer=installer,
    )

    cam.start()

    assert direct_sender.open_calls == ["AK Virtual Camera"]
    assert sink.open_calls == 0
    assert installer.sync_calls == []
    assert cam.started is True
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "active"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error is None


def test_macos_virtual_camera_direct_sender_bypasses_install_failed_status_when_device_is_visible() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=["AK Virtual Camera"],
        enabled=False,
        ipc_probe_present=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AK Virtual Camera")

    assert cam.started is True
    assert cam.backend_name == "direct_sender"
    assert cam.using_direct_sender is True
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "active"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error is None
    assert direct_sender.open_calls == ["AK Virtual Camera"]


def test_macos_virtual_camera_direct_sender_retries_enumerated_visible_name() -> None:
    direct_sender = FakeDirectSender(fail_names={"AKVC Demo"})
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Demo")

    assert cam.started is True
    assert cam.backend_name == "direct_sender"
    assert cam.using_direct_sender is True
    assert cam.direct_sender_state == "active"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error is None
    assert direct_sender.open_calls == ["AKVC Demo", "AK Virtual Camera"]


def test_macos_virtual_camera_direct_sender_prefers_native_visible_names_without_installer() -> None:
    direct_sender = FakeDirectSender(
        fail_names={"AKVC Demo"},
        available_names=["FaceTime HD Camera", "AK Virtual Camera"],
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=ExplodingInstaller(),
    )

    cam.start(name="AKVC Demo")

    assert cam.started is True
    assert cam.backend_name == "direct_sender"
    assert cam.using_direct_sender is True
    assert cam.direct_sender_state == "active"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error is None
    assert direct_sender.available_device_names_calls == 1
    assert direct_sender.open_calls == ["AKVC Demo", "AK Virtual Camera"]


def test_macos_virtual_camera_native_direct_sender_does_not_retarget_to_unrelated_virtual_camera() -> None:
    direct_sender = FakeDirectSender(
        fail_names={"AKVC Demo"},
        available_names=["OBS Virtual Camera", "FaceTime HD Camera"],
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    try:
        cam.start(name="AKVC Demo")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected start() to fail instead of retargeting to OBS Virtual Camera")

    assert direct_sender.available_device_names_calls == 1
    assert direct_sender.open_calls == ["AKVC Demo"]


def test_macos_virtual_camera_reports_missing_visible_camera_when_direct_sender_open_fails_without_candidates() -> None:
    direct_sender = FakeDirectSender(
        available_names=[],
        fail_open=True,
        open_error="camera device not found: AKVC Demo",
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    try:
        cam.start(name="AKVC Demo")
    except RuntimeError as exc:
        message = str(exc)
        assert "direct sender unavailable" in message
        assert "camera device not found: AKVC Demo" in message
        assert "current process snapshot reported no system video devices visible" in message
    else:
        raise AssertionError("expected start() to surface missing visible camera diagnostics")

    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_target_name == "AKVC Demo"
    assert cam.direct_sender_last_error == (
        "camera device not found: AKVC Demo "
        "(current process snapshot reported no system video devices visible)"
    )
    assert direct_sender.open_calls == ["AKVC Demo"]


def test_macos_virtual_camera_reports_environment_when_current_process_sees_no_video_devices() -> None:
    direct_sender = FakeDirectSender(
        fail_open=True,
        open_error="camera device not found: AKVC Demo",
        available_names=[],
        available_snapshot={
            "environment_device_enumeration_empty": True,
            "camera_access_status": "denied",
        },
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    try:
        cam.start(name="AKVC Demo")
    except RuntimeError as exc:
        message = str(exc)
        assert "direct sender unavailable" in message
        assert "camera device not found: AKVC Demo" in message
        assert "current process snapshot reported no system video devices visible" in message
        assert "camera access status: denied" in message
    else:
        raise AssertionError("expected start() to surface empty environment diagnostics")

    assert cam.direct_sender_last_error == (
        "camera device not found: AKVC Demo "
        "(current process snapshot reported no system video devices visible; camera access status: denied)"
    )
    assert direct_sender.open_calls == ["AKVC Demo"]


def test_macos_virtual_camera_auto_requests_camera_access_when_status_is_not_determined() -> None:
    direct_sender = FakeDirectSender(
        available_names=[],
        available_snapshot={
            "environment_device_enumeration_empty": True,
            "camera_access_status": "not_determined",
        },
        request_access_names=["AKVC Demo"],
        request_access_snapshot={
            "all_devices": ["AKVC Demo"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        },
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        width=1,
        height=1,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Demo")

    assert direct_sender.request_camera_access_calls == 1
    assert direct_sender.open_calls == ["AKVC Demo"]
    assert cam.started is True
    assert cam.using_direct_sender is True


def test_macos_virtual_camera_does_not_auto_request_camera_access_when_status_is_denied() -> None:
    direct_sender = FakeDirectSender(
        available_names=[],
        available_snapshot={
            "environment_device_enumeration_empty": True,
            "camera_access_status": "denied",
        },
        request_access_names=["AKVC Demo"],
        request_access_snapshot={
            "all_devices": ["AKVC Demo"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        },
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Demo")

    assert direct_sender.request_camera_access_calls == 0
    assert direct_sender.open_calls == ["AKVC Demo"]
    assert cam.started is True
    assert cam.using_direct_sender is True


def test_macos_virtual_camera_exposes_direct_sender_device_snapshot() -> None:
    direct_sender = FakeDirectSender(
        available_names=["AKVC Demo"],
        available_snapshot={
            "all_devices": ["AKVC Demo"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        },
    )
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=ExplodingInstaller(),
    )

    assert cam.direct_sender_device_snapshot() == {
        "all_devices": ["AKVC Demo"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }


def test_macos_virtual_camera_exposes_direct_sender_readiness() -> None:
    direct_sender = FakeDirectSender(
        available_names=["AKVC Demo"],
        available_snapshot={
            "all_devices": ["AKVC Demo"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        },
    )
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=ExplodingInstaller(),
    )

    readiness = cam.direct_sender_readiness(name="AKVC Demo")

    assert readiness["ready"] is True
    assert readiness["blocker_code"] == "ready"
    assert readiness["camera_name"] == "AKVC Demo"
    assert readiness["target_visible"] is True


def test_macos_virtual_camera_direct_sender_readiness_reports_unavailable_library() -> None:
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("library missing")),
        installer=ExplodingInstaller(),
    )

    readiness = cam.direct_sender_readiness(name="AKVC Demo")

    assert readiness["ready"] is False
    assert readiness["blocker_code"] == "direct_sender_unavailable"
    assert readiness["camera_name"] == "AKVC Demo"
    assert "library missing" in readiness["message"]


def test_macos_virtual_camera_direct_sender_readiness_surfaces_installation_blocker_when_target_not_visible() -> None:
    direct_sender = FakeDirectSender(
        available_names=["OBS Virtual Camera", "FaceTime HD Camera"],
        available_snapshot={
            "all_devices": ["OBS Virtual Camera", "FaceTime HD Camera"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        },
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        all_devices=["OBS Virtual Camera", "FaceTime HD Camera"],
        enabled=False,
        system_extension_registered=False,
    )
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    readiness = cam.direct_sender_readiness(name="AKVC Demo")

    assert readiness["ready"] is False
    assert readiness["blocker_code"] == "system_extension_not_registered"
    assert readiness["installer_blocker_code"] == "system_extension_not_registered"
    assert readiness["direct_sender_blocker_code"] == "target_device_not_visible"
    assert readiness["camera_name"] == "AKVC Demo"
    assert readiness["camera_access_status"] == "authorized"
    assert readiness["system_extension_registered"] is False
    assert readiness["target_visible"] is False
    assert "system extension" in readiness["message"].lower()


def test_macos_virtual_camera_direct_sender_readiness_preserves_camera_access_blocker() -> None:
    direct_sender = FakeDirectSender(
        available_names=[],
        available_snapshot={
            "all_devices": [],
            "camera_access_status": "denied",
            "environment_device_enumeration_empty": True,
        },
    )
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=ExplodingInstaller(),
    )

    readiness = cam.direct_sender_readiness(name="AKVC Demo")

    assert readiness["ready"] is False
    assert readiness["blocker_code"] == "camera_access_denied"
    assert "installer_blocker_code" not in readiness


def test_macos_virtual_camera_attempts_direct_open_when_native_snapshot_reports_empty_environment() -> None:
    direct_sender = FakeDirectSender(
        available_names=[],
        available_snapshot={"environment_device_enumeration_empty": True},
    )
    installer = ExplodingInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_only=True,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Demo")

    assert direct_sender.open_calls == ["AKVC Demo"]
    assert cam.started is True
    assert cam.using_direct_sender is True


def test_macos_virtual_camera_direct_only_raises_without_installer_fallback() -> None:
    direct_sender = FakeDirectSender(
        fail_open=True,
        available_names=["AKVC Demo"],
    )
    installer = ExplodingInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_only=True,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    try:
        cam.start(name="AKVC Demo")
    except RuntimeError as exc:
        assert str(exc) == "macOS direct sender unavailable: direct sender open failed"
    else:
        raise AssertionError("expected direct_only start() to stop after direct sender failure")

    assert direct_sender.open_calls == ["AKVC Demo"]


def test_macos_virtual_camera_direct_only_requires_direct_sender_library() -> None:
    installer = ExplodingInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_only=True,
        direct_sender_factory=None,
        installer=installer,
    )

    try:
        cam.start(name="AKVC Demo")
    except RuntimeError as exc:
        assert str(exc) == "macOS direct sender unavailable: macOS direct sender is required but unavailable"
    else:
        raise AssertionError("expected direct_only start() to require direct sender availability")


def test_macos_virtual_camera_enumerate_devices_merges_native_and_installer_names() -> None:
    direct_sender = FakeDirectSender(
        available_names=["OBS Virtual Camera", "AK Virtual Camera", "AK Virtual Camera"],
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera", "AKVC Demo"],
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    assert cam.enumerate_devices() == [
        "OBS Virtual Camera",
        "AK Virtual Camera",
        "AKVC Demo",
    ]
    assert direct_sender.available_device_names_calls == 1
    assert direct_sender.close_calls == 1


def test_macos_virtual_camera_direct_sender_uses_status_all_devices_prefix_fallback() -> None:
    direct_sender = FakeDirectSender(fail_names={"AKVC Demo"})
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        all_devices=["FaceTime高清相机", "AK Virtual Camera"],
        device_prefix="AK Virtual Camera",
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Demo")

    assert cam.started is True
    assert cam.backend_name == "direct_sender"
    assert cam.using_direct_sender is True
    assert cam.direct_sender_state == "active"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error is None
    assert direct_sender.open_calls == ["AKVC Demo", "AK Virtual Camera"]


def test_macos_virtual_camera_falls_back_to_shared_memory_when_direct_sender_unavailable() -> None:
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
    )

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        direct_sender_factory=lambda **kwargs: None,
        installer=installer,
    )

    cam.start()

    assert sink.open_calls == 1
    assert installer.sync_calls == ["/akvc-frames-v1"]
    assert cam.backend_name == "shared_memory"
    assert cam.using_direct_sender is False
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "fallback_shared_memory"
    assert cam.direct_sender_target_name is None
    assert cam.direct_sender_last_error == "macOS direct sender library not available"


def test_macos_virtual_camera_falls_back_to_shared_memory_when_direct_sender_open_fails() -> None:
    sink = FakeSink()
    direct_sender = FakeDirectSender(fail_open=True)
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
    )

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start()

    assert direct_sender.open_calls == ["AK Virtual Camera"]
    assert direct_sender.close_calls == 1
    assert sink.open_calls == 1
    assert installer.sync_calls == ["/akvc-frames-v1"]
    assert cam.backend_name == "shared_memory"
    assert cam.using_direct_sender is False
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "fallback_shared_memory"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error == "direct sender open failed"


def test_macos_virtual_camera_direct_sender_failure_still_raises_install_error_for_shared_memory_fallback() -> None:
    direct_sender = FakeDirectSender(fail_open=True)
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_FAILED,
        devices=[],
        enabled=False,
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    try:
        cam.start()
    except RuntimeError as exc:
        assert "不可用" in str(exc)
    else:
        raise AssertionError("expected install failure after direct sender fallback")

    assert direct_sender.open_calls == ["AK Virtual Camera"]
    assert cam.started is False
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error == (
        "direct sender open failed "
        "(current process snapshot reported no system video devices visible)"
    )


def test_macos_virtual_camera_direct_sender_creation_failure_falls_back_to_shared_memory() -> None:
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
    )

    def fail_factory(**kwargs):
        del kwargs
        raise RuntimeError("direct sender create failed")

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        direct_sender_factory=fail_factory,
        installer=installer,
    )

    cam.start()

    assert cam.started is True
    assert cam.backend_name == "shared_memory"
    assert cam.using_direct_sender is False
    assert cam.direct_sender_attempted is True
    assert cam.direct_sender_state == "fallback_shared_memory"
    assert cam.direct_sender_target_name is None
    assert cam.direct_sender_last_error == "direct sender create failed"
    assert sink.open_calls == 1
    assert installer.sync_calls == ["/akvc-frames-v1"]


def test_macos_virtual_camera_direct_sender_reports_attempted_fallback_names_on_total_failure() -> None:
    sink = FakeSink()
    direct_sender = FakeDirectSender(fail_open=True)
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
    )

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Demo")

    assert cam.started is True
    assert cam.backend_name == "shared_memory"
    assert cam.direct_sender_target_name == "AK Virtual Camera"
    assert cam.direct_sender_last_error == (
        "direct sender open failed (tried: AKVC Demo, AK Virtual Camera)"
    )
    assert direct_sender.open_calls == ["AKVC Demo", "AK Virtual Camera"]


def test_macos_virtual_camera_direct_sender_upconverts_bgr_ndarray_to_bgra_fast_path() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=6,
        height=4,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start()
    cam.push_frame(np.zeros((4, 6, 3), dtype=np.uint8))

    assert len(direct_sender.published) == 1
    assert direct_sender.published[0].fourcc == FourCC.BGRA32
    assert direct_sender.published[0].data[3] == 255


def test_macos_virtual_camera_direct_sender_preserves_bgra_ndarray_fast_path() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=6,
        height=4,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start()
    frame = np.zeros((4, 6, 4), dtype=np.uint8)
    frame[0, 0] = [11, 22, 33, 255]
    cam.push_frame(frame)

    assert len(direct_sender.published) == 1
    assert direct_sender.published[0].fourcc == FourCC.BGRA32
    assert list(direct_sender.published[0].data[:4]) == [11, 22, 33, 255]
    assert cam.last_frame_fourcc == FourCC.BGRA32
    assert cam.last_frame_format_name == "BGRA32"


def test_macos_virtual_camera_start_persists_requested_camera_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(tmp_path / "device-name.txt"))
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["Demo Camera"],
    )

    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=FakePipeline(),
        installer=installer,
    )
    cam.start(name="Demo Camera")

    assert (tmp_path / "device-name.txt").read_text(encoding="utf-8") == "Demo Camera\n"
    assert sink.open_calls == 1


def test_macos_virtual_camera_direct_sender_start_does_not_write_camera_name_override(
    monkeypatch,
    tmp_path,
) -> None:
    override_path = tmp_path / "device-name.txt"
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(override_path))
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )

    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start(name="AKVC Direct")

    assert cam.started is True
    assert cam.using_direct_sender is True
    assert direct_sender.open_calls == ["AKVC Direct"]
    assert override_path.exists() is False


def test_macos_virtual_camera_send_auto_starts_direct_sender_with_configured_camera_name() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AKVC Auto"],
    )
    cam = MacVirtualCamera(
        width=6,
        height=4,
        camera_name="AKVC Auto",
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.send(np.zeros((4, 6, 3), dtype=np.uint8))

    assert cam.started is True
    assert cam.using_direct_sender is True
    assert direct_sender.open_calls == ["AKVC Auto"]
    assert len(direct_sender.published) == 1


def test_macos_virtual_camera_send_aliases_push_frame() -> None:
    sink = FakeSink()
    pipeline = FakePipeline()

    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )
    cam.start()
    cam.send(np.zeros((4, 6, 3), dtype=np.uint8))

    assert len(pipeline.frames) == 1
    assert len(sink.published) == 1


def test_macos_virtual_camera_push_frame_accepts_qimage_like_input() -> None:
    sink = FakeSink()
    pipeline = FakePipeline()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )
    image = FakeQImage(2, 1, bytes([1, 2, 3, 4, 5, 6]))

    cam.start()
    cam.push_frame(image)

    assert len(pipeline.frames) == 1
    frame = pipeline.frames[0]
    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 2
    assert frame.height == 1
    assert list(frame.data[:6]) == [1, 2, 3, 4, 5, 6]
    assert sink.published == [frame]


def test_macos_virtual_camera_send_accepts_qpixmap_like_input() -> None:
    sink = FakeSink()
    pipeline = FakePipeline()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )
    pixmap = FakeQPixmap(FakeQImage(1, 1, bytes([7, 8, 9])))

    cam.start()
    cam.send(pixmap)

    assert len(pipeline.frames) == 1
    frame = pipeline.frames[0]
    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 1
    assert frame.height == 1
    assert list(frame.data[:3]) == [7, 8, 9]
    assert sink.published == [frame]


def test_macos_virtual_camera_direct_sender_accepts_bgra_qimage_like_input() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=1,
        height=1,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )
    image = FakeQImage(1, 1, bytes([1, 2, 3, 255]), fmt=FakeQImage.Format.Format_BGRA8888)

    cam.start()
    cam.push_frame(image)

    assert len(direct_sender.published) == 1
    frame = direct_sender.published[0]
    assert frame.fourcc == FourCC.BGRA32
    assert frame.width == 1
    assert frame.height == 1
    assert bytes(frame.data[:4]) == bytes([1, 2, 3, 255])


def test_macos_virtual_camera_request_camera_access_uses_direct_sender_snapshot() -> None:
    direct_sender = FakeDirectSender(
        available_snapshot={
            "all_devices": [],
            "camera_access_status": "denied",
            "environment_device_enumeration_empty": True,
        }
    )
    cam = MacVirtualCamera(
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )

    snapshot = cam.request_camera_access()

    assert direct_sender.request_camera_access_calls == 1
    assert snapshot == {
        "all_devices": [],
        "camera_access_status": "denied",
        "environment_device_enumeration_empty": True,
    }


def test_macos_virtual_camera_direct_sender_send_pixmap_preserves_bgra_fast_path() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=2,
        height=1,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )
    pixmap = FakeQPixmap(
        FakeQImage(
            2,
            1,
            bytes([1, 2, 3, 255, 4, 5, 6, 255]),
            fmt=FakeQImage.Format.Format_BGRA8888,
        )
    )

    cam.start()
    cam.send_pixmap(pixmap)

    assert len(direct_sender.published) == 1
    frame = direct_sender.published[0]
    assert frame.fourcc == FourCC.BGRA32
    assert list(frame.data[:8]) == [1, 2, 3, 255, 4, 5, 6, 255]
    assert cam.last_frame_format_name == "BGRA32"


def test_macos_virtual_camera_direct_sender_send_pixmap_prefers_bgra_conversion_fast_path() -> None:
    class ConvertibleQImage(FakeQImage):
        class Format(FakeQImage.Format):
            Format_Invalid = 99

        def __init__(self, width: int, height: int, payload: bytes, *, converted) -> None:
            super().__init__(width, height, payload, fmt=self.Format.Format_Invalid)
            self._converted = converted
            self.convert_calls: list[int] = []

        def bytesPerLine(self) -> int:
            return self._width * 4

        def convertToFormat(self, fmt: int):
            self.convert_calls.append(fmt)
            return self._converted

    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    converted = FakeQImage(
        1,
        1,
        bytes([9, 8, 7, 255]),
        fmt=FakeQImage.Format.Format_BGRA8888,
    )
    source = ConvertibleQImage(
        1,
        1,
        bytes([0, 0, 0, 0]),
        converted=converted,
    )
    cam = MacVirtualCamera(
        width=1,
        height=1,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )

    cam.start()
    cam.send_pixmap(FakeQPixmap(source))

    assert source.convert_calls == [FakeQImage.Format.Format_BGRA8888]
    assert len(direct_sender.published) == 1
    frame = direct_sender.published[0]
    assert frame.fourcc == FourCC.BGRA32
    assert list(frame.data[:4]) == [9, 8, 7, 255]


def test_macos_virtual_camera_direct_sender_resize_falls_back_without_cv2(monkeypatch) -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=2,
        height=2,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )
    pixmap = FakeQPixmap(
        FakeQImage(
            1,
            1,
            bytes([10, 20, 30, 255]),
            fmt=FakeQImage.Format.Format_BGRA8888,
        )
    )
    original_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cv2" or name.startswith("cv2."):
            raise ModuleNotFoundError("blocked cv2 for resize fallback test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    cam.start()
    cam.send_pixmap(pixmap)

    assert len(direct_sender.published) == 1
    frame = direct_sender.published[0]
    assert frame.width == 2
    assert frame.height == 2
    assert frame.fourcc == FourCC.BGRA32
    assert list(frame.data[:16]) == [
        10, 20, 30, 255,
        10, 20, 30, 255,
        10, 20, 30, 255,
        10, 20, 30, 255,
    ]


def test_macos_virtual_camera_push_frame_accepts_grayscale_qimage_like_input() -> None:
    class GrayQImage(FakeQImage):
        def bytesPerLine(self) -> int:
            return self._width

        def format(self) -> int:
            return self.Format.Format_Grayscale8

    sink = FakeSink()
    pipeline = FakePipeline()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )
    image = GrayQImage(2, 1, bytes([5, 11]))

    cam.start()
    cam.push_frame(image)

    assert len(pipeline.frames) == 1
    frame = pipeline.frames[0]
    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 2
    assert frame.height == 1
    assert list(frame.data[:6]) == [5, 5, 5, 11, 11, 11]
    assert sink.published == [frame]


def test_macos_virtual_camera_send_widget_grabs_and_pushes_frame() -> None:
    sink = FakeSink()
    pipeline = FakePipeline()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )
    widget = FakeWidget(FakeQPixmap(FakeQImage(1, 1, bytes([9, 8, 7]))))

    cam.start()
    cam.send_widget(widget)

    assert len(pipeline.frames) == 1
    frame = pipeline.frames[0]
    assert frame.width == 1
    assert frame.height == 1
    assert list(frame.data[:3]) == [9, 8, 7]
    assert sink.published == [frame]


def test_macos_virtual_camera_direct_sender_send_widget_preserves_bgra_fast_path() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=1,
        height=1,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )
    widget = FakeWidget(
        FakeQPixmap(
            FakeQImage(
                1,
                1,
                bytes([9, 8, 7, 255]),
                fmt=FakeQImage.Format.Format_BGRA8888,
            )
        )
    )

    cam.start()
    cam.send_widget(widget)

    assert len(direct_sender.published) == 1
    frame = direct_sender.published[0]
    assert frame.fourcc == FourCC.BGRA32
    assert list(frame.data[:4]) == [9, 8, 7, 255]
    assert cam.last_frame_fourcc == FourCC.BGRA32


def test_macos_virtual_camera_send_screen_uses_grabwindow_arguments() -> None:
    sink = FakeSink()
    pipeline = FakePipeline()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=pipeline,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )
    screen = FakeScreen(FakeQPixmap(FakeQImage(1, 1, bytes([1, 3, 5]))))

    cam.start()
    cam.send_screen(screen, window=7, x=10, y=20, width=640, height=360)

    assert screen.calls == [(7, 10, 20, 640, 360)]
    assert len(pipeline.frames) == 1
    frame = pipeline.frames[0]
    assert list(frame.data[:3]) == [1, 3, 5]
    assert sink.published == [frame]


def test_macos_virtual_camera_direct_sender_send_screen_preserves_bgra_fast_path() -> None:
    direct_sender = FakeDirectSender()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
    )
    cam = MacVirtualCamera(
        width=1,
        height=1,
        direct_sender_factory=lambda **kwargs: direct_sender,
        installer=installer,
    )
    screen = FakeScreen(
        FakeQPixmap(
            FakeQImage(
                1,
                1,
                bytes([6, 5, 4, 255]),
                fmt=FakeQImage.Format.Format_BGRA8888,
            )
        )
    )

    cam.start()
    cam.send_screen(screen, window=11, x=12, y=13, width=320, height=240)

    assert screen.calls == [(11, 12, 13, 320, 240)]
    assert len(direct_sender.published) == 1
    frame = direct_sender.published[0]
    assert frame.fourcc == FourCC.BGRA32
    assert list(frame.data[:4]) == [6, 5, 4, 255]
    assert cam.last_frame_format_name == "BGRA32"


def test_macos_virtual_camera_install_state_and_device_queries_delegate() -> None:
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera", "AK Virtual Camera 4K"],
    )

    cam = MacVirtualCamera(installer=installer)

    assert cam.is_installed() is True
    assert cam.enumerate_devices() == ["AK Virtual Camera", "AK Virtual Camera 4K"]
    assert cam.install_extension() is True
    assert installer.state_calls == 1
    assert installer.device_calls == 1
    assert installer.install_calls == 1


def test_macos_virtual_camera_helper_exe_app_bundle_builds_default_installer(monkeypatch) -> None:
    observed = {}

    class FakeDefaultInstaller(FakeInstaller):
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            super().__init__(
                state=ExtensionInstallState.INSTALLED,
                devices=["AK Virtual Camera"],
                enabled=True,
            )

    monkeypatch.setattr(
        "akvc.platforms.macos.virtual_camera.DefaultMacInstallerService",
        FakeDefaultInstaller,
    )

    cam = MacVirtualCamera(helper_exe="/Applications/Amaran Desktop.app")

    assert isinstance(cam._installer, FakeDefaultInstaller)
    assert observed == {"app_bundle": "/Applications/Amaran Desktop.app"}


def test_macos_virtual_camera_helper_exe_binary_builds_default_installer(monkeypatch) -> None:
    observed = {}

    class FakeDefaultInstaller(FakeInstaller):
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            super().__init__(
                state=ExtensionInstallState.INSTALLED,
                devices=["AK Virtual Camera"],
                enabled=True,
            )

    monkeypatch.setattr(
        "akvc.platforms.macos.virtual_camera.DefaultMacInstallerService",
        FakeDefaultInstaller,
    )

    cam = MacVirtualCamera(helper_exe="/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop")

    assert isinstance(cam._installer, FakeDefaultInstaller)
    assert observed == {
        "app_executable": "/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop"
    }


def test_macos_virtual_camera_explicit_host_bundle_builds_default_installer(monkeypatch) -> None:
    observed = {}

    class FakeDefaultInstaller(FakeInstaller):
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            super().__init__(
                state=ExtensionInstallState.INSTALLED,
                devices=["AK Virtual Camera"],
                enabled=True,
            )

    monkeypatch.setattr(
        "akvc.platforms.macos.virtual_camera.DefaultMacInstallerService",
        FakeDefaultInstaller,
    )

    cam = MacVirtualCamera(host_bundle="/Applications/Amaran Desktop.app")

    assert isinstance(cam._installer, FakeDefaultInstaller)
    assert observed == {"app_bundle": "/Applications/Amaran Desktop.app"}


def test_macos_virtual_camera_explicit_host_executable_builds_default_installer(monkeypatch) -> None:
    observed = {}

    class FakeDefaultInstaller(FakeInstaller):
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            super().__init__(
                state=ExtensionInstallState.INSTALLED,
                devices=["AK Virtual Camera"],
                enabled=True,
            )

    monkeypatch.setattr(
        "akvc.platforms.macos.virtual_camera.DefaultMacInstallerService",
        FakeDefaultInstaller,
    )

    cam = MacVirtualCamera(
        host_executable="/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop"
    )

    assert isinstance(cam._installer, FakeDefaultInstaller)
    assert observed == {
        "app_executable": "/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop"
    }


def test_macos_virtual_camera_explicit_installer_wins_over_helper_exe(monkeypatch) -> None:
    calls = []

    class FakeDefaultInstaller(FakeInstaller):
        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)
            super().__init__(
                state=ExtensionInstallState.INSTALLED,
                devices=["AK Virtual Camera"],
                enabled=True,
            )

    monkeypatch.setattr(
        "akvc.platforms.macos.virtual_camera.DefaultMacInstallerService",
        FakeDefaultInstaller,
    )
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
    )

    cam = MacVirtualCamera(
        helper_exe="/Applications/Amaran Desktop.app",
        installer=installer,
    )

    assert cam._installer is installer
    assert calls == []


def test_macos_virtual_camera_explicit_host_bundle_wins_over_helper_exe(monkeypatch) -> None:
    observed = {}

    class FakeDefaultInstaller(FakeInstaller):
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            super().__init__(
                state=ExtensionInstallState.INSTALLED,
                devices=["AK Virtual Camera"],
                enabled=True,
            )

    monkeypatch.setattr(
        "akvc.platforms.macos.virtual_camera.DefaultMacInstallerService",
        FakeDefaultInstaller,
    )

    cam = MacVirtualCamera(
        helper_exe="/tmp/legacy-helper",
        host_bundle="/Applications/Amaran Desktop.app",
    )

    assert isinstance(cam._installer, FakeDefaultInstaller)
    assert observed == {"app_bundle": "/Applications/Amaran Desktop.app"}


def test_macos_virtual_camera_uninstall_stops_stream_and_delegates() -> None:
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
    )
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=installer,
    )

    cam.start()
    assert cam.uninstall_extension() is True

    assert sink.open_calls == 1
    assert sink.close_calls == 1
    assert installer.uninstall_calls == 1
    assert cam.started is False


def test_macos_virtual_camera_creates_latest_frame_provider_and_streamer() -> None:
    cam = MacVirtualCamera(
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        )
    )

    provider = cam.create_latest_frame_provider(repeat_last=False)
    bridge = cam.create_pyside6_bridge()
    streamer = cam.create_pyside6_streamer(timer_factory=lambda: object())

    assert provider.__class__.__name__ == "LatestFrameProvider"
    assert getattr(provider, "_repeat_last") is False
    assert bridge.__class__.__name__ == "PySide6VirtualCameraBridge"
    assert bridge.camera is cam
    assert streamer.__class__.__name__ == "PySide6VirtualCameraStreamer"
    assert streamer.camera is cam


def test_macos_virtual_camera_status_delegates_to_installer() -> None:
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
        devices=["AK Virtual Camera"],
    )

    cam = MacVirtualCamera(installer=installer)
    status = cam.status()

    assert status.state is ExtensionInstallState.INSTALL_PENDING_APPROVAL
    assert status.devices == ["AK Virtual Camera"]
    assert status.enabled is False


def test_macos_virtual_camera_surfaces_installation_snapshot_and_readiness() -> None:
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        ipc_probe_present=True,
        ipc_ready=True,
    )

    cam = MacVirtualCamera(installer=installer)
    snapshot = cam.inspect_installation()
    readiness = cam.readiness()

    assert snapshot.status.state is ExtensionInstallState.INSTALLED
    assert snapshot.devices == ["AK Virtual Camera"]
    assert snapshot.readiness.phase == "installed_visible"
    assert snapshot.readiness.ready is True
    assert snapshot.readiness.blocker_code == "ready"
    assert readiness.phase == "installed_visible"
    assert readiness.ready is True


def test_macos_virtual_camera_surfaces_ipc_descriptor_and_stream_capabilities() -> None:
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        ipc_probe_present=True,
        ipc_ready=True,
    )

    cam = MacVirtualCamera(installer=installer)
    descriptor = cam.ipc_descriptor()
    capabilities = cam.stream_capabilities()

    assert isinstance(descriptor, MacIPCDescriptor)
    assert descriptor.transport == "shared_memory_ringbuffer"
    assert descriptor.framebus.shared_memory_name == "/akvc-frames-v1"
    assert descriptor.ready is True
    assert isinstance(capabilities, MacStreamCapabilities)
    assert capabilities.supported_formats == (
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    )
    assert capabilities.supported_frame_rates == (30, 60)


def test_macos_virtual_camera_start_uses_ipc_descriptor_shared_memory_name(tmp_path, monkeypatch) -> None:
    observed: list[str] = []
    sink = FakeSink()
    override_path = tmp_path / "akvc-macos-shm-name.txt"
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(override_path))

    def sink_factory(*, shm_name: str | None = None):
        observed.append(str(shm_name))
        return sink

    class DescriptorInstaller(FakeInstaller):
        def status(self) -> ExtensionStatus:
            status = super().status()
            return ExtensionStatus(
                state=status.state,
                devices=status.devices,
                enabled=status.enabled,
                approval_required=status.approval_required,
                ipc_probe_present=True,
                ipc_ready=True,
                shared_memory_name="/akvc-custom",
            )

    cam = MacVirtualCamera(
        sink_factory=sink_factory,
        installer=DescriptorInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
            enabled=True,
        ),
    )

    cam.start()

    assert observed == ["/akvc-custom"]
    assert sink.open_calls == 1
    assert override_path.read_text(encoding="utf-8") == "/akvc-custom\n"


def test_macos_virtual_camera_start_invokes_supported_ipc_sync_command() -> None:
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
    )

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        installer=installer,
    )

    cam.start()

    assert installer.sync_calls == ["/akvc-frames-v1"]
    assert sink.open_calls == 1


def test_macos_virtual_camera_start_uses_native_synced_shared_memory_name(
    tmp_path,
    monkeypatch,
) -> None:
    observed: list[str] = []
    override_path = tmp_path / "akvc-macos-shm-name.txt"
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(override_path))

    def sink_factory(*, shm_name: str | None = None):
        observed.append(str(shm_name))
        return FakeSink(shared_memory_name=shm_name)

    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
        sync_result_shared_memory_name="/akvc-synced",
    )

    cam = MacVirtualCamera(
        sink_factory=sink_factory,
        installer=installer,
    )

    cam.start()

    assert installer.sync_calls == ["/akvc-frames-v1"]
    assert observed == ["/akvc-synced"]
    assert override_path.read_text(encoding="utf-8") == "/akvc-synced\n"


def test_macos_virtual_camera_start_fails_when_supported_ipc_sync_command_fails() -> None:
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=False,
        sync_last_error="native sync tool failed",
    )

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        installer=installer,
    )

    try:
        cam.start()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("start should surface supported sync-ipc command failures")

    assert "IPC 配置同步失败" in message
    assert "native sync tool failed" in message
    assert installer.sync_calls == ["/akvc-frames-v1"]
    assert sink.open_calls == 0


def test_macos_virtual_camera_start_allows_sync_to_recover_ipc_readiness() -> None:
    sink = FakeSink()
    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        ipc_probe_present=True,
        ipc_ready=False,
        ipc_environment_blocked=True,
        ipc_last_error="probe status=open_failed; direct_open_errno=13",
        ipc_direct_open_errno=13,
        sync_supported=True,
        sync_success=True,
        sync_promotes_ipc_ready=True,
    )

    cam = MacVirtualCamera(
        sink_factory=lambda **kwargs: sink,
        installer=installer,
    )

    cam.start()

    assert installer.sync_calls == ["/akvc-frames-v1"]
    assert installer.ipc_ready is True
    assert installer.ipc_environment_blocked is False
    assert sink.open_calls == 1


def test_macos_virtual_camera_sync_ipc_configuration_rebinds_started_sink_when_name_changes() -> None:
    created_sinks: list[FakeSink] = []

    def sink_factory(*, shm_name: str | None = None):
        sink = FakeSink(shared_memory_name=shm_name)
        created_sinks.append(sink)
        return sink

    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
    )
    cam = MacVirtualCamera(
        sink_factory=sink_factory,
        installer=installer,
    )

    cam.start()
    sync_result = cam.sync_ipc_configuration_result("/akvc-custom")

    assert sync_result.supported is True
    assert sync_result.success is True
    assert sync_result.shared_memory_name == "/akvc-custom"
    assert installer.sync_calls == ["/akvc-frames-v1", "/akvc-custom"]
    assert len(created_sinks) == 2
    assert created_sinks[0].shared_memory_name == "/akvc-frames-v1"
    assert created_sinks[0].open_calls == 1
    assert created_sinks[0].close_calls == 1
    assert created_sinks[1].shared_memory_name == "/akvc-custom"
    assert created_sinks[1].open_calls == 1
    assert created_sinks[1].close_calls == 0
    assert cam.consumer_count == created_sinks[1].consumer_count


def test_macos_virtual_camera_sync_ipc_configuration_persists_native_synced_name(
    tmp_path,
    monkeypatch,
) -> None:
    override_path = tmp_path / "akvc-macos-shm-name.txt"
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(override_path))

    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
        sync_result_shared_memory_name="/akvc-canonical",
    )
    cam = MacVirtualCamera(installer=installer)

    sync_result = cam.sync_ipc_configuration_result("/akvc-requested")

    assert sync_result.supported is True
    assert sync_result.success is True
    assert sync_result.shared_memory_name == "/akvc-canonical"
    assert installer.sync_calls == ["/akvc-requested"]
    assert override_path.read_text(encoding="utf-8") == "/akvc-canonical\n"


def test_macos_virtual_camera_sync_ipc_configuration_tolerates_override_write_errors(
    monkeypatch,
    tmp_path,
) -> None:
    override_path = tmp_path / "akvc-macos-shm-name.txt"
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(override_path))

    original_write_text = Path.write_text

    def fake_write_text(self: Path, data: str, encoding: str = "utf-8", **kwargs) -> int:
        del data, encoding, kwargs
        if self == override_path:
            raise PermissionError("blocked")
        return original_write_text(self, "", encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=True,
        sync_success=True,
        sync_result_shared_memory_name="/akvc-canonical",
    )
    cam = MacVirtualCamera(installer=installer)

    sync_result = cam.sync_ipc_configuration_result("/akvc-requested")

    assert sync_result.supported is True
    assert sync_result.success is True
    assert sync_result.shared_memory_name == "/akvc-canonical"
    assert installer.sync_calls == ["/akvc-requested"]


def test_macos_virtual_camera_sync_ipc_configuration_does_not_rebind_when_unsupported() -> None:
    created_sinks: list[FakeSink] = []

    def sink_factory(*, shm_name: str | None = None):
        sink = FakeSink(shared_memory_name=shm_name)
        created_sinks.append(sink)
        return sink

    installer = FakeInstaller(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        sync_supported=False,
        sync_success=False,
    )
    cam = MacVirtualCamera(
        sink_factory=sink_factory,
        installer=installer,
    )

    cam.start()
    sync_result = cam.sync_ipc_configuration_result("/akvc-custom")

    assert sync_result.supported is False
    assert sync_result.success is False
    assert sync_result.shared_memory_name == "/akvc-custom"
    assert installer.sync_calls == ["/akvc-frames-v1", "/akvc-custom"]
    assert len(created_sinks) == 1
    assert created_sinks[0].shared_memory_name == "/akvc-frames-v1"
    assert created_sinks[0].open_calls == 1
    assert created_sinks[0].close_calls == 0


def test_macos_virtual_camera_push_before_start_auto_starts() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        pipeline=FakePipeline(),
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        )
    )

    cam.push_frame(np.zeros((2, 2, 3), dtype=np.uint8))

    assert cam.started is True
    assert cam.using_direct_sender is False
    assert sink.open_calls == 1
    assert len(sink.published) == 1


def test_macos_virtual_camera_supports_context_manager_lifecycle() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
        ),
    )

    with cam as active:
        assert active is cam
        assert cam.started is True

    assert cam.started is False
    assert sink.open_calls == 1
    assert sink.close_calls == 1


def test_macos_virtual_camera_start_requires_installed_extension() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=FakeInstaller(
            state=ExtensionInstallState.NOT_INSTALLED,
            devices=[],
        ),
    )

    try:
        cam.start()
    except RuntimeError as exc:
        assert "install_extension" in str(exc)
        assert "未安装" in str(exc)
    else:
        raise AssertionError("start should require installed macOS extension")

    assert sink.open_calls == 0
    assert cam.started is False


def test_macos_virtual_camera_start_requires_approval_when_extension_pending() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            devices=[],
        ),
    )

    try:
        cam.start()
    except RuntimeError as exc:
        assert "批准" in str(exc)
        assert "系统设置" in str(exc)
    else:
        raise AssertionError("start should require approval when extension is pending")

    assert sink.open_calls == 0
    assert cam.started is False


def test_macos_virtual_camera_start_requires_visible_device_after_install() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=[],
        ),
    )

    try:
        cam.start()
    except RuntimeError as exc:
        assert "还没有出现虚拟摄像头" in str(exc)
    else:
        raise AssertionError("start should require a visible system camera device")


def test_macos_virtual_camera_start_requires_ready_ipc_probe() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ipc_direct_open_errno=13,
        ),
    )

    try:
        cam.start()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("start should require a ready macOS IPC probe")

    assert "FrameBus" in message or "IPC" in message
    assert "direct_open_errno=13" in message
    assert sink.open_calls == 0

    assert sink.open_calls == 0
    assert cam.started is False


def test_macos_virtual_camera_start_requires_ready_producer_side_ipc_probe() -> None:
    sink = FakeSink()
    cam = MacVirtualCamera(
        sink_factory=lambda: sink,
        installer=FakeInstaller(
            state=ExtensionInstallState.INSTALLED,
            devices=["AK Virtual Camera"],
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
            ipc_direct_open_errno=1,
        ),
    )

    try:
        cam.start()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("start should require a ready macOS IPC probe")

    assert "FrameBus" in message or "IPC" in message
    assert "producer_open_failed" in message
    assert "direct_open_errno=1" in message
    assert sink.open_calls == 0
    assert cam.started is False
