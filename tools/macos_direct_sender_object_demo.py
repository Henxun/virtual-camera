# SPDX-License-Identifier: Apache-2.0
"""Direct macOS sender-object demo mirroring the accepted native sender path.

This helper exercises the low-level Python compatibility object path directly:

    MacDirectCameraSender.send(...)

It is intentionally narrower than ``macos_direct_push_demo.py``:
- no shared-memory fallback
- no helper hot path
- targets the native CMIO sink-stream sender object directly
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable


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


def _default_sender_factory(
    *,
    width: int,
    height: int,
    fps: float,
    name: str,
    direct_sender_library: str | None = None,
):
    from akvc.sdk import MacDirectCameraSender

    return MacDirectCameraSender(
        width=width,
        height=height,
        fps=fps,
        camera_name=name,
        library_path=direct_sender_library,
    )


def _default_sdk_readiness_probe(
    *,
    width: int,
    height: int,
    fps: float,
    name: str,
    request_camera_access: bool,
    direct_sender_library: str | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
):
    resolved_app_bundle, resolved_app_executable = _resolve_container_app_args(
        app_bundle=app_bundle,
        app_executable=app_executable,
        host_bundle=host_bundle,
        host_executable=host_executable,
    )

    return {
        "ready": None,
        "blocker_code": "compatibility_probe_unavailable",
        "message": (
            "当前仓库已不再依赖旧的 Python macOS VirtualCamera facade；"
            "请以 sender 自身 readiness 或已验收的原生运行链路为准。"
        ),
        "app_bundle": resolved_app_bundle,
        "app_executable": resolved_app_executable,
        "direct_sender_library": direct_sender_library,
        "request_camera_access": bool(request_camera_access),
    }


def _make_bytes_frame_factory(*, width: int, height: int) -> tuple[Callable[[], Any], str]:
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


def _import_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "direct sender object demo requires numpy for frame-kind=numpy-direct. "
            "Install it first, for example: python -m pip install numpy"
        ) from exc
    return np


def _make_numpy_frame_factory(*, width: int, height: int) -> tuple[Callable[[], Any], str]:
    np = _import_numpy()
    state = {"index": 0}

    def _factory():
        index = state["index"]
        state["index"] += 1
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = ((index * 5) % 256, 96, 180)
        return frame

    return _factory, "numpy.ndarray"


def _make_bgra_bytes_frame_factory(*, width: int, height: int) -> tuple[Callable[[], Any], str]:
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


def _make_frame_factory(
    *,
    width: int,
    height: int,
    frame_kind: str,
) -> tuple[Callable[[], Any], str]:
    if frame_kind == "bytes-bgr":
        return _make_bytes_frame_factory(width=width, height=height)
    if frame_kind == "bytes-bgra":
        return _make_bgra_bytes_frame_factory(width=width, height=height)
    if frame_kind == "numpy-direct":
        return _make_numpy_frame_factory(width=width, height=height)
    raise ValueError(f"unsupported direct sender object frame kind: {frame_kind}")


def _sender_library_path(sender: object) -> str | None:
    value = getattr(sender, "library_path", None)
    return str(value) if isinstance(value, str) and value else None


def _sender_camera_name(sender: object, requested_name: str) -> str:
    value = getattr(sender, "camera_name", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    normalized = str(requested_name).strip()
    return normalized or "AK Virtual Camera"


def _sender_readiness(
    sender: object,
    *,
    requested_name: str,
    request_camera_access: bool,
    snapshot: dict[str, object] | None,
) -> dict[str, object] | None:
    readiness = getattr(sender, "direct_sender_readiness", None)
    if callable(readiness):
        result = readiness(
            name=requested_name,
            request_camera_access=request_camera_access,
        )
        if isinstance(result, dict):
            return dict(result)
    if not isinstance(snapshot, dict):
        return None
    camera_access_status = str(snapshot.get("camera_access_status") or "").strip() or "unknown"
    environment_empty = bool(snapshot.get("environment_device_enumeration_empty"))
    visible_devices = [
        str(item).strip()
        for item in snapshot.get("all_devices", [])
        if str(item).strip()
    ] if isinstance(snapshot.get("all_devices"), list) else []
    normalized_name = str(requested_name).strip() or "AK Virtual Camera"
    visible_keys = {name.casefold() for name in visible_devices}
    target_visible = normalized_name.casefold() in visible_keys
    ready = camera_access_status == "authorized" and target_visible and not environment_empty
    blocker_code = "ready" if ready else "direct_sender_not_ready"
    message = (
        "当前进程已具备 direct sender 发送条件。"
        if ready
        else "当前 demo 运行时没有拿到原生 readiness helper，已回退为基于 snapshot 的近似判断。"
    )
    return {
        "ready": ready,
        "blocker_code": blocker_code,
        "message": message,
        "camera_name": normalized_name,
        "camera_access_status": camera_access_status,
        "target_visible": target_visible,
        "visible_devices": visible_devices,
        "snapshot": dict(snapshot),
    }


def build_report(
    *,
    width: int,
    height: int,
    fps: float,
    name: str,
    frame_kind: str,
    frame_source_kind: str,
    requested_frames: int,
    frames_sent: int,
    consumer_count: int,
    direct_sender_library_path: str | None,
    device_snapshot: dict[str, object] | None,
    requested_camera_access_snapshot: dict[str, object] | None,
    direct_sender_readiness: dict[str, object] | None,
    sdk_direct_sender_readiness: dict[str, object] | None,
    requested_camera_access: bool,
    inspect_only: bool,
) -> dict[str, object]:
    direct_sender_state = "inspected" if inspect_only else "active"
    return {
        "mode": "direct-sender-object",
        "backend_name": "direct_sender_object",
        "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
        "width": int(width),
        "height": int(height),
        "fps": float(fps),
        "camera_name": str(name),
        "requested_frame_kind": str(frame_kind),
        "frame_source_kind": str(frame_source_kind),
        "requested_frames": int(requested_frames),
        "frames_sent": int(frames_sent),
        "consumer_count": int(consumer_count),
        "requested_camera_access": bool(requested_camera_access),
        "sdk_direct_push_used": False,
        "using_direct_sender": True,
        "direct_sender_attempted": True,
        "direct_sender_state": direct_sender_state,
        "direct_sender_target_name": str(name),
        "direct_sender_library_path": direct_sender_library_path,
        "runtime_topology": {
            "runtime_topology_kind": "camera_extension_direct_sender_object",
            "runtime_frame_path": (
                "python_object -> MacDirectCameraSender -> camera_extension "
                "-> system_camera_device -> client_app"
            ),
            "runtime_host_role": "activation_and_install_out_of_band",
            "runtime_host_in_frame_hot_path": False,
            "runtime_dedicated_host_daemon_required": False,
            "runtime_container_app_configured": None,
            "runtime_data_plane": "cmio_sink_stream_direct",
            "runtime_control_plane": "system_extension_preinstalled",
        },
        "runtime_topology_kind": "camera_extension_direct_sender_object",
        "runtime_frame_path": (
            "python_object -> MacDirectCameraSender -> camera_extension "
            "-> system_camera_device -> client_app"
        ),
        "runtime_host_role": "activation_and_install_out_of_band",
        "runtime_host_in_frame_hot_path": False,
        "runtime_dedicated_host_daemon_required": False,
        "runtime_container_app_configured": None,
        "runtime_data_plane": "cmio_sink_stream_direct",
        "runtime_control_plane": "system_extension_preinstalled",
        "helper_hot_path_used": False,
        "shared_memory_fallback_used": False,
        "inspect_only": bool(inspect_only),
        "direct_only": True,
        "device_snapshot": device_snapshot,
        "direct_sender_device_snapshot": device_snapshot,
        "requested_camera_access_snapshot": requested_camera_access_snapshot,
        "direct_sender_readiness": direct_sender_readiness,
        "direct_sender_ready": (
            direct_sender_readiness.get("ready")
            if isinstance(direct_sender_readiness, dict)
            else None
        ),
        "direct_sender_blocker_code": (
            direct_sender_readiness.get("blocker_code")
            if isinstance(direct_sender_readiness, dict)
            else None
        ),
        "direct_sender_readiness_message": (
            direct_sender_readiness.get("message")
            if isinstance(direct_sender_readiness, dict)
            else None
        ),
        "sdk_direct_sender_readiness": sdk_direct_sender_readiness,
        "sdk_direct_sender_ready": (
            sdk_direct_sender_readiness.get("ready")
            if isinstance(sdk_direct_sender_readiness, dict)
            else None
        ),
        "sdk_direct_sender_blocker_code": (
            sdk_direct_sender_readiness.get("blocker_code")
            if isinstance(sdk_direct_sender_readiness, dict)
            else None
        ),
        "sdk_direct_sender_readiness_message": (
            sdk_direct_sender_readiness.get("message")
            if isinstance(sdk_direct_sender_readiness, dict)
            else None
        ),
    }


def run_demo(
    *,
    width: int,
    height: int,
    fps: float,
    frames: int,
    name: str,
    frame_kind: str = "bytes-bgr",
    request_camera_access: bool = False,
    inspect_only: bool = False,
    direct_sender_library: str | None = None,
    app_bundle: str | None = None,
    app_executable: str | None = None,
    host_bundle: str | None = None,
    host_executable: str | None = None,
    sender_factory: Callable[..., object] = _default_sender_factory,
    sdk_readiness_factory: Callable[..., dict[str, object] | None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    sender = sender_factory(
        width=width,
        height=height,
        fps=fps,
        name=name,
        direct_sender_library=direct_sender_library,
    )
    device_snapshot = None
    requested_camera_access_snapshot = None
    snapshot_getter = getattr(sender, "available_device_snapshot", None)
    if callable(snapshot_getter):
        snapshot = snapshot_getter()
        if isinstance(snapshot, dict):
            device_snapshot = dict(snapshot)
    request_access_getter = getattr(sender, "request_camera_access", None)
    if request_camera_access and callable(request_access_getter):
        snapshot = request_access_getter()
        if isinstance(snapshot, dict):
            requested_camera_access_snapshot = dict(snapshot)
            if device_snapshot is None:
                device_snapshot = dict(snapshot)
    readiness_payload = _sender_readiness(
        sender,
        requested_name=name,
        request_camera_access=request_camera_access,
        snapshot=requested_camera_access_snapshot or device_snapshot,
    )
    sdk_readiness_payload = None
    resolved_app_bundle, resolved_app_executable = _resolve_container_app_args(
        app_bundle=app_bundle,
        app_executable=app_executable,
        host_bundle=host_bundle,
        host_executable=host_executable,
    )
    if sdk_readiness_factory is not None:
        try:
            candidate = sdk_readiness_factory(
                width=width,
                height=height,
                fps=fps,
                name=name,
                request_camera_access=bool(request_camera_access),
                direct_sender_library=direct_sender_library,
                app_bundle=resolved_app_bundle,
                app_executable=resolved_app_executable,
            )
        except Exception:
            candidate = None
        if isinstance(candidate, dict):
            sdk_readiness_payload = dict(candidate)

    requested_frames = int(frames)
    frames_sent = 0
    frame_source_kind = "none"
    try:
        if not inspect_only:
            frame_factory, frame_source_kind = _make_frame_factory(
                width=width,
                height=height,
                frame_kind=frame_kind,
            )
            period = 1.0 / max(float(fps), 1.0)
            for _ in range(requested_frames):
                sender.send(frame_factory())
                frames_sent += 1
                sleeper(period)
        return build_report(
            width=width,
            height=height,
            fps=fps,
            name=_sender_camera_name(sender, name),
            frame_kind=frame_kind,
            frame_source_kind=frame_source_kind,
            requested_frames=requested_frames,
            frames_sent=frames_sent,
            consumer_count=int(getattr(sender, "consumer_count", 0) or 0),
            direct_sender_library_path=_sender_library_path(sender),
            device_snapshot=device_snapshot,
            requested_camera_access_snapshot=requested_camera_access_snapshot,
            direct_sender_readiness=readiness_payload,
            sdk_direct_sender_readiness=sdk_readiness_payload,
            requested_camera_access=bool(request_camera_access),
            inspect_only=inspect_only,
        )
    finally:
        close = getattr(sender, "close", None)
        if callable(close):
            close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS direct sender object demo")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--name", default="AK Virtual Camera")
    parser.add_argument(
        "--frame-kind",
        choices=("bytes-bgr", "bytes-bgra", "numpy-direct"),
        default="bytes-bgr",
    )
    parser.add_argument("--direct-sender-library")
    parser.add_argument("--app-bundle")
    parser.add_argument("--app-executable")
    parser.add_argument("--host-bundle")
    parser.add_argument("--host-executable")
    parser.add_argument("--request-camera-access", action="store_true")
    parser.add_argument("--inspect-only", action="store_true")
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

    common_kwargs = dict(
        width=args.width,
        height=args.height,
        fps=args.fps,
        frames=args.frames,
        name=args.name,
        frame_kind=args.frame_kind,
        request_camera_access=bool(args.request_camera_access),
        direct_sender_library=args.direct_sender_library,
        app_bundle=app_bundle,
        app_executable=app_executable,
        sdk_readiness_factory=_default_sdk_readiness_probe,
    )
    try:
        payload = run_demo(
            **common_kwargs,
            inspect_only=bool(args.inspect_only),
        )
        exit_code = 0
    except (RuntimeError, ValueError) as exc:
        if args.report_json:
            try:
                payload = run_demo(
                    **common_kwargs,
                    inspect_only=True,
                )
            except Exception:
                payload = {
                    "mode": "direct-sender-object",
                    "backend_name": "direct_sender_object",
                    "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
                    "camera_name": str(args.name),
                    "requested_frame_kind": str(args.frame_kind),
                    "requested_frames": int(args.frames),
                    "frames_sent": 0,
                    "direct_only": True,
                    "inspect_only": True,
                    "using_direct_sender": True,
                    "direct_sender_attempted": True,
                }
            payload["error"] = str(exc)
            payload.setdefault("direct_sender_last_error", str(exc))
            exit_code = 1
        else:
            print(str(exc), file=sys.stderr)
            return 1

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)

    if args.report_json:
        output = Path(args.report_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
