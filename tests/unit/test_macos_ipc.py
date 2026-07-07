# SPDX-License-Identifier: Apache-2.0
"""macOS IPC surface tests."""

from __future__ import annotations

import os
from pathlib import Path

from akvc.platforms.macos.installer import ExtensionInstallState, ExtensionStatus
from akvc.platforms.macos.ipc import (
    CAMERA_NAME_ENV,
    DEFAULT_CAMERA_NAME_FILE,
    DEFAULT_SHARED_STATE_DIR,
    DEFAULT_SHARED_MEMORY_NAME_FILE,
    DEFAULT_SUPPORTED_FORMATS,
    DEFAULT_SUPPORTED_FRAME_RATES,
    apply_camera_name_override,
    apply_shared_memory_name_override,
    default_camera_name_override_path,
    MacFrameBusLayout,
    MacIPCDescriptor,
    MacStreamCapabilities,
    default_framebus_layout,
    default_shared_memory_name_override_path,
    read_camera_name_override,
    resolve_camera_name_override_path,
    ipc_descriptor_from_status,
    read_shared_memory_name_override,
    resolve_shared_memory_name_override_path,
    stream_capabilities_from_status,
    validate_camera_name,
    write_camera_name_override,
    validate_shared_memory_name,
    write_shared_memory_name_override,
)


def test_default_framebus_layout_matches_protocol_contract() -> None:
    layout = default_framebus_layout()

    assert isinstance(layout, MacFrameBusLayout)
    assert layout.shared_memory_name == "/akvc-frames-v1"
    assert layout.schema_version == 2
    assert layout.slot_count == 4
    assert layout.slot_size == 0x00300000
    assert layout.region_size > layout.ring_control_size


def test_ipc_descriptor_from_status_uses_status_overrides() -> None:
    status = ExtensionStatus(
        state=ExtensionInstallState.INSTALLED,
        devices=["AK Virtual Camera"],
        enabled=True,
        shared_memory_name="/akvc-custom",
        mach_service_name="group.com.sidus.amaran-desktop.cameraextension",
        ipc_transport="iosurface_ring",
        ipc_probe_present=True,
        ipc_ready=False,
        ipc_environment_blocked=True,
        ipc_last_error="probe status=producer_open_failed; direct_open_errno=1",
        ipc_probe_path="/tmp/framebus-roundtrip.json",
        ipc_direct_open_errno=1,
    )

    descriptor = ipc_descriptor_from_status(status)

    assert isinstance(descriptor, MacIPCDescriptor)
    assert descriptor.transport == "iosurface_ring"
    assert descriptor.framebus.shared_memory_name == "/akvc-custom"
    assert descriptor.mach_service_name == "group.com.sidus.amaran-desktop.cameraextension"
    assert descriptor.probe_path == "/tmp/framebus-roundtrip.json"
    assert descriptor.ready is False
    assert descriptor.environment_blocked is True
    assert descriptor.direct_open_errno == 1
    assert "producer_open_failed" in str(descriptor.last_error)


def test_stream_capabilities_from_status_falls_back_to_defaults() -> None:
    capabilities = stream_capabilities_from_status(ExtensionStatus())

    assert isinstance(capabilities, MacStreamCapabilities)
    assert capabilities.supported_formats == DEFAULT_SUPPORTED_FORMATS
    assert capabilities.supported_frame_rates == DEFAULT_SUPPORTED_FRAME_RATES


def test_stream_capabilities_from_status_prefers_status_payload() -> None:
    status = ExtensionStatus(
        supported_formats=["1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        supported_frame_rates=[30, 60],
    )

    capabilities = stream_capabilities_from_status(status)

    assert capabilities.supported_formats == (
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    )
    assert capabilities.supported_frame_rates == (30, 60)


def test_shared_memory_name_override_path_defaults_to_shared_state_dir() -> None:
    path = default_shared_memory_name_override_path()

    assert path == DEFAULT_SHARED_STATE_DIR / DEFAULT_SHARED_MEMORY_NAME_FILE
    assert "Library/Group Containers/group.com.sidus.amaran-desktop/akvc-shared" in str(path)


def test_shared_memory_name_override_round_trip_uses_explicit_path(tmp_path) -> None:
    path = tmp_path / "akvc-macos-shm-name.txt"

    written = write_shared_memory_name_override("/akvc-custom", path=path)
    observed = read_shared_memory_name_override(path=path)

    assert written == path
    assert path.read_text(encoding="utf-8") == "/akvc-custom\n"
    assert observed == "/akvc-custom"


def test_camera_name_override_path_defaults_to_shared_state_dir() -> None:
    path = default_camera_name_override_path()

    assert path == DEFAULT_SHARED_STATE_DIR / DEFAULT_CAMERA_NAME_FILE
    assert "Library/Group Containers/group.com.sidus.amaran-desktop/akvc-shared" in str(path)


def test_camera_name_override_round_trip_uses_explicit_path(tmp_path) -> None:
    path = tmp_path / "akvc-macos-device-name.txt"

    written = write_camera_name_override("Demo Camera", path=path)
    observed = read_camera_name_override(path=path)

    assert written == path
    assert path.read_text(encoding="utf-8") == "Demo Camera\n"
    assert observed == "Demo Camera"


def test_apply_shared_memory_name_override_sets_env_and_tolerates_write_errors(
    monkeypatch,
    tmp_path,
) -> None:
    path = tmp_path / "akvc-macos-shm-name.txt"
    monkeypatch.delenv("AKVC_MACOS_SHM_NAME", raising=False)

    original_write_text = Path.write_text

    def fake_write_text(self: Path, data: str, encoding: str = "utf-8", **kwargs) -> int:
        del data, encoding, kwargs
        if self == path:
            raise PermissionError("blocked")
        return original_write_text(self, "", encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    written = apply_shared_memory_name_override("/akvc-demo", path=path)

    assert written is None
    assert os.environ["AKVC_MACOS_SHM_NAME"] == "/akvc-demo"
    assert path.exists() is False


def test_apply_camera_name_override_sets_env_and_tolerates_write_errors(
    monkeypatch,
    tmp_path,
) -> None:
    path = tmp_path / "akvc-macos-device-name.txt"
    monkeypatch.delenv(CAMERA_NAME_ENV, raising=False)

    original_write_text = Path.write_text

    def fake_write_text(self: Path, data: str, encoding: str = "utf-8", **kwargs) -> int:
        del data, encoding, kwargs
        if self == path:
            raise PermissionError("blocked")
        return original_write_text(self, "", encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    written = apply_camera_name_override("Demo Camera", path=path)

    assert written is None
    assert os.environ[CAMERA_NAME_ENV] == "Demo Camera"
    assert path.exists() is False


def test_resolve_shared_memory_name_override_path_prefers_env(monkeypatch, tmp_path) -> None:
    expected = tmp_path / "override.txt"
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(expected))

    assert resolve_shared_memory_name_override_path() == expected


def test_resolve_camera_name_override_path_prefers_env(monkeypatch, tmp_path) -> None:
    expected = tmp_path / "camera-name.txt"
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(expected))

    assert resolve_camera_name_override_path() == expected


def test_validate_shared_memory_name_rejects_invalid_values() -> None:
    assert validate_shared_memory_name("/akvc-valid") == "/akvc-valid"

    try:
        validate_shared_memory_name("akvc-invalid")
    except ValueError as exc:
        assert "start with '/'" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing leading slash to be rejected")


def test_validate_camera_name_rejects_invalid_values() -> None:
    assert validate_camera_name("Demo Camera") == "Demo Camera"

    try:
        validate_camera_name(" \n ")
    except ValueError as exc:
        assert "must not be empty" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected blank camera name to be rejected")
