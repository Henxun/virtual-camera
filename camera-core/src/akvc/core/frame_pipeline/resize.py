# SPDX-License-Identifier: Apache-2.0
"""Resize stage — native-backed RGB24 resize."""

from __future__ import annotations

from akvc._core_native import resize_rgb24_frame

from ..frame import Frame
from .pipeline import PipelineStage


class ResizeStage(PipelineStage):
    def __init__(self, target_w: int, target_h: int) -> None:
        self.target_w = target_w
        self.target_h = target_h

    @property
    def name(self) -> str:
        return "resize"

    def process(self, frame: Frame) -> Frame:
        return resize_rgb24_frame(frame, self.target_w, self.target_h)
