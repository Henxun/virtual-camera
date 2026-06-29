# SPDX-License-Identifier: Apache-2.0
"""Windows shared-memory frame sink."""

from __future__ import annotations

from akvc._core_native import NativeWindowsFrameBusProducer

from ..errors import FrameBusError
from ..frame import FourCC, Frame
from .base import FrameSink


class WindowsShmSink(FrameSink):
    def __init__(self) -> None:
        self._producer = NativeWindowsFrameBusProducer()
        self._opened = False

    def open(self) -> None:
        self._producer.open()
        self._opened = True

    def close(self) -> None:
        self._producer.close()
        self._opened = False

    @property
    def consumer_count(self) -> int:
        if not self._opened:
            return 0
        return self._producer.consumer_count

    def publish(self, frame: Frame) -> None:
        if not self._opened:
            raise FrameBusError("sink not opened")
        if frame.fourcc != FourCC.NV12:
            raise FrameBusError(
                f"only NV12 supported in Phase 2; got fourcc={frame.fourcc:#x}"
            )
        self._producer.publish(frame)
