# SPDX-License-Identifier: Apache-2.0
"""Native virtual camera session smoke tests."""

from __future__ import annotations

from akvc._core_native import NativeVirtualCameraSession


def test_native_virtual_camera_session_defaults_are_idle() -> None:
    session = NativeVirtualCameraSession(1280, 720, 30.0, "")

    assert session.started is False
    assert session.consumer_count == 0

    session.close()


def test_native_virtual_camera_session_exposes_expected_methods() -> None:
    for name in ("start", "push_frame", "stop", "close"):
        assert hasattr(NativeVirtualCameraSession, name)
