# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import numpy as np

from akvc._core_native import FLAG_ERROR
from apps.desktop.akvc_app.services.source_info import ProviderInfo
from apps.desktop.akvc_app.workers.source_provider import UsbCameraProvider


class FakeCapture:
    def __init__(self, results: list[tuple[bool, object]]) -> None:
        self._results = list(results)
        self.read_calls = 0
        self.released = False

    def read(self) -> tuple[bool, object]:
        self.read_calls += 1
        if not self._results:
            return False, None
        return self._results.pop(0)

    def release(self) -> None:
        self.released = True


class FakeNativeCapture:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, result: object | Exception) -> None:
        self.result = result
        self.calls: list[tuple[int, str]] = []

    def open(self, device_index: int, backend: str) -> object:
        self.calls.append((device_index, backend))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeProber:
    def __init__(self, indices: list[int]) -> None:
        self.indices = indices
        self.calls: list[int] = []

    def list_indices(self, max_probe: int) -> list[int]:
        self.calls.append(max_probe)
        return list(self.indices)


def fake_native_provider_info(*, id: str, name: str):
    class NativeFormat:
        def __init__(self) -> None:
            self.fourcc = 0x20424752
            self.width = 1280
            self.height = 720
            self.fps_num = 30
            self.fps_den = 1

    class NativeInfo:
        def __init__(self) -> None:
            self.id = id
            self.name = name
            self.formats = [NativeFormat()]

    return NativeInfo()


def test_read_returns_stop_requested_error_after_stop_request() -> None:
    provider = UsbCameraProvider(device_index=0)
    provider._cap = FakeCapture([(True, np.zeros((2, 3, 3), dtype=np.uint8))])
    provider.request_stop()

    frame = provider.read()

    assert frame.flags == FLAG_ERROR
    assert frame.meta == {"reason": "stop requested"}


def test_read_retries_once_then_returns_frame() -> None:
    provider = UsbCameraProvider(device_index=0, width=3, height=2)
    provider._cap = FakeCapture([
        (False, None),
        (True, np.full((2, 3, 3), 7, dtype=np.uint8)),
    ])

    frame = provider.read()

    assert frame.flags == 0
    assert frame.width == 3
    assert frame.height == 2
    assert frame.seq == 1
    assert provider._cap.read_calls == 2


def test_read_returns_error_after_double_failure() -> None:
    provider = UsbCameraProvider(device_index=0, width=4, height=2)
    provider._cap = FakeCapture([(False, None), (False, None)])

    frame = provider.read()

    assert frame.flags == FLAG_ERROR
    assert frame.meta == {"reason": "read failed"}


def test_close_is_idempotent_and_releases_legacy_capture() -> None:
    provider = UsbCameraProvider(device_index=0)
    capture = FakeCapture([])
    provider._cap = capture

    provider.close()
    provider.close()

    assert capture.released is True
    assert provider._cap is None


def test_close_is_idempotent_and_closes_native_capture() -> None:
    provider = UsbCameraProvider(device_index=0)
    capture = FakeNativeCapture()
    provider._cap = capture

    provider.close()
    provider.close()

    assert capture.closed is True
    assert provider._cap is None


def test_list_devices_uses_native_prober(monkeypatch) -> None:
    prober = FakeProber([2, 5])

    def fake_list_usb_sources(max_probe: int = 8, width: int = 1280, height: int = 720, fps: int = 30):
        return [
            fake_native_provider_info(id=f"usb:{i}", name=f"USB Camera {i}")
            for i in prober.list_indices(max_probe)
        ]

    monkeypatch.setattr("apps.desktop.akvc_app.workers.source_provider._list_usb_sources", fake_list_usb_sources)

    devices = UsbCameraProvider.list_devices(max_probe=8)

    assert prober.calls == [8]
    assert devices == [
        ProviderInfo(id="usb:2", name="USB Camera 2", formats=devices[0].formats),
        ProviderInfo(id="usb:5", name="USB Camera 5", formats=devices[1].formats),
    ]


def test_open_uses_native_opener_result() -> None:
    provider = UsbCameraProvider(device_index=3, backend="msmf")
    opener = FakeOpener(FakeNativeCapture())
    provider._opener = opener

    provider.open()

    assert opener.calls == [(3, "msmf")]
    assert provider._cap is opener.result


def test_open_propagates_native_open_failure() -> None:
    provider = UsbCameraProvider(device_index=3, backend="msmf")
    provider._opener = FakeOpener(RuntimeError("Cannot open USB camera 3: device index out of range"))

    try:
        provider.open()
    except RuntimeError as exc:
        assert str(exc) == "Cannot open USB camera 3: device index out of range"
    else:
        raise AssertionError("open should fail when native opener fails")
