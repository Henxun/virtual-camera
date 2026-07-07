# SPDX-License-Identifier: Apache-2.0
"""Compatibility wrappers around the shared AKVC helper service."""

from __future__ import annotations

from pathlib import Path

from akvc.helper_service import (
    DEFAULT_PERSISTENT_LOG,
    DEFAULT_TASK_NAME,
    PIPE_NAME,
    START_TIMEOUT_S,
    HelperService as SharedHelperService,
    NativeWindowsHelperClient,
)
from akvc.runtime import find_helper_exe


class HelperService(SharedHelperService):
    def __init__(self, helper_exe: str | Path | None = None) -> None:
        self._proc = None
        self._helper_exe = Path(helper_exe) if helper_exe is not None else None
        self.last_error_message = None
        self._native = NativeWindowsHelperClient()

    def _resolved_helper_exe(self):
        return find_helper_exe(self._helper_exe)


__all__ = [
    "DEFAULT_PERSISTENT_LOG",
    "DEFAULT_TASK_NAME",
    "PIPE_NAME",
    "START_TIMEOUT_S",
    "HelperService",
    "NativeWindowsHelperClient",
    "find_helper_exe",
]
