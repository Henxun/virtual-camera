# SPDX-License-Identifier: Apache-2.0
"""Native-backed frame compatibility layer."""

from __future__ import annotations

from akvc._core_native import (
    FLAG_DISCONTINUITY,
    FLAG_ERROR,
    FLAG_KEYFRAME,
    FLAG_NONE,
    FLAG_PLACEHOLDER,
    FLAG_STALE,
    FOURCC_MJPG,
    FOURCC_NV12,
    FOURCC_RGB24,
    FOURCC_YUY2,
    Frame,
    fourcc_name,
)


class FourCC:
    NV12 = FOURCC_NV12
    YUY2 = FOURCC_YUY2
    RGB24 = FOURCC_RGB24
    MJPG = FOURCC_MJPG

    _NAMES = {
        NV12: "NV12",
        YUY2: "YUY2",
        RGB24: "RGB24",
        MJPG: "MJPG",
    }

    @classmethod
    def name(cls, fourcc: int) -> str:
        return fourcc_name(fourcc)


__all__ = [
    "FLAG_NONE",
    "FLAG_KEYFRAME",
    "FLAG_DISCONTINUITY",
    "FLAG_PLACEHOLDER",
    "FLAG_STALE",
    "FLAG_ERROR",
    "FourCC",
    "Frame",
]
