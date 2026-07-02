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
MACOS_EXT_BUNDLE = MACOS_BUILD / "Build" / "Products" / "Release" / "akvc-camera-extension.systemextension"


def _cmake_args(source: Path, build: Path) -> list[str]:
    args = ["cmake", "-G", CMAKE_GENERATOR]
    # The -A option is only valid for Visual Studio generators.
    if CMAKE_GENERATOR.startswith("Visual Studio"):
        args += ["-A", CMAKE_PLATFORM]
    args += ["-S", str(source), "-B", str(build)]
    return args


def _build_env() -> dict[str, str] | None:
    return _VCVARS_ENV


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> int:
    print(f"[make] $ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(cwd) if cwd else None, env=env)


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
    if not cache.exists():
        return
    try:
        for line in cache.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("CMAKE_GENERATOR:INTERNAL="):
                existing = line.split("=", 1)[1].strip()
                if existing and existing != CMAKE_GENERATOR:
                    print(
                        f"[make] purging stale CMake cache "
                        f"(was '{existing}', now '{CMAKE_GENERATOR}'): {build_dir}"
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
    return _run(_cmake_args(ROOT, BUILD), env=_build_env())


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


def cmd_configure_macos(_: argparse.Namespace) -> int:
    _check_macos()
    xcodegen = _require_tool("xcodegen")
    _require_tool("xcodebuild")
    MACOS_BUILD.mkdir(parents=True, exist_ok=True)
    # Generate the .xcodeproj from project.yml. The generated project lives
    # next to project.yml (in virtualcam/macos/).
    return _run([xcodegen, "generate", "--spec", str(MACOS_PROJECT_YML)],
                cwd=MACOS_ROOT)


def cmd_build_macos(args: argparse.Namespace) -> int:
    _check_macos()
    _require_tool("xcodebuild")
    proj = MACOS_ROOT / "akvc-macos.xcodeproj"
    if not proj.is_dir():
        rc = cmd_configure_macos(args)
        if rc != 0:
            return rc
    # Build the Camera Extension system-extension target. The scheme name
    # is defined in project.yml; "akvc-camera-extension" is the extension
    # target, "akvc-host" the host app.
    rc = _run([
        "xcodebuild", "-project", str(proj),
        "-scheme", "akvc-camera-extension",
        "-configuration", "Release",
        "-derivedDataPath", str(MACOS_BUILD),
        "build",
    ])
    if rc != 0:
        return rc
    print(f"[make] Camera Extension bundle: {MACOS_EXT_BUNDLE}")
    print("[make] NOTE: signing + notarization required before it will load "
          "on a non-debug Mac. See docs/phase4/signing-notarization.md.")
    if args.python:
        _run([sys.executable, "-m", "pip", "install", "-e",
              str(ROOT / "camera-core")])
        _run([sys.executable, "-m", "pip", "install", "-e",
              str(ROOT / "apps" / "desktop")])
        _run([sys.executable, "-m", "pip", "install", "-e",
              str(ROOT / "apps" / "cli")])
    return 0


def cmd_register_macos(_: argparse.Namespace) -> int:
    _check_macos()
    # The Apple-blessed way to install a Camera Extension is to run the host
    # app, which triggers an OSSystemExtensionRequest that the user must
    # approve. systemextensionsctl is a developer-only escape hatch.
    print(
        "[make] macOS Camera Extension registration is interactive:\n"
        "  1. Build & sign the host app (cmd_build_macos + signing runbook).\n"
        "  2. Launch the host app — it posts OSSystemExtensionRequest.\n"
        "  3. Approve the system-extension prompt in System Settings.\n"
        "  4. Enable the camera in System Settings > Privacy > Camera.\n"
        "For dev-only sideloading you can also run:\n"
        "  systemextensionsctl developer on   # one-time\n"
        "  systemextensionsctl install <team> akvc-camera-extension"
    )
    return 0


def cmd_unregister_macos(_: argparse.Namespace) -> int:
    _check_macos()
    print(
        "[make] To uninstall the Camera Extension:\n"
        "  systemextensionsctl uninstall <team-id> akvc-camera-extension\n"
        "or delete it via System Settings > Extensions."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="make.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("configure").set_defaults(func="configure")
    pb = sub.add_parser("build")
    pb.add_argument("--python", action="store_true",
                    help="also pip install -e the Python packages")
    pb.set_defaults(func="build")
    sub.add_parser("register").set_defaults(func="register")
    sub.add_parser("unregister").set_defaults(func="unregister")
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
        "run":        cmd_run,
        "test":       cmd_test,
        "install_runtime": cmd_install_runtime,
        "clean":      cmd_clean,
    }
    return int(table[args.func](args))


if __name__ == "__main__":
    raise SystemExit(main())
