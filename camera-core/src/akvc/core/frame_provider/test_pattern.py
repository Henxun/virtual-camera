# SPDX-License-Identifier: Apache-2.0
"""Built-in test pattern provider — used when no real source is available."""

from __future__ import annotations

import time
from enum import Enum

import numpy as np

from ..frame import Frame, FLAG_PLACEHOLDER
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


# Friendly display names shown in the source selector.
PATTERN_NAMES: dict[Pattern, str] = {
    Pattern.COLORBAR: "Color Bars",
    Pattern.GRADIENT: "Gradient",
    Pattern.CHECKERBOARD: "Checkerboard",
    Pattern.NOISE: "Noise",
    Pattern.SOLID: "Solid Red",
    Pattern.MOVING_BOX: "Moving Box",
}


class TestPatternProvider(FrameProvider):
    """Generates animated test patterns at the requested fps."""

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
        self._frame_period = 1.0 / fps
        self._next_t: float = 0.0
        self._seq = 0
        self._opened = False

    def open(self) -> None:
        self._next_t = time.perf_counter()
        self._opened = True

    def read(self) -> Frame:
        if not self._opened:
            self.open()

        now = time.perf_counter()
        wait = self._next_t - now
        if wait > 0:
            time.sleep(wait)
        self._next_t += self._frame_period

        self._seq += 1
        bgr = self._render(self._seq)
        return Frame.from_bgr(bgr, seq=self._seq, flags=FLAG_PLACEHOLDER)

    def close(self) -> None:
        self._opened = False

    def describe(self) -> ProviderInfo:
        from ..frame import FourCC

        return ProviderInfo(
            id=f"test:{self.pattern.value}",
            name=PATTERN_NAMES.get(self.pattern, self.pattern.value),
            formats=(FormatSpec(FourCC.RGB24, self.width, self.height, self.fps),),
        )

    # ---- renderers ----

    def _render(self, seq: int) -> np.ndarray:
        renderer = {
            Pattern.COLORBAR: self._render_colorbar,
            Pattern.GRADIENT: self._render_gradient,
            Pattern.CHECKERBOARD: self._render_checkerboard,
            Pattern.NOISE: self._render_noise,
            Pattern.SOLID: self._render_solid,
            Pattern.MOVING_BOX: self._render_moving_box,
        }
        return renderer[self.pattern](seq)

    def _render_colorbar(self, seq: int) -> np.ndarray:
        """SMPTE-ish color bars with sliding scan line."""
        h, w = self.height, self.width
        bars = 8
        bar_w = w // bars
        colors = np.array(
            [
                [192, 192, 192],  # white
                [0, 192, 192],    # cyan
                [192, 192, 0],    # yellow
                [0, 192, 0],      # green
                [192, 0, 192],    # magenta
                [0, 0, 192],      # blue
                [192, 0, 0],      # red
                [16, 16, 16],     # black
            ],
            dtype=np.uint8,
        )
        img = np.empty((h, w, 3), dtype=np.uint8)
        for i in range(bars):
            x0 = i * bar_w
            x1 = w if i == bars - 1 else x0 + bar_w
            img[:, x0:x1] = colors[i]
        # Sliding scan line.
        img[(seq * 4) % h, :, :] = (255, 255, 255)
        return img

    def _render_gradient(self, seq: int) -> np.ndarray:
        """Horizontal RGB gradient that slowly shifts hue."""
        h, w = self.height, self.width
        t = seq * 0.02
        r = (np.arange(w, dtype=np.float32) + t * 50) % 256
        g = (np.arange(w, dtype=np.float32) * 0.5 + t * 30) % 256
        b = (255 - np.arange(w, dtype=np.float32) * 0.3 + t * 20) % 256
        row_r = np.tile(r.astype(np.uint8), (h, 1))
        row_g = np.tile(g.astype(np.uint8), (h, 1))
        row_b = np.tile(b.astype(np.uint8), (h, 1))
        return np.stack([row_b, row_g, row_r], axis=-1)

    def _render_checkerboard(self, seq: int) -> np.ndarray:
        """Animated checkerboard that scrolls."""
        h, w = self.height, self.width
        size = 40
        offset = (seq * 2) % size
        x = (np.arange(w, dtype=np.int32) + offset) // size
        y = np.arange(h, dtype=np.int32)[:, None] // size
        mask = (x + y) % 2 == 0
        img = np.where(mask[..., None], np.array([200, 200, 200]), np.array([30, 30, 30])).astype(np.uint8)
        return img

    def _render_noise(self, seq: int) -> np.ndarray:
        """Fresh random noise every frame — TV static effect."""
        h, w = self.height, self.width
        return np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)

    def _render_solid(self, seq: int) -> np.ndarray:
        """Solid red with a blinking timestamp overlay."""
        h, w = self.height, self.width
        img = np.full((h, w, 3), (0, 0, 180), dtype=np.uint8)
        # Draw a simple cross that blinks.
        if (seq // 15) % 2 == 0:
            cx, cy = w // 2, h // 2
            img[cy - 20:cy + 20, cx - 2:cx + 2] = (255, 255, 255)
            img[cy - 2:cy + 2, cx - 20:cx + 20] = (255, 255, 255)
        return img

    def _render_moving_box(self, seq: int) -> np.ndarray:
        """A colored box bouncing around on a dark background."""
        h, w = self.height, self.width
        img = np.full((h, w, 3), 20, dtype=np.uint8)
        box_size = 80
        period = 120
        t = seq % period
        # Bounce diagonally.
        progress = t / period
        x = int(progress * (w - box_size))
        y = int((1 - abs(2 * progress - 1)) * (h - box_size))
        color = ((seq * 5) % 256, (seq * 3) % 256, (seq * 7) % 256)
        img[y:y + box_size, x:x + box_size] = color
        # Border.
        img[y:y + box_size, x] = (255, 255, 255)
        img[y:y + box_size, x + box_size - 1] = (255, 255, 255)
        img[y, x:x + box_size] = (255, 255, 255)
        img[y + box_size - 1, x:x + box_size] = (255, 255, 255)
        return img
