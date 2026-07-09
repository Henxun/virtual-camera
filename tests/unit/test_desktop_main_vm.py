# SPDX-License-Identifier: Apache-2.0
"""ViewModel payload coverage for desktop install and IPC status."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAMERA_CORE_SRC = ROOT / "camera-core" / "src"
DESKTOP_SRC = ROOT / "apps" / "desktop"


def test_main_view_model_emits_ipc_install_fields() -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        import types

        sys.path.insert(0, r"{camera_core_src}")
        sys.path.insert(0, r"{desktop_src}")

        class FakeBoundSignal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)
            def emit(self, *args, **kwargs):
                for callback in list(self.callbacks):
                    callback(*args, **kwargs)

        class FakeSignalDescriptor:
            def __init__(self):
                self.name = None
            def __set_name__(self, owner, name):
                self.name = name
            def __get__(self, instance, owner):
                if instance is None:
                    return self
                signal = instance.__dict__.get(self.name)
                if signal is None:
                    signal = FakeBoundSignal()
                    instance.__dict__[self.name] = signal
                return signal

        def Signal(*args, **kwargs):
            return FakeSignalDescriptor()

        def Slot(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class QObject:
            def __init__(self, parent=None):
                self.parent = parent

        class FakeTimeoutSignal(FakeBoundSignal):
            pass

        class QTimer:
            def __init__(self, parent=None):
                self.parent = parent
                self.interval = 0
                self.timeout = FakeTimeoutSignal()
                self.started = False
            def setInterval(self, interval):
                self.interval = interval
            def start(self):
                self.started = True

        class QThread(QObject):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.started = FakeBoundSignal()
                self.finished = FakeBoundSignal()
            def start(self):
                self.started.emit()
            def quit(self):
                self.finished.emit()
            def deleteLater(self):
                pass

        class QImage:
            Format = types.SimpleNamespace(Format_RGB888=0)
            def __init__(self, *args, **kwargs):
                pass

        class QPixmap:
            @classmethod
            def fromImage(cls, image):
                return ("pixmap", image)

        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.QObject = QObject
        qtcore.QThread = QThread
        qtcore.QTimer = QTimer
        qtcore.Signal = Signal
        qtcore.Slot = Slot
        qtgui = types.ModuleType("PySide6.QtGui")
        qtgui.QImage = QImage
        qtgui.QPixmap = QPixmap

        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui

        from akvc_app.viewmodels.main_vm import MainViewModel

        worker_status = types.SimpleNamespace(
            running=False,
            fps=0.0,
            frames_published=0,
            frames_dropped=0,
            consumer_count=0,
            last_preview=None,
            last_error="",
            install_state="installed",
            install_phase="installed_visible",
            install_devices=["AK Virtual Camera"],
            install_all_devices=["FaceTime HD Camera", "AK Virtual Camera"],
            install_device_prefix="AK Virtual Camera",
            approval_required=False,
            install_enabled=True,
            supported_formats=["1280x720@30/60 NV12", "1920x1080@30/60 NV12"],
            supported_frame_rates=[30, 60],
            ipc_transport="shared_memory_ringbuffer",
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
            ipc_probe_path="/tmp/framebus-roundtrip.json",
            ipc_direct_open_errno=13,
            install_blocker_code="ipc_environment_blocked",
            install_message="系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止。",
            install_steps=["step 1"],
            verification_targets=[],
            manual_app_validation_present=True,
            manual_app_validation_ready=False,
            manual_app_validation_failed_criteria=["system_camera_device_visible"],
            manual_app_validation_failed_labels=["系统已枚举到虚拟摄像头"],
            manual_app_validation_unknown_criteria=["notarization_tooling_ready"],
            manual_app_validation_unknown_labels=["公证工具链已就绪"],
            manual_app_validation_blockers=["system_camera_device_visible", "notarization_tooling_ready"],
            manual_app_validation_blocker_labels=["系统已枚举到虚拟摄像头", "公证工具链已就绪"],
            manual_app_validation_manifest_path="/tmp/session-manifest.json",
            can_open_settings=True,
            stream_start_ready=False,
            stream_start_message="系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止。",
            runtime_topology_kind="camera_extension_direct_framebus",
            runtime_frame_path="python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
            runtime_host_role="container_activation_command_bridge",
            runtime_host_in_frame_hot_path=False,
            runtime_dedicated_host_daemon_required=False,
            runtime_container_app_configured=True,
            runtime_data_plane="shared_memory_ringbuffer",
            runtime_control_plane="host_activation_plus_sync_ipc",
        )

        class FakeFacade:
            def poll_status(self):
                return worker_status
            def install_virtual_camera(self):
                return worker_status
            def recheck_install_status(self):
                return worker_status
            def open_install_settings(self):
                return True
            def list_sources(self):
                return []
            def selected_source(self):
                return None
            def select_source(self, source_id):
                self.selected = source_id
            def start(self):
                pass
            def stop(self):
                pass

        vm = MainViewModel(FakeFacade())
        install_payloads = []
        metrics_payloads = []
        vm.install_status_changed.connect(install_payloads.append)
        vm.metrics_changed.connect(metrics_payloads.append)

        vm.install_virtual_camera()
        vm._poll_status()

        payload = {{
            "install_all_devices": install_payloads[-1]["all_devices"],
            "install_device_prefix": install_payloads[-1]["device_prefix"],
            "install_ipc_probe_present": install_payloads[-1]["ipc_probe_present"],
            "install_ipc_ready": install_payloads[-1]["ipc_ready"],
            "install_ipc_environment_blocked": install_payloads[-1]["ipc_environment_blocked"],
            "install_ipc_direct_open_errno": install_payloads[-1]["ipc_direct_open_errno"],
            "install_blocker_code": install_payloads[-1]["install_blocker_code"],
            "install_manual_app_validation_ready": install_payloads[-1]["manual_app_validation_ready"],
            "install_manual_app_validation_blockers": install_payloads[-1]["manual_app_validation_blockers"],
            "install_manual_app_validation_blocker_labels": install_payloads[-1]["manual_app_validation_blocker_labels"],
            "install_supported_formats": install_payloads[-1]["supported_formats"],
            "install_supported_frame_rates": install_payloads[-1]["supported_frame_rates"],
            "install_runtime_topology_kind": install_payloads[-1]["runtime_topology_kind"],
            "install_runtime_host_role": install_payloads[-1]["runtime_host_role"],
            "install_runtime_host_in_frame_hot_path": install_payloads[-1]["runtime_host_in_frame_hot_path"],
            "install_runtime_container_app_configured": install_payloads[-1]["runtime_container_app_configured"],
            "metrics_ipc_transport": metrics_payloads[-1]["ipc_transport"],
            "metrics_ipc_probe_path": metrics_payloads[-1]["ipc_probe_path"],
            "metrics_install_all_devices": metrics_payloads[-1]["install_all_devices"],
            "metrics_install_device_prefix": metrics_payloads[-1]["install_device_prefix"],
            "metrics_install_blocker_code": metrics_payloads[-1]["install_blocker_code"],
            "metrics_manual_app_validation_ready": metrics_payloads[-1]["manual_app_validation_ready"],
            "metrics_manual_app_validation_blockers": metrics_payloads[-1]["manual_app_validation_blockers"],
            "metrics_manual_app_validation_blocker_labels": metrics_payloads[-1]["manual_app_validation_blocker_labels"],
            "metrics_supported_formats": metrics_payloads[-1]["supported_formats"],
            "metrics_supported_frame_rates": metrics_payloads[-1]["supported_frame_rates"],
            "metrics_stream_start_ready": metrics_payloads[-1]["stream_start_ready"],
            "metrics_runtime_data_plane": metrics_payloads[-1]["runtime_data_plane"],
            "metrics_runtime_control_plane": metrics_payloads[-1]["runtime_control_plane"],
        }}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC), desktop_src=str(DESKTOP_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == {
        "install_all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
        "install_blocker_code": "ipc_environment_blocked",
        "install_device_prefix": "AK Virtual Camera",
        "install_ipc_direct_open_errno": 13,
        "install_ipc_environment_blocked": True,
        "install_ipc_probe_present": True,
        "install_ipc_ready": False,
        "install_manual_app_validation_blocker_labels": ["系统已枚举到虚拟摄像头", "公证工具链已就绪"],
        "install_manual_app_validation_blockers": ["system_camera_device_visible", "notarization_tooling_ready"],
        "install_manual_app_validation_ready": False,
        "install_runtime_container_app_configured": True,
        "install_runtime_host_in_frame_hot_path": False,
        "install_runtime_host_role": "container_activation_command_bridge",
        "install_runtime_topology_kind": "camera_extension_direct_framebus",
        "install_supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"],
        "install_supported_frame_rates": [30, 60],
        "metrics_install_all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
        "metrics_install_blocker_code": "ipc_environment_blocked",
        "metrics_install_device_prefix": "AK Virtual Camera",
        "metrics_ipc_probe_path": "/tmp/framebus-roundtrip.json",
        "metrics_ipc_transport": "shared_memory_ringbuffer",
        "metrics_manual_app_validation_blocker_labels": ["系统已枚举到虚拟摄像头", "公证工具链已就绪"],
        "metrics_manual_app_validation_blockers": ["system_camera_device_visible", "notarization_tooling_ready"],
        "metrics_manual_app_validation_ready": False,
        "metrics_runtime_control_plane": "host_activation_plus_sync_ipc",
        "metrics_runtime_data_plane": "shared_memory_ringbuffer",
        "metrics_stream_start_ready": False,
        "metrics_supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"],
        "metrics_supported_frame_rates": [30, 60],
    }


def test_main_vm_propagates_producer_side_ipc_blocker_state() -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        import types

        sys.path.insert(0, r"{camera_core_src}")
        sys.path.insert(0, r"{desktop_src}")

        class FakeSignal:
            def __init__(self, *args, **kwargs):
                self._callbacks = []
            def connect(self, callback):
                self._callbacks.append(callback)
            def emit(self, *args, **kwargs):
                for callback in list(self._callbacks):
                    callback(*args, **kwargs)

        class FakeQObject:
            def __init__(self, parent=None):
                self.parent = parent

        class FakeTimer:
            def __init__(self, parent=None):
                self.parent = parent
                self.interval = None
                self.timeout = FakeSignal()
            def setInterval(self, interval):
                self.interval = interval
            def start(self):
                self.started = True

        class FakeThread(FakeQObject):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.started = FakeSignal()
                self.finished = FakeSignal()
            def start(self):
                self.started.emit()
            def quit(self):
                self.finished.emit()
            def deleteLater(self):
                pass

        class FakeImage:
            class Format:
                Format_RGB888 = 0
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class FakePixmap:
            @staticmethod
            def fromImage(image):
                return ("pixmap", image)

        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.QObject = FakeQObject
        qtcore.QThread = FakeThread
        qtcore.QTimer = FakeTimer
        qtcore.Signal = FakeSignal
        def Slot(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
        qtcore.Slot = Slot
        qtgui = types.ModuleType("PySide6.QtGui")
        qtgui.QImage = FakeImage
        qtgui.QPixmap = FakePixmap
        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui

        from akvc_app.viewmodels.main_vm import MainViewModel

        worker_status = types.SimpleNamespace(
            running=False,
            fps=0.0,
            frames_published=0,
            frames_dropped=0,
            consumer_count=0,
            last_preview=None,
            last_error="",
            install_state="installed",
            install_phase="installed_visible",
            install_devices=["AK Virtual Camera"],
            install_all_devices=["AK Virtual Camera"],
            install_device_prefix="AK Virtual Camera",
            approval_required=False,
            install_enabled=True,
            supported_formats=["1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
            supported_frame_rates=[30, 60],
            runtime_topology_kind="camera_extension",
            runtime_frame_path="direct_sender",
            runtime_host_role="container_activation_command_bridge",
            runtime_host_in_frame_hot_path=False,
            runtime_dedicated_host_daemon_required=False,
            runtime_container_app_configured=True,
            runtime_data_plane="cmio_sink_stream",
            runtime_control_plane="system_extension_activation",
            ipc_transport="iosurface_ring",
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
            ipc_probe_path="/tmp/framebus-roundtrip.json",
            ipc_direct_open_errno=1,
            install_blocker_code="ipc_environment_blocked",
            install_message="系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止。",
            install_steps=["step 1"],
            verification_targets=[],
            can_open_settings=True,
            stream_start_ready=False,
            stream_start_message="系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止。",
        )

        class FakeFacade:
            def poll_status(self):
                return worker_status
            def install_virtual_camera(self):
                return worker_status
            def recheck_install_status(self):
                return worker_status
            def open_install_settings(self):
                return True
            def list_sources(self):
                return []
            def selected_source(self):
                return None
            def select_source(self, source_id):
                self.selected = source_id
            def start(self):
                pass
            def stop(self):
                pass

        vm = MainViewModel(FakeFacade())
        install_payloads = []
        metrics_payloads = []
        vm.install_status_changed.connect(install_payloads.append)
        vm.metrics_changed.connect(metrics_payloads.append)

        vm.install_virtual_camera()
        vm._poll_status()

        payload = {{
            "install_ipc_direct_open_errno": install_payloads[-1]["ipc_direct_open_errno"],
            "install_ipc_environment_blocked": install_payloads[-1]["ipc_environment_blocked"],
            "install_blocker_code": install_payloads[-1]["install_blocker_code"],
            "install_supported_formats": install_payloads[-1]["supported_formats"],
            "install_supported_frame_rates": install_payloads[-1]["supported_frame_rates"],
            "metrics_ipc_transport": metrics_payloads[-1]["ipc_transport"],
            "metrics_ipc_direct_open_errno": metrics_payloads[-1]["ipc_direct_open_errno"],
            "metrics_install_blocker_code": metrics_payloads[-1]["install_blocker_code"],
            "metrics_stream_start_ready": metrics_payloads[-1]["stream_start_ready"],
            "metrics_ipc_last_error": metrics_payloads[-1]["ipc_last_error"],
            "metrics_supported_formats": metrics_payloads[-1]["supported_formats"],
            "metrics_supported_frame_rates": metrics_payloads[-1]["supported_frame_rates"],
        }}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC), desktop_src=str(DESKTOP_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"install_blocker_code": "ipc_environment_blocked", "install_ipc_direct_open_errno": 1, "install_ipc_environment_blocked": true, '
        '"install_supported_formats": ["1920x1080@30/60 NV12", "3840x2160@30/60 NV12"], "install_supported_frame_rates": [30, 60], '
        '"metrics_install_blocker_code": "ipc_environment_blocked", "metrics_ipc_direct_open_errno": 1, '
        '"metrics_ipc_last_error": "shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1", '
        '"metrics_ipc_transport": "iosurface_ring", "metrics_stream_start_ready": false, '
        '"metrics_supported_formats": ["1920x1080@30/60 NV12", "3840x2160@30/60 NV12"], "metrics_supported_frame_rates": [30, 60]}'
    )
