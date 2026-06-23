# SPDX-License-Identifier: Apache-2.0
"""Runtime locator tests."""

from __future__ import annotations

from pathlib import Path

import akvc.runtime as runtime
from akvc.runtime import find_dshow_dll, find_helper_exe, find_mf_dll


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


def test_packaged_runtime_assets_are_discoverable() -> None:
    helper = find_helper_exe()
    dshow = find_dshow_dll()
    mf = find_mf_dll()

    assert helper is not None and helper.name == "akvc_helper.exe"
    assert dshow is not None and dshow.name == "akvc-dshow.dll"
    assert mf is not None and mf.name == "akvc-mf.dll"
    assert Path(helper).is_file()
    assert Path(dshow).is_file()
    assert Path(mf).is_file()
