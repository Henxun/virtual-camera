# SPDX-License-Identifier: Apache-2.0
"""Pure-Python frame providers for the desktop worker path.

Replaces the former akvc._core_native-backed providers. Test patterns are
generated with numpy; USB cameras are read via cv2.VideoCapture. read() returns
a contiguous uint8 BGR24 HxWx3 numpy array ready for akvc_camera.push_frame.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

import numpy as np

from ..services.source_info import (
    DEFAULT_PROVIDER_FPS,
    DEFAULT_PROVIDER_HEIGHT,
    DEFAULT_PROVIDER_WIDTH,
    PATTERN_NAMES,
    Pattern,
    ProviderInfo,
    describe_source_id,
    parse_source_id,
)


class FrameProvider(Protocol):
    def open(self) -> None: ...
    def read(self) -> np.ndarray: ...
    def request_stop(self) -> None: ...
    def close(self) -> None: ...
    def describe(self) -> ProviderInfo: ...


class TestPatternProvider:
    __test__ = False  # not a pytest test class

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
        self._stop = threading.Event()
        self._frame_index = 0

    def open(self) -> None:
        self._stop.clear()
        self._frame_index = 0

    def request_stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self._stop.set()

    def read(self) -> np.ndarray:
        # Regulate to target fps so test patterns don't spin as fast as possible.
        target_dt = 1.0 / max(1, self.fps)
        time.sleep(max(0.0, target_dt - 0.001))
        idx = self._frame_index
        self._frame_index += 1
        return _render_test_pattern(self.pattern, self.width, self.height, idx)

    def describe(self) -> ProviderInfo:
        return describe_source_id(
            f"test:{self.pattern.value}",
            width=self.width,
            height=self.height,
            fps=self.fps,
        )


class UsbCameraProvider:
    __test__ = False  # not a pytest test class

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
        self._stop = threading.Event()

    @staticmethod
    def list_devices(max_probe: int = 8) -> list[ProviderInfo]:
        from ..services.source_info import list_usb_sources
        return list_usb_sources(max_probe=max_probe)

    def open(self) -> None:
        import cv2  # type: ignore
        self._stop.clear()
        backend = cv2.CAP_MSMF if self.backend == "msmf" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.device_index, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._cap = cap

    def request_stop(self) -> None:
        self._stop.set()

    def read(self) -> np.ndarray:
        import cv2  # type: ignore
        if self._cap is None:
            raise RuntimeError("USB provider not opened")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            # Return a black frame on read failure so the pipeline keeps flowing.
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)
        if frame.shape[:2] != (self.height, self.width):
            frame = cv2.resize(frame, (self.width, self.height))
        return np.ascontiguousarray(frame[:, :, :3])

    def close(self) -> None:
        self._stop.set()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def describe(self) -> ProviderInfo:
        return describe_source_id(
            f"usb:{self.device_index}",
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
    parsed = parse_source_id(source_id)
    if parsed.get("kind") == "usb":
        return UsbCameraProvider(
            device_index=int(parsed.get("device_index") or 0),
            width=width, height=height, fps=fps,
        )
    return TestPatternProvider(
        width=width, height=height, fps=fps,
        pattern=Pattern.from_id(str(parsed.get("pattern_id") or "colorbar")),
    )


# ---- test pattern rendering (numpy) ----

def _render_test_pattern(pattern: Pattern, w: int, h: int, idx: int) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    if pattern == Pattern.SOLID:
        frame[:] = (0, 0, 200)  # solid red (BGR)
        return frame
    if pattern == Pattern.NOISE:
        rng = np.random.default_rng()
        frame[:] = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
        return frame
    if pattern == Pattern.GRADIENT:
        xs = np.arange(w, dtype=np.int32)
        ys = np.arange(h, dtype=np.int32)
        frame[:, :, 0] = (xs * 255 // max(w - 1, 1))[None, :]
        frame[:, :, 1] = (ys * 255 // max(h - 1, 1))[:, None]
        frame[:, :, 2] = ((xs[None, :] + ys[:, None]) * 255 // (w + h - 2))
        return frame
    if pattern == Pattern.CHECKERBOARD:
        cell = 40
        yy, xx = np.indices((h, w))
        chk = ((xx // cell) + (yy // cell)) % 2
        frame[chk == 1] = (255, 255, 255)
        return frame
    if pattern == Pattern.MOVING_BOX:
        frame[:] = (30, 30, 30)
        box = 80
        x = (idx * 8) % (w - box)
        y = (idx * 4) % (h - box)
        frame[y:y + box, x:x + box] = (0, 200, 0)
        return frame
    # COLORBAR (default): vertical color bars.
    bars = [
        (255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
        (255, 0, 255), (0, 0, 255), (0, 0, 0),
    ]
    bar_w = max(1, w // len(bars))
    for i, color in enumerate(bars):
        x0 = i * bar_w
        x1 = min(w, x0 + bar_w)
        frame[:, x0:x1] = color
    return frame


__all__ = [
    "FrameProvider",
    "Pattern",
    "PATTERN_NAMES",
    "ProviderInfo",
    "TestPatternProvider",
    "UsbCameraProvider",
    "create_provider_from_source_id",
]
