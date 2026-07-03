# SPDX-License-Identifier: Apache-2.0
"""AK Virtual Camera SDK package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLE = None

if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    runtime_dir = Path(__file__).resolve().parent / "_runtime" / "windows"
    if runtime_dir.is_dir():
        _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(runtime_dir))

from .sdk import VirtualCamera

__version__ = "0.2.0"

__all__ = ["VirtualCamera", "__version__"]
