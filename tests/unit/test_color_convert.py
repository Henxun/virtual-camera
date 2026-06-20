# SPDX-License-Identifier: Apache-2.0
"""Color-convert stage tests (BGR → NV12)."""

from __future__ import annotations

import numpy as np

from akvc.core.frame import FourCC, Frame
from akvc.core.frame_pipeline import ColorConvertStage


def test_grey_bgr_yields_neutral_chroma() -> None:
    h, w = 240, 320
    grey = np.full((h, w, 3), 128, dtype=np.uint8)
    f = ColorConvertStage(dst="NV12").process(Frame.from_bgr(grey))
    assert f.fourcc == FourCC.NV12

    y_size = h * w
    y = f.data[:y_size]
    uv = f.data[y_size : y_size + h * w // 2]

    # Y for mid-grey BGR is roughly between 110 and 145 depending on conversion
    # matrix (BT.601 limited). Accept a generous window.
    assert 100 <= int(y.mean()) <= 160, f"Y mean = {y.mean()}"

    # Chroma should be approximately neutral (128 ± a few).
    assert 120 <= int(uv.mean()) <= 136, f"UV mean = {uv.mean()}"
