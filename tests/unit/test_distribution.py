# SPDX-License-Identifier: Apache-2.0
"""Tests for pip-install friendly runtime distribution helpers."""

from __future__ import annotations

from pathlib import Path

from akvc.distribution import (
    EmbeddedRuntimeConfig,
    RuntimeAssetLayout,
    build_runtime_env,
    collect_runtime_layout,
    copy_runtime_assets,
    embed_macos_extension_in_app_bundle,
    embed_macos_runtime_in_app_bundle,
    prepare_macos_host_runtime,
)
import akvc.distribution as distribution


def test_collect_runtime_layout_reports_windows_assets(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "akvc_helper.exe"
    dshow = tmp_path / "akvc-dshow.dll"
    helper.write_text("helper", encoding="utf-8")
    dshow.write_text("dshow", encoding="utf-8")

    monkeypatch.setattr(distribution, "find_helper_exe", lambda explicit=None: helper)
    monkeypatch.setattr(distribution, "find_dshow_dll", lambda explicit=None: dshow)
    monkeypatch.setattr(distribution, "find_mf_dll", lambda explicit=None: None)

    layout = collect_runtime_layout("windows")

    assert isinstance(layout, RuntimeAssetLayout)
    assert layout.platform == "win32"
    assert layout.root == tmp_path
    assert layout.as_dict()["akvc_helper.exe"] == helper
    assert layout.as_dict()["akvc-dshow.dll"] == dshow
    assert layout.missing == ("akvc-mf.dll",)
    assert layout.ready is False


def test_copy_runtime_assets_requires_complete_layout_by_default(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "akvc_helper.exe"
    helper.write_text("helper", encoding="utf-8")

    monkeypatch.setattr(distribution, "find_helper_exe", lambda explicit=None: helper)
    monkeypatch.setattr(distribution, "find_dshow_dll", lambda explicit=None: None)
    monkeypatch.setattr(distribution, "find_mf_dll", lambda explicit=None: None)

    try:
        copy_runtime_assets(tmp_path / "out", platform_name="win32")
    except FileNotFoundError as exc:
        assert "akvc-dshow.dll" in str(exc)
        assert "akvc-mf.dll" in str(exc)
    else:
        raise AssertionError("copy_runtime_assets should fail when required assets are missing")


def test_copy_runtime_assets_copies_found_files(monkeypatch, tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    pkg = tmp_path / "VirtualCamera.pkg"

    for path in (
        status_tool,
        install_tool,
        uninstall_tool,
        list_devices_tool,
        sync_ipc_tool,
        direct_sender_lib,
        pkg,
    ):
        path.write_text(path.name, encoding="utf-8")

    monkeypatch.setattr(distribution, "find_macos_status_tool", lambda explicit=None: status_tool)
    monkeypatch.setattr(distribution, "find_macos_install_tool", lambda explicit=None: install_tool)
    monkeypatch.setattr(distribution, "find_macos_uninstall_tool", lambda explicit=None: uninstall_tool)
    monkeypatch.setattr(distribution, "find_macos_list_devices_tool", lambda explicit=None: list_devices_tool)
    monkeypatch.setattr(distribution, "find_macos_sync_ipc_tool", lambda explicit=None: sync_ipc_tool)
    monkeypatch.setattr(distribution, "find_macos_direct_sender_library", lambda explicit=None: direct_sender_lib)
    monkeypatch.setattr(distribution, "find_macos_pkg", lambda explicit=None: pkg)

    target_dir = tmp_path / "bundle-runtime"
    layout = copy_runtime_assets(target_dir, platform_name="darwin")

    assert layout.platform == "darwin"
    assert layout.root == target_dir
    assert layout.ready is True
    assert (target_dir / "akvc-macos-status").read_text(encoding="utf-8") == "akvc-macos-status"
    assert (target_dir / "VirtualCamera.pkg").read_text(encoding="utf-8") == "VirtualCamera.pkg"


def test_build_runtime_env_uses_runtime_dir_and_container_metadata(tmp_path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    for filename in (
        "akvc-macos-status",
        "akvc-macos-install",
        "akvc-macos-uninstall",
        "akvc-macos-list-devices",
        "akvc-macos-sync-ipc",
        "libakvc-macos-direct-sender.dylib",
        "VirtualCamera.pkg",
    ):
        (runtime_dir / filename).write_text(filename, encoding="utf-8")

    app_bundle = tmp_path / "amaran Desktop.app"
    app_executable = app_bundle / "Contents" / "MacOS" / "amaran Desktop"

    env = build_runtime_env(
        platform_name="macos",
        runtime_dir=runtime_dir,
        app_bundle=app_bundle,
        app_executable=app_executable,
    )

    assert env["AKVC_MACOS_STATUS_TOOL"] == str(runtime_dir / "akvc-macos-status")
    assert env["AKVC_MACOS_PKG"] == str(runtime_dir / "VirtualCamera.pkg")
    assert env["AKVC_CONTAINER_APP_BUNDLE"] == str(app_bundle)
    assert env["AKVC_CONTAINER_APP_EXECUTABLE"] == str(app_executable)


def test_embed_macos_runtime_in_app_bundle_uses_default_resources_path(monkeypatch, tmp_path) -> None:
    copied_layout = RuntimeAssetLayout(
        platform="darwin",
        root=tmp_path / "target",
        assets=tuple(),
        missing=tuple(),
    )
    calls: list[tuple[Path, str, bool, bool]] = []

    def fake_copy_runtime_assets(target_dir, *, platform_name=None, overwrite=True, require_complete=True):
        calls.append((Path(target_dir), str(platform_name), overwrite, require_complete))
        return copied_layout

    monkeypatch.setattr(distribution, "copy_runtime_assets", fake_copy_runtime_assets)

    app_bundle = tmp_path / "Demo.app"
    layout = embed_macos_runtime_in_app_bundle(app_bundle)

    assert layout is copied_layout
    assert calls == [
        (
            app_bundle / "Contents" / "Resources" / "virtual_camera" / "macos",
            "darwin",
            True,
            True,
        )
    ]


def test_prepare_macos_host_runtime_returns_layout_and_env(monkeypatch, tmp_path) -> None:
    layout = RuntimeAssetLayout(
        platform="darwin",
        root=tmp_path / "Demo.app" / "Contents" / "Resources" / "virtual_camera" / "macos",
        assets=tuple(),
        missing=tuple(),
    )
    env = {"AKVC_MACOS_STATUS_TOOL": "/tmp/runtime/akvc-macos-status"}

    monkeypatch.setattr(distribution, "embed_macos_runtime_in_app_bundle", lambda *args, **kwargs: layout)
    monkeypatch.setattr(distribution, "build_runtime_env", lambda **kwargs: env)

    app_bundle = tmp_path / "Demo.app"
    prepared = prepare_macos_host_runtime(app_bundle)

    assert isinstance(prepared, EmbeddedRuntimeConfig)
    assert prepared.layout is layout
    assert prepared.env is env


def test_embed_macos_extension_in_app_bundle_copies_extension_directory(monkeypatch, tmp_path) -> None:
    extension = tmp_path / "com.sidus.amaran-desktop.cameraextension.systemextension"
    executable = extension / "Contents" / "MacOS" / "akvc-camera-extension"
    executable.parent.mkdir(parents=True)
    executable.write_text("binary", encoding="utf-8")

    monkeypatch.setattr(distribution, "find_macos_extension_bundle", lambda explicit=None: extension)

    app_bundle = tmp_path / "Demo.app"
    embedded = embed_macos_extension_in_app_bundle(app_bundle)

    assert embedded == (
        app_bundle
        / "Contents"
        / "Library"
        / "SystemExtensions"
        / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    assert (embedded / "Contents" / "MacOS" / "akvc-camera-extension").read_text(encoding="utf-8") == "binary"


def test_prepare_macos_host_runtime_can_embed_extension(monkeypatch, tmp_path) -> None:
    layout = RuntimeAssetLayout(
        platform="darwin",
        root=tmp_path / "Demo.app" / "Contents" / "Resources" / "virtual_camera" / "macos",
        assets=tuple(),
        missing=tuple(),
    )
    extension_path = (
        tmp_path
        / "Demo.app"
        / "Contents"
        / "Library"
        / "SystemExtensions"
        / "com.sidus.amaran-desktop.cameraextension.systemextension"
    )
    env = {"AKVC_MACOS_STATUS_TOOL": "/tmp/runtime/akvc-macos-status"}

    monkeypatch.setattr(distribution, "embed_macos_runtime_in_app_bundle", lambda *args, **kwargs: layout)
    monkeypatch.setattr(distribution, "embed_macos_extension_in_app_bundle", lambda *args, **kwargs: extension_path)
    monkeypatch.setattr(distribution, "build_runtime_env", lambda **kwargs: dict(env))

    app_bundle = tmp_path / "Demo.app"
    prepared = prepare_macos_host_runtime(app_bundle, embed_extension=True)

    assert prepared.extension_bundle_path == extension_path
    assert prepared.env["AKVC_MACOS_EXTENSION_BUNDLE"] == str(extension_path)
