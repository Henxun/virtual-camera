# SPDX-License-Identifier: Apache-2.0
"""Frame data class tests."""

from __future__ import annotations

import numpy as np

from akvc._core_native import FLAG_NONE, FOURCC_NV12, FOURCC_RGB24, FOURCC_YUY2, Frame, fourcc_name


class FourCC:
    NV12 = FOURCC_NV12
    YUY2 = FOURCC_YUY2
    RGB24 = FOURCC_RGB24

    @classmethod
    def name(cls, fourcc: int) -> str:
        return fourcc_name(fourcc)


def test_make_nv12_round_trip() -> None:
    h, w = 480, 640
    y = np.full((h, w), 64, dtype=np.uint8)
    uv = np.full((h // 2, w), 128, dtype=np.uint8)
    f = Frame.make_nv12(y, uv)
    assert f.fourcc == FourCC.NV12
    assert f.width == w and f.height == h
    assert f.plane_size == (h * w, h * w // 2)
    assert f.data.dtype == np.uint8
    assert f.data.size == h * w + (h * w // 2)
    assert f.data[:5].tolist() == [64, 64, 64, 64, 64]
    assert f.data[h * w : h * w + 5].tolist() == [128, 128, 128, 128, 128]


def test_from_bgr_basic() -> None:
    bgr = np.zeros((360, 640, 3), dtype=np.uint8)
    bgr[..., 0] = 1
    bgr[..., 1] = 2
    bgr[..., 2] = 3
    f = Frame.from_bgr(bgr)
    assert f.fourcc == FourCC.RGB24
    assert f.flags == FLAG_NONE
    assert f.data.size == 360 * 640 * 3


def test_fourcc_names() -> None:
    assert FourCC.name(FourCC.NV12) == "NV12"
    assert FourCC.name(FourCC.YUY2) == "YUY2"
    assert FourCC.name(FourCC.RGB24) == "RGB24"
    assert FourCC.name(0xDEADBEEF) == "0xDEADBEEF"
