# SPDX-License-Identifier: Apache-2.0
"""Minimal direct-push virtual camera demo for macOS.

This tool exercises the public Python SDK path without requiring a helper
process in the frame hot path. It can validate multiple Python entrypoints:

    VirtualCamera.push_frame(...)
    VirtualCamera.send_pixmap(...)
    VirtualCamera.send_widget(...)
    VirtualCamera.send_screen(...)

PySide6 is not required; the demo can synthesize lightweight QImage/QPixmap-
like objects for contract and smoke validation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))


class DirectPushDemoRuntimeError(RuntimeError):
    def __init__(self, message: str, *, camera_state: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.camera_state = dict(camera_state or {})


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
    direct_only: bool = False,
    helper_exe: str | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    direct_sender_library: str | None = None,
):
    from akvc.sdk.virtual_camera import VirtualCamera

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
        direct_only=direct_only,
        helper_exe=helper_exe,
        app_bundle=resolved_app_bundle,
        app_executable=resolved_app_executable,
        direct_sender_library=direct_sender_library,
    )


def _import_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Direct push demo requires numpy. Install it first, for example: "
            "python -m pip install numpy"
        ) from exc
    return np


def _make_numpy_frame_factory(*, width: int, height: int):
    np = _import_numpy()
    state = {"index": 0}

    def _factory():
        index = state["index"]
        state["index"] += 1
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = ((index * 5) % 256, 96, 180)
        return frame

    return _factory, "numpy.ndarray"


def _make_bytes_frame_factory(*, width: int, height: int):
    from akvc.core.frame import Frame

    state = {"index": 0}
    frame_bytes = width * height * 3

    def _factory():
        index = state["index"]
        state["index"] += 1
        payload = bytearray(frame_bytes)
        blue = (index * 5) % 256
        for offset in range(0, frame_bytes, 3):
            payload[offset] = blue
            payload[offset + 1] = 96
            payload[offset + 2] = 180
        return Frame.from_bgr_bytes(width=width, height=height, data=payload)

    return _factory, "Frame"


def _make_bgra_bytes_frame_factory(*, width: int, height: int):
    from akvc.core.frame import Frame

    state = {"index": 0}
    frame_bytes = width * height * 4

    def _factory():
        index = state["index"]
        state["index"] += 1
        payload = bytearray(frame_bytes)
        blue = (index * 5) % 256
        for offset in range(0, frame_bytes, 4):
            payload[offset] = blue
            payload[offset + 1] = 96
            payload[offset + 2] = 180
            payload[offset + 3] = 255
        return Frame.from_bgra_bytes(width=width, height=height, data=payload)

    return _factory, "Frame"


def _make_qimage_bgra_frame_factory(*, width: int, height: int):
    class _FakeBits(bytearray):
        def setsize(self, size: int) -> None:
            self._size = size

        def asstring(self, size: int) -> bytes:
            return bytes(self[:size])

    class _FakeQImage:
        class Format:
            Format_BGRA8888 = 1

        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def width(self) -> int:
            return width

        def height(self) -> int:
            return height

        def bytesPerLine(self) -> int:
            return width * 4

        def format(self) -> int:
            return self.Format.Format_BGRA8888

        def constBits(self) -> _FakeBits:
            return _FakeBits(self._payload)

    state = {"index": 0}
    frame_bytes = width * height * 4

    def _factory():
        index = state["index"]
        state["index"] += 1
        payload = bytearray(frame_bytes)
        blue = (index * 5) % 256
        for offset in range(0, frame_bytes, 4):
            payload[offset] = blue
            payload[offset + 1] = 96
            payload[offset + 2] = 180
            payload[offset + 3] = 255
        return _FakeQImage(bytes(payload))

    return _factory, "QImage"


def _wrap_entrypoint_payload(entrypoint: str, payload_factory, payload_kind: str):
    if entrypoint == "push-frame":
        return payload_factory, payload_kind

    if entrypoint == "send-pixmap":
        class _FakeQPixmap:
            def __init__(self, image: Any) -> None:
                self._image = image

            def toImage(self) -> Any:
                return self._image

        def _factory():
            return _FakeQPixmap(payload_factory())

        return _factory, "QPixmap"

    if entrypoint == "send-widget":
        class _FakeQPixmap:
            def __init__(self, image: Any) -> None:
                self._image = image

            def toImage(self) -> Any:
                return self._image

        class _FakeWidget:
            def __init__(self, grabbed: Any) -> None:
                self._grabbed = grabbed

            def grab(self) -> Any:
                return self._grabbed

        def _factory():
            return _FakeWidget(_FakeQPixmap(payload_factory()))

        return _factory, "QWidget"

    if entrypoint == "send-screen":
        class _FakeQPixmap:
            def __init__(self, image: Any) -> None:
                self._image = image

            def toImage(self) -> Any:
                return self._image

        class _FakeScreen:
            def __init__(self, grabbed: Any) -> None:
                self._grabbed = grabbed

            def grabWindow(
                self,
                window: int,
                x: int,
                y: int,
                width: int,
                height: int,
            ) -> Any:
                del window, x, y, width, height
                return self._grabbed

        def _factory():
            return _FakeScreen(_FakeQPixmap(payload_factory()))

        return _factory, "QScreen"

    raise ValueError(f"unsupported entrypoint: {entrypoint}")


def _entrypoint_python_kind(entrypoint: str) -> str:
    if entrypoint == "push-frame":
        return "push_frame"
    if entrypoint == "send-pixmap":
        return "send_pixmap"
    if entrypoint == "send-widget":
        return "send_widget"
    if entrypoint == "send-screen":
        return "send_screen"
    raise ValueError(f"unsupported entrypoint: {entrypoint}")


def _submit_frame(camera: Any, entrypoint: str, payload: Any) -> None:
    if entrypoint == "push-frame":
        camera.push_frame(payload)
        return
    if entrypoint == "send-pixmap":
        camera.send_pixmap(payload)
        return
    if entrypoint == "send-widget":
        camera.send_widget(payload)
        return
    if entrypoint == "send-screen":
        camera.send_screen(payload)
        return
    raise ValueError(f"unsupported entrypoint: {entrypoint}")


def _make_frame_factory(*, width: int, height: int, frame_kind: str = "auto"):
    if frame_kind == "numpy":
        return _make_numpy_frame_factory(width=width, height=height)
    if frame_kind == "bytes":
        return _make_bytes_frame_factory(width=width, height=height)
    if frame_kind == "bgra-bytes":
        return _make_bgra_bytes_frame_factory(width=width, height=height)
    if frame_kind == "qimage-bgra":
        return _make_qimage_bgra_frame_factory(width=width, height=height)
    if frame_kind != "auto":
        raise ValueError(f"unsupported frame_kind: {frame_kind}")
    try:
        return _make_numpy_frame_factory(width=width, height=height)
    except RuntimeError:
        return _make_bytes_frame_factory(width=width, height=height)


def _resolve_frame_factory(*, width: int, height: int, frame_kind: str):
    try:
        return _make_frame_factory(
            width=width,
            height=height,
            frame_kind=frame_kind,
        )
    except TypeError as exc:
        if "frame_kind" not in str(exc):
            raise
        return _make_frame_factory(width=width, height=height)


def _resolve_frame_count(*, fps: float, duration: float, frames: int | None) -> int:
    if frames is not None:
        if int(frames) <= 0:
            raise ValueError("frames must be > 0 when provided")
        return int(frames)
    if fps <= 0:
        raise ValueError("fps must be > 0")
    return max(1, int(math.ceil(max(0.0, float(duration)) * float(fps))))


def build_demo_report(
    *,
    width: int,
    height: int,
    fps: float,
    duration: float,
    requested_frames: int,
    frames_sent: int,
    camera_name: str,
    camera: Any,
    frame_source_kind: str,
    python_entrypoint_kind: str,
    requested_frame_kind: str,
    requested_entrypoint: str,
    direct_only: bool,
    probe_only: bool,
) -> dict[str, object]:
    runtime_snapshot = _safe_runtime_snapshot(camera)
    runtime_topology = (
        dict(runtime_snapshot.get("runtime_topology", {}))
        if isinstance(runtime_snapshot.get("runtime_topology"), dict)
        else _safe_runtime_topology(camera)
    )
    return {
        "mode": "direct-push",
        "direct_only": bool(direct_only),
        "allow_shared_memory_fallback": not bool(direct_only),
        "probe_only": bool(probe_only),
        "frame_source_kind": frame_source_kind,
        "python_entrypoint_kind": python_entrypoint_kind,
        "requested_frame_kind": requested_frame_kind,
        "requested_entrypoint": requested_entrypoint,
        "sdk_direct_push_used": True,
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
        "helper_hot_path_used": bool(
            runtime_snapshot.get("helper_hot_path_used", getattr(camera, "helper_hot_path_used", False))
        ),
        "shared_memory_fallback_used": bool(
            runtime_snapshot.get(
                "shared_memory_fallback_used",
                getattr(camera, "shared_memory_fallback_used", False),
            )
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
        "last_frame_fourcc": runtime_snapshot.get("last_frame_fourcc", getattr(camera, "last_frame_fourcc", None)),
        "last_frame_format_name": runtime_snapshot.get(
            "last_frame_format_name",
            getattr(camera, "last_frame_format_name", None),
        ),
        "width": int(width),
        "height": int(height),
        "fps": float(fps),
        "duration": float(duration),
        "requested_frames": int(requested_frames),
        "frames_sent": int(frames_sent),
        "camera_name": camera_name,
        "consumer_count": int(runtime_snapshot.get("consumer_count", getattr(camera, "consumer_count", 0))),
    }


def _evaluate_direct_runtime_payload(payload: dict[str, object]) -> tuple[bool, str | None]:
    issues: list[str] = []
    if payload.get("using_direct_sender") is not True:
        issues.append("using_direct_sender != true")
    if payload.get("helper_hot_path_used") is not False:
        issues.append("helper_hot_path_used != false")
    if payload.get("shared_memory_fallback_used") is not False:
        issues.append("shared_memory_fallback_used != false")
    if payload.get("runtime_host_in_frame_hot_path") is True:
        issues.append("runtime_host_in_frame_hot_path == true")
    if payload.get("runtime_dedicated_host_daemon_required") is True:
        issues.append("runtime_dedicated_host_daemon_required == true")
    if payload.get("allow_shared_memory_fallback") is True:
        issues.append("allow_shared_memory_fallback == true")
    if payload.get("direct_only") is False:
        issues.append("direct_only == false")
    if not issues:
        return True, None
    return False, "direct runtime requirement failed: " + ", ".join(issues)


def _snapshot_camera_state(camera: Any) -> dict[str, object]:
    runtime_snapshot = _safe_runtime_snapshot(camera)
    direct_sender_snapshot = None
    direct_sender_snapshot_getter = getattr(camera, "direct_sender_device_snapshot", None)
    if callable(direct_sender_snapshot_getter):
        try:
            direct_sender_snapshot = direct_sender_snapshot_getter()
        except Exception:
            direct_sender_snapshot = None
    runtime_topology = (
        dict(runtime_snapshot.get("runtime_topology", {}))
        if isinstance(runtime_snapshot.get("runtime_topology"), dict)
        else _safe_runtime_topology(camera)
    )
    return {
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
        "direct_sender_device_snapshot": direct_sender_snapshot,
        "last_frame_fourcc": runtime_snapshot.get("last_frame_fourcc", getattr(camera, "last_frame_fourcc", None)),
        "last_frame_format_name": runtime_snapshot.get(
            "last_frame_format_name",
            getattr(camera, "last_frame_format_name", None),
        ),
        "consumer_count": int(runtime_snapshot.get("consumer_count", getattr(camera, "consumer_count", 0))),
        "runtime_topology": runtime_topology,
        "runtime_snapshot": runtime_snapshot or None,
    }


def _safe_runtime_snapshot(camera: Any) -> dict[str, object]:
    runtime_snapshot_getter = getattr(camera, "runtime_snapshot", None)
    if not callable(runtime_snapshot_getter):
        return {}
    try:
        snapshot = runtime_snapshot_getter()
    except Exception:
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def _safe_runtime_topology(camera: Any) -> dict[str, object]:
    runtime_topology_getter = getattr(camera, "runtime_topology", None)
    if not callable(runtime_topology_getter):
        return {}
    if not (
        bool(getattr(camera, "using_direct_sender", False))
        or getattr(camera, "backend_name", None)
    ):
        return {}
    try:
        runtime_topology = runtime_topology_getter()
    except Exception:
        return {}
    return runtime_topology if isinstance(runtime_topology, dict) else {}


def run_demo(
    *,
    width: int = 1280,
    height: int = 720,
    fps: float = 30.0,
    duration: float = 3.0,
    frames: int | None = None,
    name: str = "AK Virtual Camera",
    direct_only: bool = True,
    helper_exe: str | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    direct_sender_library: str | None = None,
    frame_kind: str = "auto",
    entrypoint: str = "push-frame",
    probe_only: bool = False,
    request_camera_access: bool = False,
    camera_factory=None,
    sleeper: Callable[[float], None] = time.sleep,
    frame_factory=None,
) -> dict[str, object]:
    if duration < 0:
        raise ValueError("duration must be >= 0")
    requested_frames = _resolve_frame_count(fps=fps, duration=duration, frames=frames)
    frame_interval_seconds = 0.0 if fps <= 0 else 1.0 / float(fps)
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
            direct_only=direct_only,
            helper_exe=helper_exe,
            app_bundle=resolved_app_bundle,
            app_executable=resolved_app_executable,
            direct_sender_library=direct_sender_library,
        )
    except TypeError:
        camera = camera_builder(
            width=width,
            height=height,
            fps=fps,
            helper_exe=helper_exe,
            app_bundle=resolved_app_bundle,
            app_executable=resolved_app_executable,
            direct_sender_library=direct_sender_library,
        )
    frame_source_kind = "custom"
    python_entrypoint_kind = _entrypoint_python_kind(entrypoint)
    requested_access_snapshot = None
    if request_camera_access:
        request_access = getattr(camera, "request_camera_access", None)
        if callable(request_access):
            requested_access_snapshot = request_access()
    if frame_factory is None:
        payload_factory, payload_kind = _resolve_frame_factory(
            width=width,
            height=height,
            frame_kind=frame_kind,
        )
        producer, frame_source_kind = _wrap_entrypoint_payload(
            entrypoint,
            payload_factory,
            payload_kind,
        )
    else:
        producer = frame_factory

    frames_sent = 0
    camera_state: dict[str, object] | None = None
    try:
        try:
            if probe_only:
                camera_state = _snapshot_camera_state(camera)
                requested_frames = 0
            else:
                camera.start(name=name)
                for index in range(requested_frames):
                    _submit_frame(camera, entrypoint, producer())
                    frames_sent += 1
                    if index + 1 < requested_frames and frame_interval_seconds > 0:
                        sleeper(frame_interval_seconds)
                camera_state = _snapshot_camera_state(camera)
        except Exception as exc:
            if camera_state is None:
                camera_state = _snapshot_camera_state(camera)
            raise DirectPushDemoRuntimeError(str(exc), camera_state=camera_state) from exc
    finally:
        if camera_state is None:
            camera_state = _snapshot_camera_state(camera)
        camera.close()

    payload = build_demo_report(
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        requested_frames=requested_frames,
        frames_sent=frames_sent,
        camera_name=name,
        camera=camera,
        frame_source_kind=frame_source_kind,
        python_entrypoint_kind=python_entrypoint_kind,
        requested_frame_kind=frame_kind,
        requested_entrypoint=entrypoint,
        direct_only=direct_only,
        probe_only=probe_only,
    )
    payload.update(camera_state)
    if requested_access_snapshot is not None:
        payload["requested_camera_access"] = True
        payload["requested_camera_access_snapshot"] = requested_access_snapshot
    direct_runtime_ready, direct_runtime_note = _evaluate_direct_runtime_payload(payload)
    payload["direct_runtime_ready"] = direct_runtime_ready
    if direct_runtime_note:
        payload["direct_runtime_note"] = direct_runtime_note
    return payload


def main(
    argv: list[str] | None = None,
    *,
    camera_factory=None,
    sleeper: Callable[[float], None] = time.sleep,
    frame_factory=None,
) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS direct-push virtual camera demo")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--name", default="AK Virtual Camera")
    parser.add_argument(
        "--allow-shared-memory-fallback",
        action="store_true",
        help="Allow installer/shared-memory fallback instead of requiring pure direct sender mode.",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Only inspect the native direct sender device snapshot without starting or pushing frames.",
    )
    parser.add_argument(
        "--request-camera-access",
        action="store_true",
        help="Request macOS camera permission for the current Python process before probing or starting.",
    )
    parser.add_argument(
        "--require-direct-runtime",
        action="store_true",
        help="Fail if the resulting runtime path is not pure direct sender with no helper hot path or shared-memory fallback.",
    )
    parser.add_argument("--app-bundle")
    parser.add_argument("--app-executable")
    parser.add_argument("--host-bundle")
    parser.add_argument("--host-executable")
    parser.add_argument("--direct-sender-library")
    parser.add_argument(
        "--frame-kind",
        choices=("auto", "numpy", "bytes", "bgra-bytes", "qimage-bgra"),
        default="auto",
    )
    parser.add_argument(
        "--entrypoint",
        choices=("push-frame", "send-pixmap", "send-widget", "send-screen"),
        default="push-frame",
    )
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
    if app_bundle and app_executable:
        parser.error("--app-bundle/--host-bundle and --app-executable/--host-executable are mutually exclusive")

    common_kwargs = dict(
        width=args.width,
        height=args.height,
        fps=args.fps,
        duration=args.duration,
        frames=args.frames,
        name=args.name,
        direct_only=not bool(args.allow_shared_memory_fallback),
        app_bundle=app_bundle,
        app_executable=app_executable,
        direct_sender_library=args.direct_sender_library,
        frame_kind=args.frame_kind,
        entrypoint=args.entrypoint,
        request_camera_access=bool(args.request_camera_access),
        camera_factory=camera_factory,
        sleeper=sleeper,
        frame_factory=frame_factory,
    )

    try:
        payload = run_demo(
            **common_kwargs,
            probe_only=bool(args.probe_only),
        )
    except (RuntimeError, ValueError) as exc:
        failure_camera_state = (
            dict(exc.camera_state)
            if isinstance(exc, DirectPushDemoRuntimeError)
            else {}
        )
        if args.report_json:
            try:
                payload = run_demo(
                    **common_kwargs,
                    probe_only=True,
                )
            except Exception:
                payload = {
                    "mode": "direct-push",
                    "direct_only": not bool(args.allow_shared_memory_fallback),
                    "allow_shared_memory_fallback": bool(args.allow_shared_memory_fallback),
                    "probe_only": bool(args.probe_only),
                    "camera_name": args.name,
                    "requested_frame_kind": args.frame_kind,
                    "requested_entrypoint": args.entrypoint,
                    "direct_sender_last_error": str(exc),
                    "error": str(exc),
                }
            if failure_camera_state:
                payload.update(failure_camera_state)
            payload["probe_only"] = bool(args.probe_only)
            payload["failure_report_generated_via_probe"] = True
            payload["requested_frames"] = _resolve_frame_count(
                fps=args.fps,
                duration=args.duration,
                frames=args.frames,
            )
            payload["frames_sent"] = 0
            payload["error"] = str(exc)
            rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            output_path = Path(args.report_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        print(str(exc), file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.report_json:
        output_path = Path(args.report_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    if args.require_direct_runtime and payload.get("direct_runtime_ready") is not True:
        print(
            str(payload.get("direct_runtime_note") or "direct runtime requirement failed"),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
