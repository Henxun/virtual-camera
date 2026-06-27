# SPDX-License-Identifier: Apache-2.0
"""Helper Service — Python client for the akvc_helper process."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import re
import struct
import subprocess
import tempfile
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

PIPE_NAME = r"\\.\pipe\akvc-helper-ctrl"
WAIT_TIMEOUT_MS = 250
START_TIMEOUT_S = 8.0

_STARTUP_ERROR_RE = re.compile(
    r"^\[helper\] startup_error status=(?P<status>-?\d+) op=(?P<op>\S+) win32=(?P<win32>\d+) object=(?P<object>\S+) hint=(?P<hint>.+)$"
)


class HelperService:
    """Manages the akvc_helper.exe process via named-pipe IPC."""

    def __init__(self, helper_exe: str | Path | None = None) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._helper_exe = Path(helper_exe) if helper_exe is not None else None
        self._startup_log_path: Optional[Path] = None
        self._last_pipe_error: Optional[str] = None
        self.last_error_message: Optional[str] = None

    def start(self) -> bool:
        self._last_pipe_error = None
        if self.ping():
            self.last_error_message = None
            return True

        exe = find_helper_exe(self._helper_exe)
        if exe is None:
            self.last_error_message = (
                "AKVC helper executable not found. Ensure akvc/_runtime/windows/akvc_helper.exe "
                "is packaged with the application or set AKVC_HELPER_EXE explicitly."
            )
            return False

        if self._launch_elevated(exe):
            deadline = time.monotonic() + START_TIMEOUT_S
            while time.monotonic() < deadline:
                if self.ping():
                    self.last_error_message = None
                    return True
                if self._proc is not None and self._proc.poll() is not None:
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
        magic, pid, heartbeat, seq_lo, seq_hi = struct.unpack("<I I Q I I", data[:24])
        return {
            "magic": magic,
            "pid": pid,
            "heartbeat_100ns": heartbeat,
            "producer_seq": (seq_hi << 32) | seq_lo,
        }

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        name_w = name[:255]
        name_bytes = name_w.encode("utf-16-le")
        payload = struct.pack("<I", len(name_bytes) // 2) + name_bytes
        data = self._transact(CMD_REGISTER_MF, payload=payload)
        if data is None or len(data) < 4:
            return False
        rsp = struct.unpack("<I", data[:4])[0]
        return rsp == RSP_OK

    def _launch_elevated(self, exe: Path) -> bool:
        self._startup_log_path = Path(tempfile.gettempdir()) / "akvc-helper-startup.log"
        if self._is_process_elevated():
            try:
                self._proc = subprocess.Popen(
                    [
                        str(exe),
                        "--pipe",
                        PIPE_NAME,
                        "--parent-pid",
                        str(os.getpid()),
                        "--log",
                        str(self._startup_log_path),
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return True
            except OSError as exc:
                self._proc = None
                self.last_error_message = f"Failed to launch AKVC helper at {exe}: {exc}"
                return False

        args = (
            f'--pipe "{PIPE_NAME}" '
            f'--parent-pid {os.getpid()} '
            f'--log "{self._startup_log_path}"'
        )
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.ShellExecuteW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        shell32.ShellExecuteW.restype = ctypes.wintypes.HINSTANCE

        rc = shell32.ShellExecuteW(None, "runas", str(exe), args, str(exe.parent), 0)
        if int(rc) <= 32:
            self._proc = None
            self.last_error_message = (
                f"Failed to launch AKVC helper at {exe} with elevation (ShellExecuteW rc={int(rc)})."
            )
            return False
        self._proc = None
        return True

    def _transact(self, cmd: int, payload: bytes = b"") -> Optional[bytes]:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.WaitNamedPipeW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        kernel32.WaitNamedPipeW.restype = ctypes.c_int
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.ReadFile.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        kernel32.ReadFile.restype = ctypes.c_int
        kernel32.WriteFile.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        kernel32.WriteFile.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        if not kernel32.WaitNamedPipeW(PIPE_NAME, WAIT_TIMEOUT_MS):
            self._last_pipe_error = f"WaitNamedPipeW err={ctypes.get_last_error()}"
            return None

        handle = kernel32.CreateFileW(
            PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            self._last_pipe_error = f"CreateFileW err={ctypes.get_last_error()}"
            return None

        try:
            request = struct.pack("<I", cmd) + payload
            written = ctypes.c_uint32(0)
            buf = ctypes.create_string_buffer(request)
            if not kernel32.WriteFile(handle, buf, len(request), ctypes.byref(written), None):
                return None

            read_len = 24 if cmd == CMD_STATUS else 4
            response = ctypes.create_string_buffer(read_len)
            read = ctypes.c_uint32(0)
            if not kernel32.ReadFile(handle, response, read_len, ctypes.byref(read), None):
                return None
            if read.value != read_len:
                return None
            return response.raw[: read.value]
        finally:
            kernel32.CloseHandle(handle)

    def _is_process_elevated(self) -> bool:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        advapi32.OpenProcessToken.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.OpenProcessToken.restype = ctypes.c_int
        advapi32.GetTokenInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        advapi32.GetTokenInformation.restype = ctypes.c_int
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        class TOKEN_ELEVATION(ctypes.Structure):
            _fields_ = [("TokenIsElevated", ctypes.c_uint32)]

        TOKEN_QUERY = 0x0008
        TokenElevation = 20
        token = ctypes.c_void_p()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
            return False
        try:
            elevation = TOKEN_ELEVATION()
            size = ctypes.c_uint32(0)
            if not advapi32.GetTokenInformation(
                token,
                TokenElevation,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(size),
            ):
                return False
            return bool(elevation.TokenIsElevated)
        finally:
            kernel32.CloseHandle(token)

    def _describe_start_failure(self, exe: Path) -> str:
        if self._proc is None:
            log_hint = (
                f" Helper startup log: {self._startup_log_path}."
                if self._startup_log_path is not None
                else ""
            )
            return (
                f"AKVC helper at {exe} did not start or the control pipe {PIPE_NAME} is not ready. "
                f"The helper may still require elevated privileges on Windows.{log_hint}"
            )

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
        return (
            f"AKVC helper at {exe} did not respond on named pipe {PIPE_NAME} during startup. "
            f"The helper may still require elevated privileges or manual approval. {self._last_pipe_error or ''}"
        )
