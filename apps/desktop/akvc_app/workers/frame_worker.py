# SPDX-License-Identifier: Apache-2.0
"""FrameWorker subprocess — owns the FrameBus producer.

Lifecycle:
  parent → spawn(frame_worker_main, source_id, cmd_q, stat_q)
  worker:
    1. open provider
    2. open frame sink (Windows shm) — creates the named mapping/event/mutex
    3. loop: read → pipeline → publish, until "stop" arrives on cmd_q
    4. on exit: close sink (releases mapping when last handle is gone)
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from akvc.core import logging as akvc_log
from akvc.core.frame_pipeline import (
    ColorConvertStage,
    FpsRegulator,
    FramePipeline,
    ResizeStage,
)
from akvc.core.frame_provider import (
    DEFAULT_PROVIDER_FPS,
    DEFAULT_PROVIDER_HEIGHT,
    DEFAULT_PROVIDER_WIDTH,
    FrameProvider,
    create_provider_from_source_id,
)
from akvc.core.frame_sink import create_sink, FrameSink
from akvc.core.metrics import Metrics

log = logging.getLogger(__name__)


@dataclass
class WorkerCommand:
    kind: str  # "stop" | "set_source" | ...
    payload: Optional[Any] = None


def _build_provider(source_id: str) -> FrameProvider:
    return create_provider_from_source_id(
        source_id,
        width=DEFAULT_PROVIDER_WIDTH,
        height=DEFAULT_PROVIDER_HEIGHT,
        fps=DEFAULT_PROVIDER_FPS,
    )


def _start_command_watcher(
    cmd_q: "mp.Queue[WorkerCommand]",
    stop_requested: threading.Event,
    provider: FrameProvider,
) -> threading.Thread:
    def watch_commands() -> None:
        while not stop_requested.is_set():
            cmd = cmd_q.get()
            if cmd.kind != "stop":
                continue
            log.info("akvc.worker.stop_requested")
            stop_requested.set()
            try:
                provider.request_stop()
            except Exception:
                log.exception("akvc.worker.request_stop_failed")
            break

    watcher = threading.Thread(target=watch_commands, name="akvc-worker-cmd", daemon=True)
    watcher.start()
    return watcher


def frame_worker_main(
    source_id: str,
    cmd_q: "mp.Queue[WorkerCommand]",
    stat_q: "mp.Queue[dict]",
    preview_q: "mp.Queue[bytes] | None" = None,
) -> int:
    log_dir = Path.home() / "AppData" / "Local" / "AKVC" / "logs"
    akvc_log.configure(level="INFO", log_dir=log_dir, component="akvc.worker")

    for q in (cmd_q, stat_q, preview_q):
        if q is None:
            continue
        try:
            q.cancel_join_thread()
        except Exception:
            pass

    provider: Optional[FrameProvider] = None
    sink: Optional[FrameSink] = None
    metrics = Metrics()
    stop_requested = threading.Event()
    command_watcher: threading.Thread | None = None

    try:
        provider = _build_provider(source_id)
        provider.open()
        log.info("akvc.worker.provider_open source=%s", source_id)
        command_watcher = _start_command_watcher(cmd_q, stop_requested, provider)

        if sys.platform not in ("win32", "darwin"):
            raise RuntimeError(
                f"worker unsupported on platform: {sys.platform}"
            )

        sink = create_sink()
        sink.open()
        log.info("akvc.worker.sink_open")

        pipeline = (
            FramePipeline()
            .add(ResizeStage(target_w=1280, target_h=720))
            .add(FpsRegulator(target_fps=30.0))
            .add(ColorConvertStage(dst="NV12"))
        )

        last_metrics_t = time.perf_counter()
        last_preview_t = 0.0
        while True:
            if stop_requested.is_set():
                break

            t0 = time.perf_counter()
            frame = provider.read()
            if stop_requested.is_set():
                break

            # Send preview thumbnail (~5 fps) from raw BGR before NV12 conversion.
            if preview_q is not None and time.perf_counter() - last_preview_t > 0.2:
                last_preview_t = time.perf_counter()
                try:
                    if frame.fourcc == 0x20424752 and frame.data.nbytes >= frame.width * frame.height * 3:
                        bgr = frame.data[:frame.width * frame.height * 3].reshape(frame.height, frame.width, 3)
                        import cv2
                        thumb = cv2.resize(bgr, (320, 180), interpolation=cv2.INTER_LINEAR)
                        # Convert BGR→RGB for Qt display.
                        rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
                        preview_q.put_nowait(rgb.tobytes())
                except (queue.Full, Exception):
                    pass

            frame = pipeline.process(frame)
            if stop_requested.is_set():
                break

            try:
                sink.publish(frame)
                metrics.frames_published.inc()
                metrics.fps.tick()
                metrics.last_publish_latency_ms.set((time.perf_counter() - t0) * 1000.0)
            except Exception:
                metrics.frames_dropped.inc()
                log.exception("akvc.worker.publish_failed")

            if time.perf_counter() - last_metrics_t > 0.5:
                snap = metrics.snapshot()
                try:
                    stat_q.put_nowait({"kind": "metrics", **snap,
                                       "consumer_count": sink.consumer_count})
                except queue.Full:
                    pass
                last_metrics_t = time.perf_counter()

        return 0

    except Exception as exc:
        tb = traceback.format_exc()
        log.error("akvc.worker.fatal error=%s", exc)
        try:
            stat_q.put_nowait({"kind": "error", "error": str(exc), "traceback": tb})
        except Exception:
            pass
        return 1
    finally:
        stop_requested.set()
        try:
            if provider is not None:
                provider.request_stop()
        except Exception:
            pass
        try:
            if sink is not None:
                sink.close()
        except Exception:
            pass
        try:
            if provider is not None:
                provider.close()
        except Exception:
            pass
        if command_watcher is not None:
            command_watcher.join(timeout=0.2)
        log.info("akvc.worker.exit")
