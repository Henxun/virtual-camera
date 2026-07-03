# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS benchmark helper."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_benchmark.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("macos_benchmark_tool", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClock:
    def __init__(self) -> None:
        self.wall = 0.0
        self.cpu = 0.0

    def perf_counter(self) -> float:
        return self.wall

    def process_time(self) -> float:
        return self.cpu

    def sleep(self, seconds: float) -> None:
        self.wall += max(0.0, float(seconds))


class FakeCamera:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.sent_frames = 0
        self.started = False
        self.closed = False
        self.consumer_count = 1

    def start(self, name: str = "AK Virtual Camera") -> None:
        del name
        self.started = True

    def send(self, frame) -> None:
        del frame
        self.sent_frames += 1
        self._clock.wall += 0.002
        self._clock.cpu += 0.001

    def close(self) -> None:
        self.closed = True


def test_macos_benchmark_tool_exists_and_declares_expected_entrypoints() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "def run_benchmark(" in text
    assert "def main(" in text
    assert "process_time" in text
    assert "VirtualCamera" in text
    assert "--width" in text
    assert "--height" in text
    assert "--fps" in text
    assert "--duration" in text
    assert "--warmup" in text
    assert "--profile" in text
    assert "--matrix" in text
    assert "--output" in text


def test_run_benchmark_returns_structured_metrics() -> None:
    module = _load_module()
    clock = FakeClock()
    created = {}

    def camera_factory(*, width: int, height: int, fps: float):
        created["args"] = (width, height, fps)
        cam = FakeCamera(clock)
        created["camera"] = cam
        return cam

    payload = module.run_benchmark(
        width=1920,
        height=1080,
        fps=60.0,
        duration=1.0,
        warmup=0.0,
        camera_factory=camera_factory,
        frame_factory=lambda width, height: {"width": width, "height": height},
        timer=clock.perf_counter,
        cpu_timer=clock.process_time,
        sleeper=clock.sleep,
        platform_name="macOS",
        macos_version="14.0",
        machine="arm64",
    )

    assert created["args"] == (1920, 1080, 60.0)
    assert created["camera"].started is True
    assert created["camera"].closed is True
    assert payload["scenario"]["width"] == 1920
    assert payload["scenario"]["height"] == 1080
    assert payload["scenario"]["fps"] == 60.0
    assert payload["metrics"]["frames_sent"] == 60
    assert payload["metrics"]["frames_dropped_estimate"] >= 0
    assert payload["metrics"]["avg_latency_ms"] > 0
    assert payload["metrics"]["cpu_percent"] > 0
    assert payload["system"]["platform"] == "macOS"
    assert payload["system"]["machine"] == "arm64"
    assert payload["acceptance"]["fps_target_met"] is True
    assert payload["acceptance"]["cpu_target_applies"] is True
    assert payload["acceptance"]["cpu_target_met"] is True


def test_main_writes_json_output_file() -> None:
    module = _load_module()
    clock = FakeClock()
    output = ROOT / "build" / "test-macos-benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    def camera_factory(*, width: int, height: int, fps: float):
        del width, height, fps
        return FakeCamera(clock)

    rc = module.main(
        [
            "--width", "1280",
            "--height", "720",
            "--fps", "30",
            "--duration", "1",
            "--warmup", "0",
            "--output", str(output),
        ],
        camera_factory=camera_factory,
        frame_factory=lambda width, height: [width, height],
        timer=clock.perf_counter,
        cpu_timer=clock.process_time,
        sleeper=clock.sleep,
        platform_name="macOS",
        macos_version="13.0",
        machine="x86_64",
    )

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scenario"]["width"] == 1280
    assert payload["scenario"]["height"] == 720
    assert payload["system"]["machine"] == "x86_64"


def test_main_returns_2_on_runtime_error() -> None:
    module = _load_module()
    stderr = io.StringIO()

    with contextlib.redirect_stderr(stderr):
        rc = module.main(
            ["--duration", "1"],
            camera_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("numpy missing")),
        )

    assert rc == 2
    assert "numpy missing" in stderr.getvalue()


def test_benchmark_profile_lookup_returns_expected_dimensions() -> None:
    module = _load_module()

    profile = module.resolve_benchmark_profile("4k60")

    assert profile["name"] == "4k60"
    assert profile["width"] == 3840
    assert profile["height"] == 2160
    assert profile["fps"] == 60.0


def test_run_benchmark_matrix_returns_summary_for_all_profiles() -> None:
    module = _load_module()
    clock = FakeClock()
    created = []

    def camera_factory(*, width: int, height: int, fps: float):
        created.append((width, height, fps))
        return FakeCamera(clock)

    payload = module.run_benchmark_matrix(
        profile_names=["720p30", "1080p60", "4k30"],
        duration=1.0,
        warmup=0.0,
        camera_factory=camera_factory,
        frame_factory=lambda width, height: {"width": width, "height": height},
        timer=clock.perf_counter,
        cpu_timer=clock.process_time,
        sleeper=clock.sleep,
        platform_name="macOS",
        macos_version="15.0",
        machine="arm64",
    )

    assert payload["kind"] == "benchmark_matrix"
    assert payload["profiles"] == ["720p30", "1080p60", "4k30"]
    assert len(payload["results"]) == 3
    assert created == [
        (1280, 720, 30.0),
        (1920, 1080, 60.0),
        (3840, 2160, 30.0),
    ]
    assert payload["summary"]["profiles_run"] == 3
    assert payload["summary"]["fps_targets_met"] == 3
    assert payload["summary"]["cpu_targets_applied"] == 1
    assert payload["summary"]["cpu_targets_met"] == 1
    assert payload["summary"]["benchmark_acceptance"]["profile_count"] == 3
    assert payload["summary"]["benchmark_acceptance"]["required_profile_count"] == 6
    assert payload["summary"]["benchmark_acceptance"]["required_profiles_present"] is False
    assert payload["summary"]["benchmark_acceptance"]["missing_required_profiles"] == [
        "4k60",
        "720p60",
        "1080p30",
    ]
    assert payload["summary"]["benchmark_acceptance"]["unexpected_profiles"] == []
    assert payload["summary"]["benchmark_acceptance"]["1080p60_cpu_target_met"] is True


def test_main_writes_matrix_json_output_file(tmp_path) -> None:
    module = _load_module()
    clock = FakeClock()
    output = tmp_path / "benchmark-matrix.json"

    def camera_factory(*, width: int, height: int, fps: float):
        del width, height, fps
        return FakeCamera(clock)

    rc = module.main(
        [
            "--matrix",
            "--duration", "1",
            "--warmup", "0",
            "--output", str(output),
        ],
        camera_factory=camera_factory,
        frame_factory=lambda width, height: [width, height],
        timer=clock.perf_counter,
        cpu_timer=clock.process_time,
        sleeper=clock.sleep,
        platform_name="macOS",
        macos_version="14.4",
        machine="arm64",
    )

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["kind"] == "benchmark_matrix"
    assert payload["profiles"] == ["720p30", "720p60", "1080p30", "1080p60", "4k30", "4k60"]
    assert payload["summary"]["profiles_run"] == 6
    assert payload["summary"]["benchmark_acceptance"]["required_profile_count"] == 6
    assert payload["summary"]["benchmark_acceptance"]["required_profiles_present"] is True
    assert payload["summary"]["benchmark_acceptance"]["missing_required_profiles"] == []
    assert payload["summary"]["benchmark_acceptance"]["unexpected_profiles"] == []
