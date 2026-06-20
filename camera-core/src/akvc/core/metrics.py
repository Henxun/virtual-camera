# SPDX-License-Identifier: Apache-2.0
"""Lightweight metrics — replaced by OpenTelemetry in Phase 6."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Counter:
    name: str
    value: int = 0

    def inc(self, n: int = 1) -> None:
        self.value += n


@dataclass
class Gauge:
    name: str
    value: float = 0.0

    def set(self, v: float) -> None:
        self.value = v


@dataclass
class RateMeter:
    """Sliding-window rate over the last `window_s` seconds."""

    name: str
    window_s: float = 1.0
    _events: deque[float] = field(default_factory=lambda: deque(maxlen=1024))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def tick(self) -> None:
        now = time.perf_counter()
        with self._lock:
            self._events.append(now)
            cutoff = now - self.window_s
            while self._events and self._events[0] < cutoff:
                self._events.popleft()

    def rate(self) -> float:
        with self._lock:
            if not self._events:
                return 0.0
            now = time.perf_counter()
            cutoff = now - self.window_s
            while self._events and self._events[0] < cutoff:
                self._events.popleft()
            return len(self._events) / self.window_s


@dataclass
class Metrics:
    fps: RateMeter = field(default_factory=lambda: RateMeter("akvc.fps"))
    frames_published: Counter = field(default_factory=lambda: Counter("akvc.frames_published"))
    frames_dropped: Counter = field(default_factory=lambda: Counter("akvc.frames_dropped"))
    last_publish_latency_ms: Gauge = field(
        default_factory=lambda: Gauge("akvc.publish_latency_ms")
    )

    def snapshot(self) -> dict:
        return {
            "fps": round(self.fps.rate(), 2),
            "frames_published": self.frames_published.value,
            "frames_dropped": self.frames_dropped.value,
            "last_publish_latency_ms": round(self.last_publish_latency_ms.value, 3),
        }
