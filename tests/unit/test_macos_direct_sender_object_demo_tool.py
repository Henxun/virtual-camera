# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS direct sender object demo helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_direct_sender_object_demo.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("macos_direct_sender_object_demo", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSender:
    def __init__(self) -> None:
        self.start_calls: list[str] = []
        self.send_calls = []
        self.close_calls = 0
        self.consumer_count = 1
        self.library_path = "/tmp/libakvc-macos-direct-sender.dylib"
        self.snapshot = {
            "all_devices": ["AKVC Direct"],
            "camera_access_status": "authorized",
            "environment_device_enumeration_empty": False,
        }
        self.request_camera_access_calls = 0

    def available_device_snapshot(self) -> dict[str, object]:
        return dict(self.snapshot)

    def request_camera_access(self) -> dict[str, object]:
        self.request_camera_access_calls += 1
        return dict(self.snapshot)

    def direct_sender_readiness(self, *, name: str | None = None, request_camera_access: bool = False):
        return {
            "ready": True,
            "blocker_code": "ready",
            "message": "当前进程已具备 direct sender 发送条件。",
            "camera_name": name or "AK Virtual Camera",
            "camera_access_status": "authorized",
            "target_visible": True,
            "visible_devices": ["AKVC Direct"],
            "snapshot": dict(self.snapshot),
        }

    def start(self, name: str = "AK Virtual Camera") -> None:
        self.start_calls.append(name)

    def send(self, frame) -> None:
        self.send_calls.append(frame)

    def close(self) -> None:
        self.close_calls += 1


def test_macos_direct_sender_object_demo_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "MacDirectCameraSender.send(...)" in text
    assert "camera_name=name" in text
    assert "--frame-kind" in text
    assert "--direct-sender-library" in text
    assert "--app-bundle" in text
    assert "--host-bundle" in text
    assert "--host-executable" in text
    assert "--request-camera-access" in text
    assert "--inspect-only" in text
    assert "--report-json" in text
    assert '"mode": "direct-sender-object"' in text


def test_run_demo_uses_sender_object_path_and_reports_frames_sent() -> None:
    module = _load_module()
    sender = FakeSender()
    slept = []
    original_factory = module._make_frame_factory

    class FakeFrame:
        pass

    def fake_make_frame_factory(*, width: int, height: int, frame_kind: str):
        assert width == 640
        assert height == 360
        assert frame_kind == "bytes-bgr"
        state = {"index": 0}

        def _factory():
            state["index"] += 1
            return FakeFrame()

        return _factory, "Frame"

    module._make_frame_factory = fake_make_frame_factory
    try:
        payload = module.run_demo(
            width=640,
            height=360,
            fps=20.0,
            frames=3,
            name="AKVC Direct",
            sender_factory=lambda **kwargs: sender,
            sleeper=lambda seconds: slept.append(seconds),
        )
    finally:
        module._make_frame_factory = original_factory

    assert sender.start_calls == []
    assert len(sender.send_calls) == 3
    assert sender.close_calls == 1
    assert payload["mode"] == "direct-sender-object"
    assert payload["python_entrypoint_kind"] == "MacDirectCameraSender.send(auto-open)"
    assert payload["requested_frame_kind"] == "bytes-bgr"
    assert payload["frame_source_kind"] == "Frame"
    assert payload["frames_sent"] == 3
    assert payload["consumer_count"] == 1
    assert payload["helper_hot_path_used"] is False
    assert payload["shared_memory_fallback_used"] is False
    assert payload["device_snapshot"]["all_devices"] == ["AKVC Direct"]
    assert payload["direct_sender_ready"] is True
    assert payload["direct_sender_blocker_code"] == "ready"
    assert payload["direct_sender_readiness"]["camera_name"] == "AKVC Direct"
    assert payload["sdk_direct_sender_readiness"] is None
    assert slept == [0.05, 0.05, 0.05]


def test_run_demo_inspect_only_can_request_camera_access_without_sending() -> None:
    module = _load_module()
    sender = FakeSender()

    payload = module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        frames=5,
        name="AKVC Direct",
        inspect_only=True,
        request_camera_access=True,
        sender_factory=lambda **kwargs: sender,
    )

    assert sender.start_calls == []
    assert sender.send_calls == []
    assert sender.request_camera_access_calls == 1
    assert sender.close_calls == 1
    assert payload["inspect_only"] is True
    assert payload["frames_sent"] == 0
    assert payload["requested_camera_access_snapshot"]["camera_access_status"] == "authorized"
    assert payload["direct_sender_ready"] is True
    assert payload["direct_sender_blocker_code"] == "ready"
    assert payload["sdk_direct_sender_readiness"] is None


def test_run_demo_can_include_augmented_sdk_readiness() -> None:
    module = _load_module()
    sender = FakeSender()

    payload = module.run_demo(
        width=640,
        height=360,
        fps=30.0,
        frames=0,
        name="AKVC Direct",
        inspect_only=True,
        request_camera_access=True,
        host_bundle="/Applications/Amaran Desktop.app",
        sender_factory=lambda **kwargs: sender,
        sdk_readiness_factory=lambda **kwargs: {
            "ready": False,
            "blocker_code": "host_notarization_missing",
            "message": "Notary Ticket Missing",
            "camera_name": kwargs["name"],
            "app_bundle": kwargs["app_bundle"],
            "installer_blocker_code": "host_notarization_missing",
            "direct_sender_blocker_code": "target_device_not_visible",
            "system_extension_registered": False,
        },
    )

    assert payload["sdk_direct_sender_ready"] is False
    assert payload["sdk_direct_sender_blocker_code"] == "host_notarization_missing"
    assert payload["sdk_direct_sender_readiness_message"] == "Notary Ticket Missing"
    assert payload["sdk_direct_sender_readiness"]["app_bundle"] == "/Applications/Amaran Desktop.app"
    assert payload["sdk_direct_sender_readiness"]["system_extension_registered"] is False


def test_main_writes_direct_sender_object_report_json(tmp_path) -> None:
    module = _load_module()
    sender = FakeSender()
    output = tmp_path / "direct-sender-object-report.json"
    original_run_demo = module.run_demo

    def fake_run_demo(**kwargs):
        del kwargs
        sender.close()
        return {
            "mode": "direct-sender-object",
            "frames_sent": 2,
            "camera_name": "AKVC Direct",
        }

    module.run_demo = fake_run_demo
    try:
        rc = module.main(
            [
                "--name",
                "AKVC Direct",
                "--frames",
                "2",
                "--report-json",
                str(output),
            ]
        )
    finally:
        module.run_demo = original_run_demo

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "direct-sender-object"
    assert payload["frames_sent"] == 2


def test_main_writes_inspect_report_when_direct_sender_object_demo_fails(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "direct-sender-object-failure-report.json"
    calls = []
    original_run_demo = module.run_demo

    def fake_run_demo(**kwargs):
        calls.append(dict(kwargs))
        if not kwargs.get("inspect_only"):
            raise RuntimeError("camera device not found: AKVC Direct")
        return {
            "mode": "direct-sender-object",
            "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
            "inspect_only": True,
            "frames_sent": 0,
            "camera_name": "AKVC Direct",
            "direct_sender_ready": False,
            "direct_sender_blocker_code": "target_device_not_visible",
        }

    module.run_demo = fake_run_demo
    try:
        rc = module.main(
            [
                "--name",
                "AKVC Direct",
                "--frames",
                "2",
                "--report-json",
                str(output),
            ]
        )
    finally:
        module.run_demo = original_run_demo

    assert rc == 1
    assert len(calls) == 2
    assert calls[0]["inspect_only"] is False
    assert calls[1]["inspect_only"] is True
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["inspect_only"] is True
    assert payload["error"] == "camera device not found: AKVC Direct"
    assert payload["direct_sender_blocker_code"] == "target_device_not_visible"
