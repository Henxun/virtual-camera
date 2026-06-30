# SPDX-License-Identifier: Apache-2.0
"""Shared Frame Bus protocol constants for the Python sinks.

Single source of truth for the on-wire schema defined in
`virtualcam/shared/akvc_protocol.h`. Both `windows_shm.py` and
`macos_shm.py` import from here so the two platforms cannot drift.

Keep these values byte-for-byte identical to the C header. Changing one
without the other breaks the consumer (DShow filter / Camera Extension).
"""

from __future__ import annotations

from akvc._core_native import NativeFrameBusProtocol

# ---------- Protocol constants (mirror akvc_protocol.h) ----------

AKVC_MAGIC = int(NativeFrameBusProtocol["AKVC_MAGIC"])
AKVC_SCHEMA_VERSION = int(NativeFrameBusProtocol["AKVC_SCHEMA_VERSION"])
AKVC_RING_SLOTS = int(NativeFrameBusProtocol["AKVC_RING_SLOTS"])
AKVC_DEFAULT_SLOT_SIZE = int(NativeFrameBusProtocol["AKVC_DEFAULT_SLOT_SIZE"])

# RingControl: 128 bytes
# magic(4) schema(4) slot_count(4) slot_size(4) producer_seq(8)
# writer_pid(4) consumer_count(4) created_pts_100ns(8)
# producer_heartbeat(8) helper_pid(4) helper_reserved(4) pad(72)
RING_CONTROL_FMT = "<IIII Q II Q Q II 72s"
RING_CONTROL_SIZE = int(NativeFrameBusProtocol["RING_CONTROL_SIZE"])

# FrameHeader: 80 bytes per akvc_protocol.h (packed, dense under '<')
# magic, schema, fourcc, w, h, stride[2], plane_offset[2], plane_size[2],
# flags, pts_100ns, seq_head, seq_tail, reserved[2]
FRAME_HEADER_FMT = "<I I I I I II II II I Q Q Q II"
FRAME_HEADER_SIZE = int(NativeFrameBusProtocol["FRAME_HEADER_SIZE"])

REGION_SIZE = int(NativeFrameBusProtocol["REGION_SIZE"])

# Field offsets within the RingControl block (for partial in-place updates).
OFF_PRODUCER_SEQ = int(NativeFrameBusProtocol["OFF_PRODUCER_SEQ"])
OFF_WRITER_PID = int(NativeFrameBusProtocol["OFF_WRITER_PID"])
OFF_PRODUCER_HEARTBEAT = int(NativeFrameBusProtocol["OFF_PRODUCER_HEARTBEAT"])

# seq fields within a FrameHeader (dense '<' layout):
# flags at 44, pts_100ns at 48, seq_head at 56, seq_tail at 64.
FRAME_HEADER_OFF_SEQ_HEAD = int(NativeFrameBusProtocol["FRAME_HEADER_OFF_SEQ_HEAD"])
FRAME_HEADER_OFF_SEQ_TAIL = int(NativeFrameBusProtocol["FRAME_HEADER_OFF_SEQ_TAIL"])
