# SPDX-License-Identifier: Apache-2.0
"""FPS regulator — token-bucket pacer.

Phase 2 implementation is conservative: it sleeps to throttle a fast source
down to `target_fps`. Bursts up to one frame are tolerated.
"""

from __future__ import annotations

import time

from ..frame import Frame
from .pipeline import PipelineStage


class FpsRegulator(PipelineStage):
    def __init__(self, target_fps: float, *, jitter_pct: float = 10.0) -> None:
        self.target_fps = float(target_fps)
        self._period = 1.0 / self.target_fps
        self._jitter = jitter_pct / 100.0
        self._last_t: float | None = None

    @property
    def name(self) -> str:
        return "fps_regulator"

    def reconfigure(self, cfg: dict) -> None:
        if "target_fps" in cfg:
            self.target_fps = float(cfg["target_fps"])
            self._period = 1.0 / self.target_fps

    def process(self, frame: Frame) -> Frame:
        now = time.perf_counter()
        if self._last_t is None:
            self._last_t = now
            return frame
        elapsed = now - self._last_t
        target = self._period * (1.0 - self._jitter)
        if elapsed < target:
            time.sleep(target - elapsed)
            now = time.perf_counter()
        self._last_t = now
        return frame
