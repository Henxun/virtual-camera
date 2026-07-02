# SPDX-License-Identifier: Apache-2.0
"""App-side provider contracts and native source metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from akvc._core_native import (
    describe_source_id as _describe_source_id,
    list_pattern_ids as _list_pattern_ids,
    list_test_pattern_sources as _list_test_pattern_sources,
    list_usb_sources as _list_usb_sources,
    parse_source_id,
)

DEFAULT_PROVIDER_WIDTH = 1280
DEFAULT_PROVIDER_HEIGHT = 720
DEFAULT_PROVIDER_FPS = 30


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


def format_spec_from_native(native: Any) -> FormatSpec:
    return FormatSpec(
        fourcc=int(native.fourcc),
        width=int(native.width),
        height=int(native.height),
        fps_num=int(native.fps_num),
        fps_den=int(native.fps_den),
    )


def provider_info_from_native(native: Any) -> ProviderInfo:
    return ProviderInfo(
        id=str(native.id),
        name=str(native.name),
        formats=tuple(format_spec_from_native(item) for item in native.formats),
    )


PATTERN_NAMES: dict[Pattern, str] = {
    Pattern(pattern_id): provider_info_from_native(_describe_source_id(f"test:{pattern_id}")).name
    for pattern_id in _list_pattern_ids()
}


def list_pattern_ids() -> list[str]:
    return list(_list_pattern_ids())


def describe_source_id(
    source_id: str,
    *,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> ProviderInfo:
    return provider_info_from_native(_describe_source_id(source_id, width, height, fps))


def list_test_pattern_sources(
    *,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> list[ProviderInfo]:
    return [provider_info_from_native(item) for item in _list_test_pattern_sources(width, height, fps)]


def list_usb_sources(
    *,
    max_probe: int = 8,
    width: int = DEFAULT_PROVIDER_WIDTH,
    height: int = DEFAULT_PROVIDER_HEIGHT,
    fps: int = DEFAULT_PROVIDER_FPS,
) -> list[ProviderInfo]:
    return [provider_info_from_native(item) for item in _list_usb_sources(max_probe, width, height, fps)]
