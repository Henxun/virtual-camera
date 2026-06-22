# SPDX-License-Identifier: Apache-2.0
"""VirtualCamera SDK tests."""

from __future__ import annotations

import numpy as np

from akvc.sdk.virtual_camera import VirtualCamera


class FakeHelper:
    def __init__(self, *, start_result: bool = True, ping_result: bool = True, register_result: bool = True) -> None:
        self.start_result = start_result
        self.ping_result = ping_result
        self.register_result = register_result
        self.start_calls = 0
        self.ping_calls = 0
        self.register_calls: list[str] = []
        self.stop_calls = 0

    def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    def ping(self) -> bool:
        self.ping_calls += 1
        return self.ping_result

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        self.register_calls.append(name)
        return self.register_result

    def stop(self) -> None:
        self.stop_calls += 1


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


def test_start_opens_sink_and_registers_once(monkeypatch) -> None:
    helper = FakeHelper()
    sink = FakeSink()

    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr("akvc.sdk.virtual_camera.create_sink", lambda: sink)

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


def test_push_frame_uses_pipeline_and_sink(monkeypatch) -> None:
    helper = FakeHelper()
    sink = FakeSink()
    pipeline = FakePipeline()

    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr("akvc.sdk.virtual_camera.create_sink", lambda: sink)

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
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)

    vc = VirtualCamera()
    try:
        vc.push_frame(np.zeros((4, 4, 3), dtype=np.uint8))
    except RuntimeError as exc:
        assert "not started" in str(exc)
    else:
        raise AssertionError("push_frame should require start()")


def test_helper_start_failure_raises(monkeypatch) -> None:
    helper = FakeHelper(start_result=False)
    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)

    vc = VirtualCamera()
    try:
        vc.start()
    except RuntimeError as exc:
        assert "failed to start" in str(exc)
    else:
        raise AssertionError("start should fail when helper does not start")


def test_close_stops_helper_and_is_idempotent(monkeypatch) -> None:
    helper = FakeHelper()
    sink = FakeSink()

    monkeypatch.setattr("akvc.sdk.virtual_camera.HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr("akvc.sdk.virtual_camera.create_sink", lambda: sink)

    vc = VirtualCamera()
    vc.start()
    vc.close()
    vc.close()

    assert sink.close_calls == 1
    assert helper.stop_calls == 2
    assert vc.started is False
