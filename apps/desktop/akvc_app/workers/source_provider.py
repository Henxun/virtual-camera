# SPDX-License-Identifier: Apache-2.0
"""App-side native source providers for the desktop worker path."""

from __future__ import annotations

import threading
from enum import Enum
from typing import Protocol

from akvc._core_native import (
    FLAG_PLACEHOLDER,
    Frame,
    NativeTestPatternProvider,
    NativeUsbCaptureOpener,
    NativeUsbFrameReader,
    list_usb_sources as _list_usb_sources,
    parse_source_id,
)

from ..services.source_info import (
    DEFAULT_PROVIDER_FPS,
    DEFAULT_PROVIDER_HEIGHT,
    DEFAULT_PROVIDER_WIDTH,
    PATTERN_NAMES,
    Pattern,
    ProviderInfo,
    describe_source_id,
    provider_info_from_native,
)


class FrameProvider(Protocol):
    def open(self) -> None: ...
    def read(self) -> Frame: ...
    def request_stop(self) -> None: ...
    def close(self) -> None: ...
    def describe(self) -> ProviderInfo: ...


class UsbCameraProvider:
    def __init__(
        self,
        device_index: int = 0,
        width: int = DEFAULT_PROVIDER_WIDTH,
        height: int = DEFAULT_PROVIDER_HEIGHT,
        fps: int = DEFAULT_PROVIDER_FPS,
        backend: str = "msmf",
    ) -> None:
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self.backend = backend
        self._cap: object | None = None
        self._stop_requested = threading.Event()
        self._opener = NativeUsbCaptureOpener(width, height, fps)
        self._reader = NativeUsbFrameReader(width, height)

    @staticmethod
    def list_devices(max_probe: int = 8) -> list[ProviderInfo]:
        return [provider_info_from_native(item) for item in _list_usb_sources(max_probe=max_probe)]

    def open(self) -> None:
        self._stop_requested.clear()
        self._reader.clear_stop()
        self._cap = self._opener.open(self.device_index, self.backend)

    def request_stop(self) -> None:
        self._stop_requested.set()
        self._reader.request_stop()

    def read(self) -> Frame:
        return self._reader.read(self._cap)

    def close(self) -> None:
        self._stop_requested.set()
        self._reader.request_stop()
        if self._cap is not None:
            close = getattr(self._cap, "close", None)
            if callable(close):
                close()
            else:
                self._cap.release()
            self._cap = None

    def describe(self) -> ProviderInfo:
        return describe_source_id(
            f"usb:{self.device_index}",
            width=self.width,
            height=self.height,
            fps=self.fps,
        )


class TestPatternProvider:
    def __init__(
        self,
        width: int = DEFAULT_PROVIDER_WIDTH,
        height: int = DEFAULT_PROVIDER_HEIGHT,
        fps: int = DEFAULT_PROVIDER_FPS,
        pattern: Pattern = Pattern.COLORBAR,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.pattern = pattern
        self._native = NativeTestPatternProvider(width, height, fps, pattern.value)

    def open(self) -> None:
        self._native.open()

    def read(self) -> Frame:
        frame = self._native.read()
        frame.flags = FLAG_PLACEHOLDER
        return frame

    def request_stop(self) -> None:
        self._native.request_stop()

    def close(self) -> None:
        self._native.close()

    def describe(self) -> ProviderInfo:
        return describe_source_id(
            f"test:{self.pattern.value}",
            width=self.width,
            height=self.height,
            fps=self.fps,
        )


def create_provider_from_source_id(
    source_id: str,
    *,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> FrameProvider:
    parsed = dict(parse_source_id(source_id))
    if parsed.get("kind") == "usb":
        device_index = int(parsed.get("device_index") or 0)
        return UsbCameraProvider(device_index=device_index, width=width, height=height, fps=fps)

    pattern_id = str(parsed.get("pattern_id") or "colorbar")
    return TestPatternProvider(
        width=width,
        height=height,
        fps=fps,
        pattern=Pattern.from_id(pattern_id),
    )


__all__ = [
    "FrameProvider",
    "Pattern",
    "PATTERN_NAMES",
    "ProviderInfo",
    "TestPatternProvider",
    "UsbCameraProvider",
    "create_provider_from_source_id",
]
