# SPDX-License-Identifier: Apache-2.0
"""MainViewModel — single source of truth for the main window.

Pure view-model: does not know about Qt widgets, only Qt signals/properties.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from ..services.facade import ServiceFacade


class _LifecycleWorker(QObject):
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(self, action: str, operation: Callable[[], None]) -> None:
        super().__init__()
        self._action = action
        self._operation = operation

    @Slot()
    def run(self) -> None:
        try:
            self._operation()
        except Exception as exc:
            self.failed.emit(self._action, str(exc))
            return
        self.finished.emit(self._action)


class MainViewModel(QObject):
    sources_changed = Signal(list)        # list[(id, name)]
    selected_source_changed = Signal(str)
    running_changed = Signal(bool)
    busy_changed = Signal(bool)
    state_text_changed = Signal(str)
    metrics_changed = Signal(dict)
    install_status_changed = Signal(dict)
    preview_changed = Signal(object)      # QPixmap
    error = Signal(str)

    def __init__(self, facade: ServiceFacade, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._running: bool | None = None
        self._busy = False
        self._state_text: str | None = None
        self._lifecycle_thread: QThread | None = None
        self._lifecycle_worker: _LifecycleWorker | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start()

        # Sources are populated by the View (MainWindow) calling
        # refresh_sources() after it wires signal connections.

    # ---------- commands ----------

    def _emit_install_status(self, st) -> None:
        self.install_status_changed.emit(
            {
                "state": st.install_state,
                "phase": st.install_phase,
                "devices": list(st.install_devices),
                "all_devices": list(st.install_all_devices),
                "device_prefix": st.install_device_prefix,
                "approval_required": st.approval_required,
                "enabled": st.install_enabled,
                "supported_formats": list(st.supported_formats),
                "supported_frame_rates": list(st.supported_frame_rates),
                "runtime_topology_kind": st.runtime_topology_kind,
                "runtime_frame_path": st.runtime_frame_path,
                "runtime_host_role": st.runtime_host_role,
                "runtime_host_in_frame_hot_path": st.runtime_host_in_frame_hot_path,
                "runtime_dedicated_host_daemon_required": st.runtime_dedicated_host_daemon_required,
                "runtime_container_app_configured": st.runtime_container_app_configured,
                "runtime_data_plane": st.runtime_data_plane,
                "runtime_control_plane": st.runtime_control_plane,
                "ipc_transport": st.ipc_transport,
                "ipc_probe_present": st.ipc_probe_present,
                "ipc_ready": st.ipc_ready,
                "ipc_environment_blocked": st.ipc_environment_blocked,
                "ipc_last_error": st.ipc_last_error,
                "ipc_probe_path": st.ipc_probe_path,
                "ipc_direct_open_errno": st.ipc_direct_open_errno,
                "install_blocker_code": st.install_blocker_code,
                "message": st.install_message,
                "steps": list(st.install_steps),
                "verification_targets": list(st.verification_targets),
                "manual_app_validation_present": bool(getattr(st, "manual_app_validation_present", False)),
                "manual_app_validation_ready": getattr(st, "manual_app_validation_ready", None),
                "manual_app_validation_failed_criteria": list(
                    getattr(st, "manual_app_validation_failed_criteria", [])
                ),
                "manual_app_validation_failed_labels": list(
                    getattr(st, "manual_app_validation_failed_labels", [])
                ),
                "manual_app_validation_unknown_criteria": list(
                    getattr(st, "manual_app_validation_unknown_criteria", [])
                ),
                "manual_app_validation_unknown_labels": list(
                    getattr(st, "manual_app_validation_unknown_labels", [])
                ),
                "manual_app_validation_blockers": list(
                    getattr(st, "manual_app_validation_blockers", [])
                ),
                "manual_app_validation_blocker_labels": list(
                    getattr(st, "manual_app_validation_blocker_labels", [])
                ),
                "manual_app_validation_manifest_path": str(
                    getattr(st, "manual_app_validation_manifest_path", "") or ""
                ),
                "can_open_settings": st.can_open_settings,
                "stream_start_ready": st.stream_start_ready,
                "stream_start_message": st.stream_start_message,
                "last_error": st.last_error or "",
            }
        )

    @Slot()
    def refresh_sources(self) -> None:
        srcs = [(s.id, s.name) for s in self._facade.list_sources()]
        self.sources_changed.emit(srcs)
        sel = self._facade.selected_source()
        if sel:
            self.selected_source_changed.emit(sel)

    @Slot(str)
    def select_source(self, source_id: str) -> None:
        if self._busy:
            return
        self._facade.select_source(source_id)
        self.selected_source_changed.emit(source_id)

    @Slot()
    def start(self) -> None:
        if self._busy or self._running:
            return
        self._begin_lifecycle("start", "Starting…", self._facade.start)

    @Slot()
    def stop(self) -> None:
        if self._busy or not self._running:
            return
        self._begin_lifecycle("stop", "Stopping…", self._facade.stop)

    # ---------- lifecycle ----------

    def _begin_lifecycle(self, action: str, state_text: str, operation: Callable[[], None]) -> None:
        self._set_busy(True)
        self._set_state_text(state_text)
        self._poll_timer.stop()
        self._launch_lifecycle(action, operation)

    def _launch_lifecycle(self, action: str, operation: Callable[[], None]) -> None:
        thread = QThread(self)
        worker = _LifecycleWorker(action, operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_lifecycle_finished)
        worker.failed.connect(self._on_lifecycle_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._clear_lifecycle_worker)
        thread.finished.connect(thread.deleteLater)
        self._lifecycle_thread = thread
        self._lifecycle_worker = worker
        thread.start()

    @Slot(str)
    def _on_lifecycle_finished(self, action: str) -> None:
        self._set_running(action == "start")
        self._finish_lifecycle()

    @Slot(str, str)
    def _on_lifecycle_failed(self, action: str, message: str) -> None:
        if action == "start":
            self._set_running(False)
        self._finish_lifecycle()
        self.error.emit(message)

    @Slot()
    def _clear_lifecycle_worker(self) -> None:
        self._lifecycle_thread = None
        self._lifecycle_worker = None

    def _finish_lifecycle(self) -> None:
        self._set_busy(False)
        self._set_state_text("Streaming" if bool(self._running) else "Idle")
        self._poll_timer.start()
        self._poll_status()

    @Slot()
    def install_virtual_camera(self) -> None:
        try:
            st = self._facade.install_virtual_camera()
            self._emit_install_status(st)
        except Exception as exc:
            self.error.emit(str(exc))

    @Slot()
    def open_install_settings(self) -> None:
        try:
            if not self._facade.open_install_settings():
                st = self._facade.poll_status()
                if st.last_error:
                    self.error.emit(st.last_error)
                    return
            st = self._facade.poll_status()
            self._emit_install_status(st)
        except Exception as exc:
            self.error.emit(str(exc))

    @Slot()
    def recheck_install_status(self) -> None:
        try:
            st = self._facade.recheck_install_status()
            self._emit_install_status(st)
        except Exception as exc:
            self.error.emit(str(exc))

    # ---------- polling ----------

    def _set_running(self, running: bool) -> None:
        if self._running == running:
            return
        self._running = running
        if not self._busy:
            self._set_state_text("Streaming" if running else "Idle")
        self.running_changed.emit(running)

    def _set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        self.busy_changed.emit(busy)

    def _set_state_text(self, text: str) -> None:
        if self._state_text == text:
            return
        self._state_text = text
        self.state_text_changed.emit(text)

    def _poll_status(self) -> None:
        st = self._facade.poll_status()
        self.metrics_changed.emit(
            {
                "fps": st.fps,
                "published": st.frames_published,
                "dropped": st.frames_dropped,
                "consumers": st.consumer_count,
                "running": st.running,
                "last_error": st.last_error or "",
                "install_state": st.install_state,
                "install_phase": st.install_phase,
                "install_devices": list(st.install_devices),
                "install_all_devices": list(st.install_all_devices),
                "install_device_prefix": st.install_device_prefix,
                "approval_required": st.approval_required,
                "install_enabled": st.install_enabled,
                "supported_formats": list(st.supported_formats),
                "supported_frame_rates": list(st.supported_frame_rates),
                "runtime_topology_kind": st.runtime_topology_kind,
                "runtime_frame_path": st.runtime_frame_path,
                "runtime_host_role": st.runtime_host_role,
                "runtime_host_in_frame_hot_path": st.runtime_host_in_frame_hot_path,
                "runtime_dedicated_host_daemon_required": st.runtime_dedicated_host_daemon_required,
                "runtime_container_app_configured": st.runtime_container_app_configured,
                "runtime_data_plane": st.runtime_data_plane,
                "runtime_control_plane": st.runtime_control_plane,
                "ipc_transport": st.ipc_transport,
                "ipc_probe_present": st.ipc_probe_present,
                "ipc_ready": st.ipc_ready,
                "ipc_environment_blocked": st.ipc_environment_blocked,
                "ipc_last_error": st.ipc_last_error,
                "ipc_probe_path": st.ipc_probe_path,
                "ipc_direct_open_errno": st.ipc_direct_open_errno,
                "install_blocker_code": st.install_blocker_code,
                "install_message": st.install_message,
                "install_steps": list(st.install_steps),
                "verification_targets": list(st.verification_targets),
                "manual_app_validation_present": bool(getattr(st, "manual_app_validation_present", False)),
                "manual_app_validation_ready": getattr(st, "manual_app_validation_ready", None),
                "manual_app_validation_failed_criteria": list(
                    getattr(st, "manual_app_validation_failed_criteria", [])
                ),
                "manual_app_validation_failed_labels": list(
                    getattr(st, "manual_app_validation_failed_labels", [])
                ),
                "manual_app_validation_unknown_criteria": list(
                    getattr(st, "manual_app_validation_unknown_criteria", [])
                ),
                "manual_app_validation_unknown_labels": list(
                    getattr(st, "manual_app_validation_unknown_labels", [])
                ),
                "manual_app_validation_blockers": list(
                    getattr(st, "manual_app_validation_blockers", [])
                ),
                "manual_app_validation_blocker_labels": list(
                    getattr(st, "manual_app_validation_blocker_labels", [])
                ),
                "manual_app_validation_manifest_path": str(
                    getattr(st, "manual_app_validation_manifest_path", "") or ""
                ),
                "can_open_settings": st.can_open_settings,
                "stream_start_ready": st.stream_start_ready,
                "stream_start_message": st.stream_start_message,
            }
        )
        self._emit_install_status(st)
        if st.last_preview:
            pix = QPixmap.fromImage(
                QImage(st.last_preview, 320, 180, QImage.Format.Format_RGB888)
            )
            self.preview_changed.emit(pix)
        self._set_running(st.running)
