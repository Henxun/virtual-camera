# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time

from akvc._core_native import NativeCounter, NativeGauge, NativeMetrics, NativeRateMeter


def test_native_counter_basic() -> None:
    counter = NativeCounter("akvc.test", 2)

    counter.inc()
    counter.inc(3)
    counter.value = 10

    assert counter.name == "akvc.test"
    assert counter.value == 10


def test_native_gauge_basic() -> None:
    gauge = NativeGauge("akvc.latency", 1.5)

    gauge.set(2.25)
    gauge.value = 3.5

    assert gauge.name == "akvc.latency"
    assert gauge.value == 3.5


def test_native_rate_meter_basic() -> None:
    meter = NativeRateMeter("akvc.fps", 1.0)

    meter.tick()
    meter.tick()

    assert meter.name == "akvc.fps"
    assert meter.window_s == 1.0
    assert meter.rate() >= 2.0


def test_native_rate_meter_expires_old_events() -> None:
    meter = NativeRateMeter("akvc.fps", 0.01)
    meter.tick()

    time.sleep(0.03)

    assert meter.rate() == 0.0


def test_native_metrics_snapshot_matches_expected_keys_and_rounding() -> None:
    metrics = NativeMetrics()

    metrics.fps.tick()
    metrics.frames_published.inc(3)
    metrics.frames_dropped.inc()
    metrics.last_publish_latency_ms.set(1.23456)

    snapshot = metrics.snapshot()

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
