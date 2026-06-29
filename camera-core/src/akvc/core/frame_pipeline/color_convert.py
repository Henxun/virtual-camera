# SPDX-License-Identifier: Apache-2.0
"""Color conversion stage — native-backed BGR → NV12."""

from __future__ import annotations

from akvc._core_native import rgb24_to_nv12_frame

from ..frame import Frame
from .pipeline import PipelineStage


class ColorConvertStage(PipelineStage):
    def __init__(self, dst: str = "NV12") -> None:
        if dst != "NV12":
            raise ValueError(f"Phase 2 supports NV12 only, got {dst!r}")
        self.dst = dst

    @property
    def name(self) -> str:
        return "color_convert"

    def process(self, frame: Frame) -> Frame:
        return rgb24_to_nv12_frame(frame)
