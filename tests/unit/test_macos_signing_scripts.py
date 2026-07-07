# SPDX-License-Identifier: Apache-2.0
"""Executable checks for macOS signing/notarization scripts."""

from __future__ import annotations

import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER_DIR = ROOT / "installer" / "macos"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_minimal_bundles(base: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    app = base / "akvc-host.app"
    demo_app = base / "akvc-demo-app.app"
    ext = base / "com.sidus.amaran-desktop.cameraextension.systemextension"
    (app / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (demo_app / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    embedded_ext = app / "Contents" / "Library" / "SystemExtensions" / ext.name
    (embedded_ext / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (ext / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)

    plistlib.dump(
        {
            "CFBundleIdentifier": "com.sidus.amaran-desktop",
            "CFBundleExecutable": "akvc-host",
            "CFBundlePackageType": "APPL",
        },
        (app / "Contents" / "Info.plist").open("wb"),
    )
    plistlib.dump(
        {
            "CFBundleIdentifier": "com.sidus.amaran-desktop.demo-app",
            "CFBundleExecutable": "akvc-demo-app",
            "CFBundlePackageType": "APPL",
        },
        (demo_app / "Contents" / "Info.plist").open("wb"),
    )
    plistlib.dump(
        {
            "CFBundleIdentifier": "com.sidus.amaran-desktop.cameraextension",
            "CFBundleExecutable": "akvc-camera-extension",
            "CFBundlePackageType": "XPC!",
        },
        (ext / "Contents" / "Info.plist").open("wb"),
    )
    plistlib.dump(
        {
            "CFBundleIdentifier": "com.sidus.amaran-desktop.cameraextension",
            "CFBundleExecutable": "akvc-camera-extension",
            "CFBundlePackageType": "XPC!",
        },
        (embedded_ext / "Contents" / "Info.plist").open("wb"),
    )
    app_entitlements = base / "HostApp.entitlements"
    demo_app_entitlements = base / "DemoApp.entitlements"
    ext_entitlements = base / "CameraExtension.entitlements"
    app_entitlements.write_text("{}", encoding="utf-8")
    demo_app_entitlements.write_text("{}", encoding="utf-8")
    ext_entitlements.write_text("{}", encoding="utf-8")
    return (
        app,
        demo_app,
        ext,
        app_entitlements,
        demo_app_entitlements,
        ext_entitlements,
    )


def test_macos_sign_app_script_requires_extension_bundle(tmp_path) -> None:
    app, _, _, app_entitlements, _, ext_entitlements = _write_minimal_bundles(tmp_path)
    missing_ext = tmp_path / "missing.systemextension"

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "sign_app.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "SIGN_IDENTITY": "Developer ID Application: Example",
            "APP_BUNDLE": str(app),
            "EXT_BUNDLE": str(missing_ext),
            "ENTITLEMENTS_APP": str(app_entitlements),
            "ENTITLEMENTS_EXT": str(ext_entitlements),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "missing extension bundle" in completed.stderr


def test_macos_signing_and_notary_scripts_autodetect_container_bundle_defaults() -> None:
    sign_text = (INSTALLER_DIR / "sign_app.sh").read_text(encoding="utf-8")
    notarize_text = (INSTALLER_DIR / "notarize.sh").read_text(encoding="utf-8")
    staple_text = (INSTALLER_DIR / "staple.sh").read_text(encoding="utf-8")

    assert "source \"${ROOT}/installer/macos/common.sh\"" in sign_text
    assert "source \"${ROOT}/installer/macos/common.sh\"" in notarize_text
    assert "source \"${ROOT}/installer/macos/common.sh\"" in staple_text
    assert "APP_BUNDLE=\"${APP_BUNDLE:-}\"" in sign_text
    assert "APP_BUNDLE=\"${APP_BUNDLE:-}\"" in notarize_text
    assert "APP_BUNDLE=\"${APP_BUNDLE:-}\"" in staple_text
    assert "akvc_autodetect_container_app_bundle \"${PRODUCTS_DIR}\"" in sign_text
    assert "akvc_autodetect_container_app_bundle \"${PRODUCTS_DIR}\"" in notarize_text
    assert "akvc_autodetect_container_app_bundle \"${PRODUCTS_DIR}\"" in staple_text


def test_macos_sign_app_script_signs_extension_then_app_and_runs_assessment(tmp_path) -> None:
    (
        app,
        demo_app,
        ext,
        app_entitlements,
        demo_app_entitlements,
        ext_entitlements,
    ) = _write_minimal_bundles(tmp_path)
    embedded_ext = app / "Contents" / "Library" / "SystemExtensions" / ext.name
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    direct_sender_lib.write_text("dylib", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "calls.log"
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    for tool_name in (
        "akvc-macos-status",
        "akvc-macos-install",
        "akvc-macos-uninstall",
        "akvc-macos-list-devices",
        "akvc-macos-sync-ipc",
    ):
        _write_executable(products_dir / tool_name, "#!/usr/bin/env bash\nexit 0\n")

    _write_executable(
        bin_dir / "codesign",
        "#!/usr/bin/env bash\n"
        "echo \"codesign:$*\" >> \"$LOG_PATH\"\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "sign_app.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LOG_PATH": str(log_path),
            "SIGN_IDENTITY": "Developer ID Application: Example",
            "PRODUCTS_DIR": str(products_dir),
            "APP_BUNDLE": str(app),
            "EXT_BUNDLE": str(ext),
            "DIRECT_SENDER_LIB": str(direct_sender_lib),
            "ENTITLEMENTS_APP": str(app_entitlements),
            "DEMO_APP_BUNDLE": str(demo_app),
            "ENTITLEMENTS_DEMO_APP": str(demo_app_entitlements),
            "ENTITLEMENTS_EXT": str(ext_entitlements),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any("com.sidus.amaran-desktop.cameraextension.systemextension" in line and "--entitlements" in line for line in calls if line.startswith("codesign:"))
    install_sign_lines = [
        line
        for line in calls
        if line.startswith("codesign:")
        and "akvc-macos-install" in line
        and "--sign" in line
    ]
    uninstall_sign_lines = [
        line
        for line in calls
        if line.startswith("codesign:")
        and "akvc-macos-uninstall" in line
        and "--sign" in line
    ]
    assert install_sign_lines
    assert uninstall_sign_lines
    assert all("--entitlements" not in line for line in install_sign_lines)
    assert all("--entitlements" not in line for line in uninstall_sign_lines)
    assert any("libakvc-macos-direct-sender.dylib" in line for line in calls if line.startswith("codesign:"))
    assert any("akvc-host.app" in line and "--deep" in line for line in calls if line.startswith("codesign:"))
    assert any("akvc-demo-app.app" in line and "--deep" in line for line in calls if line.startswith("codesign:"))
    assert any("--remove-signature" in line and "akvc-macos-install" in line for line in calls if line.startswith("codesign:"))
    assert any(line.startswith("spctl:-a -vvv") and str(app) in line for line in calls)
    assert any(line.startswith("spctl:-a -vvv") and str(demo_app) in line for line in calls)


def test_macos_sign_app_script_embeds_configured_provisioning_profiles(tmp_path) -> None:
    app, _, ext, app_entitlements, _, ext_entitlements = _write_minimal_bundles(tmp_path)
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    direct_sender_lib.write_text("dylib", encoding="utf-8")
    host_profile = tmp_path / "host.provisionprofile"
    extension_profile = tmp_path / "extension.provisionprofile"
    host_profile.write_text("host-profile", encoding="utf-8")
    extension_profile.write_text("extension-profile", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "calls.log"
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    for tool_name in (
        "akvc-macos-status",
        "akvc-macos-install",
        "akvc-macos-uninstall",
        "akvc-macos-list-devices",
        "akvc-macos-sync-ipc",
    ):
        _write_executable(products_dir / tool_name, "#!/usr/bin/env bash\nexit 0\n")

    _write_executable(
        bin_dir / "codesign",
        "#!/usr/bin/env bash\n"
        "echo \"codesign:$*\" >> \"$LOG_PATH\"\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "sign_app.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LOG_PATH": str(log_path),
            "SIGN_IDENTITY": "Developer ID Application: Example",
            "PRODUCTS_DIR": str(products_dir),
            "APP_BUNDLE": str(app),
            "EXT_BUNDLE": str(ext),
            "DIRECT_SENDER_LIB": str(direct_sender_lib),
            "ENTITLEMENTS_APP": str(app_entitlements),
            "ENTITLEMENTS_EXT": str(ext_entitlements),
            "HOST_PROVISIONING_PROFILE": str(host_profile),
            "EXTENSION_PROVISIONING_PROFILE": str(extension_profile),
            "HOST_EXPECTED_APP_ID": "",
            "EXT_EXPECTED_APP_ID": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (app / "Contents" / "embedded.provisionprofile").read_text(encoding="utf-8") == "host-profile"
    assert (ext / "Contents" / "embedded.provisionprofile").read_text(encoding="utf-8") == "extension-profile"
    assert (
        app
        / "Contents"
        / "Library"
        / "SystemExtensions"
        / ext.name
        / "Contents"
        / "embedded.provisionprofile"
    ).read_text(encoding="utf-8") == "extension-profile"


def test_macos_sign_app_script_rejects_device_bound_profiles_for_other_macs(tmp_path) -> None:
    app, _, ext, app_entitlements, _, ext_entitlements = _write_minimal_bundles(tmp_path)
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    direct_sender_lib.write_text("dylib", encoding="utf-8")
    host_profile = tmp_path / "host.provisionprofile"
    extension_profile = tmp_path / "extension.provisionprofile"
    host_profile.write_text("host-profile", encoding="utf-8")
    extension_profile.write_text("extension-profile", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    host_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Entitlements</key><dict>
<key>com.apple.application-identifier</key><string>XP3H66JF79.com.sidus.amaran-desktop</string>
</dict>
<key>ProvisionedDevices</key><array><string>OTHER-UDID</string></array>
</dict></plist>
"""
    ext_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Entitlements</key><dict>
<key>com.apple.application-identifier</key><string>XP3H66JF79.com.sidus.amaran-desktop.cameraextension</string>
</dict>
<key>ProvisionedDevices</key><array><string>OTHER-UDID</string></array>
</dict></plist>
"""

    _write_executable(
        bin_dir / "security",
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == *\"host.provisionprofile\"* ]]; then\n"
        f"cat <<'EOF'\n{host_plist}\nEOF\n"
        "else\n"
        f"cat <<'EOF'\n{ext_plist}\nEOF\n"
        "fi\n",
    )
    _write_executable(
        bin_dir / "system_profiler",
        "#!/usr/bin/env bash\n"
        "cat <<'EOF'\n"
        "Hardware:\n"
        "    Hardware Overview:\n"
        "      Provisioning UDID: CURRENT-UDID\n"
        "EOF\n",
    )
    _write_executable(
        bin_dir / "codesign",
        "#!/usr/bin/env bash\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "exit 0\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "sign_app.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SIGN_IDENTITY": "Developer ID Application: Example",
            "APP_BUNDLE": str(app),
            "EXT_BUNDLE": str(ext),
            "DIRECT_SENDER_LIB": str(direct_sender_lib),
            "ENTITLEMENTS_APP": str(app_entitlements),
            "ENTITLEMENTS_EXT": str(ext_entitlements),
            "HOST_PROVISIONING_PROFILE": str(host_profile),
            "EXTENSION_PROVISIONING_PROFILE": str(extension_profile),
            "HOST_EXPECTED_APP_ID": "",
            "EXT_EXPECTED_APP_ID": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert (
        "host provisioning profile does not include this Mac's Provisioning UDID" in completed.stderr
        or "host provisioning profile app identifier mismatch" in completed.stderr
    )


def test_macos_sign_app_script_auto_detects_sign_identity(tmp_path) -> None:
    app, _, ext, app_entitlements, _, ext_entitlements = _write_minimal_bundles(tmp_path)
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    direct_sender_lib.write_text("dylib", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "calls.log"
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    for tool_name in (
        "akvc-macos-status",
        "akvc-macos-install",
        "akvc-macos-uninstall",
        "akvc-macos-list-devices",
        "akvc-macos-sync-ipc",
    ):
        _write_executable(products_dir / tool_name, "#!/usr/bin/env bash\nexit 0\n")

    _write_executable(
        bin_dir / "security",
        "#!/usr/bin/env bash\n"
        "echo '  1) ABCDEF1234567890 \"Developer ID Application: Example Corp (TEAMID)\"'\n",
    )
    _write_executable(
        bin_dir / "codesign",
        "#!/usr/bin/env bash\n"
        "echo \"codesign:$*\" >> \"$LOG_PATH\"\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "sign_app.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LOG_PATH": str(log_path),
            "PRODUCTS_DIR": str(products_dir),
            "APP_BUNDLE": str(app),
            "EXT_BUNDLE": str(ext),
            "DIRECT_SENDER_LIB": str(direct_sender_lib),
            "ENTITLEMENTS_APP": str(app_entitlements),
            "ENTITLEMENTS_EXT": str(ext_entitlements),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any("--sign Developer ID Application: Example Corp (TEAMID)" in line for line in calls)


def test_macos_sign_app_script_falls_back_when_timestamp_service_is_unavailable(tmp_path) -> None:
    app, _, ext, app_entitlements, _, ext_entitlements = _write_minimal_bundles(tmp_path)
    direct_sender_lib = tmp_path / "libakvc-macos-direct-sender.dylib"
    direct_sender_lib.write_text("dylib", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "calls.log"
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    for tool_name in (
        "akvc-macos-status",
        "akvc-macos-install",
        "akvc-macos-uninstall",
        "akvc-macos-list-devices",
        "akvc-macos-sync-ipc",
    ):
        _write_executable(products_dir / tool_name, "#!/usr/bin/env bash\nexit 0\n")

    _write_executable(
        bin_dir / "codesign",
        "#!/usr/bin/env bash\n"
        "echo \"codesign:$*\" >> \"$LOG_PATH\"\n"
        "if printf '%s\\n' \"$*\" | grep -q -- '--timestamp'; then\n"
        "  echo 'The timestamp service is not available.' >&2\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "sign_app.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LOG_PATH": str(log_path),
            "SIGN_IDENTITY": "Developer ID Application: Example",
            "PRODUCTS_DIR": str(products_dir),
            "APP_BUNDLE": str(app),
            "EXT_BUNDLE": str(ext),
            "DIRECT_SENDER_LIB": str(direct_sender_lib),
            "ENTITLEMENTS_APP": str(app_entitlements),
            "ENTITLEMENTS_EXT": str(ext_entitlements),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "retrying without --timestamp" in completed.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any("--timestamp" in line for line in calls if line.startswith("codesign:"))
    assert any("--timestamp" not in line for line in calls if line.startswith("codesign:"))


def test_macos_notarize_script_rejects_unsigned_pkg(tmp_path) -> None:
    pkg_path = tmp_path / "VirtualCamera.pkg"
    pkg_path.write_text("pkg", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "submit.log"

    _write_executable(
        bin_dir / "pkgutil",
        "#!/usr/bin/env bash\n"
        "echo 'Package \"VirtualCamera.pkg\":'\n"
        "echo '   Status: no signature'\n",
    )
    _write_executable(
        bin_dir / "xcrun",
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"--find\" ] && [ \"$2\" = \"notarytool\" ]; then\n"
        "  echo /usr/bin/notarytool\n"
        "  exit 0\n"
        "fi\n"
        "echo \"$*\" >> \"$MARKER_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "notarize.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PKG_PATH": str(pkg_path),
            "NOTARY_PROFILE": "ExampleProfile",
            "NOTARIZE_TARGETS": "pkg",
            "MARKER_PATH": str(marker),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "pkg must be signed before notarization" in completed.stderr
    assert not marker.exists()


def test_macos_notarize_script_submits_app_archive_before_pkg(tmp_path) -> None:
    app, _, _, _, _, _ = _write_minimal_bundles(tmp_path)
    pkg_path = tmp_path / "VirtualCamera.pkg"
    pkg_path.write_text("pkg", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "calls.log"

    _write_executable(
        bin_dir / "pkgutil",
        "#!/usr/bin/env bash\n"
        "echo \"pkgutil:$*\" >> \"$LOG_PATH\"\n"
        "echo 'Package \"VirtualCamera.pkg\":'\n"
        "echo '   Status: signed by a developer certificate issued by Apple'\n",
    )
    _write_executable(
        bin_dir / "xcrun",
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"--find\" ] && [ \"$2\" = \"notarytool\" ]; then\n"
        "  echo /usr/bin/notarytool\n"
        "  exit 0\n"
        "fi\n"
        "echo \"xcrun:$*\" >> \"$LOG_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "notarize.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "APP_BUNDLE": str(app),
            "PKG_PATH": str(pkg_path),
            "NOTARY_PROFILE": "ExampleProfile",
            "LOG_PATH": str(log_path),
            "NOTARIZE_TARGETS": "app,pkg",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    submit_calls = [line for line in calls if line.startswith("xcrun:notarytool submit ")]
    assert len(submit_calls) == 2
    assert ".app.zip --keychain-profile ExampleProfile --wait" in submit_calls[0]
    assert str(pkg_path) in submit_calls[1]


def test_macos_staple_script_runs_app_and_pkg_assessment(tmp_path) -> None:
    app, _, _, _, _, _ = _write_minimal_bundles(tmp_path)
    pkg_path = tmp_path / "VirtualCamera.pkg"
    pkg_path.write_text("pkg", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "calls.log"

    _write_executable(
        bin_dir / "pkgutil",
        "#!/usr/bin/env bash\n"
        "echo \"pkgutil:$*\" >> \"$LOG_PATH\"\n",
    )
    _write_executable(
        bin_dir / "xcrun",
        "#!/usr/bin/env bash\n"
        "echo \"xcrun:$*\" >> \"$LOG_PATH\"\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
    )

    completed = subprocess.run(
        ["bash", str(INSTALLER_DIR / "staple.sh")],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "APP_BUNDLE": str(app),
            "PKG_PATH": str(pkg_path),
            "LOG_PATH": str(log_path),
            "STAPLE_TARGETS": "app,pkg",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("pkgutil:--check-signature") for line in calls)
    assert any("xcrun:stapler staple" in line and str(app) in line for line in calls)
    assert any("xcrun:stapler validate" in line and str(app) in line for line in calls)
    assert any(line.startswith("spctl:-a -vvv") and str(app) in line for line in calls)
    assert any("xcrun:stapler staple" in line for line in calls)
    assert any("xcrun:stapler validate" in line for line in calls)
    assert any(line.startswith("spctl:-a -vvv -t install") and str(pkg_path) in line for line in calls)
