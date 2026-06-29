# SPDX-License-Identifier: Apache-2.0
"""FrameProvider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..frame import Frame


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


class FrameProvider(ABC):
    """Abstract source of frames.

    Implementations must be safe to use from a single thread (the FrameWorker
    process). They are NOT required to be thread-safe.
    """

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Frame:
        """Read one frame.

        Must not raise on transient errors; instead return a placeholder
        Frame with FLAG_ERROR set so the pipeline keeps producing output.
        """

    def request_stop(self) -> None:
        return None

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def describe(self) -> ProviderInfo: ...
