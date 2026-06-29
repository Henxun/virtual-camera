# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from apps.desktop.akvc_app.views.main_window import MainWindow


class FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, value) -> None:
        for callback in list(self._callbacks):
            callback(value)


class FakeVm:
    def __init__(self) -> None:
        self.sources_changed = FakeSignal()
        self.selected_source_changed = FakeSignal()
        self.running_changed = FakeSignal()
        self.metrics_changed = FakeSignal()
        self.preview_changed = FakeSignal()
        self.error = FakeSignal()
        self.start_calls = 0
        self.stop_calls = 0
        self.refresh_calls = 0
        self.selected_calls: list[str] = []

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def refresh_sources(self) -> None:
        self.refresh_calls += 1

    def select_source(self, source_id: str) -> None:
        self.selected_calls.append(source_id)


def _get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_selected_source_signal_updates_combo_box() -> None:
    _get_app()
    vm = FakeVm()
    window = MainWindow(vm)

    vm.sources_changed.emit([
        ("usb:1", "USB Camera 1"),
        ("test:checkerboard", "Checkerboard"),
    ])
    vm.selected_source_changed.emit("test:checkerboard")

    assert window._source_combo.currentData() == "test:checkerboard"


def test_selected_source_signal_does_not_reenter_select_source() -> None:
    _get_app()
    vm = FakeVm()
    window = MainWindow(vm)

    vm.sources_changed.emit([
        ("usb:1", "USB Camera 1"),
        ("test:checkerboard", "Checkerboard"),
    ])
    vm.selected_source_changed.emit("test:checkerboard")

    assert vm.selected_calls == []
