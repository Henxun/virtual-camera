# SPDX-License-Identifier: Apache-2.0
"""Color conversion stage — BGR → NV12 (BT.601 limited) using OpenCV.

Phase 2 uses OpenCV `cvtColor(...COLOR_BGR2YUV_I420)` and re-packs I420 → NV12
because OpenCV does not expose direct BGR → NV12 in all builds.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..frame import Frame, FourCC
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
        if frame.fourcc == FourCC.NV12:
            return frame
        if frame.fourcc != FourCC.RGB24:
            # YUY2 → NV12 not supported in Phase 2; pass through.
            return frame

        bgr = frame.data.reshape(frame.height, frame.width, 3)

        # I420 has Y (h*w), U (h/2 * w/2), V (h/2 * w/2) — total = h * w * 3/2.
        i420 = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)
        h, w = frame.height, frame.width
        y = i420[:h, :].copy()
        u = i420[h : h + h // 4].reshape(h // 2, w // 2)
        v = i420[h + h // 4 : h + h // 2].reshape(h // 2, w // 2)

        # Interleave U and V into NV12 UV plane.
        uv = np.empty((h // 2, w), dtype=np.uint8)
        uv[:, 0::2] = u
        uv[:, 1::2] = v

        return Frame.make_nv12(
            y, uv, pts_100ns=frame.pts_100ns, seq=frame.seq, flags=frame.flags
        )
