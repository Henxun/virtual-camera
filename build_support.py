# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
CAMERA_CORE_BUILD_SUPPORT = REPO_ROOT / "camera-core" / "build_support.py"

_spec = importlib.util.spec_from_file_location("akvc_camera_core_build_support", CAMERA_CORE_BUILD_SUPPORT)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"failed to load camera-core build support from {CAMERA_CORE_BUILD_SUPPORT}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

AkvcBuildExt = _module.AkvcBuildExt


def akvc_native_extensions():
    return _module.akvc_native_extensions(REPO_ROOT)
