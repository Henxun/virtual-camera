# SPDX-License-Identifier: Apache-2.0
"""macOS virtual camera producer benchmark helper.

This tool focuses on the Python -> SDK -> frame-sink producer path so we can
track a stable baseline before full end-to-end application lab validation is
available. It emits structured JSON that can be compared across machines,
architectures, and future IPC implementations.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))


CameraFactory = Callable[..., Any]
FrameFactory = Callable[[int, int], Any]
Timer = Callable[[], float]
Sleeper = Callable[[float], None]


DEFAULT_BENCHMARK_PROFILES: dict[str, dict[str, float | int | str]] = {
    "720p30": {"name": "720p30", "width": 1280, "height": 720, "fps": 30.0},
    "720p60": {"name": "720p60", "width": 1280, "height": 720, "fps": 60.0},
    "1080p30": {"name": "1080p30", "width": 1920, "height": 1080, "fps": 30.0},
    "1080p60": {"name": "1080p60", "width": 1920, "height": 1080, "fps": 60.0},
    "4k30": {"name": "4k30", "width": 3840, "height": 2160, "fps": 30.0},
    "4k60": {"name": "4k60", "width": 3840, "height": 2160, "fps": 60.0},
}
REQUIRED_BENCHMARK_PROFILE_NAMES = list(DEFAULT_BENCHMARK_PROFILES.keys())


def _default_camera_factory(*, width: int, height: int, fps: float):
    try:
        from akvc.sdk.virtual_camera import VirtualCamera
    except ModuleNotFoundError as exc:
        if exc.name == "numpy":
            raise RuntimeError(
                "macOS benchmark requires numpy. Install benchmark deps first, "
                "for example: python -m pip install numpy opencv-python-headless"
            ) from exc
        raise

    return VirtualCamera(width=width, height=height, fps=fps)


def _default_frame_factory(width: int, height: int):
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "macOS benchmark requires numpy. Install benchmark deps first, "
            "for example: python -m pip install numpy opencv-python-headless"
        ) from exc

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[..., 0] = 48
    frame[..., 1] = 96
    frame[..., 2] = 160
    return frame


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    index = max(0, min(len(values) - 1, int(math.ceil(ratio * len(values))) - 1))
    ordered = sorted(float(value) for value in values)
    return float(ordered[index])


def _max_rss_mb() -> float | None:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        return None
    # On macOS ru_maxrss is bytes.
    return float(usage) / (1024.0 * 1024.0)


def resolve_benchmark_profile(name: str) -> dict[str, float | int | str]:
    normalized = str(name).strip().lower()
    try:
        profile = DEFAULT_BENCHMARK_PROFILES[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown benchmark profile: {name}") from exc
    return dict(profile)


def _send_frames(
    *,
    camera,
    frame,
    frame_count: int,
    interval_seconds: float,
    timer: Timer,
    sleeper: Sleeper,
    capture_latencies: bool,
) -> tuple[int, int, list[float], float]:
    latencies_ms: list[float] = []
    dropped_estimate = 0
    phase_start = timer()
    deadline = phase_start

    for _ in range(frame_count):
        now = timer()
        if interval_seconds > 0 and now < deadline:
            sleeper(deadline - now)
        elif interval_seconds > 0 and now > deadline + interval_seconds:
            dropped_estimate += int((now - deadline) / interval_seconds)
            deadline = now

        t0 = timer()
        camera.send(frame)
        latency_ms = max(0.0, (timer() - t0) * 1000.0)
        if capture_latencies:
            latencies_ms.append(latency_ms)
        deadline += interval_seconds

    wall_seconds = max(timer() - phase_start, 1e-9)
    return frame_count, dropped_estimate, latencies_ms, wall_seconds


def run_benchmark(
    *,
    width: int = 1920,
    height: int = 1080,
    fps: float = 60.0,
    duration: float = 5.0,
    warmup: float = 1.0,
    name: str = "AK Virtual Camera",
    camera_factory: CameraFactory | None = None,
    frame_factory: FrameFactory | None = None,
    timer: Timer = time.perf_counter,
    cpu_timer: Timer = time.process_time,
    sleeper: Sleeper = time.sleep,
    platform_name: str | None = None,
    macos_version: str | None = None,
    machine: str | None = None,
) -> dict[str, object]:
    if fps <= 0:
        raise ValueError("fps must be > 0")
    if duration <= 0:
        raise ValueError("duration must be > 0")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    camera = (camera_factory or _default_camera_factory)(width=width, height=height, fps=fps)
    frame = (frame_factory or _default_frame_factory)(width, height)

    warmup_frames = max(0, int(round(warmup * fps)))
    benchmark_frames = max(1, int(round(duration * fps)))
    interval_seconds = 1.0 / float(fps)
    memory_before_mb = _max_rss_mb()

    camera.start(name=name)
    try:
        if warmup_frames:
            _send_frames(
                camera=camera,
                frame=frame,
                frame_count=warmup_frames,
                interval_seconds=interval_seconds,
                timer=timer,
                sleeper=sleeper,
                capture_latencies=False,
            )

        cpu_before = cpu_timer()
        sent_frames, dropped_estimate, latencies_ms, wall_seconds = _send_frames(
            camera=camera,
            frame=frame,
            frame_count=benchmark_frames,
            interval_seconds=interval_seconds,
            timer=timer,
            sleeper=sleeper,
            capture_latencies=True,
        )
        cpu_seconds = max(cpu_timer() - cpu_before, 0.0)
    finally:
        camera.close()

    memory_after_mb = _max_rss_mb()
    actual_fps = float(sent_frames) / max(wall_seconds, 1e-9)
    average_latency_ms = statistics.fmean(latencies_ms) if latencies_ms else 0.0
    cpu_percent = (cpu_seconds / max(wall_seconds, 1e-9)) * 100.0
    total_scheduled = sent_frames + dropped_estimate
    drop_rate = (float(dropped_estimate) / float(total_scheduled)) if total_scheduled else 0.0
    cpu_target_applies = width == 1920 and height == 1080 and round(fps) == 60

    payload = {
        "scenario": {
            "name": name,
            "input_type": "synthetic_numpy_bgr",
            "width": int(width),
            "height": int(height),
            "fps": float(fps),
            "duration_seconds": float(duration),
            "warmup_seconds": float(warmup),
            "expected_frames": int(benchmark_frames),
        },
        "system": {
            "platform": platform_name or platform.system(),
            "macos_version": macos_version or platform.mac_ver()[0],
            "machine": machine or platform.machine(),
            "python_version": platform.python_version(),
        },
        "metrics": {
            "frames_sent": int(sent_frames),
            "frames_dropped_estimate": int(dropped_estimate),
            "drop_rate": float(drop_rate),
            "wall_seconds": float(wall_seconds),
            "cpu_seconds": float(cpu_seconds),
            "cpu_percent": float(cpu_percent),
            "actual_fps": float(actual_fps),
            "avg_latency_ms": float(average_latency_ms),
            "p95_latency_ms": float(_percentile(latencies_ms, 0.95)),
            "p99_latency_ms": float(_percentile(latencies_ms, 0.99)),
            "memory_before_mb": memory_before_mb,
            "memory_after_mb": memory_after_mb,
            "consumer_count": int(getattr(camera, "consumer_count", 0)),
        },
        "acceptance": {
            "fps_target_met": actual_fps >= float(fps) * 0.98,
            "cpu_target_applies": cpu_target_applies,
            "cpu_target_percent": 10.0 if cpu_target_applies else None,
            "cpu_target_met": (cpu_percent < 10.0) if cpu_target_applies else None,
        },
    }
    return payload


def run_benchmark_matrix(
    *,
    profile_names: list[str] | None = None,
    duration: float = 5.0,
    warmup: float = 1.0,
    name: str = "AK Virtual Camera",
    camera_factory: CameraFactory | None = None,
    frame_factory: FrameFactory | None = None,
    timer: Timer = time.perf_counter,
    cpu_timer: Timer = time.process_time,
    sleeper: Sleeper = time.sleep,
    platform_name: str | None = None,
    macos_version: str | None = None,
    machine: str | None = None,
) -> dict[str, object]:
    selected = profile_names or list(DEFAULT_BENCHMARK_PROFILES)
    required_profiles = list(REQUIRED_BENCHMARK_PROFILE_NAMES)
    selected_set = {str(name) for name in selected}
    required_set = {str(name) for name in required_profiles}
    results: list[dict[str, object]] = []
    fps_targets_met = 0
    cpu_targets_applied = 0
    cpu_targets_met = 0

    for profile_name in selected:
        profile = resolve_benchmark_profile(profile_name)
        payload = run_benchmark(
            width=int(profile["width"]),
            height=int(profile["height"]),
            fps=float(profile["fps"]),
            duration=duration,
            warmup=warmup,
            name=name,
            camera_factory=camera_factory,
            frame_factory=frame_factory,
            timer=timer,
            cpu_timer=cpu_timer,
            sleeper=sleeper,
            platform_name=platform_name,
            macos_version=macos_version,
            machine=machine,
        )
        payload["profile"] = profile
        results.append(payload)
        acceptance = payload.get("acceptance", {})
        if acceptance.get("fps_target_met"):
            fps_targets_met += 1
        if acceptance.get("cpu_target_applies"):
            cpu_targets_applied += 1
            if acceptance.get("cpu_target_met"):
                cpu_targets_met += 1

    summary_acceptance = {
        "profile_count": len(results),
        "required_profile_count": len(required_profiles),
        "required_profiles_present": selected_set == required_set,
        "missing_required_profiles": sorted(required_set - selected_set),
        "unexpected_profiles": sorted(selected_set - required_set),
        "all_fps_targets_met": fps_targets_met == len(results),
        "1080p60_cpu_target_met": any(
            str(item.get("profile", {}).get("name")) == "1080p60"
            and bool(item.get("acceptance", {}).get("cpu_target_met"))
            for item in results
        ),
    }
    return {
        "kind": "benchmark_matrix",
        "profiles": [str(name) for name in selected],
        "results": results,
        "summary": {
            "profiles_run": len(results),
            "fps_targets_met": fps_targets_met,
            "cpu_targets_applied": cpu_targets_applied,
            "cpu_targets_met": cpu_targets_met,
            "benchmark_acceptance": summary_acceptance,
        },
    }


def main(
    argv: list[str] | None = None,
    *,
    camera_factory: CameraFactory | None = None,
    frame_factory: FrameFactory | None = None,
    timer: Timer = time.perf_counter,
    cpu_timer: Timer = time.process_time,
    sleeper: Sleeper = time.sleep,
    platform_name: str | None = None,
    macos_version: str | None = None,
    machine: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS benchmark helper")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--warmup", type=float, default=1.0)
    parser.add_argument("--profile", choices=list(DEFAULT_BENCHMARK_PROFILES), help="Run a named benchmark profile")
    parser.add_argument("--matrix", action="store_true", help="Run the default benchmark profile matrix")
    parser.add_argument("--name", default="AK Virtual Camera")
    parser.add_argument("--output", help="Write JSON payload to this path")
    args = parser.parse_args(argv)

    try:
        if args.matrix:
            payload = run_benchmark_matrix(
                duration=args.duration,
                warmup=args.warmup,
                name=args.name,
                camera_factory=camera_factory,
                frame_factory=frame_factory,
                timer=timer,
                cpu_timer=cpu_timer,
                sleeper=sleeper,
                platform_name=platform_name,
                macos_version=macos_version,
                machine=machine,
            )
        elif args.profile:
            profile = resolve_benchmark_profile(args.profile)
            payload = run_benchmark(
                width=int(profile["width"]),
                height=int(profile["height"]),
                fps=float(profile["fps"]),
                duration=args.duration,
                warmup=args.warmup,
                name=args.name,
                camera_factory=camera_factory,
                frame_factory=frame_factory,
                timer=timer,
                cpu_timer=cpu_timer,
                sleeper=sleeper,
                platform_name=platform_name,
                macos_version=macos_version,
                machine=machine,
            )
            payload["profile"] = profile
        else:
            payload = run_benchmark(
                width=args.width,
                height=args.height,
                fps=args.fps,
                duration=args.duration,
                warmup=args.warmup,
                name=args.name,
                camera_factory=camera_factory,
                frame_factory=frame_factory,
                timer=timer,
                cpu_timer=cpu_timer,
                sleeper=sleeper,
                platform_name=platform_name,
                macos_version=macos_version,
                machine=machine,
            )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
