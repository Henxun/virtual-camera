# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QObject

from apps.desktop.akvc_app.viewmodels.main_vm import MainViewModel
from apps.desktop.akvc_app.services.facade import WorkerStatus


class FakeSignal:
    def __init__(self) -> None:
        self.values: list[object] = []

    def emit(self, *args) -> None:
        if len(args) == 1:
            self.values.append(args[0])
        else:
            self.values.append(args)


class FakeTimer:
    def __init__(self, _parent=None) -> None:
        self.interval = None
        self.started = False
        self.start_calls = 0
        self.stop_calls = 0
        self.timeout = self
        self._callback = None

    def setInterval(self, interval: int) -> None:
        self.interval = interval

    def connect(self, callback) -> None:
        self._callback = callback

    def start(self) -> None:
        self.started = True
        self.start_calls += 1

    def stop(self) -> None:
        self.started = False
        self.stop_calls += 1


class FakeLifecycleWorker:
    def __init__(self, vm: MainViewModel, action: str, operation) -> None:
        self._vm = vm
        self._action = action
        self._operation = operation

    def run(self) -> None:
        try:
            self._operation()
        except Exception as exc:
            self._vm._on_lifecycle_failed(self._action, str(exc))
        else:
            self._vm._on_lifecycle_finished(self._action)
        self._vm._clear_lifecycle_worker()


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


def _make_vm(monkeypatch, facade: FakeFacade) -> MainViewModel:
    monkeypatch.setattr("apps.desktop.akvc_app.viewmodels.main_vm.QTimer", FakeTimer)
    parent = DummyParent()
    vm = MainViewModel(facade, parent=parent)
    vm._test_parent = parent

    def fake_launch(action: str, operation) -> None:
        vm._lifecycle_thread = SimpleNamespace(start_calls=1)
        vm._lifecycle_worker = FakeLifecycleWorker(vm, action, operation)

    vm._launch_lifecycle = fake_launch
    return vm


def test_start_launches_lifecycle_without_blocking(monkeypatch) -> None:
    facade = FakeFacade()
    vm = _make_vm(monkeypatch, facade)
    busy = FakeSignal()
    state = FakeSignal()
    running = FakeSignal()
    vm.busy_changed.connect(busy.emit)
    vm.state_text_changed.connect(state.emit)
    vm.running_changed.connect(running.emit)

    vm.start()

    assert facade.start_calls == 0
    assert busy.values == [True]
    assert state.values == ["Starting…"]
    assert vm._poll_timer.stop_calls == 1
    assert vm._lifecycle_thread is not None
    assert vm._lifecycle_thread.start_calls == 1
    assert running.values == []


def test_start_success_emits_running_after_worker_finishes(monkeypatch) -> None:
    facade = FakeFacade()
    facade.status.running = True
    vm = _make_vm(monkeypatch, facade)
    running = FakeSignal()
    busy = FakeSignal()
    state = FakeSignal()
    vm.running_changed.connect(running.emit)
    vm.busy_changed.connect(busy.emit)
    vm.state_text_changed.connect(state.emit)

    vm.start()
    vm._lifecycle_worker.run()

    assert facade.start_calls == 1
    assert running.values == [True]
    assert busy.values == [True, False]
    assert state.values == ["Starting…", "Streaming"]
    assert vm._poll_timer.start_calls == 2


def test_start_failure_emits_running_false_and_error(monkeypatch) -> None:
    facade = FakeFacade(start_error=RuntimeError("helper launch failed"))
    vm = _make_vm(monkeypatch, facade)
    running = FakeSignal()
    error = FakeSignal()
    busy = FakeSignal()
    state = FakeSignal()
    vm.running_changed.connect(running.emit)
    vm.error.connect(error.emit)
    vm.busy_changed.connect(busy.emit)
    vm.state_text_changed.connect(state.emit)

    vm.start()
    vm._lifecycle_worker.run()

    assert running.values == [False]
    assert error.values == ["helper launch failed"]
    assert busy.values == [True, False]
    assert state.values == ["Starting…", "Idle"]


def test_busy_blocks_repeated_start_and_source_changes(monkeypatch) -> None:
    facade = FakeFacade()
    vm = _make_vm(monkeypatch, facade)

    vm.start()
    vm.start()
    vm.select_source("test:checkerboard")

    assert facade.start_calls == 0
    assert facade.selected == "test:colorbar"


def test_stop_launches_lifecycle_without_blocking(monkeypatch) -> None:
    facade = FakeFacade()
    facade.status.running = False
    vm = _make_vm(monkeypatch, facade)
    vm._running = True
    busy = FakeSignal()
    state = FakeSignal()
    running = FakeSignal()
    vm.busy_changed.connect(busy.emit)
    vm.state_text_changed.connect(state.emit)
    vm.running_changed.connect(running.emit)

    vm.stop()

    assert facade.stop_calls == 0
    assert busy.values == [True]
    assert state.values == ["Stopping…"]
    assert vm._poll_timer.stop_calls == 1
    assert running.values == []


def test_poll_does_not_redundantly_emit_unchanged_running(monkeypatch) -> None:
    facade = FakeFacade()
    facade.status.running = True
    vm = _make_vm(monkeypatch, facade)
    running = FakeSignal()
    vm.running_changed.connect(running.emit)
    vm.metrics_changed.connect(lambda *_args: None)

    vm._set_running(True)
    vm._poll_status()
    vm._poll_status()

    assert running.values == [True]
