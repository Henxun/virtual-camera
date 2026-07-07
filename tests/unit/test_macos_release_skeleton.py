# SPDX-License-Identifier: Apache-2.0
"""Repository checks for macOS release/CI skeletons."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macos_installer_scripts_exist() -> None:
    installer_dir = ROOT / "installer" / "macos"
    expected = [
        installer_dir / "build_pkg.sh",
        installer_dir / "build_dmg.sh",
        installer_dir / "build_zip.sh",
        installer_dir / "sign_app.sh",
        installer_dir / "notarize.sh",
        installer_dir / "staple.sh",
        installer_dir / "uninstall.sh",
    ]
    for path in expected:
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")


def test_macos_github_actions_workflow_exists() -> None:
    workflow = (ROOT / ".github" / "workflows" / "macos.yml").read_text(encoding="utf-8")
    assert "macos-14" in workflow
    assert "macos-13" in workflow
    assert "xcodegen generate" in workflow
    assert "test_macos_native_skeleton.py" in workflow
    assert "test_macos_smoke_tool.py" in workflow
    assert "test_macos_install_session_tool.py" in workflow
    assert "test_macos_make_tool_wrappers.py" in workflow
    assert "test_macos_native_verify_tool.py" in workflow
    assert "test_macos_status_binary_check_tool.py" in workflow
    assert "test_macos_list_devices_binary_check_tool.py" in workflow
    assert "test_macos_install_result_api.py" in workflow
    assert "test_macos_ipc.py" in workflow
    assert "test_package_lazy_imports.py" in workflow
    assert "test_cli_macos_install.py" in workflow
    assert "test_desktop_macos_install_status.py" in workflow
    assert "test_desktop_main_window.py" in workflow
    assert "test_macos_shm_sink.py" in workflow
    assert "test_macos_packaging_scripts.py" in workflow
    assert "test_macos_signing_scripts.py" in workflow
    assert "test_macos_uninstall_script.py" in workflow
    assert "test_macos_runtime_sync.py" in workflow
    assert "test_macos_benchmark_tool.py" in workflow
    assert "test_macos_app_matrix_contract_tool.py" in workflow
    assert "test_macos_build_contract_tool.py" in workflow
    assert "test_macos_capability_contract_tool.py" in workflow
    assert "test_macos_topology_contract_tool.py" in workflow
    assert "test_macos_readiness_contract_tool.py" in workflow
    assert "test_macos_status_contract_tool.py" in workflow
    assert "test_macos_validation_session_artifact_check_tool.py" in workflow
    assert "test_macos_validation_session_acceptance_tool.py" in workflow
    assert "test_macos_validation_session_summary_tool.py" in workflow
    assert "test_macos_validation_session_summary_contract_tool.py" in workflow
    assert "test_macos_validation_session_contract_tool.py" in workflow
    assert "test_macos_framebus_contract_tool.py" in workflow
    assert "test_macos_framebus_roundtrip_tool.py" in workflow
    assert "test_macos_input_contract_tool.py" in workflow
    assert "test_macos_release_diagnostics_tool.py" in workflow
    assert "test_macos_sdk_contract_tool.py" in workflow
    assert "test_macos_stream_contract_tool.py" in workflow
    assert "test_macos_toolchain_preflight_tool.py" in workflow
    assert "test_macos_validation_report_tool.py" in workflow
    assert "test_pyside6_demo_tool.py" in workflow
    assert "test_macos_validation_session_tool.py" in workflow
    assert "tools/macos_smoke.py" in workflow
    assert "tools/macos_install_session.py" in workflow
    assert "tools/macos_native_verify.py" in workflow
    assert "tools/macos_status_binary_check.py" in workflow
    assert "tools/macos_list_devices_binary_check.py" in workflow
    assert "tools/macos_benchmark.py" in workflow
    assert "tools/macos_app_matrix_contract.py" in workflow
    assert "tools/macos_build_contract.py" in workflow
    assert "tools/macos_capability_contract.py" in workflow
    assert "tools/macos_topology_contract.py" in workflow
    assert "tools/macos_readiness_contract.py" in workflow
    assert "tools/macos_status_contract.py" in workflow
    assert "tools/macos_validation_session_artifact_check.py" in workflow
    assert "tools/macos_validation_session_acceptance.py" in workflow
    assert "tools/macos_validation_session_summary.py" in workflow
    assert "tools/macos_validation_session_summary_contract.py" in workflow
    assert "tools/macos_validation_session_contract.py" in workflow
    assert "tools/macos_framebus_contract.py" in workflow
    assert "tools/macos_framebus_roundtrip.py" in workflow
    assert "tools/macos_input_contract.py" in workflow
    assert "tools/macos_release_diagnostics.py" in workflow
    assert "tools/macos_sdk_contract.py" in workflow
    assert "tools/macos_stream_contract.py" in workflow
    assert "tools/macos_toolchain_preflight.py" in workflow
    assert "tools/macos_validation_report.py" in workflow
    assert "tools/pyside6_virtual_camera_demo.py" in workflow
    assert "tools/macos_validation_session.py" in workflow
    assert "bash -n installer/macos/build_pkg.sh" in workflow
    assert "python tools/make.py validation-session" in workflow
    assert "--run-list-devices-binary-check" in workflow
    assert "python tools/make.py validation-session-artifact-check" in workflow
    assert "python tools/make.py validation-session-acceptance-contract" in workflow
    assert "python tools/make.py validation-session-summary" in workflow
    assert "python tools/make.py release-diagnostics" in workflow
    assert "python tools/make.py package --skip-build --sync-runtime" in workflow
    assert "camera-core/src/akvc/_runtime/macos/VirtualCamera.pkg" in workflow
    assert "build/macos/session/release-diagnostics.json" in workflow
    assert "build/macos/session/status-binary-check.json" in workflow
    assert "build/macos/session/list-devices-binary-check.json" in workflow
    assert "build/macos/session/entrypoints-contract.json" in workflow
    assert "camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc" in workflow
    assert "build/macos/framebus-roundtrip.json" in workflow
    assert "build/macos/session/install-session-report.json" in workflow
    assert "build/macos/session/smoke-report.json" in workflow
    assert "build/macos/session/session-manifest.json" in workflow
    assert "build/macos/session/session-manifest-check.json" in workflow
    assert "build/macos/session/session-acceptance.json" in workflow
    assert "build/macos/session/session-acceptance-contract.json" in workflow
    assert "build/macos/session/session-summary.md" in workflow
    assert "build/macos/session/validation-report.json" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "VirtualCamera.dmg" in workflow
    assert "VirtualCamera.zip" in workflow
    assert "python tools/make.py verify-native" in workflow
    assert "python tools/make.py framebus-roundtrip" in workflow


def test_macos_jenkinsfile_exists() -> None:
    jenkinsfile = (ROOT / "jenkins" / "macos.Jenkinsfile").read_text(encoding="utf-8")
    assert "agent { label 'macos' }" in jenkinsfile
    assert "xcodegen generate --spec project.yml" in jenkinsfile
    assert "python3 tools/make.py build" in jenkinsfile
    assert "test_macos_smoke_tool.py" in jenkinsfile
    assert "test_macos_install_session_tool.py" in jenkinsfile
    assert "test_macos_make_tool_wrappers.py" in jenkinsfile
    assert "test_macos_status_binary_check_tool.py" in jenkinsfile
    assert "test_macos_list_devices_binary_check_tool.py" in jenkinsfile
    assert "test_macos_install_result_api.py" in jenkinsfile
    assert "test_macos_ipc.py" in jenkinsfile
    assert "test_package_lazy_imports.py" in jenkinsfile
    assert "test_cli_macos_install.py" in jenkinsfile
    assert "test_desktop_macos_install_status.py" in jenkinsfile
    assert "test_desktop_main_window.py" in jenkinsfile
    assert "test_macos_shm_sink.py" in jenkinsfile
    assert "test_macos_packaging_scripts.py" in jenkinsfile
    assert "test_macos_signing_scripts.py" in jenkinsfile
    assert "test_macos_uninstall_script.py" in jenkinsfile
    assert "test_macos_runtime_sync.py" in jenkinsfile
    assert "test_macos_benchmark_tool.py" in jenkinsfile
    assert "test_macos_app_matrix_contract_tool.py" in jenkinsfile
    assert "test_macos_build_contract_tool.py" in jenkinsfile
    assert "test_macos_capability_contract_tool.py" in jenkinsfile
    assert "test_macos_topology_contract_tool.py" in jenkinsfile
    assert "test_macos_readiness_contract_tool.py" in jenkinsfile
    assert "test_macos_status_contract_tool.py" in jenkinsfile
    assert "test_macos_validation_session_artifact_check_tool.py" in jenkinsfile
    assert "test_macos_validation_session_acceptance_tool.py" in jenkinsfile
    assert "test_macos_validation_session_summary_tool.py" in jenkinsfile
    assert "test_macos_validation_session_summary_contract_tool.py" in jenkinsfile
    assert "test_macos_validation_session_contract_tool.py" in jenkinsfile
    assert "test_macos_framebus_contract_tool.py" in jenkinsfile
    assert "test_macos_framebus_roundtrip_tool.py" in jenkinsfile
    assert "test_macos_input_contract_tool.py" in jenkinsfile
    assert "test_macos_release_diagnostics_tool.py" in jenkinsfile
    assert "test_macos_sdk_contract_tool.py" in jenkinsfile
    assert "test_macos_stream_contract_tool.py" in jenkinsfile
    assert "test_macos_toolchain_preflight_tool.py" in jenkinsfile
    assert "test_macos_validation_report_tool.py" in jenkinsfile
    assert "test_pyside6_demo_tool.py" in jenkinsfile
    assert "test_macos_validation_session_tool.py" in jenkinsfile
    assert "macos_native_verify.py" in jenkinsfile
    assert "macos_status_binary_check.py" in jenkinsfile
    assert "macos_list_devices_binary_check.py" in jenkinsfile
    assert "macos_install_session.py" in jenkinsfile
    assert "macos_benchmark.py" in jenkinsfile
    assert "macos_app_matrix_contract.py" in jenkinsfile
    assert "macos_build_contract.py" in jenkinsfile
    assert "macos_capability_contract.py" in jenkinsfile
    assert "macos_topology_contract.py" in jenkinsfile
    assert "macos_readiness_contract.py" in jenkinsfile
    assert "macos_status_contract.py" in jenkinsfile
    assert "macos_validation_session_artifact_check.py" in jenkinsfile
    assert "macos_validation_session_acceptance.py" in jenkinsfile
    assert "macos_validation_session_summary.py" in jenkinsfile
    assert "macos_validation_session_summary_contract.py" in jenkinsfile
    assert "macos_validation_session_contract.py" in jenkinsfile
    assert "macos_framebus_contract.py" in jenkinsfile
    assert "macos_framebus_roundtrip.py" in jenkinsfile
    assert "macos_input_contract.py" in jenkinsfile
    assert "macos_release_diagnostics.py" in jenkinsfile
    assert "macos_sdk_contract.py" in jenkinsfile
    assert "macos_stream_contract.py" in jenkinsfile
    assert "macos_toolchain_preflight.py" in jenkinsfile
    assert "macos_validation_report.py" in jenkinsfile
    assert "pyside6_virtual_camera_demo.py" in jenkinsfile
    assert "macos_validation_session.py" in jenkinsfile
    assert "python3 tools/make.py validation-session" in jenkinsfile
    assert "--run-list-devices-binary-check" in jenkinsfile
    assert "python3 tools/make.py validation-session-artifact-check" in jenkinsfile
    assert "python3 tools/make.py validation-session-acceptance-contract" in jenkinsfile
    assert "python3 tools/make.py validation-session-summary" in jenkinsfile
    assert "python3 tools/make.py release-diagnostics" in jenkinsfile
    assert "python3 tools/make.py package --skip-build --sync-runtime" in jenkinsfile
    assert "camera-core/src/akvc/_runtime/macos/VirtualCamera.pkg" in jenkinsfile
    assert "build/macos/session/release-diagnostics.json" in jenkinsfile
    assert "build/macos/session/status-binary-check.json" in jenkinsfile
    assert "build/macos/session/list-devices-binary-check.json" in jenkinsfile
    assert "build/macos/session/entrypoints-contract.json" in jenkinsfile
    assert "camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc" in jenkinsfile
    assert "build/macos/framebus-roundtrip.json" in jenkinsfile
    assert "build/macos/session/install-session-report.json" in jenkinsfile
    assert "build/macos/session/smoke-report.json" in jenkinsfile
    assert "build/macos/session/session-manifest.json" in jenkinsfile
    assert "build/macos/session/session-manifest-check.json" in jenkinsfile
    assert "build/macos/session/session-acceptance.json" in jenkinsfile
    assert "build/macos/session/session-acceptance-contract.json" in jenkinsfile
    assert "build/macos/session/session-summary.md" in jenkinsfile
    assert "build/macos/session/validation-report.json" in jenkinsfile
    assert "python3 tools/make.py verify-native" in jenkinsfile
    assert "python3 tools/make.py framebus-roundtrip" in jenkinsfile
    assert "bash -n installer/macos/build_pkg.sh" in jenkinsfile
    assert "build_dmg.sh" in jenkinsfile
    assert "archiveArtifacts" in jenkinsfile


def test_make_py_exposes_macos_release_entrypoints() -> None:
    make_py = (ROOT / "tools" / "make.py").read_text(encoding="utf-8")
    assert 'sub.add_parser("package")' in make_py
    assert 'sub.add_parser("sign")' in make_py
    assert 'sub.add_parser("notarize")' in make_py
    assert 'sub.add_parser("staple")' in make_py
    assert 'sub.add_parser("smoke")' in make_py
    assert 'sub.add_parser("verify-native")' in make_py
    assert 'sub.add_parser("preflight")' in make_py
    assert 'sub.add_parser("release-diagnostics")' in make_py
    assert 'sub.add_parser("benchmark")' in make_py
    assert 'sub.add_parser("framebus-roundtrip")' in make_py
    assert 'sub.add_parser("list-devices-binary-check")' in make_py
    assert 'sub.add_parser("validation-report")' in make_py
    assert 'sub.add_parser("validation-session")' in make_py
    assert 'sub.add_parser("validation-session-artifact-check")' in make_py
    assert 'sub.add_parser("validation-session-acceptance")' in make_py
    assert 'sub.add_parser("validation-session-acceptance-contract")' in make_py
    assert 'sub.add_parser("validation-session-summary")' in make_py
    assert 'sub.add_parser("install-session")' in make_py
    assert 'sub.add_parser("sync-macos-runtime")' in make_py
    assert '--output' in make_py
    assert '--install-session-json' in make_py
    assert '--smoke-json' in make_py
    assert '--framebus-roundtrip-json' in make_py
    assert '--status-binary-check-json' in make_py
    assert '--install-session-tool' in make_py
    assert '--framebus-roundtrip-tool' in make_py
    assert '--status-binary-check-tool' in make_py
    assert '--list-devices-binary-check-tool' in make_py
    assert '--artifact-check-tool' in make_py
    assert '--acceptance-tool' in make_py
    assert '--summary-tool' in make_py
    assert '--require-existing-artifacts' in make_py
    assert '--smoke-tool' in make_py
    assert '--run-uninstall' in make_py
    assert '--run-install-session' in make_py
    assert '--run-framebus-roundtrip' in make_py
    assert '--run-status-binary-check' in make_py
    assert '--run-list-devices-binary-check' in make_py
    assert "cmd_package_macos" in make_py
    assert "cmd_install_session_macos" in make_py
    assert "cmd_sync_macos_runtime" in make_py
    assert "cmd_smoke_macos" in make_py
    assert "cmd_verify_native_macos" in make_py
    assert "cmd_preflight_macos" in make_py
    assert "cmd_release_diagnostics_macos" in make_py
    assert "cmd_benchmark_macos" in make_py
    assert "cmd_framebus_roundtrip_macos" in make_py
    assert "cmd_list_devices_binary_check_macos" in make_py
    assert "cmd_validation_report_macos" in make_py
    assert "cmd_validation_session_macos" in make_py
    assert "cmd_validation_session_artifact_check_macos" in make_py
    assert "cmd_validation_session_acceptance_macos" in make_py
    assert "cmd_validation_session_acceptance_contract_macos" in make_py
    assert "cmd_validation_session_summary_macos" in make_py


def test_python_package_metadata_carries_macos_runtime_assets() -> None:
    root_pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    core_pyproject = (ROOT / "camera-core" / "pyproject.toml").read_text(encoding="utf-8")

    assert '_runtime/macos/akvc-macos-status' in root_pyproject
    assert '_runtime/macos/akvc-macos-install' in root_pyproject
    assert '_runtime/macos/akvc-macos-uninstall' in root_pyproject
    assert '_runtime/macos/akvc-macos-list-devices' in root_pyproject
    assert '_runtime/macos/akvc-macos-sync-ipc' in root_pyproject
    assert '_runtime/macos/libakvc-macos-direct-sender.dylib' in root_pyproject
    assert '_runtime/macos/VirtualCamera.pkg' in root_pyproject

    assert '[tool.setuptools.package-data]' in core_pyproject
    assert '"akvc" = [' in core_pyproject
    assert '_runtime/windows/akvc_helper.exe' in core_pyproject
    assert '_runtime/windows/akvc-mf.dll' in core_pyproject
    assert '_runtime/windows/akvc-dshow.dll' in core_pyproject
    assert '_runtime/macos/README.md' in core_pyproject
    assert '_runtime/macos/akvc-macos-status' in core_pyproject
    assert '_runtime/macos/akvc-macos-install' in core_pyproject
    assert '_runtime/macos/akvc-macos-uninstall' in core_pyproject
    assert '_runtime/macos/akvc-macos-list-devices' in core_pyproject
    assert '_runtime/macos/akvc-macos-sync-ipc' in core_pyproject
    assert '_runtime/macos/libakvc-macos-direct-sender.dylib' in core_pyproject
    assert '_runtime/macos/VirtualCamera.pkg' in core_pyproject
