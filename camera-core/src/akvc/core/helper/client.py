# SPDX-License-Identifier: Apache-2.0
"""Helper Service — Python client for the akvc_helper process."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from akvc._core_native import NativeWindowsHelperClient

from ...runtime import find_helper_exe


PIPE_NAME = r"\\.\pipe\akvc-helper-ctrl"
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
        self.last_error_message: Optional[str] = None
        self._native = NativeWindowsHelperClient()

    def start(self) -> bool:
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

        if self._launch(exe):
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
        self._native.quit()
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
        return bool(self._native.ping())

    def status(self) -> Optional[dict]:
        data = self._native.status()
        if data is None:
            return None
        return dict(data)

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        return bool(self._native.register_mf(name[:255]))

    def _launch(self, exe: Path) -> bool:
        self._startup_log_path = Path(tempfile.gettempdir()) / "akvc-helper-startup.log"
        if self._native.is_process_elevated():
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

        launched = self._native.launch(str(exe), os.getpid(), str(self._startup_log_path))
        if not launched:
            self._proc = None
            detail = self._native.last_launch_error
            self.last_error_message = (
                f"Failed to launch AKVC helper at {exe} with elevation ({detail})."
                if detail
                else f"Failed to launch AKVC helper at {exe} with elevation."
            )
            return False
        self._proc = None
        return True

    def _describe_start_failure(self, exe: Path) -> str:
        if self._proc is None:
            log_hint = (
                f" Helper startup log: {self._startup_log_path}."
                if self._startup_log_path is not None
                else ""
            )
            pipe_hint = self._native.last_pipe_error
            tail = f" {pipe_hint}" if pipe_hint else ""
            return (
                f"AKVC helper at {exe} did not start or the control pipe {PIPE_NAME} is not ready. "
                f"The helper may still require elevated privileges on Windows.{log_hint}{tail}"
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
        pipe_hint = self._native.last_pipe_error
        tail = f" {pipe_hint}" if pipe_hint else ""
        return (
            f"AKVC helper at {exe} did not respond on named pipe {PIPE_NAME} during startup. "
            f"The helper may still require elevated privileges or manual approval.{tail}"
        )
