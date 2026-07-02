# SPDX-License-Identifier: Apache-2.0
"""ServiceFacade — single entry point for ViewModel layer."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field
from typing import Optional

from akvc._core_native import NativeRuntimeHost

from .helper_service import HelperService
from .source_info import ProviderInfo, list_test_pattern_sources, list_usb_sources

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
    """Facade between Qt ViewModels and native runtime host."""

    def __init__(self) -> None:
        self._state = ServiceState()
        self._runtime = NativeRuntimeHost()
        self._runtime_mu = threading.RLock()
        self._is_windows = sys.platform == "win32"
        self._helper = HelperService() if self._is_windows else None
        self._device_registered = False

    def bootstrap(self) -> None:
        log.info("akvc.facade.bootstrap")
        self._state.sources = self._discover_sources()
        if self._state.sources:
            self._state.selected_source_id = self._state.sources[0].id

    def shutdown(self) -> None:
        log.info("akvc.facade.shutdown")
        self.stop()
        if self._helper is not None:
            try:
                self._helper.stop()
            except Exception:
                pass
        self._device_registered = False

    def list_sources(self) -> list[ProviderInfo]:
        return list(self._state.sources)

    def select_source(self, source_id: str) -> None:
        self._state.selected_source_id = source_id

    def selected_source(self) -> Optional[str]:
        return self._state.selected_source_id

    def _discover_sources(self) -> list[ProviderInfo]:
        try:
            usb = list_usb_sources(max_probe=4)
        except Exception:  # pragma: no cover
            log.exception("usb probe failed")
            usb = []
        patterns = list_test_pattern_sources()
        return list(usb) + list(patterns)

    def start(self) -> None:
        if self._state.worker_status.running:
            log.info("akvc.facade.start.already_running")
            return
        if not self._state.selected_source_id:
            raise RuntimeError("no source selected")

        if self._is_windows:
            assert self._helper is not None
            helper_was_alive = self._helper.ping()
            if not helper_was_alive:
                self._device_registered = False
            if not self._helper.ensure_running():
                detail = self._helper.last_error_message or "failed to start akvc helper"
                raise RuntimeError(detail)
            if not self._helper.ping():
                raise RuntimeError("akvc helper is not responding")
            if not self._device_registered:
                if self._helper.register_mf(name="AK Virtual Camera"):
                    self._device_registered = True
                    log.info("akvc.facade.mf_registered")
                else:
                    raise RuntimeError("failed to register MF virtual camera")
        else:
            if not self._device_registered:
                log.info("akvc.facade.macos_assume_extension_active")
                self._device_registered = True

        with self._runtime_mu:
            self._runtime.start_source(self._state.selected_source_id)
        self._state.worker_status.running = True
        log.info("akvc.facade.start source=%s", self._state.selected_source_id)

    def stop(self, timeout: float = 5.0) -> None:
        if not self._state.worker_status.running:
            return
        log.info("akvc.facade.stop.begin timeout=%.3f", timeout)
        with self._runtime_mu:
            self._runtime.stop()
        self._state.worker_status.running = False
        log.info("akvc.facade.stop.graceful")

    def poll_status(self) -> WorkerStatus:
        st = self._state.worker_status
        with self._runtime_mu:
            snap = dict(self._runtime.snapshot())
        st.fps = float(snap.get("fps") or 0.0)
        st.frames_published = int(snap.get("frames_published") or 0)
        st.frames_dropped = int(snap.get("frames_dropped") or 0)
        st.consumer_count = int(snap.get("consumer_count") or 0)
        st.last_error = None if snap.get("last_error") is None else str(snap.get("last_error"))
        preview = snap.get("last_preview")
        st.last_preview = None if preview is None else bytes(preview)
        st.running = bool(snap.get("running"))
        return st
