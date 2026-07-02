# SPDX-License-Identifier: Apache-2.0
"""High-level virtual camera wrapper for external apps."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from akvc._core_native import NativeVirtualCameraSession


class VirtualCamera:
    """Push BGR frames into the system virtual camera."""

    def __init__(
        self,
        *,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
        helper_exe: str | Path | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self._session = NativeVirtualCameraSession(width, height, fps, "" if helper_exe is None else str(helper_exe))

    @property
    def started(self) -> bool:
        return self._session.started

    @property
    def consumer_count(self) -> int:
        return self._session.consumer_count

    def start(self, name: str = "AK Virtual Camera") -> None:
        self._session.start(name)

    def push_frame(self, bgr: np.ndarray):
        return self._session.push_frame(bgr)

    def stop(self) -> None:
        self._session.stop()

    def close(self) -> None:
        self._session.close()

    def shutdown(self) -> None:
        self.close()

    def __enter__(self) -> "VirtualCamera":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
