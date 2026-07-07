# SPDX-License-Identifier: Apache-2.0
"""Checks for the PySide6 virtual camera demo helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "pyside6_virtual_camera_demo.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pyside6_virtual_camera_demo", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class FakeQTimer:
    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.timeout = FakeSignal()
        self.started = []
        self.stop_calls = 0

    def start(self, interval_ms: int) -> None:
        self.started.append(interval_ms)

    def stop(self) -> None:
        self.stop_calls += 1


class FakeLabel:
    def __init__(self, text: str = "") -> None:
        self.text_value = text

    def setText(self, text: str) -> None:
        self.text_value = text

    def setStyleSheet(self, style: str) -> None:
        self.style = style


class FakeLayout:
    def __init__(self, widget) -> None:
        self.widget = widget
        self.children = []

    def addWidget(self, widget) -> None:
        self.children.append(widget)


class FakeWidget:
    def __init__(self) -> None:
        self.title = ""
        self.size = (0, 0)
        self.shown = False
        self.closed = False

    def setWindowTitle(self, title: str) -> None:
        self.title = title

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def show(self) -> None:
        self.shown = True

    def close(self) -> None:
        self.closed = True


class FakeQColor:
    @staticmethod
    def fromHsv(h, s, v):
        return {"h": h, "s": s, "v": v}


class FakeQImage:
    class Format:
        Format_RGB32 = 1

    def __init__(self, width: int, height: int, fmt: int) -> None:
        self.width = width
        self.height = height
        self.fmt = fmt
        self.fill_calls = []

    def fill(self, color) -> None:
        self.fill_calls.append(color)


class FakeQPixmap:
    def __init__(self, image) -> None:
        self.image = image

    @classmethod
    def fromImage(cls, image):
        return cls(image)


class FakeApp:
    def __init__(self) -> None:
        self.events = 0
        self.screen = object()

    def processEvents(self) -> None:
        self.events += 1

    def primaryScreen(self):
        return self.screen


class FakeQApplication:
    _instance = None

    def __init__(self, argv=None) -> None:
        del argv
        self._app = FakeApp()
        FakeQApplication._instance = self

    @classmethod
    def instance(cls):
        return cls._instance._app if cls._instance is not None else None

    def __call__(self, argv=None):
        del argv
        return self._app


class FakeQtModule:
    QApplication = FakeQApplication
    QWidget = FakeWidget
    QLabel = FakeLabel
    QVBoxLayout = FakeLayout
    QTimer = FakeQTimer
    QColor = FakeQColor
    QImage = FakeQImage
    QPixmap = FakeQPixmap


class FakeCamera:
    def __init__(self) -> None:
        self.start_calls = []
        self.close_calls = 0
        self.consumer_count = 1
        self.push_frame_calls = []
        self.send_image_calls = []
        self.send_pixmap_calls = []
        self.send_widget_calls = []
        self.send_screen_calls = []
        self.streamer_factory_calls = 0
        self.latest_provider_factory_calls = []
        self.backend_name = "direct_sender"
        self.using_direct_sender = True
        self.direct_sender_attempted = True
        self.direct_sender_state = "active"
        self.direct_sender_target_name = "AKVC Demo"
        self.direct_sender_library_path = "/tmp/libakvc-macos-direct-sender.dylib"
        self.direct_sender_last_error = None
        self.runtime_topology_payload = {
            "runtime_topology_kind": "camera_extension_direct_sender",
            "runtime_frame_path": "python_sdk -> cmio_sink_stream_direct -> camera_extension -> system_camera_device -> client_app",
            "runtime_host_role": "container_activation_command_bridge",
            "runtime_host_in_frame_hot_path": False,
            "runtime_dedicated_host_daemon_required": False,
            "runtime_container_app_configured": True,
            "runtime_data_plane": "cmio_sink_stream_direct",
            "runtime_control_plane": "host_activation_only",
        }
        self.runtime_snapshot_payload = {
            "started": True,
            "camera_name": "AKVC Demo",
            "backend_name": "direct_sender",
            "using_direct_sender": True,
            "direct_sender_attempted": True,
            "direct_sender_state": "active",
            "direct_sender_target_name": "AKVC Demo",
            "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
            "direct_sender_last_error": None,
            "consumer_count": 1,
            "runtime_topology": dict(self.runtime_topology_payload),
        }

    def start(self, name: str = "AK Virtual Camera") -> None:
        self.start_calls.append(name)

    def close(self) -> None:
        self.close_calls += 1

    def push_frame(self, frame) -> None:
        self.push_frame_calls.append(frame)

    def send_image(self, image) -> None:
        self.send_image_calls.append(image)

    def send_pixmap(self, pixmap) -> None:
        self.send_pixmap_calls.append(pixmap)

    def send_widget(self, widget) -> None:
        self.send_widget_calls.append(widget)

    def send_screen(
        self,
        screen,
        *,
        window: int = 0,
        x: int = 0,
        y: int = 0,
        width: int = -1,
        height: int = -1,
    ) -> None:
        self.send_screen_calls.append((screen, window, x, y, width, height))

    def create_pyside6_streamer(self):
        self.streamer_factory_calls += 1
        return FakeStreamer(self)

    def create_latest_frame_provider(self, *, repeat_last: bool = True):
        self.latest_provider_factory_calls.append(repeat_last)
        return FakeLatestFrameProvider(repeat_last=repeat_last)

    def runtime_topology(self):
        return dict(self.runtime_topology_payload)

    def runtime_snapshot(self):
        payload = dict(self.runtime_snapshot_payload)
        payload["runtime_topology"] = dict(self.runtime_topology_payload)
        payload["consumer_count"] = self.consumer_count
        return payload


class FakeStreamer:
    instances = []

    def __init__(self, camera) -> None:
        self.camera = camera
        self.calls = []
        self.stop_calls = 0
        FakeStreamer.instances.append(self)

    def start_provider_stream(self, provider, *, interval_ms: int = 33) -> None:
        self.calls.append(("provider", interval_ms, provider))

    def start_latest_frame_stream(self, provider, *, interval_ms: int = 33) -> None:
        self.calls.append(("latest-provider", interval_ms, provider))

    def start_video_file_stream(
        self,
        path: str,
        *,
        interval_ms: int = 33,
        loop: bool = True,
        cv2_module=None,
        provider_factory=None,
    ) -> None:
        self.calls.append(("video-file", interval_ms, path, loop, cv2_module, provider_factory))

    def start_widget_stream(self, widget, *, interval_ms: int = 33) -> None:
        self.calls.append(("widget", interval_ms, widget))

    def start_screen_stream(self, screen, *, interval_ms: int = 33, window: int = 0, x: int = 0, y: int = 0, width: int = -1, height: int = -1) -> None:
        self.calls.append(("screen", interval_ms, screen, window, x, y, width, height))

    def stop(self) -> None:
        self.stop_calls += 1


class FakeVideoProvider:
    instances = []

    def __init__(self, path: str, *, loop: bool = True) -> None:
        self.path = path
        self.loop = loop
        self.close_calls = 0
        FakeVideoProvider.instances.append(self)

    def __call__(self):
        return "video-frame"

    def close(self) -> None:
        self.close_calls += 1


class FakeLatestFrameProvider:
    instances = []

    def __init__(self, *, repeat_last: bool = True) -> None:
        self.repeat_last = repeat_last
        self.submit_calls = []
        self.close_calls = 0
        FakeLatestFrameProvider.instances.append(self)

    def submit(self, frame) -> None:
        self.submit_calls.append(frame)

    def __call__(self):
        return self.submit_calls[-1] if self.submit_calls else "latest-frame"

    def close(self) -> None:
        self.close_calls += 1


def test_pyside6_demo_tool_exists_and_declares_expected_modes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "--mode" in text
    assert "provider" in text
    assert "latest-provider" in text
    assert "numpy-direct" in text
    assert "image" in text
    assert "pixmap" in text
    assert "widget" in text
    assert "screen" in text
    assert "video-file" in text
    assert "--video-path" in text
    assert "--duration" in text
    assert "--fps" in text
    assert "create_pyside6_streamer" in text
    assert "create_latest_frame_provider" in text
    assert "send_image" in text
    assert "send_pixmap" in text
    assert "send_widget" in text
    assert "send_screen" in text
    assert "VirtualCamera" in text
    assert "runtime_snapshot" in text


def test_run_demo_numpy_direct_mode_uses_push_frame_without_qt() -> None:
    module = _load_module()
    camera = FakeCamera()
    expected_direct_only = module.sys.platform == "darwin"

    payload = module.run_demo(
        mode="numpy-direct",
        width=640,
        height=360,
        fps=20.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        qt_loader=lambda: (_ for _ in ()).throw(AssertionError("qt loader should not be used")),
        sleeper=lambda seconds: None,
    )

    assert payload["mode"] == "numpy-direct"
    assert payload["frame_source_kind"] == "numpy_direct"
    assert payload["python_entrypoint_kind"] == "push_frame"
    assert payload["sdk_streamer_factory_used"] is False
    assert payload["sdk_latest_provider_factory_used"] is False
    assert payload["sdk_direct_push_used"] is True
    assert payload["requested_direct_only"] is expected_direct_only
    assert payload["allow_shared_memory_fallback"] is (not expected_direct_only)
    assert payload["backend_name"] == "direct_sender"
    assert payload["using_direct_sender"] is True
    assert payload["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert payload["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert payload["runtime_control_plane"] == "host_activation_only"
    assert payload["runtime_snapshot"]["backend_name"] == "direct_sender"
    assert payload["runtime_snapshot"]["runtime_topology"]["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert len(camera.push_frame_calls) == 1
    frame = camera.push_frame_calls[0]
    assert frame.shape == (360, 640, 3)
    assert frame.dtype.name == "uint8"


def test_run_demo_provider_mode_starts_camera_and_streamer() -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    camera = FakeCamera()
    slept = []
    expected_direct_only = module.sys.platform == "darwin"

    payload = module.run_demo(
        mode="provider",
        width=1280,
        height=720,
        fps=25.0,
        duration=0.1,
        name="AKVC Demo",
        camera_factory=lambda **kwargs: camera,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: slept.append(seconds),
    )

    assert payload["mode"] == "provider"
    assert payload["frame_source_kind"] == "callable_provider"
    assert payload["python_entrypoint_kind"] == "create_pyside6_streamer.start_provider_stream"
    assert payload["sdk_streamer_factory_used"] is True
    assert payload["sdk_latest_provider_factory_used"] is False
    assert payload["sdk_direct_push_used"] is False
    assert payload["requested_direct_only"] is expected_direct_only
    assert payload["runtime_snapshot"]["direct_sender_target_name"] == "AKVC Demo"
    assert camera.start_calls == ["AKVC Demo"]
    assert camera.close_calls == 1
    assert camera.streamer_factory_calls == 1
    assert abs(sum(slept) - 0.1) < 1e-6
    assert len(FakeStreamer.instances) == 1
    call = FakeStreamer.instances[0].calls[0]
    assert call[0] == "provider"
    assert call[1] == 40
    assert FakeStreamer.instances[0].stop_calls == 1


def test_run_demo_screen_mode_uses_primary_screen() -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    camera = FakeCamera()

    payload = module.run_demo(
        mode="screen",
        width=640,
        height=360,
        fps=20.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
    )

    assert payload["mode"] == "screen"
    assert payload["frame_source_kind"] == "screen_grab"
    assert payload["python_entrypoint_kind"] == "send_screen"
    assert payload["sdk_streamer_factory_used"] is False
    assert payload["sdk_direct_push_used"] is True
    assert camera.streamer_factory_calls == 0
    assert len(camera.send_screen_calls) == 1
    call = camera.send_screen_calls[0]
    assert call[1:] == (0, 0, 0, 640, 360)


def test_run_demo_image_mode_uses_direct_qimage_push() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        mode="image",
        width=640,
        height=360,
        fps=20.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
    )

    assert payload["mode"] == "image"
    assert payload["frame_source_kind"] == "qimage_direct"
    assert payload["python_entrypoint_kind"] == "send_image"
    assert payload["sdk_streamer_factory_used"] is False
    assert payload["sdk_direct_push_used"] is True
    assert len(camera.send_image_calls) == 1
    assert camera.send_image_calls[0].__class__.__name__ == "FakeQImage"


def test_run_demo_pixmap_mode_uses_direct_qpixmap_push() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        mode="pixmap",
        width=640,
        height=360,
        fps=20.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
    )

    assert payload["mode"] == "pixmap"
    assert payload["frame_source_kind"] == "qpixmap_direct"
    assert payload["python_entrypoint_kind"] == "send_pixmap"
    assert payload["sdk_streamer_factory_used"] is False
    assert payload["sdk_direct_push_used"] is True
    assert len(camera.send_pixmap_calls) == 1
    assert camera.send_pixmap_calls[0].__class__.__name__ == "FakeQPixmap"


def test_run_demo_widget_mode_uses_widget_stream() -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    camera = FakeCamera()

    payload = module.run_demo(
        mode="widget",
        width=800,
        height=450,
        fps=30.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
    )

    assert payload["mode"] == "widget"
    assert payload["frame_source_kind"] == "widget_grab"
    assert payload["python_entrypoint_kind"] == "send_widget"
    assert payload["sdk_streamer_factory_used"] is False
    assert payload["sdk_direct_push_used"] is True
    assert camera.streamer_factory_calls == 0
    assert len(camera.send_widget_calls) == 1
    assert camera.send_widget_calls[0].__class__.__name__ == "FakeWidget"


def test_run_demo_video_file_mode_uses_video_provider() -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    FakeVideoProvider.instances.clear()
    camera = FakeCamera()

    payload = module.run_demo(
        mode="video-file",
        width=1280,
        height=720,
        fps=30.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
        video_provider_cls=FakeVideoProvider,
        video_path="demo.mp4",
    )

    assert payload["mode"] == "video-file"
    assert payload["frame_source_kind"] == "opencv_video_file"
    assert payload["python_entrypoint_kind"] == "create_pyside6_streamer.start_video_file_stream"
    assert payload["sdk_streamer_factory_used"] is True
    assert payload["sdk_latest_provider_factory_used"] is False
    assert payload["sdk_direct_push_used"] is False
    assert payload["video_path"] == "demo.mp4"
    call = FakeStreamer.instances[0].calls[0]
    assert call[0] == "video-file"
    assert call[1] == 33
    assert call[2] == "demo.mp4"
    provider_factory = call[5]
    provider = provider_factory("demo.mp4", loop=True)
    assert isinstance(provider, FakeVideoProvider)
    assert provider.path == "demo.mp4"


def test_run_demo_latest_provider_mode_uses_latest_frame_provider() -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    camera = FakeCamera()

    payload = module.run_demo(
        mode="latest-provider",
        width=1280,
        height=720,
        fps=30.0,
        duration=0.0,
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
    )

    assert payload["mode"] == "latest-provider"
    assert payload["frame_source_kind"] == "latest_frame_provider"
    assert payload["python_entrypoint_kind"] == "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream"
    assert payload["sdk_streamer_factory_used"] is True
    assert payload["sdk_latest_provider_factory_used"] is True
    assert payload["sdk_direct_push_used"] is False
    assert len(FakeLatestFrameProvider.instances) == 1
    provider = FakeLatestFrameProvider.instances[0]
    assert camera.latest_provider_factory_calls == [True]
    assert provider.repeat_last is True
    assert len(provider.submit_calls) == 1
    assert provider.close_calls == 1
    call = FakeStreamer.instances[0].calls[0]
    assert call[0] == "latest-provider"
    assert call[1] == 33
    assert call[2] is provider


def test_run_demo_on_darwin_requests_direct_only_by_default() -> None:
    module = _load_module()
    camera = FakeCamera()
    observed = {}
    original_platform = module.sys.platform
    module.sys.platform = "darwin"
    try:
        payload = module.run_demo(
            mode="numpy-direct",
            width=640,
            height=360,
            fps=20.0,
            duration=0.0,
            camera_factory=lambda **kwargs: observed.update(kwargs) or camera,
            qt_loader=lambda: (_ for _ in ()).throw(AssertionError("qt loader should not be used")),
            sleeper=lambda seconds: None,
        )
    finally:
        module.sys.platform = original_platform

    assert observed["direct_only"] is True
    assert payload["requested_direct_only"] is True
    assert payload["allow_shared_memory_fallback"] is False


def test_run_demo_on_darwin_can_allow_shared_memory_fallback() -> None:
    module = _load_module()
    camera = FakeCamera()
    observed = {}
    original_platform = module.sys.platform
    module.sys.platform = "darwin"
    try:
        payload = module.run_demo(
            mode="numpy-direct",
            width=640,
            height=360,
            fps=20.0,
            duration=0.0,
            allow_shared_memory_fallback=True,
            camera_factory=lambda **kwargs: observed.update(kwargs) or camera,
            qt_loader=lambda: (_ for _ in ()).throw(AssertionError("qt loader should not be used")),
            sleeper=lambda seconds: None,
        )
    finally:
        module.sys.platform = original_platform

    assert observed["direct_only"] is False
    assert payload["requested_direct_only"] is False
    assert payload["allow_shared_memory_fallback"] is True


def test_main_writes_demo_report_json(tmp_path) -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    camera = FakeCamera()
    output = tmp_path / "demo-report.json"
    expected_direct_only = module.sys.platform == "darwin"

    rc = module.main(
        [
            "--mode", "provider",
            "--width", "960",
            "--height", "540",
            "--fps", "24",
            "--duration", "0",
            "--name", "AKVC Demo",
            "--report-json", str(output),
        ],
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
    )

    assert rc == 0
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "provider"
    assert payload["width"] == 960
    assert payload["height"] == 540
    assert payload["fps"] == 24.0
    assert payload["duration"] == 0.0
    assert payload["camera_name"] == "AKVC Demo"
    assert payload["consumer_count"] == 1
    assert payload["frame_source_kind"] == "callable_provider"
    assert payload["python_entrypoint_kind"] == "create_pyside6_streamer.start_provider_stream"
    assert payload["sdk_streamer_factory_used"] is True
    assert payload["sdk_latest_provider_factory_used"] is False
    assert payload["sdk_direct_push_used"] is False
    assert payload["requested_direct_only"] is expected_direct_only
    assert payload["allow_shared_memory_fallback"] is (not expected_direct_only)
    assert payload["backend_name"] == "direct_sender"
    assert payload["using_direct_sender"] is True
    assert payload["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert payload["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert payload["video_path"] is None


def test_main_writes_numpy_direct_report_json(tmp_path) -> None:
    module = _load_module()
    camera = FakeCamera()
    output = tmp_path / "demo-report.json"
    expected_direct_only = module.sys.platform == "darwin"

    rc = module.main(
        [
            "--mode", "numpy-direct",
            "--width", "640",
            "--height", "360",
            "--fps", "20",
            "--duration", "0",
            "--name", "AKVC Demo",
            "--report-json", str(output),
        ],
        camera_factory=lambda **kwargs: camera,
        qt_loader=lambda: (_ for _ in ()).throw(AssertionError("qt loader should not be used")),
        sleeper=lambda seconds: None,
    )

    assert rc == 0
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "numpy-direct"
    assert payload["frame_source_kind"] == "numpy_direct"
    assert payload["python_entrypoint_kind"] == "push_frame"
    assert payload["sdk_streamer_factory_used"] is False
    assert payload["sdk_latest_provider_factory_used"] is False
    assert payload["sdk_direct_push_used"] is True
    assert payload["requested_direct_only"] is expected_direct_only
    assert payload["allow_shared_memory_fallback"] is (not expected_direct_only)


def test_main_writes_video_path_for_video_file_mode(tmp_path) -> None:
    module = _load_module()
    FakeStreamer.instances.clear()
    FakeVideoProvider.instances.clear()
    camera = FakeCamera()
    output = tmp_path / "demo-report.json"

    rc = module.main(
        [
            "--mode", "video-file",
            "--width", "1280",
            "--height", "720",
            "--fps", "30",
            "--duration", "0",
            "--name", "AKVC Demo",
            "--video-path", "demo.mp4",
            "--report-json", str(output),
        ],
        camera_factory=lambda **kwargs: camera,
        streamer_cls=FakeStreamer,
        qt_loader=lambda: FakeQtModule,
        sleeper=lambda seconds: None,
        video_provider_cls=FakeVideoProvider,
    )

    assert rc == 0
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "video-file"
    assert payload["frame_source_kind"] == "opencv_video_file"
    assert payload["python_entrypoint_kind"] == "create_pyside6_streamer.start_video_file_stream"
    assert payload["sdk_streamer_factory_used"] is True
    assert payload["sdk_latest_provider_factory_used"] is False
    assert payload["sdk_direct_push_used"] is False
    assert payload["video_path"] == "demo.mp4"
