#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the AK Virtual Camera desktop app with Nuitka (macOS).

Produces a standalone .app bundle that includes:
  - the PySide6 desktop app (akvc_app)
  - the C++ akvc_camera pybind binding (akvc_camera.so)
  - the camera extension (.systemextension) embedded under
    Contents/Library/SystemExtensions/ (if built via xcodebuild)

Run on macOS:
    python tools/package_nuitka.py

Prerequisites:
  - Python 3.11+ with the desktop app installed (pip install -e apps/desktop)
  - nuitka: pip install nuitka
  - Xcode + Command Line Tools (for the C++ binding + camera extension)
  - CMake

NOTE: this script is authored on Windows and is best-effort for macOS. If
Nuitka or the linker reports missing modules/symbols, adjust the --include-*
flags or the akvc_camera_macos source list in camera-core/CMakeLists.txt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build-macos"
DIST_DIR = ROOT / "dist"
APP_NAME = "AK Virtual Camera"
APP_VERSION = "0.2.0"
BUNDLE_NAME = "AKVirtualCamera.app"
ENTRY = ROOT / "apps" / "desktop" / "main.py"

# Camera extension bundle (built by xcodebuild via `make.py build` macOS).
EXTENSION_BUNDLE_ID = "com.sidus.amaran-desktop.cameraextension"
EXTENSION_GLOB = "com.sidus.amaran-desktop.cameraextension.systemextension"


def _run(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print(f"[package] $ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _binding_so() -> Path:
    """Locate the built akvc_camera pybind module (.so / .cpython-*.so)."""
    # Specific expected locations first (fast path).
    for cand in [
        BUILD_DIR / "bin" / "Release" / "akvc_camera.so",
        BUILD_DIR / "bin" / "akvc_camera.so",
        BUILD_DIR / "lib" / "akvc_camera.so",
    ]:
        if cand.is_file():
            return cand
    # Fall back to a recursive glob: pybind11 may tag the suffix with the Python
    # ABI (e.g. akvc_camera.cpython-311-darwin.so) and/or place it under a
    # per-target subdir depending on the generator.
    if BUILD_DIR.is_dir():
        for cand in BUILD_DIR.rglob("akvc_camera*.so"):
            return cand
    return Path()


def _binding_inputs() -> list[Path]:
    return [
        ROOT / "camera-core" / "CMakeLists.txt",
        ROOT / "camera-core" / "bindings" / "python" / "module.cpp",
        ROOT / "camera-core" / "src" / "platform" / "macos" / "macos_session.mm",
        ROOT / "virtualcam" / "macos" / "direct_sender" / "AKVCDirectCameraSender.mm",
    ]


def _binding_is_stale(so: Path) -> bool:
    if not so.is_file():
        return True
    so_mtime = so.stat().st_mtime
    return any(src.is_file() and src.stat().st_mtime > so_mtime for src in _binding_inputs())


def ensure_binding_built() -> Path:
    """Configure + build the akvc_camera_python target if the .so is missing."""
    so = _binding_so()
    if so.is_file() and not _binding_is_stale(so):
        print(f"[package] akvc_camera binding found: {so}")
        return so
    if so.is_file():
        print(f"[package] rebuilding stale akvc_camera binding: {so}")
    else:
        print("[package] building C++ akvc_camera binding (cmake)...")
    rc = _run(["cmake", "-S", str(ROOT), "-B", str(BUILD_DIR),
               "-DCMAKE_BUILD_TYPE=Release"])
    if rc != 0:
        sys.exit("[package] cmake configure failed")
    rc = _run(["cmake", "--build", str(BUILD_DIR),
               "--target", "akvc_camera_python", "-j"])
    if rc != 0:
        sys.exit("[package] cmake build akvc_camera_python failed")
    so = _binding_so()
    if not so.is_file():
        # Diagnostic: list any .so/.dylib files actually produced, so the user
        # can see where the binding landed (or if it didn't).
        produced = []
        if BUILD_DIR.is_dir():
            produced = [p for pat in ("*.so", "*.dylib") for p in BUILD_DIR.rglob(pat)]
        hint = "\n  ".join(str(p.relative_to(ROOT)) for p in produced[:15]) or "(none)"
        sys.exit(
            f"[package] akvc_camera.so not found under {BUILD_DIR} after build.\n"
            f"  .so/.dylib files present:\n  {hint}\n"
            f"  If the binding has a different name/path, adjust _binding_so() "
            f"in tools/package_nuitka.py (BUILD_DIR.rglob already searches "
            f"'akvc_camera*.so')."
        )
    print(f"[package] akvc_camera binding built: {so}")
    return so


def find_extension() -> Path | None:
    """Locate the built .systemextension (if xcodebuild produced it)."""
    for base in [BUILD_DIR / "macos" / "Build" / "Products" / "Release",
                 ROOT / "build" / "macos" / "Build" / "Products" / "Release"]:
        ext = base / EXTENSION_GLOB
        if ext.is_dir():
            return ext
    return None


def _can_import(python: str, module: str) -> bool:
    """Return True if `python -c 'import module'` succeeds."""
    return subprocess.call([python, "-c", f"import {module}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def _select_nuitka_python() -> str:
    """Pick a Python that has both nuitka and PySide6 importable.

    Prefers the project .venv (where the user typically installs PySide6 +
    nuitka), falling back to sys.executable. Nuitka's pyside6 plugin locates
    PySide6 via the Python running Nuitka, so they must be in the same env."""
    candidates = []
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        candidates.append(str(venv_python))
    candidates.append(sys.executable)
    for py in candidates:
        if _can_import(py, "nuitka") and _can_import(py, "PySide6"):
            print(f"[package] using python for nuitka: {py}")
            return py
    sys.exit(
        "[package] no python found with both nuitka AND PySide6 importable.\n"
        "  Activate the project venv and install them:\n"
        "    source .venv/bin/activate\n"
        "    pip install nuitka PySide6\n"
        "  then re-run: python tools/package_nuitka.py"
    )


def run_nuitka(binding_so: Path) -> int:
    """Run Nuitka to produce the .app bundle."""
    nuitka_python = _select_nuitka_python()

    # Put the binding's dir on PYTHONPATH so Nuitka can import akvc_camera at
    # compile time (--include-module requires it to be importable).
    env = os.environ.copy()
    binding_dir = str(binding_so.parent)
    env["PYTHONPATH"] = binding_dir + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        nuitka_python, "-m", "nuitka",
        "--standalone",
        "--macos-create-app-bundle",
        f"--macos-app-name={BUNDLE_NAME.removesuffix('.app')}",
        f"--macos-app-version={APP_VERSION}",
        "--enable-plugin=pyside6",
        "--include-package=akvc_app",
        "--include-module=akvc_camera",        # the C++ pybind binding (.so)
        "--include-package-data=akvc_app",
        "--nofollow-import-to=akvc_app.tests",
        f"--output-dir={DIST_DIR}",
        str(ENTRY),
    ]
    return _run(cmd, env=env)


def clean_previous_app_bundles() -> None:
    """Remove stale app bundles so this run cannot sign/package old output."""
    for app in (DIST_DIR / BUNDLE_NAME, DIST_DIR / f"{ENTRY.stem}.app"):
        if app.exists():
            shutil.rmtree(app)
            print(f"[package] removed stale app bundle: {app}")


def patch_info_plist(app: Path) -> None:
    """Add NSCameraUsageDescription to the bundle's Info.plist.

    The DirectSender uses AVCaptureDeviceDiscoverySession to find the camera
    device; macOS requires an NSCameraUsageDescription string or the camera
    list comes back empty (DirectSender.start fails with 'camera device not
    found'). Nuitka's generated Info.plist does not include it."""
    import plistlib
    plist_path = app / "Contents" / "Info.plist"
    if not plist_path.is_file():
        print("[package] Info.plist not found - skip NSCameraUsageDescription patch")
        return
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)
    data.setdefault("NSPrincipalClass", "NSApplication")
    data.setdefault("NSCameraUsageDescription",
                    "AK Virtual Camera needs camera access to stream frames.")
    data.setdefault("NSCameraUseContinuityCameraDeviceType", True)
    # Also declare the system-extension install intent (informational).
    data.setdefault("NSSystemExtensionUsageDescription",
                    "AK Virtual Camera installs a camera extension.")
    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)
    print("[package] patched Info.plist: NSCameraUsageDescription")


def embed_extension(app: Path) -> None:
    """Embed the .systemextension into the .app bundle."""
    ext = find_extension()
    if ext is None:
        print("[package] camera extension not built - skip embedding. "
              "Build it via `python tools/make.py build` (macOS) first if you "
              "need VC-M-1 (extension activation).")
        return
    dest_dir = app / "Contents" / "Library" / "SystemExtensions"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / ext.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ext, dest)
    print(f"[package] embedded camera extension: {dest}")


def sign_bundle(app: Path) -> None:
    """Sign the app + embedded extension so the system accepts the
    OSSystemExtensionRequest. Debug = ad-hoc ('-'); set AKVC_SIGN_IDENTITY
    (e.g. 'Developer ID Application: ...') for a real identity.

    Order: sign the host app deep first (covers PySide6/Python nested
    binaries with Hardened Runtime + host entitlements), then re-sign the
    embedded extension with its own (camera-extension sandbox) entitlements.
    Re-sign the host shallow at the end so the outer app seal records the
    final extension signature without overwriting extension entitlements."""
    identity = os.environ.get("AKVC_SIGN_IDENTITY", "-")
    ext_ent = ROOT / "virtualcam" / "macos" / "camera_extension" / "CameraExtension.entitlements"
    host_ent = ROOT / "tools" / "nuitka_host.entitlements"
    ext_dir = app / "Contents" / "Library" / "SystemExtensions"

    print(f"[package] signing bundle (identity={identity})...")
    host_cmd = ["codesign", "--force", "--options", "runtime", "--deep",
                "--timestamp=none", "-s", identity]
    if host_ent.is_file():
        host_cmd += ["--entitlements", str(host_ent)]
    host_cmd += [str(app)]
    rc = _run(host_cmd)
    if rc != 0:
        print(f"[package] warning: codesign host app rc={rc} (the app may still "
              "run in developer mode)", file=sys.stderr)

    for ext in ext_dir.glob("*.systemextension"):
        ext_cmd = ["codesign", "--force", "--options", "runtime", "--timestamp=none",
                   "-s", identity]
        if ext_ent.is_file():
            ext_cmd += ["--entitlements", str(ext_ent)]
        ext_cmd += [str(ext)]
        rc = _run(ext_cmd)
        if rc != 0:
            print(f"[package] warning: codesign extension rc={rc}", file=sys.stderr)

    seal_cmd = ["codesign", "--force", "--options", "runtime",
                "--timestamp=none", "-s", identity]
    if host_ent.is_file():
        seal_cmd += ["--entitlements", str(host_ent)]
    seal_cmd += [str(app)]
    rc = _run(seal_cmd)
    if rc != 0:
        print(f"[package] warning: codesign host seal rc={rc}", file=sys.stderr)

    rc = _run(["codesign", "--verify", "--verbose=2", str(app)])
    if rc != 0:
        sys.exit("[package] codesign verify failed")


def main() -> int:
    if sys.platform != "darwin":
        print(f"[package] this script is macOS-only (sys.platform={sys.platform})", file=sys.stderr)
        return 1

    binding_so = ensure_binding_built()
    clean_previous_app_bundles()
    rc = run_nuitka(binding_so)
    if rc != 0:
        return rc

    # Nuitka may name the bundle after the entry script (main.py -> main.app)
    # when --macos-app-name doesn't take effect for a given version; rename to
    # the canonical bundle name so embed_extension() finds it.
    app = DIST_DIR / BUNDLE_NAME
    if not app.is_dir():
        apps = sorted(DIST_DIR.glob("*.app")) if DIST_DIR.is_dir() else []
        if len(apps) == 1:
            if app.exists():
                shutil.rmtree(app)
            apps[0].rename(app)
            print(f"[package] renamed {apps[0].name} -> {BUNDLE_NAME}")
        else:
            sys.exit(f"[package] expected {BUNDLE_NAME} not found in {DIST_DIR}; "
                     f"found: {[a.name for a in apps]}")
    embed_extension(app)
    patch_info_plist(app)
    sign_bundle(app)
    print(f"[package] done: {app}")
    print("[package] open it, or for VC-M-1 first run: "
          "systemextensionsctl developer on  (debug) + approve the extension prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
