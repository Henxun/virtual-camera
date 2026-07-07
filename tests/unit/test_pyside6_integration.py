# SPDX-License-Identifier: Apache-2.0
"""PySide6 integration helper tests."""

from __future__ import annotations

from akvc.integrations.pyside6 import (
    LatestFrameProvider,
    OpenCVVideoFileProvider,
    PySide6VirtualCameraBridge,
    PySide6VirtualCameraStreamer,
    push_qimage,
    push_qpixmap,
    push_screen,
    push_widget,
)


class FakeCamera:
    def __init__(self) -> None:
        self.frames = []

    def push_frame(self, frame) -> None:
        self.frames.append(frame)


class FakePixmap:
    pass


class FakeWidget:
    def __init__(self, pixmap) -> None:
        self._pixmap = pixmap

    def grab(self):
        return self._pixmap


class FakeScreen:
    def __init__(self, pixmap) -> None:
        self._pixmap = pixmap
        self.calls = []

    def grabWindow(self, window, x, y, width, height):
        self.calls.append((window, x, y, width, height))
        return self._pixmap


class FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self) -> None:
        for callback in list(self.callbacks):
            callback()


class FakeTimer:
    def __init__(self) -> None:
        self.timeout = FakeSignal()
        self.started_with = []
        self.stop_calls = 0

    def start(self, interval_ms: int) -> None:
        self.started_with.append(interval_ms)

    def stop(self) -> None:
        self.stop_calls += 1


class ClosableProvider:
    def __init__(self, frames) -> None:
        self._frames = list(frames)
        self.close_calls = 0

    def __call__(self):
        if self._frames:
            return self._frames.pop(0)
        raise StopIteration("provider exhausted")

    def close(self) -> None:
        self.close_calls += 1


class FakeCapture:
    def __init__(self, frames, *, opened: bool = True) -> None:
        self._initial_frames = list(frames)
        self.frames = list(frames)
        self.opened = opened
        self.read_calls = 0
        self.set_calls = []
        self.release_calls = 0

    def isOpened(self) -> bool:
        return self.opened

    def read(self):
        self.read_calls += 1
        if self.frames:
            item = self.frames.pop(0)
            return True, item
        return False, None

    def set(self, prop, value) -> None:
        self.set_calls.append((prop, value))
        if value == 0:
            self.frames = list(self._initial_frames)

    def release(self) -> None:
        self.release_calls += 1


class FakeCv2:
    CAP_PROP_POS_FRAMES = 1

    def __init__(self, capture: FakeCapture) -> None:
        self._capture = capture
        self.opened_paths = []

    def VideoCapture(self, path: str):
        self.opened_paths.append(path)
        return self._capture


def test_push_qimage_forwards_to_camera() -> None:
    camera = FakeCamera()
    image = object()

    push_qimage(camera, image)

    assert camera.frames == [image]


def test_push_qpixmap_forwards_to_camera() -> None:
    camera = FakeCamera()
    pixmap = FakePixmap()

    push_qpixmap(camera, pixmap)

    assert camera.frames == [pixmap]


def test_push_widget_grabs_and_sends_pixmap() -> None:
    camera = FakeCamera()
    pixmap = FakePixmap()

    push_widget(camera, FakeWidget(pixmap))

    assert camera.frames == [pixmap]


def test_push_screen_uses_grabwindow_and_sends_pixmap() -> None:
    camera = FakeCamera()
    pixmap = FakePixmap()
    screen = FakeScreen(pixmap)

    push_screen(camera, screen, window=11, x=2, y=3, width=640, height=360)

    assert screen.calls == [(11, 2, 3, 640, 360)]
    assert camera.frames == [pixmap]


def test_bridge_wraps_common_qt_capture_entrypoints() -> None:
    camera = FakeCamera()
    bridge = PySide6VirtualCameraBridge(camera)
    pixmap = FakePixmap()
    widget = FakeWidget(pixmap)
    screen = FakeScreen(pixmap)
    image = object()

    bridge.send_image(image)
    bridge.send_pixmap(pixmap)
    bridge.send_widget(widget)
    bridge.send_screen(screen)

    assert camera.frames == [image, pixmap, pixmap, pixmap]


def test_streamer_start_widget_stream_grabs_frames_on_timer_ticks() -> None:
    camera = FakeCamera()
    pixmap = FakePixmap()
    timer = FakeTimer()
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_widget_stream(FakeWidget(pixmap), interval_ms=33)
    timer.timeout.emit()
    timer.timeout.emit()

    assert timer.started_with == [33]
    assert camera.frames == [pixmap, pixmap]
    assert streamer.running is True


def test_streamer_exposes_wrapped_camera() -> None:
    camera = FakeCamera()
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=FakeTimer)

    assert streamer.camera is camera


def test_streamer_start_screen_stream_uses_grabwindow_arguments() -> None:
    camera = FakeCamera()
    pixmap = FakePixmap()
    timer = FakeTimer()
    screen = FakeScreen(pixmap)
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_screen_stream(
        screen,
        interval_ms=16,
        window=7,
        x=10,
        y=20,
        width=640,
        height=360,
    )
    timer.timeout.emit()

    assert timer.started_with == [16]
    assert screen.calls == [(7, 10, 20, 640, 360)]
    assert camera.frames == [pixmap]


def test_streamer_start_provider_stream_invokes_callable_each_tick() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    frames = iter(["frame-1", "frame-2"])
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_provider_stream(lambda: next(frames), interval_ms=40)
    timer.timeout.emit()
    timer.timeout.emit()

    assert timer.started_with == [40]
    assert camera.frames == ["frame-1", "frame-2"]


def test_streamer_skips_tick_when_provider_has_no_frame_available() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    def provider():
        raise LookupError("no frame yet")

    streamer.start_provider_stream(provider, interval_ms=33)
    timer.timeout.emit()

    assert camera.frames == []
    assert streamer.running is True


def test_streamer_skips_tick_when_provider_returns_none() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    def provider():
        return None

    streamer.start_provider_stream(provider, interval_ms=33)
    timer.timeout.emit()

    assert camera.frames == []
    assert streamer.running is True


def test_streamer_stops_when_provider_is_exhausted() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    frames = iter(["frame-1"])
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_provider_stream(lambda: next(frames), interval_ms=33)
    timer.timeout.emit()
    timer.timeout.emit()

    assert camera.frames == ["frame-1"]
    assert timer.stop_calls == 1
    assert streamer.running is False


def test_streamer_start_latest_frame_stream_uses_explicit_entrypoint() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    provider = LatestFrameProvider()
    provider.submit("frame-1")
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_latest_frame_stream(provider, interval_ms=20)
    timer.timeout.emit()

    assert timer.started_with == [20]
    assert camera.frames == ["frame-1"]
    assert streamer.running is True


def test_streamer_start_video_file_stream_closes_owned_provider_on_stop() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    owned_provider = ClosableProvider(["frame-1"])
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_video_file_stream(
        "demo.mp4",
        interval_ms=25,
        provider_factory=lambda path, *, loop=True, cv2_module=None: owned_provider,
    )
    timer.timeout.emit()
    streamer.stop()

    assert timer.started_with == [25]
    assert camera.frames == ["frame-1"]
    assert owned_provider.close_calls == 1
    assert streamer.running is False


def test_streamer_replacing_owned_video_provider_closes_previous_instance() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    first = ClosableProvider(["frame-1"])
    second = ClosableProvider(["frame-2"])
    providers = iter([first, second])
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    def factory(path, *, loop=True, cv2_module=None):
        del path, loop, cv2_module
        return next(providers)

    streamer.start_video_file_stream("first.mp4", interval_ms=30, provider_factory=factory)
    streamer.start_video_file_stream("second.mp4", interval_ms=30, provider_factory=factory)
    timer.timeout.emit()
    streamer.stop()

    assert first.close_calls == 1
    assert second.close_calls == 1
    assert camera.frames == ["frame-2"]


def test_streamer_owned_video_provider_is_closed_when_exhausted() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    provider = ClosableProvider(["frame-1"])
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_video_file_stream(
        "demo.mp4",
        interval_ms=33,
        provider_factory=lambda path, *, loop=True, cv2_module=None: provider,
    )
    timer.timeout.emit()
    timer.timeout.emit()

    assert camera.frames == ["frame-1"]
    assert timer.stop_calls == 1
    assert provider.close_calls == 1
    assert streamer.running is False


def test_streamer_stop_stops_timer_and_clears_running_state() -> None:
    camera = FakeCamera()
    timer = FakeTimer()
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=lambda: timer)

    streamer.start_provider_stream(lambda: "frame", interval_ms=30)
    streamer.stop()

    assert timer.stop_calls == 1
    assert streamer.running is False


def test_streamer_rejects_nonpositive_interval() -> None:
    camera = FakeCamera()
    streamer = PySide6VirtualCameraStreamer(camera, timer_factory=FakeTimer)

    try:
        streamer.start_provider_stream(lambda: "frame", interval_ms=0)
    except ValueError as exc:
        assert "interval_ms" in str(exc)
    else:
        raise AssertionError("expected ValueError for interval_ms <= 0")


def test_latest_frame_provider_returns_latest_submission_and_repeats_last_by_default() -> None:
    provider = LatestFrameProvider()

    provider.submit("frame-1")
    assert provider() == "frame-1"

    provider.submit("frame-2")
    provider.submit("frame-3")
    assert provider() == "frame-3"
    assert provider() == "frame-3"


def test_latest_frame_provider_requires_new_submission_when_repeat_last_is_disabled() -> None:
    provider = LatestFrameProvider(repeat_last=False)
    provider.submit("frame-1")

    assert provider() == "frame-1"
    try:
        provider()
    except LookupError as exc:
        assert "no frame" in str(exc)
    else:
        raise AssertionError("expected LookupError when no new frame is available")


def test_latest_frame_provider_close_stops_future_reads_and_rejects_new_frames() -> None:
    provider = LatestFrameProvider()
    provider.submit("frame-1")
    provider.close()

    try:
        provider()
    except StopIteration as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("expected StopIteration after provider close()")

    try:
        provider.submit("frame-2")
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when submitting to a closed provider")


def test_opencv_video_file_provider_reads_frames_and_loops() -> None:
    capture = FakeCapture(["frame-1"])
    cv2 = FakeCv2(capture)
    provider = OpenCVVideoFileProvider("demo.mp4", cv2_module=cv2, loop=True)

    first = provider()
    second = provider()
    provider.close()

    assert first == "frame-1"
    assert second == "frame-1"
    assert cv2.opened_paths == ["demo.mp4"]
    assert capture.set_calls == [(cv2.CAP_PROP_POS_FRAMES, 0)]
    assert capture.release_calls == 1


def test_opencv_video_file_provider_rejects_unopenable_capture() -> None:
    capture = FakeCapture([], opened=False)
    cv2 = FakeCv2(capture)

    try:
        OpenCVVideoFileProvider("broken.mp4", cv2_module=cv2)
    except RuntimeError as exc:
        assert "broken.mp4" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for unopened capture")


def test_opencv_video_file_provider_raises_stop_iteration_without_loop() -> None:
    capture = FakeCapture([])
    cv2 = FakeCv2(capture)
    provider = OpenCVVideoFileProvider("demo.mp4", cv2_module=cv2, loop=False)

    try:
        provider()
    except StopIteration:
        pass
    else:
        raise AssertionError("expected StopIteration when loop=False and no frame is available")
