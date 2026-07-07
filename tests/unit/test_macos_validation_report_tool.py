# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation report helper."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from tools import macos_validation_report as report_tool


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = ROOT / "docs" / "macos" / "manual_validation_results.example.json"


def _pass_target(app_id: str) -> dict[str, object]:
    return {
        "id": app_id,
        "reviewed": True,
        "result": "pass",
        "evidence": {
            "device_listed": True,
            "device_selected": True,
            "preview_visible": True,
            "screenshot": f"artifacts/{app_id}.png",
        },
    }


def test_macos_validation_report_tool_exists_and_declares_expected_options() -> None:
    script = ROOT / "tools" / "macos_validation_report.py"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "DefaultMacInstallerService" in text
    assert "--name" in text
    assert "--status-tool" in text
    assert "--list-devices-tool" in text
    assert "--install-tool" in text
    assert "--uninstall-tool" in text
    assert "--sync-ipc-tool" in text
    assert "--app-bundle" in text
    assert "--app-executable" in text
    assert "--host-bundle" in text
    assert "--host-executable" in text
    assert "--pkg-path" in text
    assert "--installer-executable" in text
    assert "--disable-auto-package" in text
    assert "--preflight-json" in text
    assert "--release-diagnostics-json" in text
    assert "--install-session-json" in text
    assert "--smoke-json" in text
    assert "--framebus-roundtrip-json" in text
    assert "--status-binary-check-json" in text
    assert "--list-devices-binary-check-json" in text
    assert "--benchmark-json" in text
    assert "--demo-json" in text
    assert "--manual-results" in text
    assert "--write-manual-template" in text
    assert "--run-install" in text
    assert "--output" in text
    assert "verification_targets" in text
    assert "readiness" in text
    assert "runtime_assets" in text
    assert "runtime_topology_kind" in text
    assert "runtime_snapshot" in text
    assert "runtime_frame_path" in text
    assert "runtime_host_role" in text
    assert "runtime_host_in_frame_hot_path" in text
    assert "runtime_dedicated_host_daemon_required" in text
    assert "runtime_data_plane" in text
    assert "runtime_control_plane" in text
    assert "install_command_notarization_missing" in text
    assert "system_extension_registered" in text
    assert "summary" in text


def test_macos_validation_report_tool_run_install_wraps_commands_with_host_overrides(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("not_installed", encoding="utf-8")
    output_json = tmp_path / "validation-report.json"
    manual_template = tmp_path / "manual-results.template.json"
    device_name_file = tmp_path / "device-name.txt"

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
device_name = Path(os.environ["AKVC_DEVICE_NAME_FILE"]).read_text(encoding="utf-8").strip()
print(json.dumps({{
    "state": "installed" if state == "installed" else "not_installed",
    "devices": [device_name] if state == "installed" else [],
    "device_prefix": device_name,
    "enabled": state == "installed",
}}))
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
device_name = Path(os.environ["AKVC_DEVICE_NAME_FILE"]).read_text(encoding="utf-8").strip()
print(json.dumps({{"devices": [device_name] if state == "installed" else [], "device_prefix": device_name}}))
""",
    )

    env = dict(os.environ)
    env["AKVC_DEVICE_NAME_FILE"] = str(device_name_file)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--name",
            "AKVC Demo",
            "--status-tool",
            str(status_tool),
            "--install-tool",
            str(install_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--host-bundle",
            str(host_bundle),
            "--run-install",
            "--write-manual-template",
            str(manual_template),
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
    assert payload["install"]["success"] is True
    assert payload["install"]["phase"] == "installed_visible"
    assert payload["install"]["device_prefix"] == "AKVC Demo"
    assert payload["summary"]["install_success"] is True
    assert payload["summary"]["status_start_blocker_code"] == "not_installed"
    assert manual_template.is_file()


def test_runtime_assets_snapshot_reports_resolved_and_packaged_assets(tmp_path, monkeypatch) -> None:
    packaged_dir = tmp_path / "runtime" / "macos"
    packaged_dir.mkdir(parents=True)
    for name in report_tool.PACKAGED_MACOS_RUNTIME_ASSETS:
        (packaged_dir / name).write_text(name, encoding="utf-8")

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    devices_tool = tmp_path / "akvc-macos-list-devices"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    direct_sender_library = tmp_path / "libakvc-macos-direct-sender.dylib"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    for path in (
        status_tool,
        install_tool,
        devices_tool,
        uninstall_tool,
        sync_ipc_tool,
        direct_sender_library,
        pkg_path,
    ):
        path.write_text(path.name, encoding="utf-8")
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("host", encoding="utf-8")

    monkeypatch.setattr(report_tool, "PACKAGED_MACOS_RUNTIME_DIR", packaged_dir)
    monkeypatch.setattr(report_tool, "find_macos_uninstall_tool", lambda explicit=None: uninstall_tool)
    monkeypatch.setattr(report_tool, "find_macos_sync_ipc_tool", lambda explicit=None: sync_ipc_tool)
    monkeypatch.setattr(
        report_tool,
        "find_macos_direct_sender_library",
        lambda explicit=None: direct_sender_library,
    )
    monkeypatch.setattr(report_tool, "find_macos_pkg", lambda explicit=None: pkg_path)

    payload = report_tool._runtime_assets_snapshot(
        status_tool=status_tool,
        install_tool=install_tool,
        devices_tool=devices_tool,
        app_bundle=str(host_bundle),
        app_executable=str(host_executable),
        package_install_command=["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"],
        auto_install_package=False,
    )

    assert payload["resolved_assets"]["status_tool"] == str(status_tool)
    assert payload["resolved_assets"]["install_tool"] == str(install_tool)
    assert payload["resolved_assets"]["devices_tool"] == str(devices_tool)
    assert payload["resolved_assets"]["uninstall_tool"] == str(uninstall_tool)
    assert payload["resolved_assets"]["sync_ipc_tool"] == str(sync_ipc_tool)
    assert payload["resolved_assets"]["direct_sender_library"] == str(direct_sender_library)
    assert payload["resolved_assets"]["pkg"] == str(pkg_path)
    assert payload["provenance"]["host_bundle"] == str(host_bundle)
    assert payload["provenance"]["host_executable"] == str(host_executable)
    assert payload["provenance"]["extension_bundle"] == str(
        host_bundle / "Contents" / "Library" / "SystemExtensions" / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    assert payload["provenance"]["package_install_command"] == [
        "/usr/sbin/installer",
        "-pkg",
        str(pkg_path),
        "-target",
        "/",
    ]
    assert payload["provenance"]["auto_install_package"] is False
    assert payload["summary"]["status_tool_resolved"] is True
    assert payload["summary"]["install_tool_resolved"] is True
    assert payload["summary"]["devices_tool_resolved"] is True
    assert payload["summary"]["uninstall_tool_resolved"] is True
    assert payload["summary"]["sync_ipc_tool_resolved"] is True
    assert payload["summary"]["direct_sender_library_resolved"] is True
    assert payload["summary"]["pkg_resolved"] is True
    assert payload["summary"]["host_bundle_configured"] is True
    assert payload["summary"]["host_executable_configured"] is True
    assert payload["summary"]["extension_bundle_derived"] is True
    assert payload["summary"]["package_install_command_present"] is True
    assert payload["summary"]["auto_install_package"] is False
    assert payload["summary"]["packaged_assets_present"] is True
    assert payload["summary"]["packaged_tools_present"] is True
    assert payload["summary"]["packaged_pkg_present"] is True
    assert payload["summary"]["sync_ipc_tool_resolved"] is True


def test_validation_report_summary_surfaces_runtime_release_product_set_consistency() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": True, "blocker_code": "ready"},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload=None,
        release_diagnostics_payload={
            "summary": {
                "release_artifacts_present": True,
                "pkg_includes_extension_payload": True,
                "pkg_payload_appledouble_clean": True,
                "host_embeds_extension_bundle": True,
            },
            "artifacts": {
                "app_bundle": {"path": "/Applications/Amaran Desktop.app"},
                "extension_bundle": {
                    "path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension"
                },
                "sync_ipc_tool": {"path": "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc"},
                "pkg": {"path": "/tmp/VirtualCamera.pkg"},
            },
        },
        runtime_assets_payload={
            "resolved_assets": {
                "sync_ipc_tool": "/tmp/runtime/akvc-macos-sync-ipc",
                "pkg": "/tmp/VirtualCamera.pkg",
            },
            "provenance": {
                "host_bundle": "/Applications/Amaran Desktop.app",
                "extension_bundle": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
            },
            "summary": {},
        },
        status_payload={},
        install_session_payload=None,
        smoke_payload=None,
        framebus_roundtrip_payload=None,
        status_binary_check_payload=None,
        list_devices_binary_check_payload=None,
        install_payload=None,
    )

    assert summary["release_app_bundle_path"] == "/Applications/Amaran Desktop.app"
    assert summary["release_extension_bundle_path"] == (
        "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    assert summary["release_sync_ipc_tool_path"] == "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc"
    assert summary["release_pkg_path"] == "/tmp/VirtualCamera.pkg"
    assert summary["runtime_release_host_bundle_identity_consistent"] is True
    assert summary["runtime_release_extension_bundle_identity_consistent"] is True
    assert summary["runtime_release_sync_ipc_tool_identity_consistent"] is True
    assert summary["runtime_release_pkg_identity_consistent"] is True
    assert summary["runtime_release_host_bundle_path_equal"] is True
    assert summary["runtime_release_extension_bundle_path_equal"] is True
    assert summary["runtime_release_sync_ipc_tool_path_equal"] is False
    assert summary["runtime_release_pkg_path_equal"] is True
    assert summary["runtime_release_product_identity_consistent"] is True
    assert summary["runtime_release_product_path_equal"] is False
    assert summary["runtime_topology_kind"] == "camera_extension_direct_framebus"
    assert summary["runtime_host_role"] == "container_activation_command_bridge"
    assert summary["runtime_host_in_frame_hot_path"] is False
    assert summary["runtime_dedicated_host_daemon_required"] is False
    assert summary["runtime_container_app_configured"] is True
    assert summary["runtime_data_plane"] == "shared_memory_ringbuffer"
    assert summary["runtime_control_plane"] == "host_activation_plus_sync_ipc"
    assert summary["runtime_frame_path"] == (
        "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app"
    )


def test_manual_validation_results_example_file_exists() -> None:
    payload = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))

    assert EXAMPLE_JSON.is_file()
    assert set(payload) == {
        "zoom",
        "teams",
        "google_meet",
        "obs",
        "quicktime",
        "facetime",
    }
    assert payload["zoom"]["result"] in {"pass", "fail", "pending", "skipped"}
    assert isinstance(payload["zoom"]["validated"], bool)
    assert payload["zoom"]["evidence"] == {
        "device_listed": False,
        "device_selected": False,
        "preview_visible": False,
        "screenshot": "",
    }


def test_macos_validation_report_tool_merges_status_benchmark_and_manual_results(tmp_path) -> None:
    state_file = tmp_path / "state.txt"
    state_file.write_text("installed", encoding="utf-8")

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    benchmark_json = tmp_path / "benchmark.json"
    demo_json = tmp_path / "demo.json"
    preflight_json = tmp_path / "preflight.json"
    release_diagnostics_json = tmp_path / "release-diagnostics.json"
    install_session_json = tmp_path / "install-session.json"
    smoke_json = tmp_path / "smoke.json"
    framebus_roundtrip_json = tmp_path / "framebus-roundtrip.json"
    status_binary_check_json = tmp_path / "status-binary-check.json"
    list_devices_binary_check_json = tmp_path / "list-devices-binary-check.json"
    manual_results = tmp_path / "manual-results.json"
    output_json = tmp_path / "validation-report.json"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
    "approval_required": False,
    "bundle_path": "/Applications/AKVC.app",
    "extension_identifier": "com.sidus.amaran-desktop.cameraextension",
    "shared_memory_name": "/akvc-status",
    "mach_service_name": "com.sidus.amaran-desktop.cameraextension",
    "ipc_transport": "shared_memory_ringbuffer",
    "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
    "supported_frame_rates": [30, 60]
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

    benchmark_json.write_text(
        json.dumps(
            {
                "scenario": {"width": 1920, "height": 1080, "fps": 60.0},
                "metrics": {"cpu_percent": 7.5, "actual_fps": 59.2},
                "acceptance": {"fps_target_met": True, "cpu_target_met": True},
            }
        ),
        encoding="utf-8",
    )
    demo_json.write_text(
        json.dumps(
            {
                "mode": "provider",
                "python_entrypoint_kind": "create_pyside6_streamer.start_provider_stream",
                "sdk_streamer_factory_used": True,
                "sdk_latest_provider_factory_used": False,
                "sdk_direct_push_used": False,
                "width": 1920,
                "height": 1080,
                "fps": 60.0,
                "duration": 5.0,
                "camera_name": "AKVC Demo",
            }
        ),
        encoding="utf-8",
    )
    preflight_json.write_text(
        json.dumps(
            {
                "readiness": {
                    "can_generate_project": True,
                    "can_build_native": True,
                    "can_package": True,
                    "can_sign": False,
                    "can_notarize": False,
                    "can_staple": True,
                }
            }
        ),
        encoding="utf-8",
    )
    release_diagnostics_json.write_text(
        json.dumps(
            {
                "summary": {
                    "release_artifacts_present": True,
                    "universal2_ready": True,
                    "app_signed": True,
                    "app_gatekeeper_accepted": True,
                    "app_stapled": True,
                    "extension_signed": True,
                    "pkg_signed": False,
                    "pkg_gatekeeper_accepted": False,
                    "pkg_stapled": False,
                    "pkg_install_location_expected": True,
                    "pkg_identifier_expected": True,
                    "pkg_includes_extension_payload": True,
                    "pkg_payload_appledouble_clean": True,
                    "host_bundle_identifier_expected": True,
                    "extension_bundle_identifier_expected": True,
                    "minimum_system_version_expected": True,
                    "host_embeds_extension_bundle": True,
                }
            }
        ),
        encoding="utf-8",
    )
    smoke_json.write_text(
        json.dumps(
            {
                "install": {"success": True, "phase": "installed_visible"},
                "uninstall": {"success": True, "phase": "uninstalled", "state": "not_installed", "returncode": 0},
            }
        ),
        encoding="utf-8",
    )
    framebus_roundtrip_json.write_text(
        json.dumps(
            {
                "producer_control": {"producer_seq": 1},
                "observed": {"direct_open_errno": 13},
                "consistency": {"all_checks_passed": False, "status_ok": False},
            }
        ),
        encoding="utf-8",
    )
    status_binary_check_json.write_text(
        json.dumps(
            {
                "consistency": {
                    "all_checks_passed": True,
                    "ipc_keys_present": True,
                },
                "payload": {
                    "ipc_environment_blocked": True,
                    "ipc_direct_open_errno": 13,
                },
            }
        ),
        encoding="utf-8",
    )
    list_devices_binary_check_json.write_text(
        json.dumps(
            {
                "consistency": {
                    "all_checks_passed": True,
                },
                "result": {
                    "device_prefix": "AK Virtual Camera",
                    "devices": ["AK Virtual Camera"],
                    "all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                },
                "override_prefix_case": {
                    "consistency": {
                        "all_checks_passed": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    install_session_json.write_text(
        json.dumps(
            {
                "install": {
                    "success": True,
                    "phase": "installed_visible",
                    "ipc_probe_present": True,
                    "ipc_ready": False,
                    "ipc_environment_blocked": True,
                    "ipc_direct_open_errno": 13,
                },
                "post_status": {
                    "state": "installed",
                    "phase": "installed_visible",
                    "ipc_probe_present": True,
                    "ipc_ready": False,
                    "ipc_environment_blocked": True,
                    "ipc_direct_open_errno": 13,
                },
                "uninstall": {"success": True, "phase": "uninstalled", "state": "not_installed", "returncode": 0},
            }
        ),
        encoding="utf-8",
    )
    manual_results.write_text(
        json.dumps(
            {
                "zoom": {"validated": True, "result": "pass", "notes": "preview visible"},
                "obs": {"validated": True, "result": "pass"},
                "facetime": {"validated": False, "result": "pending", "notes": "not tested yet"},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--benchmark-json",
            str(benchmark_json),
            "--demo-json",
            str(demo_json),
            "--preflight-json",
            str(preflight_json),
            "--release-diagnostics-json",
            str(release_diagnostics_json),
            "--install-session-json",
            str(install_session_json),
            "--smoke-json",
            str(smoke_json),
            "--framebus-roundtrip-json",
            str(framebus_roundtrip_json),
            "--status-binary-check-json",
            str(status_binary_check_json),
            "--list-devices-binary-check-json",
            str(list_devices_binary_check_json),
            "--manual-results",
            str(manual_results),
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
    assert payload["status"]["extension_identifier"] == "com.sidus.amaran-desktop.cameraextension"
    assert payload["summary"]["device_visible"] is True
    assert payload["summary"]["status_readiness_phase"] == "installed_visible"
    assert payload["summary"]["status_start_ready"] is True
    assert payload["summary"]["status_start_blocker_code"] == "ready"
    assert payload["summary"]["status_shared_memory_name"] == "/akvc-status"
    assert payload["summary"]["status_mach_service_name"] == "com.sidus.amaran-desktop.cameraextension"
    assert payload["summary"]["status_ipc_transport"] == "shared_memory_ringbuffer"
    assert payload["summary"]["validated_apps"] == 3
    assert payload["summary"]["passed_apps"] == 2
    assert payload["summary"]["failed_apps"] == 0
    assert payload["summary"]["pending_apps"] == 4
    assert payload["summary"]["skipped_apps"] == 0
    assert payload["summary"]["passed_app_ids"] == ["zoom", "obs"]
    assert payload["summary"]["reviewed_app_ids"] == ["facetime", "obs", "zoom"]
    assert payload["summary"]["failed_app_ids"] == []
    assert payload["summary"]["pending_app_ids"] == ["teams", "google_meet", "quicktime", "facetime"]
    assert payload["summary"]["skipped_app_ids"] == []
    assert payload["summary"]["unreviewed_app_ids"] == ["teams", "google_meet", "quicktime"]
    assert payload["summary"]["observed_target_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
        "zoom",
    ]
    assert payload["summary"]["missing_target_app_ids"] == []
    assert payload["summary"]["unexpected_target_app_ids"] == []
    assert payload["summary"]["target_app_ids_complete"] is True
    assert payload["summary"]["manual_validation_ready"] is False
    assert payload["summary"]["manual_validation_complete"] is False
    assert payload["summary"]["manual_validation_all_passed"] is False
    assert payload["summary"]["demo_present"] is True
    assert payload["summary"]["demo_mode"] == "provider"
    assert payload["summary"]["demo_mode_supported"] is True
    assert payload["summary"]["demo_width"] == 1920
    assert payload["summary"]["demo_height"] == 1080
    assert payload["summary"]["demo_fps"] == 60.0
    assert payload["summary"]["demo_duration"] == 5.0
    assert payload["summary"]["demo_camera_name"] == "AKVC Demo"
    assert payload["summary"]["demo_video_path"] is None
    assert payload["summary"]["demo_frame_source_kind"] is None
    assert payload["summary"]["demo_python_entrypoint_kind"] == "create_pyside6_streamer.start_provider_stream"
    assert payload["summary"]["demo_sdk_streamer_factory_used"] is True
    assert payload["summary"]["demo_sdk_latest_provider_factory_used"] is False
    assert payload["summary"]["demo_sdk_direct_push_used"] is False
    assert payload["summary"]["preflight_present"] is True
    assert payload["summary"]["release_diagnostics_present"] is True
    assert payload["summary"]["release_artifacts_present"] is True
    assert payload["summary"]["release_universal2_ready"] is True
    assert payload["summary"]["release_app_signed"] is True
    assert payload["summary"]["release_app_gatekeeper_accepted"] is True
    assert payload["summary"]["release_app_stapled"] is True
    assert payload["summary"]["release_extension_signed"] is True
    assert payload["summary"]["release_pkg_signed"] is False
    assert payload["summary"]["release_pkg_gatekeeper_accepted"] is False
    assert payload["summary"]["release_pkg_stapled"] is False
    assert payload["summary"]["release_pkg_install_location_expected"] is True
    assert payload["summary"]["release_pkg_identifier_expected"] is True
    assert payload["summary"]["release_pkg_includes_extension_payload"] is True
    assert payload["summary"]["release_pkg_payload_appledouble_clean"] is True
    assert payload["summary"]["release_host_bundle_identifier_expected"] is True
    assert payload["summary"]["release_extension_bundle_identifier_expected"] is True
    assert payload["summary"]["release_minimum_system_version_expected"] is True
    assert payload["summary"]["release_host_embeds_extension_bundle"] is True
    assert payload["summary"]["runtime_status_tool_resolved"] is True
    assert payload["summary"]["runtime_devices_tool_resolved"] is True
    assert isinstance(payload["summary"]["runtime_pkg_resolved"], bool)
    assert payload["summary"]["install_present"] is False
    assert payload["summary"]["install_success"] is None
    assert payload["summary"]["install_session_present"] is True
    assert payload["summary"]["install_session_success"] is True
    assert payload["summary"]["install_session_uninstall_success"] is True
    assert payload["summary"]["install_session_uninstall_phase"] == "uninstalled"
    assert payload["summary"]["install_session_uninstall_state"] == "not_installed"
    assert payload["summary"]["install_session_ipc_probe_present"] is True
    assert payload["summary"]["install_session_ipc_ready"] is False
    assert payload["summary"]["install_session_ipc_environment_blocked"] is True
    assert payload["summary"]["install_session_ipc_direct_open_errno"] == 13
    assert payload["summary"]["smoke_present"] is True
    assert payload["summary"]["smoke_install_success"] is True
    assert payload["summary"]["smoke_uninstall_success"] is True
    assert payload["summary"]["smoke_uninstall_phase"] == "uninstalled"
    assert payload["summary"]["smoke_uninstall_state"] == "not_installed"
    assert payload["summary"]["framebus_roundtrip_present"] is True
    assert payload["summary"]["framebus_roundtrip_passed"] is False
    assert payload["summary"]["framebus_roundtrip_direct_open_errno"] == 13
    assert payload["summary"]["framebus_roundtrip_environment_blocked"] is True
    assert payload["summary"]["framebus_roundtrip_producer_seq"] == 1
    assert payload["summary"]["framebus_roundtrip_producer_initialized"] is True
    assert payload["summary"]["status_binary_check_present"] is True
    assert payload["summary"]["status_binary_check_passed"] is True
    assert payload["summary"]["status_binary_check_ipc_keys_present"] is True
    assert payload["summary"]["status_binary_check_ipc_environment_blocked"] is True
    assert payload["summary"]["status_binary_check_ipc_direct_open_errno"] == 13
    assert payload["summary"]["list_devices_binary_check_present"] is True
    assert payload["summary"]["list_devices_binary_check_passed"] is True
    assert payload["summary"]["list_devices_binary_check_device_prefix"] == "AK Virtual Camera"
    assert payload["summary"]["list_devices_binary_check_filtered_device_count"] == 1
    assert payload["summary"]["list_devices_binary_check_total_device_count"] == 2
    assert payload["summary"]["list_devices_binary_check_override_no_match_ok"] is True
    assert payload["status"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["status"]["supported_frame_rates"] == [30, 60]
    assert payload["status"]["shared_memory_name"] == "/akvc-status"
    assert payload["status"]["mach_service_name"] == "com.sidus.amaran-desktop.cameraextension"
    assert payload["status"]["ipc_transport"] == "shared_memory_ringbuffer"
    assert "runtime_assets" in payload
    assert payload["readiness"]["phase"] == "installed_visible"
    assert payload["readiness"]["ready"] is True
    assert payload["readiness"]["blocker_code"] == "ready"
    assert "Zoom" in payload["readiness"]["steps"][0]
    assert "install_session" in payload
    assert "smoke" in payload
    assert "framebus_roundtrip" in payload
    assert "status_binary_check" in payload
    assert "list_devices_binary_check" in payload
    assert "resolved_assets" in payload["runtime_assets"]
    assert payload["summary"]["preflight_readiness"]["can_package"] is True
    assert payload["benchmark"]["metrics"]["cpu_percent"] == 7.5
    assert payload["demo"]["mode"] == "provider"
    assert payload["preflight"]["readiness"]["can_staple"] is True
    assert payload["release_diagnostics"]["summary"]["universal2_ready"] is True
    zoom = next(item for item in payload["verification_targets"] if item["id"] == "zoom")
    assert zoom["validated"] is True
    assert zoom["result"] == "pass"
    assert zoom["notes"] == "preview visible"
    facetime = next(item for item in payload["verification_targets"] if item["id"] == "facetime")
    assert facetime["validated"] is False
    assert facetime["result"] == "pending"


def test_macos_validation_report_tool_surfaces_install_snapshot_when_run_install_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    state_file = tmp_path / "state.txt"
    state_file.write_text("not_installed", encoding="utf-8")
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    output_json = tmp_path / "validation-report.json"

    write_tool(
        status_tool,
        f"""#!/usr/bin/env python3
import json
from pathlib import Path
state = Path({str(state_file)!r}).read_text(encoding="utf-8").strip()
payload = {{
    "state": "installed" if state == "installed" else "not_installed",
    "devices": ["AK Virtual Camera"] if state == "installed" else [],
    "enabled": state == "installed",
    "shared_memory_name": "/akvc-install" if state == "installed" else None,
    "mach_service_name": "com.sidus.amaran-desktop.cameraextension" if state == "installed" else None,
    "ipc_transport": "shared_memory_ringbuffer" if state == "installed" else None,
    "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12", "3840x2160@30/60 NV12"],
    "supported_frame_rates": [30, 60],
    "ipc_probe_present": state == "installed",
    "ipc_ready": state == "installed",
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

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
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
    assert payload["install"]["success"] is True
    assert payload["install"]["phase"] == "installed_visible"
    assert payload["install"]["enumerated_devices"] == ["AK Virtual Camera"]
    assert payload["install"]["supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["install"]["supported_frame_rates"] == [30, 60]
    assert payload["install"]["shared_memory_name"] == "/akvc-install"
    assert payload["install"]["mach_service_name"] == "com.sidus.amaran-desktop.cameraextension"
    assert payload["install"]["ipc_transport"] == "shared_memory_ringbuffer"
    assert payload["install"]["start_ready"] is True
    assert payload["install"]["start_blocker_code"] == "ready"
    assert payload["install"]["ipc_probe_present"] is True
    assert payload["install"]["ipc_ready"] is True
    assert payload["summary"]["install_present"] is True
    assert payload["summary"]["install_success"] is True
    assert payload["summary"]["install_phase"] == "installed_visible"
    assert payload["summary"]["install_start_ready"] is True
    assert payload["summary"]["install_start_blocker_code"] == "ready"
    assert payload["summary"]["install_shared_memory_name"] == "/akvc-install"
    assert payload["summary"]["install_mach_service_name"] == "com.sidus.amaran-desktop.cameraextension"
    assert payload["summary"]["install_ipc_transport"] == "shared_memory_ringbuffer"
    assert payload["summary"]["install_supported_formats"] == [
        "1280x720@30/60 NV12",
        "1920x1080@30/60 NV12",
        "3840x2160@30/60 NV12",
    ]
    assert payload["summary"]["install_supported_frame_rates"] == [30, 60]


def test_validation_report_summary_surfaces_target_app_result_ids() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": True, "blocker_code": "ready"},
        verification_targets=[
            {"id": "zoom", "reviewed": True, "result": "pass"},
            {"id": "teams", "reviewed": True, "result": "fail"},
            {"id": "google_meet", "reviewed": False, "result": "pending"},
            {"id": "obs", "reviewed": True, "result": "skipped"},
        ],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_payload=None,
        install_session_payload=None,
        smoke_payload=None,
        framebus_roundtrip_payload=None,
        status_binary_check_payload=None,
    )

    assert summary["validated_apps"] == 3
    assert summary["passed_apps"] == 1
    assert summary["failed_apps"] == 1
    assert summary["pending_apps"] == 1
    assert summary["skipped_apps"] == 1
    assert summary["passed_app_ids"] == ["zoom"]
    assert summary["reviewed_app_ids"] == ["obs", "teams", "zoom"]
    assert summary["failed_app_ids"] == ["teams"]
    assert summary["pending_app_ids"] == ["google_meet"]
    assert summary["skipped_app_ids"] == ["obs"]
    assert summary["unreviewed_app_ids"] == ["google_meet"]
    assert summary["observed_target_app_ids"] == ["google_meet", "obs", "teams", "zoom"]
    assert summary["missing_target_app_ids"] == ["facetime", "quicktime"]
    assert summary["unexpected_target_app_ids"] == []
    assert summary["target_app_ids_complete"] is False
    assert summary["manual_validation_complete"] is False
    assert summary["manual_validation_all_passed"] is False


def test_validation_report_summary_surfaces_manual_validation_readiness_and_completion() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": True, "blocker_code": "ready"},
        verification_targets=[
            _pass_target("zoom"),
            _pass_target("teams"),
            _pass_target("google_meet"),
            _pass_target("obs"),
            _pass_target("quicktime"),
            _pass_target("facetime"),
        ],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_payload=None,
        install_session_payload={
            "install": {"success": True},
            "post_status": {
                "ipc_environment_blocked": False,
            },
            "sync_ipc": {
                "supported": True,
                "success": True,
            },
        },
        smoke_payload=None,
        framebus_roundtrip_payload={
            "consistency": {"all_checks_passed": True},
            "environment_blocked": False,
        },
        status_binary_check_payload={
            "payload": {"ipc_environment_blocked": False},
        },
    )

    assert summary["manual_validation_ready"] is True
    assert summary["manual_validation_complete"] is True
    assert summary["manual_validation_all_passed"] is True
    assert summary["manual_validation_missing_evidence_app_ids"] == []


def test_validation_report_summary_surfaces_ipc_identity_fields() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": True, "blocker_code": "ready"},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_session_payload=None,
        smoke_payload=None,
        framebus_roundtrip_payload=None,
        status_binary_check_payload=None,
        status_payload={
            "shared_memory_name": "/akvc-status",
            "mach_service_name": "com.akvc.status",
            "ipc_transport": "shared_memory_ringbuffer",
        },
        install_payload={
            "shared_memory_name": "/akvc-install",
            "mach_service_name": "com.akvc.install",
            "ipc_transport": "iosurface_ring",
        },
    )

    assert summary["status_shared_memory_name"] == "/akvc-status"
    assert summary["status_mach_service_name"] == "com.akvc.status"
    assert summary["status_ipc_transport"] == "shared_memory_ringbuffer"
    assert summary["install_shared_memory_name"] == "/akvc-install"
    assert summary["install_mach_service_name"] == "com.akvc.install"
    assert summary["install_ipc_transport"] == "iosurface_ring"


def test_validation_report_summary_surfaces_demo_snapshot() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": True, "blocker_code": "ready"},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload={
            "mode": "latest-provider",
            "frame_source_kind": "latest_frame_provider",
            "python_entrypoint_kind": "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream",
            "sdk_streamer_factory_used": True,
            "sdk_latest_provider_factory_used": True,
            "sdk_direct_push_used": False,
            "width": 1280,
            "height": 720,
            "fps": 30,
            "duration": 5,
            "camera_name": "AKVC Demo",
            "consumer_count": 2,
            "video_path": "demo.mp4",
        },
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_payload=None,
        install_session_payload=None,
        smoke_payload=None,
        framebus_roundtrip_payload=None,
        status_binary_check_payload=None,
    )

    assert summary["demo_present"] is True
    assert summary["demo_mode"] == "latest-provider"
    assert summary["demo_mode_supported"] is True
    assert summary["demo_width"] == 1280
    assert summary["demo_height"] == 720
    assert summary["demo_fps"] == 30.0
    assert summary["demo_duration"] == 5.0
    assert summary["demo_camera_name"] == "AKVC Demo"
    assert summary["demo_consumer_count"] == 2
    assert summary["demo_video_path"] == "demo.mp4"
    assert summary["demo_frame_source_kind"] == "latest_frame_provider"
    assert summary["demo_python_entrypoint_kind"] == "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream"
    assert summary["demo_sdk_streamer_factory_used"] is True
    assert summary["demo_sdk_latest_provider_factory_used"] is True
    assert summary["demo_sdk_direct_push_used"] is False


def test_validation_report_summary_prefers_demo_runtime_topology_when_direct_sender_active() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AKVC Direct"],
        readiness_payload={"phase": "installed_visible", "ready": True, "blocker_code": "ready"},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload={
            "mode": "provider",
            "runtime_snapshot": {
                "started": True,
                "camera_name": "AKVC Direct",
                "backend_name": "direct_sender",
                "using_direct_sender": True,
                "shared_memory_name": "/akvc-direct",
                "last_frame_format_name": "BGRA32",
                "runtime_topology": {
                    "runtime_topology_kind": "camera_extension_direct_sender",
                    "runtime_frame_path": (
                        "python_sdk -> cmio_sink_stream_direct -> camera_extension -> "
                        "system_camera_device -> client_app"
                    ),
                    "runtime_host_role": "container_activation_command_bridge",
                    "runtime_host_in_frame_hot_path": False,
                    "runtime_dedicated_host_daemon_required": False,
                    "runtime_container_app_configured": True,
                    "runtime_data_plane": "cmio_sink_stream_direct",
                    "runtime_control_plane": "host_activation_only",
                },
            },
        },
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_payload=None,
        install_session_payload={
            "sync_ipc": {
                "ipc_transport": "shared_memory_ringbuffer",
                "supported": True,
                "success": True,
            }
        },
        smoke_payload=None,
        framebus_roundtrip_payload=None,
        status_binary_check_payload=None,
        status_payload={"ipc_transport": "shared_memory_ringbuffer"},
    )

    assert summary["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert summary["runtime_frame_path"] == (
        "python_sdk -> cmio_sink_stream_direct -> camera_extension -> system_camera_device -> client_app"
    )
    assert summary["runtime_host_role"] == "container_activation_command_bridge"
    assert summary["runtime_host_in_frame_hot_path"] is False
    assert summary["runtime_dedicated_host_daemon_required"] is False
    assert summary["runtime_container_app_configured"] is True
    assert summary["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert summary["runtime_control_plane"] == "host_activation_only"
    assert summary["demo_runtime_snapshot_present"] is True
    assert summary["demo_runtime_snapshot_started"] is True
    assert summary["demo_shared_memory_name"] == "/akvc-direct"
    assert summary["demo_last_frame_format_name"] == "BGRA32"


def test_macos_validation_report_tool_summarizes_benchmark_matrix_payload(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    benchmark_json = tmp_path / "benchmark-matrix.json"
    output_json = tmp_path / "validation-report.json"

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
    "approval_required": False
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
    benchmark_json.write_text(
        json.dumps(
            {
                "kind": "benchmark_matrix",
                "profiles": ["720p30", "1080p60"],
                "results": [
                    {"profile": {"name": "720p30"}, "acceptance": {"fps_target_met": True, "cpu_target_applies": False, "cpu_target_met": None}},
                    {"profile": {"name": "1080p60"}, "acceptance": {"fps_target_met": True, "cpu_target_applies": True, "cpu_target_met": True}},
                ],
                "summary": {
                    "profiles_run": 2,
                    "fps_targets_met": 2,
                    "cpu_targets_applied": 1,
                    "cpu_targets_met": 1,
                    "benchmark_acceptance": {
                        "profile_count": 2,
                        "all_fps_targets_met": True,
                        "1080p60_cpu_target_met": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--benchmark-json",
            str(benchmark_json),
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
    assert payload["summary"]["benchmark_present"] is True
    assert payload["summary"]["benchmark_kind"] == "benchmark_matrix"
    assert payload["summary"]["status_start_blocker_code"] == "ready"
    assert payload["summary"]["benchmark_acceptance"]["profile_count"] == 2
    assert payload["summary"]["benchmark_acceptance"]["1080p60_cpu_target_met"] is True
    assert payload["summary"]["benchmark_matrix_profiles"] == [
        {
            "profile_name": "720p30",
            "width": None,
            "height": None,
            "fps": None,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": None,
            "cpu_percent": None,
            "avg_latency_ms": None,
        },
        {
            "profile_name": "1080p60",
            "width": None,
            "height": None,
            "fps": None,
            "fps_target_met": True,
            "cpu_target_applies": True,
            "cpu_target_met": True,
            "actual_fps": None,
            "cpu_percent": None,
            "avg_latency_ms": None,
        },
    ]


def test_validation_report_summary_treats_framebus_errno_1_as_environment_blocked() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": False, "blocker_code": "ipc_environment_blocked"},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_payload=None,
        install_session_payload=None,
        smoke_payload=None,
        framebus_roundtrip_payload={
            "error": "shm_open(create) failed (errno=1)",
            "environment_blocked": True,
            "observed": {
                "status": "producer_open_failed",
                "direct_open_errno": 1,
            },
            "consistency": {
                "all_checks_passed": False,
                "status_ok": False,
                "environment_blocked": True,
            },
        },
        status_binary_check_payload=None,
    )

    assert summary["framebus_roundtrip_present"] is True
    assert summary["framebus_roundtrip_direct_open_errno"] == 1
    assert summary["framebus_roundtrip_environment_blocked"] is True


def test_validation_report_summary_surfaces_status_binary_producer_errno_1() -> None:
    summary = report_tool._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={"phase": "installed_visible", "ready": False, "blocker_code": "ipc_environment_blocked"},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload=None,
        release_diagnostics_payload=None,
        runtime_assets_payload=None,
        install_session_payload=None,
        smoke_payload=None,
        framebus_roundtrip_payload=None,
        status_binary_check_payload={
            "consistency": {
                "all_checks_passed": True,
                "ipc_keys_present": True,
            },
            "payload": {
                "ipc_environment_blocked": True,
                "ipc_direct_open_errno": 1,
                "ipc_last_error": "shm_open(create) failed (errno=1); probe status=producer_open_failed; direct_open_errno=1",
            },
            "fixture_cases": [
                {
                    "name": "producer_open_failed_errno_1",
                    "payload": {
                        "ipc_environment_blocked": True,
                        "ipc_direct_open_errno": 1,
                    },
                }
            ],
        },
    )

    assert summary["status_binary_check_present"] is True
    assert summary["status_binary_check_passed"] is True
    assert summary["status_binary_check_ipc_keys_present"] is True
    assert summary["status_binary_check_ipc_environment_blocked"] is True
    assert summary["status_binary_check_ipc_direct_open_errno"] == 1


def test_macos_validation_report_tool_writes_manual_template(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    template_json = tmp_path / "manual-template.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "devices": ["AK Virtual Camera"],
    "enabled": True,
    "approval_required": False
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

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--write-manual-template",
            str(template_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(template_json.read_text(encoding="utf-8"))
    assert set(payload) == {
        "zoom",
        "teams",
        "google_meet",
        "obs",
        "quicktime",
        "facetime",
    }
    assert payload["zoom"]["validated"] is False
    assert payload["zoom"]["result"] == "pending"
    assert payload["zoom"]["ready"] is True
    assert payload["zoom"]["evidence"] == {
        "device_listed": False,
        "device_selected": False,
        "preview_visible": False,
        "screenshot": "",
    }
    assert "checks" in payload["quicktime"]
    assert "实时画面" in payload["quicktime"]["checks"][1]
    assert "steps" in payload["quicktime"]
    assert "AK Virtual Camera" in payload["quicktime"]["steps"][1]


def test_macos_validation_report_tool_manual_template_uses_runtime_device_prefix(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    template_json = tmp_path / "manual-results.template.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({
    "state": "installed",
    "enabled": True,
    "approval_required": False,
    "device_prefix": "Demo Camera",
    "devices": ["Demo Camera"],
    "all_devices": ["FaceTime HD Camera", "Demo Camera"]
}))
""",
    )
    write_tool(
        list_devices_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"devices": ["Demo Camera"]}))
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--list-devices-tool",
            str(list_devices_tool),
            "--write-manual-template",
            str(template_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(template_json.read_text(encoding="utf-8"))
    assert "Demo Camera" in payload["zoom"]["status"]
    assert "Demo Camera" in payload["quicktime"]["steps"][1]
    assert "Demo Camera" in payload["facetime"]["checks"][0]


def test_macos_validation_report_tool_rejects_missing_status_tool() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert '"runtime_assets"' in completed.stdout
    assert '"status"' in completed.stdout


def test_macos_validation_report_tool_rejects_unknown_manual_result_key(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    manual_results = tmp_path / "manual-results.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}))
""",
    )
    manual_results.write_text(
        json.dumps({"googlemeet": {"validated": True, "result": "pass"}}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--manual-results",
            str(manual_results),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "unknown manual results key" in completed.stderr


def test_macos_validation_report_tool_rejects_invalid_manual_result_value(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    manual_results = tmp_path / "manual-results.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}))
""",
    )
    manual_results.write_text(
        json.dumps({"zoom": {"validated": True, "result": "ok"}}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--manual-results",
            str(manual_results),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "invalid manual result" in completed.stderr


def test_macos_validation_report_tool_rejects_invalid_manual_evidence_shape(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    manual_results = tmp_path / "manual-results.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}))
""",
    )
    manual_results.write_text(
        json.dumps({"zoom": {"validated": True, "result": "pass", "evidence": {"preview_visible": "yes"}}}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--manual-results",
            str(manual_results),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "manual result evidence.preview_visible must be bool" in completed.stderr


def test_macos_validation_report_tool_rejects_non_object_preflight_json(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    preflight_json = tmp_path / "preflight.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}))
""",
    )
    preflight_json.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--preflight-json",
            str(preflight_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "preflight JSON must be an object" in completed.stderr


def test_macos_validation_report_tool_rejects_non_object_release_diagnostics_json(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    release_diagnostics_json = tmp_path / "release-diagnostics.json"

    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_tool(
        status_tool,
        """#!/usr/bin/env python3
import json
print(json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}))
""",
    )
    release_diagnostics_json.write_text(json.dumps(["bad"]), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_report.py"),
            "--status-tool",
            str(status_tool),
            "--release-diagnostics-json",
            str(release_diagnostics_json),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "release diagnostics JSON must be an object" in completed.stderr
