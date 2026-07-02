# SPDX-License-Identifier: Apache-2.0
"""Native color-convert tests (BGR → NV12)."""

from __future__ import annotations

import numpy as np

from akvc._core_native import FOURCC_NV12, Frame, rgb24_to_nv12_frame


def test_grey_bgr_yields_neutral_chroma() -> None:
    h, w = 240, 320
    grey = np.full((h, w, 3), 128, dtype=np.uint8)
    frame = rgb24_to_nv12_frame(Frame.from_bgr(grey))
    assert frame.fourcc == FOURCC_NV12

    y_size = h * w
    y = frame.data[:y_size]
    uv = frame.data[y_size : y_size + h * w // 2]

    assert 100 <= int(y.mean()) <= 160, f"Y mean = {y.mean()}"
    assert 120 <= int(uv.mean()) <= 136, f"UV mean = {uv.mean()}"
