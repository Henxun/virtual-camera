# SPDX-License-Identifier: Apache-2.0
"""PySide6/direct virtual camera demo helper.

Provides small runnable examples for current Python/PySide6 compatibility
entrypoints over the native virtual-camera stack: pure-Python numpy direct
push, pull-based provider, latest-frame provider, QImage/QPixmap direct push,
QWidget capture, primary-screen capture, and local video-file relay.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
import json


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))


def _resolve_container_app_args(
    *,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
) -> tuple[str | None, str | None]:
    if app_bundle and host_bundle and app_bundle != host_bundle:
        raise ValueError("--app-bundle and --host-bundle cannot point at different macOS app bundles")
    if app_executable and host_executable and app_executable != host_executable:
        raise ValueError(
            "--app-executable and --host-executable cannot point at different macOS app executables"
        )
    return app_bundle or host_bundle, app_executable or host_executable


def _default_camera_factory(
    *,
    width: int,
    height: int,
    fps: float,
    direct_only: bool | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    direct_sender_library: str | None = None,
):
    try:
        from akvc.sdk.virtual_camera import VirtualCamera
    except ModuleNotFoundError as exc:
        if exc.name == "numpy":
            raise RuntimeError(
                "PySide6 demo requires numpy. Install runtime deps first, "
                "for example: python -m pip install numpy opencv-python-headless PySide6"
            ) from exc
        raise
    effective_direct_only = (
        sys.platform == "darwin" if direct_only is None else bool(direct_only)
    )
    resolved_app_bundle, resolved_app_executable = _resolve_container_app_args(
        app_bundle=app_bundle,
        app_executable=app_executable,
        host_bundle=host_bundle,
        host_executable=host_executable,
    )
    return VirtualCamera(
        width=width,
        height=height,
        fps=fps,
        direct_only=effective_direct_only,
        app_bundle=resolved_app_bundle,
        app_executable=resolved_app_executable,
        direct_sender_library=direct_sender_library,
    )


def _import_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Direct numpy demo requires numpy. Install runtime deps first, "
            "for example: python -m pip install numpy"
        ) from exc
    return np


def _default_streamer_cls():
    try:
        from akvc.integrations.pyside6 import PySide6VirtualCameraStreamer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PySide6 demo requires akvc-core PySide6 integration dependencies to be importable"
        ) from exc
    return PySide6VirtualCameraStreamer


def _default_video_provider_cls():
    try:
        from akvc.integrations.pyside6 import OpenCVVideoFileProvider
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PySide6 video-file demo requires akvc-core video-file integration dependencies to be importable"
        ) from exc
    return OpenCVVideoFileProvider


def _default_latest_frame_provider_cls():
    try:
        from akvc.integrations.pyside6 import LatestFrameProvider
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PySide6 latest-provider demo requires akvc-core latest-frame integration dependencies to be importable"
        ) from exc
    return LatestFrameProvider


def _create_streamer(camera: Any, streamer_cls=None):
    create_streamer = getattr(camera, "create_pyside6_streamer", None)
    if callable(create_streamer):
        return create_streamer(), True
    if streamer_cls is not None:
        return streamer_cls(camera), False
    return _default_streamer_cls()(camera), False


def _create_latest_frame_provider(camera: Any, latest_frame_provider_cls=None):
    create_provider = getattr(camera, "create_latest_frame_provider", None)
    if callable(create_provider):
        return create_provider(repeat_last=True), True
    if latest_frame_provider_cls is not None:
        return latest_frame_provider_cls(repeat_last=True), False
    return _default_latest_frame_provider_cls()(repeat_last=True), False


def _load_qt():
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QColor, QImage, QPixmap
        from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PySide6 demo requires PySide6. Install it first, for example: "
            "python -m pip install PySide6"
        ) from exc
    return SimpleNamespace(
        QApplication=QApplication,
        QWidget=QWidget,
        QLabel=QLabel,
        QVBoxLayout=QVBoxLayout,
        QTimer=QTimer,
        QColor=QColor,
        QImage=QImage,
        QPixmap=QPixmap,
    )


def _ensure_app(qt) -> Any:
    app = qt.QApplication.instance()
    if app is None:
        qt.QApplication([])
        app = qt.QApplication.instance()
    if app is None:
        raise RuntimeError("failed to create QApplication instance")
    return app


def _interval_ms_from_fps(fps: float) -> int:
    if fps <= 0:
        raise ValueError("fps must be > 0")
    return max(1, int(round(1000.0 / float(fps))))


def _mode_requires_qt(mode: str) -> bool:
    return mode in {
        "provider",
        "latest-provider",
        "image",
        "pixmap",
        "widget",
        "screen",
        "video-file",
    }


def _make_numpy_frame_provider(*, width: int, height: int):
    np = _import_numpy()
    frame_state = {"index": 0}

    def _provider():
        index = frame_state["index"]
        frame_state["index"] += 1
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = ((index * 5) % 256, 100, 50)
        return frame

    return _provider


def _make_provider(qt, *, width: int, height: int) -> Callable[[], Any]:
    frame_state = {"index": 0}
    qimage_format = getattr(getattr(qt.QImage, "Format", qt.QImage), "Format_RGB32", None)
    if qimage_format is None:
        qimage_format = getattr(qt.QImage, "Format_RGB32")

    def _provider():
        index = frame_state["index"]
        frame_state["index"] += 1
        image = qt.QImage(width, height, qimage_format)
        color = qt.QColor.fromHsv((index * 7) % 360, 255, 220)
        image.fill(color)
        return image

    return _provider


def _make_pixmap_from_image(qt, image: Any) -> Any:
    qpixmap_type = getattr(qt, "QPixmap", None)
    if qpixmap_type is None:
        raise RuntimeError("Qt loader does not expose QPixmap")
    from_image = getattr(qpixmap_type, "fromImage", None)
    if callable(from_image):
        return from_image(image)
    try:
        return qpixmap_type(image)
    except TypeError as exc:
        raise RuntimeError("QPixmap construction from QImage is unavailable") from exc


def _create_demo_widget(qt, *, width: int, height: int, interval_ms: int):
    widget = qt.QWidget()
    widget.setWindowTitle("AKVC PySide6 Demo")
    widget.resize(width, height)
    label = qt.QLabel("AK Virtual Camera PySide6 Demo")
    layout = qt.QVBoxLayout(widget)
    layout.addWidget(label)
    counter = {"value": 0}

    def _refresh():
        counter["value"] += 1
        label.setText(f"AKVC PySide6 Demo Frame {counter['value']}")
        if hasattr(label, "setStyleSheet"):
            hue = (counter["value"] * 9) % 360
            label.setStyleSheet(
                "font-size: 18px; padding: 24px; color: white; "
                f"background-color: hsl({hue}, 70%, 35%);"
            )

    timer = qt.QTimer(widget)
    if hasattr(timer, "timeout") and hasattr(timer.timeout, "connect"):
        timer.timeout.connect(_refresh)
    timer.start(interval_ms)
    _refresh()
    widget.show()
    return widget, timer


def _create_latest_provider_source(qt, latest_frame_provider_factory, *, width: int, height: int, interval_ms: int):
    provider, provider_used_sdk_factory = latest_frame_provider_factory()
    frame_factory = _make_provider(qt, width=width, height=height)
    producer_timer = qt.QTimer()

    def _submit_next() -> None:
        provider.submit(frame_factory())

    if hasattr(producer_timer, "timeout") and hasattr(producer_timer.timeout, "connect"):
        producer_timer.timeout.connect(_submit_next)
    _submit_next()
    producer_timer.start(max(1, int(interval_ms // 2) or 1))
    return provider, producer_timer, provider_used_sdk_factory


def _start_direct_camera_push_loop(
    qt,
    *,
    interval_ms: int,
    push_once: Callable[[], None],
):
    timer = qt.QTimer()
    if hasattr(timer, "timeout") and hasattr(timer.timeout, "connect"):
        timer.timeout.connect(push_once)
    push_once()
    timer.start(interval_ms)
    return timer


def _pump_for_duration(*, app: Any | None, duration: float, sleeper: Callable[[float], None]) -> None:
    remaining = max(0.0, float(duration))
    while remaining > 0:
        slice_seconds = min(0.05, remaining)
        if app is not None and hasattr(app, "processEvents"):
            app.processEvents()
        sleeper(slice_seconds)
        remaining -= slice_seconds
    if app is not None and hasattr(app, "processEvents"):
        app.processEvents()


def _run_direct_push_iterations(
    *,
    duration: float,
    interval_ms: int,
    push_once: Callable[[], None],
    sleeper: Callable[[float], None],
) -> None:
    iterations = max(1, int(math.ceil(max(0.0, float(duration)) * 1000.0 / interval_ms)))
    for index in range(iterations):
        push_once()
        if index + 1 < iterations:
            sleeper(interval_ms / 1000.0)


def build_demo_report(
    *,
    mode: str,
    frame_source_kind: str,
    python_entrypoint_kind: str,
    sdk_streamer_factory_used: bool,
    sdk_latest_provider_factory_used: bool,
    sdk_direct_push_used: bool,
    requested_direct_only: bool | None,
    width: int,
    height: int,
    fps: float,
    duration: float,
    camera_name: str,
    camera: Any,
    video_path: str | None = None,
) -> dict[str, object]:
    runtime_snapshot_getter = getattr(camera, "runtime_snapshot", None)
    runtime_snapshot = runtime_snapshot_getter() if callable(runtime_snapshot_getter) else {}
    if not isinstance(runtime_snapshot, dict):
        runtime_snapshot = {}
    runtime_topology = (
        dict(runtime_snapshot.get("runtime_topology", {}))
        if isinstance(runtime_snapshot.get("runtime_topology"), dict)
        else {}
    )
    if not runtime_topology:
        runtime_topology_getter = getattr(camera, "runtime_topology", None)
        runtime_topology = runtime_topology_getter() if callable(runtime_topology_getter) else {}
    if not isinstance(runtime_topology, dict):
        runtime_topology = {}
    return {
        "mode": mode,
        "frame_source_kind": frame_source_kind,
        "python_entrypoint_kind": python_entrypoint_kind,
        "sdk_streamer_factory_used": bool(sdk_streamer_factory_used),
        "sdk_latest_provider_factory_used": bool(sdk_latest_provider_factory_used),
        "sdk_direct_push_used": bool(sdk_direct_push_used),
        "requested_direct_only": requested_direct_only,
        "allow_shared_memory_fallback": (
            None if requested_direct_only is None else not bool(requested_direct_only)
        ),
        "backend_name": runtime_snapshot.get("backend_name", getattr(camera, "backend_name", None)),
        "using_direct_sender": bool(
            runtime_snapshot.get("using_direct_sender", getattr(camera, "using_direct_sender", False))
        ),
        "direct_sender_attempted": bool(
            runtime_snapshot.get("direct_sender_attempted", getattr(camera, "direct_sender_attempted", False))
        ),
        "direct_sender_state": runtime_snapshot.get("direct_sender_state", getattr(camera, "direct_sender_state", None)),
        "direct_sender_target_name": runtime_snapshot.get(
            "direct_sender_target_name",
            getattr(camera, "direct_sender_target_name", None),
        ),
        "direct_sender_library_path": runtime_snapshot.get(
            "direct_sender_library_path",
            getattr(camera, "direct_sender_library_path", None),
        ),
        "direct_sender_last_error": runtime_snapshot.get(
            "direct_sender_last_error",
            getattr(camera, "direct_sender_last_error", None),
        ),
        "runtime_topology_kind": runtime_topology.get("runtime_topology_kind"),
        "runtime_frame_path": runtime_topology.get("runtime_frame_path"),
        "runtime_host_role": runtime_topology.get("runtime_host_role"),
        "runtime_host_in_frame_hot_path": runtime_topology.get("runtime_host_in_frame_hot_path"),
        "runtime_dedicated_host_daemon_required": runtime_topology.get(
            "runtime_dedicated_host_daemon_required"
        ),
        "runtime_container_app_configured": runtime_topology.get(
            "runtime_container_app_configured"
        ),
        "runtime_data_plane": runtime_topology.get("runtime_data_plane"),
        "runtime_control_plane": runtime_topology.get("runtime_control_plane"),
        "width": int(width),
        "height": int(height),
        "fps": float(fps),
        "duration": float(duration),
        "camera_name": camera_name,
        "consumer_count": int(runtime_snapshot.get("consumer_count", getattr(camera, "consumer_count", 0))),
        "video_path": str(video_path) if video_path else None,
        "runtime_snapshot": runtime_snapshot or None,
    }


def run_demo(
    *,
    mode: str = "provider",
    width: int = 1280,
    height: int = 720,
    fps: float = 30.0,
    duration: float = 5.0,
    name: str = "AK Virtual Camera",
    camera_factory=None,
    streamer_cls=None,
    qt_loader=None,
    sleeper: Callable[[float], None] = time.sleep,
    video_provider_cls=None,
    latest_frame_provider_cls=None,
    video_path: str | None = None,
    allow_shared_memory_fallback: bool = False,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    direct_sender_library: str | None = None,
) -> dict[str, object]:
    if duration < 0:
        raise ValueError("duration must be >= 0")
    interval_ms = _interval_ms_from_fps(fps)
    qt = None
    app = None
    if _mode_requires_qt(mode):
        qt = (qt_loader or _load_qt)()
        app = _ensure_app(qt)
    requested_direct_only = (
        sys.platform == "darwin" and not bool(allow_shared_memory_fallback)
    )
    camera_builder = camera_factory or _default_camera_factory
    resolved_app_bundle, resolved_app_executable = _resolve_container_app_args(
        app_bundle=app_bundle,
        app_executable=app_executable,
        host_bundle=host_bundle,
        host_executable=host_executable,
    )
    try:
        camera = camera_builder(
            width=width,
            height=height,
            fps=fps,
            direct_only=requested_direct_only,
            app_bundle=resolved_app_bundle,
            app_executable=resolved_app_executable,
            direct_sender_library=direct_sender_library,
        )
    except TypeError:
        camera = camera_builder(width=width, height=height, fps=fps)
    streamer = None
    widget = None
    widget_timer = None
    latest_provider = None
    latest_provider_timer = None
    direct_push_timer = None
    frame_source_kind = "callable_provider"
    python_entrypoint_kind = "create_pyside6_streamer.start_provider_stream"
    sdk_streamer_factory_used = False
    sdk_latest_provider_factory_used = False
    sdk_direct_push_used = False

    camera.start(name=name)
    try:
        if mode == "numpy-direct":
            frame_source_kind = "numpy_direct"
            python_entrypoint_kind = "push_frame"
            sdk_direct_push_used = True
            frame_provider = _make_numpy_frame_provider(width=width, height=height)
            _run_direct_push_iterations(
                duration=duration,
                interval_ms=interval_ms,
                push_once=lambda: camera.push_frame(frame_provider()),
                sleeper=sleeper,
            )
        elif mode == "provider":
            frame_source_kind = "callable_provider"
            python_entrypoint_kind = "create_pyside6_streamer.start_provider_stream"
            streamer, sdk_streamer_factory_used = _create_streamer(camera, streamer_cls=streamer_cls)
            streamer.start_provider_stream(
                _make_provider(qt, width=width, height=height),
                interval_ms=interval_ms,
            )
        elif mode == "latest-provider":
            frame_source_kind = "latest_frame_provider"
            python_entrypoint_kind = "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream"
            streamer, sdk_streamer_factory_used = _create_streamer(camera, streamer_cls=streamer_cls)
            latest_provider, latest_provider_timer, sdk_latest_provider_factory_used = _create_latest_provider_source(
                qt,
                lambda: _create_latest_frame_provider(camera, latest_frame_provider_cls=latest_frame_provider_cls),
                width=width,
                height=height,
                interval_ms=interval_ms,
            )
            streamer.start_latest_frame_stream(latest_provider, interval_ms=interval_ms)
        elif mode == "image":
            frame_source_kind = "qimage_direct"
            python_entrypoint_kind = "send_image"
            sdk_direct_push_used = True
            image_provider = _make_provider(qt, width=width, height=height)
            direct_push_timer = _start_direct_camera_push_loop(
                qt,
                interval_ms=interval_ms,
                push_once=lambda: camera.send_image(image_provider()),
            )
        elif mode == "pixmap":
            frame_source_kind = "qpixmap_direct"
            python_entrypoint_kind = "send_pixmap"
            sdk_direct_push_used = True
            image_provider = _make_provider(qt, width=width, height=height)
            direct_push_timer = _start_direct_camera_push_loop(
                qt,
                interval_ms=interval_ms,
                push_once=lambda: camera.send_pixmap(
                    _make_pixmap_from_image(qt, image_provider())
                ),
            )
        elif mode == "widget":
            frame_source_kind = "widget_grab"
            python_entrypoint_kind = "send_widget"
            sdk_direct_push_used = True
            widget, widget_timer = _create_demo_widget(
                qt,
                width=width,
                height=height,
                interval_ms=interval_ms,
            )
            direct_push_timer = _start_direct_camera_push_loop(
                qt,
                interval_ms=interval_ms,
                push_once=lambda: camera.send_widget(widget),
            )
        elif mode == "screen":
            frame_source_kind = "screen_grab"
            python_entrypoint_kind = "send_screen"
            sdk_direct_push_used = True
            if not hasattr(app, "primaryScreen"):
                raise RuntimeError("QApplication does not expose primaryScreen()")
            screen = app.primaryScreen()
            if screen is None:
                raise RuntimeError("no primary screen available")
            direct_push_timer = _start_direct_camera_push_loop(
                qt,
                interval_ms=interval_ms,
                push_once=lambda: camera.send_screen(
                    screen,
                    width=width,
                    height=height,
                ),
            )
        elif mode == "video-file":
            frame_source_kind = "opencv_video_file"
            if not video_path:
                raise ValueError("video-file mode requires --video-path")
            python_entrypoint_kind = "create_pyside6_streamer.start_video_file_stream"
            streamer, sdk_streamer_factory_used = _create_streamer(camera, streamer_cls=streamer_cls)
            video_provider_type = video_provider_cls or _default_video_provider_cls()
            streamer.start_video_file_stream(
                video_path,
                interval_ms=interval_ms,
                loop=True,
                provider_factory=video_provider_type,
            )
        else:
            raise ValueError(f"unsupported mode: {mode}")

        if mode != "numpy-direct":
            _pump_for_duration(app=app, duration=duration, sleeper=sleeper)
    finally:
        if streamer is not None:
            streamer.stop()
        if widget_timer is not None and hasattr(widget_timer, "stop"):
            widget_timer.stop()
        if direct_push_timer is not None and hasattr(direct_push_timer, "stop"):
            direct_push_timer.stop()
        if latest_provider_timer is not None and hasattr(latest_provider_timer, "stop"):
            latest_provider_timer.stop()
        if widget is not None and hasattr(widget, "close"):
            widget.close()
        if latest_provider is not None and hasattr(latest_provider, "close"):
            latest_provider.close()
        camera.close()
    return build_demo_report(
        mode=mode,
        frame_source_kind=frame_source_kind,
        python_entrypoint_kind=python_entrypoint_kind,
        sdk_streamer_factory_used=sdk_streamer_factory_used,
        sdk_latest_provider_factory_used=sdk_latest_provider_factory_used,
        sdk_direct_push_used=sdk_direct_push_used,
        requested_direct_only=requested_direct_only,
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        camera_name=name,
        camera=camera,
        video_path=video_path,
    )


def main(
    argv: list[str] | None = None,
    *,
    camera_factory=None,
    streamer_cls=None,
    qt_loader=None,
    sleeper: Callable[[float], None] = time.sleep,
    video_provider_cls=None,
    latest_frame_provider_cls=None,
) -> int:
    parser = argparse.ArgumentParser(description="AKVC PySide6 virtual camera demo")
    parser.add_argument(
        "--mode",
        choices=["numpy-direct", "provider", "latest-provider", "image", "pixmap", "widget", "screen", "video-file"],
        default="provider",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--name", default="AK Virtual Camera")
    parser.add_argument("--video-path")
    parser.add_argument("--allow-shared-memory-fallback", action="store_true")
    parser.add_argument("--app-bundle")
    parser.add_argument("--app-executable")
    parser.add_argument("--host-bundle")
    parser.add_argument("--host-executable")
    parser.add_argument("--direct-sender-library")
    parser.add_argument("--report-json")
    args = parser.parse_args(argv)
    try:
        app_bundle, app_executable = _resolve_container_app_args(
            app_bundle=args.app_bundle,
            app_executable=args.app_executable,
            host_bundle=args.host_bundle,
            host_executable=args.host_executable,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        payload = run_demo(
            mode=args.mode,
            width=args.width,
            height=args.height,
            fps=args.fps,
            duration=args.duration,
            name=args.name,
            camera_factory=camera_factory,
            streamer_cls=streamer_cls,
            qt_loader=qt_loader,
            sleeper=sleeper,
            video_provider_cls=video_provider_cls,
            latest_frame_provider_cls=latest_frame_provider_cls,
            video_path=args.video_path,
            allow_shared_memory_fallback=bool(args.allow_shared_memory_fallback),
            app_bundle=app_bundle,
            app_executable=app_executable,
            direct_sender_library=args.direct_sender_library,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.report_json:
        output_path = Path(args.report_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
