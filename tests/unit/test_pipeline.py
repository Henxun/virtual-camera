# SPDX-License-Identifier: Apache-2.0
"""Pipeline tests."""

from __future__ import annotations

import numpy as np

from akvc.core.frame import FourCC, Frame
from akvc.core.frame_pipeline import (
    ColorConvertStage,
    FpsRegulator,
    FramePipeline,
    ResizeStage,
)


def _bgr_frame(w: int, h: int) -> Frame:
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[..., 1] = 200  # green
    return Frame.from_bgr(bgr)


def test_pipeline_resize_then_nv12() -> None:
    f = _bgr_frame(1920, 1080)
    pipe = (
        FramePipeline()
        .add(ResizeStage(target_w=1280, target_h=720))
        .add(ColorConvertStage(dst="NV12"))
    )
    out = pipe.process(f)
    assert out.fourcc == FourCC.NV12
    assert out.width == 1280 and out.height == 720
    # Y plane is 1280*720, UV plane is 1280*720/2.
    assert out.plane_size == (1280 * 720, 1280 * 720 // 2)


def test_fps_regulator_does_not_starve() -> None:
    """Regulator should not introduce more than ~2x the period of latency
    on a single frame measurement."""
    import time

    reg = FpsRegulator(target_fps=120.0)
    f = _bgr_frame(64, 64)
    # Prime
    reg.process(f)
    t0 = time.perf_counter()
    reg.process(f)
    dt = time.perf_counter() - t0
    # Period for 120fps = 8.3ms; allow up to 25ms on slow CI runners.
    assert dt < 0.025, f"regulator slept too long: {dt:.3f}s"
