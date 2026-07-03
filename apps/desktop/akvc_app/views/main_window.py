# SPDX-License-Identifier: Apache-2.0
"""Main window — pure View, talks only to MainViewModel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..viewmodels.main_vm import MainViewModel


class MainWindow(QMainWindow):
    def __init__(self, vm: MainViewModel) -> None:
        super().__init__()
        self.vm = vm
        self._running = False
        self._busy = False
        self.setWindowTitle("AK Virtual Camera")
        self.resize(640, 720)

        # Source selector
        self._source_combo = QComboBox(self)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)

        # Start/Stop
        self._btn_install = QPushButton("Install", self)
        self._btn_open_settings = QPushButton("Open Settings", self)
        self._btn_recheck_install = QPushButton("Recheck", self)
        self._btn_start = QPushButton("Start", self)
        self._btn_stop = QPushButton("Stop", self)
        self._btn_install.clicked.connect(self.vm.install_virtual_camera)
        self._btn_open_settings.clicked.connect(self.vm.open_install_settings)
        self._btn_recheck_install.clicked.connect(self.vm.recheck_install_status)
        self._btn_start.clicked.connect(self.vm.start)
        self._btn_stop.clicked.connect(self.vm.stop)
        self._btn_stop.setEnabled(False)
        self._btn_open_settings.setEnabled(False)
        self._btn_start.setToolTip("")

        # Status labels
        self._lbl_state = QLabel("Idle", self)
        self._lbl_install = QLabel("Install: unknown", self)
        self._lbl_install_hint = QLabel("", self)
        self._lbl_install_hint.setWordWrap(True)
        self._lbl_install_steps = QLabel("", self)
        self._lbl_install_steps.setWordWrap(True)
        self._lbl_verification = QLabel("", self)
        self._lbl_verification.setWordWrap(True)
        self._lbl_fps = QLabel("FPS: 0.00", self)
        self._lbl_published = QLabel("Published: 0", self)
        self._lbl_dropped = QLabel("Dropped: 0", self)

        # Preview area
        self._preview_label = QLabel(self)
        self._preview_label.setFixedSize(320, 180)
        self._preview_label.setStyleSheet(
            "background-color: #1a1a1a; border: 1px solid #444;"
        )
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setText("Preview")
        self._preview_label.hide()

        # Layout
        srcgrp = QGroupBox("Source", self)
        srclay = QHBoxLayout(srcgrp)
        srclay.addWidget(self._source_combo, 1)

        ctrlgrp = QGroupBox("Control", self)
        ctrllay = QHBoxLayout(ctrlgrp)
        ctrllay.addWidget(self._btn_install)
        ctrllay.addWidget(self._btn_open_settings)
        ctrllay.addWidget(self._btn_recheck_install)
        ctrllay.addWidget(self._btn_start)
        ctrllay.addWidget(self._btn_stop)

        statgrp = QGroupBox("Status", self)
        statlay = QVBoxLayout(statgrp)
        statlay.addWidget(self._lbl_state)
        statlay.addWidget(self._lbl_install)
        statlay.addWidget(self._lbl_install_hint)
        statlay.addWidget(self._lbl_install_steps)
        statlay.addWidget(self._lbl_verification)
        statlay.addWidget(self._lbl_fps)
        statlay.addWidget(self._lbl_published)
        statlay.addWidget(self._lbl_dropped)

        central = QWidget(self)
        lay = QVBoxLayout(central)
        lay.addWidget(srcgrp)
        lay.addWidget(ctrlgrp)
        lay.addWidget(statgrp)
        lay.addWidget(self._preview_label, alignment=Qt.AlignCenter)
        lay.addStretch(1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready. Select a source and click Start.")

        # Wire VM signals
        self.vm.sources_changed.connect(self._on_sources)
        self.vm.selected_source_changed.connect(self._on_selected_source)
        self.vm.running_changed.connect(self._on_running)
        self.vm.busy_changed.connect(self._on_busy_changed)
        self.vm.state_text_changed.connect(self._on_state_text_changed)
        self.vm.metrics_changed.connect(self._on_metrics)
        self.vm.install_status_changed.connect(self._on_install_status)
        self.vm.preview_changed.connect(self._on_preview)
        self.vm.error.connect(self._on_error)

        # Populate sources after signal connections are established.
        self.vm.refresh_sources()
        self._sync_controls()

    @Slot(list)
    def _on_sources(self, sources: list) -> None:
        self._source_combo.blockSignals(True)
        self._source_combo.clear()
        for sid, name in sources:
            self._source_combo.addItem(name, sid)
        self._source_combo.blockSignals(False)

    @Slot(int)
    def _on_source_changed(self, index: int) -> None:
        if index < 0:
            return
        sid = self._source_combo.itemData(index)
        if isinstance(sid, str):
            self.vm.select_source(sid)

    @Slot(str)
    def _on_selected_source(self, source_id: str) -> None:
        index = self._source_combo.findData(source_id)
        if index < 0 or index == self._source_combo.currentIndex():
            return
        self._source_combo.blockSignals(True)
        self._source_combo.setCurrentIndex(index)
        self._source_combo.blockSignals(False)

    @Slot(bool)
    def _on_running(self, running: bool) -> None:
        self._running = running
        self._preview_label.setVisible(running)
        self._sync_controls()

    @Slot(bool)
    def _on_busy_changed(self, busy: bool) -> None:
        self._busy = busy
        self._sync_controls()

    @Slot(str)
    def _on_state_text_changed(self, text: str) -> None:
        self._lbl_state.setText(text)

    def _sync_controls(self) -> None:
        self._btn_start.setEnabled(not self._busy and not self._running)
        self._btn_stop.setEnabled(not self._busy and self._running)
        self._source_combo.setEnabled(not self._busy and not self._running)

    @Slot(object)
    def _on_preview(self, pix: QPixmap) -> None:
        self._preview_label.setPixmap(pix)

    @Slot(dict)
    def _on_metrics(self, m: dict) -> None:
        self._lbl_fps.setText(f"FPS: {m.get('fps', 0):.2f}")
        self._lbl_published.setText(f"Published: {m.get('published', 0)}")
        self._lbl_dropped.setText(f"Dropped: {m.get('dropped', 0)}")
        self.statusBar().showMessage(self._compose_status_bar_message(m))

    @Slot(dict)
    def _on_install_status(self, status: dict) -> None:
        state = status.get("state", "unknown")
        phase = status.get("phase", "")
        devices = status.get("devices") or []
        message = status.get("message", "")
        steps = status.get("steps") or []
        verification_targets = status.get("verification_targets") or []
        can_open_settings = bool(status.get("can_open_settings", False))
        self._stream_start_ready = bool(status.get("stream_start_ready", True))
        self._stream_start_message = str(status.get("stream_start_message", "") or "")
        ipc_probe_present = bool(status.get("ipc_probe_present", False))
        ipc_ready = status.get("ipc_ready")
        ipc_environment_blocked = bool(status.get("ipc_environment_blocked", False))
        ipc_transport = str(status.get("ipc_transport", "") or "")
        ipc_direct_open_errno = status.get("ipc_direct_open_errno")
        ipc_last_error = str(status.get("ipc_last_error", "") or "")
        ipc_probe_path = str(status.get("ipc_probe_path", "") or "")
        runtime_topology_kind = str(status.get("runtime_topology_kind", "") or "")
        runtime_host_role = str(status.get("runtime_host_role", "") or "")
        runtime_host_in_frame_hot_path = bool(status.get("runtime_host_in_frame_hot_path", False))
        runtime_dedicated_host_daemon_required = bool(
            status.get("runtime_dedicated_host_daemon_required", False)
        )
        runtime_container_app_configured = bool(
            status.get("runtime_container_app_configured", False)
        )
        runtime_data_plane = str(status.get("runtime_data_plane", "") or "")
        runtime_control_plane = str(status.get("runtime_control_plane", "") or "")
        manual_app_validation_present = bool(status.get("manual_app_validation_present", False))
        manual_app_validation_ready = status.get("manual_app_validation_ready")
        manual_app_validation_failed_criteria = list(status.get("manual_app_validation_failed_criteria") or [])
        manual_app_validation_failed_labels = list(status.get("manual_app_validation_failed_labels") or [])
        manual_app_validation_unknown_criteria = list(status.get("manual_app_validation_unknown_criteria") or [])
        manual_app_validation_unknown_labels = list(status.get("manual_app_validation_unknown_labels") or [])
        manual_app_validation_blockers = list(status.get("manual_app_validation_blockers") or [])
        manual_app_validation_blocker_labels = list(status.get("manual_app_validation_blocker_labels") or [])
        supported_formats = list(status.get("supported_formats") or [])
        supported_frame_rates = list(status.get("supported_frame_rates") or [])
        self._lbl_install.setText(
            self._compose_install_label(
                state=str(state),
                phase=str(phase),
                devices=list(devices),
                supported_formats=supported_formats,
                supported_frame_rates=supported_frame_rates,
                ipc_probe_present=ipc_probe_present,
                ipc_ready=ipc_ready,
                ipc_environment_blocked=ipc_environment_blocked,
                ipc_direct_open_errno=ipc_direct_open_errno if isinstance(ipc_direct_open_errno, int) else None,
            )
        )
        self._lbl_install_hint.setText(
            self._compose_install_hint(
                install_message=message,
                stream_start_ready=self._stream_start_ready,
                stream_start_message=self._stream_start_message,
                runtime_topology_kind=runtime_topology_kind,
                runtime_host_role=runtime_host_role,
                runtime_host_in_frame_hot_path=runtime_host_in_frame_hot_path,
                runtime_dedicated_host_daemon_required=runtime_dedicated_host_daemon_required,
                runtime_container_app_configured=runtime_container_app_configured,
                runtime_data_plane=runtime_data_plane,
                runtime_control_plane=runtime_control_plane,
                ipc_probe_present=ipc_probe_present,
                ipc_ready=ipc_ready,
                ipc_environment_blocked=ipc_environment_blocked,
                ipc_transport=ipc_transport,
                ipc_direct_open_errno=ipc_direct_open_errno if isinstance(ipc_direct_open_errno, int) else None,
                ipc_last_error=ipc_last_error,
                ipc_probe_path=ipc_probe_path,
                manual_app_validation_present=manual_app_validation_present,
                manual_app_validation_ready=manual_app_validation_ready,
                manual_app_validation_failed_criteria=manual_app_validation_failed_criteria,
                manual_app_validation_unknown_criteria=manual_app_validation_unknown_criteria,
                manual_app_validation_blockers=manual_app_validation_blockers,
                manual_app_validation_failed_labels=manual_app_validation_failed_labels,
                manual_app_validation_unknown_labels=manual_app_validation_unknown_labels,
                manual_app_validation_blocker_labels=manual_app_validation_blocker_labels,
            )
        )
        self._lbl_install_steps.setText("\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1)))
        verification_lines: list[str] = []
        for target in verification_targets:
            name = str(target.get("name", "Unknown"))
            target_status = str(target.get("status", ""))
            target_steps = target.get("steps") or []
            verification_lines.append(f"{name}: {target_status}")
            verification_lines.extend(
                f"  {index}. {step}" for index, step in enumerate(target_steps, 1)
            )
        self._lbl_verification.setText("\n".join(verification_lines))
        self._btn_open_settings.setEnabled(can_open_settings)
        self._btn_recheck_install.setEnabled(True)
        self._apply_start_enabled_state(running=self._btn_stop.isEnabled())

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        QMessageBox.warning(self, "AK Virtual Camera", msg)
