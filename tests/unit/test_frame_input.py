# SPDX-License-Identifier: Apache-2.0
"""Frame input adapter tests."""

from __future__ import annotations

import numpy as np

from akvc.core.frame import FourCC
from akvc.core.frame_input import coerce_direct_frame_input, coerce_frame_input


class FakeBits(bytearray):
    def setsize(self, size: int) -> None:
        self._size = size

    def asstring(self, size: int) -> bytes:
        return bytes(self[:size])


class FakeQImage:
    class Format:
        Format_BGR888 = 1
        Format_RGB888 = 2
        Format_RGBA8888 = 3
        Format_BGRA8888 = 4
        Format_Grayscale8 = 5
        Format_Indexed8 = 6
        Format_ARGB32 = 7
        Format_Invalid = 99

    def __init__(
        self,
        width: int,
        height: int,
        payload: bytes,
        *,
        fmt: int,
        bytes_per_line: int,
        converted_image: "FakeQImage | None" = None,
    ) -> None:
        self._width = width
        self._height = height
        self._payload = payload
        self._format = fmt
        self._bytes_per_line = bytes_per_line
        self._converted_image = converted_image
        self.convert_calls: list[int] = []

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def bytesPerLine(self) -> int:
        return self._bytes_per_line

    def format(self) -> int:
        return self._format

    def constBits(self) -> FakeBits:
        return FakeBits(self._payload)

    def convertToFormat(self, fmt: int):
        self.convert_calls.append(fmt)
        if self._converted_image is None:
            raise RuntimeError(f"cannot convert to format {fmt}")
        return self._converted_image


class FakeQImageBitsOnly(FakeQImage):
    def constBits(self) -> FakeBits:
        raise AttributeError("constBits not available")

    def bits(self) -> FakeBits:
        return FakeBits(self._payload)


class FakeQPixmap:
    def __init__(self, image: FakeQImage) -> None:
        self._image = image

    def toImage(self) -> FakeQImage:
        return self._image


def test_coerce_frame_input_accepts_bgr_ndarray() -> None:
    bgr = np.zeros((3, 4, 3), dtype=np.uint8)
    bgr[0, 0] = [7, 8, 9]

    frame = coerce_frame_input(bgr)

    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 4
    assert frame.height == 3
    assert frame.data[:3].tolist() == [7, 8, 9]


def test_coerce_frame_input_accepts_bgra_ndarray_and_drops_alpha() -> None:
    bgra = np.zeros((2, 2, 4), dtype=np.uint8)
    bgra[0, 0] = [10, 20, 30, 255]

    frame = coerce_frame_input(bgra)

    assert frame.fourcc == FourCC.RGB24
    assert frame.data[:3].tolist() == [10, 20, 30]


def test_coerce_direct_frame_input_preserves_bgra_ndarray() -> None:
    bgra = np.zeros((2, 2, 4), dtype=np.uint8)
    bgra[0, 0] = [10, 20, 30, 255]

    frame = coerce_direct_frame_input(bgra)

    assert frame.fourcc == FourCC.BGRA32
    assert frame.data[:4].tolist() == [10, 20, 30, 255]


def test_coerce_direct_frame_input_upconverts_bgr_ndarray_to_bgra() -> None:
    bgr = np.zeros((1, 2, 3), dtype=np.uint8)
    bgr[0, 0] = [10, 20, 30]
    bgr[0, 1] = [40, 50, 60]

    frame = coerce_direct_frame_input(bgr)

    assert frame.fourcc == FourCC.BGRA32
    assert frame.data[:8].tolist() == [10, 20, 30, 255, 40, 50, 60, 255]


def test_coerce_frame_input_accepts_grayscale_ndarray_and_expands_to_bgr() -> None:
    gray = np.array([[7, 9]], dtype=np.uint8)

    frame = coerce_frame_input(gray)

    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 2
    assert frame.height == 1
    assert frame.data[:6].tolist() == [7, 7, 7, 9, 9, 9]


def test_coerce_frame_input_accepts_float_ndarray_and_clips_to_uint8() -> None:
    bgr = np.array([[[12.4, 260.8, -5.0]]], dtype=np.float32)

    frame = coerce_frame_input(bgr)

    assert frame.fourcc == FourCC.RGB24
    assert frame.data[:3].tolist() == [12, 255, 0]


def test_coerce_frame_input_accepts_qimage_rgb888_and_converts_to_bgr() -> None:
    # Two RGB pixels: (30,20,10) then (60,50,40)
    image = FakeQImage(
        2,
        1,
        bytes([30, 20, 10, 60, 50, 40]),
        fmt=FakeQImage.Format.Format_RGB888,
        bytes_per_line=6,
    )

    frame = coerce_frame_input(image)

    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 2
    assert frame.height == 1
    assert frame.data[:6].tolist() == [10, 20, 30, 40, 50, 60]


def test_coerce_frame_input_accepts_qpixmap_via_toimage() -> None:
    image = FakeQImage(
        1,
        1,
        bytes([1, 2, 3]),
        fmt=FakeQImage.Format.Format_BGR888,
        bytes_per_line=3,
    )

    frame = coerce_frame_input(FakeQPixmap(image))

    assert frame.fourcc == FourCC.RGB24
    assert frame.data[:3].tolist() == [1, 2, 3]


def test_coerce_frame_input_accepts_qimage_grayscale8_and_expands_to_bgr() -> None:
    image = FakeQImage(
        2,
        1,
        bytes([9, 27]),
        fmt=FakeQImage.Format.Format_Grayscale8,
        bytes_per_line=2,
    )

    frame = coerce_frame_input(image)

    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 2
    assert frame.height == 1
    assert frame.data[:6].tolist() == [9, 9, 9, 27, 27, 27]


def test_coerce_frame_input_converts_qimage_via_converttoformat_when_needed() -> None:
    converted = FakeQImage(
        1,
        1,
        bytes([4, 5, 6]),
        fmt=FakeQImage.Format.Format_BGR888,
        bytes_per_line=3,
    )
    image = FakeQImage(
        1,
        1,
        bytes([9, 8, 7, 6]),
        fmt=FakeQImage.Format.Format_RGBA8888,
        bytes_per_line=4,
        converted_image=converted,
    )

    frame = coerce_frame_input(image)

    assert frame.fourcc == FourCC.RGB24
    assert frame.data[:3].tolist() == [4, 5, 6]
    assert image.convert_calls == [FakeQImage.Format.Format_BGR888]


def test_coerce_direct_frame_input_prefers_bgra_conversion_when_qimage_format_is_unsupported() -> None:
    converted = FakeQImage(
        1,
        1,
        bytes([7, 8, 9, 255]),
        fmt=FakeQImage.Format.Format_BGRA8888,
        bytes_per_line=4,
    )
    image = FakeQImage(
        1,
        1,
        bytes([0, 1, 2, 3]),
        fmt=FakeQImage.Format.Format_Invalid,
        bytes_per_line=4,
        converted_image=converted,
    )

    frame = coerce_direct_frame_input(image)

    assert frame.fourcc == FourCC.BGRA32
    assert bytes(frame.data[:4]) == bytes([7, 8, 9, 255])
    assert image.convert_calls == [FakeQImage.Format.Format_BGRA8888]


def test_coerce_direct_frame_input_preserves_qimage_bgra8888() -> None:
    image = FakeQImage(
        1,
        1,
        bytes([4, 5, 6, 255]),
        fmt=FakeQImage.Format.Format_BGRA8888,
        bytes_per_line=4,
    )

    frame = coerce_direct_frame_input(image)

    assert frame.fourcc == FourCC.BGRA32
    assert bytes(frame.data[:4]) == bytes([4, 5, 6, 255])


def test_coerce_direct_frame_input_upconverts_qimage_bgr888_to_bgra() -> None:
    image = FakeQImage(
        2,
        1,
        bytes([1, 2, 3, 4, 5, 6]),
        fmt=FakeQImage.Format.Format_BGR888,
        bytes_per_line=6,
    )

    frame = coerce_direct_frame_input(image)

    assert frame.fourcc == FourCC.BGRA32
    assert bytes(frame.data[:8]) == bytes([1, 2, 3, 255, 4, 5, 6, 255])


def test_coerce_frame_input_can_fall_back_to_grayscale_qimage_conversion() -> None:
    converted = FakeQImage(
        2,
        1,
        bytes([6, 30]),
        fmt=FakeQImage.Format.Format_Grayscale8,
        bytes_per_line=2,
    )
    image = FakeQImage(
        2,
        1,
        bytes([0, 1, 2, 3, 4, 5, 6, 7]),
        fmt=999,
        bytes_per_line=8,
        converted_image=converted,
    )

    frame = coerce_frame_input(image)

    assert frame.fourcc == FourCC.RGB24
    assert frame.width == 2
    assert frame.height == 1
    assert frame.data[:6].tolist() == [6, 6, 6, 30, 30, 30]


def test_coerce_frame_input_supports_qimage_bits_fallback_when_constbits_missing() -> None:
    image = FakeQImageBitsOnly(
        1,
        1,
        bytes([11, 12, 13]),
        fmt=FakeQImage.Format.Format_BGR888,
        bytes_per_line=3,
    )

    frame = coerce_frame_input(image)

    assert frame.fourcc == FourCC.RGB24
    assert frame.data[:3].tolist() == [11, 12, 13]


def test_coerce_frame_input_rejects_unsupported_array_shape() -> None:
    invalid = np.zeros((1, 1, 2), dtype=np.uint8)

    try:
        coerce_frame_input(invalid)
    except ValueError as exc:
        assert "HxW, HxWx3, or HxWx4" in str(exc)
    else:
        raise AssertionError("expected ValueError for unsupported ndarray shape")
