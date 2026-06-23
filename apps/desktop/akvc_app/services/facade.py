# SPDX-License-Identifier: Apache-2.0
"""ServiceFacade — single entry point for ViewModel layer."""

from __future__ import annotations

import logging
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from akvc.core.frame_provider import (
    Pattern,
    ProviderInfo,
    TestPatternProvider,
    UsbCameraProvider,
)
from akvc.core.helper.client import HelperService

from ..workers.frame_worker import WorkerCommand, frame_worker_main

log = logging.getLogger(__name__)


@dataclass
class WorkerStatus:
    running: bool = False
    fps: float = 0.0
    frames_published: int = 0
    frames_dropped: int = 0
    consumer_count: int = 0
    last_preview: bytes | None = None  # raw BGR 320×180 thumbnail bytes
    last_error: Optional[str] = None


@dataclass
class ServiceState:
    sources: list[ProviderInfo] = field(default_factory=list)
    selected_source_id: Optional[str] = None
    worker_status: WorkerStatus = field(default_factory=WorkerStatus)


class ServiceFacade:
    """Facade between Qt ViewModels and camera-core / FrameWorker subprocess."""

    def __init__(self) -> None:
        self._state = ServiceState()
        self._proc: Optional[mp.Process] = None
        self._cmd_q: Optional[mp.Queue] = None
        self._stat_q: Optional[mp.Queue] = None
        self._preview_q: Optional[mp.Queue] = None
        # HelperService is Windows-only (it spawns akvc_helper.exe which
        # registers the MF VirtualCamera and owns the Global\ shared memory).
        # On macOS the Camera Extension is activated by a native host app
        # (see virtualcam/macos/host); the Python side just publishes frames
        # to the POSIX shm region. Phase 4 will wire the host-app activation
        # through a small native bridge — until then macOS start() opens the
        # sink directly.
        self._is_windows = sys.platform == "win32"
        self._helper = HelperService() if self._is_windows else None
        self._device_registered = False

    # ---------- lifecycle ----------

    def bootstrap(self) -> None:
        log.info("akvc.facade.bootstrap")
        self._state.sources = self._discover_sources()
        if self._state.sources:
            self._state.selected_source_id = self._state.sources[0].id

    def shutdown(self) -> None:
        log.info("akvc.facade.shutdown")
        self.stop()
        # Tear down the helper so the MF VirtualCamera is cleanly removed
        # (Stop + Remove) and no stale device node lingers. (Windows only.)
        if self._helper is not None:
            try:
                self._helper.stop()
            except Exception:
                pass
        self._device_registered = False

    # ---------- source management ----------

    def list_sources(self) -> list[ProviderInfo]:
        return list(self._state.sources)

    def select_source(self, source_id: str) -> None:
        self._state.selected_source_id = source_id

    def selected_source(self) -> Optional[str]:
        return self._state.selected_source_id

    def _discover_sources(self) -> list[ProviderInfo]:
        try:
            usb = UsbCameraProvider.list_devices(max_probe=4)
        except Exception:  # pragma: no cover
            log.exception("usb probe failed")
            usb = []
        # Built-in test patterns.
        patterns: list[ProviderInfo] = []
        for p in Pattern:
            patterns.append(TestPatternProvider(pattern=p).describe())
        return list(usb) + patterns

    # ---------- start / stop ----------

    def start(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            log.info("akvc.facade.start.already_running")
            return
        if not self._state.selected_source_id:
            raise RuntimeError("no source selected")

        if self._is_windows:
            # Ensure Helper is running (owns the Frame Bus).
            assert self._helper is not None
            if not self._helper.start():
                log.warning("akvc.facade.start.helper_unavailable")
            elif not self._device_registered:
                # Register MF virtual camera once (it persists for the helper's
                # lifetime; re-registering on every Start() would conflict with
                # the existing device and make it disappear from Chrome).
                if self._helper.register_mf(name="AK Virtual Camera"):
                    self._device_registered = True
                    log.info("akvc.facade.mf_registered")
                else:
                    log.warning("akvc.facade.mf_registration_failed")
        else:
            # macOS: the Camera Extension is activated out-of-band by the
            # native host app. The Python producer just opens the POSIX shm
            # sink inside the worker. # VERIFY: Phase 4 will add a host-app
            # activation hook here once the Swift bridge exists.
            if not self._device_registered:
                log.info("akvc.facade.macos_assume_extension_active")
                self._device_registered = True

        ctx = mp.get_context("spawn")
        self._cmd_q = ctx.Queue(maxsize=8)
        self._stat_q = ctx.Queue(maxsize=64)
        self._preview_q = ctx.Queue(maxsize=4)
        self._proc = ctx.Process(
            target=frame_worker_main,
            args=(self._state.selected_source_id, self._cmd_q, self._stat_q, self._preview_q),
            daemon=True,
            name="akvc-frame-worker",
        )
        self._proc.start()
        self._state.worker_status.running = True
        log.info(
            "akvc.facade.start pid=%s source=%s",
            self._proc.pid,
            self._state.selected_source_id,
        )

    def stop(self, timeout: float = 5.0) -> None:
        if self._proc is None:
            return
        try:
            if self._cmd_q is not None:
                self._cmd_q.put_nowait(WorkerCommand("stop"))
        except Exception:
            pass
        self._proc.join(timeout=timeout)
        if self._proc.is_alive():
            log.warning("akvc.facade.stop.killed")
            self._proc.terminate()
            self._proc.join(timeout=2.0)
        self._proc = None
        self._cmd_q = None
        self._stat_q = None
        self._state.worker_status.running = False

    def poll_status(self) -> WorkerStatus:
        st = self._state.worker_status
        if self._stat_q is None:
            return st
        try:
            while True:
                msg = self._stat_q.get_nowait()
                kind = msg.get("kind")
                if kind == "metrics":
                    st.fps = float(msg.get("fps", 0.0))
                    st.frames_published = int(msg.get("frames_published", 0))
                    st.frames_dropped = int(msg.get("frames_dropped", 0))
                    st.consumer_count = int(msg.get("consumer_count", 0))
                elif kind == "error":
                    st.last_error = str(msg.get("error", ""))
        except Exception:
            pass
        # Drain preview queue.
        if self._preview_q is not None:
            try:
                while True:
                    st.last_preview = self._preview_q.get_nowait()
            except Exception:
                pass
        st.running = bool(self._proc and self._proc.is_alive())
        return st
