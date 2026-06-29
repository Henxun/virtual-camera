# SPDX-License-Identifier: Apache-2.0
"""Built-in test pattern provider — used when no real source is available."""

from __future__ import annotations

from enum import Enum

from akvc._core_native import NativeTestPatternProvider

from ..frame import FLAG_PLACEHOLDER
from .base import FormatSpec, FrameProvider, ProviderInfo


class Pattern(Enum):
    COLORBAR = "colorbar"
    GRADIENT = "gradient"
    CHECKERBOARD = "checkerboard"
    NOISE = "noise"
    SOLID = "solid"
    MOVING_BOX = "moving_box"

    @staticmethod
    def from_id(s: str) -> Pattern:
        for p in Pattern:
            if p.value == s:
                return p
        return Pattern.COLORBAR


PATTERN_NAMES: dict[Pattern, str] = {
    Pattern.COLORBAR: "Color Bars",
    Pattern.GRADIENT: "Gradient",
    Pattern.CHECKERBOARD: "Checkerboard",
    Pattern.NOISE: "Noise",
    Pattern.SOLID: "Solid Red",
    Pattern.MOVING_BOX: "Moving Box",
}


class TestPatternProvider(FrameProvider):
    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        pattern: Pattern = Pattern.COLORBAR,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.pattern = pattern
        self._native = NativeTestPatternProvider(width, height, fps, pattern.value)

    def open(self) -> None:
        self._native.open()

    def read(self):
        frame = self._native.read()
        frame.flags = FLAG_PLACEHOLDER
        return frame

    def close(self) -> None:
        self._native.close()

    def describe(self) -> ProviderInfo:
        from ..frame import FourCC

        return ProviderInfo(
            id=f"test:{self.pattern.value}",
            name=PATTERN_NAMES.get(self.pattern, self.pattern.value),
            formats=(FormatSpec(FourCC.RGB24, self.width, self.height, self.fps),),
        )
