# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS Frame Bus roundtrip helper."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from akvc.core.errors import FrameBusOpenError
from tools import macos_framebus_roundtrip as roundtrip_tool


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_framebus_roundtrip.py"


def test_macos_framebus_roundtrip_tool_exists_and_references_native_probe() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "framebus_consumer_probe.c" in text
    assert "framebus_posix.c" in text
    assert "MacOsShmSink" in text
    assert "VirtualCamera" in text
    assert "all_checks_passed" in text
    assert "xcrun" in text
    assert "shm_unlink" in text
    assert "consumer_count" in text
    assert "producer_open_failed" in text
    assert "--shm-name" in text
    assert "--producer-kind" in text


def test_macos_framebus_roundtrip_tool_can_render_structured_producer_open_failure() -> None:
    payload = roundtrip_tool._build_error_payload(
        binary=ROOT / "build" / "macos" / "framebus_consumer_probe",
        compile_command=["clang", "framebus_consumer_probe.c"],
        expected={"producer_seq": 1, "consumer_count": 1},
        producer_control=None,
        error=FrameBusOpenError("shm_open(create) failed (errno=1)"),
        status="producer_open_failed",
        shm_name="/akvc-custom",
        producer_kind="mac-virtual-camera",
    )

    assert payload["observed"]["status"] == "producer_open_failed"
    assert payload["producer_kind"] == "mac-virtual-camera"
    assert payload["shared_memory_name"] == "/akvc-custom"
    assert payload["observed"]["direct_open_errno"] == 1
    assert payload["environment_blocked"] is True
    assert payload["consistency"]["environment_blocked"] is True
    assert payload["consistency"]["all_checks_passed"] is False


def test_macos_framebus_roundtrip_tool_supports_mac_virtual_camera_producer(monkeypatch, tmp_path) -> None:
    observed_calls: list[str] = []

    monkeypatch.setattr(roundtrip_tool, "_compile_probe", lambda binary, *, compiler: ["clang", str(binary), compiler])
    monkeypatch.setattr(roundtrip_tool, "_cleanup_shared_region", lambda shm_name: None)

    class FakeProducer:
        def close(self) -> None:
            observed_calls.append("producer.close")

    def fake_publish_with_virtual_camera(*, frame, shm_name):
        observed_calls.append(f"publish:{shm_name}:{frame.width}x{frame.height}")
        return (
            {
                "producer_seq": 1,
                "writer_pid": 123,
                "consumer_count": 0,
                "slot_count": 8,
                "slot_size": 1048576,
            },
            FakeProducer(),
        )

    monkeypatch.setattr(roundtrip_tool, "_publish_with_virtual_camera", fake_publish_with_virtual_camera)
    monkeypatch.setattr(
        roundtrip_tool,
        "_run_probe",
        lambda binary, *, attempts, sleep_ms, shm_name: {
            "status": "ok",
            "returncode": 0,
            "stderr": "",
            "producer_alive": True,
            "producer_seq": 1,
            "consumer_count": 1,
            "view_seq": 1,
            "width": 64,
            "height": 36,
            "fourcc": int(roundtrip_tool.FourCC.NV12),
            "flags": 2,
            "stride0": 64,
            "stride1": 64,
            "plane0_size": 64 * 36,
            "plane1_size": (64 * 36) // 2,
            "plane0_checksum": roundtrip_tool._checksum_bytes(roundtrip_tool._make_nv12_payload(64, 36)[0]),
            "plane1_checksum": roundtrip_tool._checksum_bytes(roundtrip_tool._make_nv12_payload(64, 36)[1]),
        },
    )

    payload = roundtrip_tool.evaluate_roundtrip(
        width=64,
        height=36,
        binary=tmp_path / "probe",
        compiler="clang",
        skip_compile=False,
        attempts=3,
        sleep_ms=10,
        flags=2,
        shm_name="/akvc-direct",
        producer_kind="mac-virtual-camera",
    )

    assert payload["producer_kind"] == "mac-virtual-camera"
    assert payload["consistency"]["all_checks_passed"] is True
    assert observed_calls == ["publish:/akvc-direct:64x36", "producer.close"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only roundtrip")
def test_macos_framebus_roundtrip_tool_reports_success(tmp_path) -> None:
    pytest.importorskip("numpy")
    if shutil.which("clang") is None or shutil.which("xcrun") is None:
        pytest.skip("clang/xcrun not available")

    output = tmp_path / "framebus-roundtrip.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--width",
            "64",
            "--height",
            "36",
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else json.loads(completed.stdout)
    if completed.returncode != 0:
        if payload.get("observed", {}).get("direct_open_errno") in {1, 13}:
            pytest.skip("current macOS environment denies cross-process shm_open on the probe path")
        raise AssertionError(completed.stderr or completed.stdout)
    assert payload["consistency"]["all_checks_passed"] is True
    assert payload["observed"]["status"] == "ok"
    assert payload["observed"]["producer_alive"] is True
    assert payload["observed"]["width"] == 64
    assert payload["observed"]["height"] == 36
    assert payload["observed"]["consumer_count"] == 1
    assert payload["observed"]["plane0_size"] == 64 * 36
    assert payload["observed"]["plane1_size"] == (64 * 36) // 2
    assert payload["expected"]["plane0_checksum"] == payload["observed"]["plane0_checksum"]
    assert payload["expected"]["plane1_checksum"] == payload["observed"]["plane1_checksum"]
