# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import numpy as np

from akvc._core_native import FLAG_PLACEHOLDER, FOURCC_RGB24
from apps.desktop.akvc_app.services.source_info import PATTERN_NAMES, Pattern
from apps.desktop.akvc_app.workers.source_provider import TestPatternProvider


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


def test_read_returns_placeholder_rgb24_frame_with_monotonic_seq() -> None:
    provider = TestPatternProvider(width=64, height=48, fps=30, pattern=Pattern.COLORBAR)

    frame1 = provider.read()
    frame2 = provider.read()

    assert frame1.fourcc == FOURCC_RGB24
    assert frame1.flags == FLAG_PLACEHOLDER
    assert frame1.width == 64
    assert frame1.height == 48
    assert tuple(frame1.stride) == (64 * 3, 0)
    assert tuple(frame1.plane_size) == (64 * 48 * 3, 0)
    assert frame1.seq == 1
    assert frame2.seq == 2


def test_noise_pattern_changes_between_frames() -> None:
    provider = TestPatternProvider(width=32, height=24, fps=30, pattern=Pattern.NOISE)

    frame1 = provider.read()
    frame2 = provider.read()

    assert not np.array_equal(frame1.data, frame2.data)


def test_moving_box_pattern_changes_between_frames() -> None:
    provider = TestPatternProvider(width=96, height=72, fps=30, pattern=Pattern.MOVING_BOX)

    frame1 = provider.read()
    frame2 = provider.read()

    assert not np.array_equal(frame1.data, frame2.data)


def test_request_stop_short_circuits_read() -> None:
    provider = TestPatternProvider(width=32, height=24, fps=30, pattern=Pattern.SOLID)

    provider.request_stop()
    frame = provider.read()

    assert frame.flags == FLAG_PLACEHOLDER
    assert frame.meta["reason"] == "stop requested"


