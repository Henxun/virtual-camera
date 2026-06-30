# SPDX-License-Identifier: Apache-2.0
"""Lightweight metrics — replaced by OpenTelemetry in Phase 6."""

from __future__ import annotations

from akvc._core_native import NativeCounter, NativeGauge, NativeMetrics, NativeRateMeter


class Counter:
    def __init__(self, name: str, value: int = 0) -> None:
        self._native = NativeCounter(name, value)

    @property
    def name(self) -> str:
        return self._native.name

    @property
    def value(self) -> int:
        return int(self._native.value)

    @value.setter
    def value(self, value: int) -> None:
        self._native.value = int(value)

    def inc(self, n: int = 1) -> None:
        self._native.inc(n)


class Gauge:
    def __init__(self, name: str, value: float = 0.0) -> None:
        self._native = NativeGauge(name, value)

    @property
    def name(self) -> str:
        return self._native.name

    @property
    def value(self) -> float:
        return float(self._native.value)

    @value.setter
    def value(self, value: float) -> None:
        self._native.value = float(value)

    def set(self, v: float) -> None:
        self._native.set(v)


class RateMeter:
    """Sliding-window rate over the last `window_s` seconds."""

    def __init__(self, name: str, window_s: float = 1.0) -> None:
        self._native = NativeRateMeter(name, window_s)

    @property
    def name(self) -> str:
        return self._native.name

    @property
    def window_s(self) -> float:
        return float(self._native.window_s)

    @window_s.setter
    def window_s(self, value: float) -> None:
        self._native.window_s = float(value)

    def tick(self) -> None:
        self._native.tick()

    def rate(self) -> float:
        return float(self._native.rate())


class Metrics:
    def __init__(self) -> None:
        self._native = NativeMetrics()
        self.fps = self._native.fps
        self.frames_published = self._native.frames_published
        self.frames_dropped = self._native.frames_dropped
        self.last_publish_latency_ms = self._native.last_publish_latency_ms

    def snapshot(self) -> dict:
        return dict(self._native.snapshot())
