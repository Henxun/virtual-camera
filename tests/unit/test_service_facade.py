# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import queue
import threading
import time

from apps.desktop.akvc_app.services.facade import ServiceFacade
from apps.desktop.akvc_app.workers.frame_worker import WorkerCommand, _start_command_watcher
from akvc.core.frame_provider.usb import UsbCameraProvider


class FakeHelper:
    def __init__(self, *, start_result: bool = True, ping_result: bool = True, register_result: bool = True,
                 last_error_message: str | None = None) -> None:
        self.start_result = start_result
        self.ping_result = ping_result
        self.register_result = register_result
        self.last_error_message = last_error_message

    def start(self) -> bool:
        return self.start_result

    def ping(self) -> bool:
        return self.ping_result

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        return self.register_result

    def stop(self) -> None:
        return None


class FakeProvider:
    def __init__(self) -> None:
        self.stop_requested = threading.Event()

    def request_stop(self) -> None:
        self.stop_requested.set()


def test_start_raises_when_helper_fails(monkeypatch) -> None:
    facade = ServiceFacade()
    facade._state.selected_source_id = "demo"
    facade._helper = FakeHelper(
        start_result=False,
        last_error_message="helper launch failed",
    )
    monkeypatch.setattr(facade, "_is_windows", True)

    try:
        facade.start()
    except RuntimeError as exc:
        assert "helper launch failed" in str(exc)
    else:
        raise AssertionError("start should fail when helper does not start")


def test_start_raises_when_mf_registration_fails(monkeypatch) -> None:
    facade = ServiceFacade()
    facade._state.selected_source_id = "demo"
    facade._helper = FakeHelper(register_result=False)
    monkeypatch.setattr(facade, "_is_windows", True)

    try:
        facade.start()
    except RuntimeError as exc:
        assert "register MF virtual camera" in str(exc)
    else:
        raise AssertionError("start should fail when MF registration fails")


def test_command_watcher_sets_stop_and_notifies_provider() -> None:
    cmd_q: queue.Queue[WorkerCommand] = queue.Queue()
    stop_requested = threading.Event()
    provider = FakeProvider()

    watcher = _start_command_watcher(cmd_q, stop_requested, provider)
    cmd_q.put(WorkerCommand("stop"))
    watcher.join(timeout=1.0)

    assert stop_requested.is_set()
    assert provider.stop_requested.is_set()


def test_usb_provider_read_short_circuits_after_stop_request() -> None:
    provider = UsbCameraProvider(device_index=0)
    provider.request_stop()

    frame = provider.read()

    assert frame.meta == {"reason": "not opened"}


def test_stop_returns_after_worker_exits() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.join_calls: list[float] = []
            self.terminate_called = False
            self.alive = True

        def join(self, timeout: float | None = None) -> None:
            self.join_calls.append(0.0 if timeout is None else timeout)
            self.alive = False

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.terminate_called = True

    facade = ServiceFacade()
    facade._proc = FakeProcess()
    facade._cmd_q = queue.Queue()

    facade.stop(timeout=0.1)

    assert facade._proc is None
