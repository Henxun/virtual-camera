# SPDX-License-Identifier: Apache-2.0
"""UI gating checks for the desktop main window."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_SRC = ROOT / "apps" / "desktop"


def test_main_window_uses_install_status_to_gate_start_button() -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        import types

        sys.path.insert(0, r"{desktop_src}")

        class FakeSignal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)
            def emit(self, *args, **kwargs):
                for callback in list(self.callbacks):
                    callback(*args, **kwargs)

        class FakeQt:
            AlignCenter = 0

        def Slot(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class FakeWidget:
            def __init__(self, parent=None):
                self.parent = parent
                self.visible = True
                self.enabled = True
                self.layout = None
            def setLayout(self, layout):
                self.layout = layout
            def setVisible(self, visible):
                self.visible = visible
            def hide(self):
                self.visible = False
            def setEnabled(self, enabled):
                self.enabled = enabled
            def isEnabled(self):
                return self.enabled

        class FakeMainWindow(FakeWidget):
            def __init__(self):
                super().__init__(None)
                self.window_title = ""
                self.size = (0, 0)
                self.central = None
                self._status_bar = None
            def setWindowTitle(self, title):
                self.window_title = title
            def resize(self, width, height):
                self.size = (width, height)
            def setCentralWidget(self, widget):
                self.central = widget
            def setStatusBar(self, bar):
                self._status_bar = bar
            def statusBar(self):
                return self._status_bar

        class FakeLabel(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.text_value = text
                self.word_wrap = False
                self.tooltip = ""
            def setText(self, text):
                self.text_value = text
            def text(self):
                return self.text_value
            def setWordWrap(self, value):
                self.word_wrap = value
            def setFixedSize(self, width, height):
                self.size = (width, height)
            def setStyleSheet(self, style):
                self.style = style
            def setAlignment(self, alignment):
                self.alignment = alignment
            def setPixmap(self, pixmap):
                self.pixmap = pixmap

        class FakeButton(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.text_value = text
                self.clicked = FakeSignal()
                self.tooltip = ""
            def setToolTip(self, text):
                self.tooltip = text
            def toolTip(self):
                return self.tooltip

        class FakeComboBox(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.currentIndexChanged = FakeSignal()
                self.items = []
                self._block = False
            def blockSignals(self, value):
                self._block = value
            def clear(self):
                self.items = []
            def addItem(self, name, data):
                self.items.append((name, data))
            def itemData(self, index):
                return self.items[index][1]

        class FakeLayout:
            def __init__(self, parent=None):
                self.parent = parent
                self.children = []
            def addWidget(self, widget, *args, **kwargs):
                self.children.append(widget)
            def addStretch(self, value):
                self.children.append(("stretch", value))

        class FakeGroupBox(FakeWidget):
            def __init__(self, title="", parent=None):
                super().__init__(parent)
                self.title = title

        class FakeStatusBar(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.message = ""
            def showMessage(self, message):
                self.message = message

        class FakeMessageBox:
            calls = []
            @classmethod
            def warning(cls, parent, title, message):
                cls.calls.append((title, message))

        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.Qt = FakeQt
        qtcore.Slot = Slot
        qtgui = types.ModuleType("PySide6.QtGui")
        qtgui.QPixmap = object
        qtwidgets = types.ModuleType("PySide6.QtWidgets")
        qtwidgets.QComboBox = FakeComboBox
        qtwidgets.QGroupBox = FakeGroupBox
        qtwidgets.QHBoxLayout = FakeLayout
        qtwidgets.QLabel = FakeLabel
        qtwidgets.QMainWindow = FakeMainWindow
        qtwidgets.QMessageBox = FakeMessageBox
        qtwidgets.QPushButton = FakeButton
        qtwidgets.QStatusBar = FakeStatusBar
        qtwidgets.QVBoxLayout = FakeLayout
        qtwidgets.QWidget = FakeWidget

        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        pyside6.QtWidgets = qtwidgets
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui
        sys.modules["PySide6.QtWidgets"] = qtwidgets

        vm_module = types.ModuleType("akvc_app.viewmodels.main_vm")
        class MainViewModel:
            pass
        vm_module.MainViewModel = MainViewModel
        sys.modules["akvc_app.viewmodels.main_vm"] = vm_module

        from akvc_app.views.main_window import MainWindow

        class FakeVm:
            def __init__(self):
                self.sources_changed = FakeSignal()
                self.selected_source_changed = FakeSignal()
                self.running_changed = FakeSignal()
                self.busy_changed = FakeSignal()
                self.state_text_changed = FakeSignal()
                self.metrics_changed = FakeSignal()
                self.install_status_changed = FakeSignal()
                self.preview_changed = FakeSignal()
                self.error = FakeSignal()
                self.refresh_sources_calls = 0
                self.recheck_install_status_calls = 0
            def refresh_sources(self):
                self.refresh_sources_calls += 1
            def recheck_install_status(self):
                self.recheck_install_status_calls += 1
            def install_virtual_camera(self):
                pass
            def open_install_settings(self):
                pass
            def start(self):
                pass
            def stop(self):
                pass
            def select_source(self, source_id):
                self.selected = source_id

        vm = FakeVm()
        window = MainWindow(vm)

        blocked_before = window._btn_start.isEnabled()
        window._on_install_status({{
            "state": "install_pending_approval",
            "phase": "pending_approval",
            "devices": [],
            "message": "请先批准扩展",
            "runtime_topology_kind": "camera_extension_direct_framebus",
            "runtime_host_role": "container_activation_command_bridge",
            "runtime_host_in_frame_hot_path": False,
            "runtime_dedicated_host_daemon_required": False,
            "runtime_container_app_configured": True,
            "runtime_data_plane": "shared_memory_ringbuffer",
            "runtime_control_plane": "host_activation_plus_sync_ipc",
            "supported_formats": ["1280x720@30/60 NV12"],
            "supported_frame_rates": [30],
            "ipc_probe_present": False,
            "ipc_ready": None,
            "ipc_environment_blocked": False,
            "ipc_transport": "",
            "ipc_direct_open_errno": None,
            "ipc_last_error": "",
            "ipc_probe_path": "",
            "steps": [],
            "verification_targets": [],
            "can_open_settings": True,
            "stream_start_ready": False,
            "stream_start_message": "桌面推流依赖缺失，请先安装 numpy / cv2 后再启动虚拟摄像头。",
        }})
        blocked_after = window._btn_start.isEnabled()
        blocked_tooltip = window._btn_start.toolTip()
        blocked_hint = window._lbl_install_hint.text_value

        window._on_install_status({{
            "state": "installed",
            "phase": "installed_visible",
            "devices": ["AK Virtual Camera"],
            "message": "已可开始推流",
            "runtime_topology_kind": "camera_extension_direct_framebus",
            "runtime_host_role": "container_activation_command_bridge",
            "runtime_host_in_frame_hot_path": False,
            "runtime_dedicated_host_daemon_required": False,
            "runtime_container_app_configured": True,
            "runtime_data_plane": "shared_memory_ringbuffer",
            "runtime_control_plane": "host_activation_plus_sync_ipc",
            "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"],
            "supported_frame_rates": [30, 60],
            "ipc_probe_present": True,
            "ipc_ready": True,
            "ipc_environment_blocked": False,
            "ipc_transport": "shared_memory_ringbuffer",
            "ipc_direct_open_errno": None,
            "ipc_last_error": "",
            "ipc_probe_path": "/tmp/framebus-roundtrip.json",
            "steps": [],
            "verification_targets": [],
            "can_open_settings": True,
            "stream_start_ready": True,
            "stream_start_message": "",
        }})
        ready_after = window._btn_start.isEnabled()
        ready_tooltip = window._btn_start.toolTip()
        ready_hint = window._lbl_install_hint.text_value

        window._on_running(True)
        running_start = window._btn_start.isEnabled()
        running_stop = window._btn_stop.isEnabled()

        payload = {{
            "refresh_sources_calls": vm.refresh_sources_calls,
            "recheck_install_status_calls": vm.recheck_install_status_calls,
            "blocked_before": blocked_before,
            "blocked_after": blocked_after,
            "blocked_tooltip": blocked_tooltip,
            "blocked_hint": blocked_hint,
            "ready_after": ready_after,
            "ready_tooltip": ready_tooltip,
            "ready_hint": ready_hint,
            "running_start": running_start,
            "running_stop": running_stop,
        }}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        """
    ).format(desktop_src=str(DESKTOP_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == {
        "blocked_after": False,
        "blocked_before": True,
        "blocked_hint": "桌面推流依赖缺失，请先安装 numpy / cv2 后再启动虚拟摄像头。",
        "blocked_tooltip": "",
        "ready_after": True,
        "ready_hint": "已可开始推流",
        "ready_tooltip": "",
        "recheck_install_status_calls": 0,
        "refresh_sources_calls": 1,
        "running_start": False,
        "running_stop": True,
    }


def test_main_window_surfaces_ipc_blocked_details_in_install_status() -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        import types

        sys.path.insert(0, r"{desktop_src}")

        class FakeSignal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)
            def emit(self, *args, **kwargs):
                for callback in list(self.callbacks):
                    callback(*args, **kwargs)

        class FakeQt:
            AlignCenter = 0

        def Slot(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class FakeWidget:
            def __init__(self, parent=None):
                self.parent = parent
                self.visible = True
                self.enabled = True
            def setVisible(self, visible):
                self.visible = visible
            def hide(self):
                self.visible = False
            def setEnabled(self, enabled):
                self.enabled = enabled
            def isEnabled(self):
                return self.enabled

        class FakeMainWindow(FakeWidget):
            def __init__(self):
                super().__init__(None)
                self._status_bar = None
            def setWindowTitle(self, title):
                self.title = title
            def resize(self, width, height):
                self.size = (width, height)
            def setCentralWidget(self, widget):
                self.central = widget
            def setStatusBar(self, bar):
                self._status_bar = bar
            def statusBar(self):
                return self._status_bar

        class FakeLabel(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.text_value = text
            def setText(self, text):
                self.text_value = text
            def setWordWrap(self, value):
                self.word_wrap = value
            def setFixedSize(self, width, height):
                self.size = (width, height)
            def setStyleSheet(self, style):
                self.style = style
            def setAlignment(self, alignment):
                self.alignment = alignment
            def setPixmap(self, pixmap):
                self.pixmap = pixmap

        class FakeButton(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.clicked = FakeSignal()
                self.tooltip = ""
            def setToolTip(self, text):
                self.tooltip = text
            def toolTip(self):
                return self.tooltip

        class FakeComboBox(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.currentIndexChanged = FakeSignal()
            def blockSignals(self, value):
                self.blocked = value
            def clear(self):
                pass
            def addItem(self, name, data):
                pass
            def itemData(self, index):
                return ""

        class FakeLayout:
            def __init__(self, parent=None):
                self.parent = parent
            def addWidget(self, widget, *args, **kwargs):
                pass
            def addStretch(self, value):
                pass

        class FakeGroupBox(FakeWidget):
            def __init__(self, title="", parent=None):
                super().__init__(parent)

        class FakeStatusBar(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.message = ""
            def showMessage(self, message):
                self.message = message

        class FakeMessageBox:
            @classmethod
            def warning(cls, parent, title, message):
                pass

        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.Qt = FakeQt
        qtcore.Slot = Slot
        qtgui = types.ModuleType("PySide6.QtGui")
        qtgui.QPixmap = object
        qtwidgets = types.ModuleType("PySide6.QtWidgets")
        qtwidgets.QComboBox = FakeComboBox
        qtwidgets.QGroupBox = FakeGroupBox
        qtwidgets.QHBoxLayout = FakeLayout
        qtwidgets.QLabel = FakeLabel
        qtwidgets.QMainWindow = FakeMainWindow
        qtwidgets.QMessageBox = FakeMessageBox
        qtwidgets.QPushButton = FakeButton
        qtwidgets.QStatusBar = FakeStatusBar
        qtwidgets.QVBoxLayout = FakeLayout
        qtwidgets.QWidget = FakeWidget

        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        pyside6.QtWidgets = qtwidgets
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui
        sys.modules["PySide6.QtWidgets"] = qtwidgets

        vm_module = types.ModuleType("akvc_app.viewmodels.main_vm")
        class MainViewModel:
            pass
        vm_module.MainViewModel = MainViewModel
        sys.modules["akvc_app.viewmodels.main_vm"] = vm_module

        from akvc_app.views.main_window import MainWindow

        class FakeVm:
            def __init__(self):
                self.sources_changed = FakeSignal()
                self.selected_source_changed = FakeSignal()
                self.running_changed = FakeSignal()
                self.busy_changed = FakeSignal()
                self.state_text_changed = FakeSignal()
                self.metrics_changed = FakeSignal()
                self.install_status_changed = FakeSignal()
                self.preview_changed = FakeSignal()
                self.error = FakeSignal()
            def refresh_sources(self):
                pass
            def install_virtual_camera(self):
                pass
            def open_install_settings(self):
                pass
            def recheck_install_status(self):
                pass
            def start(self):
                pass
            def stop(self):
                pass
            def select_source(self, source_id):
                pass

        window = MainWindow(FakeVm())
        window._on_install_status({{
            "state": "installed",
            "phase": "installed_visible",
            "devices": ["AK Virtual Camera"],
            "message": "系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止：probe status=open_failed; direct_open_errno=13",
            "runtime_topology_kind": "camera_extension_direct_framebus",
            "runtime_host_role": "container_activation_command_bridge",
            "runtime_host_in_frame_hot_path": False,
            "runtime_dedicated_host_daemon_required": False,
            "runtime_container_app_configured": True,
            "runtime_data_plane": "shared_memory_ringbuffer",
            "runtime_control_plane": "host_activation_plus_sync_ipc",
            "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
            "supported_frame_rates": [30, 60],
            "ipc_probe_present": True,
            "ipc_ready": False,
            "ipc_environment_blocked": True,
            "ipc_transport": "shared_memory_ringbuffer",
            "ipc_direct_open_errno": 13,
            "ipc_last_error": "probe status=open_failed; direct_open_errno=13",
            "ipc_probe_path": "/tmp/framebus-roundtrip.json",
            "steps": [],
            "verification_targets": [],
            "can_open_settings": True,
            "stream_start_ready": False,
            "stream_start_message": "系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止：probe status=open_failed; direct_open_errno=13",
        }})
        window._on_metrics({{
            "fps": 0.0,
            "published": 0,
            "dropped": 0,
            "consumers": 0,
            "last_error": "",
            "install_state": "installed",
            "install_phase": "installed_visible",
            "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
            "supported_frame_rates": [30, 60],
            "ipc_probe_present": True,
            "ipc_ready": False,
            "ipc_environment_blocked": True,
            "ipc_direct_open_errno": 13,
        }})

        payload = {{
            "install_label": window._lbl_install.text_value,
            "install_hint": window._lbl_install_hint.text_value,
            "status_bar": window.statusBar().message,
            "start_enabled": window._btn_start.isEnabled(),
            "start_tooltip": window._btn_start.toolTip(),
        }}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        """
    ).format(desktop_src=str(DESKTOP_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == {
        "install_hint": "系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止：probe status=open_failed; direct_open_errno=13",
        "install_label": (
            "Activation state: installed (installed_visible)\n"
            "Devices: AK Virtual Camera\n"
            "Formats: 1280x720@30/60 NV12, 1920x1080@30/60 NV12, 3840x2160@30/60 NV12\n"
            "Frame rates: 30, 60\n"
            "IPC: blocked (errno 13)"
        ),
        "start_enabled": False,
        "start_tooltip": "",
        "status_bar": "Idle | FPS 0.0 | Published 0 | Consumers 0 | installed",
    }


def test_main_window_surfaces_producer_side_ipc_blocked_details_in_install_status() -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        import types

        sys.path.insert(0, r"{desktop_src}")

        class FakeSignal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)
            def emit(self, *args, **kwargs):
                for callback in list(self.callbacks):
                    callback(*args, **kwargs)

        class FakeQt:
            AlignCenter = 0

        def Slot(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class FakeWidget:
            def __init__(self, parent=None):
                self.parent = parent
                self.visible = True
                self.enabled = True
            def setVisible(self, visible):
                self.visible = visible
            def hide(self):
                self.visible = False
            def setEnabled(self, enabled):
                self.enabled = enabled
            def isEnabled(self):
                return self.enabled

        class FakeMainWindow(FakeWidget):
            def __init__(self):
                super().__init__(None)
                self._status_bar = None
            def setWindowTitle(self, title):
                self.title = title
            def resize(self, width, height):
                self.size = (width, height)
            def setCentralWidget(self, widget):
                self.central = widget
            def setStatusBar(self, bar):
                self._status_bar = bar
            def statusBar(self):
                return self._status_bar

        class FakeLabel(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.text_value = text
            def setText(self, text):
                self.text_value = text
            def setWordWrap(self, value):
                self.word_wrap = value
            def setFixedSize(self, width, height):
                self.size = (width, height)
            def setStyleSheet(self, style):
                self.style = style
            def setAlignment(self, alignment):
                self.alignment = alignment
            def setPixmap(self, pixmap):
                self.pixmap = pixmap

        class FakeButton(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.clicked = FakeSignal()
                self.tooltip = ""
            def setToolTip(self, text):
                self.tooltip = text
            def toolTip(self):
                return self.tooltip

        class FakeComboBox(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.currentIndexChanged = FakeSignal()
            def blockSignals(self, value):
                self.blocked = value
            def clear(self):
                pass
            def addItem(self, name, data):
                pass
            def itemData(self, index):
                return ""

        class FakeLayout:
            def __init__(self, parent=None):
                self.parent = parent
            def addWidget(self, widget, *args, **kwargs):
                pass
            def addStretch(self, value):
                pass

        class FakeGroupBox(FakeWidget):
            def __init__(self, title="", parent=None):
                super().__init__(parent)

        class FakeStatusBar(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.message = ""
            def showMessage(self, message):
                self.message = message

        class FakeMessageBox:
            @classmethod
            def warning(cls, parent, title, message):
                pass

        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.Qt = FakeQt
        qtcore.Slot = Slot
        qtgui = types.ModuleType("PySide6.QtGui")
        qtgui.QPixmap = object
        qtwidgets = types.ModuleType("PySide6.QtWidgets")
        qtwidgets.QComboBox = FakeComboBox
        qtwidgets.QGroupBox = FakeGroupBox
        qtwidgets.QHBoxLayout = FakeLayout
        qtwidgets.QLabel = FakeLabel
        qtwidgets.QMainWindow = FakeMainWindow
        qtwidgets.QMessageBox = FakeMessageBox
        qtwidgets.QPushButton = FakeButton
        qtwidgets.QStatusBar = FakeStatusBar
        qtwidgets.QVBoxLayout = FakeLayout
        qtwidgets.QWidget = FakeWidget

        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        pyside6.QtWidgets = qtwidgets
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui
        sys.modules["PySide6.QtWidgets"] = qtwidgets

        vm_module = types.ModuleType("akvc_app.viewmodels.main_vm")
        class MainViewModel:
            pass
        vm_module.MainViewModel = MainViewModel
        sys.modules["akvc_app.viewmodels.main_vm"] = vm_module

        from akvc_app.views.main_window import MainWindow

        class FakeVm:
            def __init__(self):
                self.sources_changed = FakeSignal()
                self.selected_source_changed = FakeSignal()
                self.running_changed = FakeSignal()
                self.busy_changed = FakeSignal()
                self.state_text_changed = FakeSignal()
                self.metrics_changed = FakeSignal()
                self.install_status_changed = FakeSignal()
                self.preview_changed = FakeSignal()
                self.error = FakeSignal()
            def refresh_sources(self):
                pass
            def install_virtual_camera(self):
                pass
            def open_install_settings(self):
                pass
            def recheck_install_status(self):
                pass
            def start(self):
                pass
            def stop(self):
                pass
            def select_source(self, source_id):
                pass

        window = MainWindow(FakeVm())
        window._on_install_status({{
            "state": "installed",
            "phase": "installed_visible",
            "devices": ["AK Virtual Camera"],
            "message": "系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止：shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
            "supported_formats": ["1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
            "supported_frame_rates": [30, 60],
            "ipc_probe_present": True,
            "ipc_ready": False,
            "ipc_environment_blocked": True,
            "ipc_transport": "iosurface_ring",
            "ipc_direct_open_errno": 1,
            "ipc_last_error": "shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
            "ipc_probe_path": "/tmp/framebus-roundtrip.json",
            "steps": [],
            "verification_targets": [],
            "can_open_settings": True,
            "stream_start_ready": False,
            "stream_start_message": "系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止：shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
        }})
        window._on_metrics({{
            "fps": 0.0,
            "published": 0,
            "dropped": 0,
            "consumers": 0,
            "last_error": "",
            "install_state": "installed",
            "install_phase": "installed_visible",
            "supported_formats": ["1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
            "supported_frame_rates": [30, 60],
            "ipc_probe_present": True,
            "ipc_ready": False,
            "ipc_environment_blocked": True,
            "ipc_direct_open_errno": 1,
        }})

        payload = {{
            "install_label": window._lbl_install.text_value,
            "install_hint": window._lbl_install_hint.text_value,
            "status_bar": window.statusBar().message,
            "start_enabled": window._btn_start.isEnabled(),
            "start_tooltip": window._btn_start.toolTip(),
        }}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        """
    ).format(desktop_src=str(DESKTOP_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"install_hint": "系统摄像头扩展已可见，但 Python Producer 到 Camera Extension 的 FrameBus IPC 仍被当前环境阻止：shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1", '
        '"install_label": "Activation state: installed (installed_visible)\\nDevices: AK Virtual Camera\\nFormats: 1920x1080@30/60 NV12, 3840x2160@30/60 NV12\\nFrame rates: 30, 60\\nIPC: blocked (errno 1)", '
        '"start_enabled": false, '
        '"start_tooltip": "", '
        '"status_bar": "Idle | FPS 0.0 | Published 0 | Consumers 0 | installed"}'
    )


def test_main_window_surfaces_manual_app_validation_blockers_in_install_hint() -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        import types

        sys.path.insert(0, r"{desktop_src}")

        class FakeSignal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)
            def emit(self, *args, **kwargs):
                for callback in list(self.callbacks):
                    callback(*args, **kwargs)

        class FakeQt:
            AlignCenter = 0

        def Slot(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class FakeWidget:
            def __init__(self, parent=None):
                self.parent = parent
                self.visible = True
                self.enabled = True
            def setVisible(self, visible):
                self.visible = visible
            def hide(self):
                self.visible = False
            def setEnabled(self, enabled):
                self.enabled = enabled
            def isEnabled(self):
                return self.enabled

        class FakeMainWindow(FakeWidget):
            def __init__(self):
                super().__init__(None)
                self._status_bar = None
            def setWindowTitle(self, title):
                self.title = title
            def resize(self, width, height):
                self.size = (width, height)
            def setCentralWidget(self, widget):
                self.central = widget
            def setStatusBar(self, bar):
                self._status_bar = bar
            def statusBar(self):
                return self._status_bar

        class FakeLabel(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.text_value = text
            def setText(self, text):
                self.text_value = text
            def setWordWrap(self, value):
                self.word_wrap = value
            def setFixedSize(self, width, height):
                self.size = (width, height)
            def setStyleSheet(self, style):
                self.style = style
            def setAlignment(self, alignment):
                self.alignment = alignment
            def setPixmap(self, pixmap):
                self.pixmap = pixmap

        class FakeButton(FakeWidget):
            def __init__(self, text="", parent=None):
                super().__init__(parent)
                self.clicked = FakeSignal()
                self.tooltip = ""
            def setToolTip(self, text):
                self.tooltip = text
            def toolTip(self):
                return self.tooltip

        class FakeComboBox(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.currentIndexChanged = FakeSignal()
            def blockSignals(self, value):
                self.blocked = value
            def clear(self):
                pass
            def addItem(self, name, data):
                pass
            def itemData(self, index):
                return ""

        class FakeLayout:
            def __init__(self, parent=None):
                self.parent = parent
            def addWidget(self, widget, *args, **kwargs):
                pass
            def addStretch(self, value):
                pass

        class FakeGroupBox(FakeWidget):
            def __init__(self, title="", parent=None):
                super().__init__(parent)

        class FakeStatusBar(FakeWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.message = ""
            def showMessage(self, message):
                self.message = message

        class FakeMessageBox:
            @classmethod
            def warning(cls, parent, title, message):
                pass

        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.Qt = FakeQt
        qtcore.Slot = Slot
        qtgui = types.ModuleType("PySide6.QtGui")
        qtgui.QPixmap = object
        qtwidgets = types.ModuleType("PySide6.QtWidgets")
        qtwidgets.QComboBox = FakeComboBox
        qtwidgets.QGroupBox = FakeGroupBox
        qtwidgets.QHBoxLayout = FakeLayout
        qtwidgets.QLabel = FakeLabel
        qtwidgets.QMainWindow = FakeMainWindow
        qtwidgets.QMessageBox = FakeMessageBox
        qtwidgets.QPushButton = FakeButton
        qtwidgets.QStatusBar = FakeStatusBar
        qtwidgets.QVBoxLayout = FakeLayout
        qtwidgets.QWidget = FakeWidget

        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        pyside6.QtWidgets = qtwidgets
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui
        sys.modules["PySide6.QtWidgets"] = qtwidgets

        vm_module = types.ModuleType("akvc_app.viewmodels.main_vm")
        class MainViewModel:
            pass
        vm_module.MainViewModel = MainViewModel
        sys.modules["akvc_app.viewmodels.main_vm"] = vm_module

        from akvc_app.views.main_window import MainWindow

        class FakeVm:
            def __init__(self):
                self.sources_changed = FakeSignal()
                self.selected_source_changed = FakeSignal()
                self.running_changed = FakeSignal()
                self.busy_changed = FakeSignal()
                self.state_text_changed = FakeSignal()
                self.metrics_changed = FakeSignal()
                self.install_status_changed = FakeSignal()
                self.preview_changed = FakeSignal()
                self.error = FakeSignal()
            def refresh_sources(self):
                pass
            def install_virtual_camera(self):
                pass
            def open_install_settings(self):
                pass
            def recheck_install_status(self):
                pass
            def start(self):
                pass
            def stop(self):
                pass
            def select_source(self, source_id):
                pass

        window = MainWindow(FakeVm())
        window._on_install_status({{
            "state": "installed",
            "phase": "installed_visible",
            "devices": ["AK Virtual Camera"],
            "message": "虚拟摄像头已安装并出现在系统设备列表中，可在 Zoom/Meet/OBS 中继续验证。",
            "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"],
            "supported_frame_rates": [30, 60],
            "ipc_probe_present": True,
            "ipc_ready": True,
            "ipc_environment_blocked": False,
            "ipc_transport": "shared_memory_ringbuffer",
            "ipc_direct_open_errno": None,
            "ipc_last_error": "",
            "ipc_probe_path": "/tmp/framebus-roundtrip.json",
            "steps": [],
            "verification_targets": [],
            "manual_app_validation_present": True,
            "manual_app_validation_ready": False,
            "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
            "manual_app_validation_failed_labels": ["系统已枚举到虚拟摄像头"],
            "manual_app_validation_unknown_criteria": ["notarization_tooling_ready"],
            "manual_app_validation_unknown_labels": ["公证工具链已就绪"],
            "manual_app_validation_blockers": ["system_camera_device_visible", "notarization_tooling_ready"],
            "manual_app_validation_blocker_labels": ["系统已枚举到虚拟摄像头", "公证工具链已就绪"],
            "can_open_settings": True,
            "stream_start_ready": True,
            "stream_start_message": "",
        }})

        payload = {{
            "install_hint": window._lbl_install_hint.text_value,
            "start_enabled": window._btn_start.isEnabled(),
        }}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        """
    ).format(desktop_src=str(DESKTOP_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"install_hint": "虚拟摄像头已安装并出现在系统设备列表中，可在 Zoom/Meet/OBS 中继续验证。", "start_enabled": true}'
    )
