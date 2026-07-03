# SPDX-License-Identifier: Apache-2.0
"""High-level virtual camera wrapper for external apps."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional
import sys

if TYPE_CHECKING:
    from akvc.platforms.macos import MacVirtualCamera


class _PassthroughPipeline:
    def process(self, frame):
        return frame


def _build_default_pipeline(width: int, height: int, fps: float):
    try:
        from akvc.core.frame_pipeline import (
            ColorConvertStage,
            FpsRegulator,
            FramePipeline,
            ResizeStage,
        )

        return (
            FramePipeline()
            .add(ResizeStage(target_w=width, target_h=height))
            .add(FpsRegulator(target_fps=fps))
            .add(ColorConvertStage(dst="NV12"))
        )
    except ModuleNotFoundError:
        return _PassthroughPipeline()


def _coerce_frame_input(frame_input):
    from akvc.core.frame_input import coerce_frame_input

    return coerce_frame_input(frame_input)


def _create_sink():
    from akvc.core.frame_sink import create_sink

    return create_sink()


def _push_widget(camera, widget) -> None:
    from akvc.integrations.pyside6 import push_widget

    push_widget(camera, widget)


def _push_screen(
    camera,
    screen,
    *,
    window: int = 0,
    x: int = 0,
    y: int = 0,
    width: int = -1,
    height: int = -1,
) -> None:
    from akvc.integrations.pyside6 import push_screen

    push_screen(
        camera,
        screen,
        window=window,
        x=x,
        y=y,
        width=width,
        height=height,
    )


def _create_latest_frame_provider(*, repeat_last: bool = True):
    from akvc.integrations.pyside6 import LatestFrameProvider

    return LatestFrameProvider(repeat_last=repeat_last)


def _create_pyside6_streamer(camera, *, timer_factory=None):
    from akvc.integrations.pyside6 import PySide6VirtualCameraStreamer

    return PySide6VirtualCameraStreamer(camera, timer_factory=timer_factory)


def _create_pyside6_bridge(camera):
    from akvc.integrations.pyside6 import PySide6VirtualCameraBridge

    return PySide6VirtualCameraBridge(camera)


def _load_macos_virtual_camera_class():
    from akvc.platforms.macos import MacVirtualCamera

    return MacVirtualCamera


def _load_helper_service_class():
    from apps.desktop.akvc_app.services.helper_service import HelperService

    return HelperService


def _load_native_virtual_camera_session_class():
    from akvc._core_native import NativeVirtualCameraSession

    return NativeVirtualCameraSession


def _frame_to_native_payload(frame_input, frame):
    try:
        import numpy as np
        from akvc.core.frame import FourCC
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in lazy-import tests
        raise RuntimeError("numpy is required to push frames on the native session path") from exc

    if isinstance(frame_input, np.ndarray):
        array = frame_input
        if array.ndim == 2:
            array = np.repeat(array[..., None], 3, axis=2)
        elif array.ndim == 3 and array.shape[2] == 4:
            array = array[..., :3]
        if array.dtype != np.uint8:
            if np.issubdtype(array.dtype, np.floating):
                array = np.clip(array, 0.0, 255.0).astype(np.uint8)
            else:
                array = np.clip(array, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(array)

    if frame.fourcc == FourCC.BGRA32:
        data = frame.data.reshape(frame.height, frame.width, 4)
        return data[:, :, :3].copy()

    data = frame.data.reshape(frame.height, frame.width, 3)
    return data.copy()


class VirtualCamera:
    """Cross-platform virtual camera facade for Windows/macOS backends."""

    def __init__(
        self,
        *,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
        camera_name: str = "AK Virtual Camera",
        direct_only: bool = False,
        app_bundle: str | Path | None = None,
        app_executable: str | Path | None = None,
        helper_exe: str | Path | None = None,
        host_bundle: str | Path | None = None,
        host_executable: str | Path | None = None,
        direct_sender_library: str | Path | None = None,
        pipeline=None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self._default_camera_name = str(camera_name).strip() or "AK Virtual Camera"
        self._is_windows = sys.platform == "win32"
        self._is_macos = sys.platform == "darwin"
        self._helper = None
        if self._is_windows:
            try:
                helper_service = _load_helper_service_class()
            except ModuleNotFoundError:
                helper_service = None
            if helper_service is not None:
                self._helper = helper_service(helper_exe=helper_exe)
        self._native_session = None
        if not self._is_macos:
            native_virtual_camera_session = _load_native_virtual_camera_session_class()
            self._native_session = native_virtual_camera_session(
                width,
                height,
                fps,
                "" if helper_exe is None else str(helper_exe),
            )
        self._using_native_session = False
        self._mac_backend = None
        if self._is_macos:
            mac_virtual_camera = _load_macos_virtual_camera_class()
            self._mac_backend = mac_virtual_camera(
                width=width,
                height=height,
                fps=fps,
                camera_name=self._default_camera_name,
                direct_only=direct_only,
                app_bundle=app_bundle,
                app_executable=app_executable,
                helper_exe=helper_exe,
                host_bundle=host_bundle,
                host_executable=host_executable,
                direct_sender_library=direct_sender_library,
                pipeline=pipeline,
            )
        self._pipeline = pipeline
        self._sink: Optional[object] = None
        self._started = False
        self._mf_registered = False
        self._last_frame_fourcc: int | None = None

    def _resolved_camera_name(self, name: str | None = None) -> str:
        normalized = str(name).strip() if name is not None else ""
        if normalized:
            self._default_camera_name = normalized
            return normalized
        return self._default_camera_name

    @property
    def started(self) -> bool:
        if self._mac_backend is not None:
            return self._mac_backend.started
        if self._using_native_session and self._native_session is not None:
            return bool(self._native_session.started)
        return self._started

    @property
    def consumer_count(self) -> int:
        if self._mac_backend is not None:
            return self._mac_backend.consumer_count
        if self._using_native_session and self._native_session is not None:
            return int(self._native_session.consumer_count)
        if self._sink is None:
            return 0
        return int(getattr(self._sink, "consumer_count", 0))

    @property
    def backend_name(self) -> str | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "backend_name", None)
        if self._using_native_session:
            return "native_session"
        if self._sink is not None or self._started:
            return "shared_memory"
        return None

    @property
    def using_direct_sender(self) -> bool:
        if self._mac_backend is not None:
            return bool(getattr(self._mac_backend, "using_direct_sender", False))
        return False

    @property
    def helper_hot_path_used(self) -> bool:
        if self._mac_backend is not None:
            return bool(getattr(self._mac_backend, "helper_hot_path_used", False))
        return bool(self._helper is not None and self._started and not self._using_native_session)

    @property
    def shared_memory_fallback_used(self) -> bool:
        if self._mac_backend is not None:
            return bool(getattr(self._mac_backend, "shared_memory_fallback_used", False))
        return bool(self._sink is not None or (self._started and not self._using_native_session))

    @property
    def direct_sender_attempted(self) -> bool:
        if self._mac_backend is not None:
            return bool(getattr(self._mac_backend, "direct_sender_attempted", False))
        return False

    @property
    def direct_sender_last_error(self) -> str | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "direct_sender_last_error", None)
        return None

    @property
    def direct_sender_target_name(self) -> str | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "direct_sender_target_name", None)
        return None

    @property
    def direct_sender_library_path(self) -> str | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "direct_sender_library_path", None)
        return None

    @property
    def direct_sender_state(self) -> str | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "direct_sender_state", None)
        return None

    @property
    def last_frame_fourcc(self) -> int | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "last_frame_fourcc", None)
        return self._last_frame_fourcc

    @property
    def last_frame_format_name(self) -> str | None:
        if self._mac_backend is not None:
            return getattr(self._mac_backend, "last_frame_format_name", None)
        if self._last_frame_fourcc is None:
            return None
        from akvc.core.frame import FourCC

        return FourCC.name(self._last_frame_fourcc)

    def start(self, name: str | None = None) -> None:
        resolved_name = self._resolved_camera_name(name)
        if self._mac_backend is not None:
            self._mac_backend.start(name=resolved_name)
            return
        if self._started:
            return
        helper_failure: RuntimeError | None = None
        if self._helper is not None:
            try:
                if not self._helper.start():
                    detail = self._helper.last_error_message or "failed to start akvc helper"
                    raise RuntimeError(detail)
                if not self._helper.ping():
                    raise RuntimeError("akvc helper is not responding")
                if not self._mf_registered:
                    if not self._helper.register_mf(name=resolved_name):
                        raise RuntimeError("failed to register MF virtual camera")
                    self._mf_registered = True
                sink = _create_sink()
                sink.open()
                self._sink = sink
                self._using_native_session = False
                self._started = True
                return
            except ModuleNotFoundError:
                self._sink = None
            except RuntimeError as exc:
                helper_failure = exc
        if helper_failure is not None:
            raise helper_failure
        if self._native_session is None:
            native_virtual_camera_session = _load_native_virtual_camera_session_class()
            self._native_session = native_virtual_camera_session(
                self.width,
                self.height,
                self.fps,
                "",
            )
        self._native_session.start(resolved_name)
        self._using_native_session = True
        self._started = True

    def push_frame(self, frame_input) -> None:
        if self._mac_backend is not None:
            self._mac_backend.push_frame(frame_input)
            return
        if not self.started:
            raise RuntimeError("virtual camera is not started")
        frame = _coerce_frame_input(frame_input)
        self._last_frame_fourcc = int(frame.fourcc)
        if self._using_native_session:
            if self._native_session is None:
                raise RuntimeError("native virtual camera session is unavailable")
            self._native_session.push_frame(_frame_to_native_payload(frame_input, frame))
            return
        if self._sink is None:
            raise RuntimeError("virtual camera sink is unavailable")
        if self._pipeline is None:
            self._pipeline = _build_default_pipeline(self.width, self.height, self.fps)
        frame = self._pipeline.process(frame)
        self._sink.publish(frame)
        self._last_frame_fourcc = int(frame.fourcc)

    def send(self, frame_input) -> None:
        self.push_frame(frame_input)

    def send_image(self, image) -> None:
        self.send(image)

    def send_pixmap(self, pixmap) -> None:
        self.send(pixmap)

    def send_widget(self, widget) -> None:
        _push_widget(self, widget)

    def send_screen(
        self,
        screen,
        *,
        window: int = 0,
        x: int = 0,
        y: int = 0,
        width: int = -1,
        height: int = -1,
    ) -> None:
        _push_screen(
            self,
            screen,
            window=window,
            x=x,
            y=y,
            width=width,
            height=height,
        )

    def create_latest_frame_provider(self, *, repeat_last: bool = True):
        if self._mac_backend is not None:
            create_provider = getattr(self._mac_backend, "create_latest_frame_provider", None)
            if callable(create_provider):
                return create_provider(repeat_last=repeat_last)
        return _create_latest_frame_provider(repeat_last=repeat_last)

    def create_pyside6_streamer(self, *, timer_factory=None):
        if self._mac_backend is not None:
            create_streamer = getattr(self._mac_backend, "create_pyside6_streamer", None)
            if callable(create_streamer):
                return create_streamer(timer_factory=timer_factory)
        return _create_pyside6_streamer(self, timer_factory=timer_factory)

    def create_pyside6_bridge(self):
        if self._mac_backend is not None:
            create_bridge = getattr(self._mac_backend, "create_pyside6_bridge", None)
            if callable(create_bridge):
                return create_bridge()
        return _create_pyside6_bridge(self)

    def stop(self) -> None:
        if self._mac_backend is not None:
            self._mac_backend.stop()
            return
        if not self._started:
            return
        if self._using_native_session and self._native_session is not None:
            self._native_session.stop()
        elif self._sink is not None:
            self._sink.close()
            self._sink = None
        self._started = False
        self._using_native_session = False

    def close(self) -> None:
        if self._mac_backend is not None:
            self._mac_backend.close()
            return
        self.stop()
        if self._helper is not None:
            self._helper.stop()
        if self._native_session is not None:
            self._native_session.close()

    def shutdown(self) -> None:
        self.close()

    def enumerate_devices(self) -> list[str]:
        if self._mac_backend is None:
            return []
        return self._mac_backend.enumerate_devices()

    def direct_sender_device_snapshot(self):
        if self._mac_backend is None:
            return None
        snapshot_getter = getattr(self._mac_backend, "direct_sender_device_snapshot", None)
        if callable(snapshot_getter):
            return snapshot_getter()
        return None

    def request_camera_access(self):
        if self._mac_backend is None:
            return None
        request_access = getattr(self._mac_backend, "request_camera_access", None)
        if callable(request_access):
            return request_access()
        return self.direct_sender_device_snapshot()

    def direct_sender_readiness(self, name: str = "AK Virtual Camera", *, request_camera_access: bool = False):
        if self._mac_backend is None:
            return None
        readiness = getattr(self._mac_backend, "direct_sender_readiness", None)
        if callable(readiness):
            return readiness(name=name, request_camera_access=request_camera_access)
        snapshot = (
            self.request_camera_access()
            if request_camera_access
            else self.direct_sender_device_snapshot()
        )
        if not isinstance(snapshot, dict):
            return None
        camera_access_status = str(snapshot.get("camera_access_status") or "").strip() or "unknown"
        visible_devices = [
            str(item).strip()
            for item in snapshot.get("all_devices", [])
            if str(item).strip()
        ] if isinstance(snapshot.get("all_devices"), list) else []
        environment_empty = bool(snapshot.get("environment_device_enumeration_empty"))
        ready = camera_access_status == "authorized" and not environment_empty
        return {
            "ready": ready,
            "blocker_code": "ready" if ready else "direct_sender_not_ready",
            "message": "direct sender readiness is unavailable from the current backend fallback path",
            "camera_name": str(name).strip() or "AK Virtual Camera",
            "camera_access_status": camera_access_status,
            "target_visible": False,
            "visible_devices": visible_devices,
            "snapshot": snapshot,
        }

    def status(self):
        if self._mac_backend is None:
            return None
        return self._mac_backend.status()

    def readiness(self):
        if self._mac_backend is None:
            return None
        return self._mac_backend.readiness()

    def ipc_descriptor(self):
        if self._mac_backend is None:
            return None
        return self._mac_backend.ipc_descriptor()

    def stream_capabilities(self):
        if self._mac_backend is None:
            return None
        return self._mac_backend.stream_capabilities()

    def inspect_installation(self):
        if self._mac_backend is None:
            return None
        return self._mac_backend.inspect_installation()

    def runtime_topology(self):
        if self._mac_backend is None:
            return None
        runtime_topology = getattr(self._mac_backend, "runtime_topology", None)
        if callable(runtime_topology):
            return runtime_topology()
        return None

    def runtime_snapshot(self):
        if self._mac_backend is None:
            return None
        runtime_snapshot = getattr(self._mac_backend, "runtime_snapshot", None)
        if callable(runtime_snapshot):
            return runtime_snapshot()
        return None

    def is_installed(self) -> bool:
        if self._mac_backend is None:
            return False
        return self._mac_backend.is_installed()

    def install_extension_result(self):
        if self._mac_backend is None:
            return None
        return self._mac_backend.install_extension_result()

    def install_extension(self) -> bool:
        if self._mac_backend is None:
            return False
        return self._mac_backend.install_extension()

    def uninstall_extension_result(self):
        if self._mac_backend is None:
            return None
        uninstall_result = getattr(self._mac_backend, "uninstall_extension_result", None)
        if not callable(uninstall_result):
            return None
        return uninstall_result()

    def uninstall_extension(self) -> bool:
        if self._mac_backend is None:
            return False
        uninstall = getattr(self._mac_backend, "uninstall_extension", None)
        if not callable(uninstall):
            return False
        return bool(uninstall())

    def sync_ipc_configuration_result(self, shared_memory_name: str | None = None):
        if self._mac_backend is None:
            return None
        sync_result = getattr(self._mac_backend, "sync_ipc_configuration_result", None)
        if not callable(sync_result):
            return None
        return sync_result(shared_memory_name)

    def sync_ipc_configuration(self, shared_memory_name: str | None = None) -> bool:
        if self._mac_backend is None:
            return False
        sync_ipc = getattr(self._mac_backend, "sync_ipc_configuration", None)
        if callable(sync_ipc):
            return bool(sync_ipc(shared_memory_name))
        result = self.sync_ipc_configuration_result(shared_memory_name)
        return bool(result and getattr(result, "supported", False) and getattr(result, "success", False))

    def __enter__(self) -> "VirtualCamera":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
