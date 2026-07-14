# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from shutil import copy2, rmtree
import subprocess
import sys

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.egg_info import egg_info as _egg_info
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel


ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent
BUILD_LIB_DIR = WORKSPACE_ROOT / "build" / "lib"
BUILD_PACKAGE_DIR = BUILD_LIB_DIR / "akvc"
LOCAL_BUILD_DIR = ROOT / "build"
LOCAL_BUILD_PACKAGE_DIR = LOCAL_BUILD_DIR / "lib" / "akvc"
PACKAGE_RUNTIME_DIR = BUILD_PACKAGE_DIR
PACKAGE_MACOS_RUNTIME_DIR = BUILD_PACKAGE_DIR
RUNTIME_STAGE_DIR = WORKSPACE_ROOT / ".akvc" / "package-runtime-build"
RUNTIME_STAGE_BIN_DIR = RUNTIME_STAGE_DIR / "bin"
BUILD_BIN_DIR = WORKSPACE_ROOT / "build" / "bin" / "Release"
DSHOW_BUILD_BIN_DIR = WORKSPACE_ROOT / "build" / "bin" / "dshow" / "Release"
RUNTIME_FILES = (
    "akvc_helper.exe",
    "akvc-mf.dll",
    "akvc-dshow.dll",
)
PYTHON_BINDING_ARTIFACT = "akvc_camera.pyd"
MACOS_RUNTIME_FILES = (
    "akvc-macos-status",
    "akvc-macos-install",
    "akvc-macos-uninstall",
    "akvc-macos-list-devices",
    "akvc-macos-sync-ipc",
    "libakvc-macos-direct-sender.dylib",
)


def _existing_runtime_sources() -> tuple[dict[str, Path], Path]:
    runtime_paths = {
        "akvc_helper.exe": BUILD_BIN_DIR / "akvc_helper.exe",
        "akvc-mf.dll": BUILD_BIN_DIR / "akvc-mf.dll",
        "akvc-dshow.dll": DSHOW_BUILD_BIN_DIR / "akvc-dshow.dll",
    }
    return runtime_paths, BUILD_BIN_DIR / PYTHON_BINDING_ARTIFACT


def remove_stale_compat_binaries(root: Path) -> None:
    for stale in root.glob("_core_native*.pyd"):
        stale.unlink(missing_ok=True)


def remove_stale_binding_binaries(root: Path) -> None:
    for stale in root.glob("akvc_camera*.pyd"):
        stale.unlink(missing_ok=True)


def remove_stale_runtime_dir(root: Path) -> None:
    runtime_dir = root / "_runtime"
    if runtime_dir.exists():
        rmtree(runtime_dir)


def sync_native_package_tree() -> None:
    if sys.platform == "darwin":
        remove_stale_runtime_dir(BUILD_PACKAGE_DIR)
        staged_runtime = RUNTIME_STAGE_DIR / "akvc"
        existing_runtime = WORKSPACE_ROOT / "build" / "macos" / "Build" / "Products" / "Release"
        existing_sources = {name: existing_runtime / name for name in MACOS_RUNTIME_FILES}
        if any(not path.is_file() for path in existing_sources.values()):
            subprocess.run(
                [sys.executable, "tools/make.py", "install-runtime", "--prefix", str(RUNTIME_STAGE_DIR)],
                cwd=WORKSPACE_ROOT,
                check=True,
            )
            existing_sources = {name: staged_runtime / name for name in MACOS_RUNTIME_FILES}
        PACKAGE_MACOS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        missing = []
        for name, src in existing_sources.items():
            if not src.is_file():
                missing.append(str(src))
                continue
            dst = PACKAGE_MACOS_RUNTIME_DIR / name
            copy2(src, dst)
            dst.chmod(0o755)
        if missing:
            raise FileNotFoundError("Missing AKVC macOS runtime artifacts: " + ", ".join(missing))
        return
    if sys.platform != "win32":
        return

    remove_stale_runtime_dir(BUILD_PACKAGE_DIR)

    runtime_paths, binding_src = _existing_runtime_sources()
    missing_runtime = [name for name in RUNTIME_FILES if not runtime_paths[name].is_file()]
    missing_binding = not binding_src.is_file()

    if missing_runtime or missing_binding:
        subprocess.run(
            [
                sys.executable,
                "tools/make.py",
                "install-runtime",
                "--prefix",
                str(RUNTIME_STAGE_DIR),
            ],
            cwd=WORKSPACE_ROOT,
            check=True,
        )
        runtime_paths = {name: RUNTIME_STAGE_BIN_DIR / name for name in RUNTIME_FILES}
        binding_src = BUILD_BIN_DIR / PYTHON_BINDING_ARTIFACT

    BUILD_PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    remove_stale_compat_binaries(BUILD_PACKAGE_DIR)
    remove_stale_binding_binaries(BUILD_LIB_DIR)
    if LOCAL_BUILD_PACKAGE_DIR.exists():
        remove_stale_compat_binaries(LOCAL_BUILD_PACKAGE_DIR)

    missing = []
    for name in RUNTIME_FILES:
        src = runtime_paths[name]
        if not src.is_file():
            missing.append(str(src))
            continue
        copy2(src, PACKAGE_RUNTIME_DIR / name)

    if not binding_src.is_file():
        missing.append(str(binding_src))
    else:
        copy2(binding_src, BUILD_PACKAGE_DIR / PYTHON_BINDING_ARTIFACT)

    if missing:
        raise FileNotFoundError(
            "Missing AKVC Windows runtime artifacts: " + ", ".join(missing)
        )


class egg_info(_egg_info):
    def run(self):
        sync_native_package_tree()
        super().run()


class build_py(_build_py):
    def run(self):
        sync_native_package_tree()
        build_package_dir = Path(self.build_lib) / "akvc"
        build_package_dir.mkdir(parents=True, exist_ok=True)
        remove_stale_runtime_dir(build_package_dir)
        remove_stale_compat_binaries(build_package_dir)
        super().run()
        remove_stale_runtime_dir(build_package_dir)
        remove_stale_compat_binaries(build_package_dir)


class bdist_wheel(_bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False


# `package-dir` points at the generated package tree.  Setuptools validates
# that directory while applying pyproject.toml, before any command's run()
# method is entered, so the tree must exist before setup() is called.
sync_native_package_tree()


setup(cmdclass={"egg_info": egg_info, "build_py": build_py, "bdist_wheel": bdist_wheel})
