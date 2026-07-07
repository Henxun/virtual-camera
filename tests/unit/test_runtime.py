# SPDX-License-Identifier: Apache-2.0
"""Runtime locator tests."""

from __future__ import annotations

from pathlib import Path

import akvc.runtime as runtime
from akvc.runtime import (
    find_dshow_dll,
    find_helper_exe,
    find_macos_container_app_bundle,
    find_macos_container_app_executable,
    find_macos_direct_sender_library,
    find_macos_extension_bundle,
    find_macos_framebus_roundtrip_report,
    find_macos_host_app_bundle,
    find_macos_host_executable,
    find_macos_install_tool,
    find_macos_list_devices_tool,
    find_macos_pkg,
    find_macos_session_manifest,
    find_macos_status_tool,
    find_macos_sync_ipc_tool,
    find_macos_uninstall_tool,
    find_mf_dll,
    resolve_macos_container_app,
)


def test_explicit_runtime_paths_win_over_other_sources(tmp_path) -> None:
    helper = tmp_path / "akvc_helper.exe"
    dshow = tmp_path / "akvc-dshow.dll"
    mf = tmp_path / "akvc-mf.dll"
    helper.write_bytes(b"x")
    dshow.write_bytes(b"x")
    mf.write_bytes(b"x")

    assert find_helper_exe(helper) == helper
    assert find_dshow_dll(dshow) == dshow
    assert find_mf_dll(mf) == mf


def test_runtime_package_dir_is_checked_before_importlib_resources(tmp_path, monkeypatch) -> None:
    helper = tmp_path / "_runtime" / "windows" / "akvc_helper.exe"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_PACKAGE_ROOT", tmp_path)

    assert runtime._resource_path("_runtime/windows/akvc_helper.exe") == helper


def test_staged_runtime_assets_are_discoverable(tmp_path, monkeypatch) -> None:
    helper = tmp_path / "akvc_helper.exe"
    dshow = tmp_path / "akvc-dshow.dll"
    mf = tmp_path / "akvc-mf.dll"
    helper.write_bytes(b"x")
    dshow.write_bytes(b"x")
    mf.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_STAGED_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path / "missing-build"])

    assert find_helper_exe() == helper
    assert find_dshow_dll() == dshow
    assert find_mf_dll() == mf


def test_packaged_runtime_assets_are_discoverable_from_package_dir(tmp_path, monkeypatch) -> None:
    helper = tmp_path / "akvc_helper.exe"
    dshow = tmp_path / "akvc-dshow.dll"
    mf = tmp_path / "akvc-mf.dll"
    helper.write_bytes(b"x")
    dshow.write_bytes(b"x")
    mf.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_PACKAGE_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(runtime, "_STAGED_RUNTIME_DIR", tmp_path / "missing")
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path / "missing-build"])

    assert find_helper_exe() == helper
    assert find_dshow_dll() == dshow
    assert find_mf_dll() == mf


def test_packaged_macos_extension_bundle_is_discoverable_from_package_dir(tmp_path, monkeypatch) -> None:
    extension = tmp_path / "com.sidus.amaran-desktop.cameraextension.systemextension"
    (extension / "Contents").mkdir(parents=True)

    monkeypatch.setattr(runtime, "_PACKAGE_MACOS_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path / "missing-build"])

    assert find_macos_extension_bundle() == extension


def test_runtime_locator_returns_none_when_no_asset_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_PACKAGE_RUNTIME_DIR", tmp_path / "missing-package")
    monkeypatch.setattr(runtime, "_STAGED_RUNTIME_DIR", tmp_path / "missing-stage")
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path / "missing-build"])
    monkeypatch.setattr(runtime.resources, "files", lambda _pkg: Path(tmp_path / "missing-importlib"))

    assert find_helper_exe() is None
    assert find_dshow_dll() is None
    assert find_mf_dll() is None


def test_explicit_macos_tool_paths_win_over_other_sources(tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    pkg = tmp_path / "VirtualCamera.pkg"
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    framebus_report = tmp_path / "framebus-roundtrip.json"
    session_manifest = tmp_path / "session-manifest.json"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    sync_ipc_tool.write_bytes(b"x")
    direct_sender_lib.write_bytes(b"x")
    uninstall_tool.write_bytes(b"x")
    pkg.write_bytes(b"x")
    framebus_report.write_text("{}", encoding="utf-8")
    session_manifest.write_text("{}", encoding="utf-8")
    host_executable.parent.mkdir(parents=True)
    host_executable.write_bytes(b"x")

    assert find_macos_status_tool(status_tool) == status_tool
    assert find_macos_install_tool(install_tool) == install_tool
    assert find_macos_list_devices_tool(list_devices_tool) == list_devices_tool
    assert find_macos_sync_ipc_tool(sync_ipc_tool) == sync_ipc_tool
    assert find_macos_direct_sender_library(direct_sender_lib) == direct_sender_lib
    assert find_macos_uninstall_tool(uninstall_tool) == uninstall_tool
    assert find_macos_pkg(pkg) == pkg
    assert find_macos_framebus_roundtrip_report(framebus_report) == framebus_report
    assert find_macos_session_manifest(session_manifest) == session_manifest
    assert find_macos_host_app_bundle(host_bundle) == host_bundle
    assert find_macos_host_executable(host_executable) == host_executable


def test_macos_tool_paths_can_be_resolved_from_env(tmp_path, monkeypatch) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    pkg = tmp_path / "VirtualCamera.pkg"
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    framebus_report = tmp_path / "framebus-roundtrip.json"
    session_manifest = tmp_path / "session-manifest.json"
    status_tool.write_bytes(b"x")
    install_tool.write_bytes(b"x")
    list_devices_tool.write_bytes(b"x")
    sync_ipc_tool.write_bytes(b"x")
    direct_sender_lib.write_bytes(b"x")
    uninstall_tool.write_bytes(b"x")
    pkg.write_bytes(b"x")
    framebus_report.write_text("{}", encoding="utf-8")
    session_manifest.write_text("{}", encoding="utf-8")
    host_executable.parent.mkdir(parents=True)
    host_executable.write_bytes(b"x")

    monkeypatch.setenv("AKVC_MACOS_STATUS_TOOL", str(status_tool))
    monkeypatch.setenv("AKVC_MACOS_INSTALL_TOOL", str(install_tool))
    monkeypatch.setenv("AKVC_MACOS_LIST_DEVICES_TOOL", str(list_devices_tool))
    monkeypatch.setenv("AKVC_MACOS_SYNC_IPC_TOOL", str(sync_ipc_tool))
    monkeypatch.setenv("AKVC_MACOS_DIRECT_SENDER_LIB", str(direct_sender_lib))
    monkeypatch.setenv("AKVC_MACOS_UNINSTALL_TOOL", str(uninstall_tool))
    monkeypatch.setenv("AKVC_MACOS_PKG", str(pkg))
    monkeypatch.setenv("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON", str(framebus_report))
    monkeypatch.setenv("AKVC_MACOS_SESSION_MANIFEST_JSON", str(session_manifest))
    monkeypatch.setenv("AKVC_HOST_APP_BUNDLE", str(host_bundle))
    monkeypatch.setenv("AKVC_HOST_EXECUTABLE", str(host_executable))

    assert find_macos_status_tool() == status_tool
    assert find_macos_install_tool() == install_tool
    assert find_macos_list_devices_tool() == list_devices_tool
    assert find_macos_sync_ipc_tool() == sync_ipc_tool
    assert find_macos_direct_sender_library() == direct_sender_lib
    assert find_macos_uninstall_tool() == uninstall_tool
    assert find_macos_pkg() == pkg
    assert find_macos_framebus_roundtrip_report() == framebus_report
    assert find_macos_session_manifest() == session_manifest
    assert find_macos_host_app_bundle() == host_bundle
    assert find_macos_host_executable() == host_executable


def test_macos_container_app_paths_prefer_container_env_over_host_env(tmp_path, monkeypatch) -> None:
    host_bundle = tmp_path / "akvc-host.app"
    host_executable = host_bundle / "Contents" / "MacOS" / "akvc-host"
    container_bundle = tmp_path / "MyApp.app"
    container_executable = container_bundle / "Contents" / "MacOS" / "MyApp"
    host_executable.parent.mkdir(parents=True)
    container_executable.parent.mkdir(parents=True)
    host_executable.write_bytes(b"x")
    container_executable.write_bytes(b"x")

    monkeypatch.setenv("AKVC_HOST_APP_BUNDLE", str(host_bundle))
    monkeypatch.setenv("AKVC_HOST_EXECUTABLE", str(host_executable))
    monkeypatch.setenv("AKVC_CONTAINER_APP_BUNDLE", str(container_bundle))
    monkeypatch.setenv("AKVC_CONTAINER_APP_EXECUTABLE", str(container_executable))

    assert find_macos_container_app_bundle() == container_bundle
    assert find_macos_container_app_executable() == container_executable


def test_macos_host_paths_fall_back_to_container_env(tmp_path, monkeypatch) -> None:
    container_bundle = tmp_path / "MyDesktop.app"
    container_executable = container_bundle / "Contents" / "MacOS" / "MyDesktop"
    container_executable.parent.mkdir(parents=True)
    container_executable.write_bytes(b"x")

    monkeypatch.delenv("AKVC_HOST_APP_BUNDLE", raising=False)
    monkeypatch.delenv("AKVC_HOST_EXECUTABLE", raising=False)
    monkeypatch.setenv("AKVC_CONTAINER_APP_BUNDLE", str(container_bundle))
    monkeypatch.setenv("AKVC_CONTAINER_APP_EXECUTABLE", str(container_executable))

    assert find_macos_host_app_bundle() == container_bundle
    assert find_macos_host_executable() == container_executable


def test_macos_host_paths_autodetect_preferred_embedded_container_bundle(tmp_path, monkeypatch) -> None:
    products_dir = tmp_path / "build" / "macos" / "Build" / "Products" / "Release"
    legacy_host_bundle = products_dir / "akvc-host.app"
    legacy_host_executable = legacy_host_bundle / "Contents" / "MacOS" / "akvc-host"
    main_bundle = products_dir / "Amaran Desktop.app"
    main_executable = main_bundle / "Contents" / "MacOS" / "Amaran Desktop"
    extension_relpath = (
        Path("Contents")
        / "Library"
        / "SystemExtensions"
        / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )

    legacy_host_executable.parent.mkdir(parents=True)
    main_executable.parent.mkdir(parents=True)
    (legacy_host_bundle / extension_relpath).mkdir(parents=True)
    (main_bundle / extension_relpath).mkdir(parents=True)
    legacy_host_executable.write_bytes(b"x")
    main_executable.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_APPLICATIONS_DIR", tmp_path / "Applications")
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path])
    monkeypatch.delenv("AKVC_HOST_APP_BUNDLE", raising=False)
    monkeypatch.delenv("AKVC_HOST_EXECUTABLE", raising=False)
    monkeypatch.delenv("AKVC_CONTAINER_APP_BUNDLE", raising=False)
    monkeypatch.delenv("AKVC_CONTAINER_APP_EXECUTABLE", raising=False)

    assert find_macos_host_app_bundle() == main_bundle
    assert find_macos_host_executable() == main_executable


def test_macos_host_paths_resolve_demo_app_when_it_is_only_development_container(
    tmp_path,
    monkeypatch,
) -> None:
    products_dir = tmp_path / "build" / "macos" / "Build" / "Products" / "Release"
    demo_app_bundle = products_dir / "akvc-demo-app.app"
    demo_app_executable = demo_app_bundle / "Contents" / "MacOS" / "akvc-demo-app"
    extension_relpath = (
        Path("Contents")
        / "Library"
        / "SystemExtensions"
        / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )

    demo_app_executable.parent.mkdir(parents=True)
    (demo_app_bundle / extension_relpath).mkdir(parents=True)
    demo_app_executable.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_APPLICATIONS_DIR", tmp_path / "Applications")
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path])
    monkeypatch.delenv("AKVC_HOST_APP_BUNDLE", raising=False)
    monkeypatch.delenv("AKVC_HOST_EXECUTABLE", raising=False)
    monkeypatch.delenv("AKVC_CONTAINER_APP_BUNDLE", raising=False)
    monkeypatch.delenv("AKVC_CONTAINER_APP_EXECUTABLE", raising=False)

    assert find_macos_host_app_bundle() == demo_app_bundle
    assert find_macos_host_executable() == demo_app_executable


def test_macos_host_executable_respects_cf_bundle_executable_name(tmp_path, monkeypatch) -> None:
    bundle = tmp_path / "Amaran Desktop.app"
    executable = bundle / "Contents" / "MacOS" / "amaran-desktop"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"x")
    (bundle / "Contents").mkdir(parents=True, exist_ok=True)
    with (bundle / "Contents" / "Info.plist").open("wb") as fh:
        runtime.plistlib.dump({"CFBundleExecutable": "amaran-desktop"}, fh)

    monkeypatch.delenv("AKVC_HOST_EXECUTABLE", raising=False)
    monkeypatch.delenv("AKVC_CONTAINER_APP_EXECUTABLE", raising=False)

    assert find_macos_host_executable(bundle) == executable


def test_resolve_macos_container_app_maps_bundle_to_executable_and_extension(tmp_path) -> None:
    bundle = tmp_path / "MyCameraApp.app"
    executable = bundle / "Contents" / "MacOS" / "MyCameraApp"
    extension = (
        bundle
        / "Contents"
        / "Library"
        / "SystemExtensions"
        / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    executable.parent.mkdir(parents=True)
    extension.mkdir(parents=True)
    executable.write_bytes(b"x")

    descriptor = resolve_macos_container_app(app_bundle=bundle)

    assert descriptor.app_bundle_path == bundle
    assert descriptor.app_executable_path == executable
    assert descriptor.extension_bundle_path == extension
    assert descriptor.installed_in_applications is False
    assert descriptor.source == "explicit"


def test_packaged_macos_runtime_assets_are_discoverable(tmp_path, monkeypatch) -> None:
    runtime_root = tmp_path / "_runtime" / "macos"
    runtime_root.mkdir(parents=True)
    status_tool = runtime_root / "akvc-macos-status"
    install_tool = runtime_root / "akvc-macos-install"
    list_devices_tool = runtime_root / "akvc-macos-list-devices"
    sync_ipc_tool = runtime_root / "akvc-macos-sync-ipc"
    direct_sender_lib = runtime_root / "libakvc-macos-direct-sender.dylib"
    uninstall_tool = runtime_root / "akvc-macos-uninstall"
    pkg = runtime_root / "VirtualCamera.pkg"
    for path in (
        status_tool,
        install_tool,
        list_devices_tool,
        sync_ipc_tool,
        direct_sender_lib,
        uninstall_tool,
        pkg,
    ):
        path.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path / "__missing__"])

    assert find_macos_status_tool() == status_tool
    assert find_macos_install_tool() == install_tool
    assert find_macos_list_devices_tool() == list_devices_tool
    assert find_macos_sync_ipc_tool() == sync_ipc_tool
    assert find_macos_direct_sender_library() == direct_sender_lib
    assert find_macos_uninstall_tool() == uninstall_tool
    assert find_macos_pkg() == pkg


def test_macos_framebus_roundtrip_report_can_be_resolved_from_build_paths(tmp_path, monkeypatch) -> None:
    report = tmp_path / "build" / "macos" / "session" / "framebus-roundtrip.json"
    report.parent.mkdir(parents=True)
    report.write_text("{}", encoding="utf-8")

    monkeypatch.delenv("AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON", raising=False)
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path])

    assert find_macos_framebus_roundtrip_report() == report


def test_macos_session_manifest_can_be_resolved_from_build_paths(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "build" / "macos" / "session" / "session-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")

    monkeypatch.delenv("AKVC_MACOS_SESSION_MANIFEST_JSON", raising=False)
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path])

    assert find_macos_session_manifest() == manifest
