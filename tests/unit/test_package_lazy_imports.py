# SPDX-License-Identifier: Apache-2.0
"""Package import tests that avoid forcing video dependencies."""

from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAMERA_CORE_SRC = ROOT / "camera-core" / "src"


def test_importing_top_level_akvc_does_not_force_numpy_or_cv2() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.sdk", None)
    sys.modules.pop("akvc.sdk.virtual_camera", None)

    module = importlib.import_module("akvc")

    assert module.__version__ == "0.2.0"
    assert "akvc.sdk.virtual_camera" not in sys.modules
    assert "akvc.platforms.macos.direct_sender" not in sys.modules


def test_importing_macos_installer_module_does_not_force_virtual_camera_dependencies() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.sdk", None)
    sys.modules.pop("akvc.sdk.virtual_camera", None)

    module = importlib.import_module("akvc.platforms.macos.installer")

    assert hasattr(module, "CommandMacInstallerService")
    assert "akvc.sdk.virtual_camera" not in sys.modules


def test_importing_macos_package_does_not_force_direct_sender_module() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.platforms", None)
    sys.modules.pop("akvc.platforms.macos", None)
    sys.modules.pop("akvc.platforms.macos.direct_sender", None)

    module = importlib.import_module("akvc.platforms.macos")

    assert hasattr(module, "DefaultMacInstallerService")
    assert "akvc.platforms.macos.direct_sender" not in sys.modules


def test_importing_sdk_package_does_not_force_macos_direct_sender_module() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.sdk", None)
    sys.modules.pop("akvc.platforms", None)
    sys.modules.pop("akvc.platforms.macos", None)
    sys.modules.pop("akvc.platforms.macos.direct_sender", None)

    module = importlib.import_module("akvc.sdk")

    assert hasattr(module, "VirtualCamera")
    assert "akvc.platforms.macos.direct_sender" not in sys.modules


def test_importing_top_level_akvc_exposes_direct_sender_lazy_exports() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.sdk", None)
    sys.modules.pop("akvc.platforms", None)
    sys.modules.pop("akvc.platforms.macos", None)
    sys.modules.pop("akvc.platforms.macos.direct_sender", None)

    module = importlib.import_module("akvc")

    assert "MacDirectCameraSender" in module.__all__
    assert "DirectSenderError" in module.__all__
    assert "create_direct_sender" in module.__all__
    assert "akvc.platforms.macos.direct_sender" not in sys.modules


def test_accessing_top_level_direct_sender_export_loads_only_macos_sender_module() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.sdk", None)
    sys.modules.pop("akvc.sdk.virtual_camera", None)
    sys.modules.pop("akvc.platforms", None)
    sys.modules.pop("akvc.platforms.macos", None)
    sys.modules.pop("akvc.platforms.macos.direct_sender", None)

    module = importlib.import_module("akvc")
    exported = module.MacDirectCameraSender

    assert exported.__name__ == "MacDirectCameraSender"
    assert "akvc.platforms.macos.direct_sender" in sys.modules
    assert "akvc.sdk.virtual_camera" not in sys.modules


def test_accessing_sdk_direct_sender_export_does_not_force_virtual_camera_module() -> None:
    sys.modules.pop("akvc", None)
    sys.modules.pop("akvc.sdk", None)
    sys.modules.pop("akvc.sdk.virtual_camera", None)
    sys.modules.pop("akvc.platforms", None)
    sys.modules.pop("akvc.platforms.macos", None)
    sys.modules.pop("akvc.platforms.macos.direct_sender", None)

    module = importlib.import_module("akvc.sdk")
    exported = module.MacDirectCameraSender

    assert exported.__name__ == "MacDirectCameraSender"
    assert "akvc.platforms.macos.direct_sender" in sys.modules
    assert "akvc.sdk.virtual_camera" not in sys.modules


def test_importing_sdk_virtual_camera_module_does_not_require_numpy_or_cv2() -> None:
    script = textwrap.dedent(
        """
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        module = importlib.import_module("akvc.sdk.virtual_camera")
        payload = {{
            "has_virtual_camera": hasattr(module, "VirtualCamera"),
            "frame_input_loaded": "akvc.core.frame_input" in sys.modules,
            "frame_pipeline_loaded": "akvc.core.frame_pipeline" in sys.modules,
            "numpy_loaded": "numpy" in sys.modules,
            "cv2_loaded": "cv2" in sys.modules,
        }}
        print(json.dumps(payload, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"cv2_loaded": false, "frame_input_loaded": false, '
        '"frame_pipeline_loaded": false, "has_virtual_camera": true, "numpy_loaded": false}'
    )


def test_importing_macos_virtual_camera_module_supports_status_path_without_numpy() -> None:
    script = textwrap.dedent(
        """
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        module = importlib.import_module("akvc.platforms.macos.virtual_camera")
        installer_mod = importlib.import_module("akvc.platforms.macos.installer")

        class FakeInstaller:
            def extension_state(self):
                return installer_mod.ExtensionInstallState.NOT_INSTALLED

            def install_extension(self):
                return False

            def enumerate_devices(self):
                return ["AK Virtual Camera"]

            def status(self):
                return installer_mod.ExtensionStatus(
                    state=installer_mod.ExtensionInstallState.NOT_INSTALLED,
                    devices=["AK Virtual Camera"],
                    enabled=False,
                )

        cam = module.MacVirtualCamera(installer=FakeInstaller())
        status = cam.status()
        readiness = cam.readiness()
        snapshot = cam.inspect_installation()
        payload = {{
            "devices": cam.enumerate_devices(),
            "installed": cam.is_installed(),
            "state": status.state.value,
            "readiness_blocker_code": readiness.blocker_code,
            "snapshot_devices": snapshot.devices,
            "frame_input_loaded": "akvc.core.frame_input" in sys.modules,
            "frame_pipeline_loaded": "akvc.core.frame_pipeline" in sys.modules,
            "numpy_loaded": "numpy" in sys.modules,
            "cv2_loaded": "cv2" in sys.modules,
        }}
        print(json.dumps(payload, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"cv2_loaded": false, "devices": ["AK Virtual Camera"], '
        '"frame_input_loaded": false, "frame_pipeline_loaded": false, '
        '"installed": false, "numpy_loaded": false, "readiness_blocker_code": "not_installed", '
        '"snapshot_devices": ["AK Virtual Camera"], "state": "not_installed"}'
    )


def test_importing_macos_ipc_module_does_not_require_numpy_or_cv2() -> None:
    script = textwrap.dedent(
        """
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        module = importlib.import_module("akvc.platforms.macos.ipc")
        payload = {{
            "has_descriptor": hasattr(module, "MacIPCDescriptor"),
            "has_capabilities": hasattr(module, "MacStreamCapabilities"),
            "frame_input_loaded": "akvc.core.frame_input" in sys.modules,
            "frame_pipeline_loaded": "akvc.core.frame_pipeline" in sys.modules,
            "numpy_loaded": "numpy" in sys.modules,
            "cv2_loaded": "cv2" in sys.modules,
        }}
        print(json.dumps(payload, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"cv2_loaded": false, "frame_input_loaded": false, '
        '"frame_pipeline_loaded": false, "has_capabilities": true, '
        '"has_descriptor": true, "numpy_loaded": false}'
    )


def test_instantiating_sdk_virtual_camera_on_darwin_does_not_require_numpy_until_frame_flow() -> None:
    script = textwrap.dedent(
        """
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        module = importlib.import_module("akvc.sdk.virtual_camera")
        module.sys.platform = "darwin"
        cam = module.VirtualCamera()
        payload = {{
            "has_backend": cam._mac_backend is not None,
            "frame_input_loaded": "akvc.core.frame_input" in sys.modules,
            "frame_pipeline_loaded": "akvc.core.frame_pipeline" in sys.modules,
            "numpy_loaded": "numpy" in sys.modules,
            "cv2_loaded": "cv2" in sys.modules,
        }}
        print(json.dumps(payload, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"cv2_loaded": false, "frame_input_loaded": false, '
        '"frame_pipeline_loaded": false, "has_backend": true, "numpy_loaded": false}'
    )


def test_importing_desktop_service_facade_supports_macos_install_status_without_numpy_or_cv2() -> None:
    desktop_src = ROOT / "apps" / "desktop"
    script = textwrap.dedent(
        """
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        sys.path.insert(0, r"{desktop_src}")
        module = importlib.import_module("akvc_app.services.facade")
        module.sys.platform = "darwin"
        installer_mod = importlib.import_module("akvc.platforms.macos.installer")

        class FakeMacCamera:
            def status(self):
                return installer_mod.ExtensionStatus(
                    state=installer_mod.ExtensionInstallState.NOT_INSTALLED,
                    enabled=False,
                )

            def enumerate_devices(self):
                return []

            def install_extension_result(self):
                return installer_mod.InstallExtensionResult(
                    success=False,
                    phase="",
                    state=installer_mod.ExtensionInstallState.NOT_INSTALLED,
                )

        module.VirtualCamera = lambda **kwargs: FakeMacCamera()
        module._list_usb_sources = lambda max_probe=4: []
        facade = module.ServiceFacade()
        status = facade.recheck_install_status()
        payload = {{
            "state": status.install_state,
            "phase": status.install_phase,
            "numpy_loaded": "numpy" in sys.modules,
            "cv2_loaded": "cv2" in sys.modules,
            "has_pattern_sources": len(facade._discover_sources()) >= 1,
        }}
        print(json.dumps(payload, sort_keys=True))
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC), desktop_src=str(desktop_src))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"cv2_loaded": false, "has_pattern_sources": true, '
        '"numpy_loaded": false, "phase": "", "state": "not_installed"}'
    )


def test_importing_frame_module_without_numpy_still_supports_metadata_only_paths() -> None:
    script = textwrap.dedent(
        """
        import builtins
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        orig_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "numpy" or name.startswith("numpy."):
                raise ModuleNotFoundError("blocked numpy for lazy-import test")
            return orig_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import
        try:
            module = importlib.import_module("akvc.core.frame")
            frame = module.Frame(
                width=2,
                height=2,
                fourcc=module.FourCC.NV12,
                data=b"\\x00" * 6,
                stride=(2, 2),
                plane_size=(4, 2),
            )
            payload = {{
                "has_frame": hasattr(module, "Frame"),
                "fourcc_name": module.FourCC.name(module.FourCC.NV12),
                "frame_width": frame.width,
                "numpy_loaded": "numpy" in sys.modules,
            }}
            print(json.dumps(payload, sort_keys=True))
        finally:
            builtins.__import__ = orig_import
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"fourcc_name": "NV12", "frame_width": 2, "has_frame": true, "numpy_loaded": false}'
    )


def test_importing_macos_roundtrip_path_without_numpy_succeeds() -> None:
    tool_path = ROOT / "tools" / "macos_framebus_roundtrip.py"
    script = textwrap.dedent(
        """
        import builtins
        import importlib
        import importlib.util
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        orig_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "numpy" or name.startswith("numpy."):
                raise ModuleNotFoundError("blocked numpy for lazy-import test")
            return orig_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import
        try:
            shm_module = importlib.import_module("akvc.core.frame_sink.macos_shm")
            spec = importlib.util.spec_from_file_location("akvc_macos_roundtrip_tool", r"{tool_path}")
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            payload = {{
                "has_sink": hasattr(shm_module, "MacOsShmSink"),
                "tool_loaded": hasattr(module, "evaluate_roundtrip"),
                "numpy_loaded": "numpy" in sys.modules,
            }}
            print(json.dumps(payload, sort_keys=True))
        finally:
            builtins.__import__ = orig_import
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC), tool_path=str(tool_path))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"has_sink": true, "numpy_loaded": false, "tool_loaded": true}'
    )


def test_coerce_frame_input_accepts_frame_instances_without_numpy() -> None:
    script = textwrap.dedent(
        """
        import builtins
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        orig_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "numpy" or name.startswith("numpy."):
                raise ModuleNotFoundError("blocked numpy for lazy-import test")
            return orig_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import
        try:
            frame_mod = importlib.import_module("akvc.core.frame")
            frame_input_mod = importlib.import_module("akvc.core.frame_input")
            frame = frame_mod.Frame.from_bgr_bytes(
                width=2,
                height=1,
                data=bytearray([1, 2, 3, 4, 5, 6]),
            )
            coerced = frame_input_mod.coerce_frame_input(frame)
            payload = {{
                "same_object": coerced is frame,
                "fourcc_name": frame_mod.FourCC.name(coerced.fourcc),
                "numpy_loaded": "numpy" in sys.modules,
            }}
            print(json.dumps(payload, sort_keys=True))
        finally:
            builtins.__import__ = orig_import
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"fourcc_name": "RGB24", "numpy_loaded": false, "same_object": true}'
    )


def test_coerce_direct_frame_input_accepts_qimage_like_bgra_without_numpy() -> None:
    script = textwrap.dedent(
        """
        import builtins
        import importlib
        import json
        import sys

        sys.path.insert(0, r"{camera_core_src}")
        orig_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "numpy" or name.startswith("numpy."):
                raise ModuleNotFoundError("blocked numpy for lazy-import test")
            return orig_import(name, globals, locals, fromlist, level)

        class FakeBits(bytearray):
            def setsize(self, size):
                self._size = size

            def asstring(self, size):
                return bytes(self[:size])

        class FakeQImage:
            class Format:
                Format_BGRA8888 = 1

            def width(self):
                return 1

            def height(self):
                return 1

            def bytesPerLine(self):
                return 4

            def format(self):
                return self.Format.Format_BGRA8888

            def constBits(self):
                return FakeBits(b"\\x01\\x02\\x03\\xff")

        builtins.__import__ = blocked_import
        try:
            frame_mod = importlib.import_module("akvc.core.frame")
            frame_input_mod = importlib.import_module("akvc.core.frame_input")
            coerced = frame_input_mod.coerce_direct_frame_input(FakeQImage())
            payload = {{
                "fourcc_name": frame_mod.FourCC.name(coerced.fourcc),
                "bytes": list(coerced.data[:4]),
                "numpy_loaded": "numpy" in sys.modules,
            }}
            print(json.dumps(payload, sort_keys=True))
        finally:
            builtins.__import__ = orig_import
        """
    ).format(camera_core_src=str(CAMERA_CORE_SRC))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"bytes": [1, 2, 3, 255], "fourcc_name": "BGRA32", "numpy_loaded": false}'
    )
