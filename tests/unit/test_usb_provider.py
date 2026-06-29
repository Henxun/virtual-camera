# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import numpy as np

from akvc.core.frame import FLAG_ERROR
from akvc.core.frame_provider.usb import UsbCameraProvider


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


class FakeOpenCapture:
    def __init__(self, backend: int, opened: bool) -> None:
        self.backend = backend
        self._opened = opened
        self.released = False
        self.properties: list[tuple[int, int]] = []
        self.raise_on_props: set[int] = set()

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True

    def set(self, prop: int, value: int) -> bool:
        self.properties.append((prop, value))
        if prop in self.raise_on_props:
            raise RuntimeError(f"unsupported property {prop}")
        return True


class FakeProbeCapture:
    def __init__(self, backend: int, opened: bool) -> None:
        self.backend = backend
        self._opened = opened
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True


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


def test_close_is_idempotent_and_releases_capture() -> None:
    provider = UsbCameraProvider(device_index=0)
    capture = FakeCapture([])
    provider._cap = capture

    provider.close()
    provider.close()

    assert capture.released is True
    assert provider._cap is None


def test_list_devices_preserves_probe_order_and_provider_shape(monkeypatch) -> None:
    captures: list[FakeProbeCapture] = []
    seen: list[tuple[int, int]] = []

    def fake_video_capture(index: int, backend: int) -> FakeProbeCapture:
        seen.append((index, backend))
        outcomes = {
            (0, provider_backend("msmf", 0)): False,
            (0, provider_backend("dshow", 0)): True,
            (1, provider_backend("msmf", 0)): True,
            (2, provider_backend("msmf", 0)): False,
            (2, provider_backend("dshow", 0)): False,
        }
        capture = FakeProbeCapture(backend, outcomes[(index, backend)])
        captures.append(capture)
        return capture

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    devices = UsbCameraProvider.list_devices(max_probe=3)

    assert [device.id for device in devices] == ["usb:0", "usb:1"]
    assert [device.name for device in devices] == ["USB Camera 0", "USB Camera 1"]
    assert [device.formats for device in devices] == [(), ()]
    assert seen == [
        (0, provider_backend("msmf", 0)),
        (0, provider_backend("dshow", 0)),
        (1, provider_backend("msmf", 0)),
        (2, provider_backend("msmf", 0)),
        (2, provider_backend("dshow", 0)),
    ]
    assert all(capture.released for capture in captures)


def test_list_devices_respects_max_probe(monkeypatch) -> None:
    seen: list[int] = []

    def fake_video_capture(index: int, backend: int) -> FakeProbeCapture:
        seen.append(index)
        return FakeProbeCapture(backend, opened=False)

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    assert UsbCameraProvider.list_devices(max_probe=2) == []
    assert seen == [0, 0, 1, 1]


def test_list_devices_skips_dshow_when_msmf_succeeds(monkeypatch) -> None:
    seen: list[tuple[int, int]] = []

    def fake_video_capture(index: int, backend: int) -> FakeProbeCapture:
        seen.append((index, backend))
        return FakeProbeCapture(backend, opened=True)

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    devices = UsbCameraProvider.list_devices(max_probe=2)

    assert [device.id for device in devices] == ["usb:0", "usb:1"]
    assert seen == [
        (0, provider_backend("msmf", 0)),
        (1, provider_backend("msmf", 0)),
    ]


def test_open_preserves_backend_fallback_order(monkeypatch) -> None:
    seen: list[int] = []

    def fake_video_capture(index: int, backend: int) -> FakeOpenCapture:
        seen.append(backend)
        return FakeOpenCapture(backend, opened=(len(seen) == 2))

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    provider = UsbCameraProvider(device_index=0, backend="msmf")
    provider.open()

    assert seen[:2] == [provider_backend("msmf", 0), provider_backend("msmf", 1)]
    assert provider._cap is not None


    captures: list[FakeOpenCapture] = []

    def fake_video_capture(index: int, backend: int) -> FakeOpenCapture:
        capture = FakeOpenCapture(backend, opened=(len(captures) == 1))
        captures.append(capture)
        return capture

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    provider = UsbCameraProvider(device_index=0, backend="msmf")
    provider.open()

    assert captures[0].released is True
    assert captures[1].released is False
    assert provider._cap is captures[1]


def test_open_configures_successful_capture_properties(monkeypatch) -> None:
    capture = FakeOpenCapture(provider_backend("msmf", 0), opened=True)

    def fake_video_capture(index: int, backend: int) -> FakeOpenCapture:
        return capture

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    provider = UsbCameraProvider(device_index=0, width=640, height=480, fps=25, backend="msmf")
    provider.open()

    import cv2

    assert capture.properties == [
        (cv2.CAP_PROP_FRAME_WIDTH, 640),
        (cv2.CAP_PROP_FRAME_HEIGHT, 480),
        (cv2.CAP_PROP_FPS, 25),
        (cv2.CAP_PROP_BUFFERSIZE, 1),
        (cv2.CAP_PROP_READ_TIMEOUT_MSEC, 250),
    ]


def test_open_ignores_property_set_exceptions(monkeypatch) -> None:
    import cv2

    capture = FakeOpenCapture(provider_backend("msmf", 0), opened=True)
    capture.raise_on_props = {cv2.CAP_PROP_BUFFERSIZE, cv2.CAP_PROP_READ_TIMEOUT_MSEC}

    def fake_video_capture(index: int, backend: int) -> FakeOpenCapture:
        return capture

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    provider = UsbCameraProvider(device_index=0, backend="msmf")
    provider.open()

    assert provider._cap is capture
    assert capture.released is False


def test_open_raises_after_all_backends_fail(monkeypatch) -> None:
    def fake_video_capture(index: int, backend: int) -> FakeOpenCapture:
        return FakeOpenCapture(backend, opened=False)

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    provider = UsbCameraProvider(device_index=3, backend="msmf")

    try:
        provider.open()
    except RuntimeError as exc:
        assert str(exc) == "Cannot open USB camera 3: None"
    else:
        raise AssertionError("open should fail after all backends fail")


def test_open_keeps_successful_capture_unreleased(monkeypatch) -> None:
    capture = FakeOpenCapture(provider_backend("dshow", 0), opened=True)

    def fake_video_capture(index: int, backend: int) -> FakeOpenCapture:
        return capture

    monkeypatch.setattr("akvc.core.frame_provider.usb.cv2.VideoCapture", fake_video_capture)

    provider = UsbCameraProvider(device_index=0, backend="dshow")
    provider.open()

    assert provider._cap is capture
    assert capture.released is False


def provider_backend(kind: str, index: int) -> int:
    import cv2

    order = {
        "msmf": [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY],
        "dshow": [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY],
        "any": [cv2.CAP_ANY, cv2.CAP_MSMF, cv2.CAP_DSHOW],
    }
    return order[kind][index]
