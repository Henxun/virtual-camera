# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import queue
import threading
import time

from apps.desktop.akvc_app.services.facade import ServiceFacade
from apps.desktop.akvc_app.workers.frame_worker import WorkerCommand, _build_provider, _start_command_watcher
from akvc.core.frame_provider import DEFAULT_PROVIDER_FPS, DEFAULT_PROVIDER_HEIGHT, DEFAULT_PROVIDER_WIDTH
from akvc.core.frame_provider.base import ProviderInfo
from akvc.core.frame_provider.test_pattern import TestPatternProvider
from akvc.core.frame_provider.usb import UsbCameraProvider


class FakeHelper:
    def __init__(self, *, start_result: bool = True, ping_result: bool = True, register_result: bool = True,
                 last_error_message: str | None = None) -> None:
        self.start_result = start_result
        self.ping_result = ping_result
        self.register_result = register_result
        self.last_error_message = last_error_message
        self.start_calls = 0
        self.ping_calls = 0
        self.register_calls: list[str] = []
        self.stop_calls = 0

    def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    def ping(self) -> bool:
        self.ping_calls += 1
        return self.ping_result

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        self.register_calls.append(name)
        return self.register_result

    def stop(self) -> None:
        self.stop_calls += 1
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


def test_build_provider_routes_usb_source_ids() -> None:
    provider = _build_provider("usb:2")

    assert isinstance(provider, UsbCameraProvider)
    assert provider.device_index == 2
    assert provider.width == DEFAULT_PROVIDER_WIDTH
    assert provider.height == DEFAULT_PROVIDER_HEIGHT
    assert provider.fps == DEFAULT_PROVIDER_FPS


def test_build_provider_routes_test_pattern_source_ids() -> None:
    provider = _build_provider("test:moving_box")

    assert isinstance(provider, TestPatternProvider)
    assert provider.pattern.value == "moving_box"
    assert provider.width == DEFAULT_PROVIDER_WIDTH
    assert provider.height == DEFAULT_PROVIDER_HEIGHT
    assert provider.fps == DEFAULT_PROVIDER_FPS


def test_build_provider_falls_back_to_colorbar_for_unknown_pattern() -> None:
    provider = _build_provider("test:not-real")

    assert isinstance(provider, TestPatternProvider)
    assert provider.pattern.value == "colorbar"


def test_usb_provider_read_short_circuits_after_stop_request() -> None:
    provider = UsbCameraProvider(device_index=0)
    provider.request_stop()

    frame = provider.read()

    assert frame.meta == {"reason": "not opened"}


def test_discover_sources_keeps_usb_before_patterns(monkeypatch) -> None:
    facade = ServiceFacade()
    usb_sources = [
        ProviderInfo(id="usb:2", name="USB Camera 2", formats=()),
        ProviderInfo(id="usb:3", name="USB Camera 3", formats=()),
    ]
    seen: list[int] = []

    def fake_list_devices(max_probe: int = 8) -> list[ProviderInfo]:
        seen.append(max_probe)
        return usb_sources

    monkeypatch.setattr(UsbCameraProvider, "list_devices", staticmethod(fake_list_devices))

    sources = facade._discover_sources()

    assert seen == [4]
    assert sources[:2] == usb_sources
    assert all(source.id.startswith("test:") for source in sources[2:])


def test_bootstrap_selects_first_discovered_source(monkeypatch) -> None:
    facade = ServiceFacade()
    discovered = [
        ProviderInfo(id="usb:1", name="USB Camera 1", formats=()),
        ProviderInfo(id="test:colorbar", name="Color Bars", formats=()),
    ]

    monkeypatch.setattr(facade, "_discover_sources", lambda: discovered)

    facade.bootstrap()

    assert facade.list_sources() == discovered
    assert facade.selected_source() == "usb:1"


def test_bootstrap_falls_back_to_first_pattern_when_usb_empty(monkeypatch) -> None:
    facade = ServiceFacade()
    monkeypatch.setattr(UsbCameraProvider, "list_devices", staticmethod(lambda max_probe=8: []))

    facade.bootstrap()

    sources = facade.list_sources()
    assert sources
    assert sources[0].id == "test:colorbar"
    assert facade.selected_source() == "test:colorbar"


def test_discover_sources_recovers_when_usb_probe_fails(monkeypatch) -> None:
    facade = ServiceFacade()

    def fake_list_devices(max_probe: int = 8) -> list[ProviderInfo]:
        raise RuntimeError("probe failed")

    monkeypatch.setattr(UsbCameraProvider, "list_devices", staticmethod(fake_list_devices))

    sources = facade._discover_sources()

    assert sources
    assert all(source.id.startswith("test:") for source in sources)


def test_start_re_registers_after_helper_restart(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.alive = False

        def start(self) -> None:
            self.alive = True

        def join(self, timeout: float | None = None) -> None:
            self.alive = False

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.alive = False

    class FakeQueue:
        def put_nowait(self, _item) -> None:
            return None

    class FakeContext:
        def Queue(self, maxsize: int = 0):
            return FakeQueue()

        def Process(self, **kwargs):
            return FakeProcess()

    ping_states = iter([False, True, False, True])
    helper = FakeHelper()
    helper.ping = lambda: next(ping_states)

    monkeypatch.setattr("apps.desktop.akvc_app.services.facade.mp.get_context", lambda _name: FakeContext())

    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"
    facade._helper = helper
    facade._is_windows = True

    facade.start()
    facade.stop(timeout=0.1)
    facade.start()

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


