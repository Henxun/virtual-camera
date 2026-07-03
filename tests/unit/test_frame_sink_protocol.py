# SPDX-License-Identifier: Apache-2.0
"""Shared frame-bus protocol tests."""

from __future__ import annotations

import pytest

from akvc.core.errors import FrameBusSchemaMismatch
from akvc.core.frame import FourCC
from akvc.core.frame_sink._protocol import (
    AKVC_DEFAULT_SLOT_SIZE,
    AKVC_MAGIC,
    AKVC_POSIX_SHM_NAME,
    AKVC_RING_SLOTS,
    AKVC_SCHEMA_VERSION,
    FRAME_HEADER_SIZE,
    REGION_SIZE,
    RING_CONTROL_SIZE,
    FrameHeader,
    RingControl,
    expected_region_size,
    pack_frame_header,
    pack_ring_control,
    slot_index_for_seq,
    slot_offset_for_index,
    unpack_frame_header,
    unpack_ring_control,
    validate_frame_header,
    validate_ring_control,
)


def test_ring_control_round_trip_and_validation() -> None:
    ctrl = RingControl(
        producer_seq=17,
        writer_pid=1001,
        consumer_count=2,
        created_pts_100ns=123456,
        producer_heartbeat=234567,
        helper_pid=999,
    )

    raw = pack_ring_control(ctrl)
    decoded = unpack_ring_control(raw)

    assert len(raw) == RING_CONTROL_SIZE
    assert decoded == ctrl
    validate_ring_control(decoded)
    assert decoded.region_size == REGION_SIZE


def test_frame_header_round_trip_and_validation() -> None:
    header = FrameHeader(
        fourcc=FourCC.NV12,
        width=1920,
        height=1080,
        stride0=1920,
        stride1=1920,
        plane_offset0=FRAME_HEADER_SIZE,
        plane_offset1=FRAME_HEADER_SIZE + (1920 * 1080),
        plane_size0=1920 * 1080,
        plane_size1=(1920 * 1080) // 2,
        flags=0,
        pts_100ns=987654321,
        seq_head=42,
        seq_tail=42,
    )

    raw = pack_frame_header(header)
    decoded = unpack_frame_header(raw)

    assert len(raw) == FRAME_HEADER_SIZE
    assert decoded == header
    assert decoded.is_finalized is True
    validate_frame_header(decoded)


def test_validate_ring_control_rejects_schema_mismatch() -> None:
    ctrl = RingControl(schema_version=AKVC_SCHEMA_VERSION + 1)

    with pytest.raises(FrameBusSchemaMismatch):
        validate_ring_control(ctrl)


def test_validate_frame_header_rejects_inflight_frame_by_default() -> None:
    header = FrameHeader(
        fourcc=FourCC.NV12,
        width=1280,
        height=720,
        stride0=1280,
        stride1=1280,
        plane_offset0=FRAME_HEADER_SIZE,
        plane_offset1=FRAME_HEADER_SIZE + (1280 * 720),
        plane_size0=1280 * 720,
        plane_size1=(1280 * 720) // 2,
        seq_head=7,
        seq_tail=0,
    )

    with pytest.raises(FrameBusSchemaMismatch):
        validate_frame_header(header)

    validate_frame_header(header, allow_inflight=True)


def test_region_helpers_match_schema() -> None:
    assert expected_region_size() == REGION_SIZE
    assert slot_index_for_seq(1) == 0
    assert slot_index_for_seq(AKVC_RING_SLOTS) == AKVC_RING_SLOTS - 1
    assert slot_index_for_seq(AKVC_RING_SLOTS + 1) == 0
    assert slot_offset_for_index(0) == RING_CONTROL_SIZE
    assert slot_offset_for_index(1) == RING_CONTROL_SIZE + AKVC_DEFAULT_SLOT_SIZE
    assert AKVC_POSIX_SHM_NAME == "/akvc-frames-v1"
    assert AKVC_MAGIC == 0x43564B41
