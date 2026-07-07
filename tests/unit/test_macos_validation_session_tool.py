# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS validation session helper."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

from tools import macos_validation_session as session_tool


ROOT = Path(__file__).resolve().parents[2]


def test_macos_validation_session_tool_exists_and_declares_expected_options() -> None:
    script = ROOT / "tools" / "macos_validation_session.py"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "--output-dir" in text
    assert "--skip-demo" in text
    assert "--skip-benchmark" in text
    assert "--manual-results" in text
    assert "--reuse-existing-artifacts" in text
    assert "--preflight-tool" in text
    assert "--release-diagnostics-tool" in text
    assert "--smoke-tool" in text
    assert "--install-session-tool" in text
    assert "--framebus-roundtrip-tool" in text
    assert "--framebus-producer-kind" in text
    assert "--direct-push-demo-tool" in text
    assert "--direct-push-frames" in text
    assert "--direct-sender-object-demo-tool" in text
    assert "--direct-sender-object-frames" in text
    assert "--status-binary-check-tool" in text
    assert "--list-devices-binary-check-tool" in text
    assert "--entrypoints-contract-tool" in text
    assert "--sdk-contract-tool" in text
    assert "--artifact-check-tool" in text
    assert "--acceptance-tool" in text
    assert "--acceptance-contract-tool" in text
    assert "--summary-tool" in text
    assert "--skip-preflight" in text
    assert "--skip-release-diagnostics" in text
    assert "--mode" in text
    assert "video-file" in text
    assert "latest-provider" in text
    assert "--video-path" in text
    assert "--status-tool" in text
    assert "--install-tool" in text
    assert "--list-devices-tool" in text
    assert "--uninstall-tool" in text
    assert "--sync-ipc-tool" in text
    assert "--app-bundle" in text
    assert "--app-executable" in text
    assert "--host-bundle" in text
    assert "--host-executable" in text
    assert "--direct-sender-library" in text
    assert "--pkg-path" in text
    assert "--installer-executable" in text
    assert "--disable-auto-package" in text
    assert "--demo-tool" in text
    assert "--benchmark-tool" in text
    assert "--benchmark-profile" in text
    assert "--benchmark-matrix" in text
    assert "--benchmark-warmup" in text
    assert "--validation-report-tool" in text
    assert "session-manifest.json" in text
    assert "--run-uninstall" in text
    assert "--run-install-session" in text
    assert "--run-framebus-roundtrip" in text
    assert "--run-direct-sender-object-demo" in text
    assert "--run-status-binary-check" in text
    assert "--run-list-devices-binary-check" in text


def test_macos_validation_session_tool_runs_demo_benchmark_and_report(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    benchmark_tool = tmp_path / "benchmark.py"
    report_tool = tmp_path / "report.py"
    entrypoints_contract_tool = tmp_path / "entrypoints-contract.py"
    sdk_contract_tool = tmp_path / "sdk-contract.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    session_dir = tmp_path / "session"
    manual_results = tmp_path / "manual-results.json"
    preflight_tool = tmp_path / "preflight.py"
    release_diagnostics_tool = tmp_path / "release-diagnostics.py"
    host_bundle = tmp_path / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    direct_sender_library = tmp_path / "libakvc-macos-direct-sender.dylib"

    manual_results.write_text(
        json.dumps({"zoom": {"validated": True, "result": "pass"}}),
        encoding="utf-8",
    )
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    direct_sender_library.write_text("placeholder", encoding="utf-8")

    write_tool(
        preflight_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"readiness": {"can_build_native": True, "can_package": True}}), encoding="utf-8")
print("preflight-ok")
""",
    )
    write_tool(
        release_diagnostics_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"summary": {"release_artifacts_present": True, "universal2_ready": True, "app_signed": True, "app_gatekeeper_accepted": True, "app_stapled": True, "extension_signed": True, "pkg_signed": True, "pkg_gatekeeper_accepted": True, "pkg_stapled": True, "pkg_payload_appledouble_clean": True, "sync_ipc_tool_exists": True, "sync_ipc_tool_signed": True, "sync_ipc_tool_universal2_ready": True}}), encoding="utf-8")
print("release-diagnostics-ok")
""",
    )
    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
for flag, expected in [
    ("--app-bundle", %r),
    ("--app-executable", %r),
    ("--direct-sender-library", %r),
]:
    assert flag in args
    assert args[args.index(flag) + 1] == expected
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "provider", "camera_name": "AKVC Demo"}), encoding="utf-8")
print("demo-ok")
""" % (str(host_bundle), str(host_executable), str(direct_sender_library)),
    )
    write_tool(
        benchmark_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"metrics": {"cpu_percent": 8.1}}), encoding="utf-8")
print("benchmark-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 1, "passed_app_ids": ["zoom"], "reviewed_app_ids": ["zoom"], "failed_app_ids": [], "pending_app_ids": [], "skipped_app_ids": [], "unreviewed_app_ids": [], "observed_target_app_ids": ["zoom"], "missing_target_app_ids": ["facetime", "google_meet", "obs", "quicktime", "teams"], "unexpected_target_app_ids": [], "target_app_ids_complete": False, "status_start_ready": True, "status_start_blocker_code": "ready", "demo_present": True, "demo_mode": "provider", "demo_mode_supported": True, "demo_camera_name": "AKVC Demo", "demo_consumer_count": 2, "demo_frame_source_kind": "callable_provider", "demo_python_entrypoint_kind": "create_pyside6_streamer.start_provider_stream", "demo_sdk_streamer_factory_used": True, "demo_sdk_latest_provider_factory_used": False, "demo_sdk_direct_push_used": False}}), encoding="utf-8")
print("report-ok")
""",
    )
    write_tool(
        sdk_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True, "constructor_shape_aligned": True, "direct_sender_exports_present": True}}), encoding="utf-8")
print("sdk-contract-ok")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        entrypoints_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True, "surface_complete": True, "demo_case_complete": True, "cli_case_complete": True, "desktop_case_complete": True}}), encoding="utf-8")
print("entrypoints-contract-ok")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("acceptance-contract-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--preflight-tool",
            str(preflight_tool),
            "--release-diagnostics-tool",
            str(release_diagnostics_tool),
            "--demo-tool",
            str(demo_tool),
            "--app-bundle",
            str(host_bundle),
            "--app-executable",
            str(host_executable),
            "--direct-sender-library",
            str(direct_sender_library),
            "--benchmark-tool",
            str(benchmark_tool),
            "--validation-report-tool",
            str(report_tool),
            "--entrypoints-contract-tool",
            str(entrypoints_contract_tool),
            "--sdk-contract-tool",
            str(sdk_contract_tool),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--manual-results",
            str(manual_results),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["preflight_report"].endswith("preflight.json")
    assert manifest["artifacts"]["release_diagnostics_report"].endswith("release-diagnostics.json")
    assert manifest["artifacts"]["demo_report"].endswith("demo-report.json")
    assert manifest["artifacts"]["benchmark_report"].endswith("benchmark.json")
    assert manifest["artifacts"]["smoke_report"].endswith("smoke-report.json")
    assert manifest["artifacts"]["install_session_report"].endswith("install-session-report.json")
    assert manifest["artifacts"]["framebus_roundtrip_report"].endswith("framebus-roundtrip.json")
    assert manifest["artifacts"]["direct_push_demo_report"].endswith("direct-push-report.json")
    assert manifest["artifacts"]["direct_sender_object_demo_report"].endswith("direct-sender-object-report.json")
    assert manifest["artifacts"]["status_binary_check_report"].endswith("status-binary-check.json")
    assert manifest["artifacts"]["list_devices_binary_check_report"].endswith("list-devices-binary-check.json")
    assert manifest["artifacts"]["entrypoints_contract_report"].endswith("entrypoints-contract.json")
    assert manifest["artifacts"]["sdk_contract_report"].endswith("sdk-contract.json")
    assert manifest["artifacts"]["artifact_check_report"].endswith("session-manifest-check.json")
    assert manifest["artifacts"]["acceptance_report"].endswith("session-acceptance.json")
    assert manifest["artifacts"]["acceptance_contract_report"].endswith("session-acceptance-contract.json")
    assert manifest["artifacts"]["summary_report"].endswith("session-summary.md")
    assert manifest["artifacts"]["manual_template"].endswith("manual-results.template.json")
    assert manifest["artifacts"]["validation_report"].endswith("validation-report.json")
    assert manifest["steps"]["preflight"]["returncode"] == 0
    assert manifest["steps"]["release_diagnostics"]["returncode"] == 0
    assert manifest["steps"]["demo"]["returncode"] == 0
    assert manifest["steps"]["benchmark"]["returncode"] == 0
    assert manifest["steps"]["validation_report"]["returncode"] == 0
    assert manifest["steps"]["entrypoints_contract"]["returncode"] == 0
    assert manifest["steps"]["sdk_contract"]["returncode"] == 0
    assert manifest["steps"]["artifact_check"]["returncode"] == 0
    assert manifest["steps"]["acceptance"]["returncode"] == 0
    assert manifest["steps"]["acceptance_contract"]["returncode"] == 0
    assert manifest["steps"]["summary"]["returncode"] == 0
    assert manifest["summary"]["validation_report_present"] is True
    assert manifest["summary"]["direct_push_demo_present"] is False
    assert manifest["summary"]["direct_sender_object_demo_present"] is False
    assert manifest["summary"]["validation_report_summary"]["passed_apps"] == 1
    assert manifest["summary"]["validation_demo_present"] is True
    assert manifest["summary"]["validation_demo_mode"] == "provider"
    assert manifest["summary"]["validation_demo_camera_name"] == "AKVC Demo"
    assert manifest["summary"]["validation_demo_consumer_count"] == 2
    assert manifest["summary"]["validation_demo_frame_source_kind"] == "callable_provider"
    assert manifest["summary"]["validation_demo_python_entrypoint_kind"] == "create_pyside6_streamer.start_provider_stream"
    assert manifest["summary"]["validation_demo_sdk_streamer_factory_used"] is True
    assert manifest["summary"]["validation_demo_sdk_latest_provider_factory_used"] is False
    assert manifest["summary"]["validation_demo_sdk_direct_push_used"] is False
    assert manifest["summary"]["validation_passed_app_ids"] == ["zoom"]
    assert manifest["summary"]["validation_reviewed_app_ids"] == ["zoom"]
    assert manifest["summary"]["validation_failed_app_ids"] == []
    assert manifest["summary"]["validation_pending_app_ids"] == []
    assert manifest["summary"]["validation_skipped_app_ids"] == []
    assert manifest["summary"]["validation_unreviewed_app_ids"] == []
    assert manifest["summary"]["validation_observed_target_app_ids"] == ["zoom"]
    assert manifest["summary"]["validation_missing_target_app_ids"] == [
        "facetime",
        "google_meet",
        "obs",
        "quicktime",
        "teams",
    ]
    assert manifest["summary"]["validation_unexpected_target_app_ids"] == []
    assert manifest["summary"]["validation_target_app_ids_complete"] is False
    assert manifest["summary"]["release_sync_ipc_tool_exists"] is True
    assert manifest["summary"]["release_sync_ipc_tool_signed"] is True
    assert manifest["summary"]["release_sync_ipc_tool_universal2_ready"] is True
    assert manifest["summary"]["release_app_signed"] is True
    assert manifest["summary"]["release_app_gatekeeper_accepted"] is True
    assert manifest["summary"]["release_app_stapled"] is True
    assert manifest["summary"]["release_extension_signed"] is True
    assert manifest["summary"]["release_pkg_signed"] is True
    assert manifest["summary"]["release_pkg_gatekeeper_accepted"] is True
    assert manifest["summary"]["release_pkg_stapled"] is True
    assert manifest["summary"]["release_pkg_payload_appledouble_clean"] is True
    assert manifest["summary"]["entrypoints_contract_present"] is True
    assert manifest["summary"]["entrypoints_contract_passed"] is True
    assert manifest["summary"]["entrypoints_contract_surface_complete"] is True
    assert manifest["summary"]["entrypoints_contract_demo_case_complete"] is True
    assert manifest["summary"]["entrypoints_contract_cli_case_complete"] is True
    assert manifest["summary"]["entrypoints_contract_desktop_case_complete"] is True
    assert manifest["summary"]["sdk_contract_present"] is True
    assert manifest["summary"]["sdk_contract_passed"] is True
    assert manifest["summary"]["sdk_contract_constructor_shape_aligned"] is True
    assert manifest["summary"]["sdk_contract_direct_sender_exports_present"] is True
    assert manifest["summary"]["artifact_check_present"] is True
    assert manifest["summary"]["artifact_check_passed"] is True
    assert manifest["summary"]["acceptance_present"] is True
    assert manifest["summary"]["acceptance_ready"] is False
    assert manifest["summary"]["acceptance_contract_present"] is True
    assert manifest["summary"]["acceptance_contract_passed"] is True
    assert manifest["summary"]["python_entrypoints_consistent"] == "pass"
    assert manifest["summary"]["sync_ipc_control_plane_ready"] == "fail"
    assert manifest["summary"]["summary_report_present"] is True
    assert manifest["summary"]["validation_status_start_ready"] is True
    assert manifest["summary"]["validation_status_start_blocker_code"] == "ready"
    assert manifest["summary"]["effective_start_ready"] is True
    assert manifest["summary"]["effective_start_blocker_code"] == "ready"
    assert (session_dir / "preflight.json").is_file()
    assert (session_dir / "release-diagnostics.json").is_file()
    assert (session_dir / "demo-report.json").is_file()
    assert (session_dir / "benchmark.json").is_file()
    assert (session_dir / "entrypoints-contract.json").is_file()
    assert (session_dir / "sdk-contract.json").is_file()
    assert (session_dir / "session-manifest-check.json").is_file()
    assert (session_dir / "session-acceptance.json").is_file()
    assert (session_dir / "session-acceptance-contract.json").is_file()
    assert (session_dir / "session-summary.md").is_file()
    assert (session_dir / "manual-results.template.json").is_file()
    assert (session_dir / "validation-report.json").is_file()


def test_macos_validation_session_tool_runs_smoke_when_install_or_uninstall_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    smoke_tool = tmp_path / "smoke.py"
    report_tool = tmp_path / "report.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    session_dir = tmp_path / "session"

    write_tool(
        smoke_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--run-install" in args
assert "--run-uninstall" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"status": {"start_ready": False, "start_blocker_code": "device_not_visible"}, "install": {"success": True}, "uninstall": {"returncode": 0}}), encoding="utf-8")
print("smoke-ok")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("acceptance-contract-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--smoke-json" in args
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"smoke_present": True}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--smoke-tool",
            str(smoke_tool),
            "--validation-report-tool",
            str(report_tool),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-install",
            "--run-uninstall",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["smoke"]["returncode"] == 0
    assert manifest["summary"]["smoke_present"] is True
    assert manifest["summary"]["smoke_install_success"] is True
    assert manifest["summary"]["smoke_start_ready"] is False
    assert manifest["summary"]["smoke_start_blocker_code"] == "device_not_visible"
    assert manifest["summary"]["effective_start_ready"] is False
    assert manifest["summary"]["effective_start_blocker_code"] == "device_not_visible"
    assert (session_dir / "smoke-report.json").is_file()


def test_macos_validation_session_tool_runs_install_session_when_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    install_session_tool = tmp_path / "install-session.py"
    smoke_tool = tmp_path / "smoke.py"
    report_tool = tmp_path / "report.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    session_dir = tmp_path / "session"

    write_tool(
        smoke_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--run-uninstall" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"status": {"start_ready": True, "start_blocker_code": "ready"}, "uninstall": {"returncode": 0}}), encoding="utf-8")
print("smoke-ok")
""",
    )
    write_tool(
        install_session_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--run-uninstall" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"install": {"success": True}, "post_status": {"ipc_probe_present": True, "ipc_ready": True, "start_ready": True, "start_blocker_code": "ready", "shared_memory_name": "/akvc-install-session", "ipc_transport": "shared_memory_ringbuffer", "host_signature": "Developer ID Application", "host_team_identifier": "TEAM123456", "host_gatekeeper_allowed": True, "host_distribution_summary": "stapler validate passed", "host_notarization_missing": False, "install_command_notarization_missing": False, "system_extension_registered": True}, "sync_ipc": {"supported": True, "success": True, "phase": "sync_command_succeeded", "shared_memory_name": "/akvc-install-session", "ipc_transport": "shared_memory_ringbuffer", "returncode": 0}, "uninstall": {"returncode": 0}}), encoding="utf-8")
print("install-session-ok")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("acceptance-contract-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--install-session-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"install_session_present": True}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--smoke-tool",
            str(smoke_tool),
            "--install-session-tool",
            str(install_session_tool),
            "--validation-report-tool",
            str(report_tool),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-install-session",
            "--run-uninstall",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["install_session"]["returncode"] == 0
    assert manifest["summary"]["install_session_present"] is True
    assert manifest["summary"]["install_session_success"] is True
    assert manifest["summary"]["install_session_ipc_probe_present"] is True
    assert manifest["summary"]["install_session_ipc_ready"] is True
    assert manifest["summary"]["install_session_start_ready"] is True
    assert manifest["summary"]["install_session_start_blocker_code"] == "ready"
    assert manifest["summary"]["install_session_sync_ipc_present"] is True
    assert manifest["summary"]["install_session_sync_ipc_supported"] is True
    assert manifest["summary"]["install_session_sync_ipc_success"] is True
    assert manifest["summary"]["install_session_sync_ipc_phase"] == "sync_command_succeeded"
    assert manifest["summary"]["install_session_sync_ipc_shared_memory_name"] == "/akvc-install-session"
    assert manifest["summary"]["install_session_sync_ipc_transport"] == "shared_memory_ringbuffer"
    assert manifest["summary"]["install_session_sync_ipc_returncode"] == 0
    assert manifest["summary"]["install_session_host_signature"] == "Developer ID Application"
    assert manifest["summary"]["install_session_host_team_identifier"] == "TEAM123456"
    assert manifest["summary"]["install_session_host_gatekeeper_allowed"] is True
    assert manifest["summary"]["install_session_host_distribution_summary"] == "stapler validate passed"
    assert manifest["summary"]["install_session_host_notarization_missing"] is False
    assert manifest["summary"]["install_session_install_command_notarization_missing"] is False
    assert manifest["summary"]["install_session_system_extension_registered"] is True
    assert manifest["summary"]["effective_start_ready"] is True
    assert manifest["summary"]["effective_start_blocker_code"] == "ready"
    assert (session_dir / "install-session-report.json").is_file()


def test_macos_validation_session_tool_forwards_host_and_runtime_overrides(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    host_bundle = tmp_path / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    installer_executable = tmp_path / "installer"
    smoke_tool = tmp_path / "smoke.py"
    install_session_tool = tmp_path / "install-session.py"
    report_tool = tmp_path / "report.py"
    entrypoints_contract_tool = tmp_path / "entrypoints-contract.py"
    sdk_contract_tool = tmp_path / "sdk-contract.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    session_dir = tmp_path / "session"
    pkg_path = tmp_path / "VirtualCamera.pkg"

    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    for path in (
        status_tool,
        install_tool,
        list_devices_tool,
        uninstall_tool,
        sync_ipc_tool,
        installer_executable,
        pkg_path,
    ):
        path.write_text("placeholder", encoding="utf-8")

    write_tool(
        smoke_tool,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
for flag, expected in [
    ("--status-tool", {str(status_tool)!r}),
    ("--install-tool", {str(install_tool)!r}),
    ("--list-devices-tool", {str(list_devices_tool)!r}),
    ("--uninstall-tool", {str(uninstall_tool)!r}),
    ("--sync-ipc-tool", {str(sync_ipc_tool)!r}),
    ("--app-bundle", {str(host_bundle)!r}),
    ("--app-executable", {str(host_executable)!r}),
    ("--pkg-path", {str(pkg_path)!r}),
    ("--installer-executable", {str(installer_executable)!r}),
]:
    assert flag in args
    assert args[args.index(flag) + 1] == expected
assert "--disable-auto-package" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({{"status": {{"start_ready": True, "start_blocker_code": "ready"}}, "install": {{"success": True}}}}), encoding="utf-8")
print("smoke-ok")
""",
    )
    write_tool(
        install_session_tool,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
for flag, expected in [
    ("--status-tool", {str(status_tool)!r}),
    ("--install-tool", {str(install_tool)!r}),
    ("--list-devices-tool", {str(list_devices_tool)!r}),
    ("--uninstall-tool", {str(uninstall_tool)!r}),
    ("--sync-ipc-tool", {str(sync_ipc_tool)!r}),
    ("--app-bundle", {str(host_bundle)!r}),
    ("--app-executable", {str(host_executable)!r}),
    ("--pkg-path", {str(pkg_path)!r}),
    ("--installer-executable", {str(installer_executable)!r}),
]:
    assert flag in args
    assert args[args.index(flag) + 1] == expected
assert "--disable-auto-package" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({{"install": {{"success": True}}, "post_status": {{"start_ready": True, "start_blocker_code": "ready"}}}}), encoding="utf-8")
print("install-session-ok")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        sdk_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("sdk-contract-ok")
""",
    )
    write_tool(
        entrypoints_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("entrypoints-contract-ok")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("acceptance-contract-ok")
""",
    )
    write_tool(
        report_tool,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
for flag, expected in [
    ("--status-tool", {str(status_tool)!r}),
    ("--install-tool", {str(install_tool)!r}),
    ("--list-devices-tool", {str(list_devices_tool)!r}),
    ("--uninstall-tool", {str(uninstall_tool)!r}),
    ("--sync-ipc-tool", {str(sync_ipc_tool)!r}),
    ("--app-bundle", {str(host_bundle)!r}),
    ("--app-executable", {str(host_executable)!r}),
    ("--pkg-path", {str(pkg_path)!r}),
    ("--installer-executable", {str(installer_executable)!r}),
]:
    assert flag in args
    assert args[args.index(flag) + 1] == expected
assert "--disable-auto-package" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({{"zoom": {{"validated": False, "result": "pending"}}}}), encoding="utf-8")
report.write_text(json.dumps({{"summary": {{"passed_apps": 0}}}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
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
            "--app-bundle",
            str(host_bundle),
            "--app-executable",
            str(host_executable),
            "--pkg-path",
            str(pkg_path),
            "--installer-executable",
            str(installer_executable),
            "--disable-auto-package",
            "--smoke-tool",
            str(smoke_tool),
            "--install-session-tool",
            str(install_session_tool),
            "--validation-report-tool",
            str(report_tool),
            "--entrypoints-contract-tool",
            str(entrypoints_contract_tool),
            "--sdk-contract-tool",
            str(sdk_contract_tool),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-install",
            "--run-install-session",
            "--run-uninstall",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["smoke"]["returncode"] == 0
    assert manifest["steps"]["install_session"]["returncode"] == 0
    assert manifest["steps"]["validation_report"]["returncode"] == 0


def test_macos_validation_session_tool_reuses_existing_artifacts_for_manual_results_replay(
    tmp_path,
) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    manual_results = tmp_path / "manual-results.json"
    report_tool = tmp_path / "report.py"
    entrypoints_contract_tool = tmp_path / "entrypoints-contract.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_tool = tmp_path / "acceptance.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    summary_tool = tmp_path / "summary.py"

    (session_dir / "preflight.json").write_text(
        json.dumps({"readiness": {"can_build_native": True, "can_package": True}}),
        encoding="utf-8",
    )
    (session_dir / "release-diagnostics.json").write_text(
        json.dumps({"summary": {"release_artifacts_present": True, "universal2_ready": True, "pkg_payload_appledouble_clean": True}}),
        encoding="utf-8",
    )
    (session_dir / "demo-report.json").write_text(
        json.dumps({"mode": "provider", "camera_name": "AKVC Existing Demo"}),
        encoding="utf-8",
    )
    (session_dir / "benchmark.json").write_text(
        json.dumps({"metrics": {"cpu_percent": 7.9}}),
        encoding="utf-8",
    )
    (session_dir / "smoke-report.json").write_text(
        json.dumps({"status": {"start_ready": True, "start_blocker_code": "ready"}}),
        encoding="utf-8",
    )
    (session_dir / "install-session-report.json").write_text(
        json.dumps({"post_status": {"start_ready": True, "start_blocker_code": "ready"}}),
        encoding="utf-8",
    )
    (session_dir / "framebus-roundtrip.json").write_text(
        json.dumps({"consistency": {"all_checks_passed": True}}),
        encoding="utf-8",
    )
    (session_dir / "status-binary-check.json").write_text(
        json.dumps({"consistency": {"all_checks_passed": True}}),
        encoding="utf-8",
    )
    (session_dir / "session-manifest.json").write_text(
        json.dumps(
            {
                "artifacts": {
                    "validation_report": str(session_dir / "validation-report.json"),
                },
                "steps": {
                    "demo": {"returncode": 0},
                    "benchmark": {"returncode": 0},
                },
                "summary": {
                    "validation_demo_mode": "provider",
                },
            }
        ),
        encoding="utf-8",
    )
    manual_results.write_text(
        json.dumps(
            {
                "zoom": {
                    "validated": True,
                    "result": "pass",
                    "notes": "manual replay ok",
                }
            }
        ),
        encoding="utf-8",
    )

    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--preflight-json" in args
assert "--release-diagnostics-json" in args
assert "--demo-json" in args
assert "--benchmark-json" in args
assert "--smoke-json" in args
assert "--install-session-json" in args
assert "--framebus-roundtrip-json" in args
assert "--status-binary-check-json" in args
assert "--manual-results" in args
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 1, "passed_app_ids": ["zoom"], "reviewed_app_ids": ["zoom"], "failed_app_ids": [], "pending_app_ids": [], "skipped_app_ids": [], "unreviewed_app_ids": [], "observed_target_app_ids": ["zoom"], "missing_target_app_ids": ["facetime", "google_meet", "obs", "quicktime", "teams"], "unexpected_target_app_ids": [], "target_app_ids_complete": False}}), encoding="utf-8")
print("report-reuse-ok")
""",
    )
    write_tool(
        entrypoints_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True, "surface_complete": True, "demo_case_complete": True, "cli_case_complete": True, "desktop_case_complete": True}}), encoding="utf-8")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
""",
    )
    write_tool(
        acceptance_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"summary": {"acceptance_ready": True, "passed_count": 1, "failed_count": 0, "unknown_count": 0, "failed_criteria": [], "unknown_criteria": [], "manual_app_validation_ready": True, "manual_app_validation_failed_criteria": [], "manual_app_validation_unknown_criteria": [], "manual_app_validation_blockers": []}, "criteria": []}), encoding="utf-8")
""",
            )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
""",
    )
    write_tool(
        summary_tool,
        """#!/usr/bin/env python3
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("# reused summary\\n", encoding="utf-8")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--manual-results",
            str(manual_results),
            "--reuse-existing-artifacts",
            "--validation-report-tool",
            str(report_tool),
            "--entrypoints-contract-tool",
            str(entrypoints_contract_tool),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-tool",
            str(acceptance_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--summary-tool",
            str(summary_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["demo"]["returncode"] == 0
    assert manifest["steps"]["benchmark"]["returncode"] == 0
    assert manifest["steps"]["validation_report"]["returncode"] == 0
    assert manifest["summary"]["validation_report_present"] is True
    assert manifest["summary"]["validation_report_summary"]["passed_apps"] == 1
    assert manifest["summary"]["release_pkg_payload_appledouble_clean"] is True
    assert manifest["summary"]["acceptance_present"] is True
    assert manifest["summary"]["acceptance_ready"] is True
    assert manifest["summary"]["summary_report_present"] is True
    assert (session_dir / "session-summary.md").read_text(encoding="utf-8") == "# reused summary\n"


def test_validation_session_summary_falls_back_to_validation_report_install_snapshot(tmp_path) -> None:
    validation_report = tmp_path / "validation-report.json"
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"
    validation_report.write_text(
        json.dumps(
            {
                "status": {
                    "shared_memory_name": "/akvc-validation",
                    "mach_service_name": "com.akvc.validation",
                    "ipc_transport": "shared_memory_ringbuffer",
                    "supported_formats": ["1280x720@30/60 NV12"],
                    "supported_frame_rates": [30],
                },
                "summary": {
                    "status_start_ready": False,
                    "status_start_blocker_code": "not_installed",
                    "install_present": True,
                    "install_success": True,
                    "install_phase": "installed_visible",
                    "install_start_ready": True,
                    "install_start_blocker_code": "ready",
                    "install_shared_memory_name": "/akvc-validation-install",
                    "install_mach_service_name": "com.akvc.validation.install",
                    "install_ipc_transport": "validation_install_transport",
                    "install_supported_formats": ["1920x1080@30/60 NV12"],
                    "install_supported_frame_rates": [30, 60],
                    "install_ipc_probe_present": True,
                    "install_ipc_ready": True,
                    "install_ipc_environment_blocked": False,
                    "install_ipc_direct_open_errno": 0,
                },
                "runtime_assets": {
                    "resolved_assets": {
                        "status_tool": "/tmp/akvc-macos-status",
                        "install_tool": "/tmp/akvc-macos-install",
                        "devices_tool": "/tmp/akvc-macos-list-devices",
                        "uninstall_tool": "/tmp/akvc-macos-uninstall",
                        "sync_ipc_tool": "/tmp/akvc-macos-sync-ipc",
                        "pkg": "/tmp/VirtualCamera.pkg",
                    },
                    "provenance": {
                        "host_bundle": str(host_bundle),
                        "host_executable": str(host_bundle / "Contents" / "MacOS" / "akvc-host"),
                        "extension_bundle": str(
                            host_bundle
                            / "Contents"
                            / "Library"
                            / "SystemExtensions"
                            / "com.sidus.amaran-desktop.cameraextension.systemextension"
                        ),
                        "package_install_command": [
                            "/usr/sbin/installer",
                            "-pkg",
                            "/tmp/VirtualCamera.pkg",
                            "-target",
                            "/",
                        ],
                        "auto_install_package": True,
                    },
                    "summary": {
                        "host_bundle_configured": True,
                        "host_executable_configured": True,
                        "extension_bundle_derived": True,
                        "package_install_command_present": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["validation_install_present"] is True
    assert summary["validation_install_success"] is True
    assert summary["validation_install_phase"] == "installed_visible"
    assert summary["validation_install_start_ready"] is True
    assert summary["validation_install_start_blocker_code"] == "ready"
    assert summary["validation_shared_memory_name"] == "/akvc-validation"
    assert summary["validation_mach_service_name"] == "com.akvc.validation"
    assert summary["validation_ipc_transport"] == "shared_memory_ringbuffer"
    assert summary["validation_install_shared_memory_name"] == "/akvc-validation-install"
    assert summary["validation_install_mach_service_name"] == "com.akvc.validation.install"
    assert summary["validation_install_ipc_transport"] == "validation_install_transport"
    assert summary["validation_install_supported_formats"] == ["1920x1080@30/60 NV12"]
    assert summary["validation_install_supported_frame_rates"] == [30, 60]
    assert summary["validation_install_ipc_probe_present"] is True
    assert summary["validation_install_ipc_ready"] is True
    assert summary["validation_install_ipc_environment_blocked"] is False
    assert summary["validation_install_ipc_direct_open_errno"] == 0
    assert summary["runtime_status_tool_path"] == "/tmp/akvc-macos-status"
    assert summary["runtime_install_tool_path"] == "/tmp/akvc-macos-install"
    assert summary["runtime_devices_tool_path"] == "/tmp/akvc-macos-list-devices"
    assert summary["runtime_uninstall_tool_path"] == "/tmp/akvc-macos-uninstall"
    assert summary["runtime_sync_ipc_tool_path"] == "/tmp/akvc-macos-sync-ipc"
    assert summary["runtime_pkg_path"] == "/tmp/VirtualCamera.pkg"
    assert summary["runtime_host_bundle_path"] == str(host_bundle)
    assert summary["runtime_host_executable_path"] == str(host_bundle / "Contents" / "MacOS" / "akvc-host")
    assert summary["runtime_extension_bundle_path"] == str(
        host_bundle / "Contents" / "Library" / "SystemExtensions" / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    assert summary["runtime_package_install_command"] == [
        "/usr/sbin/installer",
        "-pkg",
        "/tmp/VirtualCamera.pkg",
        "-target",
        "/",
    ]
    assert summary["runtime_auto_install_package"] is True
    assert summary["runtime_host_bundle_configured"] is True
    assert summary["runtime_host_executable_configured"] is True
    assert summary["runtime_extension_bundle_derived"] is True
    assert summary["runtime_package_install_command_present"] is True
    assert summary["runtime_topology_kind"] == "camera_extension_direct_framebus"
    assert summary["runtime_frame_path"] == (
        "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app"
    )
    assert summary["runtime_host_role"] == "container_activation_command_bridge"
    assert summary["runtime_host_in_frame_hot_path"] is False
    assert summary["runtime_dedicated_host_daemon_required"] is False
    assert summary["runtime_container_app_configured"] is True
    assert summary["runtime_data_plane"] == "validation_install_transport"
    assert summary["runtime_control_plane"] == "host_activation_plus_sync_ipc"
    assert summary["effective_start_ready"] is True
    assert summary["effective_start_blocker_code"] == "ready"
    assert summary["effective_shared_memory_name"] == "/akvc-validation-install"
    assert summary["effective_mach_service_name"] == "com.akvc.validation.install"
    assert summary["effective_ipc_transport"] == "validation_install_transport"
    assert summary["effective_supported_formats"] == ["1920x1080@30/60 NV12"]
    assert summary["effective_supported_frame_rates"] == [30, 60]


def test_macos_validation_session_tool_runs_framebus_roundtrip_when_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    framebus_roundtrip_tool = tmp_path / "framebus-roundtrip.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        framebus_roundtrip_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--producer-kind" in args
assert args[args.index("--producer-kind") + 1] == "mac-virtual-camera"
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"producer_kind": "mac-virtual-camera", "consistency": {"all_checks_passed": False}, "observed": {"direct_open_errno": 13}, "producer_control": {"producer_seq": 1}}), encoding="utf-8")
print("framebus-roundtrip-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--framebus-roundtrip-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"framebus_roundtrip_present": True}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--framebus-roundtrip-tool",
            str(framebus_roundtrip_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-framebus-roundtrip",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["framebus_roundtrip"]["returncode"] == 0
    assert manifest["summary"]["framebus_roundtrip_present"] is True
    assert manifest["summary"]["framebus_roundtrip_producer_kind"] == "mac-virtual-camera"
    assert manifest["summary"]["framebus_roundtrip_direct_open_errno"] == 13
    assert manifest["summary"]["effective_start_ready"] is False
    assert manifest["summary"]["effective_start_blocker_code"] == "ipc_environment_blocked"
    assert (session_dir / "framebus-roundtrip.json").is_file()


def test_validation_session_summary_treats_framebus_errno_1_as_environment_blocked(tmp_path) -> None:
    report = tmp_path / "framebus-roundtrip.json"
    report.write_text(
        json.dumps(
            {
                "producer_kind": "mac-virtual-camera",
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
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=tmp_path / "validation-report.json",
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=report,
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["framebus_roundtrip_present"] is True
    assert summary["framebus_roundtrip_producer_kind"] == "mac-virtual-camera"
    assert summary["framebus_roundtrip_direct_open_errno"] == 1
    assert summary["framebus_roundtrip_environment_blocked"] is True


def test_validation_session_summary_surfaces_direct_push_demo_report(tmp_path) -> None:
    direct_push_report = tmp_path / "direct-push-report.json"
    direct_sender_object_report = tmp_path / "direct-sender-object-report.json"
    direct_push_report.write_text(
        json.dumps(
            {
                "mode": "direct-push",
                "frame_source_kind": "numpy.ndarray",
                "python_entrypoint_kind": "push_frame",
                "requested_frame_kind": "qimage-bgra",
                "requested_entrypoint": "send-widget",
                "sdk_direct_push_used": True,
                "backend_name": "direct_sender",
                "using_direct_sender": True,
                "direct_sender_attempted": True,
                "direct_sender_state": "active",
                "runtime_topology_kind": "camera_extension_direct_sender",
                "runtime_frame_path": "python_sdk -> cmio_sink_stream_direct -> camera_extension -> system_camera_device -> client_app",
                "runtime_host_role": "container_activation_command_bridge",
                "runtime_host_in_frame_hot_path": False,
                "runtime_dedicated_host_daemon_required": False,
                "runtime_container_app_configured": True,
                "runtime_data_plane": "cmio_sink_stream_direct",
                "runtime_control_plane": "host_activation_only",
                "direct_sender_target_name": "AKVC Direct",
                "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "direct_sender_last_error": None,
                "helper_hot_path_used": False,
                "shared_memory_fallback_used": False,
                "camera_name": "AKVC Direct",
                "consumer_count": 3,
                "requested_camera_access": True,
                "requested_camera_access_snapshot": {
                    "all_devices": ["AKVC Direct"],
                    "avfoundation_devices": ["AKVC Direct"],
                    "cmio_devices": ["AKVC Direct"],
                    "camera_access_status": "authorized",
                    "camera_access_authorized": True,
                    "camera_access_denied": False,
                    "camera_access_restricted": False,
                    "camera_access_not_determined": False,
                    "environment_device_enumeration_empty": False,
                },
                "requested_frames": 12,
                "frames_sent": 12,
                "direct_only": True,
                "probe_only": False,
                "direct_sender_device_snapshot": {
                    "all_devices": ["AKVC Direct"],
                    "avfoundation_devices": ["AKVC Direct"],
                    "cmio_devices": ["AKVC Direct"],
                    "camera_access_status": "authorized",
                    "camera_access_authorized": True,
                    "camera_access_denied": False,
                    "camera_access_restricted": False,
                    "camera_access_not_determined": False,
                    "environment_device_enumeration_empty": False,
                },
            }
        ),
        encoding="utf-8",
    )
    direct_sender_object_report.write_text(
        json.dumps(
            {
                "mode": "direct-sender-object",
                "frame_source_kind": "numpy.ndarray",
                "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
                "requested_frame_kind": "numpy-direct",
                "backend_name": "direct_sender_object",
                "using_direct_sender": True,
                "direct_sender_attempted": True,
                "direct_sender_state": "active",
                "runtime_topology_kind": "camera_extension_direct_sender_object",
                "runtime_data_plane": "cmio_sink_stream_direct",
                "runtime_control_plane": "system_extension_preinstalled",
                "direct_sender_target_name": "AKVC Object",
                "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                "camera_name": "AKVC Object",
                "consumer_count": 2,
                "requested_frames": 6,
                "frames_sent": 6,
                "direct_only": True,
                "inspect_only": False,
                "helper_hot_path_used": False,
                "shared_memory_fallback_used": False,
                "device_snapshot": {
                    "all_devices": ["AKVC Object"],
                    "avfoundation_devices": ["AKVC Object"],
                    "cmio_devices": ["AKVC Object"],
                    "camera_access_status": "authorized",
                    "camera_access_authorized": True,
                    "camera_access_denied": False,
                    "environment_device_enumeration_empty": False,
                },
            }
        ),
        encoding="utf-8",
    )
    summary = session_tool._build_manifest_summary(
        validation_report=tmp_path / "validation-report.json",
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        direct_push_demo_report=direct_push_report,
        direct_sender_object_demo_report=direct_sender_object_report,
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["direct_push_demo_present"] is True
    assert summary["direct_push_demo_mode"] == "direct-push"
    assert summary["direct_push_demo_frame_source_kind"] == "numpy.ndarray"
    assert summary["direct_push_demo_python_entrypoint_kind"] == "push_frame"
    assert summary["direct_push_demo_requested_frame_kind"] == "qimage-bgra"
    assert summary["direct_push_demo_requested_entrypoint"] == "send-widget"
    assert summary["direct_push_demo_sdk_direct_push_used"] is True
    assert summary["direct_push_demo_backend_name"] == "direct_sender"
    assert summary["direct_push_demo_using_direct_sender"] is True
    assert summary["direct_push_demo_direct_sender_attempted"] is True
    assert summary["direct_push_demo_direct_sender_state"] == "active"
    assert summary["direct_push_demo_runtime_topology_kind"] == "camera_extension_direct_sender"
    assert summary["direct_push_demo_runtime_data_plane"] == "cmio_sink_stream_direct"
    assert summary["direct_push_demo_runtime_control_plane"] == "host_activation_only"
    assert summary["direct_push_demo_helper_hot_path_used"] is False
    assert summary["direct_push_demo_shared_memory_fallback_used"] is False
    assert summary["direct_push_demo_direct_sender_target_name"] == "AKVC Direct"
    assert summary["direct_push_demo_direct_sender_library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert summary["direct_push_demo_direct_sender_last_error"] is None
    assert summary["direct_push_demo_camera_name"] == "AKVC Direct"
    assert summary["direct_push_demo_consumer_count"] == 3
    assert summary["direct_push_demo_requested_camera_access"] is True
    assert summary["direct_push_demo_requested_camera_access_snapshot_present"] is True
    assert summary["direct_push_demo_requested_camera_access_status"] == "authorized"
    assert summary["direct_push_demo_requested_camera_access_authorized"] is True
    assert summary["direct_push_demo_requested_camera_access_denied"] is False
    assert summary["direct_push_demo_requested_camera_access_environment_device_enumeration_empty"] is False
    assert summary["direct_push_demo_requested_camera_access_visible_all_devices"] == ["AKVC Direct"]
    assert summary["direct_push_demo_requested_frames"] == 12
    assert summary["direct_push_demo_frames_sent"] == 12
    assert summary["direct_push_demo_direct_only"] is True
    assert summary["direct_push_demo_probe_only"] is False
    assert summary["direct_push_demo_direct_sender_device_snapshot_present"] is True
    assert summary["direct_push_demo_camera_access_status"] == "authorized"
    assert summary["direct_push_demo_camera_access_authorized"] is True
    assert summary["direct_push_demo_camera_access_denied"] is False
    assert summary["direct_push_demo_environment_device_enumeration_empty"] is False
    assert summary["direct_push_demo_visible_all_devices"] == ["AKVC Direct"]
    assert summary["direct_push_demo_visible_avfoundation_devices"] == ["AKVC Direct"]
    assert summary["direct_push_demo_visible_cmio_devices"] == ["AKVC Direct"]
    assert summary["direct_sender_object_demo_present"] is True
    assert summary["direct_sender_object_demo_mode"] == "direct-sender-object"
    assert summary["direct_sender_object_demo_python_entrypoint_kind"] == "MacDirectCameraSender.send(auto-open)"
    assert summary["direct_sender_object_demo_requested_frame_kind"] == "numpy-direct"
    assert summary["direct_sender_object_demo_backend_name"] == "direct_sender_object"
    assert summary["direct_sender_object_demo_using_direct_sender"] is True
    assert summary["direct_sender_object_demo_direct_sender_state"] == "active"
    assert summary["direct_sender_object_demo_runtime_topology_kind"] == "camera_extension_direct_sender_object"
    assert summary["direct_sender_object_demo_runtime_data_plane"] == "cmio_sink_stream_direct"
    assert summary["direct_sender_object_demo_runtime_control_plane"] == "system_extension_preinstalled"
    assert summary["direct_sender_object_demo_direct_sender_target_name"] == "AKVC Object"
    assert summary["direct_sender_object_demo_direct_sender_library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert summary["direct_sender_object_demo_camera_name"] == "AKVC Object"
    assert summary["direct_sender_object_demo_consumer_count"] == 2
    assert summary["direct_sender_object_demo_requested_frames"] == 6
    assert summary["direct_sender_object_demo_frames_sent"] == 6
    assert summary["direct_sender_object_demo_direct_only"] is True
    assert summary["direct_sender_object_demo_probe_only"] is False
    assert summary["direct_sender_object_demo_helper_hot_path_used"] is False
    assert summary["direct_sender_object_demo_shared_memory_fallback_used"] is False
    assert summary["direct_sender_object_demo_direct_sender_device_snapshot_present"] is True
    assert summary["direct_sender_object_demo_camera_access_status"] == "authorized"
    assert summary["direct_sender_object_demo_camera_access_authorized"] is True
    assert summary["direct_sender_object_demo_visible_all_devices"] == ["AKVC Object"]


def test_validation_session_summary_surfaces_smoke_and_install_session_direct_push(tmp_path) -> None:
    smoke_report = tmp_path / "smoke-report.json"
    install_session_report = tmp_path / "install-session-report.json"
    smoke_report.write_text(
        json.dumps(
            {
                "direct_push_demo": {
                    "attempted": True,
                    "skipped": False,
                    "returncode": 0,
                    "request": {
                        "requested_frames": 9,
                        "requested_frame_kind": "qimage-bgra",
                        "requested_entrypoint": "send-widget",
                        "allow_shared_memory_fallback": True,
                        "requested_camera_access": True,
                    },
                    "payload": {
                        "mode": "direct-push",
                        "frame_source_kind": "numpy.ndarray",
                        "python_entrypoint_kind": "push_frame",
                        "requested_frame_kind": "qimage-bgra",
                        "requested_entrypoint": "send-widget",
                        "sdk_direct_push_used": True,
                        "backend_name": "direct_sender",
                        "using_direct_sender": True,
                        "direct_sender_attempted": True,
                        "direct_sender_state": "active",
                        "runtime_topology_kind": "camera_extension_direct_sender",
                        "runtime_frame_path": "python_sdk -> cmio_sink_stream_direct -> camera_extension -> system_camera_device -> client_app",
                        "runtime_host_role": "container_activation_command_bridge",
                        "runtime_host_in_frame_hot_path": False,
                        "helper_hot_path_used": False,
                        "shared_memory_fallback_used": False,
                        "runtime_dedicated_host_daemon_required": False,
                        "runtime_container_app_configured": True,
                        "runtime_data_plane": "cmio_sink_stream_direct",
                        "runtime_control_plane": "host_activation_only",
                        "direct_sender_target_name": "AKVC Smoke",
                        "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                        "direct_sender_last_error": None,
                        "camera_name": "AKVC Smoke",
                        "consumer_count": 1,
                        "requested_camera_access": True,
                        "requested_camera_access_snapshot": {
                            "all_devices": ["AKVC Smoke"],
                            "avfoundation_devices": ["AKVC Smoke"],
                            "cmio_devices": ["AKVC Smoke"],
                            "camera_access_status": "authorized",
                            "camera_access_authorized": True,
                            "camera_access_denied": False,
                            "environment_device_enumeration_empty": False,
                        },
                        "requested_frames": 9,
                        "frames_sent": 9,
                        "direct_only": True,
                        "probe_only": False,
                        "direct_sender_device_snapshot": {
                            "all_devices": ["AKVC Smoke"],
                            "avfoundation_devices": ["AKVC Smoke"],
                            "cmio_devices": ["AKVC Smoke"],
                            "camera_access_status": "authorized",
                            "camera_access_authorized": True,
                            "camera_access_denied": False,
                            "environment_device_enumeration_empty": False,
                        },
                    },
                },
                "direct_sender_object_demo": {
                    "attempted": True,
                    "skipped": False,
                    "returncode": 0,
                    "request": {
                        "requested_frames": 5,
                        "requested_frame_kind": "bytes-bgr",
                        "requested_camera_access": True,
                    },
                    "payload": {
                        "mode": "direct-sender-object",
                        "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
                        "requested_frame_kind": "bytes-bgr",
                        "backend_name": "direct_sender_object",
                        "using_direct_sender": True,
                        "direct_sender_attempted": True,
                        "direct_sender_state": "active",
                        "runtime_topology_kind": "camera_extension_direct_sender_object",
                        "runtime_data_plane": "cmio_sink_stream_direct",
                        "runtime_control_plane": "system_extension_preinstalled",
                        "direct_sender_target_name": "AKVC Smoke Object",
                        "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                        "camera_name": "AKVC Smoke Object",
                        "requested_frames": 5,
                        "frames_sent": 5,
                        "direct_only": True,
                        "inspect_only": False,
                        "helper_hot_path_used": False,
                        "shared_memory_fallback_used": False,
                        "device_snapshot": {
                            "all_devices": ["AKVC Smoke Object"],
                            "camera_access_status": "authorized",
                            "camera_access_authorized": True,
                            "camera_access_denied": False,
                            "environment_device_enumeration_empty": False,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    install_session_report.write_text(
        json.dumps(
            {
                "direct_push_demo": {
                    "attempted": False,
                    "skipped": True,
                    "skip_reason": "ipc_environment_blocked",
                    "returncode": 0,
                    "request": {
                        "requested_frames": 7,
                        "requested_frame_kind": "qimage-bgra",
                        "requested_entrypoint": "send-widget",
                        "allow_shared_memory_fallback": True,
                        "requested_camera_access": True,
                    },
                    "payload": {
                        "mode": "direct-push",
                        "python_entrypoint_kind": "push_frame",
                        "requested_frame_kind": "qimage-bgra",
                        "requested_entrypoint": "send-widget",
                        "sdk_direct_push_used": True,
                        "backend_name": "shared_memory",
                        "using_direct_sender": False,
                        "direct_sender_attempted": True,
                        "direct_sender_state": "fallback_shared_memory",
                        "runtime_topology_kind": "camera_extension_direct_framebus",
                        "runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
                        "runtime_host_role": "container_activation_command_bridge",
                        "runtime_host_in_frame_hot_path": False,
                        "helper_hot_path_used": False,
                        "shared_memory_fallback_used": True,
                        "runtime_dedicated_host_daemon_required": False,
                        "runtime_container_app_configured": True,
                        "runtime_data_plane": "shared_memory_ringbuffer",
                        "runtime_control_plane": "host_activation_plus_sync_ipc",
                        "direct_sender_target_name": "AKVC Direct",
                        "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                        "direct_sender_last_error": "camera device not found: AKVC Direct",
                        "requested_camera_access": True,
                        "requested_camera_access_snapshot": {
                            "all_devices": [],
                            "avfoundation_devices": [],
                            "cmio_devices": [],
                            "camera_access_status": "denied",
                            "camera_access_authorized": False,
                            "camera_access_denied": True,
                            "environment_device_enumeration_empty": True,
                        },
                        "requested_frames": 7,
                        "frames_sent": 0,
                        "direct_only": True,
                        "probe_only": True,
                        "error": "camera device not found: AKVC Direct",
                        "direct_sender_device_snapshot": {
                            "all_devices": [],
                            "avfoundation_devices": [],
                            "cmio_devices": [],
                            "camera_access_status": "denied",
                            "camera_access_authorized": False,
                            "camera_access_denied": True,
                            "environment_device_enumeration_empty": True,
                        },
                    },
                    "probe_payload": {
                        "mode": "direct-push",
                        "probe_only": True,
                    },
                },
                "direct_sender_object_demo": {
                    "attempted": False,
                    "skipped": True,
                    "skip_reason": "ipc_environment_blocked",
                    "returncode": 0,
                    "request": {
                        "requested_frames": 4,
                        "requested_frame_kind": "bytes-bgra",
                        "requested_camera_access": True,
                    },
                    "payload": {
                        "mode": "direct-sender-object",
                        "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)",
                        "requested_frame_kind": "bytes-bgra",
                        "backend_name": "direct_sender_object",
                        "using_direct_sender": True,
                        "direct_sender_attempted": True,
                        "direct_sender_state": "inspected",
                        "runtime_topology_kind": "camera_extension_direct_sender_object",
                        "runtime_data_plane": "cmio_sink_stream_direct",
                        "runtime_control_plane": "system_extension_preinstalled",
                        "direct_sender_target_name": "AKVC Install Object",
                        "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib",
                        "requested_frames": 4,
                        "frames_sent": 0,
                        "direct_only": True,
                        "inspect_only": True,
                        "helper_hot_path_used": False,
                        "shared_memory_fallback_used": False,
                        "device_snapshot": {
                            "all_devices": [],
                            "camera_access_status": "denied",
                            "camera_access_authorized": False,
                            "camera_access_denied": True,
                            "environment_device_enumeration_empty": True,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=tmp_path / "validation-report.json",
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=smoke_report,
        install_session_report=install_session_report,
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["smoke_direct_push_demo_present"] is True
    assert summary["smoke_direct_push_demo_attempted"] is True
    assert summary["smoke_direct_push_demo_skipped"] is False
    assert summary["smoke_direct_push_demo_returncode"] == 0
    assert summary["smoke_direct_push_demo_mode"] == "direct-push"
    assert summary["smoke_direct_push_demo_python_entrypoint_kind"] == "push_frame"
    assert summary["smoke_direct_push_demo_requested_frame_kind"] == "qimage-bgra"
    assert summary["smoke_direct_push_demo_requested_entrypoint"] == "send-widget"
    assert summary["smoke_direct_push_demo_sdk_direct_push_used"] is True
    assert summary["smoke_direct_push_demo_backend_name"] == "direct_sender"
    assert summary["smoke_direct_push_demo_using_direct_sender"] is True
    assert summary["smoke_direct_push_demo_direct_sender_attempted"] is True
    assert summary["smoke_direct_push_demo_direct_sender_state"] == "active"
    assert summary["smoke_direct_push_demo_runtime_topology_kind"] == "camera_extension_direct_sender"
    assert summary["smoke_direct_push_demo_helper_hot_path_used"] is False
    assert summary["smoke_direct_push_demo_shared_memory_fallback_used"] is False
    assert summary["smoke_direct_push_demo_runtime_data_plane"] == "cmio_sink_stream_direct"
    assert summary["smoke_direct_push_demo_runtime_control_plane"] == "host_activation_only"
    assert summary["smoke_direct_push_demo_direct_sender_target_name"] == "AKVC Smoke"
    assert summary["smoke_direct_push_demo_direct_sender_library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert summary["smoke_direct_push_demo_direct_sender_last_error"] is None
    assert summary["smoke_direct_push_demo_camera_name"] == "AKVC Smoke"
    assert summary["smoke_direct_push_demo_consumer_count"] == 1
    assert summary["smoke_direct_push_demo_requested_frames"] == 9
    assert summary["smoke_direct_push_demo_frames_sent"] == 9
    assert summary["smoke_direct_push_demo_direct_only"] is True
    assert summary["smoke_direct_push_demo_probe_only"] is False
    assert summary["smoke_direct_push_demo_allow_shared_memory_fallback"] is True
    assert summary["smoke_direct_push_demo_requested_camera_access"] is True
    assert summary["smoke_direct_push_demo_requested_camera_access_snapshot_present"] is True
    assert summary["smoke_direct_push_demo_requested_camera_access_status"] == "authorized"
    assert summary["smoke_direct_push_demo_requested_camera_access_authorized"] is True
    assert summary["smoke_direct_push_demo_requested_camera_access_denied"] is False
    assert summary["smoke_direct_push_demo_requested_camera_access_environment_device_enumeration_empty"] is False
    assert summary["smoke_direct_push_demo_requested_camera_access_visible_all_devices"] == ["AKVC Smoke"]
    assert summary["smoke_direct_push_demo_camera_access_status"] == "authorized"
    assert summary["smoke_direct_push_demo_camera_access_authorized"] is True
    assert summary["smoke_direct_push_demo_camera_access_denied"] is False
    assert summary["smoke_direct_push_demo_environment_device_enumeration_empty"] is False
    assert summary["smoke_direct_push_demo_visible_all_devices"] == ["AKVC Smoke"]
    assert summary["smoke_direct_sender_object_demo_present"] is True
    assert summary["smoke_direct_sender_object_demo_mode"] == "direct-sender-object"
    assert summary["smoke_direct_sender_object_demo_backend_name"] == "direct_sender_object"
    assert summary["smoke_direct_sender_object_demo_requested_frames"] == 5
    assert summary["smoke_direct_sender_object_demo_frames_sent"] == 5
    assert summary["smoke_direct_sender_object_demo_helper_hot_path_used"] is False
    assert summary["smoke_direct_sender_object_demo_shared_memory_fallback_used"] is False
    assert summary["smoke_direct_sender_object_demo_visible_all_devices"] == ["AKVC Smoke Object"]
    assert summary["install_session_direct_push_demo_present"] is True
    assert summary["install_session_direct_push_demo_attempted"] is False
    assert summary["install_session_direct_push_demo_skipped"] is True
    assert summary["install_session_direct_push_demo_skip_reason"] == "ipc_environment_blocked"
    assert summary["install_session_direct_push_demo_returncode"] == 0
    assert summary["install_session_direct_push_demo_mode"] == "direct-push"
    assert summary["install_session_direct_push_demo_python_entrypoint_kind"] == "push_frame"
    assert summary["install_session_direct_push_demo_requested_frame_kind"] == "qimage-bgra"
    assert summary["install_session_direct_push_demo_requested_entrypoint"] == "send-widget"
    assert summary["install_session_direct_push_demo_sdk_direct_push_used"] is True
    assert summary["install_session_direct_push_demo_backend_name"] == "shared_memory"
    assert summary["install_session_direct_push_demo_using_direct_sender"] is False
    assert summary["install_session_direct_push_demo_direct_sender_attempted"] is True
    assert summary["install_session_direct_push_demo_direct_sender_state"] == "fallback_shared_memory"
    assert summary["install_session_direct_push_demo_runtime_topology_kind"] == "camera_extension_direct_framebus"
    assert summary["install_session_direct_push_demo_helper_hot_path_used"] is False
    assert summary["install_session_direct_push_demo_shared_memory_fallback_used"] is True
    assert summary["install_session_direct_push_demo_runtime_data_plane"] == "shared_memory_ringbuffer"
    assert summary["install_session_direct_push_demo_runtime_control_plane"] == "host_activation_plus_sync_ipc"
    assert summary["install_session_direct_push_demo_direct_sender_target_name"] == "AKVC Direct"
    assert summary["install_session_direct_push_demo_direct_sender_library_path"] == "/tmp/libakvc-macos-direct-sender.dylib"
    assert summary["install_session_direct_push_demo_direct_sender_last_error"] == "camera device not found: AKVC Direct"
    assert summary["install_session_direct_push_demo_requested_frames"] == 7
    assert summary["install_session_direct_push_demo_frames_sent"] == 0
    assert summary["install_session_direct_push_demo_direct_only"] is True
    assert summary["install_session_direct_push_demo_probe_only"] is True
    assert summary["install_session_direct_push_demo_allow_shared_memory_fallback"] is True
    assert summary["install_session_direct_push_demo_requested_camera_access"] is True
    assert summary["install_session_direct_push_demo_requested_camera_access_snapshot_present"] is True
    assert summary["install_session_direct_push_demo_requested_camera_access_status"] == "denied"
    assert summary["install_session_direct_push_demo_requested_camera_access_authorized"] is False
    assert summary["install_session_direct_push_demo_requested_camera_access_denied"] is True
    assert summary["install_session_direct_push_demo_requested_camera_access_environment_device_enumeration_empty"] is True
    assert summary["install_session_direct_push_demo_requested_camera_access_visible_all_devices"] == []
    assert summary["install_session_direct_push_demo_error"] == "camera device not found: AKVC Direct"
    assert summary["install_session_direct_push_demo_probe_payload_present"] is True
    assert summary["install_session_direct_push_demo_camera_access_status"] == "denied"
    assert summary["install_session_direct_push_demo_camera_access_authorized"] is False
    assert summary["install_session_direct_push_demo_camera_access_denied"] is True
    assert summary["install_session_direct_push_demo_environment_device_enumeration_empty"] is True
    assert summary["install_session_direct_push_demo_visible_all_devices"] == []
    assert summary["install_session_direct_sender_object_demo_present"] is True
    assert summary["install_session_direct_sender_object_demo_skipped"] is True
    assert summary["install_session_direct_sender_object_demo_skip_reason"] == "ipc_environment_blocked"
    assert summary["install_session_direct_sender_object_demo_mode"] == "direct-sender-object"
    assert summary["install_session_direct_sender_object_demo_direct_sender_state"] == "inspected"
    assert summary["install_session_direct_sender_object_demo_requested_frames"] == 4
    assert summary["install_session_direct_sender_object_demo_frames_sent"] == 0
    assert summary["install_session_direct_sender_object_demo_visible_all_devices"] == []


def test_macos_validation_session_tool_runs_direct_push_demo_when_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    session_dir = tmp_path / "session"
    host_bundle = tmp_path / "Applications" / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    direct_sender_library = tmp_path / "libakvc-macos-direct-sender.dylib"
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("", encoding="utf-8")
    direct_sender_library.write_text("", encoding="utf-8")
    direct_push_tool = tmp_path / "direct-push-demo.py"
    direct_sender_object_tool = tmp_path / "direct-sender-object-demo.py"
    report_tool = tmp_path / "report.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_tool = tmp_path / "acceptance.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    sdk_contract_tool = tmp_path / "sdk-contract.py"
    summary_tool = tmp_path / "summary.py"
    entrypoints_contract_tool = tmp_path / "entrypoints-contract.py"

    write_tool(
        direct_push_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--frames" in args
assert args[args.index("--frames") + 1] == "12"
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
output.write_text(json.dumps({"mode": "direct-push", "frame_source_kind": "numpy.ndarray", "python_entrypoint_kind": "push_frame", "requested_frame_kind": "qimage-bgra", "requested_entrypoint": "send-widget", "allow_shared_memory_fallback": True, "sdk_direct_push_used": True, "backend_name": "direct_sender", "using_direct_sender": True, "direct_sender_attempted": True, "direct_sender_state": "active", "runtime_topology_kind": "camera_extension_direct_sender", "runtime_frame_path": "python_sdk -> cmio_sink_stream_direct -> camera_extension -> system_camera_device -> client_app", "runtime_host_role": "container_activation_command_bridge", "runtime_host_in_frame_hot_path": False, "runtime_dedicated_host_daemon_required": False, "runtime_container_app_configured": True, "runtime_data_plane": "cmio_sink_stream_direct", "runtime_control_plane": "host_activation_only", "camera_name": "AKVC Direct", "consumer_count": 2, "requested_camera_access": True, "requested_camera_access_snapshot": {"camera_access_status": "authorized", "environment_device_enumeration_empty": False, "all_devices": ["AKVC Direct"]}, "requested_frames": 12, "frames_sent": 12, "runtime_snapshot": {"started": True, "camera_name": "AKVC Direct", "backend_name": "direct_sender", "using_direct_sender": True, "shared_memory_name": "/akvc-direct", "last_frame_format_name": "BGRA32", "runtime_topology": {"runtime_topology_kind": "camera_extension_direct_sender", "runtime_data_plane": "cmio_sink_stream_direct", "runtime_control_plane": "host_activation_only"}}}), encoding="utf-8")
""",
    )
    write_tool(
        direct_sender_object_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--frames" in args
assert args[args.index("--frames") + 1] == "6"
assert "--direct-sender-library" in args
assert args[args.index("--direct-sender-library") + 1].endswith("libakvc-macos-direct-sender.dylib")
assert "--frame-kind" in args
assert args[args.index("--frame-kind") + 1] == "numpy-direct"
assert "--request-camera-access" in args
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "direct-sender-object", "python_entrypoint_kind": "MacDirectCameraSender.send(auto-open)", "requested_frame_kind": "numpy-direct", "backend_name": "direct_sender_object", "using_direct_sender": True, "direct_sender_attempted": True, "direct_sender_state": "active", "runtime_topology_kind": "camera_extension_direct_sender_object", "runtime_data_plane": "cmio_sink_stream_direct", "runtime_control_plane": "system_extension_preinstalled", "camera_name": "AKVC Object", "requested_frames": 6, "frames_sent": 6, "direct_only": True, "inspect_only": False, "helper_hot_path_used": False, "shared_memory_fallback_used": False, "direct_sender_library_path": "/tmp/libakvc-macos-direct-sender.dylib", "device_snapshot": {"camera_access_status": "authorized", "environment_device_enumeration_empty": False, "all_devices": ["AKVC Object"]}}), encoding="utf-8")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"status_start_ready": True, "status_start_blocker_code": "ready"}}), encoding="utf-8")
""",
    )
    write_tool(
        entrypoints_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True, "surface_complete": True, "demo_case_complete": True, "direct_push_demo_case_complete": True, "cli_case_complete": True, "desktop_case_complete": True}}), encoding="utf-8")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
""",
    )
    write_tool(
        acceptance_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"summary": {"acceptance_ready": False, "passed_count": 0, "failed_count": 0, "unknown_count": 0, "failed_criteria": [], "unknown_criteria": []}}), encoding="utf-8")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
""",
    )
    write_tool(
        sdk_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True, "constructor_shape_aligned": True, "direct_sender_exports_present": True}}), encoding="utf-8")
""",
    )
    write_tool(
        summary_tool,
        """#!/usr/bin/env python3
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("# Session Summary\\n", encoding="utf-8")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--direct-push-demo-tool",
            str(direct_push_tool),
            "--direct-push-frames",
            "12",
            "--direct-push-frame-kind",
            "qimage-bgra",
            "--direct-push-entrypoint",
            "send-widget",
            "--direct-push-allow-shared-memory-fallback",
            "--validation-report-tool",
            str(report_tool),
            "--app-bundle",
            str(host_bundle),
            "--app-executable",
            str(host_executable),
            "--direct-sender-library",
            str(direct_sender_library),
            "--direct-push-request-camera-access",
            "--direct-sender-object-demo-tool",
            str(direct_sender_object_tool),
            "--direct-sender-object-frames",
            "6",
            "--direct-sender-object-frame-kind",
            "numpy-direct",
            "--direct-sender-object-request-camera-access",
            "--entrypoints-contract-tool",
            str(entrypoints_contract_tool),
            "--artifact-check-tool",
                str(artifact_check_tool),
                "--acceptance-tool",
                str(acceptance_tool),
                "--acceptance-contract-tool",
                str(acceptance_contract_tool),
                "--sdk-contract-tool",
                str(sdk_contract_tool),
                "--summary-tool",
                str(summary_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-direct-push-demo",
            "--run-direct-sender-object-demo",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["direct_push_demo"]["returncode"] == 0
    assert manifest["steps"]["direct_push_demo"]["request"] == {
        "requested_frames": 12,
        "requested_frame_kind": "qimage-bgra",
        "requested_entrypoint": "send-widget",
        "allow_shared_memory_fallback": True,
        "requested_camera_access": True,
    }
    assert manifest["summary"]["direct_push_demo_present"] is True
    assert manifest["summary"]["direct_push_demo_mode"] == "direct-push"
    assert manifest["summary"]["direct_push_demo_python_entrypoint_kind"] == "push_frame"
    assert manifest["summary"]["direct_push_demo_requested_frame_kind"] == "qimage-bgra"
    assert manifest["summary"]["direct_push_demo_requested_entrypoint"] == "send-widget"
    assert manifest["summary"]["direct_push_demo_sdk_direct_push_used"] is True
    assert manifest["summary"]["direct_push_demo_allow_shared_memory_fallback"] is True
    assert manifest["summary"]["direct_push_demo_requested_camera_access"] is True
    assert manifest["summary"]["direct_push_demo_requested_camera_access_status"] == "authorized"
    assert manifest["summary"]["direct_push_demo_requested_frames"] == 12
    assert manifest["summary"]["direct_push_demo_frames_sent"] == 12
    assert manifest["summary"]["direct_push_demo_runtime_snapshot_present"] is True
    assert manifest["summary"]["direct_push_demo_runtime_snapshot_started"] is True
    assert manifest["summary"]["direct_push_demo_runtime_snapshot_shared_memory_name"] == "/akvc-direct"
    assert manifest["summary"]["direct_push_demo_runtime_snapshot_last_frame_format_name"] == "BGRA32"
    assert manifest["steps"]["direct_sender_object_demo"]["returncode"] == 0
    assert manifest["steps"]["direct_sender_object_demo"]["request"] == {
        "requested_frames": 6,
        "requested_frame_kind": "numpy-direct",
        "requested_camera_access": True,
    }
    assert manifest["summary"]["direct_sender_object_demo_present"] is True
    assert manifest["summary"]["direct_sender_object_demo_mode"] == "direct-sender-object"
    assert (
        manifest["summary"]["direct_sender_object_demo_python_entrypoint_kind"]
        == "MacDirectCameraSender.send(auto-open)"
    )
    assert manifest["summary"]["direct_sender_object_demo_requested_frame_kind"] == "numpy-direct"
    assert manifest["summary"]["direct_sender_object_demo_using_direct_sender"] is True
    assert manifest["summary"]["direct_sender_object_demo_helper_hot_path_used"] is False
    assert manifest["summary"]["direct_sender_object_demo_shared_memory_fallback_used"] is False
    assert manifest["summary"]["direct_sender_object_demo_requested_frames"] == 6
    assert manifest["summary"]["direct_sender_object_demo_frames_sent"] == 6
    assert manifest["summary"]["runtime_topology_kind"] == "camera_extension_direct_sender"
    assert manifest["summary"]["runtime_data_plane"] == "cmio_sink_stream_direct"
    assert manifest["summary"]["runtime_control_plane"] == "host_activation_only"
    assert (session_dir / "direct-push-report.json").is_file()
    assert (session_dir / "direct-sender-object-report.json").is_file()


def test_macos_validation_session_tool_runs_status_binary_check_when_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    status_binary_check_tool = tmp_path / "status-binary-check.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"
    status_tool = tmp_path / "akvc-macos-status"
    status_tool.write_text("placeholder", encoding="utf-8")

    write_tool(
        status_binary_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--status-tool" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "consistency": {"all_checks_passed": True, "ipc_keys_present": True},
    "payload": {"ipc_environment_blocked": True, "ipc_direct_open_errno": 13}
}), encoding="utf-8")
print("status-binary-check-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--status-binary-check-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"status_binary_check_present": True}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--status-tool",
            str(status_tool),
            "--status-binary-check-tool",
            str(status_binary_check_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-status-binary-check",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["status_binary_check"]["returncode"] == 0
    assert manifest["summary"]["status_binary_check_present"] is True
    assert manifest["summary"]["status_binary_check_passed"] is True
    assert manifest["summary"]["status_binary_check_ipc_environment_blocked"] is True
    assert manifest["summary"]["status_binary_check_ipc_direct_open_errno"] == 13
    assert manifest["summary"]["artifact_check_present"] is True
    assert manifest["summary"]["artifact_check_passed"] is True
    assert manifest["summary"]["acceptance_present"] is True
    assert manifest["summary"]["effective_start_ready"] is False
    assert manifest["summary"]["effective_start_blocker_code"] == "ipc_environment_blocked"
    assert (session_dir / "status-binary-check.json").is_file()


def test_macos_validation_session_tool_runs_list_devices_binary_check_when_requested(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    list_devices_binary_check_tool = tmp_path / "list-devices-binary-check.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    list_devices_tool.write_text("placeholder", encoding="utf-8")

    write_tool(
        list_devices_binary_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--list-devices-tool" in args
assert "--expected-prefix" in args
assert args[args.index("--expected-prefix") + 1] == "AKVC Demo"
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "consistency": {"all_checks_passed": True},
    "expected_prefix": "AKVC Demo",
    "payload": {
        "device_prefix": "AKVC Demo",
        "devices": ["AKVC Demo"],
        "all_devices": ["AKVC Demo", "FaceTime HD Camera"]
    },
    "probe_cases": [
        {
            "name": "override_prefix_no_match",
            "payload": {
                "device_prefix": "__AKVC_BINARY_CHECK_NO_MATCH__",
                "devices": [],
                "all_devices": ["AKVC Demo", "FaceTime HD Camera"]
            },
            "consistency": {"all_checks_passed": True}
        }
    ]
}), encoding="utf-8")
print("list-devices-binary-check-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--list-devices-binary-check-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--list-devices-tool",
            str(list_devices_tool),
            "--list-devices-binary-check-tool",
            str(list_devices_binary_check_tool),
            "--validation-report-tool",
            str(report_tool),
            "--name",
            "AKVC Demo",
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-list-devices-binary-check",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["list_devices_binary_check"]["returncode"] == 0
    assert manifest["summary"]["list_devices_binary_check_present"] is True
    assert manifest["summary"]["list_devices_binary_check_passed"] is True
    assert manifest["summary"]["list_devices_binary_check_device_prefix"] == "AKVC Demo"
    assert manifest["summary"]["list_devices_binary_check_filtered_device_count"] == 1
    assert manifest["summary"]["list_devices_binary_check_total_device_count"] == 2
    assert manifest["summary"]["list_devices_binary_check_override_no_match_ok"] is True
    assert manifest["summary"]["artifact_check_present"] is True
    assert manifest["summary"]["artifact_check_passed"] is True
    assert manifest["summary"]["acceptance_present"] is True
    assert (session_dir / "list-devices-binary-check.json").is_file()


def test_validation_session_summary_surfaces_status_binary_producer_errno_1(tmp_path) -> None:
    status_binary_check_report = tmp_path / "status-binary-check.json"
    status_binary_check_report.write_text(
        json.dumps(
            {
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
            }
        ),
        encoding="utf-8",
    )

    manifest = session_tool._build_manifest_summary(
        validation_report=tmp_path / "validation-report.json",
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=status_binary_check_report,
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert manifest["status_binary_check_present"] is True
    assert manifest["status_binary_check_passed"] is True
    assert manifest["status_binary_check_ipc_environment_blocked"] is True
    assert manifest["status_binary_check_ipc_direct_open_errno"] == 1
    assert manifest["effective_start_ready"] is False
    assert manifest["effective_start_blocker_code"] == "ipc_environment_blocked"


def test_validation_session_summary_surfaces_supported_formats_and_frame_rates(tmp_path) -> None:
    validation_report = tmp_path / "validation-report.json"
    smoke_report = tmp_path / "smoke-report.json"
    install_session_report = tmp_path / "install-session-report.json"

    validation_report.write_text(
        json.dumps(
            {
                "status": {
                    "devices": ["AK Virtual Camera"],
                    "all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                    "device_prefix": "AK Virtual Camera",
                    "shared_memory_name": "/akvc-validation",
                    "mach_service_name": "com.akvc.validation",
                    "ipc_transport": "validation_transport",
                    "supported_formats": ["1280x720@30/60 NV12"],
                    "supported_frame_rates": [30, 60],
                },
                "install": {
                    "status_devices": ["AK Virtual Camera"],
                    "status_all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                    "device_prefix": "AK Virtual Camera",
                },
                "summary": {
                    "status_start_ready": True,
                    "status_start_blocker_code": "ready",
                },
            }
        ),
        encoding="utf-8",
    )
    smoke_report.write_text(
        json.dumps(
            {
                "status": {
                    "devices": [],
                    "all_devices": ["FaceTime HD Camera"],
                    "device_prefix": "AK Virtual Camera",
                    "shared_memory_name": "/akvc-smoke",
                    "mach_service_name": "com.akvc.smoke",
                    "ipc_transport": "smoke_transport",
                    "supported_formats": ["1920x1080@30/60 NV12"],
                    "supported_frame_rates": [30, 60],
                },
                "install": {"success": True},
            }
        ),
        encoding="utf-8",
    )
    install_session_report.write_text(
        json.dumps(
            {
                "install": {"success": True},
                "post_status": {
                    "devices": [],
                    "all_devices": ["FaceTime HD Camera"],
                    "device_prefix": "AK Virtual Camera",
                    "shared_memory_name": "/akvc-install-session",
                    "mach_service_name": "com.akvc.install-session",
                    "ipc_transport": "install_session_transport",
                    "supported_formats": ["3840x2160@30/60 NV12"],
                    "supported_frame_rates": ["30", "60"],
                },
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=smoke_report,
        install_session_report=install_session_report,
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["validation_supported_formats"] == ["1280x720@30/60 NV12"]
    assert summary["validation_supported_frame_rates"] == [30, 60]
    assert summary["validation_devices"] == ["AK Virtual Camera"]
    assert summary["validation_all_devices"] == ["FaceTime HD Camera", "AK Virtual Camera"]
    assert summary["validation_device_prefix"] == "AK Virtual Camera"
    assert summary["validation_shared_memory_name"] == "/akvc-validation"
    assert summary["validation_mach_service_name"] == "com.akvc.validation"
    assert summary["validation_ipc_transport"] == "validation_transport"
    assert summary["validation_install_status_devices"] == ["AK Virtual Camera"]
    assert summary["validation_install_status_all_devices"] == ["FaceTime HD Camera", "AK Virtual Camera"]
    assert summary["validation_install_device_prefix"] == "AK Virtual Camera"
    assert summary["smoke_devices"] == []
    assert summary["smoke_all_devices"] == ["FaceTime HD Camera"]
    assert summary["smoke_device_prefix"] == "AK Virtual Camera"
    assert summary["smoke_supported_formats"] == ["1920x1080@30/60 NV12"]
    assert summary["smoke_supported_frame_rates"] == [30, 60]
    assert summary["smoke_shared_memory_name"] == "/akvc-smoke"
    assert summary["smoke_mach_service_name"] == "com.akvc.smoke"
    assert summary["smoke_ipc_transport"] == "smoke_transport"
    assert summary["install_session_devices"] == []
    assert summary["install_session_all_devices"] == ["FaceTime HD Camera"]
    assert summary["install_session_device_prefix"] == "AK Virtual Camera"
    assert summary["install_session_supported_formats"] == ["3840x2160@30/60 NV12"]
    assert summary["install_session_supported_frame_rates"] == [30, 60]
    assert summary["install_session_shared_memory_name"] == "/akvc-install-session"
    assert summary["install_session_mach_service_name"] == "com.akvc.install-session"
    assert summary["install_session_ipc_transport"] == "install_session_transport"
    assert summary["effective_devices"] == []
    assert summary["effective_all_devices"] == ["FaceTime HD Camera"]
    assert summary["effective_device_prefix"] == "AK Virtual Camera"
    assert summary["effective_shared_memory_name"] == "/akvc-install-session"
    assert summary["effective_mach_service_name"] == "com.akvc.install-session"
    assert summary["effective_ipc_transport"] == "install_session_transport"
    assert summary["effective_supported_formats"] == ["3840x2160@30/60 NV12"]
    assert summary["effective_supported_frame_rates"] == [30, 60]


def test_validation_session_summary_merges_artifact_check_status() -> None:
    merged = session_tool._merge_artifact_check_summary(
        {"effective_start_blocker_code": "ready"},
        {"consistency": {"all_checks_passed": True}},
    )
    assert merged["artifact_check_present"] is True
    assert merged["artifact_check_passed"] is True

    missing = session_tool._merge_artifact_check_summary(
        {"effective_start_blocker_code": "ready"},
        None,
    )
    assert missing["artifact_check_present"] is False
    assert missing["artifact_check_passed"] is None


def test_validation_session_summary_merges_entrypoints_contract_status() -> None:
    merged = session_tool._merge_entrypoints_contract_summary(
        {"effective_start_blocker_code": "ready"},
        {
            "consistency": {
                "all_checks_passed": True,
                "surface_complete": True,
                "demo_case_complete": True,
                "cli_case_complete": True,
                "desktop_case_complete": True,
            }
        },
    )
    assert merged["entrypoints_contract_present"] is True
    assert merged["entrypoints_contract_passed"] is True
    assert merged["entrypoints_contract_surface_complete"] is True
    assert merged["entrypoints_contract_demo_case_complete"] is True
    assert merged["entrypoints_contract_cli_case_complete"] is True
    assert merged["entrypoints_contract_desktop_case_complete"] is True

    missing = session_tool._merge_entrypoints_contract_summary(
        {"effective_start_blocker_code": "ready"},
        None,
    )
    assert missing["entrypoints_contract_present"] is False
    assert missing["entrypoints_contract_passed"] is None
    assert missing["entrypoints_contract_surface_complete"] is None
    assert missing["entrypoints_contract_demo_case_complete"] is None
    assert missing["entrypoints_contract_cli_case_complete"] is None
    assert missing["entrypoints_contract_desktop_case_complete"] is None


def test_validation_session_summary_merges_sdk_contract_status() -> None:
    merged = session_tool._merge_sdk_contract_summary(
        {"effective_start_blocker_code": "ready"},
        {
            "consistency": {
                "all_checks_passed": True,
                "constructor_shape_aligned": True,
                "direct_sender_exports_present": True,
            }
        },
    )
    assert merged["sdk_contract_present"] is True
    assert merged["sdk_contract_passed"] is True
    assert merged["sdk_contract_constructor_shape_aligned"] is True
    assert merged["sdk_contract_direct_sender_exports_present"] is True

    missing = session_tool._merge_sdk_contract_summary(
        {"effective_start_blocker_code": "ready"},
        None,
    )
    assert missing["sdk_contract_present"] is False
    assert missing["sdk_contract_passed"] is None
    assert missing["sdk_contract_constructor_shape_aligned"] is None
    assert missing["sdk_contract_direct_sender_exports_present"] is None


def test_validation_session_summary_surfaces_list_devices_binary_details(tmp_path) -> None:
    list_devices_binary_check_report = tmp_path / "list-devices-binary-check.json"
    list_devices_binary_check_report.write_text(
        json.dumps(
            {
                "consistency": {"all_checks_passed": True},
                "payload": {
                    "device_prefix": "AK Virtual Camera",
                    "devices": ["AK Virtual Camera"],
                    "all_devices": ["AK Virtual Camera", "FaceTime HD Camera"],
                },
                "probe_cases": [
                    {
                        "name": "override_prefix_no_match",
                        "payload": {
                            "device_prefix": "__AKVC_BINARY_CHECK_NO_MATCH__",
                            "devices": [],
                            "all_devices": ["AK Virtual Camera", "FaceTime HD Camera"],
                        },
                        "consistency": {"all_checks_passed": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=tmp_path / "validation-report.json",
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=list_devices_binary_check_report,
    )

    assert summary["list_devices_binary_check_present"] is True
    assert summary["list_devices_binary_check_passed"] is True
    assert summary["list_devices_binary_check_device_prefix"] == "AK Virtual Camera"
    assert summary["list_devices_binary_check_filtered_device_count"] == 1
    assert summary["list_devices_binary_check_total_device_count"] == 2
    assert summary["list_devices_binary_check_override_no_match_ok"] is True


def test_validation_session_summary_merges_acceptance_status() -> None:
    merged = session_tool._merge_acceptance_summary(
        {"effective_start_blocker_code": "ready"},
        {
            "summary": {
                "acceptance_ready": False,
                "passed_count": 3,
                "failed_count": 1,
                "unknown_count": 2,
                "failed_criteria": ["target_apps_all_passed"],
                "unknown_criteria": [],
                "manual_app_validation_ready": False,
                "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                "manual_app_validation_unknown_criteria": [],
                "manual_app_validation_blockers": ["system_camera_device_visible"],
            },
            "criteria": [
                {"name": "target_apps_all_passed", "status": "fail"},
                {"name": "system_camera_device_visible", "status": "pass"},
                {"name": "auto_install_ready", "status": "pass"},
                {"name": "python_entrypoints_consistent", "status": "pass"},
            ],
        },
    )
    assert merged["acceptance_present"] is True
    assert merged["acceptance_ready"] is False
    assert merged["acceptance_passed_count"] == 3
    assert merged["acceptance_failed_count"] == 1
    assert merged["acceptance_unknown_count"] == 2
    assert merged["acceptance_failed_criteria"] == ["target_apps_all_passed"]
    assert merged["acceptance_unknown_criteria"] == []
    assert merged["manual_app_validation_ready"] is False
    assert merged["manual_app_validation_failed_criteria"] == ["system_camera_device_visible"]
    assert merged["manual_app_validation_unknown_criteria"] == []
    assert merged["manual_app_validation_blockers"] == ["system_camera_device_visible"]
    assert merged["target_apps_all_passed"] == "fail"
    assert merged["system_camera_device_visible"] == "pass"
    assert merged["auto_install_ready"] == "pass"
    assert merged["python_entrypoints_consistent"] == "pass"

    missing = session_tool._merge_acceptance_summary(
        {"effective_start_blocker_code": "ready"},
        None,
    )
    assert missing["acceptance_present"] is False
    assert missing["acceptance_ready"] is None
    assert missing["acceptance_passed_count"] is None
    assert missing["acceptance_failed_count"] is None
    assert missing["acceptance_unknown_count"] is None
    assert missing["acceptance_failed_criteria"] is None
    assert missing["acceptance_unknown_criteria"] is None
    assert missing["manual_app_validation_ready"] is None
    assert missing["manual_app_validation_failed_criteria"] is None
    assert missing["manual_app_validation_unknown_criteria"] is None
    assert missing["manual_app_validation_blockers"] is None
    assert missing["target_apps_all_passed"] is None
    assert missing["system_camera_device_visible"] is None
    assert missing["auto_install_ready"] is None
    assert missing["python_entrypoints_consistent"] is None


def test_validation_session_summary_surfaces_validation_report_app_result_ids(
    tmp_path,
) -> None:
    validation_report = tmp_path / "validation-report.json"
    validation_report.write_text(
        json.dumps(
            {
                "summary": {
                    "passed_app_ids": ["zoom"],
                    "failed_app_ids": ["teams"],
                    "pending_app_ids": ["google_meet"],
                    "skipped_app_ids": ["obs"],
                    "unreviewed_app_ids": ["quicktime", "facetime"],
                }
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["validation_passed_app_ids"] == ["zoom"]
    assert summary["validation_failed_app_ids"] == ["teams"]
    assert summary["validation_pending_app_ids"] == ["google_meet"]
    assert summary["validation_skipped_app_ids"] == ["obs"]
    assert summary["validation_unreviewed_app_ids"] == ["quicktime", "facetime"]


def test_validation_session_summary_surfaces_manual_validation_progress_flags(
    tmp_path,
) -> None:
    validation_report = tmp_path / "validation-report.json"
    validation_report.write_text(
        json.dumps(
            {
                "summary": {
                    "manual_validation_ready": True,
                    "manual_validation_complete": False,
                    "manual_validation_all_passed": False,
                }
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["validation_manual_validation_ready"] is True
    assert summary["validation_manual_validation_complete"] is False
    assert summary["validation_manual_validation_all_passed"] is False


def test_validation_session_summary_surfaces_runtime_release_product_set_consistency(
    tmp_path,
) -> None:
    validation_report = tmp_path / "validation-report.json"
    validation_report.write_text(
        json.dumps(
            {
                "summary": {
                    "release_app_bundle_path": "/Applications/Amaran Desktop.app",
                    "release_extension_bundle_path": "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension",
                    "release_sync_ipc_tool_path": "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc",
                    "release_pkg_path": "/tmp/VirtualCamera.pkg",
                    "runtime_release_host_bundle_identity_consistent": True,
                    "runtime_release_extension_bundle_identity_consistent": True,
                    "runtime_release_sync_ipc_tool_identity_consistent": True,
                    "runtime_release_pkg_identity_consistent": True,
                    "runtime_release_host_bundle_path_equal": True,
                    "runtime_release_extension_bundle_path_equal": True,
                    "runtime_release_sync_ipc_tool_path_equal": False,
                    "runtime_release_pkg_path_equal": True,
                    "runtime_release_product_identity_consistent": True,
                    "runtime_release_product_path_equal": False,
                }
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["release_app_bundle_path"] == "/Applications/Amaran Desktop.app"
    assert summary["release_extension_bundle_path"] == (
        "/Applications/Amaran Desktop.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    assert summary["release_sync_ipc_tool_path"] == "/Applications/Amaran Desktop.app/Contents/MacOS/akvc-macos-sync-ipc"
    assert summary["release_pkg_path"] == "/tmp/VirtualCamera.pkg"
    assert summary["runtime_release_product_identity_consistent"] is True
    assert summary["runtime_release_product_path_equal"] is False


def test_validation_session_summary_surfaces_validation_app_matrix(
    tmp_path,
) -> None:
    validation_report = tmp_path / "validation-report.json"
    validation_report.write_text(
        json.dumps(
            {
                "verification_targets": [
                    {
                        "id": "zoom",
                        "name": "Zoom",
                        "reviewed": True,
                        "validated": True,
                        "result": "pass",
                        "notes": "preview visible",
                        "ready": True,
                        "status": "ok",
                        "steps": ["Open Zoom > Settings > Video."],
                        "checks": ["Camera list shows AK Virtual Camera."],
                    },
                    {
                        "id": "teams",
                        "name": "Teams",
                        "reviewed": True,
                        "validated": False,
                        "result": "fail",
                        "notes": "device not shown",
                        "ready": True,
                        "status": "missing",
                        "steps": ["Open Teams > Settings > Devices."],
                        "checks": ["Device settings page shows AK Virtual Camera."],
                    },
                    {
                        "id": "google_meet",
                        "name": "Google Meet",
                        "reviewed": False,
                        "validated": False,
                        "result": "pending",
                        "notes": "",
                        "ready": True,
                        "status": "pending",
                        "steps": ["Open Google Meet video settings in Chrome or Edge."],
                        "checks": ["Browser camera selector shows AK Virtual Camera."],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["validation_app_matrix"] == {
        "zoom": {
            "name": "Zoom",
            "reviewed": True,
            "validated": True,
            "result": "pass",
            "notes": "preview visible",
            "ready": True,
            "status": "ok",
            "steps": ["Open Zoom > Settings > Video."],
            "checks": ["Camera list shows AK Virtual Camera."],
        },
        "teams": {
            "name": "Teams",
            "reviewed": True,
            "validated": False,
            "result": "fail",
            "notes": "device not shown",
            "ready": True,
            "status": "missing",
            "steps": ["Open Teams > Settings > Devices."],
            "checks": ["Device settings page shows AK Virtual Camera."],
        },
        "google_meet": {
            "name": "Google Meet",
            "reviewed": False,
            "validated": False,
            "result": "pending",
            "notes": "",
            "ready": True,
            "status": "pending",
            "steps": ["Open Google Meet video settings in Chrome or Edge."],
            "checks": ["Browser camera selector shows AK Virtual Camera."],
        },
    }


def test_validation_session_summary_derives_app_counts_and_ids_from_app_matrix(
    tmp_path,
) -> None:
    validation_report = tmp_path / "validation-report.json"
    validation_report.write_text(
        json.dumps(
            {
                "verification_targets": [
                    {"id": "zoom", "reviewed": True, "validated": True, "result": "pass"},
                    {"id": "teams", "reviewed": True, "validated": False, "result": "fail"},
                    {"id": "google_meet", "reviewed": False, "validated": False, "result": "pending"},
                    {"id": "obs", "reviewed": True, "validated": False, "result": "skipped"},
                    {"id": "quicktime", "reviewed": False, "validated": False, "result": "pending"},
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = session_tool._build_manifest_summary(
        validation_report=validation_report,
        release_diagnostics_report=tmp_path / "release-diagnostics.json",
        smoke_report=tmp_path / "smoke-report.json",
        install_session_report=tmp_path / "install-session-report.json",
        framebus_roundtrip_report=tmp_path / "framebus-roundtrip.json",
        status_binary_check_report=tmp_path / "status-binary-check.json",
        list_devices_binary_check_report=tmp_path / "list-devices-binary-check.json",
    )

    assert summary["validation_validated_apps"] == 3
    assert summary["validation_passed_apps"] == 1
    assert summary["validation_failed_apps"] == 1
    assert summary["validation_pending_apps"] == 2
    assert summary["validation_skipped_apps"] == 1
    assert summary["validation_passed_app_ids"] == ["zoom"]
    assert summary["validation_failed_app_ids"] == ["teams"]
    assert summary["validation_pending_app_ids"] == ["google_meet", "quicktime"]
    assert summary["validation_skipped_app_ids"] == ["obs"]
    assert summary["validation_unreviewed_app_ids"] == ["google_meet", "quicktime"]


def test_macos_validation_session_tool_runs_artifact_check_after_validation_report(
    tmp_path,
) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    artifact_check_tool = tmp_path / "artifact-check.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--manifest" in args
assert "--require-existing-artifacts" in args
output = Path(args[args.index("--output") + 1])
manifest = Path(args[args.index("--manifest") + 1])
payload = json.loads(manifest.read_text(encoding="utf-8"))
assert payload["summary"]["validation_report_present"] is True
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"status_start_ready": True, "status_start_blocker_code": "ready"}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["artifact_check"]["returncode"] == 0
    assert manifest["summary"]["artifact_check_present"] is True
    assert manifest["summary"]["artifact_check_passed"] is True
    assert (session_dir / "session-manifest-check.json").is_file()


def test_macos_validation_session_tool_runs_acceptance_after_artifact_check(
    tmp_path,
) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_tool = tmp_path / "acceptance.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        acceptance_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
manifest = Path(args[args.index("--manifest") + 1])
payload = json.loads(manifest.read_text(encoding="utf-8"))
assert payload["summary"]["artifact_check_present"] is True
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"summary": {"acceptance_ready": False, "passed_count": 3, "failed_count": 1, "unknown_count": 0, "failed_criteria": ["target_apps_all_passed"], "unknown_criteria": [], "manual_app_validation_ready": True, "manual_app_validation_failed_criteria": [], "manual_app_validation_unknown_criteria": [], "manual_app_validation_blockers": []}, "criteria": [{"name": "target_apps_all_passed", "status": "fail"}, {"name": "system_camera_device_visible", "status": "pass"}, {"name": "auto_install_ready", "status": "pass"}]}), encoding="utf-8")
print("acceptance-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"status_start_ready": True, "status_start_blocker_code": "ready"}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-tool",
            str(acceptance_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["acceptance"]["returncode"] == 0
    assert manifest["summary"]["acceptance_present"] is True
    assert manifest["summary"]["acceptance_ready"] is False
    assert manifest["summary"]["acceptance_passed_count"] == 3
    assert manifest["summary"]["acceptance_failed_count"] == 1
    assert manifest["summary"]["acceptance_unknown_count"] == 0
    assert manifest["summary"]["acceptance_failed_criteria"] == ["target_apps_all_passed"]
    assert manifest["summary"]["manual_app_validation_ready"] is True
    assert manifest["summary"]["manual_app_validation_blockers"] == []
    assert manifest["summary"]["target_apps_all_passed"] == "fail"
    assert manifest["summary"]["system_camera_device_visible"] == "pass"
    assert manifest["summary"]["auto_install_ready"] == "pass"
    assert (session_dir / "session-acceptance.json").is_file()


def test_macos_validation_session_tool_runs_acceptance_contract_after_acceptance(
    tmp_path,
) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_tool = tmp_path / "acceptance.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        acceptance_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"summary": {"acceptance_ready": False, "passed_count": 3, "failed_count": 1, "unknown_count": 0, "failed_criteria": ["target_apps_all_passed"], "unknown_criteria": [], "manual_app_validation_ready": True, "manual_app_validation_failed_criteria": [], "manual_app_validation_unknown_criteria": [], "manual_app_validation_blockers": []}, "criteria": [{"name": "target_apps_all_passed", "status": "fail"}, {"name": "system_camera_device_visible", "status": "pass"}, {"name": "auto_install_ready", "status": "pass"}]}), encoding="utf-8")
print("acceptance-ok")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
session_manifest = output.parent / "session-manifest.json"
payload = json.loads(session_manifest.read_text(encoding="utf-8"))
assert payload["summary"]["acceptance_present"] is True
assert payload["summary"]["acceptance_ready"] is False
assert payload["summary"]["manual_app_validation_ready"] is True
assert payload["summary"]["target_apps_all_passed"] == "fail"
assert payload["summary"]["system_camera_device_visible"] == "pass"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("acceptance-contract-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"status_start_ready": True, "status_start_blocker_code": "ready"}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-tool",
            str(acceptance_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["acceptance_contract"]["returncode"] == 0
    assert manifest["summary"]["acceptance_contract_present"] is True
    assert manifest["summary"]["acceptance_contract_passed"] is True
    assert (session_dir / "session-acceptance-contract.json").is_file()


def test_macos_validation_session_tool_runs_summary_after_acceptance(
    tmp_path,
) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    artifact_check_tool = tmp_path / "artifact-check.py"
    acceptance_tool = tmp_path / "acceptance.py"
    acceptance_contract_tool = tmp_path / "acceptance-contract.py"
    summary_tool = tmp_path / "summary.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )
    write_tool(
        acceptance_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"summary": {"acceptance_ready": False, "passed_count": 3, "failed_count": 1, "unknown_count": 0, "failed_criteria": ["target_apps_all_passed"], "unknown_criteria": [], "manual_app_validation_ready": True, "manual_app_validation_failed_criteria": [], "manual_app_validation_unknown_criteria": [], "manual_app_validation_blockers": []}, "criteria": [{"name": "target_apps_all_passed", "status": "fail"}, {"name": "system_camera_device_visible", "status": "pass"}, {"name": "auto_install_ready", "status": "pass"}]}), encoding="utf-8")
print("acceptance-ok")
""",
    )
    write_tool(
        acceptance_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
session_manifest = output.parent / "session-manifest.json"
payload = json.loads(session_manifest.read_text(encoding="utf-8"))
assert payload["summary"]["acceptance_present"] is True
assert payload["summary"]["target_apps_all_passed"] == "fail"
assert payload["summary"]["system_camera_device_visible"] == "pass"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("acceptance-contract-ok")
""",
    )
    write_tool(
        summary_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
manifest = Path(args[args.index("--manifest") + 1])
payload = json.loads(manifest.read_text(encoding="utf-8"))
assert payload["summary"]["acceptance_present"] is True
assert payload["summary"]["acceptance_ready"] is False
assert payload["summary"]["manual_app_validation_ready"] is True
assert payload["summary"]["target_apps_all_passed"] == "fail"
assert payload["summary"]["system_camera_device_visible"] == "pass"
assert payload["summary"]["auto_install_ready"] == "pass"
assert payload["summary"]["acceptance_contract_present"] is True
assert payload["summary"]["acceptance_contract_passed"] is True
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("# summary\\n", encoding="utf-8")
print("summary-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"status_start_ready": True, "status_start_blocker_code": "ready"}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--acceptance-tool",
            str(acceptance_tool),
            "--acceptance-contract-tool",
            str(acceptance_contract_tool),
            "--summary-tool",
            str(summary_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["summary"]["returncode"] == 0
    assert manifest["summary"]["summary_report_present"] is True
    assert (session_dir / "session-summary.md").is_file()


def test_macos_validation_session_tool_passes_framebus_roundtrip_report_into_smoke_and_install_session(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    framebus_roundtrip_tool = tmp_path / "framebus-roundtrip.py"
    smoke_tool = tmp_path / "smoke.py"
    install_session_tool = tmp_path / "install-session.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        framebus_roundtrip_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": False}, "observed": {"direct_open_errno": 13}}), encoding="utf-8")
print("framebus-roundtrip-ok")
""",
    )
    write_tool(
        smoke_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--framebus-roundtrip-json" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "status": {"ipc_environment_blocked": True, "ipc_direct_open_errno": 13, "start_ready": False, "start_blocker_code": "ipc_environment_blocked"},
    "install": {"success": True}
}), encoding="utf-8")
print("smoke-ok")
""",
    )
    write_tool(
        install_session_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--framebus-roundtrip-json" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "install": {"success": True},
    "post_status": {"ipc_environment_blocked": True, "ipc_direct_open_errno": 13, "start_ready": False, "start_blocker_code": "ipc_environment_blocked"}
}), encoding="utf-8")
print("install-session-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--smoke-json" in args
assert "--install-session-json" in args
assert "--framebus-roundtrip-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0, "framebus_roundtrip_present": True}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--smoke-tool",
            str(smoke_tool),
            "--install-session-tool",
            str(install_session_tool),
            "--framebus-roundtrip-tool",
            str(framebus_roundtrip_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-install",
            "--run-install-session",
            "--run-framebus-roundtrip",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["smoke_ipc_environment_blocked"] is True
    assert manifest["summary"]["smoke_ipc_direct_open_errno"] == 13
    assert manifest["summary"]["smoke_start_blocker_code"] == "ipc_environment_blocked"
    assert manifest["summary"]["install_session_ipc_environment_blocked"] is True
    assert manifest["summary"]["install_session_ipc_direct_open_errno"] == 13
    assert manifest["summary"]["install_session_ipc_probe_present"] is None
    assert manifest["summary"]["install_session_ipc_ready"] is None
    assert manifest["summary"]["install_session_start_blocker_code"] == "ipc_environment_blocked"
    assert manifest["summary"]["framebus_roundtrip_environment_blocked"] is True
    assert manifest["summary"]["effective_start_blocker_code"] == "ipc_environment_blocked"


def test_macos_validation_session_tool_surfaces_capabilities_in_session_manifest(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    smoke_tool = tmp_path / "smoke.py"
    install_session_tool = tmp_path / "install-session.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        smoke_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "status": {
        "start_ready": True,
        "start_blocker_code": "ready",
        "shared_memory_name": "/akvc-smoke",
        "mach_service_name": "com.akvc.smoke",
        "ipc_transport": "smoke_transport",
        "supported_formats": ["1920x1080@30/60 NV12"],
        "supported_frame_rates": [30, 60]
    },
    "install": {"success": True}
}), encoding="utf-8")
print("smoke-ok")
""",
    )
    write_tool(
        install_session_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "install": {"success": True},
    "post_status": {
        "start_ready": True,
        "start_blocker_code": "ready",
        "shared_memory_name": "/akvc-install-session",
        "mach_service_name": "com.akvc.install-session",
        "ipc_transport": "install_session_transport",
        "supported_formats": ["3840x2160@30/60 NV12"],
        "supported_frame_rates": [30, 60]
    }
}), encoding="utf-8")
print("install-session-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--smoke-json" in args
assert "--install-session-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({
    "status": {
        "shared_memory_name": "/akvc-validation",
        "mach_service_name": "com.akvc.validation",
        "ipc_transport": "validation_transport",
        "supported_formats": ["1280x720@30/60 NV12"],
        "supported_frame_rates": [30, 60]
    },
    "summary": {
        "passed_apps": 0,
        "status_start_ready": True,
        "status_start_blocker_code": "ready"
    }
}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--smoke-tool",
            str(smoke_tool),
            "--install-session-tool",
            str(install_session_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-install",
            "--run-install-session",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["validation_shared_memory_name"] == "/akvc-validation"
    assert manifest["summary"]["smoke_shared_memory_name"] == "/akvc-smoke"
    assert manifest["summary"]["install_session_shared_memory_name"] == "/akvc-install-session"
    assert manifest["summary"]["effective_shared_memory_name"] == "/akvc-install-session"
    assert manifest["summary"]["effective_mach_service_name"] == "com.akvc.install-session"
    assert manifest["summary"]["effective_ipc_transport"] == "install_session_transport"
    assert manifest["summary"]["runtime_topology_kind"] == "camera_extension_direct_framebus"
    assert manifest["summary"]["runtime_host_in_frame_hot_path"] is False
    assert manifest["summary"]["runtime_dedicated_host_daemon_required"] is False
    assert manifest["summary"]["runtime_data_plane"] == "install_session_transport"
    assert manifest["summary"]["validation_supported_formats"] == ["1280x720@30/60 NV12"]
    assert manifest["summary"]["smoke_supported_formats"] == ["1920x1080@30/60 NV12"]
    assert manifest["summary"]["install_session_supported_formats"] == ["3840x2160@30/60 NV12"]
    assert manifest["summary"]["effective_supported_formats"] == ["3840x2160@30/60 NV12"]
    assert manifest["summary"]["effective_supported_frame_rates"] == [30, 60]


def test_macos_validation_session_tool_passes_producer_side_framebus_blocker_into_smoke_and_install_session(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    framebus_roundtrip_tool = tmp_path / "framebus-roundtrip.py"
    smoke_tool = tmp_path / "smoke.py"
    install_session_tool = tmp_path / "install-session.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        framebus_roundtrip_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "transport": "iosurface_ring",
    "error": "shm_open(create) failed (errno=1)",
    "environment_blocked": True,
    "observed": {"status": "producer_open_failed", "direct_open_errno": 1},
    "consistency": {"all_checks_passed": False, "environment_blocked": True}
}), encoding="utf-8")
print("framebus-roundtrip-ok")
""",
    )
    write_tool(
        smoke_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--framebus-roundtrip-json" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "status": {"ipc_environment_blocked": True, "ipc_direct_open_errno": 1, "start_ready": False, "start_blocker_code": "ipc_environment_blocked"},
    "install": {"success": True}
}), encoding="utf-8")
print("smoke-ok")
""",
    )
    write_tool(
        install_session_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--framebus-roundtrip-json" in args
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "install": {"success": True},
    "post_status": {"ipc_environment_blocked": True, "ipc_direct_open_errno": 1, "start_ready": False, "start_blocker_code": "ipc_environment_blocked"}
}), encoding="utf-8")
print("install-session-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--smoke-json" in args
assert "--install-session-json" in args
assert "--framebus-roundtrip-json" in args
report = Path(args[args.index("--output") + 1])
template = Path(args[args.index("--write-manual-template") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0, "framebus_roundtrip_present": True}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--smoke-tool",
            str(smoke_tool),
            "--install-session-tool",
            str(install_session_tool),
            "--framebus-roundtrip-tool",
            str(framebus_roundtrip_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
            "--run-install",
            "--run-install-session",
            "--run-framebus-roundtrip",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["smoke_ipc_environment_blocked"] is True
    assert manifest["summary"]["smoke_ipc_direct_open_errno"] == 1
    assert manifest["summary"]["smoke_start_blocker_code"] == "ipc_environment_blocked"
    assert manifest["summary"]["install_session_ipc_environment_blocked"] is True
    assert manifest["summary"]["install_session_ipc_direct_open_errno"] == 1
    assert manifest["summary"]["install_session_ipc_probe_present"] is None
    assert manifest["summary"]["install_session_ipc_ready"] is None
    assert manifest["summary"]["install_session_start_blocker_code"] == "ipc_environment_blocked"
    assert manifest["summary"]["framebus_roundtrip_present"] is True
    assert manifest["summary"]["framebus_roundtrip_direct_open_errno"] == 1
    assert manifest["summary"]["framebus_roundtrip_environment_blocked"] is True
    assert manifest["summary"]["effective_start_blocker_code"] == "ipc_environment_blocked"


def test_macos_validation_session_tool_propagates_demo_failure(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    benchmark_tool = tmp_path / "benchmark.py"
    report_tool = tmp_path / "report.py"

    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import sys
print("demo failed", file=sys.stderr)
sys.exit(3)
""",
    )
    write_tool(
        benchmark_tool,
        """#!/usr/bin/env python3
print("benchmark-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(tmp_path / "session"),
            "--demo-tool",
            str(demo_tool),
            "--benchmark-tool",
            str(benchmark_tool),
            "--validation-report-tool",
            str(report_tool),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3
    assert "demo failed" in completed.stderr


def test_macos_validation_session_tool_passes_video_file_mode_and_path(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"
    video_path = tmp_path / "demo.mp4"
    video_path.write_text("placeholder", encoding="utf-8")

    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index("--mode") + 1] == "video-file"
assert args[args.index("--video-path") + 1].endswith("demo.mp4")
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "video-file", "video_path": args[args.index("--video-path") + 1], "frame_source_kind": "opencv_video_file", "python_entrypoint_kind": "create_pyside6_streamer.start_video_file_stream", "sdk_streamer_factory_used": True, "sdk_latest_provider_factory_used": False, "sdk_direct_push_used": False}), encoding="utf-8")
print("demo-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
demo = Path(args[args.index("--demo-json") + 1])
demo_payload = json.loads(demo.read_text(encoding="utf-8"))
assert demo_payload["mode"] == "video-file"
assert demo_payload["video_path"].endswith("demo.mp4")
assert demo_payload["frame_source_kind"] == "opencv_video_file"
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0, "demo_present": True, "demo_mode": demo_payload["mode"], "demo_mode_supported": True, "demo_video_path": demo_payload["video_path"], "demo_frame_source_kind": demo_payload["frame_source_kind"], "demo_python_entrypoint_kind": demo_payload["python_entrypoint_kind"], "demo_sdk_streamer_factory_used": demo_payload["sdk_streamer_factory_used"], "demo_sdk_latest_provider_factory_used": demo_payload["sdk_latest_provider_factory_used"], "demo_sdk_direct_push_used": demo_payload["sdk_direct_push_used"]}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--demo-tool",
            str(demo_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-benchmark",
            "--mode",
            "video-file",
            "--video-path",
            str(video_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "--video-path" in manifest["steps"]["demo"]["command"]
    assert "--demo-json" in manifest["steps"]["validation_report"]["command"]
    payload = json.loads((session_dir / "demo-report.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "video-file"
    assert payload["video_path"].endswith("demo.mp4")
    assert manifest["summary"]["validation_demo_present"] is True
    assert manifest["summary"]["validation_demo_mode"] == "video-file"
    assert manifest["summary"]["validation_demo_mode_supported"] is True
    assert manifest["summary"]["validation_demo_video_path"].endswith("demo.mp4")
    assert manifest["summary"]["validation_demo_frame_source_kind"] == "opencv_video_file"
    assert manifest["summary"]["validation_demo_python_entrypoint_kind"] == "create_pyside6_streamer.start_video_file_stream"
    assert manifest["summary"]["validation_demo_sdk_streamer_factory_used"] is True
    assert manifest["summary"]["validation_demo_sdk_latest_provider_factory_used"] is False
    assert manifest["summary"]["validation_demo_sdk_direct_push_used"] is False


def test_macos_validation_session_tool_passes_latest_provider_mode(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index("--mode") + 1] == "latest-provider"
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "latest-provider", "frame_source_kind": "latest_frame_provider", "python_entrypoint_kind": "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream", "sdk_streamer_factory_used": True, "sdk_latest_provider_factory_used": True, "sdk_direct_push_used": False}), encoding="utf-8")
print("demo-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
demo = Path(args[args.index("--demo-json") + 1])
demo_payload = json.loads(demo.read_text(encoding="utf-8"))
assert demo_payload["mode"] == "latest-provider"
assert demo_payload["frame_source_kind"] == "latest_frame_provider"
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0, "demo_present": True, "demo_mode": demo_payload["mode"], "demo_mode_supported": True, "demo_frame_source_kind": demo_payload["frame_source_kind"], "demo_python_entrypoint_kind": demo_payload["python_entrypoint_kind"], "demo_sdk_streamer_factory_used": demo_payload["sdk_streamer_factory_used"], "demo_sdk_latest_provider_factory_used": demo_payload["sdk_latest_provider_factory_used"], "demo_sdk_direct_push_used": demo_payload["sdk_direct_push_used"]}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--demo-tool",
            str(demo_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-benchmark",
            "--mode",
            "latest-provider",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "latest-provider" in manifest["steps"]["demo"]["command"]
    assert "--demo-json" in manifest["steps"]["validation_report"]["command"]
    payload = json.loads((session_dir / "demo-report.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "latest-provider"
    assert manifest["summary"]["validation_demo_present"] is True
    assert manifest["summary"]["validation_demo_mode"] == "latest-provider"
    assert manifest["summary"]["validation_demo_mode_supported"] is True
    assert manifest["summary"]["validation_demo_video_path"] is None
    assert manifest["summary"]["validation_demo_frame_source_kind"] == "latest_frame_provider"
    assert manifest["summary"]["validation_demo_python_entrypoint_kind"] == "create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream"
    assert manifest["summary"]["validation_demo_sdk_streamer_factory_used"] is True
    assert manifest["summary"]["validation_demo_sdk_latest_provider_factory_used"] is True
    assert manifest["summary"]["validation_demo_sdk_direct_push_used"] is False


def test_macos_validation_session_tool_passes_widget_mode(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index("--mode") + 1] == "widget"
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "widget", "frame_source_kind": "widget_grab", "python_entrypoint_kind": "send_widget", "sdk_streamer_factory_used": False, "sdk_latest_provider_factory_used": False, "sdk_direct_push_used": True}), encoding="utf-8")
print("demo-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
demo = Path(args[args.index("--demo-json") + 1])
demo_payload = json.loads(demo.read_text(encoding="utf-8"))
assert demo_payload["mode"] == "widget"
assert demo_payload["frame_source_kind"] == "widget_grab"
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0, "demo_present": True, "demo_mode": demo_payload["mode"], "demo_mode_supported": True, "demo_frame_source_kind": demo_payload["frame_source_kind"], "demo_python_entrypoint_kind": demo_payload["python_entrypoint_kind"], "demo_sdk_streamer_factory_used": demo_payload["sdk_streamer_factory_used"], "demo_sdk_latest_provider_factory_used": demo_payload["sdk_latest_provider_factory_used"], "demo_sdk_direct_push_used": demo_payload["sdk_direct_push_used"]}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--demo-tool",
            str(demo_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-benchmark",
            "--mode",
            "widget",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "widget" in manifest["steps"]["demo"]["command"]
    assert "--demo-json" in manifest["steps"]["validation_report"]["command"]
    payload = json.loads((session_dir / "demo-report.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "widget"
    assert manifest["summary"]["validation_demo_present"] is True
    assert manifest["summary"]["validation_demo_mode"] == "widget"
    assert manifest["summary"]["validation_demo_mode_supported"] is True
    assert manifest["summary"]["validation_demo_video_path"] is None
    assert manifest["summary"]["validation_demo_frame_source_kind"] == "widget_grab"
    assert manifest["summary"]["validation_demo_python_entrypoint_kind"] == "send_widget"
    assert manifest["summary"]["validation_demo_sdk_streamer_factory_used"] is False
    assert manifest["summary"]["validation_demo_sdk_latest_provider_factory_used"] is False
    assert manifest["summary"]["validation_demo_sdk_direct_push_used"] is True


def test_macos_validation_session_tool_passes_screen_mode(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index("--mode") + 1] == "screen"
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "screen", "frame_source_kind": "screen_grab", "python_entrypoint_kind": "send_screen", "sdk_streamer_factory_used": False, "sdk_latest_provider_factory_used": False, "sdk_direct_push_used": True}), encoding="utf-8")
print("demo-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
demo = Path(args[args.index("--demo-json") + 1])
demo_payload = json.loads(demo.read_text(encoding="utf-8"))
assert demo_payload["mode"] == "screen"
assert demo_payload["frame_source_kind"] == "screen_grab"
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0, "demo_present": True, "demo_mode": demo_payload["mode"], "demo_mode_supported": True, "demo_frame_source_kind": demo_payload["frame_source_kind"], "demo_python_entrypoint_kind": demo_payload["python_entrypoint_kind"], "demo_sdk_streamer_factory_used": demo_payload["sdk_streamer_factory_used"], "demo_sdk_latest_provider_factory_used": demo_payload["sdk_latest_provider_factory_used"], "demo_sdk_direct_push_used": demo_payload["sdk_direct_push_used"]}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--demo-tool",
            str(demo_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-benchmark",
            "--mode",
            "screen",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "screen" in manifest["steps"]["demo"]["command"]
    assert "--demo-json" in manifest["steps"]["validation_report"]["command"]
    payload = json.loads((session_dir / "demo-report.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "screen"
    assert manifest["summary"]["validation_demo_present"] is True
    assert manifest["summary"]["validation_demo_mode"] == "screen"
    assert manifest["summary"]["validation_demo_mode_supported"] is True
    assert manifest["summary"]["validation_demo_video_path"] is None
    assert manifest["summary"]["validation_demo_frame_source_kind"] == "screen_grab"
    assert manifest["summary"]["validation_demo_python_entrypoint_kind"] == "send_screen"
    assert manifest["summary"]["validation_demo_sdk_streamer_factory_used"] is False
    assert manifest["summary"]["validation_demo_sdk_latest_provider_factory_used"] is False
    assert manifest["summary"]["validation_demo_sdk_direct_push_used"] is True


def test_macos_validation_session_tool_passes_benchmark_matrix_and_uses_matrix_artifact(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    demo_tool = tmp_path / "demo.py"
    benchmark_tool = tmp_path / "benchmark.py"
    report_tool = tmp_path / "report.py"
    artifact_check_tool = tmp_path / "artifact-check.py"
    session_dir = tmp_path / "session"

    write_tool(
        demo_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--report-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mode": "provider"}), encoding="utf-8")
print("demo-ok")
""",
    )
    write_tool(
        benchmark_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--matrix" in args
assert args[args.index("--warmup") + 1] == "2.5"
output = Path(args[args.index("--output") + 1])
assert output.name == "benchmark-matrix.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "kind": "benchmark_matrix",
    "summary": {"benchmark_acceptance": {"profile_count": 6}},
    "results": [
        {
            "profile": {"name": "720p30", "width": 1280, "height": 720, "fps": 30.0},
            "metrics": {"actual_fps": 29.8, "cpu_percent": 3.1, "avg_latency_ms": 0.7},
            "acceptance": {"fps_target_met": True, "cpu_target_applies": False, "cpu_target_met": None},
        },
        {
            "profile": {"name": "1080p60", "width": 1920, "height": 1080, "fps": 60.0},
            "metrics": {"actual_fps": 59.6, "cpu_percent": 8.4, "avg_latency_ms": 1.1},
            "acceptance": {"fps_target_met": True, "cpu_target_applies": True, "cpu_target_met": True},
        },
    ],
}), encoding="utf-8")
print("benchmark-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "benchmark-matrix.json" in args[args.index("--benchmark-json") + 1]
benchmark_payload = json.loads(Path(args[args.index("--benchmark-json") + 1]).read_text(encoding="utf-8"))
assert benchmark_payload["kind"] == "benchmark_matrix"
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {
    "passed_apps": 0,
    "benchmark_kind": "benchmark_matrix",
    "benchmark_matrix_profiles": [
        {
            "profile_name": "720p30",
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 29.8,
            "cpu_percent": 3.1,
            "avg_latency_ms": 0.7,
        },
        {
            "profile_name": "1080p60",
            "width": 1920,
            "height": 1080,
            "fps": 60.0,
            "fps_target_met": True,
            "cpu_target_applies": True,
            "cpu_target_met": True,
            "actual_fps": 59.6,
            "cpu_percent": 8.4,
            "avg_latency_ms": 1.1,
        },
    ],
}}), encoding="utf-8")
print("report-ok")
""",
    )
    write_tool(
        artifact_check_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("artifact-check-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--demo-tool",
            str(demo_tool),
            "--benchmark-tool",
            str(benchmark_tool),
            "--validation-report-tool",
            str(report_tool),
            "--artifact-check-tool",
            str(artifact_check_tool),
            "--benchmark-matrix",
            "--benchmark-warmup",
            "2.5",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["benchmark_report"].endswith("benchmark-matrix.json")
    assert "--matrix" in manifest["steps"]["benchmark"]["command"]
    assert (session_dir / "benchmark-matrix.json").is_file()
    assert manifest["summary"]["validation_benchmark_kind"] == "benchmark_matrix"
    assert manifest["summary"]["validation_benchmark_matrix_profiles"] == [
        {
            "profile_name": "720p30",
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "fps_target_met": True,
            "cpu_target_applies": False,
            "cpu_target_met": None,
            "actual_fps": 29.8,
            "cpu_percent": 3.1,
            "avg_latency_ms": 0.7,
        },
        {
            "profile_name": "1080p60",
            "width": 1920,
            "height": 1080,
            "fps": 60.0,
            "fps_target_met": True,
            "cpu_target_applies": True,
            "cpu_target_met": True,
            "actual_fps": 59.6,
            "cpu_percent": 8.4,
            "avg_latency_ms": 1.1,
        },
    ]


def test_macos_validation_session_tool_passes_benchmark_profile(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    benchmark_tool = tmp_path / "benchmark.py"
    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        benchmark_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index("--profile") + 1] == "1080p60"
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"profile": {"name": "1080p60"}}), encoding="utf-8")
print("benchmark-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--benchmark-tool",
            str(benchmark_tool),
            "--validation-report-tool",
            str(report_tool),
            "--skip-demo",
            "--benchmark-profile",
            "1080p60",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "--profile" in manifest["steps"]["benchmark"]["command"]
    assert "1080p60" in manifest["steps"]["benchmark"]["command"]
    assert (session_dir / "benchmark.json").is_file()


def test_macos_validation_session_tool_can_skip_preflight(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--preflight-json" not in args
assert "--release-diagnostics-json" in args
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--validation-report-tool",
            str(report_tool),
            "--skip-preflight",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "preflight" not in manifest["steps"]
    assert not (session_dir / "preflight.json").exists()


def test_macos_validation_session_tool_can_skip_release_diagnostics(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    report_tool = tmp_path / "report.py"
    session_dir = tmp_path / "session"

    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--release-diagnostics-json" not in args
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0}}), encoding="utf-8")
print("report-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--validation-report-tool",
            str(report_tool),
            "--skip-release-diagnostics",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert "release_diagnostics" not in manifest["steps"]
    assert not (session_dir / "release-diagnostics.json").exists()


def test_macos_validation_session_tool_forwards_release_diagnostics_host_bundle_overrides(tmp_path) -> None:
    def write_tool(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    release_diagnostics_tool = tmp_path / "release-diagnostics.py"
    report_tool = tmp_path / "report.py"
    entrypoints_contract_tool = tmp_path / "entrypoints-contract.py"
    sdk_contract_tool = tmp_path / "sdk-contract.py"
    session_dir = tmp_path / "session"
    host_bundle = tmp_path / "Amaran Desktop.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    pkg_path = tmp_path / "VirtualCamera.pkg"

    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    sync_ipc_tool.write_text("sync", encoding="utf-8")
    pkg_path.write_text("pkg", encoding="utf-8")

    write_tool(
        release_diagnostics_tool,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index("--app-bundle") + 1] == {str(host_bundle)!r}
assert args[args.index("--extension-bundle") + 1] == {str(host_bundle / "Contents" / "Library" / "SystemExtensions" / "com.sidus.amaran-desktop.cameraextension.systemextension")!r}
assert args[args.index("--sync-ipc-tool") + 1] == {str(sync_ipc_tool)!r}
assert args[args.index("--pkg-path") + 1] == {str(pkg_path)!r}
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({{"summary": {{"release_artifacts_present": True}}}}), encoding="utf-8")
print("release-diagnostics-ok")
""",
    )
    write_tool(
        report_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
assert "--release-diagnostics-json" in args
template = Path(args[args.index("--write-manual-template") + 1])
report = Path(args[args.index("--output") + 1])
template.parent.mkdir(parents=True, exist_ok=True)
template.write_text(json.dumps({"zoom": {"validated": False, "result": "pending"}}), encoding="utf-8")
report.write_text(json.dumps({"summary": {"passed_apps": 0}}), encoding="utf-8")
print("report-ok")
""",
    )
    write_tool(
        sdk_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("sdk-contract-ok")
""",
    )
    write_tool(
        entrypoints_contract_tool,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"consistency": {"all_checks_passed": True}}), encoding="utf-8")
print("entrypoints-contract-ok")
""",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(session_dir),
            "--release-diagnostics-tool",
            str(release_diagnostics_tool),
            "--validation-report-tool",
            str(report_tool),
            "--entrypoints-contract-tool",
            str(entrypoints_contract_tool),
            "--sdk-contract-tool",
            str(sdk_contract_tool),
            "--app-bundle",
            str(host_bundle),
            "--sync-ipc-tool",
            str(sync_ipc_tool),
            "--pkg-path",
            str(pkg_path),
            "--skip-preflight",
            "--skip-demo",
            "--skip-benchmark",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((session_dir / "session-manifest.json").read_text(encoding="utf-8"))
    assert manifest["steps"]["release_diagnostics"]["returncode"] == 0
    assert (session_dir / "release-diagnostics.json").is_file()


def test_macos_validation_session_tool_requires_video_path_for_video_file_mode(tmp_path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "macos_validation_session.py"),
            "--output-dir",
            str(tmp_path / "session"),
            "--mode",
            "video-file",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "video-file mode requires --video-path" in completed.stderr
