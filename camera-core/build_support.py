# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import os

import numpy
from pybind11.setup_helpers import Pybind11Extension, build_ext


CAMERA_CORE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = CAMERA_CORE_ROOT.parent
FRAMEBUS_ROOT = REPO_ROOT / "virtualcam" / "windows" / "framebus"
SHARED_ROOT = REPO_ROOT / "virtualcam" / "shared"


class AkvcBuildExt(build_ext):
    def build_extensions(self) -> None:
        ct = self.compiler.compiler_type
        for ext in self.extensions:
            if ct == "msvc":
                ext.extra_compile_args = list(ext.extra_compile_args or []) + ["/EHsc"]
            else:
                ext.extra_compile_args = list(ext.extra_compile_args or []) + ["-fvisibility=hidden"]
        super().build_extensions()


def _relpath(path: Path, base: Path) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def akvc_native_extensions(base_dir: str | Path | None = None) -> list[Pybind11Extension]:
    base = Path(base_dir) if base_dir is not None else CAMERA_CORE_ROOT
    return [
        Pybind11Extension(
            "akvc._core_native",
            [
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "module.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "frame_types.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "pipeline_ops.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "providers" / "test_pattern_provider.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "providers" / "usb_provider.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "sinks" / "windows_framebus.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "sinks" / "macos_shm_sink.cpp", base),
                _relpath(CAMERA_CORE_ROOT / "native" / "src" / "helper" / "windows_helper_client.cpp", base),
                _relpath(FRAMEBUS_ROOT / "src" / "framebus.cpp", base),
                _relpath(FRAMEBUS_ROOT / "src" / "sddl_helper.cpp", base),
            ],
            include_dirs=[
                numpy.get_include(),
                _relpath(CAMERA_CORE_ROOT / "native" / "include", base),
                _relpath(FRAMEBUS_ROOT / "include", base),
                _relpath(SHARED_ROOT, base),
            ],
            libraries=["Advapi32", "Shell32"],
            cxx_std=17,
        )
    ]
