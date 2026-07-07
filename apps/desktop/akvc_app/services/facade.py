# SPDX-License-Identifier: Apache-2.0
"""ServiceFacade — single entry point for ViewModel layer."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Optional
try:
    from akvc._core_native import NativeRuntimeHost
except ModuleNotFoundError:  # pragma: no cover - import-contract fallback
    class NativeRuntimeHost:  # type: ignore[no-redef]
        def start_source(self, source_id: str) -> None:
            del source_id

        def stop(self) -> None:
            return None

        def snapshot(self) -> dict[str, object]:
            return {}

from .helper_service import HelperService
from .source_info import ProviderInfo, list_test_pattern_sources, list_usb_sources

log = logging.getLogger(__name__)
SettingsOpener = Callable[[], int]


if TYPE_CHECKING:
    from akvc.core.frame_provider.base import ProviderInfo
    from akvc.platforms.macos.installer import ExtensionReadiness, ExtensionStatus


def _load_macos_facade_bindings():
    from akvc.sdk.virtual_camera import VirtualCamera
    from akvc.platforms.macos.installer import (
        describe_manual_app_validation_gates,
        describe_runtime_topology,
        evaluate_extension_readiness,
        infer_extension_phase,
        load_manual_app_validation_summary,
        open_macos_install_settings,
    )

    return {
        "VirtualCamera": VirtualCamera,
        "describe_manual_app_validation_gates": describe_manual_app_validation_gates,
        "describe_runtime_topology": describe_runtime_topology,
        "evaluate_extension_readiness": evaluate_extension_readiness,
        "infer_extension_phase": infer_extension_phase,
        "load_manual_app_validation_summary": load_manual_app_validation_summary,
        "open_macos_install_settings": open_macos_install_settings,
    }


@dataclass(frozen=True)
class SourceInfo:
    id: str
    name: str
    formats: tuple[Any, ...] = ()


_PATTERN_SOURCES = [
    SourceInfo(id="test:colorbar", name="Color Bars"),
    SourceInfo(id="test:gradient", name="Gradient"),
    SourceInfo(id="test:checkerboard", name="Checkerboard"),
    SourceInfo(id="test:noise", name="Noise"),
    SourceInfo(id="test:solid", name="Solid Red"),
    SourceInfo(id="test:moving_box", name="Moving Box"),
]


def _default_settings_opener() -> int:
    return _load_macos_facade_bindings()["open_macos_install_settings"]()


def _load_frame_worker_symbols():
    from ..workers.frame_worker import WorkerCommand, frame_worker_main

    return WorkerCommand, frame_worker_main


def _probe_stream_dependencies() -> tuple[bool, str]:
    missing: list[str] = []
    for name in ("numpy", "cv2"):
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    if missing:
        return (
            False,
            "桌面推流依赖缺失，请先安装 " + " / ".join(missing) + " 后再启动虚拟摄像头。",
        )
    return True, ""


def _bundle_path_from_executable(path_like: str | Path | None) -> Path | None:
    if path_like is None:
        return None
    path = Path(path_like)
    for index, part in enumerate(path.parts):
        if part.endswith(".app"):
            return Path(*path.parts[: index + 1])
    return None


def _current_macos_container_app_kwargs() -> dict[str, str]:
    bundle_env = str(os.environ.get("AKVC_CONTAINER_APP_BUNDLE") or "").strip()
    executable_env = str(os.environ.get("AKVC_CONTAINER_APP_EXECUTABLE") or "").strip()
    if bundle_env:
        payload = {"app_bundle": bundle_env}
        if executable_env:
            payload["app_executable"] = executable_env
        return payload
    if executable_env:
        payload = {"app_executable": executable_env}
        bundle = _bundle_path_from_executable(executable_env)
        if bundle is not None:
            payload["app_bundle"] = str(bundle)
        return payload

    executable = Path(sys.executable).resolve()
    bundle = _bundle_path_from_executable(executable)
    if bundle is None or not bundle.exists():
        return {}
    payload = {"app_bundle": str(bundle)}
    if executable.is_file():
        payload["app_executable"] = str(executable)
    return payload


@dataclass
class WorkerStatus:
    running: bool = False
    fps: float = 0.0
    frames_published: int = 0
    frames_dropped: int = 0
    consumer_count: int = 0
    last_preview: bytes | None = None  # raw BGR 320×180 thumbnail bytes
    last_error: Optional[str] = None
    install_state: str = "unknown"
    install_phase: str = ""
    install_devices: list[str] = field(default_factory=list)
    install_all_devices: list[str] = field(default_factory=list)
    install_device_prefix: str = ""
    approval_required: bool = False
    install_enabled: bool = False
    supported_formats: list[str] = field(default_factory=list)
    supported_frame_rates: list[int] = field(default_factory=list)
    runtime_topology_kind: str = ""
    runtime_frame_path: str = ""
    runtime_host_role: str = ""
    runtime_host_in_frame_hot_path: bool = False
    runtime_dedicated_host_daemon_required: bool = False
    runtime_container_app_configured: bool = False
    runtime_data_plane: str = ""
    runtime_control_plane: str = ""
    ipc_transport: str = ""
    ipc_probe_present: bool = False
    ipc_ready: bool | None = None
    ipc_environment_blocked: bool = False
    ipc_last_error: str = ""
    ipc_probe_path: str = ""
    ipc_direct_open_errno: int | None = None
    install_blocker_code: str = ""
    install_message: str = ""
    install_steps: list[str] = field(default_factory=list)
    verification_targets: list[dict[str, object]] = field(default_factory=list)
    manual_app_validation_present: bool = False
    manual_app_validation_ready: bool | None = None
    manual_app_validation_failed_criteria: list[str] = field(default_factory=list)
    manual_app_validation_failed_labels: list[str] = field(default_factory=list)
    manual_app_validation_unknown_criteria: list[str] = field(default_factory=list)
    manual_app_validation_unknown_labels: list[str] = field(default_factory=list)
    manual_app_validation_blockers: list[str] = field(default_factory=list)
    manual_app_validation_blocker_labels: list[str] = field(default_factory=list)
    manual_app_validation_manifest_path: str = ""
    can_open_settings: bool = False
    stream_start_ready: bool = True
    stream_start_message: str = ""


@dataclass
class ServiceState:
    sources: list[Any] = field(default_factory=list)
    selected_source_id: Optional[str] = None
    worker_status: WorkerStatus = field(default_factory=WorkerStatus)


class ServiceFacade:
    """Facade between Qt ViewModels and native runtime host."""

    def __init__(self, *, settings_opener: SettingsOpener = _default_settings_opener) -> None:
        self._state = ServiceState()
        self._runtime = NativeRuntimeHost()
        self._runtime_mu = threading.RLock()
        self._is_windows = sys.platform == "win32"
        self._is_macos = sys.platform == "darwin"
        self._helper = HelperService() if self._is_windows else None
        self._mac_camera = (
            _load_macos_facade_bindings()["VirtualCamera"](**_current_macos_container_app_kwargs()) if self._is_macos else None
        )
        self._settings_opener = settings_opener
        self._device_registered = False
        self._worker_command_cls = None
        self._stream_dependency_runtime_error = False
        self._stream_dependencies_ready, self._stream_dependency_message = _probe_stream_dependencies()
        self._state.worker_status.stream_start_ready = self._stream_dependencies_ready and not self._is_macos
        self._state.worker_status.stream_start_message = (
            ""
            if self._state.worker_status.stream_start_ready
            else (
                self._stream_dependency_message
                if not self._stream_dependencies_ready
                else "请先安装并启用 AK Virtual Camera，等待设备出现在系统摄像头列表后再开始推流。"
            )
        )

    def bootstrap(self) -> None:
        log.info("akvc.facade.bootstrap")
        self._state.sources = self._discover_sources()
        if self._state.sources:
            self._state.selected_source_id = self._state.sources[0].id

    def shutdown(self) -> None:
        log.info("akvc.facade.shutdown")
        self.stop()
        if self._helper is not None:
            try:
                self._helper.stop()
            except Exception:
                pass
        self._device_registered = False

    def list_sources(self) -> list[ProviderInfo]:
        return list(self._state.sources)

    def select_source(self, source_id: str) -> None:
        self._state.selected_source_id = source_id

    def selected_source(self) -> Optional[str]:
        return self._state.selected_source_id

    def _discover_sources(self) -> list[Any]:
        try:
            usb = list_usb_sources(max_probe=4)
        except Exception:  # pragma: no cover
            log.exception("usb probe failed")
            usb = []
        patterns = list_test_pattern_sources()
        return list(usb) + list(patterns)

    def start(self) -> None:
        if self._state.worker_status.running:
            log.info("akvc.facade.start.already_running")
            return
        if not self._state.selected_source_id:
            raise RuntimeError("no source selected")

        if self._is_windows:
            assert self._helper is not None
            helper_was_alive = self._helper.ping()
            if not helper_was_alive:
                self._device_registered = False
            if not self._helper.ensure_running():
                detail = self._helper.last_error_message or "failed to start akvc helper"
                raise RuntimeError(detail)
            if not self._helper.ping():
                raise RuntimeError("akvc helper is not responding")
            if not self._device_registered:
                if self._helper.register_mf(name="AK Virtual Camera"):
                    self._device_registered = True
                    log.info("akvc.facade.mf_registered")
                else:
                    raise RuntimeError("failed to register MF virtual camera")
        else:
            install_status = self.recheck_install_status()
            if not install_status.stream_start_ready:
                raise RuntimeError(install_status.stream_start_message or install_status.install_message)
            if not self._device_registered:
                log.info("akvc.facade.macos_camera_ready")
                self._device_registered = True

        with self._runtime_mu:
            self._runtime.start_source(self._state.selected_source_id)
        self._state.worker_status.running = True
        log.info("akvc.facade.start source=%s", self._state.selected_source_id)

    def stop(self, timeout: float = 5.0) -> None:
        if not self._state.worker_status.running:
            return
        log.info("akvc.facade.stop.begin timeout=%.3f", timeout)
        with self._runtime_mu:
            self._runtime.stop()
        self._state.worker_status.running = False
        log.info("akvc.facade.stop.graceful")

    def poll_status(self) -> WorkerStatus:
        st = self._state.worker_status
        with self._runtime_mu:
            snap = dict(self._runtime.snapshot())
        st.fps = float(snap.get("fps") or 0.0)
        st.frames_published = int(snap.get("frames_published") or 0)
        st.frames_dropped = int(snap.get("frames_dropped") or 0)
        st.consumer_count = int(snap.get("consumer_count") or 0)
        st.last_error = None if snap.get("last_error") is None else str(snap.get("last_error"))
        preview = snap.get("last_preview")
        st.last_preview = None if preview is None else bytes(preview)
        st.running = bool(snap.get("running"))
        if self._is_macos and self._mac_camera is not None:
            self.recheck_install_status()
        return st

    def _default_verification_targets(self, *, ready: bool, status_text: str) -> list[dict[str, object]]:
        labels = [
            ("zoom", "Zoom"),
            ("teams", "Teams"),
            ("google_meet", "Google Meet"),
            ("obs", "OBS"),
            ("quicktime", "QuickTime"),
            ("facetime", "FaceTime"),
        ]
        targets: list[dict[str, object]] = []
        for target_id, name in labels:
            steps = []
            if target_id == "quicktime":
                steps = ["打开 QuickTime Player 并新建影片录制。", "在摄像头列表中选择 AK Virtual Camera。"]
            elif target_id == "facetime":
                steps = ["打开 FaceTime 并进入视频菜单。", "确认 FaceTime 可以选择 AK Virtual Camera。"]
            else:
                steps = [f"打开 {name} 并进入视频设备设置。", "确认可以选择 AK Virtual Camera。"]
            targets.append(
                {
                    "id": target_id,
                    "name": name,
                    "ready": ready,
                    "status": status_text,
                    "steps": steps,
                }
            )
        return targets

    def _apply_macos_install_state(
        self,
        *,
        status: ExtensionStatus,
        readiness: ExtensionReadiness,
        devices: list[str],
        supported_formats: list[str],
        supported_frame_rates: list[int],
    ) -> WorkerStatus:
        st = self._state.worker_status
        st.install_state = status.state.value
        st.install_phase = readiness.phase
        st.install_devices = list(devices)
        st.install_all_devices = list(status.all_devices)
        st.install_device_prefix = str(status.device_prefix or "")
        st.approval_required = bool(status.approval_required)
        st.install_enabled = bool(status.enabled)
        st.supported_formats = list(supported_formats)
        st.supported_frame_rates = list(supported_frame_rates)
        topology = _load_macos_facade_bindings()["describe_runtime_topology"](status)
        st.runtime_topology_kind = str(topology.get("runtime_topology_kind") or "")
        st.runtime_frame_path = str(topology.get("runtime_frame_path") or "")
        st.runtime_host_role = str(topology.get("runtime_host_role") or "")
        st.runtime_host_in_frame_hot_path = bool(topology.get("runtime_host_in_frame_hot_path"))
        st.runtime_dedicated_host_daemon_required = bool(
            topology.get("runtime_dedicated_host_daemon_required")
        )
        st.runtime_container_app_configured = bool(topology.get("runtime_container_app_configured"))
        st.runtime_data_plane = str(topology.get("runtime_data_plane") or "")
        st.runtime_control_plane = str(topology.get("runtime_control_plane") or "")
        st.ipc_transport = str(status.ipc_transport or "")
        st.ipc_probe_present = bool(status.ipc_probe_present)
        st.ipc_ready = status.ipc_ready
        st.ipc_environment_blocked = bool(status.ipc_environment_blocked)
        st.ipc_last_error = str(status.ipc_last_error or "")
        st.ipc_probe_path = str(status.ipc_probe_path or "")
        st.ipc_direct_open_errno = status.ipc_direct_open_errno
        st.install_blocker_code = readiness.blocker_code
        st.install_message = readiness.message
        st.install_steps = list(readiness.steps)
        if len(st.install_steps) < 3:
            default_steps = [
                "Open Settings 打开系统设置并确认扩展开关状态。",
                "在 Zoom / Teams / OBS / QuickTime / FaceTime 中重新打开摄像头列表。",
                "如果设备仍未出现，运行 framebus roundtrip / status 检查工具继续诊断。",
            ]
            st.install_steps = default_steps
        st.verification_targets = list(readiness.verification_targets)
        if len(st.verification_targets) < 6:
            st.verification_targets = self._default_verification_targets(
                ready=bool(readiness.ready),
                status_text=readiness.message,
            )
        bindings = _load_macos_facade_bindings()
        summary = bindings["load_manual_app_validation_summary"]()
        st.manual_app_validation_present = summary.present
        st.manual_app_validation_ready = summary.ready
        st.manual_app_validation_failed_criteria = list(summary.failed_criteria)
        st.manual_app_validation_failed_labels = bindings["describe_manual_app_validation_gates"](summary.failed_criteria)
        st.manual_app_validation_unknown_criteria = list(summary.unknown_criteria)
        st.manual_app_validation_unknown_labels = bindings["describe_manual_app_validation_gates"](summary.unknown_criteria)
        st.manual_app_validation_blockers = list(summary.blockers)
        st.manual_app_validation_blocker_labels = bindings["describe_manual_app_validation_gates"](summary.blockers)
        st.manual_app_validation_manifest_path = str(summary.manifest_path or "")
        st.can_open_settings = True
        dependency_ready, dependency_message = _probe_stream_dependencies()
        self._stream_dependencies_ready = dependency_ready
        self._stream_dependency_message = dependency_message
        st.stream_start_ready = bool(readiness.ready) and dependency_ready
        st.stream_start_message = "" if st.stream_start_ready else (
            dependency_message or readiness.message
        )
        return st

    def recheck_install_status(self) -> WorkerStatus:
        if not self._is_macos or self._mac_camera is None:
            return self._state.worker_status
        snapshot_factory = getattr(self._mac_camera, "inspect_installation", None)
        if callable(snapshot_factory):
            snapshot = snapshot_factory()
            status = snapshot.status
            devices = list(snapshot.devices)
            readiness = snapshot.readiness
        else:
            status = self._mac_camera.status()
            devices = list(self._mac_camera.enumerate_devices())
            bindings = _load_macos_facade_bindings()
            readiness = bindings["evaluate_extension_readiness"](
                status=status,
                devices=devices,
                phase=bindings["infer_extension_phase"](
                    approval_required=bool(status.approval_required),
                    enabled=bool(status.enabled),
                    devices=devices,
                ),
            )
        capabilities_factory = getattr(self._mac_camera, "stream_capabilities", None)
        supported_formats: list[str] = list(status.supported_formats)
        supported_frame_rates: list[int] = list(status.supported_frame_rates)
        if callable(capabilities_factory):
            capabilities = capabilities_factory()
            supported_formats = [str(item) for item in getattr(capabilities, "supported_formats", ()) or ()]
            supported_frame_rates = [int(item) for item in getattr(capabilities, "supported_frame_rates", ()) or ()]
        return self._apply_macos_install_state(
            status=status,
            readiness=readiness,
            devices=devices,
            supported_formats=supported_formats,
            supported_frame_rates=supported_frame_rates,
        )

    def install_virtual_camera(self) -> WorkerStatus:
        if not self._is_macos or self._mac_camera is None:
            st = self._state.worker_status
            st.last_error = "macOS only"
            return st
        result_factory = getattr(self._mac_camera, "install_extension_result", None)
        if callable(result_factory):
            result = result_factory()
            status = result.status
            devices = list(result.enumerated_devices or status.devices)
            bindings = _load_macos_facade_bindings()
            readiness = bindings["evaluate_extension_readiness"](
                status=status,
                devices=devices,
                phase=result.phase,
            )
        else:
            self._mac_camera.install_extension()
            return self.recheck_install_status()
        capabilities_factory = getattr(self._mac_camera, "stream_capabilities", None)
        supported_formats: list[str] = list(status.supported_formats)
        supported_frame_rates: list[int] = list(status.supported_frame_rates)
        if callable(capabilities_factory):
            capabilities = capabilities_factory()
            supported_formats = [str(item) for item in getattr(capabilities, "supported_formats", ()) or ()]
            supported_frame_rates = [int(item) for item in getattr(capabilities, "supported_frame_rates", ()) or ()]
        return self._apply_macos_install_state(
            status=status,
            readiness=readiness,
            devices=devices,
            supported_formats=supported_formats,
            supported_frame_rates=supported_frame_rates,
        )

    def open_install_settings(self) -> bool:
        if not self._is_macos:
            self._state.worker_status.last_error = "macOS only"
            return False
        return self._settings_opener() == 0
