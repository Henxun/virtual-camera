# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS direct-push demo helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_direct_push_demo.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("macos_direct_push_demo", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCamera:
    def __init__(self) -> None:
        self.start_calls = []
        self.close_calls = 0
        self.push_frame_calls = []
        self.send_pixmap_calls = []
        self.send_widget_calls = []
        self.send_screen_calls = []
        self.consumer_count = 2
        self.backend_name = "direct_sender"
        self.using_direct_sender = True
        self.direct_sender_attempted = True
        self.direct_sender_state = "active"
        self.direct_sender_target_name = "AKVC Direct"
        self.direct_sender_library_path = "/tmp/libakvc-macos-direct-sender.dylib"
        self.direct_sender_last_error = None
        self.helper_hot_path_used = False
        self.shared_memory_fallback_used = False
        self.last_frame_fourcc = None
        self.last_frame_format_name = None
        self.direct_only = True
        self.request_camera_access_calls = 0
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
            "camera_name": "AKVC Direct",
            "backend_name": "direct_sender",
            "using_direct_sender": True,
            "direct_sender_attempted": True,
            "direct_sender_state": "active",
            "direct_sender_target_name": "AKVC Direct",
            "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
            "direct_sender_last_error": None,
            "helper_hot_path_used": False,
            "shared_memory_fallback_used": False,
            "last_frame_fourcc": None,
            "last_frame_format_name": None,
            "consumer_count": 2,
            "runtime_topology": dict(self.runtime_topology_payload),
        }
        self.direct_sender_device_snapshot_payload = {
            "all_devices": ["AKVC Direct"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        }

    def start(self, name: str = "AK Virtual Camera") -> None:
        self.start_calls.append(name)

    def close(self) -> None:
        self.close_calls += 1

    def push_frame(self, frame) -> None:
        self.push_frame_calls.append(frame)
        self._record_last_frame(frame)

    def send_pixmap(self, frame) -> None:
        self.send_pixmap_calls.append(frame)
        self._record_last_frame(frame)

    def send_widget(self, frame) -> None:
        self.send_widget_calls.append(frame)
        self._record_last_frame(frame)

    def send_screen(self, frame) -> None:
        self.send_screen_calls.append(frame)
        self._record_last_frame(frame)

    def _record_last_frame(self, frame) -> None:
        self.last_frame_fourcc = getattr(frame, "fourcc", None)
        if self.last_frame_fourcc == 0x20424752:
            self.last_frame_format_name = "RGB24"
        elif self.last_frame_fourcc == 0x41524742:
            self.last_frame_format_name = "BGRA32"
        else:
            self.last_frame_format_name = None

    def direct_sender_device_snapshot(self):
        return dict(self.direct_sender_device_snapshot_payload)

    def request_camera_access(self):
        self.request_camera_access_calls += 1
        return dict(self.direct_sender_device_snapshot_payload)

    def runtime_topology(self):
        return dict(self.runtime_topology_payload)

    def runtime_snapshot(self):
        payload = dict(self.runtime_snapshot_payload)
        payload["runtime_topology"] = dict(self.runtime_topology_payload)
        payload["consumer_count"] = self.consumer_count
        payload["last_frame_fourcc"] = self.last_frame_fourcc
        payload["last_frame_format_name"] = self.last_frame_format_name
        return payload


def test_macos_direct_push_demo_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "VirtualCamera.push_frame(...)" in text
    assert "VirtualCamera.send_pixmap(...)" in text
    assert "VirtualCamera.send_widget(...)" in text
    assert "VirtualCamera.send_screen(...)" in text
    assert "--frames" in text
    assert "--app-bundle" in text
    assert "--host-bundle" in text
    assert "--direct-sender-library" in text
    assert "--allow-shared-memory-fallback" in text
    assert "--probe-only" in text
    assert "--request-camera-access" in text
    assert "--frame-kind" in text
    assert "--entrypoint" in text
    assert "--report-json" in text
    assert '"mode": "direct-push"' in text
    assert "runtime_snapshot" in text


def test_run_demo_pushes_requested_number_of_frames_without_qt() -> None:
    module = _load_module()
    camera = FakeCamera()
    slept = []
    original_factory = module._make_frame_factory

    class FakeArray:
        def __init__(self, shape) -> None:
            self.shape = shape

    def fake_make_frame_factory(*, width: int, height: int):
        state = {"index": 0}

        def _factory():
            _ = state["index"]
            state["index"] += 1
            return FakeArray((height, width, 3))

        return _factory, "numpy.ndarray"

    module._make_frame_factory = fake_make_frame_factory

    try:
        payload = module.run_demo(
            width=640,
            height=360,
            fps=20.0,
            duration=0.0,
            frames=3,
            name="AKVC Direct",
            camera_factory=lambda **kwargs: camera,
            sleeper=lambda seconds: slept.append(seconds),
        )
    finally:
        module._make_frame_factory = original_factory

    assert camera.start_calls == ["AKVC Direct"]
    assert camera.close_calls == 1
    assert len(camera.push_frame_calls) == 3
    assert camera.push_frame_calls[0].shape == (360, 640, 3)
    assert payload["mode"] == "direct-push"
    assert payload["direct_only"] is True
    assert payload["allow_shared_memory_fallback"] is False
    assert payload["frame_source_kind"] == "numpy.ndarray"
    assert payload["python_entrypoint_kind"] == "push_frame"
    assert payload["requested_frame_kind"] == "auto"
    assert payload["requested_entrypoint"] == "push-frame"
    assert payload["sdk_direct_push_used"] is True
    assert payload["backend_name"] == "direct_sender"
    assert payload["using_direct_sender"] is True
    assert payload["direct_sender_attempted"] is True
    assert payload["direct_sender_state"] == "active"
    assert payload["direct_sender_target_name"] == "AKVC Direct"
    assert payload["direct_sender_library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert payload["direct_sender_last_error"] is None
    assert payload["helper_hot_path_used"] is False
    assert payload["shared_memory_fallback_used"] is False
    assert payload["direct_runtime_ready"] is True
    assert "direct_runtime_note" not in payload
    assert payload["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert payload["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert payload["runtime_control_plane"] == "host_activation_only"
    assert payload["runtime_snapshot"]["runtime_topology"]["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert payload["runtime_snapshot"]["backend_name"] == "direct_sender"
    assert payload["direct_sender_device_snapshot"] == {
        "all_devices": ["AKVC Direct"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }
    assert payload["last_frame_fourcc"] is None
    assert payload["last_frame_format_name"] is None
    assert payload["requested_frames"] == 3
    assert payload["frames_sent"] == 3
    assert payload["consumer_count"] == 2
    assert slept == [0.05, 0.05]


def test_main_writes_direct_push_report_json(tmp_path) -> None:
    module = _load_module()
    camera = FakeCamera()
    output = tmp_path / "direct-push-report.json"
    original_factory = module._make_frame_factory

    class FakeArray:
        def __init__(self, shape) -> None:
            self.shape = shape

    def fake_make_frame_factory(*, width: int, height: int):
        state = {"index": 0}

        def _factory():
            _ = state["index"]
            state["index"] += 1
            return FakeArray((height, width, 3))

        return _factory, "numpy.ndarray"

    module._make_frame_factory = fake_make_frame_factory

    try:
        rc = module.main(
            [
                "--width", "640",
                "--height", "360",
                "--fps", "20",
                "--frames", "2",
                "--name", "AKVC Direct",
                "--report-json", str(output),
            ],
            camera_factory=lambda **kwargs: camera,
            sleeper=lambda seconds: None,
        )
    finally:
        module._make_frame_factory = original_factory

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "direct-push"
    assert payload["direct_only"] is True
    assert payload["allow_shared_memory_fallback"] is False
    assert payload["frame_source_kind"] == "numpy.ndarray"
    assert payload["python_entrypoint_kind"] == "push_frame"
    assert payload["requested_frame_kind"] == "auto"
    assert payload["requested_entrypoint"] == "push-frame"
    assert payload["backend_name"] == "direct_sender"
    assert payload["using_direct_sender"] is True
    assert payload["direct_sender_attempted"] is True
    assert payload["direct_sender_state"] == "active"
    assert payload["direct_sender_target_name"] == "AKVC Direct"
    assert payload["direct_sender_library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert payload["direct_sender_last_error"] is None
    assert payload["helper_hot_path_used"] is False
    assert payload["shared_memory_fallback_used"] is False
    assert payload["direct_runtime_ready"] is True
    assert "direct_runtime_note" not in payload
    assert payload["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert payload["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert payload["runtime_control_plane"] == "host_activation_only"
    assert payload["runtime_snapshot"]["runtime_topology"]["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert payload["runtime_snapshot"]["direct_sender_target_name"] == "AKVC Direct"
    assert payload["direct_sender_device_snapshot"] == {
        "all_devices": ["AKVC Direct"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }
    assert payload["last_frame_fourcc"] is None
    assert payload["last_frame_format_name"] is None
    assert payload["requested_frames"] == 2
    assert payload["frames_sent"] == 2


def test_main_writes_probe_report_json_when_direct_start_fails(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "direct-push-report.json"

    class FailingStartCamera(FakeCamera):
        def start(self, name: str = "AK Virtual Camera") -> None:
            self.start_calls.append(name)
            raise RuntimeError("camera device not found: OBS Virtual Camera")

    camera = FailingStartCamera()
    rc = module.main(
        [
            "--width", "640",
            "--height", "360",
            "--fps", "20",
            "--frames", "2",
            "--name", "OBS Virtual Camera",
            "--report-json", str(output),
        ],
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    assert rc == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "direct-push"
    assert payload["direct_only"] is True
    assert payload["probe_only"] is False
    assert payload["failure_report_generated_via_probe"] is True
    assert payload["camera_name"] == "OBS Virtual Camera"
    assert payload["frames_sent"] == 0
    assert payload["requested_frames"] == 2
    assert payload["error"] == "camera device not found: OBS Virtual Camera"
    assert payload["direct_sender_attempted"] is True
    assert payload["direct_sender_state"] == "active"
    assert payload["using_direct_sender"] is True
    assert payload["direct_sender_target_name"] == "AKVC Direct"
    assert payload["direct_sender_last_error"] is None
    assert payload["direct_sender_device_snapshot"] == {
        "all_devices": ["AKVC Direct"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }


def test_main_require_direct_runtime_fails_when_runtime_falls_back(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "direct-push-report.json"

    class FallbackCamera(FakeCamera):
        def __init__(self) -> None:
            super().__init__()
            self.backend_name = "shared_memory"
            self.using_direct_sender = False
            self.direct_sender_state = "fallback"
            self.shared_memory_fallback_used = True
            self.direct_only = False
            self.runtime_topology_payload = {
                "runtime_topology_kind": "camera_extension_shared_memory",
                "runtime_frame_path": "python_sdk -> shared_memory -> camera_extension -> system_camera_device -> client_app",
                "runtime_host_role": "container_activation_command_bridge",
                "runtime_host_in_frame_hot_path": False,
                "runtime_dedicated_host_daemon_required": False,
                "runtime_container_app_configured": True,
                "runtime_data_plane": "shared_memory_ringbuffer",
                "runtime_control_plane": "host_activation_only",
            }
            self.runtime_snapshot_payload.update(
                {
                    "backend_name": "shared_memory",
                    "using_direct_sender": False,
                    "direct_sender_state": "fallback",
                    "shared_memory_fallback_used": True,
                    "runtime_topology": dict(self.runtime_topology_payload),
                }
            )

    rc = module.main(
        [
            "--width", "640",
            "--height", "360",
            "--fps", "20",
            "--frames", "1",
            "--name", "AKVC Direct",
            "--allow-shared-memory-fallback",
            "--require-direct-runtime",
            "--report-json", str(output),
        ],
        camera_factory=lambda **kwargs: FallbackCamera(),
        sleeper=lambda seconds: None,
    )

    assert rc == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["direct_runtime_ready"] is False
    assert "using_direct_sender != true" in payload["direct_runtime_note"]
    assert "shared_memory_fallback_used != false" in payload["direct_runtime_note"]


def test_run_demo_falls_back_to_frame_objects_when_numpy_is_unavailable() -> None:
    module = _load_module()
    camera = FakeCamera()
    original_factory = module._make_numpy_frame_factory

    def fail_numpy_factory(*, width: int, height: int):
        del width, height
        raise RuntimeError("numpy unavailable")

    module._make_numpy_frame_factory = fail_numpy_factory
    try:
        payload = module.run_demo(
            width=4,
            height=2,
            fps=30.0,
            duration=0.0,
            frames=1,
            name="AKVC Direct",
            camera_factory=lambda **kwargs: camera,
            sleeper=lambda seconds: None,
        )
    finally:
        module._make_numpy_frame_factory = original_factory

    frame = camera.push_frame_calls[0]
    assert payload["frame_source_kind"] == "Frame"
    assert frame.width == 4
    assert frame.height == 2
    assert payload["last_frame_format_name"] == "RGB24"


def test_run_demo_can_force_bgra_frame_objects() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=4,
        height=2,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        frame_kind="bgra-bytes",
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    frame = camera.push_frame_calls[0]
    assert payload["frame_source_kind"] == "Frame"
    assert frame.fourcc == 0x41524742
    assert frame.width == 4
    assert frame.height == 2
    assert payload["last_frame_fourcc"] == 0x41524742
    assert payload["last_frame_format_name"] == "BGRA32"


def test_run_demo_can_force_qimage_like_bgra_inputs() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=4,
        height=2,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        frame_kind="qimage-bgra",
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    frame = camera.push_frame_calls[0]
    assert payload["frame_source_kind"] == "QImage"
    assert callable(getattr(frame, "format", None))
    assert frame.width() == 4
    assert frame.height() == 2


def test_run_demo_can_use_send_pixmap_entrypoint() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=4,
        height=2,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        frame_kind="qimage-bgra",
        entrypoint="send-pixmap",
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    assert payload["frame_source_kind"] == "QPixmap"
    assert payload["python_entrypoint_kind"] == "send_pixmap"
    assert len(camera.send_pixmap_calls) == 1
    pixmap = camera.send_pixmap_calls[0]
    assert callable(getattr(pixmap, "toImage", None))
    image = pixmap.toImage()
    assert callable(getattr(image, "format", None))
    assert image.width() == 4
    assert image.height() == 2


def test_run_demo_can_use_send_widget_entrypoint() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=4,
        height=2,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        frame_kind="qimage-bgra",
        entrypoint="send-widget",
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    assert payload["frame_source_kind"] == "QWidget"
    assert payload["python_entrypoint_kind"] == "send_widget"
    assert len(camera.send_widget_calls) == 1
    widget = camera.send_widget_calls[0]
    assert callable(getattr(widget, "grab", None))
    pixmap = widget.grab()
    assert callable(getattr(pixmap, "toImage", None))


def test_run_demo_can_use_send_screen_entrypoint() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=4,
        height=2,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        frame_kind="qimage-bgra",
        entrypoint="send-screen",
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    assert payload["frame_source_kind"] == "QScreen"
    assert payload["python_entrypoint_kind"] == "send_screen"
    assert len(camera.send_screen_calls) == 1
    screen = camera.send_screen_calls[0]
    assert callable(getattr(screen, "grabWindow", None))


def test_run_demo_forwards_helper_and_direct_sender_paths() -> None:
    module = _load_module()
    observed = {}
    camera = FakeCamera()

    def factory(**kwargs):
        observed.update(kwargs)
        return camera

    module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        helper_exe="/Applications/Amaran Desktop.app",
        direct_sender_library="/tmp/libakvc-macos-direct-sender.dylib",
        camera_factory=factory,
        sleeper=lambda seconds: None,
    )

    assert observed["helper_exe"] == "/Applications/Amaran Desktop.app"
    assert observed["direct_sender_library"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert observed["direct_only"] is True


def test_run_demo_forwards_explicit_host_paths() -> None:
    module = _load_module()
    observed = {}
    camera = FakeCamera()

    def factory(**kwargs):
        observed.update(kwargs)
        return camera

    module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        host_bundle="/Applications/Amaran Desktop.app",
        direct_sender_library="/tmp/libakvc-macos-direct-sender.dylib",
        camera_factory=factory,
        sleeper=lambda seconds: None,
    )

    assert observed["app_bundle"] == "/Applications/Amaran Desktop.app"
    assert observed["app_executable"] is None
    assert observed["direct_sender_library"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert observed["direct_only"] is True


def test_run_demo_can_allow_shared_memory_fallback_explicitly() -> None:
    module = _load_module()
    observed = {}
    camera = FakeCamera()

    def factory(**kwargs):
        observed.update(kwargs)
        return camera

    payload = module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        direct_only=False,
        camera_factory=factory,
        sleeper=lambda seconds: None,
    )

    assert observed["direct_only"] is False
    assert payload["direct_only"] is False


def test_run_demo_probe_only_returns_native_snapshot_without_starting_camera() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        duration=1.0,
        frames=5,
        name="AKVC Direct",
        probe_only=True,
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    assert camera.start_calls == []
    assert camera.close_calls == 1
    assert payload["probe_only"] is True
    assert payload["requested_frames"] == 0
    assert payload["frames_sent"] == 0
    assert payload["direct_sender_device_snapshot"] == {
        "all_devices": ["AKVC Direct"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }


def test_run_demo_can_request_camera_access_before_start() -> None:
    module = _load_module()
    camera = FakeCamera()

    payload = module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        duration=0.0,
        frames=1,
        name="AKVC Direct",
        request_camera_access=True,
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
    )

    assert camera.request_camera_access_calls == 1
    assert payload["requested_camera_access"] is True
    assert payload["requested_camera_access_snapshot"] == {
        "all_devices": ["AKVC Direct"],
        "camera_access_status": "authorized",
        "environment_device_enumeration_empty": False,
    }


def test_main_rejects_conflicting_host_path_flags(capsys) -> None:
    module = _load_module()

    try:
        module.main(
            [
                "--host-bundle", "/Applications/Amaran Desktop.app",
                "--host-executable", "/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse to reject conflicting host path flags")

    captured = capsys.readouterr()
    assert "mutually exclusive" in captured.err
