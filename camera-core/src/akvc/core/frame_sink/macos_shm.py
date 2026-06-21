# SPDX-License-Identifier: Apache-2.0
"""macOS POSIX shared-memory frame sink.

The Python *producer* counterpart of the C `framebus_posix.c` consumer
that lives inside the CoreMediaIO Camera Extension
(`virtualcam/macos/framebus`). It writes to a POSIX shared-memory region
(`/akvc-frames-v1`) using the exact same schema as `windows_shm.py`
(see `akvc_protocol.h`).

Differences from the Windows sink:
  * Region backing: `shm_open` + `mmap` (not CreateFileMapping).
  * Permissions: created with mode 0o666 so the Camera Extension process
    (which runs as a separate, sandboxed system-extension process) can
    open it read-only. `multiprocessing.shared_memory.SharedMemory`
    hardcodes 0o600, which would block the extension — hence the direct
    libc calls.
  * Synchronization: NO cross-process event/mutex. The Camera Extension
    polls the ring at 30 fps and relies on the seq_head/seq_tail tear
    protection. POSIX named semaphores are avoided because they face the
    same sandbox-availability risk as the shm itself.
  * Heartbeat time base: `clock_gettime(CLOCK_REALTIME)` → 100 ns ticks
    (Unix epoch). This is NOT Windows FILETIME (1601 epoch); the field
    is "same-side same-source 100ns ticks" and only needs to match the
    C consumer's clock, which also uses CLOCK_REALTIME.

This module is imported on all platforms but only functional on macOS
(`sys.platform == "darwin"`); the ctypes bindings are resolved lazily so
importing it on Windows/CI for the platform-dispatch table does not fail.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import sys
import threading
from dataclasses import dataclass

import numpy as np

from ..errors import FrameBusError, FrameBusOpenError, FrameBusSchemaMismatch
from ..frame import Frame, FourCC
from .base import FrameSink
from ._protocol import (
    AKVC_MAGIC,
    AKVC_SCHEMA_VERSION,
    AKVC_RING_SLOTS,
    AKVC_DEFAULT_SLOT_SIZE,
    RING_CONTROL_FMT,
    RING_CONTROL_SIZE,
    FRAME_HEADER_FMT,
    FRAME_HEADER_SIZE,
    REGION_SIZE,
    OFF_PRODUCER_SEQ,
    OFF_WRITER_PID,
    OFF_PRODUCER_HEARTBEAT,
    FRAME_HEADER_OFF_SEQ_TAIL,
)

# macOS POSIX shm name — must match AKVC_POSIX_SHM_NAME in akvc_protocol.h
# and the C consumer in virtualcam/macos/framebus.
SHM_NAME = "/akvc-frames-v1"

# oflag bits (macOS / POSIX)
_O_RDWR = 0o2
_O_CREAT = 0o100
_O_EXCL = 0o200
_O_RDONLY = 0o0

# mmap prot/flags
_PROT_READ = 0x1
_PROT_WRITE = 0x2
_MAP_SHARED = 0x1

# clock
_CLOCK_REALTIME = 0


class _Timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]


_libc: ctypes.CDLL | None = None


def _ensure_libc() -> ctypes.CDLL:
    global _libc
    if _libc is not None:
        return _libc
    if sys.platform != "darwin":
        raise FrameBusError("MacOsShmSink can only run on macOS")
    path = ctypes.util.find_library("c")
    if not path:
        raise FrameBusError("could not locate libc on macOS")
    _libc = ctypes.CDLL(path, use_errno=True)
    # Signatures
    _libc.shm_open.restype = ctypes.c_int
    _libc.shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_uint16]
    _libc.shm_unlink.restype = ctypes.c_int
    _libc.shm_unlink.argtypes = [ctypes.c_char_p]
    _libc.mmap.restype = ctypes.c_void_p
    _libc.mmap.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_long,
    ]
    _libc.munmap.restype = ctypes.c_int
    _libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    _libc.close.restype = ctypes.c_int
    _libc.close.argtypes = [ctypes.c_int]
    _libc.ftruncate.restype = ctypes.c_int
    _libc.ftruncate.argtypes = [ctypes.c_int, ctypes.c_long]
    _libc.clock_gettime.restype = ctypes.c_int
    _libc.clock_gettime.argtypes = [ctypes.c_int, ctypes.POINTER(_Timespec)]
    _libc.getpid.restype = ctypes.c_int
    _libc.getpid.argtypes = []
    return _libc


def _now_100ns_clock_realtime() -> int:
    """CLOCK_REALTIME in 100ns ticks (Unix epoch)."""
    lib = _ensure_libc()
    ts = _Timespec()
    if lib.clock_gettime(_CLOCK_REALTIME, ctypes.byref(ts)) != 0:
        raise FrameBusError("clock_gettime failed")
    return int(ts.tv_sec) * 10_000_000 + int(ts.tv_nsec) // 100


@dataclass
class _RingState:
    producer_seq: int = 0


class MacOsShmSink(FrameSink):
    """Producer-side writer to the macOS POSIX Frame Bus."""

    def __init__(self) -> None:
        self._fd: int = -1
        self._addr: int = 0
        self._buf: ctypes.Array | None = None
        self._view: memoryview | None = None
        self._lock = threading.Lock()
        self._state = _RingState()
        self._opened = False
        self._created_by_us = False

    # ----- lifecycle -----

    def open(self) -> None:
        if sys.platform != "darwin":
            raise FrameBusError("MacOsShmSink can only run on macOS")
        if self._opened:
            return
        lib = _ensure_libc()
        name_b = SHM_NAME.encode("ascii")

        # Try to open an existing region first (created by another producer
        # instance / a previous run). O_RDWR so we can both write and read
        # the control block for validation.
        fd = lib.shm_open(name_b, _O_RDWR, 0o666)
        self._created_by_us = False
        if fd < 0:
            # Create it. 0o666 so the Camera Extension (separate process)
            # can open read-only.
            fd = lib.shm_open(name_b, _O_RDWR | _O_CREAT | _O_EXCL, 0o666)
            if fd < 0:
                err = ctypes.get_errno()
                raise FrameBusOpenError(
                    f"shm_open(create) failed (errno={err})"
                )
            self._created_by_us = True
            if lib.ftruncate(fd, REGION_SIZE) != 0:
                err = ctypes.get_errno()
                lib.close(fd)
                raise FrameBusOpenError(
                    f"ftruncate failed (errno={err})"
                )
        self._fd = fd

        addr = lib.mmap(None, REGION_SIZE, _PROT_READ | _PROT_WRITE,
                        _MAP_SHARED, fd, 0)
        if not addr or addr == ctypes.c_void_p(-1).value:
            err = ctypes.get_errno()
            lib.close(fd)
            self._fd = -1
            raise FrameBusOpenError(f"mmap failed (errno={err})")
        self._addr = addr

        ArrType = ctypes.c_uint8 * REGION_SIZE
        self._buf = ArrType.from_address(addr)
        self._view = memoryview(self._buf)

        # Initialize / validate control block.
        ctrl = self._read_ctrl()
        if ctrl["magic"] != AKVC_MAGIC:
            self._write_ctrl(
                magic=AKVC_MAGIC,
                schema=AKVC_SCHEMA_VERSION,
                slot_count=AKVC_RING_SLOTS,
                slot_size=AKVC_DEFAULT_SLOT_SIZE,
                producer_seq=0,
                writer_pid=lib.getpid(),
                consumer_count=0,
                created_pts_100ns=_now_100ns_clock_realtime(),
            )
        else:
            if (
                ctrl["schema"] != AKVC_SCHEMA_VERSION
                or ctrl["slot_count"] != AKVC_RING_SLOTS
                or ctrl["slot_size"] != AKVC_DEFAULT_SLOT_SIZE
            ):
                self.close()
                raise FrameBusSchemaMismatch(
                    "shared region schema mismatch", details=ctrl
                )
            self._state.producer_seq = ctrl["producer_seq"]

        self._opened = True

    def close(self) -> None:
        lib = _libc
        if self._view is not None:
            self._view.release()
            self._view = None
        if self._buf is not None and lib is not None and self._addr:
            try:
                lib.munmap(ctypes.c_void_p(self._addr), REGION_SIZE)
            except Exception:
                pass
        self._buf = None
        self._addr = 0
        if self._fd >= 0 and lib is not None:
            lib.close(self._fd)
            self._fd = -1
        self._opened = False

    @property
    def consumer_count(self) -> int:
        if not self._opened:
            return 0
        return self._read_ctrl()["consumer_count"]

    # ----- publish -----

    def publish(self, frame: Frame) -> None:
        if not self._opened:
            raise FrameBusError("sink not opened")
        if frame.fourcc != FourCC.NV12:
            raise FrameBusError(
                f"only NV12 supported; got fourcc={frame.fourcc:#x}"
            )

        plane_size_y = frame.plane_size[0] or (frame.width * frame.height)
        plane_size_uv = frame.plane_size[1] or (frame.width * frame.height // 2)
        header_bytes = FRAME_HEADER_SIZE
        total = header_bytes + plane_size_y + plane_size_uv
        if total > AKVC_DEFAULT_SLOT_SIZE:
            raise FrameBusError("frame too large for slot")

        with self._lock:
            self._state.producer_seq += 1
            seq = self._state.producer_seq
            slot_index = (seq - 1) % AKVC_RING_SLOTS

        # No cross-process mutex: tear protection (seq_head/seq_tail) makes
        # concurrent reader/writer safe. We still hold self._lock around the
        # slot write so two Python threads don't interleave writes.
        with self._lock:
            slot_off = RING_CONTROL_SIZE + slot_index * AKVC_DEFAULT_SLOT_SIZE
            stride0 = frame.stride[0] or frame.width
            stride1 = frame.stride[1] or frame.width
            plane_off0 = header_bytes
            plane_off1 = header_bytes + plane_size_y

            # Header with seq_tail = 0 first (torn sentinel).
            self._pack_header(
                slot_off, frame.fourcc, frame.width, frame.height,
                stride0, stride1, plane_off0, plane_off1,
                plane_size_y, plane_size_uv, frame.flags,
                frame.pts_100ns, seq_head=seq, seq_tail=0,
            )

            data = frame.data
            if not isinstance(data, np.ndarray):
                data = np.frombuffer(data, dtype=np.uint8)
            data_bytes = data.tobytes()

            self._buf[slot_off + plane_off0 : slot_off + plane_off0 + plane_size_y] = (
                data_bytes[:plane_size_y]
            )
            self._buf[slot_off + plane_off1 : slot_off + plane_off1 + plane_size_uv] = (
                data_bytes[plane_size_y : plane_size_y + plane_size_uv]
            )

            # Finalize seq_tail, then update ring control.
            struct.pack_into("<Q", self._buf, slot_off + FRAME_HEADER_OFF_SEQ_TAIL, seq)
            struct.pack_into("<Q", self._buf, OFF_PRODUCER_SEQ, seq)
            self._write_heartbeat()

    # ----- low-level packing -----

    def _pack_header(
        self, slot_off, fourcc, width, height,
        stride0, stride1, plane_off0, plane_off1,
        plane_size_y, plane_size_uv, flags, pts_100ns,
        seq_head, seq_tail,
    ) -> None:
        packed = struct.pack(
            FRAME_HEADER_FMT,
            AKVC_MAGIC, AKVC_SCHEMA_VERSION, fourcc, width, height,
            stride0, stride1, plane_off0, plane_off1,
            plane_size_y, plane_size_uv, flags, pts_100ns,
            seq_head, seq_tail, 0, 0,
        )
        self._buf[slot_off : slot_off + FRAME_HEADER_SIZE] = packed

    def _read_ctrl(self) -> dict:
        raw = bytes(self._buf[:RING_CONTROL_SIZE])
        (
            magic, schema, slot_count, slot_size, producer_seq,
            writer_pid, consumer_count, created_pts,
            producer_heartbeat, helper_pid, helper_reserved, _pad,
        ) = struct.unpack(RING_CONTROL_FMT, raw)
        return {
            "magic": magic,
            "schema": schema,
            "slot_count": slot_count,
            "slot_size": slot_size,
            "producer_seq": producer_seq,
            "writer_pid": writer_pid,
            "consumer_count": consumer_count,
            "created_pts_100ns": created_pts,
            "producer_heartbeat": producer_heartbeat,
            "helper_pid": helper_pid,
        }

    def _write_ctrl(
        self, *, magic, schema, slot_count, slot_size, producer_seq,
        writer_pid, consumer_count, created_pts_100ns,
        producer_heartbeat=0, helper_pid=0,
    ) -> None:
        packed = struct.pack(
            RING_CONTROL_FMT,
            magic, schema, slot_count, slot_size, producer_seq,
            writer_pid, consumer_count, created_pts_100ns,
            producer_heartbeat, helper_pid, 0, b"\x00" * 72,
        )
        self._buf[:RING_CONTROL_SIZE] = packed

    def _write_heartbeat(self) -> None:
        """Update producer_heartbeat (CLOCK_REALTIME 100ns) and writer_pid.

        Must use the same time base as the C consumer's
        `clock_gettime(CLOCK_REALTIME)` so the extension's "is the producer
        alive?" check works. Using perf_counter here would make the
        extension always think the producer is dead → it would publish
        placeholder frames over the real ones (same bug we hit on Windows
        with perf_counter vs FILETIME).
        """
        struct.pack_into("<Q", self._buf, OFF_PRODUCER_HEARTBEAT,
                         _now_100ns_clock_realtime())
        lib = _ensure_libc()
        struct.pack_into("<I", self._buf, OFF_WRITER_PID, lib.getpid())
