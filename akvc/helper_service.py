# SPDX-License-Identifier: Apache-2.0
"""Windows helper orchestration shared by SDK, CLI, and desktop app."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from akvc._core_native import NativeWindowsHelperClient

from .windows_runtime import find_helper_exe

PIPE_NAME = r"\\.\pipe\akvc-helper-ctrl"
DEFAULT_TASK_NAME = "AKVirtualCameraHelper"
DEFAULT_PERSISTENT_LOG = str(Path(tempfile.gettempdir()) / "akvc-helper-persistent.log")
START_TIMEOUT_S = 8.0


class HelperService:
    def __init__(self, helper_exe: str | Path | None = None) -> None:
        self._proc = None
        self._helper_exe = Path(helper_exe) if helper_exe is not None else None
        self.last_error_message: Optional[str] = None
        self._native = NativeWindowsHelperClient()

    def _resolved_helper_exe(self) -> Optional[Path]:
        return find_helper_exe(self._helper_exe)

    def start(self) -> bool:
        exe = self._resolved_helper_exe()
        ok = self._native.start_service(str(exe) if exe is not None else "")
        self.last_error_message = None if ok else (self._native.last_error_message or None)
        return bool(ok)

    def stop(self, timeout: float = 3.0) -> None:
        self._native.quit()
        self._proc = None
        self.last_error_message = None

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

    def unregister_mf(self) -> bool:
        ok = bool(self._native.unregister_mf())
        self.last_error_message = None if ok else (self._native.last_error_message or None)
        return ok

    def install_autostart(self, task_name: str = DEFAULT_TASK_NAME, log_path: str | Path = DEFAULT_PERSISTENT_LOG) -> bool:
        exe = self._resolved_helper_exe()
        if exe is None:
            self.last_error_message = (
                "AKVC helper executable not found. Ensure akvc/_runtime/windows/akvc_helper.exe "
                "is packaged with the application or set AKVC_HELPER_EXE explicitly."
            )
            return False
        ok = bool(self._native.install_autostart(str(exe), str(log_path), task_name))
        self.last_error_message = None if ok else (
            f"Failed to install persistent AKVC helper task {task_name} ({self._native.last_launch_error})."
            if self._native.last_launch_error else f"Failed to install persistent AKVC helper task {task_name}."
        )
        return ok

    def uninstall_autostart(self, task_name: str = DEFAULT_TASK_NAME) -> bool:
        ok = bool(self._native.uninstall_autostart(task_name))
        self.last_error_message = None if ok else (
            f"Failed to uninstall persistent AKVC helper task {task_name} ({self._native.last_launch_error})."
            if self._native.last_launch_error else f"Failed to uninstall persistent AKVC helper task {task_name}."
        )
        return ok

    def start_installed(self, task_name: str = DEFAULT_TASK_NAME, timeout_s: float = START_TIMEOUT_S) -> bool:
        ok = bool(self._native.start_installed(task_name, timeout_s))
        if ok:
            self.last_error_message = None
            return True
        self.last_error_message = (
            self._native.last_error_message or (
                f"Failed to start installed AKVC helper task {task_name} ({self._native.last_launch_error})."
                if self._native.last_launch_error else f"Failed to start installed AKVC helper task {task_name}."
            )
        )
        return False

    def scheduled_task_status(self, task_name: str = DEFAULT_TASK_NAME) -> dict:
        return dict(self._native.scheduled_task_status(task_name))

    def ensure_running(self, *, task_name: str = DEFAULT_TASK_NAME, prefer_installed: bool = True) -> bool:
        exe = self._resolved_helper_exe()
        ok = bool(self._native.ensure_running(
            str(exe) if exe is not None else "",
            task_name,
            prefer_installed,
        ))
        self.last_error_message = None if ok else (self._native.last_error_message or None)
        return ok
