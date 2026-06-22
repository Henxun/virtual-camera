# SPDX-License-Identifier: Apache-2.0
"""High-level virtual camera wrapper for external apps."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from akvc.core.frame import Frame
from akvc.core.frame_pipeline import (
    ColorConvertStage,
    FpsRegulator,
    FramePipeline,
    ResizeStage,
)
from akvc.core.frame_sink import FrameSink, create_sink
from akvc.core.helper.client import HelperService


class VirtualCamera:
    """Push BGR frames into the system virtual camera."""

    def __init__(
        self,
        *,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
        helper_exe: str | Path | None = None,
        pipeline: FramePipeline | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self._helper = HelperService(helper_exe=helper_exe)
        self._pipeline = pipeline or (
            FramePipeline()
            .add(ResizeStage(target_w=width, target_h=height))
            .add(FpsRegulator(target_fps=fps))
            .add(ColorConvertStage(dst="NV12"))
        )
        self._sink: Optional[FrameSink] = None
        self._started = False
        self._mf_registered = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def consumer_count(self) -> int:
        if self._sink is None:
            return 0
        return self._sink.consumer_count

    def start(self, name: str = "AK Virtual Camera") -> None:
        if self._started:
            return
        if not self._helper.start():
            raise RuntimeError("failed to start akvc helper")
        if not self._helper.ping():
            raise RuntimeError("akvc helper is not responding")
        if not self._mf_registered:
            if not self._helper.register_mf(name=name):
                raise RuntimeError("failed to register MF virtual camera")
            self._mf_registered = True
        sink = create_sink()
        sink.open()
        self._sink = sink
        self._started = True

    def push_frame(self, bgr: np.ndarray) -> None:
        if not self._started or self._sink is None:
            raise RuntimeError("virtual camera is not started")
        frame = Frame.from_bgr(bgr)
        frame = self._pipeline.process(frame)
        self._sink.publish(frame)

    def stop(self) -> None:
        if not self._started:
            return
        assert self._sink is not None
        self._sink.close()
        self._sink = None
        self._started = False

    def close(self) -> None:
        self.stop()
        self._helper.stop()

    def shutdown(self) -> None:
        self.close()

    def __enter__(self) -> "VirtualCamera":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
