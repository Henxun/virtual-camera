# SPDX-License-Identifier: Apache-2.0
"""macOS direct sender wrapper tests."""

from __future__ import annotations

import ctypes
from pathlib import Path
from unittest.mock import patch

import numpy as np

from akvc.core.frame import Frame
from akvc.platforms.macos.direct_sender import MacDirectCameraSender

NATIVE_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "virtualcam"
    / "macos"
    / "direct_sender"
    / "AKVCDirectCameraSender.mm"
)


class FakeSymbol:
    def __init__(self, func) -> None:
        self._func = func
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._func(*args)


class FakeCDLL:
    def __init__(
        self,
        *,
        include_list_devices: bool = True,
        include_request_access: bool = True,
        list_devices_payload: bytes | None = None,
        request_access_payload: bytes | None = None,
        expected_start_name: bytes = b"AKVC Direct",
        expected_start_names: set[bytes] | None = None,
    ) -> None:
        self.akvc_macos_direct_sender_create = FakeSymbol(self._create)
        self.akvc_macos_direct_sender_destroy = FakeSymbol(self._destroy)
        self.akvc_macos_direct_sender_start = FakeSymbol(self._start)
        self.akvc_macos_direct_sender_send_bgr24 = FakeSymbol(self._send)
        self.akvc_macos_direct_sender_send_bgra32 = FakeSymbol(self._send_bgra32)
        self.akvc_macos_direct_sender_consumer_count = FakeSymbol(self._consumer_count)
        if include_list_devices:
            self.akvc_macos_direct_sender_list_devices_json = FakeSymbol(self._list_devices_json)
        if include_request_access:
            self.akvc_macos_direct_sender_request_camera_access_json = FakeSymbol(
                self._request_camera_access_json
            )
        self._handle = 1234
        self.destroy_calls = 0
        self.start_calls: list[bytes] = []
        self.send_pts_100ns: list[int] = []
        self.send_bgra_pts_100ns: list[int] = []
        self._list_devices_payload = list_devices_payload or b'["FaceTime HD Camera","AK Virtual Camera"]\0'
        self._request_access_payload = request_access_payload or self._list_devices_payload
        self._expected_start_name = expected_start_name
        self._expected_start_names = set(expected_start_names or {expected_start_name})

    def _create(self, width, height, fps, error, error_capacity) -> int:
        del error, error_capacity
        assert width == 1280
        assert height == 720
        assert float(fps) == 30.0
        return self._handle

    def _destroy(self, handle) -> None:
        actual_handle = int(handle.value) if hasattr(handle, "value") else int(handle)
        assert actual_handle == self._handle
        self.destroy_calls += 1

    def _start(self, handle, camera_name, error, error_capacity) -> int:
        actual_handle = int(handle.value) if hasattr(handle, "value") else int(handle)
        assert actual_handle == self._handle
        self.start_calls.append(camera_name)
        if camera_name not in self._expected_start_names:
            message = b"camera device not found"
            ctypes.memmove(error, message, min(len(message) + 1, error_capacity))
            return -1
        return 0

    def _send(self, handle, data, width, height, stride, pts_100ns, error, error_capacity) -> int:
        del data, error, error_capacity
        actual_handle = int(handle.value) if hasattr(handle, "value") else int(handle)
        assert actual_handle == self._handle
        assert width == 1280
        assert height == 720
        assert stride == 1280 * 3
        self.send_pts_100ns.append(int(pts_100ns))
        return 0

    def _send_bgra32(self, handle, data, width, height, stride, pts_100ns, error, error_capacity) -> int:
        del data, error, error_capacity
        actual_handle = int(handle.value) if hasattr(handle, "value") else int(handle)
        assert actual_handle == self._handle
        assert width == 1280
        assert height == 720
        assert stride == 1280 * 4
        self.send_bgra_pts_100ns.append(int(pts_100ns))
        return 0

    def _consumer_count(self, handle) -> int:
        actual_handle = int(handle.value) if hasattr(handle, "value") else int(handle)
        assert actual_handle == self._handle
        return 2

    def _list_devices_json(self, json_buffer, json_capacity, error, error_capacity) -> int:
        del error, error_capacity
        payload = self._list_devices_payload
        assert json_capacity > len(payload)
        ctypes.memmove(json_buffer, payload, len(payload))
        return 0

    def _request_camera_access_json(self, json_buffer, json_capacity, error, error_capacity) -> int:
        del error, error_capacity
        payload = self._request_access_payload
        assert json_capacity > len(payload)
        ctypes.memmove(json_buffer, payload, len(payload))
        return 0


class FakeBits(bytearray):
    def setsize(self, size: int) -> None:
        self._size = size

    def asstring(self, size: int) -> bytes:
        return bytes(self[:size])


class FakeQImage:
    class Format:
        Format_BGRA8888 = 2

    def __init__(self, width: int, height: int, payload: bytes) -> None:
        self._width = width
        self._height = height
        self._payload = payload

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def bytesPerLine(self) -> int:
        return self._width * 4

    def format(self) -> int:
        return self.Format.Format_BGRA8888

    def constBits(self) -> FakeBits:
        return FakeBits(self._payload)


class FakeQPixmap:
    def __init__(self, image: FakeQImage) -> None:
        self._image = image

    def toImage(self) -> FakeQImage:
        return self._image


def test_macos_direct_sender_native_source_gates_continuity_camera_on_info_plist_opt_in() -> None:
    text = NATIVE_SOURCE.read_text(encoding="utf-8")

    assert 'NSCameraUseContinuityCameraDeviceType' in text
    assert 'if (allow_continuity_camera)' in text
    assert 'AVCaptureDeviceTypeContinuityCamera' in text


def test_macos_direct_sender_enumerates_available_device_names() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True)
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            assert sender.library_path == str(fake_lib)
            assert sender.available_device_names() == ["FaceTime HD Camera", "AK Virtual Camera"]
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_enumerates_available_device_names_from_snapshot_object() -> None:
    payload = (
        b'{"all_devices":["FaceTime HD Camera","AK Virtual Camera"],'
        b'"avfoundation_devices":["FaceTime HD Camera"],'
        b'"cmio_devices":["AK Virtual Camera"],'
        b'"camera_access_status":"authorized",'
        b'"environment_device_enumeration_empty":false}\0'
    )
    fake_cdll = FakeCDLL(include_list_devices=True, list_devices_payload=payload)
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            snapshot = sender.available_device_snapshot()
            assert snapshot["all_devices"] == ["FaceTime HD Camera", "AK Virtual Camera"]
            assert snapshot["avfoundation_devices"] == ["FaceTime HD Camera"]
            assert snapshot["cmio_devices"] == ["AK Virtual Camera"]
            assert snapshot["camera_access_status"] == "authorized"
            assert snapshot["environment_device_enumeration_empty"] is False
            assert sender.available_device_names() == ["FaceTime HD Camera", "AK Virtual Camera"]
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_returns_empty_device_list_when_symbol_is_missing() -> None:
    fake_cdll = FakeCDLL(include_list_devices=False)
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            assert sender.available_device_names() == []
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_can_request_camera_access_snapshot() -> None:
    payload = (
        b'{"all_devices":["AK Virtual Camera"],'
        b'"avfoundation_devices":["AK Virtual Camera"],'
        b'"cmio_devices":["AK Virtual Camera"],'
        b'"camera_access_status":"authorized",'
        b'"camera_access_authorized":true,'
        b'"camera_access_denied":false,'
        b'"environment_device_enumeration_empty":false}\0'
    )
    fake_cdll = FakeCDLL(
        include_list_devices=True,
        include_request_access=True,
        request_access_payload=payload,
    )
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            snapshot = sender.request_camera_access()
            assert snapshot["all_devices"] == ["AK Virtual Camera"]
            assert snapshot["camera_access_status"] == "authorized"
            assert snapshot["camera_access_authorized"] is True
            assert snapshot["camera_access_denied"] is False
            assert snapshot["environment_device_enumeration_empty"] is False
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_readiness_reports_ready_when_target_is_visible() -> None:
    payload = (
        b'{"all_devices":["AK Virtual Camera"],'
        b'"camera_access_status":"authorized",'
        b'"camera_access_authorized":true,'
        b'"environment_device_enumeration_empty":false}\0'
    )
    fake_cdll = FakeCDLL(include_list_devices=True, list_devices_payload=payload)
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            readiness = sender.direct_sender_readiness(name="AK Virtual Camera")
            assert readiness["ready"] is True
            assert readiness["blocker_code"] == "ready"
            assert readiness["camera_name"] == "AK Virtual Camera"
            assert readiness["target_visible"] is True
            assert readiness["visible_devices"] == ["AK Virtual Camera"]
        finally:
            sender.close()


def test_macos_direct_sender_readiness_reports_camera_access_denied() -> None:
    payload = (
        b'{"all_devices":[],"avfoundation_devices":[],"cmio_devices":[],'
        b'"camera_access_status":"denied",'
        b'"camera_access_denied":true,'
        b'"environment_device_enumeration_empty":true}\0'
    )
    fake_cdll = FakeCDLL(include_list_devices=True, list_devices_payload=payload)
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            readiness = sender.direct_sender_readiness(name="AK Virtual Camera")
            assert readiness["ready"] is False
            assert readiness["blocker_code"] == "camera_access_denied"
            assert readiness["camera_access_status"] == "denied"
            assert readiness["target_visible"] is False
        finally:
            sender.close()


def test_macos_direct_sender_accepts_bgr_bytes_frame() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True, expected_start_name=b"AKVC Direct")
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")
    frame = Frame.from_bgr_bytes(
        width=1280,
        height=720,
        data=bytearray(1280 * 720 * 3),
        pts_100ns=123456789,
    )

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            sender.open(name="AKVC Direct")
            sender.publish(frame)
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1
    assert fake_cdll.send_pts_100ns == [123456789]


def test_macos_direct_sender_accepts_bgra_bytes_frame() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True, expected_start_name=b"AKVC Direct")
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")
    frame = Frame.from_bgra_bytes(
        width=1280,
        height=720,
        data=bytearray(1280 * 720 * 4),
        pts_100ns=987654321,
    )

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            sender.open(name="AKVC Direct")
            sender.publish(frame)
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1
    assert fake_cdll.send_bgra_pts_100ns == [987654321]


def test_macos_direct_sender_start_aliases_open_and_send_accepts_numpy_bgr() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True, expected_start_name=b"AKVC Direct")
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            sender.start("AKVC Direct")
            sender.send(frame)
        finally:
            sender.stop()

    assert fake_cdll.destroy_calls == 1
    assert len(fake_cdll.send_bgra_pts_100ns) == 1


def test_macos_direct_sender_send_accepts_qpixmap_like_bgra_input() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True, expected_start_name=b"AKVC Direct")
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")
    image = FakeQImage(1280, 720, bytes(1280 * 720 * 4))
    pixmap = FakeQPixmap(image)

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            sender.start("AKVC Direct")
            sender.send_pixmap(pixmap)
        finally:
            sender.close()

    assert fake_cdll.destroy_calls == 1
    assert len(fake_cdll.send_bgra_pts_100ns) == 1


def test_macos_direct_sender_send_auto_opens_configured_camera_name() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True, expected_start_name=b"AK Virtual Camera")
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(
            width=1280,
            height=720,
            fps=30.0,
            camera_name="AK Virtual Camera",
        )
        try:
            assert sender.started is False
            assert sender.camera_name is None
            sender.send(frame)
            assert sender.started is True
            assert sender.camera_name == "AK Virtual Camera"
            assert sender.consumer_count == 2
        finally:
            sender.close()

    assert fake_cdll.start_calls == [b"AK Virtual Camera"]
    assert len(fake_cdll.send_bgra_pts_100ns) == 1
    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_send_auto_opens_default_camera_name() -> None:
    fake_cdll = FakeCDLL(include_list_devices=True, expected_start_name=b"AK Virtual Camera")
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(width=1280, height=720, fps=30.0)
        try:
            sender.send(frame)
            assert sender.started is True
            assert sender.camera_name == "AK Virtual Camera"
        finally:
            sender.stop()

    assert fake_cdll.start_calls == [b"AK Virtual Camera"]
    assert len(fake_cdll.send_bgra_pts_100ns) == 1
    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_open_can_fall_back_to_visible_akvc_alias() -> None:
    payload = (
        b'{"all_devices":["OBS Virtual Camera","AKVC Demo"],'
        b'"camera_access_status":"authorized",'
        b'"environment_device_enumeration_empty":false}\0'
    )
    fake_cdll = FakeCDLL(
        include_list_devices=True,
        list_devices_payload=payload,
        expected_start_name=b"AKVC Demo",
    )
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(
            width=1280,
            height=720,
            fps=30.0,
            camera_name="AK Virtual Camera",
        )
        try:
            sender.open()
            assert sender.camera_name == "AKVC Demo"
        finally:
            sender.close()

    assert fake_cdll.start_calls == [b"AK Virtual Camera", b"AKVC Demo"]
    assert fake_cdll.destroy_calls == 1


def test_macos_direct_sender_open_does_not_fall_back_to_physical_camera_names() -> None:
    payload = (
        b'{"all_devices":["FaceTime HD Camera"],'
        b'"camera_access_status":"authorized",'
        b'"environment_device_enumeration_empty":false}\0'
    )
    fake_cdll = FakeCDLL(
        include_list_devices=True,
        list_devices_payload=payload,
        expected_start_name=b"AKVC Direct",
    )
    fake_lib = Path("/tmp/libakvc-macos-direct-sender.dylib")

    with (
        patch("akvc.platforms.macos.direct_sender.find_macos_direct_sender_library", return_value=fake_lib),
        patch("akvc.platforms.macos.direct_sender.ctypes.CDLL", return_value=fake_cdll),
    ):
        sender = MacDirectCameraSender(
            width=1280,
            height=720,
            fps=30.0,
            camera_name="AK Virtual Camera",
        )
        try:
            try:
                sender.open()
            except RuntimeError as exc:
                assert "camera device not found" in str(exc)
            else:
                raise AssertionError("expected direct sender open() to fail")
        finally:
            sender.close()

    assert fake_cdll.start_calls == [b"AK Virtual Camera"]
    assert fake_cdll.destroy_calls == 1
