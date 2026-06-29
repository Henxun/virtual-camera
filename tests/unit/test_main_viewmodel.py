# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from PySide6.QtCore import QObject

from apps.desktop.akvc_app.viewmodels.main_vm import MainViewModel
from apps.desktop.akvc_app.services.facade import WorkerStatus


class FakeSignal:
    def __init__(self) -> None:
        self.values: list[object] = []

    def emit(self, value) -> None:
        self.values.append(value)


class FakeTimer:
    def __init__(self, _parent=None) -> None:
        self.interval = None
        self.started = False
        self.timeout = self
        self._callback = None

    def setInterval(self, interval: int) -> None:
        self.interval = interval

    def connect(self, callback) -> None:
        self._callback = callback

    def start(self) -> None:
        self.started = True


class FakeFacade:
    def __init__(self, *, start_error: Exception | None = None) -> None:
        self.start_error = start_error
        self.start_calls = 0
        self.stop_calls = 0
        self.selected = "test:colorbar"
        self.sources = []
        self.status = WorkerStatus()

    def list_sources(self):
        return self.sources

    def selected_source(self):
        return self.selected

    def select_source(self, source_id: str) -> None:
        self.selected = source_id

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    def stop(self) -> None:
        self.stop_calls += 1

    def poll_status(self) -> WorkerStatus:
        return self.status


class DummyParent(QObject):
    pass


def test_start_failure_emits_running_false_and_error(monkeypatch) -> None:
    monkeypatch.setattr("apps.desktop.akvc_app.viewmodels.main_vm.QTimer", FakeTimer)
    facade = FakeFacade(start_error=RuntimeError("helper launch failed"))
    vm = MainViewModel(facade, parent=DummyParent())
    running = FakeSignal()
    error = FakeSignal()
    vm.running_changed = running
    vm.error = error

    vm.start()

    assert running.values == [False]
    assert error.values == ["helper launch failed"]


def test_start_success_emits_running_true(monkeypatch) -> None:
    monkeypatch.setattr("apps.desktop.akvc_app.viewmodels.main_vm.QTimer", FakeTimer)
    facade = FakeFacade()
    vm = MainViewModel(facade, parent=DummyParent())
    running = FakeSignal()
    vm.running_changed = running

    vm.start()

    assert running.values == [True]
    assert facade.start_calls == 1


def test_poll_does_not_redundantly_emit_unchanged_running(monkeypatch) -> None:
    monkeypatch.setattr("apps.desktop.akvc_app.viewmodels.main_vm.QTimer", FakeTimer)
    facade = FakeFacade()
    facade.status.running = True
    parent = DummyParent()
    vm = MainViewModel(facade, parent=parent)
    running = FakeSignal()
    vm.running_changed = running
    vm.metrics_changed = FakeSignal()

    vm.start()           # running flips False -> True (1 emit)
    vm._poll_status()    # running still True -> no emit
    vm._poll_status()    # running still True -> no emit

    assert running.values == [True]
