from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_camera_core_package_data_includes_macos_python_binding():
    pyproject = (ROOT / 'camera-core' / 'pyproject.toml').read_text(encoding='utf-8')

    assert '"akvc_camera*.so"' in pyproject


def test_camera_core_source_install_builds_current_arch_macos_python_binding():
    setup_source = (ROOT / 'camera-core' / 'setup.py').read_text(encoding='utf-8')

    assert 'platform.machine()' in setup_source
    assert 'CMAKE_OSX_ARCHITECTURES' in setup_source
    assert 'akvc_camera_python' in setup_source
    assert 'glob("akvc_camera*.so")' in setup_source
    assert 'copy2(binding_src, BUILD_PACKAGE_DIR / binding_src.name)' in setup_source
