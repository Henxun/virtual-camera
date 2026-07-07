# SPDX-License-Identifier: Apache-2.0
"""Cross-language macOS Frame Bus roundtrip validator.

Publishes one NV12 frame with either the raw Python POSIX shared-memory sink
or the public `VirtualCamera.start()+push_frame()` object path, then
verifies that the native `framebus_posix.c` consumer can read the same frame
through a small C probe binary.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-core" / "src"))

from akvc.core.errors import FrameBusError, FrameBusOpenError  # noqa: E402
from akvc.core.frame import FLAG_DISCONTINUITY, Frame, FourCC  # noqa: E402
from akvc.core.frame_sink.macos_shm import SHM_NAME, MacOsShmSink  # noqa: E402
from akvc.platforms.macos.installer import (  # noqa: E402
    ExtensionInstallState,
    ExtensionStatus,
)
from akvc.sdk.virtual_camera import VirtualCamera  # noqa: E402


HARNESS_SOURCE = ROOT / "virtualcam" / "macos" / "ipc" / "src" / "framebus_consumer_probe.c"
FRAMEBUS_SOURCE = ROOT / "virtualcam" / "macos" / "ipc" / "src" / "framebus_posix.c"
FRAMEBUS_INCLUDE = ROOT / "virtualcam" / "macos" / "ipc" / "include"
SHARED_INCLUDE = ROOT / "virtualcam" / "shared"
DEFAULT_BINARY = ROOT / "build" / "macos" / "framebus_consumer_probe"
DEFAULT_PRODUCER_KIND = "shm-sink"
PRODUCER_KINDS = (DEFAULT_PRODUCER_KIND, "mac-virtual-camera")


class _RoundtripInstaller:
    def __init__(self, *, shm_name: str, camera_name: str = "AK Virtual Camera") -> None:
        self._shm_name = shm_name
        self._camera_name = camera_name

    def extension_state(self) -> ExtensionInstallState:
        return ExtensionInstallState.INSTALLED

    def enumerate_devices(self) -> list[str]:
        return [self._camera_name]

    def status(self) -> ExtensionStatus:
        return ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            devices=[self._camera_name],
            all_devices=[self._camera_name],
            device_prefix=self._camera_name,
            enabled=True,
            shared_memory_name=self._shm_name,
            ipc_transport="shared_memory_ringbuffer",
            ipc_probe_present=False,
        )


class _IdentityPipeline:
    def process(self, frame: Frame) -> Frame:
        return frame


def _sdk_path() -> str:
    out = subprocess.check_output(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
        text=True,
    ).strip()
    if not out:
        raise RuntimeError("xcrun returned an empty macOS SDK path")
    return out


def _compile_probe(binary: Path, *, compiler: str) -> list[str]:
    sdk = _sdk_path()
    binary.parent.mkdir(parents=True, exist_ok=True)
    command = [
        compiler,
        "-std=c11",
        "-O2",
        "-isysroot",
        sdk,
        "-mmacosx-version-min=13.0",
        "-I",
        str(FRAMEBUS_INCLUDE),
        "-I",
        str(SHARED_INCLUDE),
        str(HARNESS_SOURCE),
        str(FRAMEBUS_SOURCE),
        "-o",
        str(binary),
    ]
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "failed to compile framebus consumer probe:\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return command


def _cleanup_shared_region(shm_name: str) -> None:
    libc_path = ctypes.util.find_library("c")
    if not libc_path:
        return
    libc = ctypes.CDLL(libc_path, use_errno=True)
    shm_unlink = libc.shm_unlink
    shm_unlink.restype = ctypes.c_int
    shm_unlink.argtypes = [ctypes.c_char_p]
    shm_unlink(shm_name.encode("ascii"))


def _checksum_bytes(data: bytes) -> int:
    acc = 1469598103934665603
    for byte in data:
        acc ^= byte
        acc = (acc * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return acc


def _make_nv12_payload(width: int, height: int) -> tuple[bytes, bytes]:
    if width <= 0 or height <= 0 or width % 2 != 0 or height % 2 != 0:
        raise ValueError("width and height must be positive even numbers for NV12")
    y_plane = bytes(((index * 7) + 11) % 256 for index in range(width * height))
    uv_plane = bytes(((index * 13) + 19) % 256 for index in range((width * height) // 2))
    return y_plane, uv_plane


def _make_roundtrip_frame(*, width: int, height: int, flags: int) -> tuple[Frame, dict[str, object]]:
    y_plane, uv_plane = _make_nv12_payload(width, height)
    frame = Frame(
        width=width,
        height=height,
        fourcc=FourCC.NV12,
        data=y_plane + uv_plane,
        pts_100ns=123456789,
        flags=flags,
        stride=(width, width),
        plane_size=(len(y_plane), len(uv_plane)),
    )
    expected = {
        "producer_seq": 1,
        "consumer_count": 1,
        "view_seq": 1,
        "width": width,
        "height": height,
        "fourcc": FourCC.NV12,
        "flags": flags,
        "stride0": width,
        "stride1": width,
        "plane0_size": len(y_plane),
        "plane1_size": len(uv_plane),
        "plane0_checksum": _checksum_bytes(y_plane),
        "plane1_checksum": _checksum_bytes(uv_plane),
    }
    return frame, expected


def _publish_with_shm_sink(*, frame: Frame, shm_name: str) -> tuple[dict[str, object] | None, MacOsShmSink]:
    sink = MacOsShmSink(shm_name=shm_name)
    producer_control: dict[str, object] | None = None
    sink.open()
    sink.publish(frame)
    ctrl = sink._read_ctrl()
    producer_control = {
        "producer_seq": int(ctrl.producer_seq),
        "writer_pid": int(ctrl.writer_pid),
        "consumer_count": int(ctrl.consumer_count),
        "slot_count": int(ctrl.slot_count),
        "slot_size": int(ctrl.slot_size),
    }
    return producer_control, sink


def _publish_with_virtual_camera(
    *,
    frame: Frame,
    shm_name: str,
) -> tuple[dict[str, object] | None, VirtualCamera]:
    camera = VirtualCamera(
        pipeline=_IdentityPipeline(),
    )
    backend = getattr(camera, "_mac_backend", None)
    if backend is None:
        raise RuntimeError("VirtualCamera did not create a macOS backend")
    backend._installer = _RoundtripInstaller(shm_name=shm_name)
    camera.start(name="AK Virtual Camera")
    camera.push_frame(frame)
    producer_control: dict[str, object] | None = None
    sink = getattr(backend, "_sink", None)
    if sink is not None and hasattr(sink, "_read_ctrl"):
        ctrl = sink._read_ctrl()
        producer_control = {
            "producer_seq": int(ctrl.producer_seq),
            "writer_pid": int(ctrl.writer_pid),
            "consumer_count": int(ctrl.consumer_count),
            "slot_count": int(ctrl.slot_count),
            "slot_size": int(ctrl.slot_size),
        }
    return producer_control, camera


def _run_probe(binary: Path, *, attempts: int, sleep_ms: int, shm_name: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(binary),
            "--attempts",
            str(attempts),
            "--sleep-ms",
            str(sleep_ms),
            "--shm-name",
            shm_name,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"framebus consumer probe returned no stdout (rc={completed.returncode}, stderr={completed.stderr.strip()})"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "framebus consumer probe returned invalid JSON:\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{completed.stderr}"
        ) from exc
    payload["returncode"] = completed.returncode
    payload["stderr"] = completed.stderr.strip()
    return payload


def _extract_errno(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"errno=(\d+)", text)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _build_error_payload(
    *,
    binary: Path,
    compile_command: list[str] | None,
    expected: dict[str, object],
    producer_control: dict[str, object] | None,
    error: BaseException,
    status: str,
    shm_name: str,
    producer_kind: str,
) -> dict[str, object]:
    message = str(error)
    direct_open_errno = _extract_errno(message)
    environment_blocked = direct_open_errno in {1, 13}
    observed = {
        "status": status,
        "direct_open_errno": direct_open_errno,
        "producer_alive": False,
        "returncode": None,
        "stderr": "",
    }
    consistency = {
        "status_ok": False,
        "producer_alive": False,
        "environment_blocked": environment_blocked,
    }
    for key in expected:
        consistency[f"{key}_match"] = False
    consistency["all_checks_passed"] = False
    return {
        "compile_command": compile_command,
        "binary": str(binary),
        "harness_source": str(HARNESS_SOURCE),
        "framebus_source": str(FRAMEBUS_SOURCE),
        "producer_kind": producer_kind,
        "shared_memory_name": shm_name,
        "producer_control": producer_control,
        "expected": expected,
        "observed": observed,
        "consistency": consistency,
        "environment_blocked": environment_blocked,
        "error": message,
    }


def evaluate_roundtrip(
    *,
    width: int,
    height: int,
    binary: Path,
    compiler: str,
    skip_compile: bool,
    attempts: int,
    sleep_ms: int,
    flags: int,
    shm_name: str,
    producer_kind: str = DEFAULT_PRODUCER_KIND,
) -> dict[str, object]:
    compile_command: list[str] | None = None
    if not skip_compile:
        compile_command = _compile_probe(binary, compiler=compiler)

    if producer_kind not in PRODUCER_KINDS:
        raise ValueError(f"unsupported producer_kind: {producer_kind}")

    frame, expected = _make_roundtrip_frame(width=width, height=height, flags=flags)

    _cleanup_shared_region(shm_name)
    producer_control: dict[str, object] | None = None
    producer = None
    try:
        if producer_kind == DEFAULT_PRODUCER_KIND:
            producer_control, producer = _publish_with_shm_sink(frame=frame, shm_name=shm_name)
        else:
            producer_control, producer = _publish_with_virtual_camera(frame=frame, shm_name=shm_name)
        observed = _run_probe(binary, attempts=attempts, sleep_ms=sleep_ms, shm_name=shm_name)
    except FrameBusOpenError as exc:
        return _build_error_payload(
            binary=binary,
            compile_command=compile_command,
            expected=expected,
            producer_control=producer_control,
            error=exc,
            status="producer_open_failed",
            shm_name=shm_name,
            producer_kind=producer_kind,
        )
    except FrameBusError as exc:
        return _build_error_payload(
            binary=binary,
            compile_command=compile_command,
            expected=expected,
            producer_control=producer_control,
            error=exc,
            status="producer_publish_failed",
            shm_name=shm_name,
            producer_kind=producer_kind,
        )
    except RuntimeError as exc:
        return _build_error_payload(
            binary=binary,
            compile_command=compile_command,
            expected=expected,
            producer_control=producer_control,
            error=exc,
            status="probe_runtime_failed",
            shm_name=shm_name,
            producer_kind=producer_kind,
        )
    finally:
        try:
            if producer is not None and hasattr(producer, "close"):
                producer.close()
        finally:
            _cleanup_shared_region(shm_name)

    consistency = {
        "status_ok": observed.get("status") == "ok" and observed.get("returncode") == 0,
        "producer_alive": observed.get("producer_alive") is True,
    }
    for key, value in expected.items():
        consistency[f"{key}_match"] = observed.get(key) == value
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "compile_command": compile_command,
        "binary": str(binary),
        "harness_source": str(HARNESS_SOURCE),
        "framebus_source": str(FRAMEBUS_SOURCE),
        "producer_kind": producer_kind,
        "shared_memory_name": shm_name,
        "producer_control": producer_control,
        "expected": expected,
        "observed": observed,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS Frame Bus roundtrip validator")
    parser.add_argument("--width", type=int, default=128)
    parser.add_argument("--height", type=int, default=72)
    parser.add_argument("--compiler", default="clang")
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--sleep-ms", type=int, default=25)
    parser.add_argument("--flags", type=int, default=FLAG_DISCONTINUITY)
    parser.add_argument("--shm-name", default=SHM_NAME)
    parser.add_argument("--producer-kind", choices=PRODUCER_KINDS, default=DEFAULT_PRODUCER_KIND)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        print("macOS framebus roundtrip requires darwin", file=sys.stderr)
        return 1

    payload = evaluate_roundtrip(
        width=args.width,
        height=args.height,
        binary=args.binary,
        compiler=args.compiler,
        skip_compile=bool(args.skip_compile),
        attempts=max(1, args.attempts),
        sleep_ms=max(0, args.sleep_ms),
        flags=int(args.flags),
        shm_name=str(args.shm_name),
        producer_kind=str(args.producer_kind),
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if payload["consistency"]["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
