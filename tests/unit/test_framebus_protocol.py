# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import struct

from akvc._core_native import NativeFrameBusProtocol

RING_CONTROL_FMT = "<IIII Q II Q Q II 72s"
FRAME_HEADER_FMT = "<I I I I I II II II I Q Q Q II"


def test_protocol_constants_are_native_backed() -> None:
    assert int(NativeFrameBusProtocol["AKVC_MAGIC"]) > 0
    assert int(NativeFrameBusProtocol["AKVC_SCHEMA_VERSION"]) > 0
    assert int(NativeFrameBusProtocol["AKVC_RING_SLOTS"]) > 0
    assert int(NativeFrameBusProtocol["AKVC_DEFAULT_SLOT_SIZE"]) > 0
    assert int(NativeFrameBusProtocol["RING_CONTROL_SIZE"]) > 0
    assert int(NativeFrameBusProtocol["FRAME_HEADER_SIZE"]) > 0
    assert int(NativeFrameBusProtocol["REGION_SIZE"]) > 0


def test_protocol_offsets_are_native_backed() -> None:
    assert int(NativeFrameBusProtocol["OFF_PRODUCER_SEQ"]) >= 0
    assert int(NativeFrameBusProtocol["OFF_WRITER_PID"]) >= 0
    assert int(NativeFrameBusProtocol["OFF_PRODUCER_HEARTBEAT"]) >= 0
    assert int(NativeFrameBusProtocol["FRAME_HEADER_OFF_SEQ_HEAD"]) >= 0
    assert int(NativeFrameBusProtocol["FRAME_HEADER_OFF_SEQ_TAIL"]) >= 0


def test_protocol_format_strings_remain_python_pack_compatible() -> None:
    assert struct.calcsize(RING_CONTROL_FMT) == int(NativeFrameBusProtocol["RING_CONTROL_SIZE"])
    assert struct.calcsize(FRAME_HEADER_FMT) == int(NativeFrameBusProtocol["FRAME_HEADER_SIZE"])
