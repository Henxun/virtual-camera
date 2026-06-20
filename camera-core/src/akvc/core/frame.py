# SPDX-License-Identifier: Apache-2.0
"""Frame data class and FourCC constants.

The on-wire schema is defined in `virtualcam/shared/akvc_protocol.h`.
Do not change values here without also changing the C header.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


class FourCC:
    """FourCC constants — kept in sync with akvc_protocol.h."""

    NV12 = 0x3231564E   # b'NV12' little-endian
    YUY2 = 0x32595559   # b'YUY2'
    RGB24 = 0x20424752  # b'RGB '
    MJPG = 0x47504A4D   # b'MJPG'

    _NAMES = {
        NV12: "NV12",
        YUY2: "YUY2",
        RGB24: "RGB24",
        MJPG: "MJPG",
    }

    @classmethod
    def name(cls, fourcc: int) -> str:
        return cls._NAMES.get(fourcc, f"0x{fourcc:08X}")


# Frame flags — keep in sync with akvc_protocol.h.
FLAG_NONE = 0
FLAG_KEYFRAME = 1
FLAG_DISCONTINUITY = 2
FLAG_PLACEHOLDER = 4
FLAG_STALE = 8
FLAG_ERROR = 16


@dataclass
class Frame:
    """In-memory frame.

    `data` carries the pixel bytes in the layout implied by `fourcc`:
      - NV12: contiguous Y plane (height * stride[0]) followed by interleaved
              UV plane (height/2 * stride[1]).
      - YUY2: packed YUYV, height * stride[0] bytes.
      - RGB24: packed BGR (OpenCV default) when produced by OpenCV.
    """

    width: int
    height: int
    fourcc: int
    data: np.ndarray
    pts_100ns: int = 0
    seq: int = 0
    flags: int = FLAG_NONE
    stride: tuple[int, int] = (0, 0)
    plane_size: tuple[int, int] = (0, 0)
    meta: dict = field(default_factory=dict)

    @staticmethod
    def now_pts_100ns() -> int:
        # 100ns ticks since Unix epoch; matches GetSystemTimePreciseAsFileTime
        # (offset by 11644473600 seconds, but we only need monotonicity at
        # consumer side, so we keep a simple time.perf_counter_ns()/100 base).
        return time.perf_counter_ns() // 100

    @classmethod
    def make_nv12(
        cls,
        y_plane: np.ndarray,
        uv_plane: np.ndarray,
        *,
        pts_100ns: Optional[int] = None,
        seq: int = 0,
        flags: int = FLAG_NONE,
    ) -> "Frame":
        if y_plane.ndim != 2 or uv_plane.ndim != 2:
            raise ValueError("NV12 planes must be 2-D")
        h, w = y_plane.shape
        # Combine into one contiguous buffer (Y || UV).
        data = np.empty(y_plane.nbytes + uv_plane.nbytes, dtype=np.uint8)
        data[: y_plane.nbytes] = y_plane.reshape(-1)
        data[y_plane.nbytes :] = uv_plane.reshape(-1)
        return cls(
            width=w,
            height=h,
            fourcc=FourCC.NV12,
            data=data,
            pts_100ns=pts_100ns if pts_100ns is not None else cls.now_pts_100ns(),
            seq=seq,
            flags=flags,
            stride=(w, w),
            plane_size=(y_plane.nbytes, uv_plane.nbytes),
        )

    @classmethod
    def from_bgr(
        cls,
        bgr: np.ndarray,
        *,
        pts_100ns: Optional[int] = None,
        seq: int = 0,
        flags: int = FLAG_NONE,
    ) -> "Frame":
        """Wrap a BGR OpenCV image as a (Phase 2 placeholder) Frame.

        The wire fourcc is RGB24 with packed BGR; the pipeline's
        ColorConvertStage is expected to convert to NV12 before publishing.
        """
        if bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("BGR frame must be HxWx3")
        h, w = bgr.shape[:2]
        return cls(
            width=w,
            height=h,
            fourcc=FourCC.RGB24,
            data=np.ascontiguousarray(bgr).reshape(-1),
            pts_100ns=pts_100ns if pts_100ns is not None else cls.now_pts_100ns(),
            seq=seq,
            flags=flags,
            stride=(w * 3, 0),
            plane_size=(w * h * 3, 0),
        )
