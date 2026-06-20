# SPDX-License-Identifier: Apache-2.0
"""FrameSink interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..frame import Frame


class FrameSink(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def publish(self, frame: Frame) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def consumer_count(self) -> int: ...
