# SPDX-License-Identifier: Apache-2.0
"""USB camera provider via OpenCV."""

from __future__ import annotations

import threading

import cv2

from akvc._core_native import (
    NativeUsbCaptureOpener,
    NativeUsbDeviceProber,
    NativeUsbFrameReader,
)

from .base import FormatSpec, FrameProvider, ProviderInfo


_DEVICE_PROBER = NativeUsbDeviceProber()


class UsbCameraProvider(FrameProvider):
    """OpenCV VideoCapture backed by MSMF (default) or DSHOW (fallback)."""

    def __init__(
        self,
        device_index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        backend: str = "msmf",  # "msmf" | "dshow" | "any"
    ) -> None:
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self.backend = backend
        self._cap: cv2.VideoCapture | None = None
        self._stop_requested = threading.Event()
        self._opener = NativeUsbCaptureOpener(width, height, fps)
        self._reader = NativeUsbFrameReader(width, height)

    @staticmethod
    def list_devices(max_probe: int = 8) -> list[ProviderInfo]:
        """Probe up to `max_probe` indices and return those that open.

        Avoid this on production paths — it spins the camera HW briefly.
        """
        return [
            ProviderInfo(id=f"usb:{i}", name=f"USB Camera {i}", formats=())
            for i in _DEVICE_PROBER.list_indices(max_probe, cv2, cv2.VideoCapture)
        ]

    def open(self) -> None:
        self._stop_requested.clear()
        self._reader.clear_stop()
        self._cap = self._opener.open(self.device_index, self.backend, cv2, cv2.VideoCapture)

    def request_stop(self) -> None:
        self._stop_requested.set()
        self._reader.request_stop()

    def read(self):
        return self._reader.read(self._cap)

    def close(self) -> None:
        self._stop_requested.set()
        self._reader.request_stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def describe(self) -> ProviderInfo:
        from ..frame import FourCC

        return ProviderInfo(
            id=f"usb:{self.device_index}",
            name=f"USB Camera {self.device_index}",
            formats=(FormatSpec(FourCC.RGB24, self.width, self.height, self.fps),),
        )

