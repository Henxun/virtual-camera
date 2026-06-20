# SPDX-License-Identifier: Apache-2.0
"""Resize stage — uses OpenCV INTER_AREA for downscale, INTER_LINEAR for upscale."""

from __future__ import annotations

import cv2
import numpy as np

from ..frame import Frame, FourCC
from .pipeline import PipelineStage


class ResizeStage(PipelineStage):
    def __init__(self, target_w: int, target_h: int) -> None:
        self.target_w = target_w
        self.target_h = target_h

    @property
    def name(self) -> str:
        return "resize"

    def process(self, frame: Frame) -> Frame:
        if frame.fourcc != FourCC.RGB24:
            # Phase 2: only resize BGR; NV12 resize is done before NV12 conversion.
            return frame
        if frame.width == self.target_w and frame.height == self.target_h:
            return frame

        bgr = frame.data.reshape(frame.height, frame.width, 3)
        interp = (
            cv2.INTER_AREA
            if (self.target_w * self.target_h) < (frame.width * frame.height)
            else cv2.INTER_LINEAR
        )
        out = cv2.resize(bgr, (self.target_w, self.target_h), interpolation=interp)
        return Frame.from_bgr(out, pts_100ns=frame.pts_100ns, seq=frame.seq, flags=frame.flags)
