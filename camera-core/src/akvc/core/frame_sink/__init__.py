# SPDX-License-Identifier: Apache-2.0
"""Frame sinks — write frames into the platform-specific frame bus."""

import sys

from .base import FrameSink

__all__ = ["FrameSink", "create_sink"]


def create_sink() -> FrameSink:
    """Return the platform-appropriate FrameSink.

    - Windows: WindowsShmSink (named file mapping `Global\\akvc-frames-v1`)
    - macOS:   MacOsShmSink (POSIX shm `/akvc-frames-v1`)
    """
    if sys.platform == "win32":
        from .windows_shm import WindowsShmSink
        return WindowsShmSink()
    if sys.platform == "darwin":
        from .macos_shm import MacOsShmSink
        return MacOsShmSink()
    raise RuntimeError(f"unsupported platform for frame sink: {sys.platform}")
