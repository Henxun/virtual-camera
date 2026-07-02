# SPDX-License-Identifier: Apache-2.0
"""Pipeline primitive tests."""

from __future__ import annotations

import time

import numpy as np

from akvc._core_native import FOURCC_NV12, Frame, NativeFpsRegulator, resize_rgb24_frame, rgb24_to_nv12_frame


def _bgr_frame(w: int, h: int) -> Frame:
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[..., 1] = 200
    return Frame.from_bgr(bgr)


def test_resize_then_nv12() -> None:
    frame = _bgr_frame(1920, 1080)
    frame = resize_rgb24_frame(frame, 1280, 720)
    out = rgb24_to_nv12_frame(frame)
    assert out.fourcc == FOURCC_NV12
    assert out.width == 1280 and out.height == 720
    assert out.plane_size == (1280 * 720, 1280 * 720 // 2)


def test_fps_regulator_does_not_starve() -> None:
    regulator = NativeFpsRegulator(120.0, 10.0)
    frame = _bgr_frame(64, 64)
    regulator.process(frame)
    t0 = time.perf_counter()
    regulator.process(frame)
    dt = time.perf_counter() - t0
    assert dt < 0.025, f"regulator slept too long: {dt:.3f}s"
