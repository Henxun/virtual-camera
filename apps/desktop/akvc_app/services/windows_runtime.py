# SPDX-License-Identifier: Apache-2.0
"""Compatibility wrappers around the shared AKVC runtime locator."""

from __future__ import annotations

from akvc.windows_runtime import find_dshow_dll, find_helper_exe, find_mf_dll

__all__ = ["find_dshow_dll", "find_helper_exe", "find_mf_dll"]
