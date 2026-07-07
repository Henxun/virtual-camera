# SPDX-License-Identifier: Apache-2.0
"""Executable checks for macOS packaging scripts."""

from __future__ import annotations

import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER_DIR = ROOT / "installer" / "macos"
DAMAGE_TOLERANT_DMG_ERRORS = (
    "device not configured",
    "设备未配置",
)


def _write_minimal_app_bundle(products_dir: Path) -> Path:
    app = products_dir / "akvc-host.app"
    macos_dir = app / "Contents" / "MacOS"
    resources_dir = app / "Contents" / "Resources"
    ext_dir = app / "Contents" / "Library" / "SystemExtensions" / "com.sidus.amaran-desktop.cameraextension.systemextension" / "Contents"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)
    ext_dir.mkdir(parents=True, exist_ok=True)

    plistlib.dump(
        {
            "CFBundleIdentifier": "com.sidus.amaran-desktop",
            "CFBundleExecutable": "akvc-host",
            "CFBundleName": "akvc-host",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "0.5.0",
        },
        (app / "Contents" / "Info.plist").open("wb"),
    )
    plistlib.dump(
        {
            "CFBundleIdentifier": "com.sidus.amaran-desktop.cameraextension",
            "CFBundleExecutable": "akvc-camera-extension",
            "CFBundleName": "akvc-camera-extension",
            "CFBundlePackageType": "XPC!",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "0.5.0",
        },
        (ext_dir / "Info.plist").open("wb"),
    )

    host_exe = macos_dir / "akvc-host"
    host_exe.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    host_exe.chmod(host_exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    ext_exe = ext_dir / "MacOS" / "akvc-camera-extension"
    ext_exe.parent.mkdir(parents=True, exist_ok=True)
    ext_exe.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    ext_exe.chmod(ext_exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return app


def _is_headless_dmg_failure(output: str) -> bool:
    lowered = output.lower()
    return any(token in lowered for token in DAMAGE_TOLERANT_DMG_ERRORS)


def test_macos_packaging_scripts_produce_pkg_dmg_and_zip(tmp_path) -> None:
    if sys.platform != "darwin":
        return

    build_dir = tmp_path / "build"
    products_dir = build_dir / "Build" / "Products" / "Release"
    products_dir.mkdir(parents=True, exist_ok=True)
    app_bundle = _write_minimal_app_bundle(products_dir)

    env = {
        "BUILD_DIR": str(build_dir),
        "PRODUCTS_DIR": str(products_dir),
        "APP_BUNDLE": str(app_bundle),
        "PKG_PATH": str(build_dir / "VirtualCamera.pkg"),
        "DMG_PATH": str(build_dir / "VirtualCamera.dmg"),
        "ZIP_PATH": str(build_dir / "VirtualCamera.zip"),
    }

    dmg_created = False
    for script_name in ("build_pkg.sh", "build_dmg.sh", "build_zip.sh"):
        completed = subprocess.run(
            ["bash", str(INSTALLER_DIR / script_name)],
            cwd=str(ROOT),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        if script_name == "build_dmg.sh" and completed.returncode != 0:
            output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            if _is_headless_dmg_failure(output):
                continue
        assert completed.returncode == 0, completed.stderr or completed.stdout
        if script_name == "build_dmg.sh":
            dmg_created = True

    assert (build_dir / "VirtualCamera.pkg").is_file()
    assert (build_dir / "VirtualCamera.zip").is_file()
    zip_listing = subprocess.run(
        ["zipinfo", "-1", str(build_dir / "VirtualCamera.zip")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert zip_listing.returncode == 0, zip_listing.stderr
    assert not any(part.startswith("._") or "/._" in part for part in zip_listing.stdout.splitlines())
    if dmg_created:
        assert (build_dir / "VirtualCamera.dmg").is_file()


def test_macos_packaging_scripts_disable_appledouble_metadata() -> None:
    common_text = (INSTALLER_DIR / "common.sh").read_text(encoding="utf-8")
    pkg_text = (INSTALLER_DIR / "build_pkg.sh").read_text(encoding="utf-8")
    zip_text = (INSTALLER_DIR / "build_zip.sh").read_text(encoding="utf-8")
    dmg_text = (INSTALLER_DIR / "build_dmg.sh").read_text(encoding="utf-8")

    assert "akvc_autodetect_container_app_bundle" in common_text
    assert "akvc-host.app" in common_text
    assert "source \"${ROOT}/installer/macos/common.sh\"" in pkg_text
    assert "source \"${ROOT}/installer/macos/common.sh\"" in zip_text
    assert "source \"${ROOT}/installer/macos/common.sh\"" in dmg_text
    assert "APP_BUNDLE=\"${APP_BUNDLE:-}\"" in pkg_text
    assert "APP_BUNDLE=\"${APP_BUNDLE:-}\"" in zip_text
    assert "APP_BUNDLE=\"${APP_BUNDLE:-}\"" in dmg_text
    assert "akvc_autodetect_container_app_bundle \"${PRODUCTS_DIR}\"" in pkg_text
    assert "akvc_autodetect_container_app_bundle \"${PRODUCTS_DIR}\"" in zip_text
    assert "akvc_autodetect_container_app_bundle \"${PRODUCTS_DIR}\"" in dmg_text
    assert "COPYFILE_DISABLE=1" in pkg_text
    assert "COPYFILE_DISABLE=1" in zip_text
    assert "find \"${STAGED_APP}\" -name '._*' -type f -delete" in pkg_text
    assert "find \"${APP_BUNDLE}\" -name '._*' -type f -delete" not in pkg_text
    assert "find \"${APP_BUNDLE}\" -name '._*' -type f -delete" not in zip_text
    assert "force_remove_dir()" in pkg_text
    assert "chmod -R u+w \"${target}\"" in pkg_text
    assert "mktemp -d \"${BUILD_DIR}/pkg-staging.XXXXXX\"" in pkg_text
    assert "failed to reuse staging dir" in pkg_text
    assert "ditto --norsrc --noextattr" in pkg_text
    assert "PKG_ROOT_DIR" in pkg_text
    assert "--root \"${PKG_ROOT_DIR}\"" in pkg_text
    assert "--component" not in pkg_text
    assert "--filter '(^|/)\\._.*'" in pkg_text
    assert "xattr -cr \"${PKG_ROOT_DIR}\"" in pkg_text
    assert "find \"${PKG_ROOT_DIR}\" -name '._*' -type f -delete" in pkg_text
    assert "pkgutil --expand-full \"${COMPONENT_PKG_PATH}\"" in pkg_text
    assert "mkbom -s \"${REPACK_FULL_DIR}/Payload\" \"${REPACK_RAW_DIR}/Bom\"" in pkg_text
    assert "cpio -o --format odc" in pkg_text
    assert "pkgutil --flatten \"${REPACK_RAW_DIR}\"" in pkg_text
    assert "force_remove_dir \"${STAGING_DIR}\"" in pkg_text
    assert "force_remove_dir \"${REPACK_DIR}\"" in pkg_text
    assert "find \"${STAGING_DIR}/$(basename \"${APP_BUNDLE}\")\" -name '._*' -type f -delete" in zip_text
    assert "find \"${STAGING_DIR}\" -name '._*' -type f -delete" in zip_text
