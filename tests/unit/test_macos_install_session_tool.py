# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS install-session helper."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macos_install_session_tool_exists_and_declares_expected_options() -> None:
    script = ROOT / "tools" / "macos_install_session.py"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "DefaultMacInstallerService" in text
    assert "--name" in text
    assert "--sync-ipc-tool" in text
    assert "--pkg-path" in text
    assert "--app-bundle" in text
    assert "--app-executable" in text
    assert "--host-bundle" in text
    assert "--host-executable" in text
    assert "--direct-sender-library" in text
    assert "--installer-executable" in text
    assert "--framebus-roundtrip-json" in text
    assert "--direct-push-demo-tool" in text
    assert "--direct-push-frames" in text
    assert "--run-direct-push-demo" in text
    assert "--direct-sender-object-demo-tool" in text
    assert "--direct-sender-object-frames" in text
    assert "--run-direct-sender-object-demo" in text
    assert "--disable-auto-package" in text
    assert "--run-uninstall" in text
    assert "--output" in text
    assert "ipc_probe_present" in text
    assert "ipc_direct_open_errno" in text
    assert "start_blocker_code" in text
    assert "host_gatekeeper_allowed" in text
    assert "host_notarization_missing" in text
    assert "system_extension_registered" in text
    assert "system_extension_registry_summary" in text
    assert "install_command_notarization_missing" in text
    assert '"sync_ipc"' in text


def test_macos_install_session_tool_runs_pkg_install_and_uninstall_roundtrip(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("not_installed", encoding="utf-8")
    output_json = tmp_path / "install-session.json"
    device_name_file = tmp_path / "device-name.txt"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    pkg_path.write_text("pkg", encoding="utf-8")
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    installer_tool = tmp_path / "fake-installer"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"

    write_tool(
        status_tool,
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
device_name = Path(os.environ["AKVC_DEVICE_NAME_FILE"]).read_text(encoding="utf-8").strip()
payload = {{
    "state": "installed" if state == "installed" else "not_installed",
    "devices": [device_name] if state == "installed" else [],
    "device_prefix": device_name,
    "enabled": state == "installed",
    "shared_memory_name": "/akvc-frames-v1",
    "bundle_path": {str(host_bundle)!r},
    "host_signature": "Developer ID Application",
    "host_team_identifier": "TEAM123456",
    "host_codesign_summary": "Signature=Developer ID Application; TeamIdentifier=TEAM123456",
    "host_gatekeeper_allowed": True,
    "host_gatekeeper_summary": "accepted; source=Notarized Developer ID",
    "host_distribution_summary": "stapler validate passed",
    "host_notarization_missing": False,
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
    write_tool(
        uninstall_tool,
        f"""#!/usr/bin/env python3
from pathlib import Path
Path({str(state_file)!r}).write_text("not_installed", encoding="utf-8")
""",
    )
    write_tool(
        sync_ipc_tool,
        """#!/usr/bin/env python3
import json
import os
print(json.dumps({
    "shared_memory_name": os.environ.get("AKVC_MACOS_SHM_NAME"),
    "ipc_transport": "shared_memory_ringbuffer",
}))
""",
    )
    write_tool(
        installer_tool,
        f"""#!/usr/bin/env python3
from pathlib import Path
bundle = Path({str(host_bundle)!r})
exe = bundle / "Contents" / "MacOS" / "akvc-host"
exe.parent.mkdir(parents=True, exist_ok=True)
exe.write_text("host", encoding="utf-8")
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_install_session.py"),
            "--name",
            "AKVC Demo",
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--uninstall-tool",
            str(uninstall_tool),
            "--sync-ipc-tool",
            str(sync_ipc_tool),
            "--pkg-path",
            str(pkg_path),
            "--app-bundle",
            str(host_bundle),
            "--installer-executable",
            str(installer_tool),
            "--run-uninstall",
            "--poll-interval-seconds",
            "0",
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
    assert device_name_file.read_text(encoding="utf-8").strip() == "AKVC Demo"
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["requested_camera_name"] == "AKVC Demo"
    assert payload["pre_status"]["state"] == "not_installed"
    assert payload["pre_status"]["phase"] == ""
    assert payload["pre_status"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["pre_status"]["host_gatekeeper_allowed"] is True
    assert payload["pre_status"]["host_notarization_missing"] is False
    assert payload["pre_status"]["supported_frame_rates"] == [30, 60]
    assert payload["pre_status"]["start_blocker_code"] == "not_installed"
    assert payload["install"]["success"] is True
    assert payload["install"]["phase"] == "installed_visible"
    assert payload["install"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["install"]["host_signature"] == "Developer ID Application"
    assert payload["install"]["host_distribution_summary"] == "stapler validate passed"
    assert payload["install"]["supported_frame_rates"] == [30, 60]
    assert payload["install"]["start_blocker_code"] == "ready"
    assert payload["install"]["device_prefix"] == "AKVC Demo"
    assert payload["post_status"]["state"] == "installed"
    assert payload["post_status"]["phase"] == "installed_visible"
    assert payload["post_status"]["device_prefix"] == "AKVC Demo"
    assert payload["post_status"]["host_team_identifier"] == "TEAM123456"
    assert payload["post_status"]["supported_frame_rates"] == [30, 60]
    assert payload["post_status"]["start_blocker_code"] == "ready"
    assert payload["sync_ipc"]["supported"] is True
    assert payload["sync_ipc"]["success"] is True
    assert payload["sync_ipc"]["phase"] == "sync_command_succeeded"
    assert payload["sync_ipc"]["shared_memory_name"] == str(payload["post_status"]["shared_memory_name"])
    assert payload["sync_ipc"]["ipc_transport"] == "shared_memory_ringbuffer"
    assert payload["uninstall"]["success"] is True
    assert payload["uninstall"]["phase"] == "uninstalled"
    assert payload["uninstall"]["state"] == "not_installed"
    assert payload["uninstall"]["returncode"] == 0
    assert payload["status_after_uninstall"]["state"] == "not_installed"


def test_macos_install_session_tool_surfaces_pkg_install_failure(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("not_installed", encoding="utf-8")
    output_json = tmp_path / "install-session.json"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    pkg_path.write_text("pkg", encoding="utf-8")
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    installer_tool = tmp_path / "fake-installer"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"state": "not_installed", "devices": [], "enabled": False}))
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
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": []}))
""",
    )
    write_tool(
        installer_tool,
        """#!/usr/bin/env python3
import sys
print("authentication failed", file=sys.stderr)
sys.exit(1)
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_install_session.py"),
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--pkg-path",
            str(pkg_path),
            "--app-bundle",
            str(host_bundle),
            "--installer-executable",
            str(installer_tool),
            "--poll-interval-seconds",
            "0",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["install"]["success"] is False
    assert payload["install"]["phase"] == "timeout_waiting_for_install"
    assert payload["install"]["start_blocker_code"] == "waiting_for_install"


def test_macos_install_session_tool_merges_framebus_roundtrip_status(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("installed", encoding="utf-8")
    output_json = tmp_path / "install-session.json"
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
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
    "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
    "supported_frame_rates": [30, 60],
}))
""",
    )
    write_tool(
        install_tool,
        """#!/usr/bin/env python3
pass
""",
    )
    write_tool(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": ["AK Virtual Camera"]}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_install_session.py"),
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--framebus-roundtrip-json",
            str(framebus_json),
            "--poll-interval-seconds",
            "0",
            "--output",
            str(output_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["pre_status"]["ipc_probe_present"] is True
    assert payload["pre_status"]["ipc_ready"] is False
    assert payload["pre_status"]["ipc_environment_blocked"] is True
    assert payload["pre_status"]["ipc_direct_open_errno"] == 13
    assert payload["pre_status"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["pre_status"]["supported_frame_rates"] == [30, 60]
    assert payload["pre_status"]["ipc_probe_path"] == str(framebus_json)
    assert payload["install"]["success"] is True
    assert payload["install"]["phase"] == "installed_visible"
    assert payload["install"]["ipc_probe_present"] is True
    assert payload["install"]["ipc_ready"] is False
    assert payload["install"]["ipc_environment_blocked"] is True
    assert payload["install"]["ipc_direct_open_errno"] == 13
    assert payload["install"]["supported_frame_rates"] == [30, 60]
    assert payload["install"]["start_ready"] is False
    assert payload["install"]["start_blocker_code"] == "ipc_environment_blocked"
    assert payload["post_status"]["ipc_probe_present"] is True
    assert payload["post_status"]["ipc_environment_blocked"] is True
    assert payload["post_status"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["post_status"]["start_blocker_code"] == "ipc_environment_blocked"


def test_macos_install_session_tool_prefers_pending_approval_result_for_post_status(tmp_path) -> None:
    output_json = tmp_path / "install-session.json"

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
            str(ROOT / "tools" / "macos_install_session.py"),
            "--name",
            "AKVC Demo",
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--disable-auto-package",
            "--poll-interval-seconds",
            "0",
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
    assert payload["post_status"]["phase"] == "pending_approval"
    assert payload["post_status"]["start_blocker_code"] == "approval_required"


def test_macos_install_session_tool_prefers_pending_approval_result_when_post_status_is_unknown(
    tmp_path,
) -> None:
    output_json = tmp_path / "install-session.json"
    state_file = tmp_path / "state.txt"
    state_file.write_text("before", encoding="utf-8")

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
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
if state == "after":
    print(json.dumps({{
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
    }}))
else:
    print(json.dumps({{
        "state": "install_failed",
        "devices": [],
        "enabled": False,
        "approval_required": False,
        "last_error": "system extension status query timed out",
    }}))
""",
    )
    write_tool(
        install_tool,
        f"""#!/usr/bin/env python3
import json
from pathlib import Path
Path({str(state_file)!r}).write_text("after", encoding="utf-8")
print(json.dumps({{
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
}}))
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
            str(ROOT / "tools" / "macos_install_session.py"),
            "--name",
            "AKVC Demo",
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--disable-auto-package",
            "--poll-interval-seconds",
            "0",
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
    assert payload["post_status"]["state"] == "install_pending_approval"
    assert payload["post_status"]["shared_memory_name"] == "/akvc-frames-v1"


def test_macos_install_session_tool_runs_direct_push_demo_when_requested(tmp_path) -> None:
    output_json = tmp_path / "install-session.json"
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
    install_tool = tmp_path / "akvc-macos-install"
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
        install_tool,
        """#!/usr/bin/env python3
pass
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
assert args[args.index("--frames") + 1] == "7"
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
output.write_text(json.dumps({"mode": "direct-push", "python_entrypoint_kind": "push_frame", "requested_frame_kind": "qimage-bgra", "requested_entrypoint": "send-widget", "sdk_direct_push_used": True, "backend_name": "direct_sender", "using_direct_sender": True, "requested_camera_access": True, "requested_camera_access_snapshot": {"camera_access_status": "authorized", "environment_device_enumeration_empty": False}, "requested_frames": 7, "frames_sent": 7}), encoding="utf-8")
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_install_session.py"),
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--direct-push-demo-tool",
            str(direct_push_tool),
            "--direct-push-frames",
            "7",
            "--direct-push-frame-kind",
            "qimage-bgra",
            "--direct-push-entrypoint",
            "send-widget",
            "--direct-push-allow-shared-memory-fallback",
            "--app-bundle",
            str(host_bundle),
            "--app-executable",
            str(host_executable),
            "--direct-sender-library",
            str(direct_sender_library),
            "--direct-push-request-camera-access",
            "--run-direct-push-demo",
            "--poll-interval-seconds",
            "0",
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
        "requested_frames": 7,
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
    assert payload["direct_push_demo"]["payload"]["requested_frames"] == 7
    assert payload["direct_push_demo"]["payload"]["frames_sent"] == 7


def test_macos_install_session_tool_preserves_probe_payload_when_direct_push_fails(tmp_path) -> None:
    output_json = tmp_path / "install-session.json"
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
    install_tool = tmp_path / "akvc-macos-install"
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
        install_tool,
        """#!/usr/bin/env python3
pass
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
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
if "--probe-only" in args:
    output.write_text(json.dumps({
        "mode": "direct-push",
        "direct_only": True,
        "probe_only": True,
        "camera_name": args[args.index("--name") + 1],
        "direct_sender_last_error": "camera device not found: AKVC Direct",
        "error": "camera device not found: AKVC Direct",
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
            str(ROOT / "tools" / "macos_install_session.py"),
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--direct-push-demo-tool",
            str(direct_push_tool),
            "--app-bundle",
            str(host_bundle),
            "--app-executable",
            str(host_executable),
            "--direct-sender-library",
            str(direct_sender_library),
            "--run-direct-push-demo",
            "--poll-interval-seconds",
            "0",
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
    assert payload["direct_push_demo"]["payload"]["error"] == "camera device not found: AKVC Direct"
    assert payload["direct_push_demo"]["payload"]["direct_sender_device_snapshot"]["camera_access_status"] == "denied"
    assert payload["direct_push_demo"]["payload"]["direct_sender_device_snapshot"]["environment_device_enumeration_empty"] is True
    assert payload["direct_push_demo"]["probe_payload"]["probe_only"] is True
