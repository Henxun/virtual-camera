# SPDX-License-Identifier: Apache-2.0
"""Pure-Python runtime host - the desktop frame-push engine.

Replaces the former akvc._core_native NativeRuntimeHost. Runs an in-process
thread that reads frames from a pure-Python provider and pushes them through
the C++ akvc_camera.VirtualCamera binding. Mirrors the NativeRuntimeHost API
(start_source / stop / snapshot) so ServiceFacade needs no changes.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..workers.source_provider import create_provider_from_source_id
from .source_info import DEFAULT_PROVIDER_FPS, DEFAULT_PROVIDER_HEIGHT, DEFAULT_PROVIDER_WIDTH

log = logging.getLogger(__name__)

PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 180


def _import_akvc_camera():
    """Import the akvc_camera pybind module, searching common build locations."""
    try:
        import akvc_camera  # type: ignore
        return akvc_camera
    except ImportError:
        pass
    # Dev checkout: the .pyd lands in build/bin/Release.
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "build" / "bin" / "Release",
        repo_root / "akvc" / "_runtime" / "windows",
    ]
    for cand in candidates:
        if cand.is_dir() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
    try:
        import akvc_camera  # type: ignore
        return akvc_camera
    except ImportError:
        return None


def _find_helper_exe() -> str:
    """Locate akvc_helper.exe (dev build output or packaged runtime)."""
    env = os.environ.get("AKVC_HELPER_EXE")
    if env:
        return env
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "build" / "bin" / "Release" / "akvc_helper.exe",
        repo_root / "akvc" / "_runtime" / "windows" / "akvc_helper.exe",
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return ""


class RuntimeHost:
    """Thread-based frame push loop backed by akvc_camera.VirtualCamera."""

    def __init__(
        self,
        *,
        width: int = DEFAULT_PROVIDER_WIDTH,
        height: int = DEFAULT_PROVIDER_HEIGHT,
        fps: float = DEFAULT_PROVIDER_FPS,
        camera_name: str = "AK Virtual Camera",
        helper_exe: str = "",
    ) -> None:
        self._width = width
        self._height = height
        self._target_fps = fps
        self._camera_name = camera_name
        self._helper_exe = helper_exe or _find_helper_exe()
        self._mu = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._measured_fps = 0.0
        self._frames_published = 0
        self._frames_dropped = 0
        self._consumer_count = 0
        self._last_error: Optional[str] = None
        self._last_preview: bytes = b""

    def start_source(self, source_id: str) -> None:
        self.stop()
        with self._mu:
            self._frames_published = 0
            self._frames_dropped = 0
            self._consumer_count = 0
            self._measured_fps = 0.0
            self._last_error = None
            self._last_preview = b""
            self._running = True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, args=(source_id,), name="akvc-runtime-host", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        self._thread = None
        with self._mu:
            self._running = False

    def snapshot(self) -> dict[str, Any]:
        with self._mu:
            return {
                "running": self._running,
                "fps": float(self._measured_fps),
                "frames_published": int(self._frames_published),
                "frames_dropped": int(self._frames_dropped),
                "consumer_count": int(self._consumer_count),
                "last_error": self._last_error,
                "last_preview": self._last_preview if self._last_preview else None,
            }

    def _set(self, **kw: Any) -> None:
        with self._mu:
            for k, v in kw.items():
                setattr(self, f"_{k}", v)

    def _run_loop(self, source_id: str) -> None:
        akvc_camera = _import_akvc_camera()
        if akvc_camera is None:
            self._set(last_error="akvc_camera module not found (build it via tools/make.py build)")
            self._running = False
            return

        provider = None
        vc = None
        try:
            provider = create_provider_from_source_id(
                source_id, width=self._width, height=self._height, fps=int(self._target_fps)
            )
            provider.open()
            vc = akvc_camera.VirtualCamera(
                self._width, self._height, self._target_fps, self._camera_name, self._helper_exe
            )
            st = vc.start()
            if st != akvc_camera.Status.Ok:
                self._set(last_error=vc.last_error or "VirtualCamera.start failed")
                return

            last_metrics_t = time.perf_counter()
            last_preview_t = 0.0
            published_window = 0

            while not self._stop.is_set():
                t0 = time.perf_counter()
                frame = provider.read()
                if self._stop.is_set():
                    break

                # Preview thumbnail (~5 fps), BGR->RGB for Qt.
                if time.perf_counter() - last_preview_t > 0.2:
                    last_preview_t = time.perf_counter()
                    try:
                        import cv2  # type: ignore
                        thumb = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT), interpolation=cv2.INTER_LINEAR)
                        rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
                        self._set(last_preview=rgb.tobytes())
                    except Exception:
                        pass

                try:
                    r = vc.push_frame(frame)
                    if r != akvc_camera.Status.Ok:
                        raise RuntimeError(vc.last_error or f"push_frame status {r}")
                    consumers = vc.consumer_count
                    with self._mu:
                        self._frames_published += 1
                        self._consumer_count = consumers
                    published_window += 1
                except Exception as exc:
                    with self._mu:
                        self._frames_dropped += 1
                        self._last_error = str(exc)
                    log.exception("akvc.runtime.push_failed")

                now = time.perf_counter()
                elapsed = now - last_metrics_t
                if elapsed >= 0.5:
                    with self._mu:
                        self._measured_fps = published_window / elapsed
                    published_window = 0
                    last_metrics_t = now

        except Exception as exc:
            self._set(last_error=str(exc))
            log.exception("akvc.runtime.fatal")
        finally:
            try:
                if vc is not None:
                    vc.stop()
            except Exception:
                pass
            try:
                if provider is not None:
                    provider.request_stop()
                    provider.close()
            except Exception:
                pass
            with self._mu:
                self._running = False
