# SPDX-License-Identifier: Apache-2.0
"""FPS regulator — native-backed token-bucket pacer."""

from __future__ import annotations

from akvc._core_native import NativeFpsRegulator

from ..frame import Frame
from .pipeline import PipelineStage


class FpsRegulator(PipelineStage):
    def __init__(self, target_fps: float, *, jitter_pct: float = 10.0) -> None:
        self.target_fps = float(target_fps)
        self._native = NativeFpsRegulator(self.target_fps, jitter_pct)

    @property
    def name(self) -> str:
        return "fps_regulator"

    def reconfigure(self, cfg: dict) -> None:
        self._native.reconfigure(cfg)
        if "target_fps" in cfg:
            self.target_fps = float(cfg["target_fps"])

    def process(self, frame: Frame) -> Frame:
        return self._native.process(frame)
