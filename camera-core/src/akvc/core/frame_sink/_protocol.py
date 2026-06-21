# SPDX-License-Identifier: Apache-2.0
"""Shared Frame Bus protocol constants for the Python sinks.

Single source of truth for the on-wire schema defined in
`virtualcam/shared/akvc_protocol.h`. Both `windows_shm.py` and
`macos_shm.py` import from here so the two platforms cannot drift.

Keep these values byte-for-byte identical to the C header. Changing one
without the other breaks the consumer (DShow filter / Camera Extension).
"""

from __future__ import annotations

import struct

# ---------- Protocol constants (mirror akvc_protocol.h) ----------

AKVC_MAGIC = 0x43564B41  # 'AKVC' little-endian
AKVC_SCHEMA_VERSION = 2  # bumped for heartbeat support
AKVC_RING_SLOTS = 4
AKVC_DEFAULT_SLOT_SIZE = 0x00300000  # 3 MiB

# RingControl: 128 bytes
# magic(4) schema(4) slot_count(4) slot_size(4) producer_seq(8)
# writer_pid(4) consumer_count(4) created_pts_100ns(8)
# producer_heartbeat(8) helper_pid(4) helper_reserved(4) pad(72)
RING_CONTROL_FMT = "<IIII Q II Q Q II 72s"
RING_CONTROL_SIZE = struct.calcsize(RING_CONTROL_FMT)  # 128

# FrameHeader: 80 bytes per akvc_protocol.h (packed, dense under '<')
# magic, schema, fourcc, w, h, stride[2], plane_offset[2], plane_size[2],
# flags, pts_100ns, seq_head, seq_tail, reserved[2]
FRAME_HEADER_FMT = "<I I I I I II II II I Q Q Q II"
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER_FMT)  # 80

REGION_SIZE = RING_CONTROL_SIZE + AKVC_RING_SLOTS * AKVC_DEFAULT_SLOT_SIZE

# Field offsets within the RingControl block (for partial in-place updates).
OFF_PRODUCER_SEQ = 16      # uint64
OFF_WRITER_PID = 24        # uint32
OFF_PRODUCER_HEARTBEAT = 40  # uint64

# seq_tail field offset within a FrameHeader (dense '<' layout):
#   11 uint32 (magic..plane_size_uv) = 44; flags(4)=48; pts(8)=56;
#   seq_head(8)=64 ... wait: 44 + flags(4) = 48, pts_100ns(8) at 48? No —
#   under '<' there is no alignment padding, so:
#     44 (after plane_size_uv) + flags(4) = 48
#     + pts_100ns(8) = 56
#     + seq_head(8) = 64
#   → seq_head at 56, seq_tail at 64.
FRAME_HEADER_OFF_SEQ_HEAD = 56
FRAME_HEADER_OFF_SEQ_TAIL = 64
