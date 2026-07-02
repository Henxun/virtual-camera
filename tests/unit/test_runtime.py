# SPDX-License-Identifier: Apache-2.0
"""Runtime locator tests."""

from __future__ import annotations

from pathlib import Path

from apps.desktop.akvc_app.services import windows_runtime as runtime
from apps.desktop.akvc_app.services.windows_runtime import find_dshow_dll, find_helper_exe, find_mf_dll


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
    helper = tmp_path / "akvc_helper.exe"
    helper.write_bytes(b"x")

    monkeypatch.setattr(runtime, "_PACKAGE_RUNTIME_DIR", tmp_path)

    assert runtime._resource_path("akvc_helper.exe") == helper


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


def test_runtime_locator_returns_none_when_no_asset_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_PACKAGE_RUNTIME_DIR", tmp_path / "missing-package")
    monkeypatch.setattr(runtime, "_STAGED_RUNTIME_DIR", tmp_path / "missing-stage")
    monkeypatch.setattr(runtime, "_build_search_roots", lambda: [tmp_path / "missing-build"])
    monkeypatch.setattr(runtime.resources, "files", lambda _pkg: Path(tmp_path / "missing-importlib"))

    assert find_helper_exe() is None
    assert find_dshow_dll() is None
    assert find_mf_dll() is None
