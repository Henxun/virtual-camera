from __future__ import annotations

import importlib
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


class _FakeBackend:
    def __init__(self) -> None:
        self.calls = []

    def build_wheel(self, wheel_directory, config_settings=None, metadata_directory=None):
        self.calls.append((Path.cwd(), wheel_directory, config_settings, metadata_directory))
        return "akvc_core-0.2.0-py3-none-any.whl"


def test_root_build_backend_delegates_wheel_build_from_camera_core(monkeypatch, tmp_path):
    backend = importlib.import_module("akvc_root_build_backend")
    fake = _FakeBackend()
    monkeypatch.setattr(backend, "_setuptools_backend", fake)

    result = backend.build_wheel(str(tmp_path), {"flag": "value"}, "metadata")

    assert result == "akvc_core-0.2.0-py3-none-any.whl"
    assert fake.calls == [
        (ROOT / "camera-core", str(tmp_path), {"flag": "value"}, "metadata"),
    ]


def test_root_pyproject_uses_forwarding_backend():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    camera_core_text = (ROOT / "camera-core" / "pyproject.toml").read_text(encoding="utf-8")
    root_config = tomllib.loads(text)

    assert 'build-backend = "akvc_root_build_backend"' in text
    assert 'backend-path = ["."]' in text
    assert 'name = "akvc-core"' in text
    assert 'name = "akvc-core"' in camera_core_text
    assert root_config["project"]["dependencies"] == [
        "numpy>=1.26,<3.0",
        "opencv-python-headless>=4.9,<5.0",
        "pydantic>=2.5,<3.0",
    ]
