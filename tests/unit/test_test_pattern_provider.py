# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import numpy as np

from apps.desktop.akvc_app.services.source_info import PATTERN_NAMES, Pattern
from apps.desktop.akvc_app.workers.source_provider import TestPatternProvider

# 'RGB ' FourCC (little-endian), as produced by describe_source_id.
FOURCC_RGB24 = 0x20424752


def test_pattern_from_id_falls_back_to_colorbar() -> None:
    assert Pattern.from_id("unknown") is Pattern.COLORBAR


def test_describe_preserves_provider_contract() -> None:
    provider = TestPatternProvider(width=320, height=240, fps=15, pattern=Pattern.MOVING_BOX)

    info = provider.describe()

    assert info.id == "test:moving_box"
    assert info.name == PATTERN_NAMES[Pattern.MOVING_BOX]
    assert len(info.formats) == 1
    assert info.formats[0].fourcc == FOURCC_RGB24
    assert info.formats[0].width == 320
    assert info.formats[0].height == 240
    assert info.formats[0].fps_num == 15
    assert info.formats[0].fps_den == 1


def test_read_returns_contiguous_bgr24_frame() -> None:
    provider = TestPatternProvider(width=64, height=48, fps=30, pattern=Pattern.COLORBAR)

    frame = provider.read()

    assert isinstance(frame, np.ndarray)
    assert frame.shape == (48, 64, 3)
    assert frame.dtype == np.uint8
    assert frame.flags["C_CONTIGUOUS"]


def test_noise_pattern_changes_between_frames() -> None:
    provider = TestPatternProvider(width=32, height=24, fps=30, pattern=Pattern.NOISE)

    frame1 = provider.read()
    frame2 = provider.read()

    assert not np.array_equal(frame1, frame2)


def test_moving_box_pattern_changes_between_frames() -> None:
    provider = TestPatternProvider(width=96, height=72, fps=30, pattern=Pattern.MOVING_BOX)

    frame1 = provider.read()
    frame2 = provider.read()

    assert not np.array_equal(frame1, frame2)


def test_request_stop_does_not_crash_read() -> None:
    # The new provider does not short-circuit read() on stop; the runtime host
    # loop checks the stop flag between reads. read() must still return a valid
    # frame after request_stop() so the loop can drain cleanly.
    provider = TestPatternProvider(width=32, height=24, fps=30, pattern=Pattern.SOLID)

    provider.request_stop()
    frame = provider.read()

    assert isinstance(frame, np.ndarray)
    assert frame.shape == (24, 32, 3)
