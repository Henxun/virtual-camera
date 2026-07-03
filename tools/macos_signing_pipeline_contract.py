# SPDX-License-Identifier: Apache-2.0
"""Contract checks for the macOS signing/notarization/staple pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import plistlib
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = ROOT / "installer" / "macos"
SIGN_APP_SCRIPT = INSTALLER_DIR / "sign_app.sh"
BUILD_PKG_SCRIPT = INSTALLER_DIR / "build_pkg.sh"
NOTARIZE_SCRIPT = INSTALLER_DIR / "notarize.sh"
STAPLE_SCRIPT = INSTALLER_DIR / "staple.sh"
RELEASE_DIAGNOSTICS_TOOL = ROOT / "tools" / "macos_release_diagnostics.py"
VALIDATION_REPORT_TOOL = ROOT / "tools" / "macos_validation_report.py"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_signing_pipeline_surface(texts: dict[str, str]) -> dict[str, bool]:
    sign_text = texts["sign_app"]
    build_pkg_text = texts["build_pkg"]
    notarize_text = texts["notarize"]
    staple_text = texts["staple"]
    release_text = texts["release_diagnostics"]
    report_text = texts["validation_report"]
    return {
        "sign_app_checks_extension_bundle": "missing extension bundle" in sign_text,
        "sign_app_checks_embedded_extension_bundle": "missing embedded extension bundle" in sign_text,
        "sign_app_checks_direct_sender_library": "missing direct sender library" in sign_text,
        "sign_app_can_auto_detect_sign_identity": "detect_sign_identity()" in sign_text
        and "Developer ID Application:" in sign_text,
        "sign_app_can_fallback_when_timestamp_unavailable": "codesign_with_runtime()" in sign_text
        and "retrying without --timestamp" in sign_text,
        "sign_app_uses_clean_staging_before_sign": "sign_bundle_in_clean_stage()" in sign_text
        and "sign_file_in_clean_stage()" in sign_text
        and "copy_target_for_stage()" in sign_text
        and "replace_target_with_stage()" in sign_text,
        "sign_app_replaces_signed_outputs_atomically": "replace_target_with_stage()" in sign_text
        and 'mv "${source}" "${destination}"' in sign_text
        and 'replace_target_with_stage "${staged_bundle}" "${bundle}"' in sign_text
        and 'replace_target_with_stage "${staged_target}" "${target}"' in sign_text,
        "sign_app_removes_stale_provisioning_profiles_when_unset": 'rm -f "${destination}"' in sign_text
        and 'if [[ -z "${profile_path}" ]]; then' in sign_text,
        "sign_app_checks_command_tools": "missing command tool" in sign_text
        and "akvc-macos-status" in sign_text
        and "akvc-macos-install" in sign_text
        and "akvc-macos-uninstall" in sign_text
        and "akvc-macos-list-devices" in sign_text
        and "akvc-macos-sync-ipc" in sign_text,
        "sign_app_signs_extension_before_app": 'echo "[macos-sign] extension:' in sign_text and 'echo "[macos-sign] app:' in sign_text,
        "sign_app_signs_embedded_extension": 'echo "[macos-sign] embedded extension:' in sign_text
        and 'sign_bundle_in_clean_stage "${EMBEDDED_EXT_BUNDLE}"' in sign_text,
        "sign_app_signs_command_tools": 'echo "[macos-sign] tool:' in sign_text
        and 'sign_file_in_clean_stage "${tool}"' in sign_text,
        "sign_app_signs_direct_sender_library": 'echo "[macos-sign] direct sender dylib:' in sign_text
        and 'sign_file_in_clean_stage "${DIRECT_SENDER_LIB}"' in sign_text,
        "sign_app_verifies_extension_and_app": 'codesign --verify ${verify_args} "${staged_bundle}"' in sign_text
        and 'codesign --verify --strict --verbose=2 "${staged_target}"' in sign_text,
        "sign_app_verifies_final_outputs_after_replace": 'codesign --verify ${verify_args} "${bundle}"' in sign_text
        and 'codesign --verify --strict --verbose=2 "${target}"' in sign_text,
        "sign_app_runs_spctl_assessment": 'spctl -a -vvv "${APP_BUNDLE}"' in sign_text,
        "build_pkg_can_auto_detect_productsign_identity": "detect_productsign_identity()" in build_pkg_text
        and "Developer ID Installer:" in build_pkg_text,
        "build_pkg_optionally_runs_productsign": "PRODUCTSIGN_IDENTITY" in build_pkg_text and "productsign --sign" in build_pkg_text,
        "build_pkg_runs_pkgutil_signature_probe": 'pkgutil --check-signature "${PKG_PATH}"' in build_pkg_text,
        "build_pkg_disables_appledouble_metadata": "COPYFILE_DISABLE=1" in build_pkg_text
        and "find \"${STAGED_APP}\" -name '._*' -type f -delete" in build_pkg_text
        and "ditto --norsrc --noextattr" in build_pkg_text
        and "--filter '(^|/)\\._.*'" in build_pkg_text
        and "xattr -cr \"${PKG_ROOT_DIR}\"" in build_pkg_text
        and "find \"${PKG_ROOT_DIR}\" -name '._*' -type f -delete" in build_pkg_text
        and "mkbom -s \"${REPACK_FULL_DIR}/Payload\" \"${REPACK_RAW_DIR}/Bom\"" in build_pkg_text
        and "cpio -o --format odc" in build_pkg_text,
        "build_pkg_rebuilds_payload_and_bom": 'pkgutil --expand-full "${COMPONENT_PKG_PATH}"' in build_pkg_text
        and 'pkgutil --expand "${COMPONENT_PKG_PATH}"' in build_pkg_text
        and 'pkgutil --flatten "${REPACK_RAW_DIR}" "${REPACK_CLEAN_PKG}"' in build_pkg_text,
        "build_pkg_uses_root_payload_not_component": "--root \"${PKG_ROOT_DIR}\"" in build_pkg_text
        and "--component" not in build_pkg_text,
        "notarize_requires_notary_profile": "NOTARY_PROFILE is required" in notarize_text,
        "notarize_supports_app_archive_submission": 'NOTARIZE_TARGETS="${NOTARIZE_TARGETS:-app,pkg}"' in notarize_text
        and "/usr/bin/ditto -c -k --keepParent --norsrc" in notarize_text
        and 'submit_for_notarization "${APP_ARCHIVE}" "app archive"' in notarize_text,
        "notarize_rejects_unsigned_pkg": "pkg must be signed before notarization" in notarize_text,
        "notarize_uses_notarytool_submit_wait": "xcrun notarytool submit" in notarize_text and "--wait" in notarize_text,
        "staple_supports_app_bundle": 'STAPLE_TARGETS="${STAPLE_TARGETS:-app,pkg}"' in staple_text
        and 'xcrun stapler staple "${APP_BUNDLE}"' in staple_text
        and 'xcrun stapler validate "${APP_BUNDLE}"' in staple_text,
        "staple_runs_pkgutil_check": 'pkgutil --check-signature "${PKG_PATH}"' in staple_text,
        "staple_runs_stapler_staple_and_validate": "xcrun stapler staple" in staple_text and "xcrun stapler validate" in staple_text,
        "staple_runs_spctl_install_assessment": 'spctl -a -vvv -t install "${PKG_PATH}"' in staple_text,
        "staple_runs_spctl_app_assessment": 'spctl -a -vvv "${APP_BUNDLE}"' in staple_text,
        "release_diagnostics_exports_signing_summary": '"app_signed"' in release_text
        and '"app_gatekeeper_accepted"' in release_text
        and '"app_stapled"' in release_text
        and '"extension_signed"' in release_text
        and '"command_tools_signed"' in release_text
        and '"pkg_gatekeeper_accepted"' in release_text
        and '"pkg_stapled"' in release_text
        and '"pkg_signed"' in release_text,
        "validation_report_exports_release_signing_summary": '"release_app_signed"' in report_text
        and '"release_app_gatekeeper_accepted"' in report_text
        and '"release_app_stapled"' in report_text
        and '"release_extension_signed"' in report_text
        and '"release_command_tools_signed"' in report_text
        and '"release_pkg_gatekeeper_accepted"' in report_text
        and '"release_pkg_stapled"' in report_text
        and '"release_pkg_signed"' in report_text,
    }


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _is_codesign_sign_invocation(line: str) -> bool:
    return line.startswith("codesign:") and "--sign " in line


def _line_mentions_basename(line: str, path: Path) -> bool:
    return path.name in line


def _write_minimal_bundles(base: Path) -> tuple[Path, Path, Path, Path]:
    app = base / "akvc-host.app"
    ext = base / "com.sidus.amaran-desktop.cameraextension.systemextension"
    (app / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
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
    ext_entitlements = base / "CameraExtension.entitlements"
    app_entitlements.write_text("{}", encoding="utf-8")
    ext_entitlements.write_text("{}", encoding="utf-8")
    return app, ext, app_entitlements, ext_entitlements


def evaluate_script_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)

        # sign_app
        app, ext, app_entitlements, ext_entitlements = _write_minimal_bundles(tmpdir / "sign")
        embedded_ext = app / "Contents" / "Library" / "SystemExtensions" / ext.name
        products_dir = tmpdir / "sign-products"
        products_dir.mkdir()
        direct_sender_lib = products_dir / "libakvc-macos-direct-sender.dylib"
        direct_sender_lib.write_text("dylib", encoding="utf-8")
        command_tools = [
            products_dir / "akvc-macos-status",
            products_dir / "akvc-macos-install",
            products_dir / "akvc-macos-uninstall",
            products_dir / "akvc-macos-list-devices",
            products_dir / "akvc-macos-sync-ipc",
        ]
        for tool in command_tools:
            _write_executable(tool, "#!/usr/bin/env bash\nexit 0\n")
        sign_bin = tmpdir / "sign-bin"
        sign_bin.mkdir()
        sign_log = tmpdir / "sign-calls.log"
        _write_executable(
            sign_bin / "codesign",
            "#!/usr/bin/env bash\n"
            "echo \"codesign:$*\" >> \"$LOG_PATH\"\n",
        )
        _write_executable(
            sign_bin / "spctl",
            "#!/usr/bin/env bash\n"
            "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
        )
        completed = subprocess.run(
            ["bash", str(SIGN_APP_SCRIPT)],
            cwd=str(ROOT),
            env={
                **os.environ,
                "PATH": f"{sign_bin}:{os.environ['PATH']}",
                "LOG_PATH": str(sign_log),
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
        sign_calls = sign_log.read_text(encoding="utf-8").splitlines() if sign_log.is_file() else []
        sign_invocations = [line for line in sign_calls if _is_codesign_sign_invocation(line)]
        sign_case = {
            "returncode": completed.returncode,
            "signs_extension": sum(
                1 for line in sign_invocations if _line_mentions_basename(line, ext)
            ) >= 2,
            "signs_embedded_extension": sum(
                1 for line in sign_invocations if _line_mentions_basename(line, embedded_ext)
            ) >= 2,
            "signs_app": any(_line_mentions_basename(line, app) for line in sign_invocations),
            "signs_all_command_tools": all(
                any(_line_mentions_basename(line, tool) for line in sign_invocations)
                for tool in command_tools
            ),
            "signs_direct_sender_library": any(
                _line_mentions_basename(line, direct_sender_lib) for line in sign_invocations
            ),
            "signs_extension_before_app": next(
                (index for index, line in enumerate(sign_invocations) if _line_mentions_basename(line, ext)),
                -1,
            ) < next(
                (index for index, line in enumerate(sign_invocations) if _line_mentions_basename(line, app)),
                10**9,
            ),
            "assesses_app": any(line.startswith("spctl:-a -vvv") and str(app) in line for line in sign_calls),
        }
        cases.append(
            {
                "name": "sign_app_signs_extension_then_app_and_assesses_result",
                "actual": sign_case,
                "expected": {
                    "returncode": 0,
                    "signs_extension": True,
                    "signs_embedded_extension": True,
                    "signs_all_command_tools": True,
                    "signs_direct_sender_library": True,
                    "signs_app": True,
                    "signs_extension_before_app": True,
                    "assesses_app": True,
                },
                "all_keys_match": sign_case == {
                    "returncode": 0,
                    "signs_extension": True,
                    "signs_embedded_extension": True,
                    "signs_all_command_tools": True,
                    "signs_direct_sender_library": True,
                    "signs_app": True,
                    "signs_extension_before_app": True,
                    "assesses_app": True,
                },
            }
        )

        stale_profiles_root = tmpdir / "sign-stale-profiles"
        app_with_stale_profile, ext_with_stale_profile, app_entitlements, ext_entitlements = _write_minimal_bundles(
            stale_profiles_root
        )
        embedded_ext_with_stale_profile = (
            app_with_stale_profile / "Contents" / "Library" / "SystemExtensions" / ext_with_stale_profile.name
        )
        (app_with_stale_profile / "Contents" / "embedded.provisionprofile").write_text(
            "stale-app-profile", encoding="utf-8"
        )
        (ext_with_stale_profile / "Contents" / "embedded.provisionprofile").write_text(
            "stale-top-level-extension-profile", encoding="utf-8"
        )
        (embedded_ext_with_stale_profile / "Contents" / "embedded.provisionprofile").write_text(
            "stale-embedded-extension-profile", encoding="utf-8"
        )
        stale_products_dir = tmpdir / "sign-stale-products"
        stale_products_dir.mkdir()
        stale_direct_sender_lib = stale_products_dir / "libakvc-macos-direct-sender.dylib"
        stale_direct_sender_lib.write_text("dylib", encoding="utf-8")
        stale_command_tools = [
            stale_products_dir / "akvc-macos-status",
            stale_products_dir / "akvc-macos-install",
            stale_products_dir / "akvc-macos-uninstall",
            stale_products_dir / "akvc-macos-list-devices",
            stale_products_dir / "akvc-macos-sync-ipc",
        ]
        for tool in stale_command_tools:
            _write_executable(tool, "#!/usr/bin/env bash\nexit 0\n")
        stale_sign_bin = tmpdir / "sign-stale-bin"
        stale_sign_bin.mkdir()
        stale_sign_log = tmpdir / "sign-stale-calls.log"
        _write_executable(
            stale_sign_bin / "codesign",
            "#!/usr/bin/env bash\n"
            "echo \"codesign:$*\" >> \"$LOG_PATH\"\n",
        )
        _write_executable(
            stale_sign_bin / "spctl",
            "#!/usr/bin/env bash\n"
            "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
        )
        completed = subprocess.run(
            ["bash", str(SIGN_APP_SCRIPT)],
            cwd=str(ROOT),
            env={
                **os.environ,
                "PATH": f"{stale_sign_bin}:{os.environ['PATH']}",
                "LOG_PATH": str(stale_sign_log),
                "SIGN_IDENTITY": "Developer ID Application: Example",
                "PRODUCTS_DIR": str(stale_products_dir),
                "APP_BUNDLE": str(app_with_stale_profile),
                "EXT_BUNDLE": str(ext_with_stale_profile),
                "DIRECT_SENDER_LIB": str(stale_direct_sender_lib),
                "ENTITLEMENTS_APP": str(app_entitlements),
                "ENTITLEMENTS_EXT": str(ext_entitlements),
                "HOST_PROVISIONING_PROFILE": "",
                "EXTENSION_PROVISIONING_PROFILE": "",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        stale_profile_case = {
            "returncode": completed.returncode,
            "app_profile_removed": not (app_with_stale_profile / "Contents" / "embedded.provisionprofile").exists(),
            "embedded_extension_profile_removed": not (
                embedded_ext_with_stale_profile / "Contents" / "embedded.provisionprofile"
            ).exists(),
            "top_level_extension_profile_removed": not (
                ext_with_stale_profile / "Contents" / "embedded.provisionprofile"
            ).exists(),
        }
        cases.append(
            {
                "name": "sign_app_clears_stale_provisioning_profiles_when_profiles_are_unset",
                "actual": stale_profile_case,
                "expected": {
                    "returncode": 0,
                    "app_profile_removed": True,
                    "embedded_extension_profile_removed": True,
                    "top_level_extension_profile_removed": True,
                },
                "all_keys_match": stale_profile_case == {
                    "returncode": 0,
                    "app_profile_removed": True,
                    "embedded_extension_profile_removed": True,
                    "top_level_extension_profile_removed": True,
                },
            }
        )

        # build_pkg
        products_dir = tmpdir / "pkg" / "Build" / "Products" / "Release"
        products_dir.mkdir(parents=True, exist_ok=True)
        app_bundle = products_dir / "akvc-host.app"
        (app_bundle / "Contents").mkdir(parents=True, exist_ok=True)
        pkg_bin = tmpdir / "pkg-bin"
        pkg_bin.mkdir()
        pkg_log = tmpdir / "pkg-calls.log"
        _write_executable(
            pkg_bin / "pkgbuild",
            "#!/usr/bin/env bash\n"
            "echo \"pkgbuild:$*\" >> \"$LOG_PATH\"\n"
            "out=\"${@: -1}\"\n"
            "touch \"$out\"\n",
        )
        _write_executable(
            pkg_bin / "productsign",
            "#!/usr/bin/env bash\n"
            "echo \"productsign:$*\" >> \"$LOG_PATH\"\n"
            "in=\"${@: -2:1}\"\n"
            "out=\"${@: -1}\"\n"
            "cp \"$in\" \"$out\"\n",
        )
        _write_executable(
            pkg_bin / "pkgutil",
            "#!/usr/bin/env bash\n"
            "echo \"pkgutil:$*\" >> \"$LOG_PATH\"\n"
            "if [ \"$1\" = \"--expand-full\" ]; then\n"
            "  mkdir -p \"$3/Payload/akvc-host.app/Contents/MacOS\"\n"
            "  printf 'binary' > \"$3/Payload/akvc-host.app/Contents/MacOS/akvc-host\"\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$1\" = \"--expand\" ]; then\n"
            "  mkdir -p \"$3\"\n"
            "  printf 'payload' > \"$3/Payload\"\n"
            "  printf 'bom' > \"$3/Bom\"\n"
            "  printf '<pkg-info identifier=\"com.akvc.virtual-camera.pkg\"/>' > \"$3/PackageInfo\"\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$1\" = \"--flatten\" ]; then\n"
            "  touch \"$3\"\n"
            "  exit 0\n"
            "fi\n"
        )
        build_dir = tmpdir / "pkg"
        pkg_path = build_dir / "VirtualCamera.pkg"
        component_pkg = build_dir / "VirtualCamera.component.pkg"
        completed = subprocess.run(
            ["bash", str(BUILD_PKG_SCRIPT)],
            cwd=str(ROOT),
            env={
                **os.environ,
                "PATH": f"{pkg_bin}:{os.environ['PATH']}",
                "LOG_PATH": str(pkg_log),
                "BUILD_DIR": str(build_dir),
                "PRODUCTS_DIR": str(products_dir),
                "APP_BUNDLE": str(app_bundle),
                "PKG_PATH": str(pkg_path),
                "COMPONENT_PKG_PATH": str(component_pkg),
                "PRODUCTSIGN_IDENTITY": "Developer ID Installer: Example",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        pkg_calls = pkg_log.read_text(encoding="utf-8").splitlines() if pkg_log.is_file() else []
        build_pkg_case = {
            "returncode": completed.returncode,
            "productsign_invoked": any(line.startswith("productsign:") for line in pkg_calls),
            "pkgbuild_uses_root": any(
                line.startswith("pkgbuild:") and "--root" in line and "--component" not in line
                for line in pkg_calls
            ),
            "payload_repack_invoked": any(line.startswith("pkgutil:--expand-full") for line in pkg_calls)
            and any(line.startswith("pkgutil:--flatten") for line in pkg_calls),
            "pkgutil_checked_signature": any(line.startswith("pkgutil:--check-signature") for line in pkg_calls),
            "final_pkg_exists": pkg_path.is_file(),
        }
        cases.append(
            {
                "name": "build_pkg_optionally_signs_pkg_and_checks_signature",
                "actual": build_pkg_case,
                "expected": {
                    "returncode": 0,
                    "productsign_invoked": True,
                    "pkgbuild_uses_root": True,
                    "payload_repack_invoked": True,
                    "pkgutil_checked_signature": True,
                    "final_pkg_exists": True,
                },
                "all_keys_match": build_pkg_case == {
                    "returncode": 0,
                    "productsign_invoked": True,
                    "pkgbuild_uses_root": True,
                    "payload_repack_invoked": True,
                    "pkgutil_checked_signature": True,
                    "final_pkg_exists": True,
                },
            }
        )

        # notarize
        notarize_root = tmpdir / "notarize"
        notarize_app, _, _, _ = _write_minimal_bundles(notarize_root)
        notarize_pkg = notarize_root / "VirtualCamera.pkg"
        notarize_pkg.parent.mkdir(parents=True, exist_ok=True)
        notarize_pkg.write_text("pkg", encoding="utf-8")
        notarize_bin = tmpdir / "notarize-bin"
        notarize_bin.mkdir()
        submit_marker = tmpdir / "submit.log"
        _write_executable(
            notarize_bin / "pkgutil",
            "#!/usr/bin/env bash\n"
            "echo 'Package \"VirtualCamera.pkg\":'\n"
            "echo '   Status: no signature'\n",
        )
        _write_executable(
            notarize_bin / "xcrun",
            "#!/usr/bin/env bash\n"
            "if [ \"$1\" = \"--find\" ] && [ \"$2\" = \"notarytool\" ]; then\n"
            "  echo /usr/bin/notarytool\n"
            "  exit 0\n"
            "fi\n"
            "echo \"$*\" >> \"$MARKER_PATH\"\n",
        )
        completed = subprocess.run(
            ["bash", str(NOTARIZE_SCRIPT)],
            cwd=str(ROOT),
            env={
                **os.environ,
                "PATH": f"{notarize_bin}:{os.environ['PATH']}",
                "PKG_PATH": str(notarize_pkg),
                "NOTARY_PROFILE": "ExampleProfile",
                "NOTARIZE_TARGETS": "pkg",
                "MARKER_PATH": str(submit_marker),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        notarize_case = {
            "returncode": completed.returncode,
            "rejects_unsigned_pkg": "pkg must be signed before notarization" in completed.stderr,
            "notary_submit_skipped": not submit_marker.exists(),
        }
        cases.append(
            {
                "name": "notarize_rejects_unsigned_pkg_before_submit",
                "actual": notarize_case,
                "expected": {
                    "returncode": 2,
                    "rejects_unsigned_pkg": True,
                    "notary_submit_skipped": True,
                },
                "all_keys_match": notarize_case == {
                    "returncode": 2,
                    "rejects_unsigned_pkg": True,
                    "notary_submit_skipped": True,
                },
            }
        )

        notarize_success_log = tmpdir / "notarize-success.log"
        _write_executable(
            notarize_bin / "pkgutil",
            "#!/usr/bin/env bash\n"
            "echo \"pkgutil:$*\" >> \"$LOG_PATH\"\n"
            "echo 'Package \"VirtualCamera.pkg\":'\n"
            "echo '   Status: signed by a developer certificate issued by Apple'\n",
        )
        _write_executable(
            notarize_bin / "xcrun",
            "#!/usr/bin/env bash\n"
            "if [ \"$1\" = \"--find\" ] && [ \"$2\" = \"notarytool\" ]; then\n"
            "  echo /usr/bin/notarytool\n"
            "  exit 0\n"
            "fi\n"
            "echo \"xcrun:$*\" >> \"$LOG_PATH\"\n",
        )
        completed = subprocess.run(
            ["bash", str(NOTARIZE_SCRIPT)],
            cwd=str(ROOT),
            env={
                **os.environ,
                "PATH": f"{notarize_bin}:{os.environ['PATH']}",
                "APP_BUNDLE": str(notarize_app),
                "PKG_PATH": str(notarize_pkg),
                "NOTARY_PROFILE": "ExampleProfile",
                "NOTARIZE_TARGETS": "app,pkg",
                "LOG_PATH": str(notarize_success_log),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        notarize_success_calls = (
            notarize_success_log.read_text(encoding="utf-8").splitlines()
            if notarize_success_log.is_file()
            else []
        )
        notarize_submit_calls = [
            line for line in notarize_success_calls if line.startswith("xcrun:notarytool submit ")
        ]
        notarize_success_case = {
            "returncode": completed.returncode,
            "submitted_app_archive": any(".app.zip --keychain-profile ExampleProfile --wait" in line for line in notarize_submit_calls),
            "submitted_pkg": any(str(notarize_pkg) in line for line in notarize_submit_calls),
            "submit_count": len(notarize_submit_calls),
        }
        cases.append(
            {
                "name": "notarize_submits_app_archive_and_pkg",
                "actual": notarize_success_case,
                "expected": {
                    "returncode": 0,
                    "submitted_app_archive": True,
                    "submitted_pkg": True,
                    "submit_count": 2,
                },
                "all_keys_match": notarize_success_case == {
                    "returncode": 0,
                    "submitted_app_archive": True,
                    "submitted_pkg": True,
                    "submit_count": 2,
                },
            }
        )

        # staple
        staple_root = tmpdir / "staple"
        staple_app, _, _, _ = _write_minimal_bundles(staple_root)
        staple_pkg = staple_root / "VirtualCamera.pkg"
        staple_pkg.parent.mkdir(parents=True, exist_ok=True)
        staple_pkg.write_text("pkg", encoding="utf-8")
        staple_bin = tmpdir / "staple-bin"
        staple_bin.mkdir()
        staple_log = tmpdir / "staple-calls.log"
        _write_executable(
            staple_bin / "pkgutil",
            "#!/usr/bin/env bash\n"
            "echo \"pkgutil:$*\" >> \"$LOG_PATH\"\n",
        )
        _write_executable(
            staple_bin / "xcrun",
            "#!/usr/bin/env bash\n"
            "echo \"xcrun:$*\" >> \"$LOG_PATH\"\n",
        )
        _write_executable(
            staple_bin / "spctl",
            "#!/usr/bin/env bash\n"
            "echo \"spctl:$*\" >> \"$LOG_PATH\"\n",
        )
        completed = subprocess.run(
            ["bash", str(STAPLE_SCRIPT)],
            cwd=str(ROOT),
            env={
                **os.environ,
                "PATH": f"{staple_bin}:{os.environ['PATH']}",
                "APP_BUNDLE": str(staple_app),
                "PKG_PATH": str(staple_pkg),
                "LOG_PATH": str(staple_log),
                "STAPLE_TARGETS": "app,pkg",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        staple_calls = staple_log.read_text(encoding="utf-8").splitlines() if staple_log.is_file() else []
        staple_case = {
            "returncode": completed.returncode,
            "stapler_staple_app_invoked": any("xcrun:stapler staple" in line and str(staple_app) in line for line in staple_calls),
            "stapler_validate_app_invoked": any("xcrun:stapler validate" in line and str(staple_app) in line for line in staple_calls),
            "spctl_app_assessment_invoked": any(line.startswith("spctl:-a -vvv") and str(staple_app) in line for line in staple_calls),
            "pkgutil_checked_signature": any(line.startswith("pkgutil:--check-signature") for line in staple_calls),
            "stapler_staple_invoked": any("xcrun:stapler staple" in line and str(staple_pkg) in line for line in staple_calls),
            "stapler_validate_invoked": any("xcrun:stapler validate" in line and str(staple_pkg) in line for line in staple_calls),
            "spctl_install_assessment_invoked": any(line.startswith("spctl:-a -vvv -t install") for line in staple_calls),
        }
        cases.append(
            {
                "name": "staple_runs_signature_check_stapler_and_spctl",
                "actual": staple_case,
                "expected": {
                    "returncode": 0,
                    "stapler_staple_app_invoked": True,
                    "stapler_validate_app_invoked": True,
                    "spctl_app_assessment_invoked": True,
                    "pkgutil_checked_signature": True,
                    "stapler_staple_invoked": True,
                    "stapler_validate_invoked": True,
                    "spctl_install_assessment_invoked": True,
                },
                "all_keys_match": staple_case == {
                    "returncode": 0,
                    "stapler_staple_app_invoked": True,
                    "stapler_validate_app_invoked": True,
                    "spctl_app_assessment_invoked": True,
                    "pkgutil_checked_signature": True,
                    "stapler_staple_invoked": True,
                    "stapler_validate_invoked": True,
                    "spctl_install_assessment_invoked": True,
                },
            }
        )

    return cases


def evaluate_release_signing_surface_case() -> dict[str, Any]:
    release_module = _load_module(
        RELEASE_DIAGNOSTICS_TOOL,
        "macos_signing_pipeline_contract_release",
    )
    report_module = _load_module(
        VALIDATION_REPORT_TOOL,
        "macos_signing_pipeline_contract_report",
    )
    summary = report_module._build_summary(
        state="installed",
        enabled=True,
        approval_required=False,
        enumerated_devices=["AK Virtual Camera"],
        readiness_payload={},
        verification_targets=[],
        benchmark_payload=None,
        demo_payload=None,
        preflight_payload={},
        release_diagnostics_payload={
            "summary": {
                "app_signed": True,
                "app_gatekeeper_accepted": True,
                "app_stapled": True,
                "extension_signed": True,
                "command_tools_signed": True,
                "pkg_signed": False,
                "pkg_gatekeeper_accepted": False,
                "pkg_stapled": False,
                "host_bundle_identifier_expected": True,
                "extension_bundle_identifier_expected": True,
                "minimum_system_version_expected": True,
            }
        },
        runtime_assets_payload={},
        install_session_payload={},
        smoke_payload={},
        framebus_roundtrip_payload={},
        status_binary_check_payload={},
        status_payload={},
        install_payload={},
    )
    return {
        "release_tool_has_pkg_signed_parser": callable(getattr(release_module, "_pkg_signed", None)),
        "validation_report_uses_build_summary": callable(getattr(report_module, "_build_summary", None)),
        "validation_report_surfaces_release_app_signed": summary.get("release_app_signed") is True,
        "validation_report_surfaces_release_app_gatekeeper_accepted": summary.get("release_app_gatekeeper_accepted") is True,
        "validation_report_surfaces_release_app_stapled": summary.get("release_app_stapled") is True,
        "validation_report_surfaces_release_extension_signed": summary.get("release_extension_signed") is True,
        "validation_report_surfaces_release_command_tools_signed": summary.get("release_command_tools_signed") is True,
        "validation_report_surfaces_release_pkg_signed": summary.get("release_pkg_signed") is False,
        "validation_report_surfaces_release_pkg_gatekeeper_accepted": summary.get("release_pkg_gatekeeper_accepted") is False,
        "validation_report_surfaces_release_pkg_stapled": summary.get("release_pkg_stapled") is False,
        "validation_report_surfaces_bundle_id_expected": summary.get("release_host_bundle_identifier_expected") is True,
        "validation_report_surfaces_minimum_system_version_expected": summary.get("release_minimum_system_version_expected") is True,
    }


def evaluate_contract() -> dict[str, Any]:
    surface = parse_signing_pipeline_surface(
        {
            "sign_app": _load_text(SIGN_APP_SCRIPT),
            "build_pkg": _load_text(BUILD_PKG_SCRIPT),
            "notarize": _load_text(NOTARIZE_SCRIPT),
            "staple": _load_text(STAPLE_SCRIPT),
            "release_diagnostics": _load_text(RELEASE_DIAGNOSTICS_TOOL),
            "validation_report": _load_text(VALIDATION_REPORT_TOOL),
        }
    )
    script_cases = evaluate_script_cases()
    release_surface_case = evaluate_release_signing_surface_case()
    consistency = {
        "surface_complete": all(bool(value) for value in surface.values()),
        "script_cases_match_expected": all(
            bool(item["all_keys_match"]) for item in script_cases
        ),
        "release_surface_case_complete": all(
            bool(value) for value in release_surface_case.values()
        ),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())
    return {
        "surface": surface,
        "script_cases": script_cases,
        "release_surface_case": release_surface_case,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AKVC macOS signing pipeline contract checker"
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_contract()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    if not bool(payload["consistency"]["all_checks_passed"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
