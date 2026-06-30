# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import struct

from akvc._core_native import NativeFrameBusProtocol
from akvc.core.frame_sink import _protocol as protocol


def test_protocol_constants_are_native_backed() -> None:
    assert protocol.AKVC_MAGIC == NativeFrameBusProtocol["AKVC_MAGIC"]
    assert protocol.AKVC_SCHEMA_VERSION == NativeFrameBusProtocol["AKVC_SCHEMA_VERSION"]
    assert protocol.AKVC_RING_SLOTS == NativeFrameBusProtocol["AKVC_RING_SLOTS"]
    assert protocol.AKVC_DEFAULT_SLOT_SIZE == NativeFrameBusProtocol["AKVC_DEFAULT_SLOT_SIZE"]
    assert protocol.RING_CONTROL_SIZE == NativeFrameBusProtocol["RING_CONTROL_SIZE"]
    assert protocol.FRAME_HEADER_SIZE == NativeFrameBusProtocol["FRAME_HEADER_SIZE"]
    assert protocol.REGION_SIZE == NativeFrameBusProtocol["REGION_SIZE"]


def test_protocol_offsets_are_native_backed() -> None:
    assert protocol.OFF_PRODUCER_SEQ == NativeFrameBusProtocol["OFF_PRODUCER_SEQ"]
    assert protocol.OFF_WRITER_PID == NativeFrameBusProtocol["OFF_WRITER_PID"]
    assert protocol.OFF_PRODUCER_HEARTBEAT == NativeFrameBusProtocol["OFF_PRODUCER_HEARTBEAT"]
    assert protocol.FRAME_HEADER_OFF_SEQ_HEAD == NativeFrameBusProtocol["FRAME_HEADER_OFF_SEQ_HEAD"]
    assert protocol.FRAME_HEADER_OFF_SEQ_TAIL == NativeFrameBusProtocol["FRAME_HEADER_OFF_SEQ_TAIL"]


def test_protocol_format_strings_remain_python_pack_compatible() -> None:
    assert struct.calcsize(protocol.RING_CONTROL_FMT) == protocol.RING_CONTROL_SIZE
    assert struct.calcsize(protocol.FRAME_HEADER_FMT) == protocol.FRAME_HEADER_SIZE
