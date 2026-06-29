# SPDX-License-Identifier: Apache-2.0
"""macOS POSIX shared-memory frame sink."""

from __future__ import annotations

import sys

from akvc._core_native import NativeMacOsShmSink

from ..errors import FrameBusError
from ..frame import FourCC, Frame
from .base import FrameSink


class MacOsShmSink(FrameSink):
    def __init__(self) -> None:
        self._native = NativeMacOsShmSink()
        self._opened = False

    def open(self) -> None:
        if sys.platform != "darwin":
            raise FrameBusError("MacOsShmSink can only run on macOS")
        self._native.open()
        self._opened = True

    def close(self) -> None:
        self._native.close()
        self._opened = False

    @property
    def consumer_count(self) -> int:
        if not self._opened:
            return 0
        return self._native.consumer_count

    def publish(self, frame: Frame) -> None:
        if not self._opened:
            raise FrameBusError("sink not opened")
        if frame.fourcc != FourCC.NV12:
            raise FrameBusError(
                f"only NV12 supported; got fourcc={frame.fourcc:#x}"
            )
        self._native.publish(frame)
