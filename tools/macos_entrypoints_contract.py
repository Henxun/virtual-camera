# SPDX-License-Identifier: Apache-2.0
"""Contract checks for current macOS Python compatibility entrypoints.

These checks verify that the surviving Python-facing demos and desktop integration
remain aligned as compatibility surfaces over the native control-layer/runtime
architecture. They are not assertions that Python is the primary architecture.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CAMERA_CORE_SRC = ROOT / "camera-core" / "src"
DESKTOP_SRC = ROOT / "apps" / "desktop"
BUILD_LIB = ROOT / "build" / "lib"
for path in (BUILD_LIB, CAMERA_CORE_SRC, DESKTOP_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

DEMO_TOOL = ROOT / "tools" / "pyside6_virtual_camera_demo.py"
DIRECT_PUSH_DEMO_TOOL = ROOT / "tools" / "macos_direct_push_demo.py"
DESKTOP_FACADE = ROOT / "apps" / "desktop" / "akvc_app" / "services" / "facade.py"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_entrypoint_surface(texts: dict[str, str]) -> dict[str, bool]:
    demo_text = texts["demo"]
    direct_push_demo_text = texts["direct_push_demo"]
    desktop_text = texts["desktop"]
    return {
        "demo_uses_python_compat_virtual_camera": "akvc.sdk.virtual_camera import VirtualCamera" in demo_text,
        "demo_avoids_macos_specific_camera_import": "MacVirtualCamera" not in demo_text,
        "demo_avoids_pyvirtualcam_reference": "pyvirtualcam" not in demo_text,
        "demo_prefers_sdk_streamer_factory": "create_pyside6_streamer" in demo_text,
        "demo_prefers_sdk_latest_provider_factory": "create_latest_frame_provider" in demo_text,
        "demo_uses_sdk_widget_push": "camera.send_widget" in demo_text,
        "demo_uses_sdk_screen_push": "camera.send_screen" in demo_text,
        "direct_push_demo_uses_python_compat_virtual_camera": (
            "akvc.sdk.virtual_camera import VirtualCamera" in direct_push_demo_text
        ),
        "direct_push_demo_avoids_macos_specific_camera_import": "MacVirtualCamera" not in direct_push_demo_text,
        "direct_push_demo_avoids_pyvirtualcam_reference": "pyvirtualcam" not in direct_push_demo_text,
        "direct_push_demo_uses_push_frame": "camera.push_frame" in direct_push_demo_text,
        "direct_push_demo_declares_direct_push_mode": '"mode": "direct-push"' in direct_push_demo_text,
        "desktop_uses_python_compat_virtual_camera": "akvc.sdk.virtual_camera import VirtualCamera" in desktop_text,
        "desktop_prefers_installation_snapshot": "inspect_installation" in desktop_text,
        "desktop_uses_stream_capabilities": "stream_capabilities" in desktop_text,
        "desktop_avoids_macos_specific_camera_import": "MacVirtualCamera" not in desktop_text,
        "desktop_avoids_pyvirtualcam_reference": "pyvirtualcam" not in desktop_text,
    }


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeQTimer:
    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.timeout = _FakeSignal()
        self.started = []
        self.stop_calls = 0

    def start(self, interval_ms: int) -> None:
        self.started.append(interval_ms)

    def stop(self) -> None:
        self.stop_calls += 1


class _FakeLabel:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.style = ""

    def setText(self, text: str) -> None:
        self.text = text

    def setStyleSheet(self, style: str) -> None:
        self.style = style


class _FakeLayout:
    def __init__(self, widget) -> None:
        self.widget = widget
        self.children = []

    def addWidget(self, widget) -> None:
        self.children.append(widget)


class _FakeWidget:
    def __init__(self) -> None:
        self.closed = False

    def setWindowTitle(self, title: str) -> None:
        self.title = title

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def show(self) -> None:
        self.shown = True

    def close(self) -> None:
        self.closed = True


class _FakeQColor:
    @staticmethod
    def fromHsv(h, s, v):
        return {"h": h, "s": s, "v": v}


class _FakeQImage:
    class Format:
        Format_RGB32 = 1

    def __init__(self, width: int, height: int, fmt: int) -> None:
        self.width = width
        self.height = height
        self.fmt = fmt
        self.fill_calls = []

    def fill(self, color) -> None:
        self.fill_calls.append(color)


class _FakeApp:
    def __init__(self) -> None:
        self.screen = object()

    def processEvents(self) -> None:
        return None

    def primaryScreen(self):
        return self.screen


class _FakeQApplication:
    _instance = None

    def __init__(self, argv=None) -> None:
        del argv
        self._app = _FakeApp()
        _FakeQApplication._instance = self

    @classmethod
    def instance(cls):
        return cls._instance._app if cls._instance is not None else None


class _FakeQtModule:
    QApplication = _FakeQApplication
    QWidget = _FakeWidget
    QLabel = _FakeLabel
    QVBoxLayout = _FakeLayout
    QTimer = _FakeQTimer
    QColor = _FakeQColor
    QImage = _FakeQImage


class _FakeCamera:
    def __init__(self) -> None:
        self.start_calls: list[str] = []
        self.close_calls = 0
        self.consumer_count = 2
        self.backend_name = "direct_sender"
        self.using_direct_sender = True
        self.streamer_factory_calls = 0
        self.latest_provider_factory_calls: list[bool] = []
        self.send_widget_calls = []
        self.send_screen_calls = []
        self.push_frame_calls = []

    def start(self, name: str = "AK Virtual Camera") -> None:
        self.start_calls.append(name)

    def close(self) -> None:
        self.close_calls += 1

    def create_pyside6_streamer(self):
        self.streamer_factory_calls += 1
        return _FakeStreamer(self)

    def create_latest_frame_provider(self, *, repeat_last: bool = True):
        self.latest_provider_factory_calls.append(repeat_last)
        return _FakeLatestFrameProvider(repeat_last=repeat_last)

    def send_widget(self, widget) -> None:
        self.send_widget_calls.append(widget)

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
        self.send_screen_calls.append((screen, window, x, y, width, height))

    def push_frame(self, frame) -> None:
        self.push_frame_calls.append(frame)


class _FakeStreamer:
    instances: list["_FakeStreamer"] = []

    def __init__(self, camera) -> None:
        self.camera = camera
        self.calls = []
        self.stop_calls = 0
        _FakeStreamer.instances.append(self)

    def start_provider_stream(self, provider, *, interval_ms: int = 33) -> None:
        self.calls.append(("provider", interval_ms, provider))

    def start_latest_frame_stream(self, provider, *, interval_ms: int = 33) -> None:
        self.calls.append(("latest-provider", interval_ms, provider))

    def stop(self) -> None:
        self.stop_calls += 1


class _FakeLatestFrameProvider:
    def __init__(self, *, repeat_last: bool = True) -> None:
        self.repeat_last = repeat_last
        self.submit_calls = []
        self.close_calls = 0

    def submit(self, frame) -> None:
        self.submit_calls.append(frame)

    def close(self) -> None:
        self.close_calls += 1


def evaluate_demo_case() -> dict[str, Any]:
    demo_module = _load_module(DEMO_TOOL, "macos_entrypoints_contract_demo")
    _FakeStreamer.instances.clear()
    provider_camera = _FakeCamera()
    provider_payload = demo_module.run_demo(
        mode="provider",
        width=1280,
        height=720,
        fps=30.0,
        duration=0.0,
        name="AKVC Contract Demo",
        camera_factory=lambda **kwargs: provider_camera,
        qt_loader=lambda: _FakeQtModule,
        sleeper=lambda seconds: None,
    )
    streamer = _FakeStreamer.instances[0]
    widget_camera = _FakeCamera()
    widget_payload = demo_module.run_demo(
        mode="widget",
        width=800,
        height=450,
        fps=30.0,
        duration=0.0,
        camera_factory=lambda **kwargs: widget_camera,
        qt_loader=lambda: _FakeQtModule,
        sleeper=lambda seconds: None,
    )
    screen_camera = _FakeCamera()
    screen_payload = demo_module.run_demo(
        mode="screen",
        width=640,
        height=360,
        fps=20.0,
        duration=0.0,
        camera_factory=lambda **kwargs: screen_camera,
        qt_loader=lambda: _FakeQtModule,
        sleeper=lambda seconds: None,
    )
    latest_camera = _FakeCamera()
    latest_payload = demo_module.run_demo(
        mode="latest-provider",
        width=1280,
        height=720,
        fps=30.0,
        duration=0.0,
        camera_factory=lambda **kwargs: latest_camera,
        qt_loader=lambda: _FakeQtModule,
        sleeper=lambda seconds: None,
    )
    latest_streamer = _FakeStreamer.instances[-1]
    latest_provider = latest_streamer.calls[0][2]
    return {
        "camera_started_with_name": provider_camera.start_calls == ["AKVC Contract Demo"],
        "camera_closed_after_run": provider_camera.close_calls == 1,
        "demo_uses_sdk_streamer_factory": provider_camera.streamer_factory_calls == 1
        and latest_camera.streamer_factory_calls == 1
        and widget_camera.streamer_factory_calls == 0
        and screen_camera.streamer_factory_calls == 0,
        "streamer_started_provider_mode": bool(streamer.calls) and streamer.calls[0][0] == "provider",
        "streamer_stopped_after_run": streamer.stop_calls == 1,
        "demo_uses_sdk_widget_push": widget_payload.get("frame_source_kind") == "widget_grab"
        and len(widget_camera.send_widget_calls) == 1,
        "demo_uses_sdk_screen_push": screen_payload.get("frame_source_kind") == "screen_grab"
        and len(screen_camera.send_screen_calls) == 1
        and screen_camera.send_screen_calls[0][1:] == (0, 0, 0, 640, 360),
        "demo_uses_sdk_latest_provider_factory": latest_payload.get("frame_source_kind") == "latest_frame_provider"
        and latest_camera.latest_provider_factory_calls == [True]
        and getattr(latest_provider, "repeat_last", False) is True,
        "report_keeps_consumer_count": provider_payload.get("consumer_count") == provider_camera.consumer_count,
        "report_keeps_frame_source_kind": provider_payload.get("frame_source_kind") == "callable_provider",
    }


def evaluate_direct_push_demo_case() -> dict[str, Any]:
    demo_module = _load_module(DIRECT_PUSH_DEMO_TOOL, "macos_entrypoints_contract_direct_push_demo")
    camera = _FakeCamera()
    frames = [{"index": 0}, {"index": 1}, {"index": 2}]
    state = {"index": 0}

    def _frame_factory():
        index = state["index"]
        state["index"] += 1
        return frames[index]

    payload = demo_module.run_demo(
        width=1280,
        height=720,
        fps=30.0,
        duration=0.0,
        frames=3,
        name="AKVC Direct Contract Demo",
        camera_factory=lambda **kwargs: camera,
        sleeper=lambda seconds: None,
        frame_factory=_frame_factory,
    )
    return {
        "camera_started_with_name": camera.start_calls == ["AKVC Direct Contract Demo"],
        "camera_closed_after_run": camera.close_calls == 1,
        "push_frame_called_for_each_requested_frame": camera.push_frame_calls == frames,
        "report_declares_direct_push_mode": payload.get("mode") == "direct-push",
        "report_declares_push_frame_entrypoint": payload.get("python_entrypoint_kind") == "push_frame",
        "report_marks_sdk_direct_push_used": payload.get("sdk_direct_push_used") is True,
        "report_keeps_backend_name": payload.get("backend_name") == camera.backend_name,
        "report_keeps_using_direct_sender": payload.get("using_direct_sender") is camera.using_direct_sender,
        "report_keeps_consumer_count": payload.get("consumer_count") == camera.consumer_count,
        "report_keeps_requested_frame_count": payload.get("requested_frames") == 3
        and payload.get("frames_sent") == 3,
    }


def evaluate_desktop_snapshot_case() -> dict[str, Any]:
    desktop_text = _read_text(DESKTOP_FACADE)
    return {
        "desktop_loads_compat_virtual_camera": "from akvc.sdk.virtual_camera import VirtualCamera" in desktop_text,
        "desktop_exposes_snapshot_path": "inspect_installation" in desktop_text,
        "desktop_exposes_capability_path": "stream_capabilities" in desktop_text,
        "desktop_marks_old_settings_opener_deleted": "deleted akvc.sdk" in desktop_text,
    }


def evaluate_contract() -> dict[str, Any]:
    surface = parse_entrypoint_surface(
        {
            "demo": _read_text(DEMO_TOOL),
            "direct_push_demo": _read_text(DIRECT_PUSH_DEMO_TOOL),
            "desktop": _read_text(DESKTOP_FACADE),
        }
    )
    demo_case = evaluate_demo_case()
    direct_push_demo_case = evaluate_direct_push_demo_case()
    desktop_case = evaluate_desktop_snapshot_case()
    consistency = {
        "surface_complete": all(bool(value) for value in surface.values()),
        "demo_case_complete": all(bool(value) for value in demo_case.values()),
        "direct_push_demo_case_complete": all(bool(value) for value in direct_push_demo_case.values()),
        "desktop_case_complete": all(bool(value) for value in desktop_case.values()),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "surface": surface,
        "demo_case": demo_case,
        "direct_push_demo_case": direct_push_demo_case,
        "desktop_case": desktop_case,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS entrypoint contract checker"
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_contract()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    if not bool(payload["consistency"]["all_checks_passed"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
