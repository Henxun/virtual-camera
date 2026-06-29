# SPDX-License-Identifier: Apache-2.0
"""Frame providers."""

from .base import FrameProvider, ProviderInfo, FormatSpec
from .test_pattern import PATTERN_NAMES, Pattern, TestPatternProvider
from .usb import UsbCameraProvider


DEFAULT_PROVIDER_WIDTH = 1280
DEFAULT_PROVIDER_HEIGHT = 720
DEFAULT_PROVIDER_FPS = 30


def create_provider_from_source_id(
    source_id: str,
    *,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> FrameProvider:
    if source_id.startswith("usb:"):
        idx = int(source_id.split(":", 1)[1])
        return UsbCameraProvider(device_index=idx, width=width, height=height, fps=fps)

    pattern_id = source_id.split(":", 1)[1] if ":" in source_id else "colorbar"
    return TestPatternProvider(
        width=width,
        height=height,
        fps=fps,
        pattern=Pattern.from_id(pattern_id),
    )


__all__ = [
    "FrameProvider",
    "ProviderInfo",
    "FormatSpec",
    "Pattern",
    "PATTERN_NAMES",
    "TestPatternProvider",
    "UsbCameraProvider",
    "DEFAULT_PROVIDER_WIDTH",
    "DEFAULT_PROVIDER_HEIGHT",
    "DEFAULT_PROVIDER_FPS",
    "create_provider_from_source_id",
]
