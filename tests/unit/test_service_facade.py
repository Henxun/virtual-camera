# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import queue
import threading

from apps.desktop.akvc_app.services.facade import ServiceFacade
from apps.desktop.akvc_app.services.source_info import (
    DEFAULT_PROVIDER_FPS,
    DEFAULT_PROVIDER_HEIGHT,
    DEFAULT_PROVIDER_WIDTH,
    ProviderInfo,
)
from akvc._core_native import parse_source_id
from apps.desktop.akvc_app.workers.frame_worker import WorkerCommand, _build_provider, _start_command_watcher
from apps.desktop.akvc_app.workers.source_provider import TestPatternProvider, UsbCameraProvider


def fake_provider_info(id: str, name: str) -> ProviderInfo:
    return ProviderInfo(id=id, name=name, formats=())


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
        self.installed = False
        self.start_installed_calls: list[str] = []

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

    def scheduled_task_status(self, task_name: str = "AKVirtualCameraHelper") -> dict:
        return {"task_name": task_name, "installed": self.installed, "pipe_reachable": self.ping_result}

    def start_installed(self, task_name: str = "AKVirtualCameraHelper", timeout_s: float = 8.0) -> bool:
        self.start_installed_calls.append(task_name)
        return self.start_result

    def ensure_running(self, *, task_name: str = "AKVirtualCameraHelper", prefer_installed: bool = True) -> bool:
        self.start_installed_calls.append(task_name)
        return self.start_result


class FakeRuntimeHost:
    def __init__(self) -> None:
        self.started = False
        self.start_calls: list[tuple[str, str]] = []
        self.stop_calls = 0
        self.snapshot_value = {
            "running": False,
            "fps": 0.0,
            "frames_published": 0,
            "frames_dropped": 0,
            "consumer_count": 0,
            "last_error": None,
            "last_preview": None,
        }

    def start_source(self, source_id: str) -> None:
        self.started = True
        self.snapshot_value["running"] = True
        self.start_calls.append(("start_source", source_id))

    def start(self, provider, pipeline, sink_factory) -> None:
        self.started = True
        self.snapshot_value["running"] = True
        self.start_calls.append(("start", "legacy"))

    def stop(self) -> None:
        self.started = False
        self.snapshot_value["running"] = False
        self.stop_calls += 1

    def snapshot(self) -> dict:
        return dict(self.snapshot_value)


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


def test_parse_source_id_routes_usb_ids() -> None:
    parsed = dict(parse_source_id("usb:2"))

    assert parsed["kind"] == "usb"
    assert parsed["device_index"] == 2
    assert parsed["pattern_id"] is None


def test_parse_source_id_routes_pattern_ids() -> None:
    parsed = dict(parse_source_id("test:moving_box"))

    assert parsed["kind"] == "test"
    assert parsed["device_index"] is None
    assert parsed["pattern_id"] == "moving_box"


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

    def fake_list_usb_sources(*, max_probe: int = 8, width: int = 1280, height: int = 720, fps: int = 30) -> list[ProviderInfo]:
        seen.append(max_probe)
        return usb_sources

    monkeypatch.setattr("apps.desktop.akvc_app.services.facade.list_usb_sources", fake_list_usb_sources)

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
    monkeypatch.setattr(
        "apps.desktop.akvc_app.services.facade.list_usb_sources",
        lambda **kwargs: [],
    )

    facade.bootstrap()

    sources = facade.list_sources()
    assert sources
    assert sources[0].id == "test:colorbar"
    assert facade.selected_source() == "test:colorbar"


def test_discover_sources_recovers_when_usb_probe_fails(monkeypatch) -> None:
    facade = ServiceFacade()

    def fake_list_usb_sources(**kwargs) -> list[ProviderInfo]:
        raise RuntimeError("probe failed")

    monkeypatch.setattr("apps.desktop.akvc_app.services.facade.list_usb_sources", fake_list_usb_sources)

    sources = facade._discover_sources()

    assert sources
    assert all(source.id.startswith("test:") for source in sources)


def test_start_re_registers_after_helper_restart(monkeypatch) -> None:
    ping_states = iter([False, True, False, True])
    helper = FakeHelper()
    helper.ping = lambda: next(ping_states)

    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"
    facade._helper = helper
    facade._runtime = FakeRuntimeHost()
    facade._is_windows = True

    facade.start()
    facade.stop(timeout=0.1)
    facade.start()

    assert facade._runtime.start_calls == [
        ("start_source", "test:colorbar"),
        ("start_source", "test:colorbar"),
    ]
    assert helper.register_calls == ["AK Virtual Camera", "AK Virtual Camera"]


def test_stop_stops_runtime_host() -> None:
    facade = ServiceFacade()
    runtime = FakeRuntimeHost()
    runtime.snapshot_value["running"] = True
    facade._runtime = runtime
    facade._state.worker_status.running = True

    facade.stop(timeout=0.1)

    assert runtime.stop_calls == 1
    assert facade._state.worker_status.running is False


