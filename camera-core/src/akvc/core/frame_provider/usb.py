# SPDX-License-Identifier: Apache-2.0
"""USB camera provider via OpenCV."""

from __future__ import annotations

import time

import cv2
import numpy as np

from ..frame import Frame, FLAG_ERROR
from .base import FormatSpec, FrameProvider, ProviderInfo


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
        self._seq = 0

    @staticmethod
    def list_devices(max_probe: int = 8) -> list[ProviderInfo]:
        """Probe up to `max_probe` indices and return those that open.

        Avoid this on production paths — it spins the camera HW briefly.
        """
        out: list[ProviderInfo] = []
        for i in range(max_probe):
            cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
            ok = cap.isOpened()
            if not ok:
                cap.release()
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                ok = cap.isOpened()
            if ok:
                out.append(
                    ProviderInfo(id=f"usb:{i}", name=f"USB Camera {i}", formats=())
                )
            cap.release()
        return out

    def open(self) -> None:
        backends = {
            "msmf": [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY],
            "dshow": [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY],
            "any": [cv2.CAP_ANY, cv2.CAP_MSMF, cv2.CAP_DSHOW],
        }.get(self.backend, [cv2.CAP_ANY])

        last_err: Exception | None = None
        for be in backends:
            try:
                cap = cv2.VideoCapture(self.device_index, be)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    cap.set(cv2.CAP_PROP_FPS, self.fps)
                    self._cap = cap
                    return
                cap.release()
            except Exception as exc:  # pragma: no cover
                last_err = exc
        raise RuntimeError(
            f"Cannot open USB camera {self.device_index}: {last_err}"
        )

    def read(self) -> Frame:
        cap = self._cap
        if cap is None:
            return self._error_frame("not opened")
        ok, bgr = cap.read()
        if not ok or bgr is None:
            # Soft retry once before giving back an error frame.
            time.sleep(0.005)
            ok, bgr = cap.read()
            if not ok or bgr is None:
                return self._error_frame("read failed")
        self._seq += 1
        return Frame.from_bgr(bgr, seq=self._seq)

    def close(self) -> None:
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

    def _error_frame(self, reason: str) -> Frame:
        bgr = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        return Frame.from_bgr(bgr, seq=self._seq, flags=FLAG_ERROR).__class__(
            **{**Frame.from_bgr(bgr, seq=self._seq, flags=FLAG_ERROR).__dict__,
               "meta": {"reason": reason}}
        )
