# SPDX-License-Identifier: Apache-2.0
"""MainViewModel — single source of truth for the main window.

Pure view-model: does not know about Qt widgets, only Qt signals/properties.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from ..services.facade import ServiceFacade


class MainViewModel(QObject):
    sources_changed = Signal(list)        # list[(id, name)]
    selected_source_changed = Signal(str)
    running_changed = Signal(bool)
    metrics_changed = Signal(dict)
    preview_changed = Signal(object)      # QPixmap
    error = Signal(str)

    def __init__(self, facade: ServiceFacade, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start()

        # Sources are populated by the View (MainWindow) calling
        # refresh_sources() after it wires signal connections.

    # ---------- commands ----------

    @Slot()
    def refresh_sources(self) -> None:
        srcs = [(s.id, s.name) for s in self._facade.list_sources()]
        self.sources_changed.emit(srcs)
        sel = self._facade.selected_source()
        if sel:
            self.selected_source_changed.emit(sel)

    @Slot(str)
    def select_source(self, source_id: str) -> None:
        self._facade.select_source(source_id)
        self.selected_source_changed.emit(source_id)

    @Slot()
    def start(self) -> None:
        try:
            self._facade.start()
            self.running_changed.emit(True)
        except Exception as exc:
            self.error.emit(str(exc))

    @Slot()
    def stop(self) -> None:
        try:
            self._facade.stop()
            self.running_changed.emit(False)
        except Exception as exc:
            self.error.emit(str(exc))

    # ---------- polling ----------

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
            }
        )
        if st.last_preview:
            pix = QPixmap.fromImage(
                QImage(st.last_preview, 320, 180, QImage.Format.Format_RGB888)
            )
            self.preview_changed.emit(pix)
        self.running_changed.emit(st.running)
