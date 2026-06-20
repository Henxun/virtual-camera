# SPDX-License-Identifier: Apache-2.0
"""Pipeline core."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..frame import Frame

log = logging.getLogger(__name__)


class PipelineStage(ABC):
    """A single transformation step.

    Stages must be deterministic on a per-frame basis and must not block on
    external resources (file I/O, network). Heavy work belongs in dedicated
    worker stages with their own lifecycle.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def process(self, frame: Frame) -> Frame: ...

    def reconfigure(self, cfg: dict) -> None:  # pragma: no cover - default no-op
        return None


class FramePipeline:
    def __init__(self, stages: list[PipelineStage] | None = None) -> None:
        self._stages: list[PipelineStage] = list(stages or [])

    def add(self, stage: PipelineStage) -> "FramePipeline":
        self._stages.append(stage)
        return self

    def remove(self, name: str) -> "FramePipeline":
        self._stages = [s for s in self._stages if s.name != name]
        return self

    @property
    def stages(self) -> list[PipelineStage]:
        return list(self._stages)

    def process(self, frame: Frame) -> Frame:
        cur = frame
        for st in self._stages:
            try:
                cur = st.process(cur)
            except Exception:
                log.exception("pipeline stage %s failed; passing frame through", st.name)
                # Continue with previous frame to satisfy invariant I3.
        return cur
