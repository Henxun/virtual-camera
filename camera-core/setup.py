# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path

from setuptools import setup


CAMERA_CORE_ROOT = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
BUILD_SUPPORT = CAMERA_CORE_ROOT / "build_support.py"

_spec = importlib.util.spec_from_file_location("akvc_camera_core_build_support", BUILD_SUPPORT)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"failed to load build support from {BUILD_SUPPORT}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

AkvcBuildExt = _module.AkvcBuildExt
akvc_native_extensions = _module.akvc_native_extensions


setup(
    cmdclass={"build_ext": AkvcBuildExt},
    ext_modules=akvc_native_extensions(CAMERA_CORE_ROOT),
)
