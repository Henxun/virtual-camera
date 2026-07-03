# SPDX-License-Identifier: Apache-2.0
"""macOS installer/status bridge tests."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import akvc.platforms.macos.installer as installer_module
from akvc.platforms.macos.installer import (
    CommandMacInstallerService,
    describe_manual_app_validation_gate,
    describe_manual_app_validation_gates,
    describe_runtime_topology,
    DefaultMacInstallerService,
    evaluate_extension_readiness,
    ExtensionReadiness,
    ExtensionInstallState,
    ExtensionRuntimeSnapshot,
    ExtensionStatus,
    InstallExtensionResult,
    ManualAppValidationSummary,
    SyncIPCConfigurationResult,
    UninstallExtensionResult,
    build_verification_targets,
    build_runtime_snapshot,
    infer_extension_phase,
    inspect_extension,
    inspect_install_result,
    load_manual_app_validation_summary,
    macos_install_settings_commands,
    open_macos_install_settings,
)


def _empty_codesign_runner(command):
    return SimpleNamespace(returncode=1, stdout="", stderr="")


def _empty_policy_runner(command):
    return SimpleNamespace(returncode=1, stdout="", stderr="")


def test_describe_runtime_topology_marks_host_as_control_plane_only() -> None:
    topology = describe_runtime_topology(
        ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            bundle_path="/Applications/AKVC.app",
            ipc_transport="shared_memory_ringbuffer",
        )
    )

    assert topology == {
        "runtime_topology_kind": "camera_extension_direct_framebus",
        "runtime_frame_path": "python_sdk -> shared_memory_ringbuffer -> camera_extension -> system_camera_device -> client_app",
        "runtime_host_role": "container_activation_command_bridge",
        "runtime_host_in_frame_hot_path": False,
        "runtime_dedicated_host_daemon_required": False,
        "runtime_container_app_configured": True,
        "runtime_data_plane": "shared_memory_ringbuffer",
        "runtime_control_plane": "host_activation_plus_sync_ipc",
    }


def test_is_build_tree_host_path_accepts_non_legacy_container_app_bundle_names() -> None:
    assert installer_module._is_build_tree_host_path(
        "/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app"
    ) is True
    assert installer_module._is_build_tree_host_path(
        "/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app/Contents/MacOS/Amaran Desktop"
    ) is True
    assert installer_module._is_build_tree_host_path(
        "/Applications/Amaran Desktop.app"
    ) is False


def test_command_installer_service_parses_status_payload() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "state": "installed",
                "devices": ["AK Virtual Camera"],
                "all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                "device_prefix": "AK Virtual Camera",
                "enabled": True,
                "approval_required": False,
                "needs_reboot": False,
                "bundle_path": "/Applications/AKVC.app",
                "extension_identifier": "com.sidus.amaran-desktop.cameraextension",
                "shared_memory_name": "/akvc-frames-v1",
                "supported_formats": ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"],
                "supported_frame_rates": [30, 60],
                "mach_service_name": "group.com.sidus.amaran-desktop.cameraextension",
            }),
            stderr="",
        )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=runner,
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALLED
    assert status.devices == ["AK Virtual Camera"]
    assert status.all_devices == ["FaceTime HD Camera", "AK Virtual Camera"]
    assert status.device_prefix == "AK Virtual Camera"
    assert status.enabled is True
    assert status.bundle_path == "/Applications/AKVC.app"
    assert status.extension_identifier == "com.sidus.amaran-desktop.cameraextension"
    assert status.shared_memory_name == "/akvc-frames-v1"
    assert status.supported_formats == ["1280x720@30/60 NV12", "1920x1080@30/60 NV12"]
    assert status.supported_frame_rates == [30, 60]
    assert status.mach_service_name == "group.com.sidus.amaran-desktop.cameraextension"
    assert svc.extension_state() is ExtensionInstallState.INSTALLED
    assert svc.enumerate_devices() == ["AK Virtual Camera"]
    assert calls[0] == ["akvc-macos-status"]


def test_load_manual_app_validation_summary_reads_session_manifest(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "session-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "summary": {
                    "manual_app_validation_ready": False,
                    "manual_app_validation_failed_criteria": ["system_camera_device_visible"],
                    "manual_app_validation_unknown_criteria": ["notarization_tooling_ready"],
                    "manual_app_validation_blockers": [
                        "system_camera_device_visible",
                        "notarization_tooling_ready",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AKVC_MACOS_SESSION_MANIFEST_JSON", str(manifest))

    summary = load_manual_app_validation_summary()

    assert summary == ManualAppValidationSummary(
        present=True,
        ready=False,
        failed_criteria=["system_camera_device_visible"],
        unknown_criteria=["notarization_tooling_ready"],
        blockers=["system_camera_device_visible", "notarization_tooling_ready"],
        manifest_path=str(manifest),
    )


def test_describe_manual_app_validation_gates_maps_known_gate_names() -> None:
    assert describe_manual_app_validation_gate("system_camera_device_visible") == "系统已枚举到虚拟摄像头"
    assert describe_manual_app_validation_gate("unknown_gate") == "unknown_gate"
    assert describe_manual_app_validation_gates(
        ["system_camera_device_visible", "notarization_tooling_ready"]
    ) == [
        "系统已枚举到虚拟摄像头",
        "公证工具链已就绪",
    ]


def test_macos_install_settings_commands_prefer_privacy_security_deep_links() -> None:
    commands = macos_install_settings_commands()

    assert commands[:2] == [
        ["open", "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension"],
        ["open", "x-apple.systempreferences:com.apple.settings.PrivacySecurity"],
    ]
    assert commands[-2:] == [
        ["open", "/System/Applications/System Settings.app"],
        ["open", "-b", "com.apple.systempreferences"],
    ]


def test_open_macos_install_settings_falls_back_until_success(monkeypatch) -> None:
    calls: list[list[str]] = []
    results = iter([1, 1, 0])

    monkeypatch.setattr("akvc.platforms.macos.installer.sys.platform", "darwin", raising=False)

    rc = open_macos_install_settings(
        command_runner=lambda command: calls.append(list(command)) or next(results)
    )

    assert rc == 0
    assert calls == [
        ["open", "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension"],
        ["open", "x-apple.systempreferences:com.apple.settings.PrivacySecurity"],
        ["open", "/System/Applications/System Settings.app"],
    ]


def test_open_macos_install_settings_rejects_non_macos(monkeypatch) -> None:
    monkeypatch.setattr("akvc.platforms.macos.installer.sys.platform", "linux", raising=False)

    rc = open_macos_install_settings(command_runner=lambda command: 0)

    assert rc == 2


def test_command_installer_service_merges_framebus_roundtrip_status(tmp_path) -> None:
    report = tmp_path / "framebus-roundtrip.json"
    report.write_text(
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

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        framebus_roundtrip_json=report,
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "installed",
                    "devices": ["AK Virtual Camera"],
                    "enabled": True,
                }
            ),
            stderr="",
        ),
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALLED
    assert status.ipc_probe_present is True
    assert status.ipc_ready is False
    assert status.ipc_environment_blocked is True
    assert status.ipc_direct_open_errno == 13
    assert status.ipc_transport == "shared_memory_ringbuffer"
    assert "direct_open_errno=13" in (status.ipc_last_error or "")
    assert status.ipc_probe_path == str(report)


def test_command_installer_service_merges_host_codesign_summary() -> None:
    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "last_error": "The operation couldn’t be completed. (OSSystemExtensionErrorDomain error 1.)",
                }
            ),
            stderr="",
        ),
        codesign_runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr=(
                "Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n"
                "Signature=adhoc\n"
                "TeamIdentifier=not set\n"
            ),
        ),
    )

    status = svc.status()

    assert status.host_signature == "adhoc"
    assert status.host_team_identifier is None
    assert status.host_codesign_summary == "Signature=adhoc; TeamIdentifier=not set"


def test_command_installer_service_detects_invalid_host_entitlements_blob() -> None:
    def inspection_runner(command):
        if command[:3] == ["codesign", "-d", "--entitlements"]:
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    "Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n"
                    "warning: binary contains an invalid entitlements blob. The OS will ignore these entitlements.\n"
                ),
            )
        if command[0] == "codesign":
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    "Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n"
                    "Signature=Developer ID Application\n"
                    "TeamIdentifier=XP3H66JF79\n"
                ),
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "last_error": "Missing entitlement com.apple.developer.system-extension.install",
                }
            ),
            stderr="",
        ),
        codesign_runner=inspection_runner,
        policy_runner=inspection_runner,
    )

    status = svc.status()

    assert status.host_entitlements_valid is False
    assert "invalid entitlements blob" in (status.host_entitlements_summary or "").lower()


def test_command_installer_service_detects_missing_host_install_entitlement() -> None:
    def inspection_runner(command):
        if command[:3] == ["codesign", "-d", "--entitlements"]:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                    "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                    "\"https://www.apple.com/DTDs/PropertyList-1.0.dtd\">"
                    "<plist version=\"1.0\"><dict>"
                    "<key>com.apple.security.app-sandbox</key><true/>"
                    "</dict></plist>"
                ),
                stderr="Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n",
            )
        if command[0] == "codesign":
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    "Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n"
                    "Signature=Developer ID Application\n"
                    "TeamIdentifier=XP3H66JF79\n"
                ),
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "last_error": "Missing entitlement com.apple.developer.system-extension.install",
                }
            ),
            stderr="",
        ),
        codesign_runner=inspection_runner,
        policy_runner=inspection_runner,
    )

    status = svc.status()

    assert status.host_entitlements_valid is False
    assert status.host_entitlements_summary == (
        "missing entitlement com.apple.developer.system-extension.install"
    )


def test_command_installer_service_merges_host_notarization_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr(
        installer_module.shutil,
        "which",
        lambda name: "/usr/bin/syspolicy_check" if name == "syspolicy_check" else None,
    )

    def inspection_runner(command):
        if command[0] == "codesign":
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    "Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n"
                    "Signature=Apple Development\n"
                    "TeamIdentifier=XP3H66JF79\n"
                ),
            )
        if command[0] == "spctl":
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr=(
                    "/Applications/Amaran Desktop.app: rejected\n"
                    "origin=Apple Development: Choshim Wei (53CY9ZZ74X)\n"
                ),
            )
        if command[0] == "/usr/bin/syspolicy_check":
            return SimpleNamespace(
                returncode=1,
                stdout="Notary Ticket Missing\nSeverity=Fatal\n",
                stderr="",
            )
        raise AssertionError(command[0])

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "last_error": "killed by launch policy",
                }
            ),
            stderr="",
        ),
        codesign_runner=inspection_runner,
        policy_runner=inspection_runner,
    )

    status = svc.status()

    assert status.host_signature == "Apple Development"
    assert status.host_team_identifier == "XP3H66JF79"
    assert status.host_gatekeeper_allowed is False
    assert status.host_gatekeeper_summary == (
        "/Applications/Amaran Desktop.app: rejected; "
        "origin=Apple Development: Choshim Wei (53CY9ZZ74X)"
    )
    assert status.host_distribution_summary == "Notary Ticket Missing; Severity=Fatal"
    assert status.host_notarization_missing is True


def test_command_installer_service_merges_install_command_notarization_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr(
        installer_module.shutil,
        "which",
        lambda name: "/usr/bin/syspolicy_check" if name == "syspolicy_check" else None,
    )

    install_path = "/tmp/akvc-macos-install"

    def inspection_runner(command):
        if command[0] == "codesign":
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    f"Executable={install_path}\n"
                    "Signature=Developer ID Application\n"
                    "TeamIdentifier=XP3H66JF79\n"
                ),
            )
        if command[0] == "spctl":
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr=(
                    f"{install_path}: rejected\n"
                    "source=Unnotarized Developer ID\n"
                    "origin=Developer ID Application: Sidus Link Ltd. (XP3H66JF79)\n"
                ),
            )
        if command[0] == "/usr/bin/syspolicy_check":
            return SimpleNamespace(
                returncode=1,
                stdout="Notary Ticket Missing\nSeverity=Fatal\n",
                stderr="",
            )
        raise AssertionError(command[0])

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command_path=install_path,
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "last_error": "killed by launch policy",
                }
            ),
            stderr="",
        ),
        codesign_runner=inspection_runner,
        policy_runner=inspection_runner,
    )

    status = svc.status()

    assert status.install_command_path == install_path
    assert status.install_command_signature == "Developer ID Application"
    assert status.install_command_team_identifier == "XP3H66JF79"
    assert status.install_command_codesign_summary == (
        "Signature=Developer ID Application; TeamIdentifier=XP3H66JF79"
    )
    assert status.install_command_gatekeeper_allowed is False
    assert status.install_command_gatekeeper_summary == (
        f"{install_path}: rejected; "
        "source=Unnotarized Developer ID; "
        "origin=Developer ID Application: Sidus Link Ltd. (XP3H66JF79)"
    )
    assert status.install_command_distribution_summary == "Notary Ticket Missing; Severity=Fatal"
    assert status.install_command_notarization_missing is True


def test_command_installer_service_tolerates_policy_runner_timeouts(monkeypatch) -> None:
    monkeypatch.setattr(
        installer_module.shutil,
        "which",
        lambda name: "/usr/bin/syspolicy_check" if name == "syspolicy_check" else None,
    )

    def inspection_runner(command):
        if command[0] == "codesign":
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    "Executable=/Applications/Amaran Desktop.app/Contents/MacOS/Amaran Desktop\n"
                    "Signature=Developer ID Application\n"
                    "TeamIdentifier=XP3H66JF79\n"
                ),
            )
        if command[0] == "spctl":
            return SimpleNamespace(
                returncode=124,
                stdout="",
                stderr="policy evaluation timed out after 5.0s",
            )
        if command[0] == "/usr/bin/syspolicy_check":
            return SimpleNamespace(
                returncode=124,
                stdout="",
                stderr="policy evaluation timed out after 5.0s",
            )
        raise AssertionError(command[0])

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "last_error": "policy checks stalled",
                }
            ),
            stderr="",
        ),
        codesign_runner=inspection_runner,
        policy_runner=inspection_runner,
    )

    status = svc.status()

    assert status.host_signature == "Developer ID Application"
    assert status.host_gatekeeper_allowed is None
    assert status.host_gatekeeper_summary == "policy evaluation timed out after 5.0s"
    assert status.host_distribution_summary == "policy evaluation timed out after 5.0s"
    assert status.host_notarization_missing is False


def test_default_policy_runner_returns_timeout_completed_process(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=list(args[0]),
            timeout=kwargs["timeout"],
            output="",
            stderr="timed out",
        )

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    completed = installer_module._default_policy_runner(["spctl", "-a", "-vvv", "/tmp/demo.app"])

    assert completed.returncode == 124
    assert completed.stdout == ""
    assert completed.stderr == "timed out"


def test_command_installer_service_tracks_system_extension_registry_presence() -> None:
    extension_identifier = "com.sidus.amaran-desktop.cameraextension"

    def inspection_runner(command):
        if command[0] == "codesign":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[0] == "spctl":
            return SimpleNamespace(returncode=0, stdout="accepted\n", stderr="")
        if command[0] == "/usr/bin/syspolicy_check":
            return SimpleNamespace(returncode=0, stdout="accepted\n", stderr="")
        if command[0] == "systemextensionsctl":
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "1 extension(s)\n"
                    "--- com.apple.system_extension.cmio\n"
                    "enabled\tactive\tteamID\tbundleID (version)\tname\t[state]\n"
                    f"*\t*\tXP3H66JF79\t{extension_identifier} (0.5.0/1)\tAKVC\t[activated enabled]\n"
                ),
                stderr="",
            )
        raise AssertionError(command[0])

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "installed",
                    "bundle_path": "/Applications/Amaran Desktop.app",
                    "extension_identifier": extension_identifier,
                    "enabled": True,
                }
            ),
            stderr="",
        ),
        codesign_runner=inspection_runner,
        policy_runner=inspection_runner,
    )

    status = svc.status()

    assert status.system_extension_registered is True
    assert extension_identifier in (status.system_extension_registry_summary or "")


def test_command_installer_service_merges_producer_side_framebus_blocker(tmp_path) -> None:
    report = tmp_path / "framebus-roundtrip.json"
    report.write_text(
        json.dumps(
            {
                "error": "shm_open(create) failed (errno=1)",
                "environment_blocked": True,
                "observed": {
                    "status": "producer_open_failed",
                    "direct_open_errno": 1,
                },
                "consistency": {
                    "all_checks_passed": False,
                    "environment_blocked": True,
                },
            }
        ),
        encoding="utf-8",
    )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        framebus_roundtrip_json=report,
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "installed",
                    "devices": ["AK Virtual Camera"],
                    "enabled": True,
                }
            ),
            stderr="",
        ),
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALLED
    assert status.ipc_probe_present is True
    assert status.ipc_ready is False
    assert status.ipc_environment_blocked is True
    assert status.ipc_direct_open_errno == 1
    assert status.ipc_transport == "shared_memory_ringbuffer"
    assert "producer_open_failed" in (status.ipc_last_error or "")
    assert "direct_open_errno=1" in (status.ipc_last_error or "")


def test_command_installer_service_exports_framebus_roundtrip_env_for_native_commands(tmp_path, monkeypatch) -> None:
    report = tmp_path / "framebus-roundtrip.json"
    report.write_text(json.dumps({"observed": {"status": "ok"}}), encoding="utf-8")
    monkeypatch.delenv("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON", raising=False)

    observed_env: list[tuple[str, str | None]] = []

    def runner(command):
        observed_env.append((command[0], os.environ.get("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON")))
        if command[0] == "akvc-macos-status":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}),
                stderr="",
            )
        if command[0] == "akvc-macos-list-devices":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        devices_command=["akvc-macos-list-devices"],
        framebus_roundtrip_json=report,
        runner=runner,
    )

    status = svc.status()
    devices = svc.enumerate_devices()
    result = svc.install_extension_result()

    assert status.ipc_probe_path == str(report)
    assert devices == ["AK Virtual Camera"]
    assert result.success is True
    assert observed_env == [
        ("akvc-macos-status", str(report)),
        ("akvc-macos-list-devices", str(report)),
        ("akvc-macos-install", str(report)),
        ("akvc-macos-status", str(report)),
        ("akvc-macos-list-devices", str(report)),
    ]
    assert os.environ.get("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON") is None


def test_command_installer_service_restores_existing_framebus_env_after_runner(tmp_path, monkeypatch) -> None:
    report = tmp_path / "framebus-roundtrip.json"
    report.write_text(json.dumps({"observed": {"status": "ok"}}), encoding="utf-8")
    monkeypatch.setenv("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON", "/tmp/original-roundtrip.json")

    seen_inside_runner: list[str | None] = []

    def runner(command):
        seen_inside_runner.append(os.environ.get("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON"))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}),
            stderr="",
        )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        framebus_roundtrip_json=report,
        runner=runner,
    )

    svc.status()

    assert seen_inside_runner == [str(report)]
    assert os.environ.get("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON") == "/tmp/original-roundtrip.json"


def test_command_installer_service_uses_dedicated_devices_command_when_available() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-list-devices":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "devices": ["AK Virtual Camera", "AK Virtual Camera 4K"],
                    "all_devices": ["FaceTime HD Camera", "AK Virtual Camera", "AK Virtual Camera 4K"],
                }),
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["status-fallback"]}),
            stderr="",
        )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        devices_command=["akvc-macos-list-devices"],
        runner=runner,
    )

    assert svc.enumerate_devices() == ["AK Virtual Camera", "AK Virtual Camera 4K"]
    assert calls == [["akvc-macos-list-devices"]]


def test_command_installer_service_falls_back_to_status_devices_when_devices_command_fails() -> None:
    def runner(command):
        if command[0] == "akvc-macos-list-devices":
            return SimpleNamespace(returncode=1, stdout="", stderr="enumeration failed")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"]}),
            stderr="",
        )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        devices_command=["akvc-macos-list-devices"],
        runner=runner,
    )

    assert svc.enumerate_devices() == ["AK Virtual Camera"]


def test_command_installer_service_returns_failed_on_invalid_json() -> None:
    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout="not-json",
            stderr="",
        ),
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALL_FAILED
    assert status.last_error == "status command returned invalid JSON"


def test_command_installer_service_install_extension_uses_install_command() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        install_command=["akvc-macos-install"],
        runner=runner,
    )

    assert svc.install_extension() is True
    assert calls == [["akvc-macos-install"]]


def test_command_installer_service_uninstall_extension_uses_uninstall_command() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        uninstall_command=["akvc-macos-uninstall"],
        runner=runner,
    )

    assert svc.uninstall_extension() is True
    assert calls == [["akvc-macos-uninstall"]]


def test_command_installer_service_sync_ipc_configuration_uses_command_and_env() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "installed",
                    "shared_memory_name": "/akvc-custom",
                    "ipc_transport": "shared_memory_ringbuffer",
                }
            ),
            stderr="",
        )

    svc = CommandMacInstallerService(
        sync_ipc_command=["akvc-macos-sync-ipc"],
        runner=runner,
    )

    result = svc.sync_ipc_configuration_result("/akvc-custom")

    assert result == SyncIPCConfigurationResult(
        supported=True,
        success=True,
        phase="sync_command_succeeded",
        shared_memory_name="/akvc-custom",
        ipc_transport="shared_memory_ringbuffer",
        returncode=0,
        stdout=json.dumps(
            {
                "state": "installed",
                "shared_memory_name": "/akvc-custom",
                "ipc_transport": "shared_memory_ringbuffer",
            }
        ),
        stderr=None,
    )
    assert svc.sync_ipc_configuration("/akvc-custom") is True
    assert calls == [
        ["/usr/bin/env", "AKVC_MACOS_SHM_NAME=/akvc-custom", "akvc-macos-sync-ipc"],
        ["/usr/bin/env", "AKVC_MACOS_SHM_NAME=/akvc-custom", "akvc-macos-sync-ipc"],
    ]


def test_command_installer_service_sync_ipc_configuration_reports_failures() -> None:
    svc = CommandMacInstallerService(
        sync_ipc_command=["akvc-macos-sync-ipc"],
        runner=lambda command: SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"last_error": "persist failed"}),
            stderr="persist failed",
        ),
    )

    result = svc.sync_ipc_configuration_result("/akvc-custom")

    assert result.supported is True
    assert result.success is False
    assert result.phase == "sync_command_failed"
    assert result.shared_memory_name == "/akvc-custom"
    assert result.last_error == "persist failed"
    assert svc.sync_ipc_configuration("/akvc-custom") is False


def test_command_installer_service_install_extension_polls_until_pending_approval() -> None:
    calls: list[list[str]] = []
    sleep_calls: list[float] = []
    statuses = iter([
        {"state": "not_installed", "devices": []},
        {"state": "install_pending_approval", "devices": []},
    ])

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-status":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(statuses)),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=runner,
        status_poll_attempts=3,
        poll_interval_seconds=0.5,
        sleep_fn=sleep_calls.append,
    )

    result = svc.install_extension_result()

    assert result == InstallExtensionResult(
        success=True,
        phase="pending_approval",
        state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
        status=result.status,
        enumerated_devices=[],
        install_returncode=0,
        install_stdout=None,
        install_stderr=None,
    )
    assert calls == [
        ["akvc-macos-install"],
        ["akvc-macos-status"],
        ["akvc-macos-status"],
    ]
    assert sleep_calls == [0.5]


def test_command_installer_service_uninstall_extension_polls_until_not_installed() -> None:
    calls: list[list[str]] = []
    sleep_calls: list[float] = []
    statuses = iter([
        {"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True},
        {"state": "not_installed", "devices": [], "enabled": False},
    ])
    devices = iter([
        {"devices": ["AK Virtual Camera"]},
        {"devices": []},
    ])

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-status":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(statuses)),
                stderr="",
            )
        if command[0] == "akvc-macos-list-devices":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(devices)),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        uninstall_command=["akvc-macos-uninstall"],
        devices_command=["akvc-macos-list-devices"],
        runner=runner,
        status_poll_attempts=3,
        poll_interval_seconds=0.5,
        sleep_fn=sleep_calls.append,
    )

    result = svc.uninstall_extension_result()

    assert result == UninstallExtensionResult(
        success=True,
        phase="uninstalled",
        state=ExtensionInstallState.NOT_INSTALLED,
        status=result.status,
        enumerated_devices=[],
        uninstall_returncode=0,
        uninstall_stdout=None,
        uninstall_stderr=None,
    )
    assert calls == [
        ["akvc-macos-uninstall"],
        ["akvc-macos-status"],
        ["akvc-macos-list-devices"],
        ["akvc-macos-status"],
        ["akvc-macos-list-devices"],
    ]
    assert sleep_calls == [0.5]


def test_command_installer_service_uninstall_extension_reports_command_failure() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-status":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}),
                stderr="",
            )
        return SimpleNamespace(returncode=1, stdout="", stderr="deactivation failed")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        uninstall_command=["akvc-macos-uninstall"],
        devices_command=["akvc-macos-list-devices"],
        runner=runner,
    )

    result = svc.uninstall_extension_result()

    assert result.success is False
    assert result.phase == "uninstall_command_failed"
    assert result.state is ExtensionInstallState.INSTALLED
    assert result.status.last_error == "deactivation failed"
    assert result.enumerated_devices == ["AK Virtual Camera"]
    assert calls == [
        ["akvc-macos-uninstall"],
        ["akvc-macos-status"],
        ["akvc-macos-list-devices"],
        ["akvc-macos-status"],
    ]


def test_command_installer_service_install_extension_polls_until_device_visible() -> None:
    calls: list[list[str]] = []
    sleep_calls: list[float] = []
    statuses = iter([
        {"state": "installed", "devices": []},
        {"state": "installed", "devices": []},
        {"state": "installed", "devices": []},
        {"state": "installed", "devices": []},
    ])
    devices = iter([
        {"devices": []},
        {"devices": ["AK Virtual Camera"]},
        {"devices": []},
        {"devices": ["AK Virtual Camera"]},
    ])

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-status":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(statuses)),
                stderr="",
            )
        if command[0] == "akvc-macos-list-devices":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(devices)),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        devices_command=["akvc-macos-list-devices"],
        runner=runner,
        status_poll_attempts=3,
        poll_interval_seconds=0.25,
        sleep_fn=sleep_calls.append,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert result.state is ExtensionInstallState.INSTALLED
    assert result.enumerated_devices == ["AK Virtual Camera"]
    assert calls == [
        ["akvc-macos-install"],
        ["akvc-macos-status"],
        ["akvc-macos-list-devices"],
        ["akvc-macos-status"],
        ["akvc-macos-list-devices"],
    ]
    assert sleep_calls == [0.25]


def test_command_installer_service_install_extension_uses_status_snapshot_when_devices_command_missing() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-status":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "state": "installed",
                        "enabled": True,
                        "devices": ["AK Virtual Camera"],
                        "all_devices": ["FaceTime HD Camera", "AK Virtual Camera"],
                        "device_prefix": "AK Virtual Camera",
                    }
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=runner,
        status_poll_attempts=2,
        poll_interval_seconds=0.0,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert result.enumerated_devices == ["AK Virtual Camera"]
    assert result.status.all_devices == ["FaceTime HD Camera", "AK Virtual Camera"]
    assert result.status.device_prefix == "AK Virtual Camera"
    assert calls == [
        ["akvc-macos-install"],
        ["akvc-macos-status"],
    ]


def test_command_installer_service_install_extension_waits_for_device_when_status_snapshot_shows_empty_filtered_devices() -> None:
    sleep_calls: list[float] = []

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "installed",
                    "enabled": True,
                    "devices": [],
                    "all_devices": ["FaceTime HD Camera"],
                    "device_prefix": "AK Virtual Camera",
                }
            )
            if command[0] == "akvc-macos-status"
            else "",
            stderr="",
        ),
        status_poll_attempts=3,
        poll_interval_seconds=0.1,
        sleep_fn=sleep_calls.append,
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "timeout_waiting_for_device"
    assert result.state is ExtensionInstallState.INSTALLED
    assert result.status.all_devices == ["FaceTime HD Camera"]
    assert result.status.device_prefix == "AK Virtual Camera"
    assert sleep_calls == [0.1, 0.1]


def test_command_installer_service_install_extension_fails_when_status_never_converges() -> None:
    sleep_calls: list[float] = []

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "not_installed", "devices": []}) if command[0] == "akvc-macos-status" else "",
            stderr="",
        ),
        status_poll_attempts=3,
        poll_interval_seconds=0.2,
        sleep_fn=sleep_calls.append,
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "timeout_waiting_for_install"
    assert result.state is ExtensionInstallState.NOT_INSTALLED
    assert sleep_calls == [0.2, 0.2]


def test_command_installer_service_install_extension_rejects_failed_state_payload() -> None:
    svc = CommandMacInstallerService(
        install_command=["akvc-macos-install"],
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "state": "install_failed",
                "last_error": "container app executable not found",
            }),
            stderr="",
        ),
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "install_failed"
    assert result.status.last_error == "container app executable not found"


def test_command_installer_service_install_extension_treats_status_query_timeout_failure_as_inconclusive() -> None:
    sleep_calls: list[float] = []

    def runner(command):
        if command[0] == "akvc-macos-install":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "state": "install_failed",
                        "last_error": "system extension status query timed out",
                    }
                ),
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "last_error": "system extension status query timed out",
                }
            ),
            stderr="",
        )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=runner,
        status_poll_attempts=3,
        poll_interval_seconds=0.2,
        sleep_fn=sleep_calls.append,
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "timeout_waiting_for_install"
    assert result.state is ExtensionInstallState.INSTALL_FAILED
    assert result.status.last_error == "system extension status query timed out"
    assert sleep_calls == [0.2, 0.2]


def test_command_installer_service_accepts_pending_approval_from_install_payload_without_requery() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[0] == "akvc-macos-install":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "state": "install_pending_approval",
                        "approval_required": True,
                    }
                ),
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "state": "install_failed",
                    "last_error": "system extension status query timed out",
                }
            ),
            stderr="",
        )

    svc = CommandMacInstallerService(
        status_command=["akvc-macos-status"],
        install_command=["akvc-macos-install"],
        runner=runner,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "pending_approval"
    assert result.state is ExtensionInstallState.INSTALL_PENDING_APPROVAL
    assert calls == [["akvc-macos-install"]]


def test_command_installer_service_install_extension_rejects_nonzero_exit() -> None:
    svc = CommandMacInstallerService(
        install_command=["akvc-macos-install"],
        runner=lambda command: SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"state": "install_failed"}),
            stderr="launch failed",
        ),
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "install_command_failed"
    assert result.install_returncode == 1
    assert result.status.last_error == "launch failed"


def test_command_installer_service_defaults_to_not_installed_without_commands() -> None:
    svc = CommandMacInstallerService()

    status = svc.status()
    install_result = svc.install_extension_result()

    assert status.state is ExtensionInstallState.NOT_INSTALLED
    assert status.devices == []
    assert install_result.success is False
    assert install_result.phase == "install_command_missing"


def test_build_verification_targets_reports_pending_approval_state() -> None:
    targets = build_verification_targets(
        state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
        phase="pending_approval",
        approval_required=True,
        enabled=False,
        devices=[],
    )

    assert len(targets) == 6
    assert all(target["ready"] is False for target in targets)
    assert all("批准" in str(target["status"]) for target in targets)
    assert "Zoom" in str(targets[0]["name"])


def test_build_verification_targets_reports_ready_state() -> None:
    targets = build_verification_targets(
        state=ExtensionInstallState.INSTALLED,
        phase="installed_visible",
        approval_required=False,
        enabled=True,
        devices=["AK Virtual Camera"],
    )

    assert len(targets) == 6
    assert all(target["ready"] is True for target in targets)
    quicktime = next(target for target in targets if target["id"] == "quicktime")
    assert "影片录制" in str(quicktime["steps"][0])
    assert isinstance(quicktime["checks"], list)
    assert "实时画面" in str(quicktime["checks"][1])


def test_build_verification_targets_uses_runtime_device_prefix_when_present() -> None:
    targets = build_verification_targets(
        state=ExtensionInstallState.INSTALLED,
        phase="installed_visible",
        approval_required=False,
        enabled=True,
        devices=["Demo Camera"],
        device_prefix="Demo Camera",
    )

    assert all(target["ready"] is True for target in targets)
    zoom = next(target for target in targets if target["id"] == "zoom")
    assert "Demo Camera" in str(zoom["status"])
    assert "Demo Camera" in str(zoom["steps"][1])
    assert "Demo Camera" in str(zoom["checks"][0])


def test_infer_extension_phase_reports_visible_pending_and_device_waiting_states() -> None:
    assert infer_extension_phase(
        approval_required=False,
        enabled=True,
        devices=["AK Virtual Camera"],
    ) == "installed_visible"
    assert infer_extension_phase(
        approval_required=True,
        enabled=False,
        devices=[],
    ) == "pending_approval"
    assert infer_extension_phase(
        approval_required=False,
        enabled=True,
        devices=[],
    ) == "timeout_waiting_for_device"
    assert infer_extension_phase(
        approval_required=False,
        enabled=False,
        devices=[],
    ) == ""


def test_evaluate_extension_readiness_marks_ipc_environment_blocked() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
        ),
        devices=["AK Virtual Camera"],
        phase="installed_visible",
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "ipc_environment_blocked"
    assert "direct_open_errno=13" in readiness.message
    assert "framebus roundtrip" in readiness.steps[0]
    assert all(target["ready"] is True for target in readiness.verification_targets)


def test_evaluate_extension_readiness_marks_approval_required() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_PENDING_APPROVAL,
            approval_required=True,
            enabled=False,
        ),
        devices=[],
        phase="pending_approval",
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "approval_required"
    assert "批准" in readiness.message
    assert "Open Settings" in readiness.steps[0]


def test_evaluate_extension_readiness_softens_status_query_timeout_failure() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            last_error="system extension status query timed out",
            bundle_path="/Users/admir/workspace/virtual-camera/build/macos/Build/Products/Release/Amaran Desktop.app",
        ),
    )

    assert readiness.ready is False
    assert readiness.phase == "timeout_waiting_for_install"
    assert readiness.blocker_code == "waiting_for_install"
    assert "安装请求已发出" in readiness.message
    assert "系统设置" in readiness.steps[1]


def test_evaluate_extension_readiness_flags_adhoc_host_codesign_blocker() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/Applications/Amaran Desktop.app",
            last_error="The operation couldn’t be completed. (OSSystemExtensionErrorDomain error 1.)",
            host_signature="adhoc",
            host_codesign_summary="Signature=adhoc; TeamIdentifier=not set",
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "host_codesign_invalid"
    assert "Signature=adhoc" in readiness.message
    assert "SIGN_IDENTITY" in readiness.steps[0]
    assert "/Applications/Amaran Desktop.app" in readiness.steps[1]
    assert "open -n -a '/Applications/Amaran Desktop.app' --args --activate" in readiness.steps[2]


def test_evaluate_extension_readiness_flags_host_entitlements_blocker() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/Applications/Amaran Desktop.app",
            last_error="Missing entitlement com.apple.developer.system-extension.install",
            host_signature="Developer ID Application",
            host_team_identifier="XP3H66JF79",
            host_codesign_summary="Signature=Developer ID Application; TeamIdentifier=XP3H66JF79",
            host_entitlements_valid=False,
            host_entitlements_summary=(
                "warning: binary contains an invalid entitlements blob. "
                "The OS will ignore these entitlements."
            ),
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "host_entitlements_invalid"
    assert "invalid entitlements blob" in readiness.message.lower()
    assert "/Applications" in readiness.steps[0]
    assert "open -n -a '/Applications/Amaran Desktop.app' --args --activate" in readiness.steps[2]


def test_evaluate_extension_readiness_uses_runtime_bundle_path_in_manual_host_commands() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/Applications/Amaran Desktop.app",
            last_error="Missing entitlement com.apple.developer.system-extension.install",
            host_signature="Developer ID Application",
            host_team_identifier="XP3H66JF79",
            host_codesign_summary="Signature=Developer ID Application; TeamIdentifier=XP3H66JF79",
            host_entitlements_valid=False,
            host_entitlements_summary="missing entitlement",
        ),
    )

    assert readiness.blocker_code == "host_entitlements_invalid"
    assert "Amaran Desktop.app" in readiness.steps[0]
    assert "open -n -a '/Applications/Amaran Desktop.app' --args --activate" in readiness.steps[2]


def test_evaluate_extension_readiness_flags_missing_notarization_blocker() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/Applications/Amaran Desktop.app",
            last_error="killed by launch policy",
            host_signature="Apple Development",
            host_team_identifier="XP3H66JF79",
            host_codesign_summary="Signature=Apple Development; TeamIdentifier=XP3H66JF79",
            host_gatekeeper_allowed=False,
            host_gatekeeper_summary=(
                "/Applications/Amaran Desktop.app: rejected; "
                "origin=Apple Development: Choshim Wei (53CY9ZZ74X)"
            ),
            host_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            host_notarization_missing=True,
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "host_notarization_missing"
    assert "缺少公证票据" in readiness.message
    assert "Developer ID Application" in readiness.steps[0]
    assert "NOTARY_PROFILE" in readiness.steps[1]


def test_evaluate_extension_readiness_ignores_install_command_entitlement_for_host_controlled_activation() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            extension_identifier="com.sidus.amaran-desktop.cameraextension",
            bundle_path="/Applications/Amaran Desktop.app",
            install_command_path="/tmp/akvc-macos-install",
            install_command_entitlements_valid=False,
            install_command_entitlements_summary=(
                "missing entitlement com.apple.developer.system-extension.install"
            ),
            last_error="system extension status query timed out",
            system_extension_registered=False,
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "system_extension_not_registered"
    assert "systemextensionsctl list" in readiness.message


def test_evaluate_extension_readiness_flags_install_command_notarization_blocker() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/Applications/Amaran Desktop.app",
            last_error="killed by launch policy",
            install_command_path="/tmp/akvc-macos-install",
            install_command_signature="Developer ID Application",
            install_command_team_identifier="XP3H66JF79",
            install_command_codesign_summary="Signature=Developer ID Application; TeamIdentifier=XP3H66JF79",
            install_command_gatekeeper_allowed=False,
            install_command_gatekeeper_summary=(
                "/tmp/akvc-macos-install: rejected; "
                "source=Unnotarized Developer ID; "
                "origin=Developer ID Application: Sidus Link Ltd. (XP3H66JF79)"
            ),
            install_command_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            install_command_notarization_missing=True,
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "install_command_notarization_missing"
    assert "akvc-macos-install" in readiness.message
    assert "Developer ID Application" in readiness.steps[0]
    assert "NOTARY_PROFILE" in readiness.steps[1]


def test_evaluate_extension_readiness_flags_system_extension_not_registered() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            extension_identifier="com.sidus.amaran-desktop.cameraextension",
            last_error="system extension status query timed out",
            system_extension_registered=False,
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "system_extension_not_registered"
    assert "systemextensionsctl list" in readiness.message


def test_evaluate_extension_readiness_does_not_treat_build_tree_notarization_as_release_blocker() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app",
            last_error="system extension status query timed out",
            host_signature="Apple Development",
            host_team_identifier="XP3H66JF79",
            host_codesign_summary="Signature=Apple Development; TeamIdentifier=XP3H66JF79",
            host_gatekeeper_allowed=False,
            host_gatekeeper_summary=(
                "/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app: rejected; "
                "origin=Developer ID Application: Example (XP3H66JF79)"
            ),
            host_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            host_notarization_missing=True,
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "developer_mode_required"
    assert any("systemextensionsctl developer on" in step for step in readiness.steps)


def test_evaluate_extension_readiness_flags_build_tree_apple_development_as_developer_mode_required() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app",
            install_command_path="/tmp/project/build/macos/Build/Products/Release/akvc-macos-install",
            last_error=(
                "The application /tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app "
                "cannot be opened for an unexpected reason, error=Launch failed."
            ),
            host_signature="Apple Development",
            host_team_identifier="XP3H66JF79",
            host_codesign_summary="Signature=Apple Development; TeamIdentifier=XP3H66JF79",
            host_gatekeeper_allowed=False,
            host_gatekeeper_summary=(
                "/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app: rejected; "
                "origin=Apple Development: Choshim Wei (53CY9ZZ74X)"
            ),
            host_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            host_notarization_missing=True,
            install_command_gatekeeper_allowed=False,
            install_command_gatekeeper_summary=(
                "/tmp/project/build/macos/Build/Products/Release/akvc-macos-install: rejected; "
                "origin=Apple Development: Choshim Wei (53CY9ZZ74X)"
            ),
            install_command_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            install_command_notarization_missing=True,
        ),
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "developer_mode_required"
    assert "Apple Development" in readiness.message
    assert "systemextensionsctl developer on" in readiness.steps[0]
    assert "xattr -dr com.apple.quarantine" in readiness.steps[1]


def test_evaluate_extension_readiness_treats_build_tree_developer_id_as_notarization_gap() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALL_FAILED,
            bundle_path="/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app",
            install_command_path="/tmp/project/build/macos/Build/Products/Release/akvc-macos-install",
            last_error=(
                "The application /tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app "
                "cannot be opened for an unexpected reason, error=Launch failed."
            ),
            host_signature="Developer ID",
            host_team_identifier="XP3H66JF79",
            host_codesign_summary="Signature=Developer ID; TeamIdentifier=XP3H66JF79",
            host_gatekeeper_allowed=False,
            host_gatekeeper_summary=(
                "/tmp/project/build/macos/Build/Products/Release/Amaran Desktop.app: rejected; "
                "source=Unnotarized Developer ID; origin=Developer ID Application: Example (XP3H66JF79)"
            ),
            host_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            host_notarization_missing=True,
            install_command_gatekeeper_allowed=False,
            install_command_gatekeeper_summary=(
                "/tmp/project/build/macos/Build/Products/Release/akvc-macos-install: rejected; "
                "source=Unnotarized Developer ID; origin=Developer ID Application: Example (XP3H66JF79)"
            ),
            install_command_distribution_summary="Notary Ticket Missing; Severity=Fatal",
            install_command_notarization_missing=True,
        ),
        phase="install_command_failed",
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "host_notarization_missing"
    assert "缺少公证票据" in readiness.message
    assert "Apple Development" not in readiness.message
    assert "NOTARY_PROFILE" in readiness.steps[1]


def test_evaluate_extension_readiness_ready_steps_use_runtime_device_prefix() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            device_prefix="Demo Camera",
        ),
        devices=["Demo Camera"],
        phase="installed_visible",
    )

    assert readiness.ready is True
    assert "Demo Camera" in readiness.steps[1]
    assert "Demo Camera" in str(readiness.verification_targets[0]["status"])
    assert all(target["ready"] is True for target in readiness.verification_targets)


def test_evaluate_extension_readiness_does_not_let_stale_ipc_override_not_installed() -> None:
    readiness = evaluate_extension_readiness(
        status=ExtensionStatus(
            state=ExtensionInstallState.NOT_INSTALLED,
            enabled=False,
            ipc_probe_present=True,
            ipc_ready=False,
            ipc_environment_blocked=True,
            ipc_last_error="probe status=open_failed; direct_open_errno=13",
        ),
        devices=[],
        phase="",
    )

    assert readiness.ready is False
    assert readiness.blocker_code == "not_installed"
    assert readiness.message == "虚拟摄像头尚未安装。"


def test_inspect_extension_collects_status_devices_and_readiness_once() -> None:
    class FakeInstaller:
        def __init__(self) -> None:
            self.status_calls = 0
            self.device_calls = 0

        def status(self) -> ExtensionStatus:
            self.status_calls += 1
            return ExtensionStatus(
                state=ExtensionInstallState.INSTALLED,
                enabled=True,
                devices=["AK Virtual Camera"],
            )

        def enumerate_devices(self) -> list[str]:
            self.device_calls += 1
            return ["AK Virtual Camera"]

    installer = FakeInstaller()

    snapshot = inspect_extension(installer)

    assert isinstance(snapshot, ExtensionRuntimeSnapshot)
    assert snapshot.status.state is ExtensionInstallState.INSTALLED
    assert snapshot.devices == ["AK Virtual Camera"]
    assert isinstance(snapshot.readiness, ExtensionReadiness)
    assert snapshot.readiness.phase == "installed_visible"
    assert snapshot.readiness.ready is True
    assert snapshot.readiness.blocker_code == "ready"
    assert installer.status_calls == 1
    assert installer.device_calls == 1


def test_inspect_install_result_projects_install_state_into_runtime_snapshot() -> None:
    result = InstallExtensionResult(
        success=True,
        phase="installed_visible",
        state=ExtensionInstallState.INSTALLED,
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            devices=["AK Virtual Camera"],
        ),
        enumerated_devices=["AK Virtual Camera"],
    )

    snapshot = inspect_install_result(result)

    assert isinstance(snapshot, ExtensionRuntimeSnapshot)
    assert snapshot.status.state is ExtensionInstallState.INSTALLED
    assert snapshot.devices == ["AK Virtual Camera"]
    assert snapshot.readiness.phase == "installed_visible"
    assert snapshot.readiness.ready is True
    assert snapshot.readiness.blocker_code == "ready"


def test_build_runtime_snapshot_respects_explicit_phase_for_install_result_style_calls() -> None:
    snapshot = build_runtime_snapshot(
        status=ExtensionStatus(
            state=ExtensionInstallState.INSTALLED,
            enabled=True,
            devices=[],
        ),
        devices=[],
        phase="timeout_waiting_for_device",
    )

    assert snapshot.status.state is ExtensionInstallState.INSTALLED
    assert snapshot.devices == []
    assert snapshot.readiness.phase == "timeout_waiting_for_device"
    assert snapshot.readiness.ready is False
    assert snapshot.readiness.blocker_code == "device_not_visible"


def test_default_installer_service_uses_runtime_discovered_tools(tmp_path, monkeypatch) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")

    monkeypatch.setenv("AKVC_MACOS_STATUS_TOOL", str(status_tool))
    monkeypatch.setenv("AKVC_MACOS_INSTALL_TOOL", str(install_tool))
    monkeypatch.setenv("AKVC_MACOS_LIST_DEVICES_TOOL", str(list_devices_tool))

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[-1].endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        if command[-1].endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = DefaultMacInstallerService(runner=runner)

    assert svc.extension_state() is ExtensionInstallState.INSTALLED
    assert svc.enumerate_devices() == ["AK Virtual Camera"]
    assert svc.install_extension() is True
    assert calls[0][-1] == str(status_tool)
    assert calls[1][-1] == str(list_devices_tool)
    assert calls[2][-1] == str(status_tool)
    assert any(
        command[-1] == str(install_tool)
        or command[-1] == "--activate"
        for command in calls
    )
    assert any(command[-1] == str(status_tool) for command in calls[3:])
    assert any(command[-1] == str(list_devices_tool) for command in calls[3:])


def test_default_installer_service_resolves_framebus_roundtrip_report_from_env(tmp_path, monkeypatch) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    report = tmp_path / "framebus-roundtrip.json"
    status_tool.write_bytes(b"x")
    report.write_text(
        json.dumps(
            {
                "observed": {"status": "ok"},
                "consistency": {"all_checks_passed": True},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AKVC_MACOS_STATUS_TOOL", str(status_tool))
    monkeypatch.setenv("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON", str(report))

    svc = DefaultMacInstallerService(
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"], "enabled": True}),
            stderr="",
        )
    )

    status = svc.status()

    assert status.ipc_probe_present is True
    assert status.ipc_ready is True
    assert status.ipc_environment_blocked is False
    assert status.ipc_probe_path == str(report)


def test_default_installer_service_prefixes_commands_with_host_environment(tmp_path, monkeypatch) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    shm_override = tmp_path / "akvc-macos-shm-name.txt"
    camera_override = tmp_path / "akvc-macos-device-name.txt"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    host_executable.parent.mkdir(parents=True)
    host_executable.write_bytes(b"x")
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(shm_override))
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(camera_override))
    monkeypatch.delenv("AKVC_MACOS_SHM_NAME", raising=False)
    monkeypatch.delenv("AKVC_DEVICE_NAME", raising=False)

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[0] == "/usr/bin/open":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        tool_name = command[-1]
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        host_bundle=str(host_bundle),
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    assert svc.extension_state() is ExtensionInstallState.INSTALLED
    assert svc.enumerate_devices() == ["AK Virtual Camera"]
    assert svc.install_extension() is True
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={host_bundle}" in calls[0]
    assert f"AKVC_HOST_EXECUTABLE={host_executable}" in calls[0]
    assert calls[0][-1] == str(status_tool)
    assert calls[1][0] == "/usr/bin/env"
    assert calls[1][-1] == str(list_devices_tool)
    assert ["/usr/bin/open", "-n", "-a", str(host_bundle), "--args", "--activate"] in calls
    assert all(command[-1] != str(install_tool) for command in calls if command)
    assert shm_override.read_text(encoding="utf-8").strip() == "/akvc-frames-v1"
    assert camera_override.read_text(encoding="utf-8").strip() == "AK Virtual Camera"


def test_default_installer_service_resolves_explicit_relative_host_bundle_to_absolute_path(
    tmp_path,
    monkeypatch,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    host_executable.parent.mkdir(parents=True)
    host_executable.write_bytes(b"x")
    monkeypatch.chdir(tmp_path)

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"]}),
            stderr="",
        )

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        host_bundle="akvc-host.app",
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALLED
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={host_bundle.resolve()}" in calls[0]
    assert f"AKVC_HOST_EXECUTABLE={host_executable.resolve()}" in calls[0]


def test_default_installer_service_accepts_container_app_arguments(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    app_bundle = tmp_path / "MyCameraApp.app"
    app_executable = app_bundle / "Contents" / "MacOS" / "MyCameraApp"
    status_tool.write_bytes(b"x")
    app_executable.parent.mkdir(parents=True)
    app_executable.write_bytes(b"x")

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"]}),
            stderr="",
        )

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        app_bundle=str(app_bundle),
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALLED
    assert svc.container_app_bundle_path == app_bundle.resolve()
    assert svc.container_app_executable_path == app_executable.resolve()
    assert f"AKVC_CONTAINER_APP_BUNDLE={app_bundle.resolve()}" in calls[0]
    assert f"AKVC_CONTAINER_APP_EXECUTABLE={app_executable.resolve()}" in calls[0]
    assert f"AKVC_HOST_APP_BUNDLE={app_bundle.resolve()}" in calls[0]
    assert f"AKVC_HOST_EXECUTABLE={app_executable.resolve()}" in calls[0]


def test_default_installer_service_resolves_container_app_executable_from_cf_bundle_executable(
    tmp_path,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    app_bundle = tmp_path / "Amaran Desktop.app"
    app_executable = app_bundle / "Contents" / "MacOS" / "amaran-desktop"
    info_plist = app_bundle / "Contents" / "Info.plist"
    status_tool.write_bytes(b"x")
    app_executable.parent.mkdir(parents=True)
    app_executable.write_bytes(b"x")
    with info_plist.open("wb") as fh:
        plistlib.dump({"CFBundleExecutable": "amaran-desktop"}, fh)

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "installed", "devices": ["AK Virtual Camera"]}),
            stderr="",
        )

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        app_bundle=str(app_bundle),
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    status = svc.status()

    assert status.state is ExtensionInstallState.INSTALLED
    assert svc.container_app_bundle_path == app_bundle.resolve()
    assert svc.container_app_executable_path == app_executable.resolve()
    assert f"AKVC_CONTAINER_APP_EXECUTABLE={app_executable.resolve()}" in calls[0]
    assert f"AKVC_HOST_EXECUTABLE={app_executable.resolve()}" in calls[0]


def test_default_installer_service_prefixes_uninstall_with_host_environment(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    uninstall_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    host_executable.parent.mkdir(parents=True)
    host_executable.write_bytes(b"x")

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        tool_name = command[-1]
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "not_installed", "devices": [], "enabled": False}),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": []}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        uninstall_tool=str(uninstall_tool),
        devices_tool=str(list_devices_tool),
        host_bundle=str(host_bundle),
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    assert svc.uninstall_extension() is True
    assert ["/usr/bin/open", "-n", "-a", str(host_bundle), "--args", "--deactivate"] in calls
    assert all(command[-1] != str(uninstall_tool) for command in calls if command)


def test_default_installer_service_auto_installs_pkg_before_extension_activation(
    tmp_path,
    monkeypatch,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    host_bundle = tmp_path / "Applications" / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")

    def fake_find_host_bundle(explicit=None):
        if explicit is not None:
            return Path(explicit) if Path(explicit).exists() else None
        return host_bundle if host_bundle.exists() else None

    def fake_find_host_executable(explicit=None):
        if explicit is not None:
            return Path(explicit) if Path(explicit).is_file() else None
        return host_executable if host_executable.is_file() else None

    monkeypatch.setattr(installer_module, "find_macos_host_app_bundle", fake_find_host_bundle)
    monkeypatch.setattr(installer_module, "find_macos_host_executable", fake_find_host_executable)

    calls: list[list[str]] = []
    statuses = iter([
        {"state": "not_installed", "devices": []},
        {"state": "installed", "devices": ["AK Virtual Camera"]},
        {"state": "installed", "devices": ["AK Virtual Camera"]},
    ])

    def runner(command):
        calls.append(list(command))
        tool_name = command[-1]
        if command[0] == "/usr/sbin/installer":
            host_executable.parent.mkdir(parents=True, exist_ok=True)
            host_executable.write_bytes(b"x")
            return SimpleNamespace(returncode=0, stdout="installer ok", stderr="")
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(statuses)),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        package_path=str(pkg_path),
        runner=runner,
        status_poll_attempts=1,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert calls[0] == [str(status_tool)]
    assert calls[1] == ["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"]
    assert calls[2][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={host_bundle}" in calls[2]
    assert f"AKVC_HOST_EXECUTABLE={host_executable}" in calls[2]
    assert calls[2][-1] == str(status_tool)
    assert calls[3][0] == "/usr/bin/env"
    assert calls[3][-1] == str(install_tool)
    assert calls[4][0] == "/usr/bin/env"
    assert calls[4][-1] == str(status_tool)
    assert calls[5][0] == "/usr/bin/env"
    assert calls[5][-1] == str(list_devices_tool)


def test_default_installer_service_surfaces_pkg_install_failure(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")

    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if command[-1].endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "not_installed", "devices": []}),
                stderr="",
            )
        if command[0] == "/usr/sbin/installer":
            return SimpleNamespace(returncode=1, stdout="", stderr="authentication failed")
        raise AssertionError(f"unexpected command: {command}")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        package_path=str(pkg_path),
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "package_install_failed"
    assert result.install_returncode == 1
    assert result.status.last_error == "authentication failed"
    assert calls[0][-1] == str(status_tool)
    assert calls[1] == ["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"]


def test_default_installer_service_surfaces_pkg_install_stdout_failure_when_stderr_is_empty(
    tmp_path,
    monkeypatch,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    host_bundle = tmp_path / "Applications" / "akvc-host.app"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")
    monkeypatch.setattr(installer_module, "find_macos_host_app_bundle", lambda explicit=None: None)
    monkeypatch.setattr(installer_module, "find_macos_host_executable", lambda explicit=None: None)

    def runner(command):
        if command[-1].endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "not_installed", "devices": []}),
                stderr="",
            )
        if command[0] == "/usr/sbin/installer":
            return SimpleNamespace(
                returncode=1,
                stdout="installer: Must be run as root to install this package.",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        package_path=str(pkg_path),
        runner=runner,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "package_install_failed"
    assert result.status.last_error == "installer: Must be run as root to install this package."


def test_default_installer_service_falls_back_to_build_tree_host_when_pkg_install_needs_root(
    tmp_path,
    monkeypatch,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    build_host_bundle = tmp_path / "build" / "macos" / "Build" / "Products" / "Release" / "akvc-host.app"
    build_host_executable = build_host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")
    build_host_executable.parent.mkdir(parents=True, exist_ok=True)
    build_host_executable.write_bytes(b"x")
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(tmp_path / "akvc-macos-shm-name.txt"))
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(tmp_path / "akvc-macos-device-name.txt"))

    monkeypatch.setattr(
        installer_module,
        "find_macos_host_app_bundle",
        lambda explicit=None: (
            Path(explicit) if explicit is not None and Path(explicit).exists() else build_host_bundle
        ),
    )
    monkeypatch.setattr(
        installer_module,
        "find_macos_host_executable",
        lambda explicit=None: (
            Path(explicit) if explicit is not None and Path(explicit).is_file() else build_host_executable
        ),
    )

    calls: list[list[str]] = []
    statuses = iter(
        [
            {"state": "not_installed", "devices": []},
            {"state": "installed", "devices": ["AK Virtual Camera"]},
        ]
    )

    def runner(command):
        calls.append(list(command))
        if command[0] == "/usr/sbin/installer":
            return SimpleNamespace(
                returncode=1,
                stdout="installer: Must be run as root to install this package.",
                stderr="",
            )
        if command[0] == "/usr/bin/open":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        tool_name = command[-1]
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(statuses)),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-install"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        package_path=str(pkg_path),
        runner=runner,
        status_poll_attempts=1,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={build_host_bundle}" in calls[0]
    assert calls[1] == ["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"]
    assert calls[2][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={build_host_bundle}" in calls[2]
    assert f"AKVC_HOST_EXECUTABLE={build_host_executable}" in calls[2]
    assert calls[2][-1] == str(install_tool)
    assert calls[3][0] == "/usr/bin/env"
    assert calls[3][-1] == str(status_tool)
    assert calls[4][0] == "/usr/bin/env"
    assert calls[4][-1] == str(list_devices_tool)


def test_default_installer_service_prefers_direct_host_activation_when_install_tool_is_launch_blocked(
    tmp_path,
    monkeypatch,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    installed_host_bundle = tmp_path / "Applications" / "akvc-host.app"
    installed_host_executable = installed_host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    installed_host_executable.parent.mkdir(parents=True, exist_ok=True)
    installed_host_executable.write_bytes(b"x")
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(tmp_path / "akvc-macos-shm-name.txt"))
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(tmp_path / "akvc-macos-device-name.txt"))

    monkeypatch.setattr(
        installer_module,
        "find_macos_host_app_bundle",
        lambda explicit=None: Path(explicit) if explicit is not None else installed_host_bundle,
    )
    monkeypatch.setattr(
        installer_module,
        "find_macos_host_executable",
        lambda explicit=None: Path(explicit) if explicit is not None else installed_host_executable,
    )

    calls: list[list[str]] = []
    statuses = iter(
        [
            {
                "state": "install_failed",
                "bundle_path": str(installed_host_bundle),
                "install_command_path": str(install_tool),
                "install_command_gatekeeper_allowed": False,
                "install_command_gatekeeper_summary": "rejected",
                "install_command_distribution_summary": "Notary Ticket Missing",
                "install_command_notarization_missing": True,
                "devices": [],
                "enabled": False,
                "approval_required": False,
            },
            {"state": "installed", "devices": ["AK Virtual Camera"]},
        ]
    )

    def runner(command):
        calls.append(list(command))
        if command[0] == "/usr/bin/open":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        tool_name = command[-1]
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(returncode=0, stdout=json.dumps(next(statuses)), stderr="")
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-install"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        runner=runner,
        status_poll_attempts=1,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={installed_host_bundle}" in calls[0]
    assert all(command != ["/usr/bin/open", "-n", "-a", str(installed_host_bundle), "--args", "--activate"] for command in calls)
    assert any(command[-1] == str(install_tool) for command in calls if command[0] == "/usr/bin/env")


def test_default_installer_service_falls_back_to_install_tool_when_direct_host_activation_fails(
    tmp_path,
    monkeypatch,
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    host_executable.parent.mkdir(parents=True, exist_ok=True)
    host_executable.write_bytes(b"x")
    monkeypatch.setenv("AKVC_MACOS_SHM_NAME_FILE", str(tmp_path / "akvc-macos-shm-name.txt"))
    monkeypatch.setenv("AKVC_DEVICE_NAME_FILE", str(tmp_path / "akvc-macos-device-name.txt"))

    calls: list[list[str]] = []
    statuses = iter([
        {"state": "installed", "devices": ["AK Virtual Camera"]},
        {"state": "installed", "devices": ["AK Virtual Camera"]},
    ])

    def runner(command):
        calls.append(list(command))
        if command[0] == "/usr/bin/open":
            return SimpleNamespace(returncode=1, stdout="", stderr="launch failed")
        tool_name = command[-1]
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(returncode=0, stdout=json.dumps(next(statuses)), stderr="")
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-install"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        host_bundle=str(host_bundle),
        runner=runner,
        status_poll_attempts=1,
        codesign_runner=_empty_codesign_runner,
        policy_runner=_empty_policy_runner,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert calls[0][0] == "/usr/bin/env"
    assert calls[1] == ["/usr/bin/open", "-n", "-a", str(host_bundle), "--args", "--activate"]
    assert any(command[-1] == str(install_tool) for command in calls if command and command[0] == "/usr/bin/env")


def test_default_installer_service_reports_pkg_install_failure_when_installed_host_is_still_missing(
    tmp_path, monkeypatch
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    build_host_bundle = tmp_path / "build" / "macos" / "Build" / "Products" / "Release" / "akvc-host.app"
    build_host_executable = build_host_bundle / "Contents" / "MacOS" / "akvc-host"
    installed_host_bundle = tmp_path / "Applications" / "akvc-host.app"
    installed_host_executable = installed_host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")
    build_host_executable.parent.mkdir(parents=True, exist_ok=True)
    build_host_executable.write_bytes(b"x")

    calls: list[list[str]] = []

    def fake_find_host_bundle(explicit=None):
        if explicit is not None:
            return Path(explicit) if Path(explicit).exists() else None
        if installed_host_bundle.exists():
            return installed_host_bundle
        return build_host_bundle

    def fake_find_host_executable(explicit=None):
        if explicit is not None:
            return Path(explicit) if Path(explicit).is_file() else None
        if installed_host_executable.is_file():
            return installed_host_executable
        return build_host_executable

    monkeypatch.setattr(installer_module, "find_macos_host_app_bundle", fake_find_host_bundle)
    monkeypatch.setattr(installer_module, "find_macos_host_executable", fake_find_host_executable)

    def runner(command):
        calls.append(list(command))
        if command[-1].endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "state": "install_failed",
                        "last_error": "system extension status query timed out",
                        "devices": [],
                        "enabled": False,
                        "approval_required": False,
                    }
                ),
                stderr="",
            )
        if command[0] == "/usr/sbin/installer":
            return SimpleNamespace(returncode=0, stdout="installer ok", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        package_path=str(pkg_path),
        runner=runner,
    )

    result = svc.install_extension_result()

    assert result.success is False
    assert result.phase == "package_install_failed"
    assert result.install_returncode == 0
    assert result.install_stdout == "installer ok"
    assert "was not discovered afterwards" in (result.status.last_error or "")
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_CONTAINER_APP_BUNDLE={build_host_bundle}" in calls[0]
    assert f"AKVC_CONTAINER_APP_EXECUTABLE={build_host_executable}" in calls[0]
    assert f"AKVC_HOST_APP_BUNDLE={build_host_bundle}" in calls[0]
    assert f"AKVC_HOST_EXECUTABLE={build_host_executable}" in calls[0]
    assert calls[0][-1] == str(status_tool)
    assert calls[1] == ["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"]


def test_default_installer_service_auto_installs_pkg_when_only_build_tree_host_exists(
    tmp_path, monkeypatch
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    build_host_bundle = tmp_path / "build" / "macos" / "Build" / "Products" / "Release" / "akvc-host.app"
    build_host_executable = build_host_bundle / "Contents" / "MacOS" / "akvc-host"
    installed_host_bundle = tmp_path / "Applications" / "akvc-host.app"
    installed_host_executable = installed_host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")
    build_host_executable.parent.mkdir(parents=True, exist_ok=True)
    build_host_executable.write_bytes(b"x")

    calls: list[list[str]] = []
    statuses = iter([
        {
            "state": "install_failed",
            "last_error": "system extension status query timed out",
            "devices": [],
            "enabled": False,
            "approval_required": False,
        },
        {"state": "installed", "devices": ["AK Virtual Camera"]},
        {"state": "installed", "devices": ["AK Virtual Camera"]},
    ])

    def fake_find_host_bundle(explicit=None):
        if explicit is not None:
            return Path(explicit) if Path(explicit).exists() else None
        if installed_host_bundle.exists():
            return installed_host_bundle
        return build_host_bundle

    def fake_find_host_executable(explicit=None):
        if explicit is not None:
            return Path(explicit) if Path(explicit).is_file() else None
        if installed_host_executable.is_file():
            return installed_host_executable
        return build_host_executable

    monkeypatch.setattr(installer_module, "find_macos_host_app_bundle", fake_find_host_bundle)
    monkeypatch.setattr(installer_module, "find_macos_host_executable", fake_find_host_executable)

    def runner(command):
        calls.append(list(command))
        tool_name = command[-1]
        if command[0] == "/usr/sbin/installer":
            installed_host_executable.parent.mkdir(parents=True, exist_ok=True)
            installed_host_executable.write_bytes(b"x")
            return SimpleNamespace(returncode=0, stdout="installer ok", stderr="")
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(next(statuses)),
                stderr="",
            )
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        package_path=str(pkg_path),
        runner=runner,
        status_poll_attempts=1,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={build_host_bundle}" in calls[0]
    assert calls[1] == ["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"]
    assert calls[2][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={installed_host_bundle}" in calls[2]
    assert f"AKVC_HOST_EXECUTABLE={installed_host_executable}" in calls[2]
    assert calls[2][-1] == str(status_tool)
    assert calls[3][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={installed_host_bundle}" in calls[3]
    assert f"AKVC_HOST_EXECUTABLE={installed_host_executable}" in calls[3]
    assert calls[3][-1] == str(install_tool)


def test_default_installer_service_reinstalls_pkg_when_installed_host_launch_policy_is_stale(
    tmp_path, monkeypatch
) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    installed_host_bundle = tmp_path / "Applications" / "akvc-host.app"
    installed_host_executable = installed_host_bundle / "Contents" / "MacOS" / "akvc-host"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    pkg_path.write_bytes(b"pkg")
    installed_host_executable.parent.mkdir(parents=True, exist_ok=True)
    installed_host_executable.write_bytes(b"x")

    monkeypatch.setattr(
        installer_module,
        "find_macos_host_app_bundle",
        lambda explicit=None: Path(explicit) if explicit is not None else installed_host_bundle,
    )
    monkeypatch.setattr(
        installer_module,
        "find_macos_host_executable",
        lambda explicit=None: Path(explicit) if explicit is not None else installed_host_executable,
    )

    calls: list[list[str]] = []
    statuses = iter(
        [
            {
                "state": "install_failed",
                "bundle_path": str(installed_host_bundle),
                "last_error": "killed by launch policy",
                "host_signature": "Apple Development",
                "host_team_identifier": "XP3H66JF79",
                "host_gatekeeper_allowed": False,
                "host_gatekeeper_summary": (
                    f"{installed_host_bundle}: rejected; "
                    "origin=Apple Development: Choshim Wei (53CY9ZZ74X)"
                ),
                "host_distribution_summary": "Notary Ticket Missing; Severity=Fatal",
                "host_notarization_missing": True,
                "devices": [],
                "enabled": False,
                "approval_required": False,
            },
            {"state": "installed", "devices": ["AK Virtual Camera"]},
            {"state": "installed", "devices": ["AK Virtual Camera"]},
        ]
    )

    def runner(command):
        calls.append(list(command))
        tool_name = command[-1]
        if command[0] == "/usr/sbin/installer":
            return SimpleNamespace(returncode=0, stdout="installer ok", stderr="")
        if tool_name.endswith("akvc-macos-status"):
            return SimpleNamespace(returncode=0, stdout=json.dumps(next(statuses)), stderr="")
        if tool_name.endswith("akvc-macos-list-devices"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"devices": ["AK Virtual Camera"]}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    svc = DefaultMacInstallerService(
        status_tool=str(status_tool),
        install_tool=str(install_tool),
        devices_tool=str(list_devices_tool),
        package_path=str(pkg_path),
        runner=runner,
        status_poll_attempts=1,
    )

    result = svc.install_extension_result()

    assert result.success is True
    assert result.phase == "installed_visible"
    assert calls[0][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={installed_host_bundle}" in calls[0]
    assert calls[1] == ["/usr/sbin/installer", "-pkg", str(pkg_path), "-target", "/"]
    assert calls[2][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={installed_host_bundle}" in calls[2]
    assert calls[2][-1] == str(status_tool)
    assert calls[3][0] == "/usr/bin/env"
    assert f"AKVC_HOST_APP_BUNDLE={installed_host_bundle}" in calls[3]
    assert calls[3][-1] == str(install_tool)
