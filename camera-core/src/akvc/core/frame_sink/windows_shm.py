# SPDX-License-Identifier: Apache-2.0
"""Windows shared-memory frame sink.

This module is the Python *producer* counterpart of the C++ `FrameBusProducer`
(see `virtualcam/windows/framebus`). It avoids ctypes/cffi and instead writes
directly to a `multiprocessing.shared_memory.SharedMemory` block whose schema
matches `akvc_protocol.h`.

The C++ consumer side uses `OpenFileMappingW(L"Global\\akvc-frames-v1")`
to read what we publish.

Tear protection: each frame slot has a leading and trailing seq word; the
consumer compares them and discards on mismatch.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import struct
import sys
import threading
import time
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
)

# ---------- Windows-only named-kernel-object names ----------
# (Not in _protocol.py — these are Windows-specific.)
SHM_NAME = r"akvc-frames-v1"          # multiprocessing strips Local\ prefix
EVENT_NAME = r"Local\akvc-frames-evt-v1"
MUTEX_NAME = r"Local\akvc-frames-mtx-v1"


# ---------- Win32 sync primitives via ctypes ----------

if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    SECURITY_ATTRIBUTES = ctypes.c_void_p  # opaque, we pass NULL for simplicity

    _kernel32.CreateEventW.restype = ctypes.c_void_p
    _kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p
    ]
    _kernel32.OpenEventW.restype = ctypes.c_void_p
    _kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    _kernel32.SetEvent.restype = ctypes.c_int
    _kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    _kernel32.CreateMutexW.restype = ctypes.c_void_p
    _kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p
    ]
    _kernel32.OpenMutexW.restype = ctypes.c_void_p
    _kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    _kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.ReleaseMutex.restype = ctypes.c_int
    _kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    _kernel32.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(ctypes.wintypes.FILETIME)]
    _kernel32.GetSystemTimeAsFileTime.restype = None


@dataclass
class _RingState:
    producer_seq: int = 0


class WindowsShmSink(FrameSink):
    """Producer-side writer to the Windows Frame Bus.

    Note: This implementation uses `mmap` via ctypes to create a named file
    mapping with the same name the C++ consumer expects. We do NOT rely on
    `multiprocessing.shared_memory.SharedMemory` because its naming scheme
    on Windows prepends a session prefix that the C++ side cannot open.
    """

    def __init__(self) -> None:
        self._mapping = None  # HANDLE
        self._view: memoryview | None = None
        self._buf: ctypes.Array | None = None
        self._event = None
        self._mutex = None
        self._lock = threading.Lock()
        self._state = _RingState()
        self._opened = False

    # ----- lifecycle -----

    def open(self) -> None:
        if sys.platform != "win32":
            raise FrameBusError("WindowsShmSink can only run on Windows")
        if self._opened:
            return

        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        PAGE_READWRITE = 0x04
        FILE_MAP_ALL_ACCESS = 0xF001F
        FILE_MAP_WRITE = 0x0002

        _kernel32.CreateFileMappingW.restype = ctypes.c_void_p
        _kernel32.CreateFileMappingW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p,
        ]
        _kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        _kernel32.OpenFileMappingW.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p,
        ]
        _kernel32.MapViewOfFile.restype = ctypes.c_void_p
        _kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t,
        ]
        _kernel32.UnmapViewOfFile.restype = ctypes.c_int
        _kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]

        # Phase 3: try opening existing SHM first (created by Helper).
        # Use "Global" prefix so the MF frame server (session 0) can read
        # frames published by the helper/worker (user session).
        h = _kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False,
                                        "Global\\akvc-frames-v1")
        created_by_us = False
        if not h:
            # Fall back to creating it ourselves (Phase 2 / no Helper).
            size_hi = (REGION_SIZE >> 32) & 0xFFFFFFFF
            size_lo = REGION_SIZE & 0xFFFFFFFF
            h = _kernel32.CreateFileMappingW(
                INVALID_HANDLE_VALUE, None, PAGE_READWRITE,
                size_hi, size_lo, "Global\\akvc-frames-v1",
            )
            if not h:
                err = ctypes.get_last_error()
                raise FrameBusOpenError(
                    f"CreateFileMappingW failed (Win32 err={err})"
                )
            created_by_us = True
        self._mapping = h

        addr = _kernel32.MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, REGION_SIZE)
        if not addr:
            err = ctypes.get_last_error()
            _kernel32.CloseHandle(h)
            self._mapping = None
            raise FrameBusOpenError(
                f"MapViewOfFile failed (Win32 err={err})"
            )

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
                writer_pid=ctypes.c_uint32(_kernel32.GetCurrentProcessId()).value
                if hasattr(_kernel32, "GetCurrentProcessId")
                else 0,
                consumer_count=0,
                created_pts_100ns=int(time.time() * 10_000_000),
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

        self._event = _kernel32.OpenEventW(0x001F0003, False,  # EVENT_ALL_ACCESS
                                            "Global\\akvc-frames-evt-v1")
        if not self._event:
            self._event = _kernel32.CreateEventW(None, 0, 0, "Global\\akvc-frames-evt-v1")
            if not self._event:
                err = ctypes.get_last_error()
                self.close()
                raise FrameBusOpenError(
                    f"CreateEventW failed (Win32 err={err})"
                )

        self._mutex = _kernel32.OpenMutexW(0x001F0001, False,  # MUTEX_ALL_ACCESS
                                            "Global\\akvc-frames-mtx-v1")
        if not self._mutex:
            self._mutex = _kernel32.CreateMutexW(None, 0, "Global\\akvc-frames-mtx-v1")
            if not self._mutex:
                err = ctypes.get_last_error()
                self.close()
                raise FrameBusOpenError(
                    f"CreateMutexW failed (Win32 err={err})"
                )

        self._opened = True

    def close(self) -> None:
        if not self._opened and not self._mapping:
            return
        if self._view is not None:
            self._view.release()
            self._view = None
        if self._buf is not None:
            try:
                _kernel32.UnmapViewOfFile(ctypes.addressof(self._buf))
            except Exception:
                pass
            self._buf = None
        if self._mapping:
            _kernel32.CloseHandle(self._mapping)
            self._mapping = None
        if self._event:
            _kernel32.CloseHandle(self._event)
            self._event = None
        if self._mutex:
            _kernel32.CloseHandle(self._mutex)
            self._mutex = None
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
                f"only NV12 supported in Phase 2; got fourcc={frame.fourcc:#x}"
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

        # Acquire mutex (best-effort; allow short stall).
        if self._mutex:
            wr = _kernel32.WaitForSingleObject(self._mutex, 50)
            if wr not in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
                raise FrameBusError("mutex wait failed")

        try:
            slot_off = RING_CONTROL_SIZE + slot_index * AKVC_DEFAULT_SLOT_SIZE

            # Header: write seq_head first, sentinel seq_tail=0, then payload, then seq_tail.
            stride0 = frame.stride[0] or frame.width
            stride1 = frame.stride[1] or frame.width
            plane_off0 = header_bytes
            plane_off1 = header_bytes + plane_size_y

            # Pack header with seq_tail = 0 first.
            self._pack_header(
                slot_off,
                frame.fourcc,
                frame.width,
                frame.height,
                stride0,
                stride1,
                plane_off0,
                plane_off1,
                plane_size_y,
                plane_size_uv,
                frame.flags,
                frame.pts_100ns,
                seq_head=seq,
                seq_tail=0,
            )

            # Copy payload.
            data = frame.data
            if not isinstance(data, np.ndarray):
                data = np.frombuffer(data, dtype=np.uint8)
            data_bytes = data.tobytes() if not data.flags["C_CONTIGUOUS"] else data.tobytes()
            # ndarray.tobytes() returns a copy regardless; that's fine for MVP.

            # Write Y
            self._buf[slot_off + plane_off0 : slot_off + plane_off0 + plane_size_y] = (
                data_bytes[:plane_size_y]
            )
            # Write UV
            self._buf[slot_off + plane_off1 : slot_off + plane_off1 + plane_size_uv] = (
                data_bytes[plane_size_y : plane_size_y + plane_size_uv]
            )

            # Finalize seq_tail.
            self._write_seq_tail(slot_off, seq)
            # Update ring control producer_seq, heartbeat, writer_pid.
            self._write_ctrl_producer_seq(seq)
            self._write_heartbeat()

        finally:
            if self._mutex:
                _kernel32.ReleaseMutex(self._mutex)

        if self._event:
            _kernel32.SetEvent(self._event)

    # ----- low-level packing -----

    def _pack_header(
        self,
        slot_off: int,
        fourcc: int,
        width: int,
        height: int,
        stride0: int,
        stride1: int,
        plane_off0: int,
        plane_off1: int,
        plane_size_y: int,
        plane_size_uv: int,
        flags: int,
        pts_100ns: int,
        seq_head: int,
        seq_tail: int,
    ) -> None:
        packed = struct.pack(
            FRAME_HEADER_FMT,
            AKVC_MAGIC,
            AKVC_SCHEMA_VERSION,
            fourcc,
            width,
            height,
            stride0,
            stride1,
            plane_off0,
            plane_off1,
            plane_size_y,
            plane_size_uv,
            flags,
            pts_100ns,
            seq_head,
            seq_tail,
            0,
            0,
        )
        self._buf[slot_off : slot_off + FRAME_HEADER_SIZE] = packed

    def _write_seq_tail(self, slot_off: int, seq_tail: int) -> None:
        # seq_tail field offset within the header: compute via struct.calcsize on prefix
        # 11 fields before seq_head/tail = magic, schema, fourcc, w, h, stride0, stride1,
        # plane_off0, plane_off1, plane_size_y, plane_size_uv, flags, pts_100ns, seq_head
        # We know layout exactly:
        #   uint32 * 11 = 44 bytes (magic..plane_size_uv)  → wait, plane fields are 4 each → 11*4=44
        #   flags (uint32) at offset 44, pts_100ns (uint64) at 48 (8-byte align), seq_head at 56,
        #   seq_tail at 64. But struct '<' is unaligned, so layout is dense:
        #     magic(4)+schema(4)+fourcc(4)+w(4)+h(4)+stride0(4)+stride1(4)+po0(4)+po1(4)+ps0(4)+ps1(4)
        #     = 44; +flags(4)=48; +pts(8)=56; +head(8)=64; tail at 64.
        seq_tail_off = slot_off + 64
        struct.pack_into("<Q", self._buf, seq_tail_off, seq_tail)

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
        self,
        *,
        magic: int,
        schema: int,
        slot_count: int,
        slot_size: int,
        producer_seq: int,
        writer_pid: int,
        consumer_count: int,
        created_pts_100ns: int,
        producer_heartbeat: int = 0,
        helper_pid: int = 0,
    ) -> None:
        packed = struct.pack(
            RING_CONTROL_FMT,
            magic, schema, slot_count, slot_size, producer_seq,
            writer_pid, consumer_count, created_pts_100ns,
            producer_heartbeat, helper_pid, 0, b"\x00" * 72,
        )
        self._buf[:RING_CONTROL_SIZE] = packed

    def _write_ctrl_producer_seq(self, seq: int) -> None:
        # producer_seq is the 5th field, offset = 4+4+4+4 = 16
        struct.pack_into("<Q", self._buf, 16, seq)

    def _write_heartbeat(self) -> None:
        """Update producer_heartbeat (offset 40) and writer_pid (offset 24).

        The heartbeat must use the same time base as the Helper's
        now_100ns() (GetSystemTimePreciseAsFileTime, absolute system time in
        100ns ticks). Using perf_counter would break the Helper's
        elapsed-time check and cause it to publish placeholder frames that
        overwrite the worker's real frames.
        """
        ft = ctypes.wintypes.FILETIME()
        _kernel32.GetSystemTimeAsFileTime(ctypes.byref(ft))
        now_100ns = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
        struct.pack_into("<Q", self._buf, 40, now_100ns)
        struct.pack_into("<I", self._buf, 24,
                         _kernel32.GetCurrentProcessId())
