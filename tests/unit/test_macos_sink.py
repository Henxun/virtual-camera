# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import numpy as np
import pytest

from akvc.core.errors import FrameBusError
from akvc.core.frame import FourCC, Frame
from akvc.core.frame_sink.macos_shm import MacOsShmSink


class FakeNativeMacOsShmSink:
    def __init__(self) -> None:
        self.open_calls = 0
        self.close_calls = 0
        self.published: list[Frame] = []
        self.consumer_count = 3

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def publish(self, frame: Frame) -> None:
        self.published.append(frame)


class FailingNativeMacOsShmSink(FakeNativeMacOsShmSink):
    def open(self) -> None:
        raise ValueError("shared region schema mismatch")


@pytest.fixture
def nv12_frame() -> Frame:
    y_plane = np.array([[16, 16], [16, 16]], dtype=np.uint8)
    uv_plane = np.array([[128, 128]], dtype=np.uint8)
    return Frame.make_nv12(y_plane, uv_plane, seq=1)


def test_open_requires_macos(monkeypatch) -> None:
    sink = MacOsShmSink()
    monkeypatch.setattr("akvc.core.frame_sink.macos_shm.sys.platform", "win32")

    with pytest.raises(FrameBusError, match="only run on macOS"):
        sink.open()


def test_open_publish_close_delegate_to_native(monkeypatch, nv12_frame: Frame) -> None:
    native = FakeNativeMacOsShmSink()
    sink = MacOsShmSink()
    sink._native = native
    monkeypatch.setattr("akvc.core.frame_sink.macos_shm.sys.platform", "darwin")

    sink.open()
    sink.publish(nv12_frame)
    sink.close()

    assert native.open_calls == 1
    assert native.published == [nv12_frame]
    assert native.close_calls == 1


def test_consumer_count_is_zero_when_closed() -> None:
    sink = MacOsShmSink()

    assert sink.consumer_count == 0


def test_consumer_count_reads_native_when_open(monkeypatch) -> None:
    native = FakeNativeMacOsShmSink()
    sink = MacOsShmSink()
    sink._native = native
    monkeypatch.setattr("akvc.core.frame_sink.macos_shm.sys.platform", "darwin")

    sink.open()

    assert sink.consumer_count == 3


def test_publish_requires_opened_sink(nv12_frame: Frame) -> None:
    sink = MacOsShmSink()

    with pytest.raises(FrameBusError, match="sink not opened"):
        sink.publish(nv12_frame)


def test_publish_rejects_non_nv12(monkeypatch) -> None:
    native = FakeNativeMacOsShmSink()
    sink = MacOsShmSink()
    sink._native = native
    monkeypatch.setattr("akvc.core.frame_sink.macos_shm.sys.platform", "darwin")
    sink.open()
    frame = Frame.from_bgr(np.array([[[0, 0, 0]]], dtype=np.uint8), seq=1)

    with pytest.raises(FrameBusError, match="only NV12 supported"):
        sink.publish(frame)


def test_native_open_errors_surface(monkeypatch) -> None:
    sink = MacOsShmSink()
    sink._native = FailingNativeMacOsShmSink()
    monkeypatch.setattr("akvc.core.frame_sink.macos_shm.sys.platform", "darwin")

    with pytest.raises(ValueError, match="shared region schema mismatch"):
        sink.open()

    assert sink.consumer_count == 0
