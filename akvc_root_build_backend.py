from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path

_CAMERA_CORE_DIR = Path(__file__).resolve().parent / "camera-core"
_setuptools_backend = None


def _backend():
    global _setuptools_backend
    if _setuptools_backend is None:
        from setuptools import build_meta

        _setuptools_backend = build_meta
    return _setuptools_backend


@contextmanager
def _camera_core_working_directory():
    previous = Path.cwd()
    os.chdir(_CAMERA_CORE_DIR)
    try:
        yield
    finally:
        os.chdir(previous)


def _delegate(hook: str, *args, **kwargs):
    with _camera_core_working_directory():
        return getattr(_backend(), hook)(*args, **kwargs)


def get_requires_for_build_wheel(config_settings=None):
    return _delegate("get_requires_for_build_wheel", config_settings)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    return _delegate("prepare_metadata_for_build_wheel", metadata_directory, config_settings)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _delegate("build_wheel", wheel_directory, config_settings, metadata_directory)


def get_requires_for_build_sdist(config_settings=None):
    return _delegate("get_requires_for_build_sdist", config_settings)


def build_sdist(sdist_directory, config_settings=None):
    return _delegate("build_sdist", sdist_directory, config_settings)


def get_requires_for_build_editable(config_settings=None):
    return _delegate("get_requires_for_build_editable", config_settings)


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return _delegate("prepare_metadata_for_build_editable", metadata_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _delegate("build_editable", wheel_directory, config_settings, metadata_directory)
