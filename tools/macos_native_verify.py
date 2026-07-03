# SPDX-License-Identifier: Apache-2.0
"""Best-effort native verification for the macOS virtual camera tree.

This verifier is intentionally lighter than full `xcodebuild` so it remains
useful on machines where XcodeGen or signing credentials are not available.
    It covers:
- plist validity
- installer script shell syntax
- native source syntax with the active macOS SDK
- capability contract consistency
- distribution/runtime asset contract consistency
- CI/Jenkins artifact publishing contract consistency
- delivery gate contract consistency
- Camera Extension topology contract consistency
- readiness/blocker contract consistency
- status/IPC contract consistency
- validation-session acceptance contract consistency
- validation-session summary contract consistency
- validation-session Markdown summary contract consistency
- Python SDK contract consistency
- Camera Extension stream-behavior contract consistency
- Frame Bus consumer probe syntax
- control-bridge sync-ipc command syntax
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MACOS_ROOT = ROOT / "virtualcam" / "macos"
INSTALLER_DIR = ROOT / "installer" / "macos"


def _run(command: list[str], *, cwd: Path | None = None) -> int:
    print(f"[macos-native-verify] $ {' '.join(command)}")
    return subprocess.call(command, cwd=str(cwd) if cwd else None)


def _sdk_path() -> str:
    out = subprocess.check_output(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
        text=True,
    ).strip()
    if not out:
        raise RuntimeError("xcrun returned an empty macOS SDK path")
    return out


def main() -> int:
    if sys.platform != "darwin":
        print("[macos-native-verify] requires macOS", file=sys.stderr)
        return 1

    sdk = _sdk_path()

    checks: list[tuple[str, list[str]]] = [
        ("demo app plist", ["plutil", "-lint", str(MACOS_ROOT / "demo_app" / "Info.plist")]),
        ("extension plist", ["plutil", "-lint", str(MACOS_ROOT / "camera_extension" / "Info.plist")]),
        (
            "installer shell syntax",
            [
                "bash",
                "-n",
                str(INSTALLER_DIR / "build_pkg.sh"),
                str(INSTALLER_DIR / "build_dmg.sh"),
                str(INSTALLER_DIR / "build_zip.sh"),
                str(INSTALLER_DIR / "sign_app.sh"),
                str(INSTALLER_DIR / "notarize.sh"),
                str(INSTALLER_DIR / "staple.sh"),
                str(INSTALLER_DIR / "uninstall.sh"),
            ],
        ),
        (
            "build contract",
            [
                sys.executable,
                "tools/macos_build_contract.py",
            ],
        ),
        (
            "distribution contract",
            [
                sys.executable,
                "tools/macos_distribution_contract.py",
            ],
        ),
        (
            "CI artifact contract",
            [
                sys.executable,
                "tools/macos_ci_artifact_contract.py",
            ],
        ),
        (
            "delivery gate contract",
            [
                sys.executable,
                "tools/macos_delivery_gate_contract.py",
            ],
        ),
        (
            "signing pipeline contract",
            [
                sys.executable,
                "tools/macos_signing_pipeline_contract.py",
            ],
        ),
        (
            "capability contract",
            [
                sys.executable,
                "tools/macos_capability_contract.py",
            ],
        ),
        (
            "app matrix contract",
            [
                sys.executable,
                "tools/macos_app_matrix_contract.py",
            ],
        ),
        (
            "topology contract",
            [
                sys.executable,
                "tools/macos_topology_contract.py",
            ],
        ),
        (
            "readiness contract",
            [
                sys.executable,
                "tools/macos_readiness_contract.py",
            ],
        ),
        (
            "status contract",
            [
                sys.executable,
                "tools/macos_status_contract.py",
            ],
        ),
        (
            "validation-session contract",
            [
                sys.executable,
                "tools/macos_validation_session_contract.py",
            ],
        ),
        (
            "validation-session acceptance contract",
            [
                sys.executable,
                "tools/macos_validation_session_acceptance_contract.py",
            ],
        ),
        (
            "validation-session summary contract",
            [
                sys.executable,
                "tools/macos_validation_session_summary_contract.py",
            ],
        ),
        (
            "sdk contract",
            [
                sys.executable,
                "tools/macos_sdk_contract.py",
            ],
        ),
        (
            "entrypoints contract",
            [
                sys.executable,
                "tools/macos_entrypoints_contract.py",
            ],
        ),
        (
            "framebus contract",
            [
                sys.executable,
                "tools/macos_framebus_contract.py",
            ],
        ),
        (
            "stream contract",
            [
                sys.executable,
                "tools/macos_stream_contract.py",
            ],
        ),
        (
            "framebus_posix syntax",
            [
                "clang",
                "-fsyntax-only",
                "-std=c11",
                "-isysroot",
                sdk,
                "-mmacosx-version-min=13.0",
                "-Ivirtualcam/macos/ipc/include",
                "-Ivirtualcam/shared",
                "virtualcam/macos/ipc/src/framebus_posix.c",
            ],
        ),
        (
            "framebus consumer probe syntax",
            [
                "clang",
                "-fsyntax-only",
                "-std=c11",
                "-isysroot",
                sdk,
                "-mmacosx-version-min=13.0",
                "-Ivirtualcam/macos/ipc/include",
                "-Ivirtualcam/shared",
                "virtualcam/macos/ipc/src/framebus_consumer_probe.c",
                "virtualcam/macos/ipc/src/framebus_posix.c",
            ],
        ),
        (
            "camera extension syntax",
            [
                "clang++",
                "-fsyntax-only",
                "-std=gnu++20",
                "-x",
                "objective-c++",
                "-fobjc-arc",
                "-isysroot",
                sdk,
                "-mmacosx-version-min=13.0",
                "-Ivirtualcam/macos/ipc/include",
                "-Ivirtualcam/shared",
                "virtualcam/macos/camera_extension/AKVCFrameProvider.mm",
                "virtualcam/macos/camera_extension/AKVCStreamSource.mm",
                "virtualcam/macos/camera_extension/AKVCDeviceSource.mm",
                "virtualcam/macos/camera_extension/AKVCProviderSource.mm",
            ],
        ),
        (
            "control bridge tools syntax",
            [
                "clang++",
                "-fsyntax-only",
                "-std=gnu++20",
                "-x",
                "objective-c++",
                "-fobjc-arc",
                "-isysroot",
                sdk,
                "-mmacosx-version-min=13.0",
                "-Ivirtualcam/macos/ipc/include",
                "-Ivirtualcam/shared",
                "virtualcam/macos/control_bridge/AKVCCommandSupport.mm",
                "virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm",
                "virtualcam/macos/control_bridge/akvc_macos_status.mm",
                "virtualcam/macos/control_bridge/akvc_macos_install.mm",
                "virtualcam/macos/control_bridge/akvc_macos_uninstall.mm",
                "virtualcam/macos/control_bridge/akvc_macos_list_devices.mm",
                "virtualcam/macos/control_bridge/akvc_macos_sync_ipc.mm",
                "virtualcam/macos/ipc/src/macos_ipc.cpp",
                "virtualcam/macos/ipc/src/framebus_posix.c",
            ],
        ),
    ]

    for name, command in checks:
        print(f"[macos-native-verify] running: {name}")
        rc = _run(command, cwd=ROOT)
        if rc != 0:
            return rc

    print("[macos-native-verify] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
