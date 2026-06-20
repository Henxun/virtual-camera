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
        self.setWindowTitle("AK Virtual Camera")
        self.resize(560, 540)

        # Source selector
        self._source_combo = QComboBox(self)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)

        # Start/Stop
        self._btn_start = QPushButton("Start", self)
        self._btn_stop = QPushButton("Stop", self)
        self._btn_start.clicked.connect(self.vm.start)
        self._btn_stop.clicked.connect(self.vm.stop)
        self._btn_stop.setEnabled(False)

        # Status labels
        self._lbl_state = QLabel("Idle", self)
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
        ctrllay.addWidget(self._btn_start)
        ctrllay.addWidget(self._btn_stop)

        statgrp = QGroupBox("Status", self)
        statlay = QVBoxLayout(statgrp)
        statlay.addWidget(self._lbl_state)
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
        self.vm.running_changed.connect(self._on_running)
        self.vm.metrics_changed.connect(self._on_metrics)
        self.vm.preview_changed.connect(self._on_preview)
        self.vm.error.connect(self._on_error)

        # Populate sources after signal connections are established.
        self.vm.refresh_sources()

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

    @Slot(bool)
    def _on_running(self, running: bool) -> None:
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self._source_combo.setEnabled(not running)
        self._lbl_state.setText("Streaming" if running else "Idle")
        self._preview_label.setVisible(running)

    @Slot(object)
    def _on_preview(self, pix: QPixmap) -> None:
        self._preview_label.setPixmap(pix)

    @Slot(dict)
    def _on_metrics(self, m: dict) -> None:
        self._lbl_fps.setText(f"FPS: {m.get('fps', 0):.2f}")
        self._lbl_published.setText(f"Published: {m.get('published', 0)}")
        self._lbl_dropped.setText(f"Dropped: {m.get('dropped', 0)}")
        consumers = m.get("consumers", 0)
        self.statusBar().showMessage(
            f"Consumers: {consumers} | Last error: {m.get('last_error', '') or '—'}"
        )

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        QMessageBox.warning(self, "AK Virtual Camera", msg)
