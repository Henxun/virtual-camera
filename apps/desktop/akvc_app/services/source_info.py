# SPDX-License-Identifier: Apache-2.0
"""App-side provider contracts and source metadata (pure Python).

Replaces the former akvc._core_native-backed source_info. Test-pattern ids and
source-id parsing are implemented here; USB enumeration is best-effort via cv2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

DEFAULT_PROVIDER_WIDTH = 1280
DEFAULT_PROVIDER_HEIGHT = 720
DEFAULT_PROVIDER_FPS = 30

_PATTERN_IDS: list[str] = ["colorbar", "gradient", "checkerboard", "noise", "solid", "moving_box"]


@dataclass(frozen=True)
class FormatSpec:
    fourcc: int
    width: int
    height: int
    fps_num: int
    fps_den: int = 1


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    formats: tuple[FormatSpec, ...] = ()


class Pattern(Enum):
    COLORBAR = "colorbar"
    GRADIENT = "gradient"
    CHECKERBOARD = "checkerboard"
    NOISE = "noise"
    SOLID = "solid"
    MOVING_BOX = "moving_box"

    @staticmethod
    def from_id(value: str) -> "Pattern":
        for pattern in Pattern:
            if pattern.value == value:
                return pattern
        return Pattern.COLORBAR


def list_pattern_ids() -> list[str]:
    return list(_PATTERN_IDS)


def parse_source_id(source_id: str) -> dict[str, Any]:
    """Parse 'test:<pattern>' or 'usb:<index>' into a dict."""
    kind, _, rest = (source_id or "").partition(":")
    kind = kind.strip().lower()
    if kind == "usb":
        try:
            idx = int(rest.strip() or "0")
        except ValueError:
            idx = 0
        return {"kind": "usb", "device_index": idx, "pattern_id": None}
    pattern_id = rest.strip() or "colorbar"
    return {"kind": "test", "pattern_id": pattern_id, "device_index": None}


def describe_source_id(
    source_id: str,
    *,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> ProviderInfo:
    parsed = parse_source_id(source_id)
    if parsed["kind"] == "usb":
        name = f"USB Camera {parsed['device_index']}"
    else:
        name = parsed["pattern_id"].replace("_", " ").title()
    return ProviderInfo(
        id=source_id,
        name=name,
        formats=(FormatSpec(fourcc=0x20424752, width=width, height=height, fps_num=fps),),
    )


def list_test_pattern_sources(
    *,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> list[ProviderInfo]:
    return [describe_source_id(f"test:{pid}", width=width, height=height, fps=fps) for pid in _PATTERN_IDS]


def list_usb_sources(
    *,
    max_probe: int = 8,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> list[ProviderInfo]:
    try:
        import cv2  # type: ignore
    except ImportError:
        return []
    out: list[ProviderInfo] = []
    for index in range(max_probe):
        cap = cv2.VideoCapture(index)
        try:
            if cap.isOpened():
                out.append(describe_source_id(f"usb:{index}", width=width, height=height, fps=fps))
        finally:
            cap.release()
    return out


PATTERN_NAMES: dict[Pattern, str] = {
    Pattern(pid): describe_source_id(f"test:{pid}").name for pid in _PATTERN_IDS
}
