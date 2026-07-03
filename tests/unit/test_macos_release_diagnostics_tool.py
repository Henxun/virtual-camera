# SPDX-License-Identifier: Apache-2.0
"""Checks for the macOS release diagnostics helper."""

from __future__ import annotations

import json
import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "macos_release_diagnostics.py"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_bundle(bundle_path: Path, bundle_id: str, executable_name: str, package_type: str) -> None:
    macos_dir = bundle_path / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)
    plistlib.dump(
        {
            "CFBundleIdentifier": bundle_id,
            "CFBundleExecutable": executable_name,
            "CFBundlePackageType": package_type,
            "LSMinimumSystemVersion": "13.0",
        },
        (bundle_path / "Contents" / "Info.plist").open("wb"),
    )
    (macos_dir / executable_name).write_text("binary", encoding="utf-8")


def test_macos_release_diagnostics_tool_exists_and_declares_expected_surface() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert SCRIPT.is_file()
    assert "--app-bundle" in text
    assert "--extension-bundle" in text
    assert "--pkg-path" in text
    assert "--dmg-path" in text
    assert "--zip-path" in text
    assert "--sync-ipc-tool" in text
    assert "command_tools_signed" in text
    assert "command_tools_universal2_ready" in text
    assert "codesign" in text
    assert "pkgutil" in text
    assert "spctl" in text
    assert "stapler" in text
    assert "lipo" in text
    assert "universal2_ready" in text
    assert "pkg_payload_appledouble_clean" in text
    assert "sync_ipc_tool_universal2_ready" in text
    assert "app_gatekeeper_accepted" in text
    assert "app_stapled" in text
    assert "pkg_gatekeeper_accepted" in text
    assert "pkg_stapled" in text
    assert "_detect_default_app_bundle" in text


def test_macos_release_diagnostics_detects_embedded_container_bundle(tmp_path) -> None:
    products_dir = tmp_path / "Build" / "Products" / "Release"
    products_dir.mkdir(parents=True, exist_ok=True)
    host = products_dir / "akvc-host.app"
    main_app = products_dir / "Amaran Desktop.app"
    extension_name = "com.sidus.amaran-desktop.cameraextension.systemextension"

    _write_bundle(host, "com.sidus.amaran-desktop", "akvc-host", "APPL")
    _write_bundle(main_app, "com.sidus.amaran-desktop", "Amaran Desktop", "APPL")
    _write_bundle(
        main_app / "Contents" / "Library" / "SystemExtensions" / extension_name,
        "com.sidus.amaran-desktop.cameraextension",
        "akvc-camera-extension",
        "XPC!",
    )

    from tools import macos_release_diagnostics as tool

    detected = tool._detect_default_app_bundle(products_dir=products_dir)

    assert detected == main_app


def test_macos_release_diagnostics_deprioritizes_legacy_akvc_host_bundle(tmp_path) -> None:
    products_dir = tmp_path / "Build" / "Products" / "Release"
    products_dir.mkdir(parents=True, exist_ok=True)
    legacy_host = products_dir / "akvc-host.app"
    main_app = products_dir / "zz-main-container.app"
    extension_name = "com.sidus.amaran-desktop.cameraextension.systemextension"

    _write_bundle(legacy_host, "com.sidus.amaran-desktop", "akvc-host", "APPL")
    _write_bundle(main_app, "com.sidus.amaran-desktop", "zz-main-container", "APPL")
    _write_bundle(
        legacy_host / "Contents" / "Library" / "SystemExtensions" / extension_name,
        "com.sidus.amaran-desktop.cameraextension",
        "akvc-camera-extension",
        "XPC!",
    )
    _write_bundle(
        main_app / "Contents" / "Library" / "SystemExtensions" / extension_name,
        "com.sidus.amaran-desktop.cameraextension",
        "akvc-camera-extension",
        "XPC!",
    )

    from tools import macos_release_diagnostics as tool

    detected = tool._detect_default_app_bundle(products_dir=products_dir)

    assert detected == main_app


def test_macos_release_diagnostics_detects_demo_app_when_no_external_app_exists(
    tmp_path,
) -> None:
    products_dir = tmp_path / "Build" / "Products" / "Release"
    products_dir.mkdir(parents=True, exist_ok=True)
    demo_app = products_dir / "akvc-demo-app.app"
    extension_name = "com.sidus.amaran-desktop.cameraextension.systemextension"

    _write_bundle(
        demo_app,
        "com.sidus.amaran-desktop.demo-app",
        "akvc-demo-app",
        "APPL",
    )
    _write_bundle(
        demo_app / "Contents" / "Library" / "SystemExtensions" / extension_name,
        "com.sidus.amaran-desktop.cameraextension",
        "akvc-camera-extension",
        "XPC!",
    )

    from tools import macos_release_diagnostics as tool

    detected = tool._detect_default_app_bundle(products_dir=products_dir)

    assert detected == demo_app


def test_macos_release_diagnostics_tool_reports_artifact_and_signature_summary(tmp_path, monkeypatch) -> None:
    app = tmp_path / "akvc-host.app"
    extension = tmp_path / "com.sidus.amaran-desktop.cameraextension.systemextension"
    pkg = tmp_path / "VirtualCamera.pkg"
    dmg = tmp_path / "VirtualCamera.dmg"
    zip_artifact = tmp_path / "VirtualCamera.zip"
    sync_ipc_tool = tmp_path / "akvc-macos-sync-ipc"
    command_tools = [
        tmp_path / "akvc-macos-status",
        tmp_path / "akvc-macos-install",
        tmp_path / "akvc-macos-uninstall",
        tmp_path / "akvc-macos-list-devices",
        sync_ipc_tool,
    ]
    output = tmp_path / "release-diagnostics.json"

    _write_bundle(app, "com.sidus.amaran-desktop", "akvc-host", "APPL")
    _write_bundle(extension, "com.sidus.amaran-desktop.cameraextension", "akvc-camera-extension", "XPC!")
    embedded_extension = app / "Contents" / "Library" / "SystemExtensions" / extension.name
    _write_bundle(embedded_extension, "com.sidus.amaran-desktop.cameraextension", "akvc-camera-extension", "XPC!")
    pkg.write_text("pkg", encoding="utf-8")
    dmg.write_text("dmg", encoding="utf-8")
    zip_artifact.write_text("zip", encoding="utf-8")
    for tool in command_tools:
        tool.write_text("binary", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "lipo",
        "#!/usr/bin/env bash\n"
        "echo 'arm64 x86_64'\n",
    )
    _write_executable(
        bin_dir / "codesign",
        "#!/usr/bin/env bash\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "spctl",
        "#!/usr/bin/env bash\n"
        "echo 'accepted'\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "pkgutil",
        """#!/usr/bin/env bash
if [ "$1" = "--check-signature" ]; then
  echo 'Package "VirtualCamera.pkg":'
  echo '   Status: signed by a developer certificate issued by Apple for distribution'
  exit 0
fi
if [ "$1" = "--payload-files" ]; then
  cat <<'EOF'
.
./akvc-host.app
./akvc-host.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension
EOF
  exit 0
fi
if [ "$1" = "--expand-full" ]; then
  mkdir -p "$3"
  cat > "$3/PackageInfo" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<pkg-info identifier="com.akvc.virtual-camera.pkg" version="0.5.0" format-version="2" install-location="/Applications" auth="root">
  <payload numberOfFiles="13" installKBytes="347"/>
  <bundle path="./akvc-host.app" id="com.sidus.amaran-desktop" CFBundleShortVersionString="0.5.0" CFBundleVersion="1"/>
</pkg-info>
EOF
  exit 0
fi
exit 1
""",
    )
    _write_executable(
        bin_dir / "xcrun",
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"stapler\" ] && [ \"$2\" = \"validate\" ]; then\n"
        "  echo 'The validate action worked!'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--app-bundle",
            str(app),
            "--extension-bundle",
            str(extension),
            "--pkg-path",
            str(pkg),
            "--dmg-path",
            str(dmg),
            "--zip-path",
            str(zip_artifact),
            "--sync-ipc-tool",
            str(sync_ipc_tool),
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["artifacts"]["app_bundle"]["bundle_identifier"] == "com.sidus.amaran-desktop"
    assert payload["artifacts"]["extension_bundle"]["bundle_identifier"] == "com.sidus.amaran-desktop.cameraextension"
    assert payload["artifacts"]["sync_ipc_tool"]["exists"] is True
    assert set(payload["artifacts"]["command_tools"]) == {
        "install",
        "list_devices",
        "status",
        "sync_ipc",
        "uninstall",
    }
    assert payload["artifacts"]["sync_ipc_tool"]["architectures"] == ["arm64", "x86_64"]
    assert payload["artifacts"]["app_bundle"]["architectures"] == ["arm64", "x86_64"]
    assert payload["artifacts"]["pkg"]["signed"] is True
    assert payload["artifacts"]["pkg"]["payload_appledouble_files"] == []
    assert payload["artifacts"]["pkg"]["payload_appledouble_clean"] is True
    assert payload["artifacts"]["pkg"]["package_info"]["identifier"] == "com.akvc.virtual-camera.pkg"
    assert payload["artifacts"]["pkg"]["package_info"]["install_location"] == "/Applications"
    assert payload["summary"]["app_signed"] is True
    assert payload["summary"]["app_gatekeeper_accepted"] is True
    assert payload["summary"]["app_stapled"] is True
    assert payload["summary"]["extension_signed"] is True
    assert payload["summary"]["pkg_signed"] is True
    assert payload["summary"]["pkg_gatekeeper_accepted"] is True
    assert payload["summary"]["pkg_stapled"] is True
    assert payload["summary"]["universal2_ready"] is True
    assert payload["summary"]["release_artifacts_present"] is True
    assert payload["summary"]["pkg_install_location_expected"] is True
    assert payload["summary"]["pkg_identifier_expected"] is True
    assert payload["summary"]["pkg_includes_extension_payload"] is True
    assert payload["summary"]["pkg_payload_appledouble_clean"] is True
    assert payload["summary"]["host_bundle_identifier_expected"] is True
    assert payload["summary"]["extension_bundle_identifier_expected"] is True
    assert payload["summary"]["minimum_system_version_expected"] is True
    assert payload["summary"]["host_embeds_extension_bundle"] is True
    assert payload["summary"]["command_tools_exist"] is True
    assert payload["summary"]["command_tools_signed"] is True
    assert payload["summary"]["command_tools_universal2_ready"] is True
    assert payload["summary"]["sync_ipc_tool_exists"] is True
    assert payload["summary"]["sync_ipc_tool_signed"] is True
    assert payload["summary"]["sync_ipc_tool_universal2_ready"] is True
