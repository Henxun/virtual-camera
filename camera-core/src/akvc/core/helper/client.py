# SPDX-License-Identifier: Apache-2.0
"""Helper Service — Python client for the akvc_helper process.

The Helper is a C++ executable that:
  - Owns the Frame Bus shared memory
  - Monitors the UI producer's heartbeat
  - Publishes placeholder (black) frames when the UI disconnects
  - Listens on stdin for control commands and responds on stdout

Usage:
    helper = HelperService()
    helper.start()       # launches akvc_helper.exe if not running
    helper.ping()        # health check -> bool
    helper.status()      # -> dict
    helper.register_mf() # register MF virtual camera
    helper.stop()        # graceful shutdown
"""

from __future__ import annotations

import os
import struct
import subprocess
import time
from ...runtime import find_helper_exe


CMD_QUIT = 0x00000001
CMD_PING = 0x00000002
CMD_STATUS = 0x00000003
CMD_REGISTER_MF = 0x00000004

RSP_OK = 0x00000000
RSP_PONG = 0x00000001
RSP_UNKNOWN = 0xFFFFFFFF


class HelperService:
    """Manages the akvc_helper.exe process via stdin/stdout IPC."""

    def __init__(self, helper_exe: str | Path | None = None) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._helper_exe = Path(helper_exe) if helper_exe is not None else None

    def start(self) -> bool:
        if self.is_alive():
            return True

        exe = find_helper_exe(self._helper_exe)
        if exe is None:
            return False

        try:
            self._proc = subprocess.Popen(
                [str(exe)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError:
            self._proc = None
            return False

        for _ in range(20):
            if self.ping():
                return True
            time.sleep(0.05)
        return False

    def stop(self, timeout: float = 3.0) -> None:
        self._transact(CMD_QUIT)
        if self._proc is not None:
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self._proc.wait(timeout=2.0)
            self._proc = None

    def is_alive(self) -> bool:
        return self.ping()

    def ping(self) -> bool:
        data = self._transact(CMD_PING)
        if data is None or len(data) < 4:
            return False
        rsp = struct.unpack("<I", data[:4])[0]
        return rsp == RSP_PONG

    def status(self) -> Optional[dict]:
        data = self._transact(CMD_STATUS)
        if data is None or len(data) < 24:
            return None
        magic, pid, heartbeat, seq_lo, seq_hi = struct.unpack(
            "<I I Q I I", data[:24]
        )
        return {
            "magic": magic,
            "pid": pid,
            "heartbeat_100ns": heartbeat,
            "producer_seq": (seq_hi << 32) | seq_lo,
        }

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        """Register the MF virtual camera with Windows.

        |name| is the friendly name shown to applications (Chrome/OBS/etc.).
        Also writes the name to HKLM\\SOFTWARE\\AKVC\\FriendlyName so the DShow
        filter uses the same name for Win11 device aggregation.
        """
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return False
        try:
            # Send command + name_len (in wchar_t units) + UTF-16 name.
            name_w = name[:255]  # truncate to fit helper's 256-wchar buffer
            name_bytes = name_w.encode("utf-16-le")
            name_len = len(name_bytes) // 2
            self._proc.stdin.write(struct.pack("<II", CMD_REGISTER_MF, name_len))
            if name_len > 0:
                self._proc.stdin.write(name_bytes)
            self._proc.stdin.flush()
            data = self._proc.stdout.read(4)
            if data is None or len(data) < 4:
                return False
            rsp = struct.unpack("<I", data[:4])[0]
            return rsp == RSP_OK
        except Exception:
            return False

    # ---------- internal ----------

    def _transact(self, cmd: int, timeout_ms: int = 5000) -> Optional[bytes]:
        """Send a command and read response via stdin/stdout."""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return None
        try:
            self._proc.stdin.write(struct.pack("<I", cmd))
            self._proc.stdin.flush()

            # For STATUS, response is 24 bytes direct (no 4-byte header).
            if cmd == CMD_STATUS:
                data = self._proc.stdout.read(24)
                return data if data and len(data) == 24 else None

            # For other commands, response is a single 4-byte status code.
            data = self._proc.stdout.read(4)
            return data if data and len(data) == 4 else None
        except Exception:
            return None
