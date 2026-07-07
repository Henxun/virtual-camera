# SPDX-License-Identifier: Apache-2.0
"""Unit tests for macOS runtime asset sync paths in tools.make."""

from __future__ import annotations

import argparse

from tools import make as make_tool


def test_sync_macos_runtime_assets_copies_tools_and_pkg(monkeypatch, tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    pkg_path = tmp_path / "VirtualCamera.pkg"
    runtime_dir = tmp_path / "runtime"

    for path in (status_tool, install_tool, uninstall_tool, list_devices_tool, sync_ipc_tool, direct_sender_lib, pkg_path):
        path.write_text(path.name, encoding="utf-8")

    monkeypatch.setattr(make_tool, "MACOS_STATUS_TOOL", status_tool)
    monkeypatch.setattr(make_tool, "MACOS_INSTALL_TOOL", install_tool)
    monkeypatch.setattr(make_tool, "MACOS_UNINSTALL_TOOL", uninstall_tool)
    monkeypatch.setattr(make_tool, "MACOS_LIST_DEVICES_TOOL", list_devices_tool)
    monkeypatch.setattr(make_tool, "MACOS_SYNC_IPC_TOOL", sync_ipc_tool)
    monkeypatch.setattr(make_tool, "MACOS_DIRECT_SENDER_LIB", direct_sender_lib)
    monkeypatch.setattr(make_tool, "MACOS_PKG", pkg_path)
    monkeypatch.setattr(make_tool, "MACOS_RUNTIME_DIR", runtime_dir)

    rc = make_tool._sync_macos_runtime_assets(require_pkg=True)

    assert rc == 0
    assert (runtime_dir / "akvc-macos-status").read_text(encoding="utf-8") == "akvc-macos-status"
    assert (runtime_dir / "akvc-macos-install").read_text(encoding="utf-8") == "akvc-macos-install"
    assert (runtime_dir / "akvc-macos-uninstall").read_text(encoding="utf-8") == "akvc-macos-uninstall"
    assert (runtime_dir / "akvc-macos-list-devices").read_text(encoding="utf-8") == "akvc-macos-list-devices"
    assert (runtime_dir / "akvc-macos-sync-ipc").read_text(encoding="utf-8") == "akvc-macos-sync-ipc"
    assert (runtime_dir / "libakvc-macos-direct-sender.dylib").read_text(encoding="utf-8") == "libakvc-macos-direct-sender.dylib"
    assert (runtime_dir / "VirtualCamera.pkg").read_text(encoding="utf-8") == "VirtualCamera.pkg"


def test_cmd_sync_macos_runtime_requires_pkg_when_requested(monkeypatch, tmp_path) -> None:
    status_tool = tmp_path / "akvc-macos-status"
    install_tool = tmp_path / "akvc-macos-install"
    uninstall_tool = tmp_path / "akvc-macos-uninstall"
    list_devices_tool = tmp_path / "akvc-macos-list-devices"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    runtime_dir = tmp_path / "runtime"

    for path in (status_tool, install_tool, uninstall_tool, list_devices_tool, sync_ipc_tool, direct_sender_lib):
        path.write_text(path.name, encoding="utf-8")

    monkeypatch.setattr(make_tool, "MACOS_STATUS_TOOL", status_tool)
    monkeypatch.setattr(make_tool, "MACOS_INSTALL_TOOL", install_tool)
    monkeypatch.setattr(make_tool, "MACOS_UNINSTALL_TOOL", uninstall_tool)
    monkeypatch.setattr(make_tool, "MACOS_LIST_DEVICES_TOOL", list_devices_tool)
    monkeypatch.setattr(make_tool, "MACOS_SYNC_IPC_TOOL", sync_ipc_tool)
    monkeypatch.setattr(make_tool, "MACOS_DIRECT_SENDER_LIB", direct_sender_lib)
    monkeypatch.setattr(make_tool, "MACOS_PKG", tmp_path / "VirtualCamera.pkg")
    monkeypatch.setattr(make_tool, "MACOS_RUNTIME_DIR", runtime_dir)

    rc = make_tool.cmd_sync_macos_runtime(argparse.Namespace(require_pkg=True))

    assert rc == 2
    assert not runtime_dir.exists()
