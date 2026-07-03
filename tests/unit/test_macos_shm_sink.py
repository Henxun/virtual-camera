# SPDX-License-Identifier: Apache-2.0
"""macOS POSIX shared-memory frame sink tests."""

from __future__ import annotations

import numpy as np
import pytest

from akvc.core.errors import FrameBusError
from akvc.core.frame import FLAG_KEYFRAME, Frame, FourCC
from akvc.core.frame_sink import macos_shm
from akvc.core.frame_sink._protocol import (
    AKVC_RING_SLOTS,
    FRAME_HEADER_SIZE,
    REGION_SIZE,
    RingControl,
    slot_offset_for_index,
    unpack_frame_header,
)


class _FakeLibC:
    def __init__(self, pid: int = 4242) -> None:
        self._pid = pid

    def getpid(self) -> int:
        return self._pid


def _make_open_sink(*, producer_seq: int = 0, consumer_count: int = 0) -> macos_shm.MacOsShmSink:
    sink = macos_shm.MacOsShmSink()
    sink._buf = bytearray(REGION_SIZE)
    sink._opened = True
    sink._state.producer_seq = producer_seq
    sink._write_ctrl(
        RingControl(
            producer_seq=producer_seq,
            consumer_count=consumer_count,
        )
    )
    return sink


def test_macos_shm_sink_publish_writes_ring_control_header_and_payload(monkeypatch) -> None:
    monkeypatch.setattr(macos_shm, "_ensure_libc", lambda: _FakeLibC(4242))
    monkeypatch.setattr(macos_shm, "_now_100ns_clock_realtime", lambda: 987654321)

    sink = _make_open_sink(consumer_count=3)
    y_plane = np.arange(8, dtype=np.uint8).reshape(2, 4)
    uv_plane = np.arange(4, dtype=np.uint8).reshape(1, 4) + 50
    frame = Frame.make_nv12(
        y_plane,
        uv_plane,
        pts_100ns=123456789,
        flags=FLAG_KEYFRAME,
    )

    sink.publish(frame)

    ctrl = sink._read_ctrl()
    slot_off = slot_offset_for_index(0)
    header = unpack_frame_header(bytes(sink._buf[slot_off: slot_off + FRAME_HEADER_SIZE]))

    assert sink.consumer_count == 3
    assert ctrl.producer_seq == 1
    assert ctrl.consumer_count == 3
    assert ctrl.writer_pid == 4242
    assert ctrl.producer_heartbeat == 987654321

    assert header.fourcc == FourCC.NV12
    assert header.width == 4
    assert header.height == 2
    assert header.flags == FLAG_KEYFRAME
    assert header.pts_100ns == 123456789
    assert header.seq_head == 1
    assert header.seq_tail == 1
    assert header.plane_offset0 == FRAME_HEADER_SIZE
    assert header.plane_offset1 == FRAME_HEADER_SIZE + y_plane.nbytes
    assert header.plane_size0 == y_plane.nbytes
    assert header.plane_size1 == uv_plane.nbytes

    plane0 = bytes(
        sink._buf[slot_off + header.plane_offset0: slot_off + header.plane_offset0 + header.plane_size0]
    )
    plane1 = bytes(
        sink._buf[slot_off + header.plane_offset1: slot_off + header.plane_offset1 + header.plane_size1]
    )
    assert plane0 == y_plane.tobytes()
    assert plane1 == uv_plane.tobytes()


def test_macos_shm_sink_uses_darwin_create_flags() -> None:
    assert macos_shm._O_CREAT == 0o1000
    assert macos_shm._O_EXCL == 0o4000


def test_macos_shm_sink_accepts_custom_shared_memory_name() -> None:
    sink = macos_shm.MacOsShmSink(shm_name="/akvc-custom")

    assert sink.shared_memory_name == "/akvc-custom"


def test_macos_shm_sink_publish_wraps_ring_slots_and_overwrites_oldest_slot(monkeypatch) -> None:
    monkeypatch.setattr(macos_shm, "_ensure_libc", lambda: _FakeLibC(777))
    monkeypatch.setattr(macos_shm, "_now_100ns_clock_realtime", lambda: 555555555)

    sink = _make_open_sink()
    for index in range(AKVC_RING_SLOTS + 1):
        fill = index + 1
        y_plane = np.full((2, 4), fill, dtype=np.uint8)
        uv_plane = np.full((1, 4), fill + 100, dtype=np.uint8)
        sink.publish(Frame.make_nv12(y_plane, uv_plane, pts_100ns=1000 + fill))

    ctrl = sink._read_ctrl()
    wrapped_slot_off = slot_offset_for_index(0)
    wrapped_header = unpack_frame_header(
        bytes(sink._buf[wrapped_slot_off: wrapped_slot_off + FRAME_HEADER_SIZE])
    )
    untouched_slot_off = slot_offset_for_index(1)
    untouched_header = unpack_frame_header(
        bytes(sink._buf[untouched_slot_off: untouched_slot_off + FRAME_HEADER_SIZE])
    )

    assert ctrl.producer_seq == AKVC_RING_SLOTS + 1
    assert wrapped_header.seq_head == AKVC_RING_SLOTS + 1
    assert wrapped_header.seq_tail == AKVC_RING_SLOTS + 1
    assert untouched_header.seq_head == 2
    assert untouched_header.seq_tail == 2

    wrapped_y = bytes(
        sink._buf[
            wrapped_slot_off + wrapped_header.plane_offset0:
            wrapped_slot_off + wrapped_header.plane_offset0 + wrapped_header.plane_size0
        ]
    )
    wrapped_uv = bytes(
        sink._buf[
            wrapped_slot_off + wrapped_header.plane_offset1:
            wrapped_slot_off + wrapped_header.plane_offset1 + wrapped_header.plane_size1
        ]
    )
    assert wrapped_y == bytes([AKVC_RING_SLOTS + 1]) * 8
    assert wrapped_uv == bytes([AKVC_RING_SLOTS + 101]) * 4


def test_macos_shm_sink_publish_rejects_short_payload_without_advancing_sequence(monkeypatch) -> None:
    monkeypatch.setattr(macos_shm, "_ensure_libc", lambda: _FakeLibC(999))
    monkeypatch.setattr(macos_shm, "_now_100ns_clock_realtime", lambda: 444444444)

    sink = _make_open_sink()
    frame = Frame(
        width=4,
        height=2,
        fourcc=FourCC.NV12,
        data=np.zeros(5, dtype=np.uint8),
        pts_100ns=2468,
        stride=(4, 4),
        plane_size=(8, 4),
    )

    with pytest.raises(FrameBusError) as exc_info:
        sink.publish(frame)

    assert "payload smaller than declared plane sizes" in str(exc_info.value)
    assert sink._read_ctrl().producer_seq == 0
    assert sink._state.producer_seq == 0
