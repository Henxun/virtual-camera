# SPDX-License-Identifier: Apache-2.0
"""tools/make.py — single build entry point.

Subcommands:
  configure    — fetch BaseClasses, build strmbase.lib, generate CMake
  build        — build native + (optional) Python install
  register     — regsvr32 the built DLL
  unregister   — remove DLL registration
  run          — start the desktop app
  test         — pytest
  clean        — remove build/ and venv

Designed to run on Windows with VS 2022 + Python 3.11–3.12. On other platforms it
prints a friendly error.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
THIRD = ROOT / "third_party"
BASECLASSES = THIRD / "baseclasses"
BASECLASSES_BUILD = BASECLASSES / "build"
STRMBASE_LIB = BASECLASSES_BUILD / "Release" / "strmbase.lib"
DSHOW_DLL = BUILD / "bin" / "Release" / "akvc-dshow.dll"
PACKAGE_RUNTIME = BUILD / "package-runtime"

# CMake generator. If the AKVC_CMAKE_GENERATOR env var is set, it wins;
# otherwise we auto-detect via vswhere (covers VS 2017 / 2019 / 2022 / 2026
# installed at default OR custom paths).
CMAKE_PLATFORM = os.environ.get("AKVC_CMAKE_PLATFORM", "x64")


_VS_MAJOR_TO_GENERATOR = {
    "15": "Visual Studio 15 2017",
    "16": "Visual Studio 16 2019",
    "17": "Visual Studio 17 2022",
    "18": "Visual Studio 18 2026",
}


def _vswhere_path() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _vs_install_path() -> Path | None:
    vsw = _vswhere_path()
    if vsw is None:
        return None
    try:
        out = subprocess.check_output(
            [str(vsw), "-latest", "-prerelease", "-products", "*",
             "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
             "-property", "installationPath"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return Path(out) if out else None
    except subprocess.CalledProcessError:
        return None


def _load_vcvars_env(arch: str = "x64") -> dict[str, str] | None:
    """Run vcvarsall.bat and capture the resulting environment.

    Returns a dict suitable for passing to subprocess as `env=...`. Returns
    None if VS or vcvarsall.bat cannot be found.
    """
    install = _vs_install_path()
    if install is None:
        print("[make] vcvars: vswhere did not return a VS install path")
        return None
    vcvarsall = install / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvarsall.is_file():
        print(f"[make] vcvars: not found at {vcvarsall}")
        return None

    # Write a tiny launcher .bat to avoid quoting hell with cmd /c on paths
    # that contain spaces. The launcher calls vcvarsall and then `set` to
    # emit the post-vcvars environment.
    import tempfile
    with tempfile.NamedTemporaryFile(
        "w", suffix=".bat", delete=False, encoding="ascii"
    ) as f:
        f.write("@echo off\r\n")
        f.write(f'call "{vcvarsall}" {arch} >nul\r\n')
        f.write("if errorlevel 1 exit /b 1\r\n")
        f.write("set\r\n")
        launcher = Path(f.name)

    try:
        # Use bytes mode + manual decode to tolerate non-ASCII output.
        proc = subprocess.run(
            ["cmd", "/c", str(launcher)],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            print(f"[make] vcvars: launcher returned {proc.returncode}: {err.strip()}")
            return None
        # Try utf-8 first, then mbcs (Windows ANSI) as fallback for cn locale.
        raw_bytes: bytes = proc.stdout
        for enc in ("utf-8", "mbcs", "latin-1"):
            try:
                raw = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return None
    finally:
        try:
            launcher.unlink()
        except OSError:
            pass

    env: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    if "PATH" not in env:
        print("[make] vcvars: launcher produced no PATH; environment looks invalid")
        return None
    return env


def _cmake_supports_generator(name: str) -> bool:
    # Prefer the JSON capabilities output (CMake 3.7+).
    try:
        out = subprocess.check_output(
            ["cmake", "-E", "capabilities"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        import json
        data = json.loads(out)
        for g in data.get("generators", []):
            if g.get("name") == name:
                return True
        # Some VS generators are listed only by their family name in newer CMake.
        return False
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        pass
    # Fallback: scan `cmake --help`.
    try:
        out = subprocess.check_output(["cmake", "--help"], text=True,
                                      stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    for line in out.splitlines():
        if line.lstrip().startswith(name):
            return True
    return False


def _detect_cmake_generator() -> str:
    override = os.environ.get("AKVC_CMAKE_GENERATOR")
    if override:
        return override

    vsw = _vswhere_path()
    if vsw is None:
        print("[make] vswhere.exe not found; falling back to 'Visual Studio 17 2022'.")
        return "Visual Studio 17 2022"

    try:
        out = subprocess.check_output(
            [
                str(vsw),
                "-latest",
                "-prerelease",
                "-products", "*",
                "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property", "installationVersion",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        out = ""

    if not out:
        print(
            "[make] vswhere returned no VS instance with C++ build tools.\n"
            "       Install the 'Desktop development with C++' workload, then retry.",
            file=sys.stderr,
        )
        sys.exit(2)

    major = out.split(".", 1)[0]
    preferred = _VS_MAJOR_TO_GENERATOR.get(major)
    if preferred is None:
        print(
            f"[make] detected VS installationVersion={out} (major={major}); "
            f"unknown generator. Set AKVC_CMAKE_GENERATOR explicitly.",
            file=sys.stderr,
        )
        sys.exit(2)

    if _cmake_supports_generator(preferred):
        print(f"[make] detected VS major={major} → generator '{preferred}'")
        return preferred

    # CMake too old for this VS version. Fall back to Ninja Multi-Config; we
    # will load vcvars ourselves so cl.exe is reachable.
    if _cmake_supports_generator("Ninja Multi-Config"):
        print(
            f"[make] CMake doesn't know '{preferred}' (CMake too old for VS {major}).\n"
            f"       Falling back to 'Ninja Multi-Config' (vcvars will be loaded automatically).\n"
            f"       Tip: upgrade CMake to >= 3.31 for native VS {major} support.",
        )
        return "Ninja Multi-Config"

    print(
        f"[make] CMake supports neither '{preferred}' nor Ninja.\n"
        f"       Upgrade CMake (`winget upgrade Kitware.CMake`) and retry.",
        file=sys.stderr,
    )
    sys.exit(2)


CMAKE_GENERATOR = _detect_cmake_generator() if sys.platform == "win32" else ""
_NEEDS_VCVARS = sys.platform == "win32" and "Ninja" in CMAKE_GENERATOR

# Cache loaded vcvars env (None if not needed / not Windows).
_VCVARS_ENV: dict[str, str] | None = None
if _NEEDS_VCVARS:
    print("[make] loading vcvars (x64) ...")
    _VCVARS_ENV = _load_vcvars_env("x64")
    if _VCVARS_ENV is None:
        print("[make] failed to load vcvars; aborting.", file=sys.stderr)
        sys.exit(2)

# ---- macOS (Phase 4) paths ----
MACOS_ROOT = ROOT / "virtualcam" / "macos"
MACOS_BUILD = BUILD / "macos"
MACOS_PROJECT_YML = MACOS_ROOT / "project.yml"
# The Camera Extension system-extension bundle (built by xcodebuild).
MACOS_EXT_BUNDLE = MACOS_BUILD / "Build" / "Products" / "Release" / "com.sidus.amaran-desktop.cameraextension.systemextension"
# Legacy fallback only. Real container-app selection should go through
# `_detect_macos_release_app_bundle()` so the main app can replace akvc-host.
MACOS_LEGACY_HOST_APP_BUNDLE = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-host.app"
MACOS_STATUS_TOOL = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-macos-status"
MACOS_INSTALL_TOOL = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-macos-install"
MACOS_UNINSTALL_TOOL = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-macos-uninstall"
MACOS_LIST_DEVICES_TOOL = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-macos-list-devices"
MACOS_SYNC_IPC_TOOL = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-macos-sync-ipc"
MACOS_DIRECT_SENDER_LIB = MACOS_BUILD / "Build" / "Products" / "Release" / "libakvc-macos-direct-sender.dylib"
MACOS_PKG = MACOS_BUILD / "VirtualCamera.pkg"
MACOS_RUNTIME_DIR = ROOT / "camera-core" / "src" / "akvc" / "_runtime" / "macos"
MACOS_DMG = MACOS_BUILD / "VirtualCamera.dmg"
MACOS_ZIP = MACOS_BUILD / "VirtualCamera.zip"
MACOS_DEPLOYMENT_TARGET = os.environ.get("MACOS_DEPLOYMENT_TARGET", "13.0")
MACOS_BUILD_ARCHS = os.environ.get("MACOS_ARCHS", "arm64 x86_64")
MACOS_INSTALLER_DIR = ROOT / "installer" / "macos"
MACOS_BUILD_PKG_SCRIPT = MACOS_INSTALLER_DIR / "build_pkg.sh"
MACOS_BUILD_DMG_SCRIPT = MACOS_INSTALLER_DIR / "build_dmg.sh"
MACOS_BUILD_ZIP_SCRIPT = MACOS_INSTALLER_DIR / "build_zip.sh"
MACOS_SIGN_SCRIPT = MACOS_INSTALLER_DIR / "sign_app.sh"
MACOS_NOTARIZE_SCRIPT = MACOS_INSTALLER_DIR / "notarize.sh"
MACOS_STAPLE_SCRIPT = MACOS_INSTALLER_DIR / "staple.sh"
MACOS_UNINSTALL_SCRIPT = MACOS_INSTALLER_DIR / "uninstall.sh"
MACOS_SMOKE_SCRIPT = ROOT / "tools" / "macos_smoke.py"
MACOS_DIRECT_PUSH_DEMO_SCRIPT = ROOT / "tools" / "macos_direct_push_demo.py"
MACOS_DIRECT_SENDER_OBJECT_DEMO_SCRIPT = ROOT / "tools" / "macos_direct_sender_object_demo.py"
MACOS_NATIVE_VERIFY_SCRIPT = ROOT / "tools" / "macos_native_verify.py"
MACOS_TOOLCHAIN_PREFLIGHT_SCRIPT = ROOT / "tools" / "macos_toolchain_preflight.py"
MACOS_RELEASE_DIAGNOSTICS_SCRIPT = ROOT / "tools" / "macos_release_diagnostics.py"
MACOS_BENCHMARK_SCRIPT = ROOT / "tools" / "macos_benchmark.py"
MACOS_FRAMEBUS_ROUNDTRIP_SCRIPT = ROOT / "tools" / "macos_framebus_roundtrip.py"
MACOS_LIST_DEVICES_BINARY_CHECK_SCRIPT = ROOT / "tools" / "macos_list_devices_binary_check.py"
MACOS_VALIDATION_REPORT_SCRIPT = ROOT / "tools" / "macos_validation_report.py"
MACOS_VALIDATION_SESSION_SCRIPT = ROOT / "tools" / "macos_validation_session.py"
MACOS_VALIDATION_SESSION_ARTIFACT_CHECK_SCRIPT = ROOT / "tools" / "macos_validation_session_artifact_check.py"
MACOS_VALIDATION_SESSION_ACCEPTANCE_SCRIPT = ROOT / "tools" / "macos_validation_session_acceptance.py"
MACOS_VALIDATION_SESSION_ACCEPTANCE_CONTRACT_SCRIPT = ROOT / "tools" / "macos_validation_session_acceptance_contract.py"
MACOS_VALIDATION_SESSION_SUMMARY_SCRIPT = ROOT / "tools" / "macos_validation_session_summary.py"
MACOS_INSTALL_SESSION_SCRIPT = ROOT / "tools" / "macos_install_session.py"
MACOS_HEADLESS_DMG_TOKENS = (
    "device not configured",
    "设备未配置",
)
BUILD_PYTHON_STAMP = BUILD / ".python-executable"


def _resolved_python_identity() -> Path:
    base = getattr(sys, "_base_executable", None)
    candidate = Path(base) if base else Path(sys.executable)
    return candidate.resolve()


def _cmake_args(source: Path, build: Path) -> list[str]:
    args = ["cmake", "-G", CMAKE_GENERATOR]
    # The -A option is only valid for Visual Studio generators.
    if CMAKE_GENERATOR.startswith("Visual Studio"):
        args += ["-A", CMAKE_PLATFORM]
    args += [
        "-S", str(source), "-B", str(build),
        f"-DPython3_EXECUTABLE={sys.executable}",
    ]
    return args


def _build_env() -> dict[str, str] | None:
    return _VCVARS_ENV


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> int:
    print(f"[make] $ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(cwd) if cwd else None, env=env)


def _run_macos_script_result(
    script: Path,
    *,
    env: dict[str, str] | None = None,
    args: list[str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    _check_macos()
    if not script.is_file():
        raise FileNotFoundError(script)
    merged_env = _macos_script_env()
    if env:
        merged_env.update(env)
    cmd = ["bash", str(script)]
    if args:
        cmd.extend(args)
    print(f"[make] $ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=merged_env,
        capture_output=capture_output,
        text=True,
        check=False,
    )


def _force_rmtree(path: Path) -> None:
    """rmtree that also clears the read-only bit (git pack/.idx on Windows).

    Without this, deleting a fresh `git clone` directory on Windows raises
    PermissionError on `.git/objects/pack/*.idx`, which the default rmtree
    cannot recover from.
    """
    if not path.exists():
        return

    import stat

    def _on_error(func, target, exc_info):
        try:
            os.chmod(target, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(target)
        except OSError:
            # Last resort: try one more time after a short pause; on Windows
            # the indexer can briefly hold a handle.
            import time
            time.sleep(0.1)
            try:
                func(target)
            except OSError:
                raise

    # Python 3.12 prefers `onexc`, older versions use `onerror`.
    try:
        shutil.rmtree(path, onexc=lambda func, p, exc: _on_error(func, p, exc))
    except TypeError:
        shutil.rmtree(path, onerror=lambda func, p, exc: _on_error(func, p, exc))


def _purge_stale_cmake_cache(build_dir: Path) -> None:
    """If a previous configure used a different generator, wipe the cache.

    We detect by reading CMAKE_GENERATOR:INTERNAL out of CMakeCache.txt.
    """
    cache = build_dir / "CMakeCache.txt"
    stamp = BUILD_PYTHON_STAMP
    current_python = str(_resolved_python_identity())
    if cache.exists() and not stamp.exists():
        print(f"[make] purging stale build cache (missing Python stamp): {build_dir}")
        shutil.rmtree(build_dir, ignore_errors=True)
        return
    if stamp.exists():
        stamped_python = stamp.read_text(encoding="utf-8", errors="ignore").strip()
        if stamped_python and Path(stamped_python) != Path(current_python):
            print(
                f"[make] purging stale build cache "
                f"(Python was '{stamped_python}', now '{current_python}'): {build_dir}"
            )
            shutil.rmtree(build_dir, ignore_errors=True)
            return
    if not cache.exists():
        return
    try:
        generator = None
        python_executable = None
        for line in cache.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("CMAKE_GENERATOR:INTERNAL="):
                generator = line.split("=", 1)[1].strip()
            elif line.startswith("Python3_EXECUTABLE:FILEPATH="):
                python_executable = line.split("=", 1)[1].strip()
        if generator and generator != CMAKE_GENERATOR:
            print(
                f"[make] purging stale CMake cache "
                f"(was '{generator}', now '{CMAKE_GENERATOR}'): {build_dir}"
            )
            shutil.rmtree(build_dir, ignore_errors=True)
            return
        if python_executable and Path(python_executable) != Path(current_python):
            print(
                f"[make] purging stale CMake cache "
                f"(Python was '{python_executable}', now '{current_python}'): {build_dir}"
            )
            shutil.rmtree(build_dir, ignore_errors=True)
            return
    except Exception:
        # If anything goes wrong reading, err on the side of purging.
        shutil.rmtree(build_dir, ignore_errors=True)


def _check_windows() -> None:
    if sys.platform != "win32":
        print("[make] Phase 2 build is Windows-only.", file=sys.stderr)
        sys.exit(1)


def _ensure_python_build_dependencies() -> int:
    missing: list[str] = []
    if importlib.util.find_spec("pybind11") is None:
        missing.append("pybind11>=2.12")
    if importlib.util.find_spec("numpy") is None:
        missing.append("numpy>=1.26,<3.0")
    if not missing:
        return 0
    return _run([sys.executable, "-m", "pip", "install", *missing])


def _ensure_baseclasses() -> None:
    """Fetch DirectShow BaseClasses sources from Windows-classic-samples.

    Strategy (network-friendly):
      - Keep a pristine, read-only-ish cache at `third_party/_classic-samples/`.
      - The first time we run, do the git clone there.
      - On every subsequent run we copy from the cache to
        `third_party/baseclasses/` and apply our patches.
      - We NEVER re-clone unless the cache is missing or the cached
        baseclasses subdirectory looks broken.

    Idempotent: safe to call repeatedly.
    """
    cache_root = THIRD / "_classic-samples"
    cache_baseclasses = (
        cache_root
        / "Samples" / "Win7Samples" / "multimedia" / "directshow" / "baseclasses"
    )

    # If already present, refresh CMakeLists and reapply patches.
    if BASECLASSES.exists() and (BASECLASSES / "streams.h").exists():
        (BASECLASSES / "CMakeLists.txt").write_text(_BASECLASSES_CMAKE, encoding="utf-8")
        _patch_baseclasses_sources()
        # If patch detected corruption it wipes BASECLASSES; fall through
        # to the refresh path below in that case.
        if BASECLASSES.exists() and (BASECLASSES / "streams.h").exists():
            return

    THIRD.mkdir(exist_ok=True)

    # Repopulate the cache only if we genuinely don't have a usable copy.
    if not (cache_baseclasses / "streams.h").is_file():
        # Clean any half-deleted leftover that previously failed to remove
        # (Windows .git/objects/pack/*.idx read-only files).
        if cache_root.exists():
            print(f"[make] cache at {cache_root} looks incomplete; resetting it.")
            _force_rmtree(cache_root)

        if _run(
            [
                "git", "clone",
                "--depth", "1",
                "--filter=blob:none",
                "--sparse",
                "https://github.com/microsoft/Windows-classic-samples.git",
                str(cache_root),
            ]
        ) != 0:
            sys.exit("[make] failed to clone Windows-classic-samples")
        if _run(
            ["git", "sparse-checkout", "set",
             "Samples/Win7Samples/multimedia/directshow/baseclasses"],
            cwd=cache_root,
        ) != 0:
            sys.exit("[make] sparse checkout failed")

        if not (cache_baseclasses / "streams.h").is_file():
            sys.exit(
                f"[make] expected BaseClasses sources at {cache_baseclasses}, "
                f"but streams.h is missing after clone"
            )
        print(
            f"[make] cached BaseClasses sources at {cache_root}\n"
            "       (kept around so future runs don't re-clone)"
        )
    else:
        print(
            f"[make] reusing cached BaseClasses at {cache_baseclasses} "
            "(no git fetch)"
        )

    # Populate the working copy from the cache.
    if BASECLASSES.exists():
        _force_rmtree(BASECLASSES)
    BASECLASSES.mkdir(parents=True, exist_ok=True)
    for item in cache_baseclasses.iterdir():
        dst = BASECLASSES / item.name
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)

    # Drop a CMakeLists.txt for strmbase, then patch the sources.
    (BASECLASSES / "CMakeLists.txt").write_text(_BASECLASSES_CMAKE, encoding="utf-8")
    _patch_baseclasses_sources()


_BASECLASSES_CMAKE = """\
# SPDX-License-Identifier: MS-PL  (or sample license; see Microsoft documentation)
cmake_minimum_required(VERSION 3.25)
project(strmbase CXX)

set(CMAKE_CXX_STANDARD 17)
add_definitions(
    -D_WIN32_WINNT=0x0A00
    -DWINVER=0x0A00
    -DUNICODE -D_UNICODE
    -D_CRT_SECURE_NO_WARNINGS
    -D_SCL_SECURE_NO_WARNINGS
    -DINITGUID
)

# These BaseClasses sample sources from Microsoft were last touched ~2010 and
# fail to compile under modern MSVC. We:
#   1. Disable strict conformance (`/permissive`) — restores legacy behaviour.
#   2. Suppress C4596 (illegal qualified member name) and other noisy diags
#      that turn into errors with /W4 + new compilers.
#   3. Exclude videoctl.cpp from the static lib because it includes
#      <ddraw.h> with an explicit IDirectDraw destructor override that the
#      new compiler rejects (C3244/C3254). We don't use any DDraw class
#      in our filter.
add_compile_options(
    /permissive
    /FI"${CMAKE_CURRENT_SOURCE_DIR}/patch_guid.h"
    /wd4267 /wd4244 /wd4100 /wd4189 /wd4127 /wd4505 /wd4324
    /wd4456 /wd4457 /wd4458 /wd4459
    /wd4302 /wd4311 /wd4312 /wd4477 /wd4838 /wd4995 /wd4996
    /wd4596 /wd4359
)

file(GLOB BC_SRC CONFIGURE_DEPENDS "*.cpp")
file(GLOB BC_HDR CONFIGURE_DEPENDS "*.h")

# Drop sources that pull in DirectDraw — we don't need them.
list(FILTER BC_SRC EXCLUDE REGEX "videoctl\\\\.cpp$")
list(FILTER BC_SRC EXCLUDE REGEX "ddmm\\\\.cpp$")
list(FILTER BC_SRC EXCLUDE REGEX "vtrans\\\\.cpp$")

add_library(strmbase STATIC ${BC_SRC} ${BC_HDR})
target_include_directories(strmbase PUBLIC .)
set_target_properties(strmbase PROPERTIES
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
"""


_BASECLASSES_PATCHES: list[tuple[str, str, str]] = [
    # (filename, needle, replacement)  — applied once at fetch time.
    # Keep these idempotent: if `needle` is missing we silently skip.
]


def _patch_baseclasses_sources() -> None:
    """Apply small textual patches to BaseClasses headers we cannot avoid.

    We don't *use* videoctl.h ourselves, but `streams.h` includes it
    transitively. We neuter the offending classes inside videoctl.h instead
    of removing the file (BaseClasses headers are interdependent).

    Patch strategy for videoctl.h:
        Wrap the whole DirectDraw block — from `class CAggDirectDraw`
        up to (but not including) `class CLoadDirectDraw` — in `#if 0`.
        CLoadDirectDraw is a non-DirectDraw class that downstream code
        actually compiles, so it must remain visible.
    """
    videoctl = BASECLASSES / "videoctl.h"
    transip = BASECLASSES / "transip.h"

    # 1. videoctl.h
    if videoctl.is_file():
        text = videoctl.read_text(encoding="latin-1")
        marker_begin = "// AKVC: BEGIN guarded DirectDraw classes"

        # First, undo any *prior* (potentially broken) patch by stripping a
        # half-applied marker block. This is what makes the patch idempotent
        # and recoverable across iterations.
        if marker_begin in text and "// AKVC: END" in text:
            # Drop everything between the markers and re-fetch from a clean
            # copy if it looks malformed (e.g. an unbalanced #endif).
            # Easiest signal of corruption: contents after the markers no
            # longer parse as valid C++ at the class-declaration level.
            #
            # Heuristic: if the byte range between BEGIN and END contains a
            # `class CAggDirectDraw` *and* a `class CAggDrawSurface`, but
            # does NOT contain a `class CLoadDirectDraw`, the patch is
            # malformed (truncated mid-class). Refuse to patch on top.
            seg_start = text.index(marker_begin)
            seg_end = text.index("// AKVC: END") + len("// AKVC: END")
            seg = text[seg_start:seg_end]
            if (
                "class CAggDirectDraw" in seg
                and "class CAggDrawSurface" in seg
                and "class CLoadDirectDraw" not in seg
            ):
                # Patch was applied incorrectly in an earlier run.
                # Don't try to fix in place; reset by re-cloning is the safe
                # path. Mark the file as needing reset.
                print(
                    "[make] videoctl.h has a malformed earlier AKVC patch.\n"
                    "       Wiping third_party/baseclasses to force a fresh clone."
                )
                shutil.rmtree(BASECLASSES, ignore_errors=True)
                shutil.rmtree(BASECLASSES_BUILD, ignore_errors=True)
                # ignore_errors above tolerates *.idx read-only files that
                # rmtree alone can't remove. Follow up with the read-only
                # aware variant so any lingering files are taken out.
                _force_rmtree(BASECLASSES)
                _force_rmtree(BASECLASSES_BUILD)
                return  # caller (_ensure_baseclasses) re-runs from scratch
            # Otherwise the patch is well-formed — nothing to do.
            return

        # Fresh patch: wrap [class CAggDirectDraw ... ) up to (class CLoadDirectDraw)
        start = text.find("class CAggDirectDraw")
        end_anchor = text.find("class CLoadDirectDraw")
        if start == -1 or end_anchor == -1:
            print("[make] videoctl.h: could not find DirectDraw block anchors; "
                  "skipping patch (this BaseClasses snapshot may differ).")
            return
        # Walk backwards from end_anchor to the most recent newline so the
        # `#endif` lands on its own line cleanly.
        end_cut = text.rfind("\n", 0, end_anchor) + 1
        patched = (
            text[:start]
            + marker_begin + "\n#if 0\n"
            + text[start:end_cut]
            + "#endif\n// AKVC: END\n\n"
            + text[end_cut:]
        )
        videoctl.write_text(patched, encoding="latin-1")
        print("[make] patched third_party/baseclasses/videoctl.h "
              "(disabled DirectDraw aggregator classes)")

    # 2. transip.h
    if transip.is_file():
        text = transip.read_text(encoding="latin-1")
        bad = "HRESULT IMemInputPin::Copy"
        good = "HRESULT Copy"
        if bad in text and "// AKVC: patched Copy" not in text:
            text = text.replace(bad, good + " /* AKVC: patched Copy */")
            transip.write_text(text, encoding="latin-1")
            print("[make] patched third_party/baseclasses/transip.h "
                  "(removed illegal qualifier on Copy)")

    # 3. patch_guid.h — the Windows 10 SDK (>= 10.0.22621.0) no longer defines
    #    GUID_NULL via DEFINE_GUID in <uuids.h>. The BaseClasses code references
    #    GUID_NULL extensively, so we provide the definition here.
    #    CMakeLists.txt already defines -DINITGUID, so DEFINE_GUID here will
    #    produce an initialized const GUID (not just extern).
    patch_guid = BASECLASSES / "patch_guid.h"
    if not patch_guid.is_file():
        patch_guid.write_text("""\
// patch_guid.h — provide GUID_NULL for Windows SDK >= 10.0.22621.0
// The new SDK dropped DEFINE_GUID(GUID_NULL, ...) from <uuids.h>.
// Force-included via /FI in CMakeLists.txt.
#pragma once
#include <guiddef.h>
DEFINE_GUID(GUID_NULL, 0L, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
""", encoding="utf-8")
        print("[make] created third_party/baseclasses/patch_guid.h "
              "(provides GUID_NULL for modern SDK)")


def _build_baseclasses() -> None:
    global STRMBASE_LIB
    if STRMBASE_LIB.exists():
        return
    BASECLASSES_BUILD.mkdir(parents=True, exist_ok=True)
    _purge_stale_cmake_cache(BASECLASSES_BUILD)
    if _run(_cmake_args(BASECLASSES, BASECLASSES_BUILD), env=_build_env()) != 0:
        sys.exit("[make] BaseClasses configure failed")
    if _run(["cmake", "--build", str(BASECLASSES_BUILD), "--config", "Release"],
            env=_build_env()) != 0:
        sys.exit("[make] BaseClasses build failed")
    if not STRMBASE_LIB.exists():
        # Some generators emit to a different sub-directory; locate it.
        candidates = list(BASECLASSES_BUILD.rglob("strmbase.lib"))
        if not candidates:
            sys.exit("[make] strmbase.lib not found after build")
        STRMBASE_LIB = candidates[0]
        print(f"[make] strmbase.lib located at {STRMBASE_LIB}")


def _ensure_windows_build_configured(args: argparse.Namespace) -> int:
    _check_windows()
    _purge_stale_cmake_cache(BUILD)
    if not (BUILD / "CMakeCache.txt").exists():
        rc = cmd_configure(args)
        if rc != 0:
            return rc
    return 0


def _build_windows_release(args: argparse.Namespace) -> int:
    rc = _ensure_windows_build_configured(args)
    if rc != 0:
        return rc
    return _run(["cmake", "--build", str(BUILD), "--config", "Release"],
                env=_build_env())


def _install_windows_runtime(prefix: Path, args: argparse.Namespace) -> int:
    rc = _build_windows_release(args)
    if rc != 0:
        return rc
    if prefix.exists():
        _force_rmtree(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    return _run([
        "cmake",
        "--install",
        str(BUILD),
        "--config",
        "Release",
        "--prefix",
        str(prefix),
    ], env=_build_env())


def _sync_windows_runtime_into_source_tree(prefix: Path) -> None:
    runtime_bin = prefix / "bin"
    runtime_pkg = ROOT / "akvc" / "_runtime" / "windows"
    runtime_pkg.mkdir(parents=True, exist_ok=True)
    for name in ("akvc_helper.exe", "akvc-dshow.dll", "akvc-mf.dll"):
        shutil.copy2(runtime_bin / name, runtime_pkg / name)

    staged_native = prefix / "akvc"
    source_native = ROOT / "akvc"
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".pyd"
    legacy_named = source_native / f"_core_native{ext_suffix}"
    plain_named = source_native / "_core_native.pyd"

    for artifact in staged_native.glob("_core_native*.pyd"):
        shutil.copy2(artifact, plain_named)
        if legacy_named != plain_named:
            shutil.copy2(artifact, legacy_named)


def cmd_configure(_: argparse.Namespace) -> int:
    _check_windows()
    rc = _ensure_python_build_dependencies()
    if rc != 0:
        return rc
    _ensure_baseclasses()
    _build_baseclasses()
    BUILD.mkdir(exist_ok=True)
    _purge_stale_cmake_cache(BUILD)
    rc = _run(_cmake_args(ROOT, BUILD), env=_build_env())
    if rc == 0:
        BUILD_PYTHON_STAMP.write_text(str(_resolved_python_identity()), encoding="utf-8")
    return rc


def cmd_build(args: argparse.Namespace) -> int:
    rc = _build_windows_release(args)
    if rc != 0:
        return rc
    if args.python:
        rc = _install_windows_runtime(PACKAGE_RUNTIME, args)
        if rc != 0:
            return rc
        _sync_windows_runtime_into_source_tree(PACKAGE_RUNTIME)
        rc = _run([sys.executable, "-m", "pip", "install", "-e",
                   str(ROOT / "camera-core")])
        if rc != 0:
            return rc
        rc = _run([sys.executable, "-m", "pip", "install", "-e",
                   str(ROOT / "apps" / "desktop")])
        if rc != 0:
            return rc
        rc = _run([sys.executable, "-m", "pip", "install", "-e",
                   str(ROOT / "apps" / "cli")])
    return rc


def cmd_register(_: argparse.Namespace) -> int:
    _check_windows()
    if not DSHOW_DLL.exists():
        print(f"[make] DLL not found: {DSHOW_DLL}", file=sys.stderr)
        print("[make] run `python tools/make.py build` first", file=sys.stderr)
        return 1
    return _run(["regsvr32", "/s", str(DSHOW_DLL)])


def cmd_unregister(_: argparse.Namespace) -> int:
    _check_windows()
    cmd = [sys.executable, "-m", "akvc_cli", "unregister"]
    if DSHOW_DLL.exists():
        cmd.extend(["--dll", str(DSHOW_DLL)])
    else:
        print(f"[make] DLL not found at {DSHOW_DLL}, relying on CLI lookup")
    return _run(cmd)


def cmd_run(_: argparse.Namespace) -> int:
    return _run([sys.executable, "-m", "akvc_app"])


def cmd_test(_: argparse.Namespace) -> int:
    return _run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests" / "unit")])


def cmd_install_runtime(args: argparse.Namespace) -> int:
    prefix = Path(args.prefix) if args.prefix else PACKAGE_RUNTIME
    return _install_windows_runtime(prefix, args)


def cmd_clean(_: argparse.Namespace) -> int:
    if BUILD.exists():
        _force_rmtree(BUILD)
    print("[make] cleaned build/")
    return 0


# ============================================================
# ---- macOS (Phase 4) commands ----
# ============================================================
# The macOS build cannot be done with CMake: a CoreMediaIO Camera Extension
# is a System Extension target that only Xcode knows how to sign & package.
# We drive `xcodegen` (declarative project.yml → .xcodeproj) + `xcodebuild`.
# Phase 4 is scaffolded but NOT buildable without a Mac + Xcode + a Developer
# ID; running these commands on macOS will surface the real toolchain errors.

def _check_macos() -> None:
    if sys.platform != "darwin":
        print("[make] macOS build requires macOS (darwin).", file=sys.stderr)
        sys.exit(1)


def _require_tool(name: str) -> str:
    """Return the path to `name` on PATH, or exit with a helpful message."""
    p = shutil.which(name)
    if not p:
        print(
            f"[make] '{name}' not found on PATH.\n"
            f"       On macOS install it with:  brew install {name}\n"
            f"       (Xcode itself is required for xcodebuild.)",
            file=sys.stderr,
        )
        sys.exit(2)
    return p


def _macos_script_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("BUILD_DIR", str(MACOS_BUILD))
    env.setdefault("PRODUCTS_DIR", str(MACOS_BUILD / "Build" / "Products" / "Release"))
    detected_app_bundle = _detect_macos_release_app_bundle()
    if detected_app_bundle is not None:
        env.setdefault("APP_BUNDLE", str(detected_app_bundle))
    env.setdefault("EXT_BUNDLE", str(MACOS_EXT_BUNDLE))
    env.setdefault("DIRECT_SENDER_LIB", str(MACOS_DIRECT_SENDER_LIB))
    env.setdefault("PKG_PATH", str(MACOS_PKG))
    env.setdefault("DMG_PATH", str(MACOS_DMG))
    env.setdefault("ZIP_PATH", str(MACOS_ZIP))
    env.setdefault("UNINSTALL_TOOL", str(MACOS_UNINSTALL_TOOL))
    sign_identity = _effective_macos_sign_identity()
    if sign_identity:
        env.setdefault("SIGN_IDENTITY", sign_identity)
    productsign_identity = _effective_macos_productsign_identity()
    if productsign_identity:
        env.setdefault("PRODUCTSIGN_IDENTITY", productsign_identity)
    return env


def _resolve_macos_container_app_overrides(
    args: argparse.Namespace,
) -> tuple[str | None, str | None]:
    app_bundle = getattr(args, "app_bundle", None)
    app_executable = getattr(args, "app_executable", None)
    host_bundle = getattr(args, "host_bundle", None)
    host_executable = getattr(args, "host_executable", None)
    if app_bundle and host_bundle and str(app_bundle) != str(host_bundle):
        raise ValueError("--app-bundle and --host-bundle cannot point at different macOS app bundles")
    if app_executable and host_executable and str(app_executable) != str(host_executable):
        raise ValueError(
            "--app-executable and --host-executable cannot point at different macOS app executables"
        )
    return (
        str(app_bundle) if app_bundle else (str(host_bundle) if host_bundle else None),
        str(app_executable) if app_executable else (str(host_executable) if host_executable else None),
    )


def _append_macos_container_app_flags(
    cmd: list[str],
    *,
    app_bundle: str | None,
    app_executable: str | None,
) -> None:
    if app_bundle:
        cmd.extend(["--app-bundle", app_bundle])
    if app_executable:
        cmd.extend(["--app-executable", app_executable])


def _macos_release_products_dir() -> Path:
    return MACOS_BUILD / "Build" / "Products" / "Release"


def _macos_app_embeds_extension(bundle_path: Path) -> bool:
    return (
        bundle_path
        / "Contents"
        / "Library"
        / "SystemExtensions"
        / MACOS_EXT_BUNDLE.name
    ).is_dir()


def _is_preferred_macos_container_app(bundle_path: Path) -> bool:
    return bundle_path.name != "akvc-host.app"


def _detect_macos_release_app_bundle() -> Path | None:
    products_dir = _macos_release_products_dir()
    candidates = sorted(path for path in products_dir.glob("*.app") if path.is_dir())
    for candidate in candidates:
        if _is_preferred_macos_container_app(candidate) and _macos_app_embeds_extension(candidate):
            return candidate
    for candidate in candidates:
        if _macos_app_embeds_extension(candidate):
            return candidate
    if MACOS_LEGACY_HOST_APP_BUNDLE.is_dir():
        return MACOS_LEGACY_HOST_APP_BUNDLE
    return None


def _detect_macos_identity(prefix: str, policy: str) -> str | None:
    if sys.platform != "darwin":
        return None
    if not shutil.which("security"):
        return None
    try:
        completed = subprocess.run(
            ["security", "find-identity", "-v", "-p", policy],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if prefix not in line:
            continue
        match = re.search(r'"([^"]+)"', line)
        if match:
            return match.group(1)
    return None


def _effective_macos_sign_identity() -> str | None:
    return os.environ.get("SIGN_IDENTITY") or _detect_macos_identity(
        "Developer ID Application:",
        "codesigning",
    )


def _effective_macos_productsign_identity() -> str | None:
    return os.environ.get("PRODUCTSIGN_IDENTITY") or _detect_macos_identity(
        "Developer ID Installer:",
        "basic",
    )


def _run_macos_script(script: Path, *, env: dict[str, str] | None = None, args: list[str] | None = None) -> int:
    try:
        completed = _run_macos_script_result(script, env=env, args=args, capture_output=False)
    except FileNotFoundError:
        print(f"[make] missing macOS helper script: {script}", file=sys.stderr)
        return 2
    return int(completed.returncode)


def _macos_release_env_overrides(args: argparse.Namespace) -> dict[str, str]:
    env: dict[str, str] = {}
    if getattr(args, "app_bundle", None):
        env["APP_BUNDLE"] = str(args.app_bundle)
    if getattr(args, "pkg_path", None):
        env["PKG_PATH"] = str(args.pkg_path)
    if getattr(args, "dmg_path", None):
        env["DMG_PATH"] = str(args.dmg_path)
    if getattr(args, "zip_path", None):
        env["ZIP_PATH"] = str(args.zip_path)
    if getattr(args, "targets", None):
        env["NOTARIZE_TARGETS"] = str(args.targets)
        env["STAPLE_TARGETS"] = str(args.targets)
    if getattr(args, "notary_profile", None):
        env["NOTARY_PROFILE"] = str(args.notary_profile)
    return env


def _is_headless_dmg_failure(output: str) -> bool:
    lowered = output.lower()
    return any(token in lowered for token in MACOS_HEADLESS_DMG_TOKENS)


def _macos_effective_archs(args: argparse.Namespace) -> str:
    value = getattr(args, "archs", None)
    if value:
        return str(value)
    return MACOS_BUILD_ARCHS


def _macos_effective_deployment_target(args: argparse.Namespace) -> str:
    value = getattr(args, "deployment_target", None)
    if value:
        return str(value)
    return MACOS_DEPLOYMENT_TARGET


def _macos_unsigned_build_settings() -> list[str]:
    """Build settings that keep compile-only flows off the signing path."""
    return [
        "CODE_SIGNING_ALLOWED=NO",
        "CODE_SIGNING_REQUIRED=NO",
        "CODE_SIGN_IDENTITY=",
        "DEVELOPMENT_TEAM=",
        "PROVISIONING_PROFILE=",
        "PROVISIONING_PROFILE_SPECIFIER=",
    ]


def _macos_project_spec_path() -> Path:
    return MACOS_ROOT / "project.yml"


def _macos_project_requires_regeneration(project_dir: Path) -> bool:
    if not project_dir.is_dir():
        return True

    spec = _macos_project_spec_path()
    project_file = project_dir / "project.pbxproj"
    if not spec.is_file() or not project_file.is_file():
        return False

    try:
        return spec.stat().st_mtime > project_file.stat().st_mtime
    except OSError:
        return False


def cmd_configure_macos(_: argparse.Namespace) -> int:
    _check_macos()
    xcodegen = _require_tool("xcodegen")
    _require_tool("xcodebuild")
    MACOS_BUILD.mkdir(parents=True, exist_ok=True)
    # Generate the .xcodeproj from project.yml. The generated project lives
    # next to project.yml (in virtualcam/macos/).
    return _run([xcodegen, "generate", "--spec", str(_macos_project_spec_path())],
                cwd=MACOS_ROOT)


def cmd_build_macos(args: argparse.Namespace) -> int:
    _check_macos()
    _require_tool("xcodebuild")
    effective_archs = _macos_effective_archs(args)
    effective_deployment_target = _macos_effective_deployment_target(args)
    proj = MACOS_ROOT / "akvc-macos.xcodeproj"
    if _macos_project_requires_regeneration(proj):
        rc = cmd_configure_macos(args)
        if rc != 0:
            return rc
    # Build the aggregate macOS scheme so the extension, container app, and
    # command-line status/install tools are produced together.
    build_cmd = [
        "xcodebuild", "-project", str(proj),
        "-scheme", "akvc-macos-all",
        "-configuration", "Release",
        "-derivedDataPath", str(MACOS_BUILD),
        f"ARCHS={effective_archs}",
        "ONLY_ACTIVE_ARCH=NO",
        f"MACOSX_DEPLOYMENT_TARGET={effective_deployment_target}",
        "build",
    ]
    build_cmd.extend(_macos_unsigned_build_settings())
    rc = _run(build_cmd)
    if rc != 0:
        return rc
    print(f"[make] Camera Extension bundle: {MACOS_EXT_BUNDLE}")
    print(f"[make] macOS direct sender dylib: {MACOS_DIRECT_SENDER_LIB}")
    print(f"[make] macOS status tool: {MACOS_STATUS_TOOL}")
    print(f"[make] macOS install tool: {MACOS_INSTALL_TOOL}")
    print("[make] NOTE: build completed without code signing so provisioning "
          "is not required for local/CI compilation.")
    print("[make] NOTE: run `python tools/make.py sign` before packaging or "
          "notarization. See docs/macos/signing.md.")
    if getattr(args, "python", False):
        _run([sys.executable, "-m", "pip", "install", "-e",
              str(ROOT / "camera-core")])
        _run([sys.executable, "-m", "pip", "install", "-e",
              str(ROOT / "apps" / "desktop")])
        _run([sys.executable, "-m", "pip", "install", "-e",
              str(ROOT / "apps" / "cli")])
    return 0


def cmd_register_macos(_: argparse.Namespace) -> int:
    _check_macos()
    # The Apple-blessed way to install a Camera Extension is to run the
    # container app, which triggers an OSSystemExtensionRequest that the user must
    # approve. systemextensionsctl is a developer-only escape hatch.
    print(
        "[make] macOS Camera Extension registration is interactive:\n"
        "  1. Build the container app (`python tools/make.py build`).\n"
        "  2. Sign the container app + extension (`python tools/make.py sign`).\n"
        "  3. Launch the container app — it posts OSSystemExtensionRequest.\n"
        "  4. Approve the system-extension prompt in System Settings.\n"
        "  5. Enable the camera in System Settings > Privacy > Camera.\n"
        "For dev-only sideloading you can also run:\n"
        "  systemextensionsctl developer on   # one-time\n"
        "  systemextensionsctl install <team> com.sidus.amaran-desktop.cameraextension"
    )
    return 0


def cmd_unregister_macos(_: argparse.Namespace) -> int:
    _check_macos()
    print(
        "[make] To uninstall the Camera Extension:\n"
        "  systemextensionsctl uninstall <team-id> com.sidus.amaran-desktop.cameraextension\n"
        "or delete it via System Settings > Extensions."
    )
    return 0


def cmd_package_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not args.skip_build:
        rc = cmd_build_macos(args)
        if rc != 0:
            return rc
    sign_identity = _effective_macos_sign_identity()
    if sign_identity:
        rc = cmd_sign_macos(args)
        if rc != 0:
            return rc
    rc = _run_macos_script(MACOS_BUILD_PKG_SCRIPT)
    if rc != 0:
        return rc
    try:
        dmg_completed = _run_macos_script_result(MACOS_BUILD_DMG_SCRIPT, capture_output=True)
    except FileNotFoundError:
        print(f"[make] missing macOS helper script: {MACOS_BUILD_DMG_SCRIPT}", file=sys.stderr)
        return 2
    if dmg_completed.stdout:
        sys.stdout.write(dmg_completed.stdout)
    if dmg_completed.stderr:
        sys.stderr.write(dmg_completed.stderr)
    if dmg_completed.returncode != 0:
        dmg_output = "\n".join(
            part for part in (dmg_completed.stdout, dmg_completed.stderr) if part
        )
        if _is_headless_dmg_failure(dmg_output):
            print("[make] NOTE: dmg creation failed in the current headless/restricted environment; continuing with pkg/zip artifacts.")
        else:
            return int(dmg_completed.returncode)
    rc = _run_macos_script(MACOS_BUILD_ZIP_SCRIPT)
    if rc != 0:
        return rc
    print(f"[make] pkg artifact: {MACOS_PKG}")
    if MACOS_DMG.is_file():
        print(f"[make] dmg artifact: {MACOS_DMG}")
    else:
        print("[make] dmg artifact: not generated in the current environment")
    print(f"[make] zip artifact: {MACOS_ZIP}")
    if getattr(args, "sync_runtime", False):
        rc = _sync_macos_runtime_assets(require_pkg=True)
        if rc != 0:
            return rc
    return 0


def cmd_sign_macos(_: argparse.Namespace) -> int:
    return _run_macos_script(MACOS_SIGN_SCRIPT)


def cmd_notarize_macos(args: argparse.Namespace) -> int:
    env = _macos_release_env_overrides(args)
    if "STAPLE_TARGETS" in env:
        env.pop("STAPLE_TARGETS", None)
    return _run_macos_script(MACOS_NOTARIZE_SCRIPT, env=env or None)


def cmd_staple_macos(args: argparse.Namespace) -> int:
    env = _macos_release_env_overrides(args)
    if "NOTARIZE_TARGETS" in env:
        env.pop("NOTARIZE_TARGETS", None)
    return _run_macos_script(MACOS_STAPLE_SCRIPT, env=env or None)


def cmd_smoke_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_SMOKE_SCRIPT.is_file():
        print(f"[make] missing smoke script: {MACOS_SMOKE_SCRIPT}", file=sys.stderr)
        return 2
    try:
        app_bundle, app_executable = _resolve_macos_container_app_overrides(args)
    except ValueError as exc:
        print(f"[make] {exc}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(MACOS_SMOKE_SCRIPT)]
    if getattr(args, "name", None):
        cmd.extend(["--name", str(args.name)])
    if getattr(args, "status_tool", None):
        cmd.extend(["--status-tool", str(args.status_tool)])
    if getattr(args, "install_tool", None):
        cmd.extend(["--install-tool", str(args.install_tool)])
    if getattr(args, "list_devices_tool", None):
        cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
    if getattr(args, "uninstall_tool", None):
        cmd.extend(["--uninstall-tool", str(args.uninstall_tool)])
    if getattr(args, "sync_ipc_tool", None):
        cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
    if getattr(args, "pkg_path", None):
        cmd.extend(["--pkg-path", str(args.pkg_path)])
    _append_macos_container_app_flags(cmd, app_bundle=app_bundle, app_executable=app_executable)
    if getattr(args, "direct_sender_library", None):
        cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
    if getattr(args, "installer_executable", None):
        cmd.extend(["--installer-executable", str(args.installer_executable)])
    if getattr(args, "direct_push_demo_tool", None):
        cmd.extend(["--direct-push-demo-tool", str(args.direct_push_demo_tool)])
    if getattr(args, "direct_push_frames", None) is not None:
        cmd.extend(["--direct-push-frames", str(args.direct_push_frames)])
    if getattr(args, "direct_push_frame_kind", None):
        cmd.extend(["--direct-push-frame-kind", str(args.direct_push_frame_kind)])
    if getattr(args, "direct_push_entrypoint", None):
        cmd.extend(["--direct-push-entrypoint", str(args.direct_push_entrypoint)])
    if getattr(args, "direct_push_allow_shared_memory_fallback", False):
        cmd.append("--direct-push-allow-shared-memory-fallback")
    if getattr(args, "direct_push_request_camera_access", False):
        cmd.append("--direct-push-request-camera-access")
    if getattr(args, "direct_sender_object_demo_tool", None):
        cmd.extend(["--direct-sender-object-demo-tool", str(args.direct_sender_object_demo_tool)])
    if getattr(args, "direct_sender_object_frames", None) is not None:
        cmd.extend(["--direct-sender-object-frames", str(args.direct_sender_object_frames)])
    if getattr(args, "direct_sender_object_frame_kind", None):
        cmd.extend(["--direct-sender-object-frame-kind", str(args.direct_sender_object_frame_kind)])
    if getattr(args, "direct_sender_object_request_camera_access", False):
        cmd.append("--direct-sender-object-request-camera-access")
    if getattr(args, "disable_auto_package", False):
        cmd.append("--disable-auto-package")
    if args.run_install:
        cmd.append("--run-install")
    if args.run_uninstall:
        cmd.append("--run-uninstall")
    if getattr(args, "run_direct_push_demo", False):
        cmd.append("--run-direct-push-demo")
    if getattr(args, "run_direct_sender_object_demo", False):
        cmd.append("--run-direct-sender-object-demo")
    if args.framebus_roundtrip_json:
        cmd.extend(["--framebus-roundtrip-json", str(args.framebus_roundtrip_json)])
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_direct_push_demo_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_DIRECT_PUSH_DEMO_SCRIPT.is_file():
        print(f"[make] missing direct push demo script: {MACOS_DIRECT_PUSH_DEMO_SCRIPT}", file=sys.stderr)
        return 2
    try:
        app_bundle, app_executable = _resolve_macos_container_app_overrides(args)
    except ValueError as exc:
        print(f"[make] {exc}", file=sys.stderr)
        return 2
    if app_bundle and app_executable:
        print(
            "[make] --app-bundle/--host-bundle and --app-executable/--host-executable are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    cmd = [
        sys.executable,
        str(MACOS_DIRECT_PUSH_DEMO_SCRIPT),
        "--width", str(args.width),
        "--height", str(args.height),
        "--fps", str(args.fps),
        "--duration", str(args.duration),
        "--name", str(args.name),
    ]
    _append_macos_container_app_flags(cmd, app_bundle=app_bundle, app_executable=app_executable)
    if getattr(args, "direct_sender_library", None):
        cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
    if getattr(args, "frame_kind", None):
        cmd.extend(["--frame-kind", str(args.frame_kind)])
    if getattr(args, "entrypoint", None):
        cmd.extend(["--entrypoint", str(args.entrypoint)])
    if getattr(args, "allow_shared_memory_fallback", False):
        cmd.append("--allow-shared-memory-fallback")
    if getattr(args, "request_camera_access", False):
        cmd.append("--request-camera-access")
    if getattr(args, "require_direct_runtime", False):
        cmd.append("--require-direct-runtime")
    if getattr(args, "probe_only", False):
        cmd.append("--probe-only")
    if getattr(args, "frames", None) is not None:
        cmd.extend(["--frames", str(args.frames)])
    if getattr(args, "output", None):
        cmd.extend(["--report-json", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_direct_sender_object_demo_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_DIRECT_SENDER_OBJECT_DEMO_SCRIPT.is_file():
        print(
            f"[make] missing direct sender object demo script: {MACOS_DIRECT_SENDER_OBJECT_DEMO_SCRIPT}",
            file=sys.stderr,
        )
        return 2
    cmd = [
        sys.executable,
        str(MACOS_DIRECT_SENDER_OBJECT_DEMO_SCRIPT),
        "--width", str(args.width),
        "--height", str(args.height),
        "--fps", str(args.fps),
        "--name", str(args.name),
    ]
    if getattr(args, "direct_sender_library", None):
        cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
    if getattr(args, "frame_kind", None):
        cmd.extend(["--frame-kind", str(args.frame_kind)])
    if getattr(args, "request_camera_access", False):
        cmd.append("--request-camera-access")
    if getattr(args, "probe_only", False):
        cmd.append("--inspect-only")
    if getattr(args, "frames", None) is not None:
        cmd.extend(["--frames", str(args.frames)])
    if getattr(args, "output", None):
        cmd.extend(["--report-json", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_verify_native_macos(_: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_NATIVE_VERIFY_SCRIPT.is_file():
        print(f"[make] missing native verify script: {MACOS_NATIVE_VERIFY_SCRIPT}", file=sys.stderr)
        return 2
    return _run([sys.executable, str(MACOS_NATIVE_VERIFY_SCRIPT)], cwd=ROOT, env=_macos_script_env())


def cmd_preflight_macos(_: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_TOOLCHAIN_PREFLIGHT_SCRIPT.is_file():
        print(f"[make] missing toolchain preflight script: {MACOS_TOOLCHAIN_PREFLIGHT_SCRIPT}", file=sys.stderr)
        return 2
    return _run([sys.executable, str(MACOS_TOOLCHAIN_PREFLIGHT_SCRIPT)], cwd=ROOT, env=_macos_script_env())


def cmd_release_diagnostics_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_RELEASE_DIAGNOSTICS_SCRIPT.is_file():
        print(f"[make] missing release diagnostics script: {MACOS_RELEASE_DIAGNOSTICS_SCRIPT}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(MACOS_RELEASE_DIAGNOSTICS_SCRIPT)]
    if args.app_bundle:
        cmd.extend(["--app-bundle", str(args.app_bundle)])
    if args.extension_bundle:
        cmd.extend(["--extension-bundle", str(args.extension_bundle)])
    if args.pkg_path:
        cmd.extend(["--pkg-path", str(args.pkg_path)])
    if args.dmg_path:
        cmd.extend(["--dmg-path", str(args.dmg_path)])
    if args.zip_path:
        cmd.extend(["--zip-path", str(args.zip_path)])
    if getattr(args, "sync_ipc_tool", None):
        cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_benchmark_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_BENCHMARK_SCRIPT.is_file():
        print(f"[make] missing benchmark script: {MACOS_BENCHMARK_SCRIPT}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(MACOS_BENCHMARK_SCRIPT)]
    if args.matrix:
        cmd.append("--matrix")
    elif args.profile:
        cmd.extend(["--profile", str(args.profile)])
    else:
        cmd.extend([
            "--width", str(args.width),
            "--height", str(args.height),
            "--fps", str(args.fps),
        ])
    cmd.extend([
        "--duration", str(args.duration),
        "--warmup", str(args.warmup),
    ])
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_framebus_roundtrip_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_FRAMEBUS_ROUNDTRIP_SCRIPT.is_file():
        print(f"[make] missing framebus roundtrip script: {MACOS_FRAMEBUS_ROUNDTRIP_SCRIPT}", file=sys.stderr)
        return 2
    cmd = [
        sys.executable,
        str(MACOS_FRAMEBUS_ROUNDTRIP_SCRIPT),
        "--width", str(args.width),
        "--height", str(args.height),
        "--attempts", str(args.attempts),
        "--sleep-ms", str(args.sleep_ms),
        "--flags", str(args.flags),
        "--producer-kind", str(args.producer_kind),
    ]
    if args.compiler:
        cmd.extend(["--compiler", str(args.compiler)])
    if args.binary:
        cmd.extend(["--binary", str(args.binary)])
    if args.skip_compile:
        cmd.append("--skip-compile")
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_list_devices_binary_check_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_LIST_DEVICES_BINARY_CHECK_SCRIPT.is_file():
        print(
            f"[make] missing list-devices binary check script: {MACOS_LIST_DEVICES_BINARY_CHECK_SCRIPT}",
            file=sys.stderr,
        )
        return 2
    cmd = [sys.executable, str(MACOS_LIST_DEVICES_BINARY_CHECK_SCRIPT)]
    if args.list_devices_tool:
        cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
    if getattr(args, "expected_prefix", None):
        cmd.extend(["--expected-prefix", str(args.expected_prefix)])
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_validation_report_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_VALIDATION_REPORT_SCRIPT.is_file():
        print(f"[make] missing validation report script: {MACOS_VALIDATION_REPORT_SCRIPT}", file=sys.stderr)
        return 2
    try:
        app_bundle, app_executable = _resolve_macos_container_app_overrides(args)
    except ValueError as exc:
        print(f"[make] {exc}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(MACOS_VALIDATION_REPORT_SCRIPT)]
    if getattr(args, "name", None):
        cmd.extend(["--name", str(args.name)])
    if args.status_tool:
        cmd.extend(["--status-tool", str(args.status_tool)])
    if args.list_devices_tool:
        cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
    if args.install_tool:
        cmd.extend(["--install-tool", str(args.install_tool)])
    if getattr(args, "uninstall_tool", None):
        cmd.extend(["--uninstall-tool", str(args.uninstall_tool)])
    if getattr(args, "sync_ipc_tool", None):
        cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
    _append_macos_container_app_flags(cmd, app_bundle=app_bundle, app_executable=app_executable)
    if getattr(args, "direct_sender_library", None):
        cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
    if getattr(args, "pkg_path", None):
        cmd.extend(["--pkg-path", str(args.pkg_path)])
    if getattr(args, "installer_executable", None):
        cmd.extend(["--installer-executable", str(args.installer_executable)])
    if getattr(args, "disable_auto_package", False):
        cmd.append("--disable-auto-package")
    if args.preflight_json:
        cmd.extend(["--preflight-json", str(args.preflight_json)])
    if args.release_diagnostics_json:
        cmd.extend(["--release-diagnostics-json", str(args.release_diagnostics_json)])
    if args.install_session_json:
        cmd.extend(["--install-session-json", str(args.install_session_json)])
    if args.smoke_json:
        cmd.extend(["--smoke-json", str(args.smoke_json)])
    if args.framebus_roundtrip_json:
        cmd.extend(["--framebus-roundtrip-json", str(args.framebus_roundtrip_json)])
    if args.status_binary_check_json:
        cmd.extend(["--status-binary-check-json", str(args.status_binary_check_json)])
    if args.list_devices_binary_check_json:
        cmd.extend(["--list-devices-binary-check-json", str(args.list_devices_binary_check_json)])
    if args.benchmark_json:
        cmd.extend(["--benchmark-json", str(args.benchmark_json)])
    if args.demo_json:
        cmd.extend(["--demo-json", str(args.demo_json)])
    if args.manual_results:
        cmd.extend(["--manual-results", str(args.manual_results)])
    if args.write_manual_template:
        cmd.extend(["--write-manual-template", str(args.write_manual_template)])
    if args.run_install:
        cmd.append("--run-install")
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_validation_session_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_VALIDATION_SESSION_SCRIPT.is_file():
        print(f"[make] missing validation session script: {MACOS_VALIDATION_SESSION_SCRIPT}", file=sys.stderr)
        return 2
    try:
        app_bundle, app_executable = _resolve_macos_container_app_overrides(args)
    except ValueError as exc:
        print(f"[make] {exc}", file=sys.stderr)
        return 2
    cmd = [
        sys.executable,
        str(MACOS_VALIDATION_SESSION_SCRIPT),
        "--output-dir", str(args.output_dir),
        "--benchmark-warmup", str(args.benchmark_warmup),
        "--mode", args.mode,
        "--width", str(args.width),
        "--height", str(args.height),
        "--fps", str(args.fps),
        "--duration", str(args.duration),
        "--name", args.name,
    ]
    if args.benchmark_profile:
        cmd.extend(["--benchmark-profile", str(args.benchmark_profile)])
    if args.benchmark_matrix:
        cmd.append("--benchmark-matrix")
    if args.video_path:
        cmd.extend(["--video-path", str(args.video_path)])
    if args.status_tool:
        cmd.extend(["--status-tool", str(args.status_tool)])
    if args.list_devices_tool:
        cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
    if args.install_tool:
        cmd.extend(["--install-tool", str(args.install_tool)])
    if getattr(args, "uninstall_tool", None):
        cmd.extend(["--uninstall-tool", str(args.uninstall_tool)])
    if getattr(args, "sync_ipc_tool", None):
        cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
    _append_macos_container_app_flags(cmd, app_bundle=app_bundle, app_executable=app_executable)
    if getattr(args, "direct_sender_library", None):
        cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
    if getattr(args, "pkg_path", None):
        cmd.extend(["--pkg-path", str(args.pkg_path)])
    if getattr(args, "installer_executable", None):
        cmd.extend(["--installer-executable", str(args.installer_executable)])
    if getattr(args, "disable_auto_package", False):
        cmd.append("--disable-auto-package")
    if args.manual_results:
        cmd.extend(["--manual-results", str(args.manual_results)])
    if args.reuse_existing_artifacts:
        cmd.append("--reuse-existing-artifacts")
    if args.preflight_tool:
        cmd.extend(["--preflight-tool", str(args.preflight_tool)])
    if args.release_diagnostics_tool:
        cmd.extend(["--release-diagnostics-tool", str(args.release_diagnostics_tool)])
    if args.smoke_tool:
        cmd.extend(["--smoke-tool", str(args.smoke_tool)])
    if args.install_session_tool:
        cmd.extend(["--install-session-tool", str(args.install_session_tool)])
    if args.framebus_roundtrip_tool:
        cmd.extend(["--framebus-roundtrip-tool", str(args.framebus_roundtrip_tool)])
    if getattr(args, "framebus_producer_kind", None):
        cmd.extend(["--framebus-producer-kind", str(args.framebus_producer_kind)])
    if getattr(args, "direct_push_demo_tool", None):
        cmd.extend(["--direct-push-demo-tool", str(args.direct_push_demo_tool)])
    if getattr(args, "direct_push_frames", None) is not None:
        cmd.extend(["--direct-push-frames", str(args.direct_push_frames)])
    if getattr(args, "direct_push_frame_kind", None):
        cmd.extend(["--direct-push-frame-kind", str(args.direct_push_frame_kind)])
    if getattr(args, "direct_push_entrypoint", None):
        cmd.extend(["--direct-push-entrypoint", str(args.direct_push_entrypoint)])
    if getattr(args, "direct_push_allow_shared_memory_fallback", False):
        cmd.append("--direct-push-allow-shared-memory-fallback")
    if getattr(args, "direct_push_request_camera_access", False):
        cmd.append("--direct-push-request-camera-access")
    if getattr(args, "direct_sender_object_demo_tool", None):
        cmd.extend(["--direct-sender-object-demo-tool", str(args.direct_sender_object_demo_tool)])
    if getattr(args, "direct_sender_object_frames", None) is not None:
        cmd.extend(["--direct-sender-object-frames", str(args.direct_sender_object_frames)])
    if getattr(args, "direct_sender_object_frame_kind", None):
        cmd.extend(["--direct-sender-object-frame-kind", str(args.direct_sender_object_frame_kind)])
    if getattr(args, "direct_sender_object_request_camera_access", False):
        cmd.append("--direct-sender-object-request-camera-access")
    if args.status_binary_check_tool:
        cmd.extend(["--status-binary-check-tool", str(args.status_binary_check_tool)])
    if args.list_devices_binary_check_tool:
        cmd.extend(["--list-devices-binary-check-tool", str(args.list_devices_binary_check_tool)])
    if getattr(args, "sdk_contract_tool", None):
        cmd.extend(["--sdk-contract-tool", str(args.sdk_contract_tool)])
    if args.artifact_check_tool:
        cmd.extend(["--artifact-check-tool", str(args.artifact_check_tool)])
    if args.acceptance_tool:
        cmd.extend(["--acceptance-tool", str(args.acceptance_tool)])
    if args.summary_tool:
        cmd.extend(["--summary-tool", str(args.summary_tool)])
    if args.demo_tool:
        cmd.extend(["--demo-tool", str(args.demo_tool)])
    if args.benchmark_tool:
        cmd.extend(["--benchmark-tool", str(args.benchmark_tool)])
    if args.validation_report_tool:
        cmd.extend(["--validation-report-tool", str(args.validation_report_tool)])
    if args.skip_demo:
        cmd.append("--skip-demo")
    if args.skip_preflight:
        cmd.append("--skip-preflight")
    if args.skip_release_diagnostics:
        cmd.append("--skip-release-diagnostics")
    if args.skip_benchmark:
        cmd.append("--skip-benchmark")
    if args.run_install:
        cmd.append("--run-install")
    if args.run_uninstall:
        cmd.append("--run-uninstall")
    if args.run_install_session:
        cmd.append("--run-install-session")
    if args.run_framebus_roundtrip:
        cmd.append("--run-framebus-roundtrip")
    if getattr(args, "run_direct_push_demo", False):
        cmd.append("--run-direct-push-demo")
    if getattr(args, "run_direct_sender_object_demo", False):
        cmd.append("--run-direct-sender-object-demo")
    if args.run_status_binary_check:
        cmd.append("--run-status-binary-check")
    if args.run_list_devices_binary_check:
        cmd.append("--run-list-devices-binary-check")
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_validation_session_artifact_check_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_VALIDATION_SESSION_ARTIFACT_CHECK_SCRIPT.is_file():
        print(
            f"[make] missing validation-session artifact check script: "
            f"{MACOS_VALIDATION_SESSION_ARTIFACT_CHECK_SCRIPT}",
            file=sys.stderr,
        )
        return 2
    cmd = [
        sys.executable,
        str(MACOS_VALIDATION_SESSION_ARTIFACT_CHECK_SCRIPT),
        "--manifest",
        str(args.manifest),
    ]
    if args.require_existing_artifacts:
        cmd.append("--require-existing-artifacts")
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_validation_session_acceptance_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_VALIDATION_SESSION_ACCEPTANCE_SCRIPT.is_file():
        print(
            f"[make] missing validation-session acceptance script: "
            f"{MACOS_VALIDATION_SESSION_ACCEPTANCE_SCRIPT}",
            file=sys.stderr,
        )
        return 2
    cmd = [
        sys.executable,
        str(MACOS_VALIDATION_SESSION_ACCEPTANCE_SCRIPT),
        "--manifest",
        str(args.manifest),
    ]
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_validation_session_acceptance_contract_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_VALIDATION_SESSION_ACCEPTANCE_CONTRACT_SCRIPT.is_file():
        print(
            f"[make] missing validation-session acceptance contract script: "
            f"{MACOS_VALIDATION_SESSION_ACCEPTANCE_CONTRACT_SCRIPT}",
            file=sys.stderr,
        )
        return 2
    cmd = [
        sys.executable,
        str(MACOS_VALIDATION_SESSION_ACCEPTANCE_CONTRACT_SCRIPT),
    ]
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_validation_session_summary_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_VALIDATION_SESSION_SUMMARY_SCRIPT.is_file():
        print(
            f"[make] missing validation-session summary script: "
            f"{MACOS_VALIDATION_SESSION_SUMMARY_SCRIPT}",
            file=sys.stderr,
        )
        return 2
    cmd = [
        sys.executable,
        str(MACOS_VALIDATION_SESSION_SUMMARY_SCRIPT),
        "--manifest",
        str(args.manifest),
    ]
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def cmd_install_session_macos(args: argparse.Namespace) -> int:
    _check_macos()
    if not MACOS_INSTALL_SESSION_SCRIPT.is_file():
        print(f"[make] missing install session script: {MACOS_INSTALL_SESSION_SCRIPT}", file=sys.stderr)
        return 2
    try:
        app_bundle, app_executable = _resolve_macos_container_app_overrides(args)
    except ValueError as exc:
        print(f"[make] {exc}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(MACOS_INSTALL_SESSION_SCRIPT)]
    if getattr(args, "name", None):
        cmd.extend(["--name", str(args.name)])
    if args.status_tool:
        cmd.extend(["--status-tool", str(args.status_tool)])
    if args.install_tool:
        cmd.extend(["--install-tool", str(args.install_tool)])
    if args.list_devices_tool:
        cmd.extend(["--list-devices-tool", str(args.list_devices_tool)])
    if args.uninstall_tool:
        cmd.extend(["--uninstall-tool", str(args.uninstall_tool)])
    if getattr(args, "sync_ipc_tool", None):
        cmd.extend(["--sync-ipc-tool", str(args.sync_ipc_tool)])
    if args.pkg_path:
        cmd.extend(["--pkg-path", str(args.pkg_path)])
    _append_macos_container_app_flags(cmd, app_bundle=app_bundle, app_executable=app_executable)
    if getattr(args, "direct_sender_library", None):
        cmd.extend(["--direct-sender-library", str(args.direct_sender_library)])
    if args.installer_executable:
        cmd.extend(["--installer-executable", str(args.installer_executable)])
    if args.framebus_roundtrip_json:
        cmd.extend(["--framebus-roundtrip-json", str(args.framebus_roundtrip_json)])
    if getattr(args, "direct_push_demo_tool", None):
        cmd.extend(["--direct-push-demo-tool", str(args.direct_push_demo_tool)])
    if getattr(args, "direct_push_frames", None) is not None:
        cmd.extend(["--direct-push-frames", str(args.direct_push_frames)])
    if getattr(args, "direct_push_frame_kind", None):
        cmd.extend(["--direct-push-frame-kind", str(args.direct_push_frame_kind)])
    if getattr(args, "direct_push_entrypoint", None):
        cmd.extend(["--direct-push-entrypoint", str(args.direct_push_entrypoint)])
    if getattr(args, "direct_push_allow_shared_memory_fallback", False):
        cmd.append("--direct-push-allow-shared-memory-fallback")
    if getattr(args, "direct_push_request_camera_access", False):
        cmd.append("--direct-push-request-camera-access")
    if getattr(args, "direct_sender_object_demo_tool", None):
        cmd.extend(["--direct-sender-object-demo-tool", str(args.direct_sender_object_demo_tool)])
    if getattr(args, "direct_sender_object_frames", None) is not None:
        cmd.extend(["--direct-sender-object-frames", str(args.direct_sender_object_frames)])
    if getattr(args, "direct_sender_object_frame_kind", None):
        cmd.extend(["--direct-sender-object-frame-kind", str(args.direct_sender_object_frame_kind)])
    if getattr(args, "direct_sender_object_request_camera_access", False):
        cmd.append("--direct-sender-object-request-camera-access")
    if args.disable_auto_package:
        cmd.append("--disable-auto-package")
    if args.run_uninstall:
        cmd.append("--run-uninstall")
    if getattr(args, "run_direct_push_demo", False):
        cmd.append("--run-direct-push-demo")
    if getattr(args, "run_direct_sender_object_demo", False):
        cmd.append("--run-direct-sender-object-demo")
    if args.status_poll_attempts is not None:
        cmd.extend(["--status-poll-attempts", str(args.status_poll_attempts)])
    if args.poll_interval_seconds is not None:
        cmd.extend(["--poll-interval-seconds", str(args.poll_interval_seconds)])
    if args.output:
        cmd.extend(["--output", str(args.output)])
    return _run(cmd, cwd=ROOT, env=_macos_script_env())


def _sync_macos_runtime_assets(*, require_pkg: bool) -> int:
    assets = {
        "akvc-macos-status": MACOS_STATUS_TOOL,
        "akvc-macos-install": MACOS_INSTALL_TOOL,
        "akvc-macos-uninstall": MACOS_UNINSTALL_TOOL,
        "akvc-macos-list-devices": MACOS_LIST_DEVICES_TOOL,
        "akvc-macos-sync-ipc": MACOS_SYNC_IPC_TOOL,
        "libakvc-macos-direct-sender.dylib": MACOS_DIRECT_SENDER_LIB,
    }
    if require_pkg:
        assets["VirtualCamera.pkg"] = MACOS_PKG
    elif MACOS_PKG.is_file():
        assets["VirtualCamera.pkg"] = MACOS_PKG

    missing = [name for name, path in assets.items() if not path.is_file()]
    if missing:
        print(
            "[make] missing macOS runtime assets: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    MACOS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for name, src in assets.items():
        dst = MACOS_RUNTIME_DIR / name
        shutil.copy2(src, dst)
        if dst.name != "VirtualCamera.pkg":
            dst.chmod(0o755)
        print(f"[make] synced macOS runtime asset: {dst}")
    return 0


def cmd_sync_macos_runtime(args: argparse.Namespace) -> int:
    return _sync_macos_runtime_assets(require_pkg=bool(args.require_pkg))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="make.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("configure").set_defaults(func="configure")
    pb = sub.add_parser("build")
    pb.add_argument("--python", action="store_true",
                    help="also pip install -e the Python packages")
    pb.add_argument("--archs",
                    help='override macOS build ARCHS (default: "arm64 x86_64")')
    pb.add_argument("--deployment-target",
                    help='override macOS deployment target (default: "13.0")')
    pb.set_defaults(func="build")
    sub.add_parser("register").set_defaults(func="register")
    sub.add_parser("unregister").set_defaults(func="unregister")
    pp = sub.add_parser("package")
    pp.add_argument("--skip-build", action="store_true",
                    help="skip xcodebuild and package current build outputs")
    pp.add_argument("--archs",
                    help='override macOS build ARCHS before packaging (default: "arm64 x86_64")')
    pp.add_argument("--deployment-target",
                    help='override macOS deployment target before packaging (default: "13.0")')
    pp.add_argument("--sync-runtime", action="store_true",
                    help="copy packaged macOS runtime assets into camera-core/src/akvc/_runtime/macos")
    pp.set_defaults(func="package")
    sub.add_parser("sign").set_defaults(func="sign")
    pn = sub.add_parser("notarize")
    pn.add_argument("--app-bundle")
    pn.add_argument("--pkg-path")
    pn.add_argument("--dmg-path")
    pn.add_argument("--zip-path")
    pn.add_argument("--targets",
                    help='comma-separated notarization targets (default script behavior: "app,pkg")')
    pn.add_argument("--notary-profile",
                    help="override NOTARY_PROFILE for notarytool keychain profile selection")
    pn.set_defaults(func="notarize")
    pst = sub.add_parser("staple")
    pst.add_argument("--app-bundle")
    pst.add_argument("--pkg-path")
    pst.add_argument("--dmg-path")
    pst.add_argument("--targets",
                     help='comma-separated staple targets (default script behavior: "app,pkg")')
    pst.set_defaults(func="staple")
    ps = sub.add_parser("smoke")
    ps.add_argument("--name", default="AK Virtual Camera",
                    help="runtime virtual camera name to persist before smoke checks")
    ps.add_argument("--status-tool")
    ps.add_argument("--install-tool")
    ps.add_argument("--list-devices-tool")
    ps.add_argument("--uninstall-tool")
    ps.add_argument("--sync-ipc-tool")
    ps.add_argument("--direct-push-demo-tool")
    ps.add_argument("--direct-push-frames", type=int)
    ps.add_argument("--direct-push-frame-kind")
    ps.add_argument("--direct-push-entrypoint")
    ps.add_argument("--direct-push-allow-shared-memory-fallback", action="store_true")
    ps.add_argument("--direct-push-request-camera-access", action="store_true")
    ps.add_argument("--direct-sender-object-demo-tool")
    ps.add_argument("--direct-sender-object-frames", type=int)
    ps.add_argument("--direct-sender-object-frame-kind")
    ps.add_argument("--direct-sender-object-request-camera-access", action="store_true")
    ps.add_argument("--pkg-path")
    ps.add_argument("--app-bundle")
    ps.add_argument("--app-executable")
    ps.add_argument("--host-bundle")
    ps.add_argument("--host-executable")
    ps.add_argument("--direct-sender-library")
    ps.add_argument("--installer-executable")
    ps.add_argument("--disable-auto-package", action="store_true")
    ps.add_argument("--run-install", action="store_true",
                    help="also run the install tool during smoke validation")
    ps.add_argument("--run-uninstall", action="store_true",
                    help="also run the uninstall tool during smoke validation")
    ps.add_argument("--run-direct-push-demo", action="store_true")
    ps.add_argument("--run-direct-sender-object-demo", action="store_true")
    ps.add_argument("--framebus-roundtrip-json",
                    help="attach an existing framebus roundtrip JSON artifact to smoke status resolution")
    ps.add_argument("--output",
                    help="write structured smoke JSON to this path")
    ps.set_defaults(func="smoke")
    pdpd = sub.add_parser("direct-push-demo")
    pdpd.add_argument("--width", type=int, default=1280)
    pdpd.add_argument("--height", type=int, default=720)
    pdpd.add_argument("--fps", type=float, default=30.0)
    pdpd.add_argument("--duration", type=float, default=3.0)
    pdpd.add_argument("--frames", type=int)
    pdpd.add_argument("--name", default="AK Virtual Camera")
    pdpd.add_argument("--app-bundle")
    pdpd.add_argument("--app-executable")
    pdpd.add_argument("--host-bundle")
    pdpd.add_argument("--host-executable")
    pdpd.add_argument("--direct-sender-library")
    pdpd.add_argument("--frame-kind")
    pdpd.add_argument("--entrypoint")
    pdpd.add_argument("--allow-shared-memory-fallback", action="store_true")
    pdpd.add_argument("--request-camera-access", action="store_true")
    pdpd.add_argument("--require-direct-runtime", action="store_true")
    pdpd.add_argument("--probe-only", "--inspect-only", dest="probe_only", action="store_true")
    pdpd.add_argument("--output")
    pdpd.set_defaults(func="direct-push-demo")
    pdso = sub.add_parser("direct-sender-object-demo")
    pdso.add_argument("--width", type=int, default=1280)
    pdso.add_argument("--height", type=int, default=720)
    pdso.add_argument("--fps", type=float, default=30.0)
    pdso.add_argument("--frames", type=int)
    pdso.add_argument("--name", default="AK Virtual Camera")
    pdso.add_argument("--direct-sender-library")
    pdso.add_argument("--frame-kind")
    pdso.add_argument("--request-camera-access", action="store_true")
    pdso.add_argument("--probe-only", "--inspect-only", dest="probe_only", action="store_true")
    pdso.add_argument("--output")
    pdso.set_defaults(func="direct-sender-object-demo")
    sub.add_parser("preflight").set_defaults(func="preflight")
    prd = sub.add_parser("release-diagnostics")
    prd.add_argument("--app-bundle")
    prd.add_argument("--extension-bundle")
    prd.add_argument("--pkg-path")
    prd.add_argument("--dmg-path")
    prd.add_argument("--zip-path")
    prd.add_argument("--sync-ipc-tool")
    prd.add_argument("--output")
    prd.set_defaults(func="release-diagnostics")
    sub.add_parser("verify-native").set_defaults(func="verify-native")
    pbm = sub.add_parser("benchmark")
    pbm.add_argument("--width", type=int, default=1920)
    pbm.add_argument("--height", type=int, default=1080)
    pbm.add_argument("--fps", type=float, default=60.0)
    pbm.add_argument("--duration", type=float, default=5.0)
    pbm.add_argument("--warmup", type=float, default=1.0)
    pbm.add_argument("--profile", choices=["720p30", "720p60", "1080p30", "1080p60", "4k30", "4k60"])
    pbm.add_argument("--matrix", action="store_true")
    pbm.add_argument("--output")
    pbm.set_defaults(func="benchmark")
    pfr = sub.add_parser("framebus-roundtrip")
    pfr.add_argument("--width", type=int, default=128)
    pfr.add_argument("--height", type=int, default=72)
    pfr.add_argument("--compiler")
    pfr.add_argument("--binary", type=Path)
    pfr.add_argument("--skip-compile", action="store_true")
    pfr.add_argument("--attempts", type=int, default=8)
    pfr.add_argument("--sleep-ms", type=int, default=25)
    pfr.add_argument("--flags", type=int, default=2)
    pfr.add_argument("--producer-kind", choices=["shm-sink", "mac-virtual-camera"], default="shm-sink")
    pfr.add_argument("--output")
    pfr.set_defaults(func="framebus-roundtrip")
    pld = sub.add_parser("list-devices-binary-check")
    pld.add_argument("--list-devices-tool")
    pld.add_argument("--expected-prefix")
    pld.add_argument("--output")
    pld.set_defaults(func="list-devices-binary-check")
    pvr = sub.add_parser("validation-report")
    pvr.add_argument("--status-tool")
    pvr.add_argument("--list-devices-tool")
    pvr.add_argument("--install-tool")
    pvr.add_argument("--uninstall-tool")
    pvr.add_argument("--sync-ipc-tool")
    pvr.add_argument("--app-bundle")
    pvr.add_argument("--app-executable")
    pvr.add_argument("--host-bundle")
    pvr.add_argument("--host-executable")
    pvr.add_argument("--pkg-path")
    pvr.add_argument("--installer-executable")
    pvr.add_argument("--disable-auto-package", action="store_true")
    pvr.add_argument("--preflight-json")
    pvr.add_argument("--release-diagnostics-json")
    pvr.add_argument("--install-session-json")
    pvr.add_argument("--smoke-json")
    pvr.add_argument("--framebus-roundtrip-json")
    pvr.add_argument("--status-binary-check-json")
    pvr.add_argument("--list-devices-binary-check-json")
    pvr.add_argument("--benchmark-json")
    pvr.add_argument("--demo-json")
    pvr.add_argument("--manual-results")
    pvr.add_argument("--write-manual-template")
    pvr.add_argument("--name", default="AK Virtual Camera")
    pvr.add_argument("--run-install", action="store_true")
    pvr.add_argument("--output")
    pvr.set_defaults(func="validation-report")
    pvs = sub.add_parser("validation-session")
    pvs.add_argument("--output-dir", required=True)
    pvs.add_argument("--status-tool")
    pvs.add_argument("--list-devices-tool")
    pvs.add_argument("--install-tool")
    pvs.add_argument("--uninstall-tool")
    pvs.add_argument("--sync-ipc-tool")
    pvs.add_argument("--app-bundle")
    pvs.add_argument("--app-executable")
    pvs.add_argument("--host-bundle")
    pvs.add_argument("--host-executable")
    pvs.add_argument("--direct-sender-library")
    pvs.add_argument("--pkg-path")
    pvs.add_argument("--installer-executable")
    pvs.add_argument("--disable-auto-package", action="store_true")
    pvs.add_argument("--manual-results")
    pvs.add_argument("--reuse-existing-artifacts", action="store_true")
    pvs.add_argument("--preflight-tool")
    pvs.add_argument("--release-diagnostics-tool")
    pvs.add_argument("--smoke-tool")
    pvs.add_argument("--install-session-tool")
    pvs.add_argument("--framebus-roundtrip-tool")
    pvs.add_argument("--framebus-producer-kind", choices=["shm-sink", "mac-virtual-camera"], default="mac-virtual-camera")
    pvs.add_argument("--direct-push-demo-tool")
    pvs.add_argument("--direct-push-frames", type=int)
    pvs.add_argument("--direct-push-frame-kind")
    pvs.add_argument("--direct-push-entrypoint")
    pvs.add_argument("--direct-push-allow-shared-memory-fallback", action="store_true")
    pvs.add_argument("--direct-push-request-camera-access", action="store_true")
    pvs.add_argument("--direct-sender-object-demo-tool")
    pvs.add_argument("--direct-sender-object-frames", type=int)
    pvs.add_argument("--direct-sender-object-frame-kind")
    pvs.add_argument("--direct-sender-object-request-camera-access", action="store_true")
    pvs.add_argument("--status-binary-check-tool")
    pvs.add_argument("--list-devices-binary-check-tool")
    pvs.add_argument("--sdk-contract-tool")
    pvs.add_argument("--artifact-check-tool")
    pvs.add_argument("--acceptance-tool")
    pvs.add_argument("--summary-tool")
    pvs.add_argument("--demo-tool")
    pvs.add_argument("--benchmark-tool")
    pvs.add_argument("--validation-report-tool")
    pvs.add_argument("--skip-preflight", action="store_true")
    pvs.add_argument("--skip-release-diagnostics", action="store_true")
    pvs.add_argument("--skip-demo", action="store_true")
    pvs.add_argument("--skip-benchmark", action="store_true")
    pvs.add_argument("--run-install", action="store_true")
    pvs.add_argument("--run-uninstall", action="store_true")
    pvs.add_argument("--run-install-session", action="store_true")
    pvs.add_argument("--run-framebus-roundtrip", action="store_true")
    pvs.add_argument("--run-direct-push-demo", action="store_true")
    pvs.add_argument("--run-direct-sender-object-demo", action="store_true")
    pvs.add_argument("--run-status-binary-check", action="store_true")
    pvs.add_argument("--run-list-devices-binary-check", action="store_true")
    pvs.add_argument("--benchmark-profile", choices=["720p30", "720p60", "1080p30", "1080p60", "4k30", "4k60"])
    pvs.add_argument("--benchmark-matrix", action="store_true")
    pvs.add_argument("--benchmark-warmup", type=float, default=1.0)
    pvs.add_argument(
        "--mode",
        choices=["numpy-direct", "provider", "latest-provider", "image", "pixmap", "widget", "screen", "video-file"],
        default="provider",
    )
    pvs.add_argument("--video-path")
    pvs.add_argument("--width", type=int, default=1280)
    pvs.add_argument("--height", type=int, default=720)
    pvs.add_argument("--fps", type=float, default=30.0)
    pvs.add_argument("--duration", type=float, default=5.0)
    pvs.add_argument("--name", default="AK Virtual Camera")
    pvs.set_defaults(func="validation-session")
    pvsa = sub.add_parser("validation-session-artifact-check")
    pvsa.add_argument("--manifest", default=str(MACOS_BUILD / "session" / "session-manifest.json"))
    pvsa.add_argument("--require-existing-artifacts", action="store_true")
    pvsa.add_argument("--output")
    pvsa.set_defaults(func="validation-session-artifact-check")
    pvsu = sub.add_parser("validation-session-acceptance")
    pvsu.add_argument("--manifest", default=str(MACOS_BUILD / "session" / "session-manifest.json"))
    pvsu.add_argument("--output")
    pvsu.set_defaults(func="validation-session-acceptance")
    pvsuc = sub.add_parser("validation-session-acceptance-contract")
    pvsuc.add_argument("--output")
    pvsuc.set_defaults(func="validation-session-acceptance-contract")
    pvss = sub.add_parser("validation-session-summary")
    pvss.add_argument("--manifest", default=str(MACOS_BUILD / "session" / "session-manifest.json"))
    pvss.add_argument("--output")
    pvss.set_defaults(func="validation-session-summary")
    pis = sub.add_parser("install-session")
    pis.add_argument("--status-tool")
    pis.add_argument("--install-tool")
    pis.add_argument("--list-devices-tool")
    pis.add_argument("--uninstall-tool")
    pis.add_argument("--sync-ipc-tool")
    pis.add_argument("--direct-push-demo-tool")
    pis.add_argument("--direct-push-frames", type=int)
    pis.add_argument("--direct-push-frame-kind")
    pis.add_argument("--direct-push-entrypoint")
    pis.add_argument("--direct-push-allow-shared-memory-fallback", action="store_true")
    pis.add_argument("--direct-push-request-camera-access", action="store_true")
    pis.add_argument("--direct-sender-object-demo-tool")
    pis.add_argument("--direct-sender-object-frames", type=int)
    pis.add_argument("--direct-sender-object-frame-kind")
    pis.add_argument("--direct-sender-object-request-camera-access", action="store_true")
    pis.add_argument("--pkg-path")
    pis.add_argument("--app-bundle")
    pis.add_argument("--app-executable")
    pis.add_argument("--host-bundle")
    pis.add_argument("--host-executable")
    pis.add_argument("--direct-sender-library")
    pis.add_argument("--installer-executable")
    pis.add_argument("--framebus-roundtrip-json")
    pis.add_argument("--disable-auto-package", action="store_true")
    pis.add_argument("--name", default="AK Virtual Camera")
    pis.add_argument("--run-uninstall", action="store_true")
    pis.add_argument("--run-direct-push-demo", action="store_true")
    pis.add_argument("--run-direct-sender-object-demo", action="store_true")
    pis.add_argument("--status-poll-attempts", type=int)
    pis.add_argument("--poll-interval-seconds", type=float)
    pis.add_argument("--output")
    pis.set_defaults(func="install-session")
    psr = sub.add_parser("sync-macos-runtime")
    psr.add_argument("--require-pkg", action="store_true",
                     help="fail if VirtualCamera.pkg is missing instead of syncing tools only")
    psr.set_defaults(func="sync-macos-runtime")
    sub.add_parser("run").set_defaults(func="run")
    sub.add_parser("test").set_defaults(func="test")
    pi = sub.add_parser("install-runtime")
    pi.add_argument("--prefix", help="installation prefix for staged runtime artifacts")
    pi.set_defaults(func="install_runtime")
    sub.add_parser("clean").set_defaults(func="clean")

    args = p.parse_args(argv)

    # Platform dispatch. Windows keeps the Phase 2/3 CMake flow; macOS uses
    # the Phase 4 xcodebuild flow. `run`/`test` are platform-agnostic.
    is_mac = sys.platform == "darwin"
    table = {
        "configure":  cmd_configure_macos if is_mac else cmd_configure,
        "build":      cmd_build_macos     if is_mac else cmd_build,
        "register":   cmd_register_macos  if is_mac else cmd_register,
        "unregister": cmd_unregister_macos if is_mac else cmd_unregister,
        "package":    cmd_package_macos   if is_mac else cmd_build,
        "sign":       cmd_sign_macos      if is_mac else cmd_register,
        "notarize":   cmd_notarize_macos  if is_mac else cmd_register,
        "staple":     cmd_staple_macos    if is_mac else cmd_register,
        "smoke":      cmd_smoke_macos     if is_mac else cmd_test,
        "direct-push-demo": cmd_direct_push_demo_macos if is_mac else cmd_test,
        "direct-sender-object-demo": cmd_direct_sender_object_demo_macos if is_mac else cmd_test,
        "preflight":  cmd_preflight_macos if is_mac else cmd_test,
        "release-diagnostics": cmd_release_diagnostics_macos if is_mac else cmd_test,
        "verify-native": cmd_verify_native_macos if is_mac else cmd_test,
        "benchmark":  cmd_benchmark_macos if is_mac else cmd_test,
        "framebus-roundtrip": cmd_framebus_roundtrip_macos if is_mac else cmd_test,
        "list-devices-binary-check": cmd_list_devices_binary_check_macos if is_mac else cmd_test,
        "validation-report": cmd_validation_report_macos if is_mac else cmd_test,
        "validation-session": cmd_validation_session_macos if is_mac else cmd_test,
        "validation-session-artifact-check": cmd_validation_session_artifact_check_macos if is_mac else cmd_test,
        "validation-session-acceptance": cmd_validation_session_acceptance_macos if is_mac else cmd_test,
        "validation-session-acceptance-contract": cmd_validation_session_acceptance_contract_macos if is_mac else cmd_test,
        "validation-session-summary": cmd_validation_session_summary_macos if is_mac else cmd_test,
        "install-session": cmd_install_session_macos if is_mac else cmd_test,
        "sync-macos-runtime": cmd_sync_macos_runtime if is_mac else cmd_test,
        "run":        cmd_run,
        "test":       cmd_test,
        "install_runtime": cmd_install_runtime,
        "clean":      cmd_clean,
    }
    return int(table[args.func](args))


if __name__ == "__main__":
    raise SystemExit(main())
