# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS smoke validation helper."""

from __future__ import annotations

import stat
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macos_smoke_tool_exists_and_checks_status_install_uninstall() -> None:
    script = ROOT / "tools" / "macos_smoke.py"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "DefaultMacInstallerService" in text
    assert "--name" in text
    assert "--list-devices-tool" in text
    assert "--uninstall-tool" in text
    assert "--app-bundle" in text
    assert "--app-executable" in text
    assert "--host-bundle" in text
    assert "--host-executable" in text
    assert "--direct-sender-library" in text
    assert "--pkg-path" in text
    assert "--installer-executable" in text
    assert "--disable-auto-package" in text
    assert "--run-install" in text
    assert "--run-uninstall" in text
    assert "--direct-push-demo-tool" in text
    assert "--direct-push-frames" in text
    assert "--run-direct-push-demo" in text
    assert "--direct-sender-object-demo-tool" in text
    assert "--direct-sender-object-frames" in text
    assert "--run-direct-sender-object-demo" in text
    assert "--framebus-roundtrip-json" in text
    assert "--output" in text
    assert "enumerated_devices" in text
    assert "ipc_probe_present" in text
    assert "ipc_direct_open_errno" in text
    assert "start_blocker_code" in text
    assert "system_extension_registered" in text
    assert "system_extension_registry_summary" in text
    assert "install_command_notarization_missing" in text
    assert "find_macos_status_tool" in text
    assert "find_macos_list_devices_tool" in text
    assert "install_extension_result" in text
    assert "uninstall_extension_result" in text
    assert '"phase"' in text or "phase" in text
    assert "verification_targets" in text


def test_macos_smoke_tool_wraps_commands_with_host_overrides(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("not_installed", encoding="utf-8")

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    host_bundle = tmp_path / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("#!/bin/sh\n", encoding="utf-8")

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"

    write_tool(
        status_tool,
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
assert os.environ.get("AKVC_HOST_APP_BUNDLE") == {str(host_bundle)!r}
assert os.environ.get("AKVC_HOST_EXECUTABLE") == {str(host_executable)!r}
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
payload = {{
    "state": "installed" if state == "installed" else "not_installed",
    "devices": ["AK Virtual Camera"] if state == "installed" else [],
    "enabled": state == "installed",
}}
print(json.dumps(payload))
""",
    )
    write_tool(
        install_tool,
        f"""#!/usr/bin/env python3
import os
from pathlib import Path
assert os.environ.get("AKVC_HOST_APP_BUNDLE") == {str(host_bundle)!r}
assert os.environ.get("AKVC_HOST_EXECUTABLE") == {str(host_executable)!r}
Path({str(state_file)!r}).write_text("installed", encoding="utf-8")
""",
    )
    write_tool(
        list_devices_tool,
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
assert os.environ.get("AKVC_HOST_APP_BUNDLE") == {str(host_bundle)!r}
assert os.environ.get("AKVC_HOST_EXECUTABLE") == {str(host_executable)!r}
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
print(json.dumps({{"devices": ["AK Virtual Camera"] if state == "installed" else []}}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--host-bundle",
            str(host_bundle),
            "--run-install",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert '"success": true' in completed.stdout
    assert '"phase": "installed_visible"' in completed.stdout


def test_macos_smoke_tool_reports_install_phase_and_devices(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("not_installed", encoding="utf-8")
    device_name_file = tmp_path / "device-name.txt"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"

    write_tool(
        status_tool,
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
device_name = Path(os.environ["AKVC_DEVICE_NAME_FILE"]).read_text(encoding="utf-8").strip()
payload = {{
        "state": "installed",
        "devices": [],
        "device_prefix": device_name,
        "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60],
    }} if state == "installed" else {{
        "state": "not_installed",
        "devices": [],
        "device_prefix": device_name,
        "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60],
    }}
print(json.dumps(payload))
""",
    )
    write_tool(
        install_tool,
        f"""#!/usr/bin/env python3
from pathlib import Path
Path({str(state_file)!r}).write_text("installed", encoding="utf-8")
""",
    )
    write_tool(
        list_devices_tool,
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
device_name = Path(os.environ["AKVC_DEVICE_NAME_FILE"]).read_text(encoding="utf-8").strip()
devices = [device_name] if state == "installed" else []
print(json.dumps({{"devices": devices, "device_prefix": device_name}}))
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--name",
            "AKVC Demo",
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--disable-auto-package",
            "--run-install",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert device_name_file.read_text(encoding="utf-8").strip() == "AKVC Demo"
    assert '"phase": "installed_visible"' in completed.stdout
    assert '"success": true' in completed.stdout
    assert '"device_prefix": "AKVC Demo"' in completed.stdout
    assert '"enumerated_devices": [' in completed.stdout
    assert '"AKVC Demo"' in completed.stdout
    assert '"start_blocker_code": "ready"' in completed.stdout
    assert '"verification_targets": [' in completed.stdout
    assert '"name": "FaceTime"' in completed.stdout
    assert '"supported_formats": [' in completed.stdout
    assert '"3840x2160@30/60 NV12"' in completed.stdout
    assert '"supported_frame_rates": [' in completed.stdout


def test_macos_smoke_tool_writes_roundtrip_json(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("installed", encoding="utf-8")
    output_json = tmp_path / "smoke-report.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"

    write_tool(
        status_tool,
        f"""#!/usr/bin/env python3
import json
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
payload = {{
        "state": "installed",
        "devices": ["AK Virtual Camera"],
        "enabled": True,
        "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60],
    }} if state == "installed" else {{
        "state": "not_installed",
        "devices": [],
        "enabled": False,
        "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60],
    }}
print(json.dumps(payload))
""",
    )
    write_tool(
        install_tool,
        f"""#!/usr/bin/env python3
from pathlib import Path
Path({str(state_file)!r}).write_text("installed", encoding="utf-8")
""",
    )
    write_tool(
        list_devices_tool,
        f"""#!/usr/bin/env python3
import json
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
devices = ["AK Virtual Camera"] if state == "installed" else []
print(json.dumps({{"devices": devices}}))
""",
    )
    write_tool(
        uninstall_tool,
        f"""#!/usr/bin/env python3
from pathlib import Path
Path({str(state_file)!r}).write_text("not_installed", encoding="utf-8")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--uninstall-tool",
            str(uninstall_tool),
            "--disable-auto-package",
            "--run-install",
            "--run-uninstall",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["status"]["state"] == "installed"
    assert payload["status"]["phase"] == "installed_visible"
    assert payload["status"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["status"]["supported_frame_rates"] == [30, 60]
    assert payload["status"]["start_blocker_code"] == "ready"
    assert payload["install"]["success"] is True
    assert payload["install"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["install"]["supported_frame_rates"] == [30, 60]
    assert payload["install"]["start_blocker_code"] == "ready"
    assert payload["status_after_install"]["state"] == "installed"
    assert payload["status_after_install"]["supported_frame_rates"] == [30, 60]
    assert payload["uninstall"]["success"] is True
    assert payload["uninstall"]["phase"] == "uninstalled"
    assert payload["uninstall"]["state"] == "not_installed"
    assert payload["uninstall"]["returncode"] == 0
    assert payload["status_after_uninstall"]["state"] == "not_installed"


def test_macos_smoke_tool_merges_framebus_roundtrip_status_into_report(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("installed", encoding="utf-8")
    output_json = tmp_path / "smoke-report.json"
    framebus_json = tmp_path / "framebus-roundtrip.json"
    framebus_json.write_text(
        json.dumps(
            {
                "observed": {
                    "status": "open_failed",
                    "direct_open_errno": 13,
                },
                "consistency": {
                    "all_checks_passed": False,
                },
            }
        ),
        encoding="utf-8",
    )

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"

    write_tool(
        status_tool,
        f"""#!/usr/bin/env python3
import json
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
payload = {{
        "state": "installed",
        "devices": ["AK Virtual Camera"],
        "enabled": True,
        "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60],
    }} if state == "installed" else {{
        "state": "not_installed",
        "devices": [],
        "enabled": False,
        "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60],
    }}
print(json.dumps(payload))
""",
    )
    write_tool(
        list_devices_tool,
        f"""#!/usr/bin/env python3
import json
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
devices = ["AK Virtual Camera"] if state == "installed" else []
print(json.dumps({{"devices": devices}}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--framebus-roundtrip-json",
            str(framebus_json),
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert '"ipc_probe_present": true' in completed.stdout


def test_macos_smoke_tool_prefers_pending_approval_install_result_for_status_after_install(
    tmp_path,
) -> None:
    output_json = tmp_path / "smoke-report.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "install_failed",
    "devices": [],
    "enabled": False,
    "approval_required": False,
    "last_error": "system extension status query timed out",
}))
""",
    )
    write_tool(
        install_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "install_pending_approval",
    "devices": [],
    "enabled": False,
    "approval_required": False,
    "device_prefix": "AKVC Demo",
    "shared_memory_name": "/akvc-frames-v1",
    "ipc_transport": "shared_memory_ringbuffer",
    "bundle_path": "/tmp/build/Amaran Desktop.app",
    "extension_identifier": "com.sidus.amaran-desktop.cameraextension",
    "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
    "supported_frame_rates": [30, 60],
    "last_error": "system extension status query timed out",
}))
""",
    )
    write_tool(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": []}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--name",
            "AKVC Demo",
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--disable-auto-package",
            "--run-install",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["install"]["phase"] == "pending_approval"
    assert payload["install"]["start_blocker_code"] == "approval_required"
    assert payload["status_after_install"]["phase"] == "pending_approval"
    assert payload["status_after_install"]["start_blocker_code"] == "approval_required"


def test_macos_smoke_tool_runs_direct_push_demo_when_requested(tmp_path) -> None:
    output_json = tmp_path / "smoke-report.json"
    device_name_file = tmp_path / "device-name.txt"
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    direct_sender_library = tmp_path / "libakvc-macos-direct-sender.dylib"
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("", encoding="utf-8")
    direct_sender_library.write_text("", encoding="utf-8")

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    direct_push_tool = tmp_path / "direct-push-demo.py"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
}))
""",
    )
    write_tool(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": ["AK Virtual Camera"]}))
""",
    )
    write_tool(
        direct_push_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--frames" in args
assert args[args.index("--frames") + 1] == "9"
assert "--app-bundle" in args
assert args[args.index("--app-bundle") + 1].endswith("Amaran Desktop.app")
assert "--app-executable" in args
assert args[args.index("--app-executable") + 1].endswith("/Contents/MacOS/Amaran Desktop")
assert "--direct-sender-library" in args
assert args[args.index("--direct-sender-library") + 1].endswith("libakvc-macos-direct-sender.dylib")
assert "--frame-kind" in args
assert args[args.index("--frame-kind") + 1] == "qimage-bgra"
assert "--entrypoint" in args
assert args[args.index("--entrypoint") + 1] == "send-widget"
assert "--allow-shared-memory-fallback" in args
assert "--request-camera-access" in args
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "direct-push", "python_entrypoint_kind": "push_frame", "sdk_direct_push_used": True, "backend_name": "direct_sender", "using_direct_sender": True, "requested_camera_access": True, "requested_camera_access_snapshot": {"camera_access_status": "authorized", "environment_device_enumeration_empty": False}, "requested_frame_kind": "qimage-bgra", "requested_entrypoint": "send-widget", "requested_frames": 9, "frames_sent": 9}), encoding="utf-8")
print("direct-push-ok")
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--direct-push-demo-tool",
            str(direct_push_tool),
            "--direct-push-frames",
            "9",
            "--direct-push-frame-kind",
            "qimage-bgra",
            "--direct-push-entrypoint",
            "send-widget",
            "--direct-push-allow-shared-memory-fallback",
            "--host-bundle",
            str(host_bundle),
            "--host-executable",
            str(host_executable),
            "--direct-sender-library",
            str(direct_sender_library),
            "--direct-push-request-camera-access",
            "--run-direct-push-demo",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["direct_push_demo"]["attempted"] is True
    assert payload["direct_push_demo"]["skipped"] is False
    assert payload["direct_push_demo"]["returncode"] == 0
    assert payload["direct_push_demo"]["request"] == {
        "requested_frames": 9,
        "requested_frame_kind": "qimage-bgra",
        "requested_entrypoint": "send-widget",
        "allow_shared_memory_fallback": True,
        "requested_camera_access": True,
    }
    assert payload["direct_push_demo"]["payload"]["mode"] == "direct-push"
    assert payload["direct_push_demo"]["payload"]["python_entrypoint_kind"] == "push_frame"
    assert payload["direct_push_demo"]["payload"]["requested_frame_kind"] == "qimage-bgra"
    assert payload["direct_push_demo"]["payload"]["requested_entrypoint"] == "send-widget"
    assert payload["direct_push_demo"]["payload"]["sdk_direct_push_used"] is True
    assert payload["direct_push_demo"]["payload"]["backend_name"] == "direct_sender"
    assert payload["direct_push_demo"]["payload"]["using_direct_sender"] is True
    assert payload["direct_push_demo"]["payload"]["requested_camera_access"] is True
    assert payload["direct_push_demo"]["payload"]["requested_camera_access_snapshot"]["camera_access_status"] == "authorized"
    assert payload["direct_push_demo"]["payload"]["requested_frames"] == 9
    assert payload["direct_push_demo"]["payload"]["frames_sent"] == 9


def test_macos_smoke_tool_skips_direct_push_demo_when_start_not_ready(tmp_path) -> None:
    output_json = tmp_path / "smoke-report.json"
    device_name_file = tmp_path / "device-name.txt"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
    "ipc_probe_present": True,
    "ipc_ready": False,
    "ipc_environment_blocked": True,
    "ipc_last_error": "probe status=open_failed; direct_open_errno=13",
    "ipc_direct_open_errno": 13,
}))
""",
    )
    write_tool(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": ["AK Virtual Camera"]}))
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--run-direct-push-demo",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["direct_push_demo"]["attempted"] is False
    assert payload["direct_push_demo"]["skipped"] is True
    assert payload["direct_push_demo"]["skip_reason"] == "ipc_environment_blocked"
    assert payload["direct_push_demo"]["request"] == {
        "requested_frames": None,
        "requested_frame_kind": None,
        "requested_entrypoint": None,
        "allow_shared_memory_fallback": False,
        "requested_camera_access": False,
    }


def test_macos_smoke_tool_preserves_probe_payload_when_direct_push_fails(tmp_path) -> None:
    output_json = tmp_path / "smoke-report.json"
    device_name_file = tmp_path / "device-name.txt"
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    direct_sender_library = tmp_path / "libakvc-macos-direct-sender.dylib"
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("", encoding="utf-8")
    direct_sender_library.write_text("", encoding="utf-8")

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    direct_push_tool = tmp_path / "direct-push-demo.py"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
    "ipc_probe_present": True,
    "ipc_ready": True,
}))
""",
    )
    write_tool(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": ["AK Virtual Camera"]}))
""",
    )
    write_tool(
        direct_push_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
report = Path(args[args.index("--report-json") + 1])
report.parent.mkdir(parents=True, exist_ok=True)
if "--probe-only" in args:
    report.write_text(json.dumps({
        "mode": "direct-push",
        "direct_only": True,
        "probe_only": True,
        "camera_name": args[args.index("--name") + 1],
        "direct_sender_last_error": "camera device not found: AKVC Smoke",
        "error": "camera device not found: AKVC Smoke",
        "direct_sender_device_snapshot": {
            "all_devices": [],
            "avfoundation_devices": [],
            "cmio_devices": [],
            "camera_access_status": "denied",
            "environment_device_enumeration_empty": True,
        },
    }), encoding="utf-8")
    raise SystemExit(0)
raise SystemExit(2)
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_smoke.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--direct-push-demo-tool",
            str(direct_push_tool),
            "--host-bundle",
            str(host_bundle),
            "--host-executable",
            str(host_executable),
            "--direct-sender-library",
            str(direct_sender_library),
            "--run-direct-push-demo",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["direct_push_demo"]["attempted"] is True
    assert payload["direct_push_demo"]["skipped"] is False
    assert payload["direct_push_demo"]["returncode"] == 2
    assert payload["direct_push_demo"]["payload"]["probe_only"] is True
    assert payload["direct_push_demo"]["payload"]["error"] == "camera device not found: AKVC Smoke"
    assert payload["direct_push_demo"]["payload"]["direct_sender_device_snapshot"]["camera_access_status"] == "denied"
    assert payload["direct_push_demo"]["payload"]["direct_sender_device_snapshot"]["environment_device_enumeration_empty"] is True
    assert payload["direct_push_demo"]["probe_payload"]["probe_only"] is True
