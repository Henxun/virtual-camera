# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from apps.desktop.akvc_app.services.facade import ServiceFacade
from apps.desktop.akvc_app.services.source_info import (
    DEFAULT_PROVIDER_FPS,
    DEFAULT_PROVIDER_HEIGHT,
    DEFAULT_PROVIDER_WIDTH,
    ProviderInfo,
    parse_source_id,
)
from apps.desktop.akvc_app.workers.source_provider import (
    TestPatternProvider,
    UsbCameraProvider,
    create_provider_from_source_id,
)


def fake_provider_info(id: str, name: str) -> ProviderInfo:
    return ProviderInfo(id=id, name=name, formats=())


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

    def stop(self) -> None:
        self.started = False
        self.snapshot_value["running"] = False
        self.stop_calls += 1

    def snapshot(self) -> dict:
        return dict(self.snapshot_value)


def test_parse_source_id_routes_usb_ids() -> None:
    parsed = parse_source_id("usb:2")
    assert parsed["kind"] == "usb"
    assert parsed["device_index"] == 2
    assert parsed["pattern_id"] is None


def test_parse_source_id_routes_pattern_ids() -> None:
    parsed = parse_source_id("test:moving_box")
    assert parsed["kind"] == "test"
    assert parsed["device_index"] is None
    assert parsed["pattern_id"] == "moving_box"


def test_build_provider_falls_back_to_colorbar_for_unknown_pattern() -> None:
    provider = create_provider_from_source_id("test:not-real")
    assert isinstance(provider, TestPatternProvider)
    assert provider.pattern.value == "colorbar"


def test_usb_provider_read_raises_when_not_opened() -> None:
    provider = UsbCameraProvider(device_index=0)
    provider.request_stop()
    try:
        provider.read()
    except RuntimeError as exc:
        assert "not opened" in str(exc)
    else:
        raise AssertionError("read() should raise when the USB provider was not opened")


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


def test_start_delegates_to_runtime_host(monkeypatch) -> None:
    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"
    runtime = FakeRuntimeHost()
    facade._runtime = runtime
    monkeypatch.setattr(facade, "_is_windows", True)

    facade.start()

    # The control layer excludes installation: start() must NOT call any helper
    # or MF registration; it only delegates to the runtime host.
    assert runtime.start_calls == [("start_source", "test:colorbar")]
    assert not hasattr(facade, "_helper") or facade._helper is None


def test_start_stop_start_restarts_runtime_host(monkeypatch) -> None:
    facade = ServiceFacade()
    facade._state.selected_source_id = "test:colorbar"
    runtime = FakeRuntimeHost()
    facade._runtime = runtime
    monkeypatch.setattr(facade, "_is_windows", True)

    facade.start()
    facade.stop(timeout=0.1)
    facade.start()

    assert runtime.start_calls == [
        ("start_source", "test:colorbar"),
        ("start_source", "test:colorbar"),
    ]
    assert runtime.stop_calls == 1


def test_stop_stops_runtime_host() -> None:
    facade = ServiceFacade()
    runtime = FakeRuntimeHost()
    runtime.snapshot_value["running"] = True
    facade._runtime = runtime
    facade._state.worker_status.running = True

    facade.stop(timeout=0.1)

    assert runtime.stop_calls == 1
    assert facade._state.worker_status.running is False
