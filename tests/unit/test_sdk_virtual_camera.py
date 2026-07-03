# SPDX-License-Identifier: Apache-2.0
"""Native virtual camera session smoke tests."""

from __future__ import annotations

import numpy as np
import pytest
from types import SimpleNamespace

from akvc.sdk.virtual_camera import VirtualCamera

_core_native = pytest.importorskip("akvc._core_native")
NativeVirtualCameraSession = _core_native.NativeVirtualCameraSession


def test_native_virtual_camera_session_defaults_are_idle() -> None:
    session = NativeVirtualCameraSession(1280, 720, 30.0, "")

    assert session.started is False
    assert session.consumer_count == 0

    session.close()


def test_native_virtual_camera_session_exposes_expected_methods() -> None:
    for name in ("start", "push_frame", "stop", "close"):
        assert hasattr(NativeVirtualCameraSession, name)
class FakeSink:
    def __init__(self) -> None:
        self.open_calls = 0
        self.close_calls = 0
        self.published = []
        self.consumer_count = 3

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


class FakeQImage:
    pass


class FakeQPixmap:
    pass


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


def test_start_opens_sink_and_registers_once(monkeypatch) -> None:
    helper = FakeHelper()
    sink = FakeSink()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "win32", raising=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr("akvc.sdk.virtual_camera._create_sink", lambda: sink)

    vc = VirtualCamera()
    vc.start(name="Demo Camera")
    vc.stop()
    vc.start(name="Demo Camera")

    assert helper.start_calls == 2
    assert helper.ping_calls == 2
    assert helper.register_calls == ["Demo Camera"]
    assert sink.open_calls == 2
    assert sink.close_calls == 1
    assert vc.started is True
    assert vc.consumer_count == 3
    assert vc.backend_name == "shared_memory"
    assert vc.using_direct_sender is False
    assert vc.helper_hot_path_used is True
    assert vc.shared_memory_fallback_used is True
    assert vc.direct_sender_attempted is False
    assert vc.direct_sender_state is None
    assert vc.direct_sender_target_name is None
    assert vc.direct_sender_library_path is None
    assert vc.direct_sender_last_error is None


def test_push_frame_uses_pipeline_and_sink(monkeypatch) -> None:
    helper = FakeHelper()
    sink = FakeSink()
    pipeline = FakePipeline()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "win32", raising=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr("akvc.sdk.virtual_camera._create_sink", lambda: sink)

    vc = VirtualCamera(pipeline=pipeline)
    vc.start()
    bgr = np.zeros((12, 16, 3), dtype=np.uint8)
    vc.push_frame(bgr)

    assert len(pipeline.frames) == 1
    assert len(sink.published) == 1
    assert sink.published[0].width == 16
    assert sink.published[0].height == 12


def test_push_frame_before_start_raises(monkeypatch) -> None:
    helper = FakeHelper()
    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "win32", raising=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)

    vc = VirtualCamera()
    try:
        vc.push_frame(np.zeros((4, 4, 3), dtype=np.uint8))
    except RuntimeError as exc:
        assert "not started" in str(exc)
    else:
        raise AssertionError("push_frame should require start()")


def test_helper_start_failure_raises_actionable_message(monkeypatch) -> None:
    helper = FakeHelper(
        start_result=False,
        last_error_message=(
            "AKVC helper failed to create global frame bus objects "
            "(Global\\akvc-frames-v1 via CreateFileMappingW, Win32 5: access denied). "
            "This host environment likely needs elevated privileges on Windows."
        ),
    )
    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "win32", raising=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)

    vc = VirtualCamera()
    try:
        vc.start()
    except RuntimeError as exc:
        assert "Global\\akvc-frames-v1" in str(exc)
        assert "elevated privileges" in str(exc)
    else:
        raise AssertionError("start should fail when helper does not start")


def test_close_stops_helper_and_is_idempotent(monkeypatch) -> None:
    helper = FakeHelper()
    sink = FakeSink()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "win32", raising=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr("akvc.sdk.virtual_camera._create_sink", lambda: sink)

    vc = VirtualCamera()
    vc.start()
    vc.close()
    vc.close()

    assert sink.close_calls == 1
    assert helper.stop_calls == 2
    assert vc.started is False


def test_start_on_darwin_opens_sink_without_windows_helper(monkeypatch) -> None:
    sink = FakeSink()
    helper_factory_calls = 0

    def fake_helper_factory(helper_exe=None):
        nonlocal helper_factory_calls
        helper_factory_calls += 1
        return FakeHelper()

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.started = False
            self.consumer_count = 0
            self.start_calls = []
            self.backend_name = None
            self.using_direct_sender = False
            self.direct_sender_attempted = False
            self.direct_sender_state = "idle"
            self.direct_sender_target_name = None
            self.direct_sender_library_path = None
            self.direct_sender_last_error = None
            self.last_frame_fourcc = None
            self.last_frame_format_name = None

        def start(self, name="AK Virtual Camera") -> None:
            self.start_calls.append(name)
            self.started = True
            self.consumer_count = sink.consumer_count
            self.backend_name = "direct_sender"
            self.using_direct_sender = True
            self.direct_sender_attempted = True
            self.direct_sender_state = "active"
            self.direct_sender_target_name = name
            sink.open()

        def push_frame(self, frame) -> None:
            sink.publish(frame)
            self.last_frame_fourcc = getattr(frame, "fourcc", None)
            self.last_frame_format_name = "RGB24" if self.last_frame_fourcc is not None else None

        def stop(self) -> None:
            if self.started:
                sink.close()
                self.started = False

        def close(self) -> None:
            self.stop()

        def enumerate_devices(self) -> list[str]:
            return ["AK Virtual Camera"]

        def status(self):
            return {"state": "installed"}

        def readiness(self):
            return SimpleNamespace(phase="installed_visible", ready=True, blocker_code="ready")

        def inspect_installation(self):
            return SimpleNamespace(
                status={"state": "installed"},
                devices=["AK Virtual Camera"],
                readiness=self.readiness(),
            )

        def ipc_descriptor(self):
            return SimpleNamespace(
                transport="shared_memory_ringbuffer",
                framebus=SimpleNamespace(shared_memory_name="/akvc-frames-v1"),
                ready=True,
            )

        def stream_capabilities(self):
            return SimpleNamespace(
                supported_formats=("1280x720@30/60 NV12", "1920x1080@30/60 NV12"),
                supported_frame_rates=(30, 60),
            )

        def is_installed(self) -> bool:
            return True

        def install_extension(self) -> bool:
            return True

        def uninstall_extension_result(self):
            return SimpleNamespace(
                success=True,
                phase="uninstalled",
                state=SimpleNamespace(value="not_installed"),
            )

        def uninstall_extension(self) -> bool:
            return True

        def sync_ipc_configuration_result(self, shared_memory_name=None):
            return SimpleNamespace(
                supported=True,
                success=True,
                phase="sync_command_succeeded",
                shared_memory_name=shared_memory_name or "/akvc-frames-v1",
            )

        def sync_ipc_configuration(self, shared_memory_name=None) -> bool:
            del shared_memory_name
            return True

    fake_mac_backend = FakeMacBackend()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", fake_helper_factory)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: fake_mac_backend),
    )

    vc = VirtualCamera()
    vc.start(name="Demo Camera")

    assert helper_factory_calls == 0
    assert sink.open_calls == 1
    assert vc.started is True
    assert vc.consumer_count == sink.consumer_count
    assert vc.backend_name == "direct_sender"
    assert vc.using_direct_sender is True
    assert vc.helper_hot_path_used is False
    assert vc.shared_memory_fallback_used is False
    assert vc.direct_sender_attempted is True
    assert vc.direct_sender_state == "active"
    assert vc.direct_sender_target_name == "Demo Camera"
    assert vc.direct_sender_library_path is None
    assert vc.direct_sender_last_error is None
    assert vc.last_frame_fourcc is None
    assert vc.last_frame_format_name is None
    assert vc.status() == {"state": "installed"}
    assert vc.readiness().phase == "installed_visible"
    assert vc.inspect_installation().devices == ["AK Virtual Camera"]
    assert vc.ipc_descriptor().transport == "shared_memory_ringbuffer"
    assert vc.stream_capabilities().supported_frame_rates == (30, 60)
    assert vc.is_installed() is True
    assert vc.enumerate_devices() == ["AK Virtual Camera"]
    assert vc.install_extension() is True
    assert vc.uninstall_extension_result().phase == "uninstalled"
    assert vc.uninstall_extension() is True
    assert vc.sync_ipc_configuration() is True
    assert vc.sync_ipc_configuration_result().phase == "sync_command_succeeded"


def test_send_before_start_on_darwin_uses_backend_auto_start(monkeypatch) -> None:
    observed = {}

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            self.started = False
            self.consumer_count = 0
            self.sent = []
            self.backend_name = None
            self.using_direct_sender = False
            self.direct_sender_attempted = False
            self.direct_sender_state = "idle"
            self.direct_sender_target_name = None
            self.direct_sender_library_path = None
            self.direct_sender_last_error = None
            self.last_frame_fourcc = None
            self.last_frame_format_name = None

        def push_frame(self, frame) -> None:
            if not self.started:
                self.started = True
                self.consumer_count = 1
                self.backend_name = "direct_sender"
                self.using_direct_sender = True
                self.direct_sender_attempted = True
                self.direct_sender_state = "active"
                self.direct_sender_target_name = observed["camera_name"]
            self.sent.append(frame)
            self.last_frame_fourcc = getattr(frame, "fourcc", None)
            if self.last_frame_fourcc is not None:
                self.last_frame_format_name = "RGB24"

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera(camera_name="AKVC Auto")
    vc.send(np.zeros((4, 6, 3), dtype=np.uint8))

    assert observed["camera_name"] == "AKVC Auto"
    assert vc.backend_name == "direct_sender"
    assert vc.started is True
    assert vc.consumer_count == 1
    assert vc.using_direct_sender is True
    assert vc.direct_sender_target_name == "AKVC Auto"
    assert vc.helper_hot_path_used is False


def test_virtual_camera_forwards_helper_exe_to_macos_backend(monkeypatch) -> None:
    observed = {}

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            self.started = False
            self.consumer_count = 0

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera(
        helper_exe="/Applications/Amaran Desktop.app",
        direct_sender_library="/tmp/libakvc-macos-direct-sender.dylib",
    )

    assert vc._mac_backend is not None
    assert observed["helper_exe"] == "/Applications/Amaran Desktop.app"
    assert observed["direct_sender_library"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert observed["width"] == 1280
    assert observed["height"] == 720
    assert observed["fps"] == 30.0


def test_virtual_camera_forwards_container_app_arguments_to_macos_backend(monkeypatch) -> None:
    observed = {}

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            self.started = False
            self.consumer_count = 0

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera(
        app_bundle="/Applications/Amaran Desktop.app",
        app_executable="/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop",
    )

    assert vc._mac_backend is not None
    assert observed["app_bundle"] == "/Applications/Amaran Desktop.app"
    assert observed["app_executable"] == (
        "/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop"
    )


def test_virtual_camera_forwards_direct_only_to_macos_backend(monkeypatch) -> None:
    observed = {}

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            self.started = False
            self.consumer_count = 0

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera(direct_only=True)

    assert vc._mac_backend is not None
    assert observed["direct_only"] is True


def test_direct_sender_device_snapshot_on_darwin_delegates_to_macos_backend(monkeypatch) -> None:
    expected = {
        "all_devices": ["AKVC Demo"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0

        def direct_sender_device_snapshot(self):
            return dict(expected)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera()

    assert vc.direct_sender_device_snapshot() == expected


def test_request_camera_access_on_darwin_delegates_to_macos_backend(monkeypatch) -> None:
    expected = {
        "all_devices": [],
        "camera_access_status": "denied",
        "environment_device_enumeration_empty": True,
    }

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0

        def request_camera_access(self):
            return dict(expected)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera()

    assert vc.request_camera_access() == expected


def test_direct_sender_readiness_on_darwin_delegates_to_macos_backend(monkeypatch) -> None:
    expected = {
        "ready": False,
        "blocker_code": "camera_access_denied",
        "message": "当前进程没有摄像头权限，direct sender 暂不可用。",
        "camera_name": "AK Virtual Camera",
        "camera_access_status": "denied",
        "target_visible": False,
        "visible_devices": [],
        "snapshot": {
            "all_devices": [],
            "camera_access_status": "denied",
            "environment_device_enumeration_empty": True,
        },
    }

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0

        def direct_sender_readiness(self, name="AK Virtual Camera", *, request_camera_access=False):
            assert name == "AK Virtual Camera"
            assert request_camera_access is True
            return dict(expected)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera()

    assert vc.direct_sender_readiness(request_camera_access=True) == expected


def test_runtime_topology_on_darwin_delegates_to_macos_backend(monkeypatch) -> None:
    expected = {
        "runtime_topology_kind": "camera_extension_direct_sender",
        "runtime_data_plane": "cmio_sink_stream_direct",
        "runtime_control_plane": "host_activation_only",
        "runtime_host_in_frame_hot_path": False,
    }

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0

        def runtime_topology(self):
            return dict(expected)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera()

    assert vc.runtime_topology() == expected


def test_runtime_snapshot_on_darwin_delegates_to_macos_backend(monkeypatch) -> None:
    expected = {
        "started": True,
        "backend_name": "direct_sender",
        "runtime_topology": {"runtime_topology_kind": "camera_extension_direct_sender"},
    }

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0

        def runtime_snapshot(self):
            return dict(expected)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera()

    assert vc.runtime_snapshot() == expected


def test_virtual_camera_maps_legacy_host_paths_to_container_app_args(monkeypatch) -> None:
    observed = {}

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            observed.update(kwargs)
            self.started = False
            self.consumer_count = 0

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend(**kwargs)),
    )

    vc = VirtualCamera(
        host_bundle="/Applications/Amaran Desktop.app",
        direct_sender_library="/tmp/libakvc-macos-direct-sender.dylib",
    )

    assert vc._mac_backend is not None
    assert observed["app_bundle"] == "/Applications/Amaran Desktop.app"
    assert observed["app_executable"] is None
    assert observed["helper_exe"] is None
    assert observed["direct_sender_library"] == "/tmp/libakvc-macos-direct-sender.dylib"


def test_close_on_darwin_is_idempotent_without_helper(monkeypatch) -> None:
    sink = FakeSink()

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True
            sink.open()

        def stop(self) -> None:
            if self.started:
                sink.close()
                self.started = False

        def close(self) -> None:
            self.stop()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: FakeMacBackend()),
    )

    vc = VirtualCamera()
    vc.start()
    vc.close()
    vc.close()

    assert sink.close_calls == 1
    assert vc.started is False


def test_create_pyside6_bridge_wraps_virtual_camera_without_backend(monkeypatch) -> None:
    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "linux", raising=False)

    vc = VirtualCamera()
    bridge = vc.create_pyside6_bridge()

    assert bridge.__class__.__name__ == "PySide6VirtualCameraBridge"
    assert bridge.camera is vc


def test_push_frame_on_darwin_delegates_qimage_like_input_to_macos_backend(monkeypatch) -> None:
    image = FakeQImage()

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0
            self.pushed = []
            self.last_frame_fourcc = None
            self.last_frame_format_name = None

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def push_frame(self, frame) -> None:
            self.pushed.append(frame)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    backend = FakeMacBackend()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: backend),
    )

    vc = VirtualCamera()
    vc.start()
    vc.push_frame(image)

    assert backend.pushed == [image]
    assert vc.last_frame_fourcc is None
    assert vc.last_frame_format_name is None


def test_send_on_darwin_delegates_qpixmap_like_input_to_macos_backend(monkeypatch) -> None:
    pixmap = FakeQPixmap()

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0
            self.pushed = []

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def push_frame(self, frame) -> None:
            self.pushed.append(frame)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    backend = FakeMacBackend()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: backend),
    )

    vc = VirtualCamera()
    vc.start()
    vc.send(pixmap)

    assert backend.pushed == [pixmap]


def test_send_widget_and_send_screen_on_darwin_delegate_to_macos_backend(monkeypatch) -> None:
    pixmap = FakeQPixmap()
    widget = FakeWidget(pixmap)
    screen = FakeScreen(pixmap)

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0
            self.pushed = []

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def push_frame(self, frame) -> None:
            self.pushed.append(frame)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

    backend = FakeMacBackend()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: backend),
    )

    vc = VirtualCamera()
    vc.start()
    vc.send_widget(widget)
    vc.send_screen(screen, window=7, x=10, y=20, width=640, height=360)

    assert screen.calls == [(7, 10, 20, 640, 360)]
    assert backend.pushed == [pixmap, pixmap]


def test_create_pyside6_helpers_on_darwin_prefer_macos_backend(monkeypatch) -> None:
    bridge_calls = []
    provider_calls = []
    streamer_calls = []

    class FakeMacBackend:
        def __init__(self, **kwargs) -> None:
            self.started = False
            self.consumer_count = 0

        def start(self, name="AK Virtual Camera") -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            self.stop()

        def create_pyside6_bridge(self):
            bridge_calls.append(True)
            return {"bridge": True}

        def create_latest_frame_provider(self, *, repeat_last: bool = True):
            provider_calls.append(repeat_last)
            return {"provider": repeat_last}

        def create_pyside6_streamer(self, *, timer_factory=None):
            streamer_calls.append(timer_factory)
            return {"streamer": timer_factory}

    backend = FakeMacBackend()
    timer_factory = lambda: object()

    monkeypatch.setattr("akvc.sdk.virtual_camera.sys.platform", "darwin", raising=False)
    monkeypatch.setattr(
        "akvc.sdk.virtual_camera._load_macos_virtual_camera_class",
        lambda: (lambda **kwargs: backend),
    )

    vc = VirtualCamera()

    bridge = vc.create_pyside6_bridge()
    provider = vc.create_latest_frame_provider(repeat_last=False)
    streamer = vc.create_pyside6_streamer(timer_factory=timer_factory)

    assert bridge_calls == [True]
    assert provider_calls == [False]
    assert streamer_calls == [timer_factory]
    assert bridge == {"bridge": True}
    assert provider == {"provider": False}
    assert streamer == {"streamer": timer_factory}
