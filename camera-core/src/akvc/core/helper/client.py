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
import re
import struct
import subprocess
import time
from pathlib import Path
from typing import Optional

from ...runtime import find_helper_exe


CMD_QUIT = 0x00000001
CMD_PING = 0x00000002
CMD_STATUS = 0x00000003
CMD_REGISTER_MF = 0x00000004

RSP_OK = 0x00000000
RSP_PONG = 0x00000001
RSP_UNKNOWN = 0xFFFFFFFF

_STARTUP_ERROR_RE = re.compile(
    r"^\[helper\] startup_error status=(?P<status>-?\d+) op=(?P<op>\S+) win32=(?P<win32>\d+) object=(?P<object>\S+) hint=(?P<hint>.+)$"
)


class HelperService:
    """Manages the akvc_helper.exe process via stdin/stdout IPC."""

    def __init__(self, helper_exe: str | Path | None = None) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._helper_exe = Path(helper_exe) if helper_exe is not None else None
        self.last_error_message: Optional[str] = None

    def start(self) -> bool:
        if self.is_alive():
            self.last_error_message = None
            return True

        exe = find_helper_exe(self._helper_exe)
        if exe is None:
            self.last_error_message = (
                "AKVC helper executable not found. Ensure akvc/_runtime/windows/akvc_helper.exe "
                "is packaged with the application or set AKVC_HELPER_EXE explicitly."
            )
            return False

        try:
            self._proc = subprocess.Popen(
                [str(exe)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self._proc = None
            self.last_error_message = f"Failed to launch AKVC helper at {exe}: {exc}"
            return False

        self.last_error_message = None
        for _ in range(20):
            if self.ping():
                self.last_error_message = None
                return True
            if self._proc.poll() is not None:
                self.last_error_message = self._describe_start_failure(exe)
                self._proc = None
                return False
            time.sleep(0.05)

        self.last_error_message = self._describe_start_failure(exe)
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

    def _describe_start_failure(self, exe: Path) -> str:
        if self._proc is None:
            return f"AKVC helper at {exe} did not start."

        stderr = ""
        if self._proc.stderr is not None:
            stderr = self._proc.stderr.read().decode("utf-8", errors="replace")
        stderr_lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        for line in stderr_lines:
            match = _STARTUP_ERROR_RE.match(line)
            if not match:
                continue
            win32 = int(match.group("win32"))
            obj = match.group("object")
            op = match.group("op")
            if win32 == 5:
                return (
                    "AKVC helper failed to create global frame bus objects "
                    f"({obj} via {op}, Win32 5: access denied). "
                    "This host environment likely needs elevated privileges on Windows."
                )
            return (
                "AKVC helper failed during startup "
                f"({obj} via {op}, Win32 {win32})."
            )
        if stderr_lines:
            return f"AKVC helper failed during startup: {' | '.join(stderr_lines)}"
        if self._proc.poll() is not None:
            return f"AKVC helper exited during startup with code {self._proc.returncode}."
        return f"AKVC helper at {exe} did not respond to ping during startup."
