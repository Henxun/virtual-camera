# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time

from akvc._core_native import NativeCounter, NativeGauge, NativeMetrics, NativeRateMeter
from akvc.core.metrics import Counter, Gauge, Metrics, RateMeter


def test_counter_delegates_to_native() -> None:
    counter = Counter("akvc.test", value=2)

    counter.inc()
    counter.inc(3)
    counter.value = 10

    assert isinstance(counter._native, NativeCounter)
    assert counter.name == "akvc.test"
    assert counter.value == 10


def test_gauge_delegates_to_native() -> None:
    gauge = Gauge("akvc.latency", value=1.5)

    gauge.set(2.25)
    gauge.value = 3.5

    assert isinstance(gauge._native, NativeGauge)
    assert gauge.name == "akvc.latency"
    assert gauge.value == 3.5


def test_rate_meter_delegates_to_native() -> None:
    meter = RateMeter("akvc.fps", window_s=1.0)

    meter.tick()
    meter.tick()

    assert isinstance(meter._native, NativeRateMeter)
    assert meter.name == "akvc.fps"
    assert meter.window_s == 1.0
    assert meter.rate() >= 2.0


def test_rate_meter_expires_old_events() -> None:
    meter = RateMeter("akvc.fps", window_s=0.01)
    meter.tick()

    time.sleep(0.03)

    assert meter.rate() == 0.0


def test_metrics_snapshot_matches_legacy_keys_and_rounding() -> None:
    metrics = Metrics()

    metrics.fps.tick()
    metrics.frames_published.inc(3)
    metrics.frames_dropped.inc()
    metrics.last_publish_latency_ms.set(1.23456)

    snapshot = metrics.snapshot()

    assert isinstance(metrics._native, NativeMetrics)
    assert set(snapshot) == {
        "fps",
        "frames_published",
        "frames_dropped",
        "last_publish_latency_ms",
    }
    assert snapshot["fps"] >= 1.0
    assert snapshot["frames_published"] == 3
    assert snapshot["frames_dropped"] == 1
    assert snapshot["last_publish_latency_ms"] == 1.235
