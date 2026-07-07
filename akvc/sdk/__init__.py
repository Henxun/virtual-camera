# SPDX-License-Identifier: Apache-2.0
"""High-level SDK entrypoints for external applications."""

from typing import TYPE_CHECKING

__all__ = [
    "VirtualCamera",
    "MacDirectCameraSender",
    "DirectSenderError",
    "create_direct_sender",
]

if TYPE_CHECKING:
    from akvc.platforms.macos import (
        DirectSenderError,
        MacDirectCameraSender,
        create_direct_sender,
    )
    from .virtual_camera import VirtualCamera


def __getattr__(name: str):
    if name == "VirtualCamera":
        from .virtual_camera import VirtualCamera

        return VirtualCamera
    if name in {"MacDirectCameraSender", "DirectSenderError", "create_direct_sender"}:
        from akvc.platforms.macos import (
            DirectSenderError,
            MacDirectCameraSender,
            create_direct_sender,
        )

        exports = {
            "MacDirectCameraSender": MacDirectCameraSender,
            "DirectSenderError": DirectSenderError,
            "create_direct_sender": create_direct_sender,
        }
        return exports[name]
    raise AttributeError(name)
