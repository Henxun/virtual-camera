# SPDX-License-Identifier: Apache-2.0
"""Python SDK contract checks for the macOS virtual camera path.

This checker keeps the macOS backend aligned with the existing cross-platform
`VirtualCamera` surface so the public Python API does not drift while native
Camera Extension work continues underneath.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_AKVC = ROOT / "akvc" / "__init__.py"
SDK_INIT = ROOT / "akvc" / "sdk" / "__init__.py"
SDK_VIRTUAL_CAMERA = ROOT / "camera-core" / "src" / "akvc" / "sdk" / "virtual_camera.py"
MACOS_VIRTUAL_CAMERA = ROOT / "camera-core" / "src" / "akvc" / "platforms" / "macos" / "virtual_camera.py"

EXPECTED_SHARED_METHODS = [
    "close",
    "create_pyside6_bridge",
    "create_latest_frame_provider",
    "create_pyside6_streamer",
    "direct_sender_readiness",
    "enumerate_devices",
    "inspect_installation",
    "ipc_descriptor",
    "install_extension",
    "install_extension_result",
    "is_installed",
    "push_frame",
    "readiness",
    "send",
    "send_image",
    "send_pixmap",
    "send_screen",
    "send_widget",
    "shutdown",
    "start",
    "status",
    "stop",
    "stream_capabilities",
    "sync_ipc_configuration",
    "sync_ipc_configuration_result",
    "uninstall_extension",
    "uninstall_extension_result",
]
EXPECTED_SHARED_PROPERTIES = [
    "consumer_count",
    "started",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_class(path: Path, class_name: str) -> ast.ClassDef:
    module = ast.parse(_read_text(path), filename=str(path))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise ValueError(f"class not found: {class_name} in {path}")


def _parse_literal___all__(path: Path) -> list[str]:
    module = ast.parse(_read_text(path), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    names: list[str] = []
                    for item in node.value.elts:
                        if isinstance(item, ast.Constant) and isinstance(item.value, str):
                            names.append(item.value)
                    return names
    raise ValueError(f"__all__ not found in {path}")


def _parse_public_surface(path: Path, class_name: str) -> dict[str, Any]:
    cls = _parse_class(path, class_name)
    methods: dict[str, list[str]] = {}
    properties: list[str] = []
    allowed_dunders = {"__init__", "__enter__", "__exit__"}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list and any(
                isinstance(decorator, ast.Name) and decorator.id == "property"
                for decorator in node.decorator_list
            ):
                if not node.name.startswith("_"):
                    properties.append(node.name)
                continue

            if node.name.startswith("_") and node.name not in allowed_dunders:
                continue
            methods[node.name] = _function_signature(node)
    return {
        "methods": methods,
        "properties": sorted(properties),
    }


def _function_signature(node: ast.FunctionDef) -> list[str]:
    args = []
    for argument in node.args.args:
        if argument.arg != "self":
            args.append(argument.arg)
    if node.args.vararg is not None:
        args.append(f"*{node.args.vararg.arg}")
    for argument in node.args.kwonlyargs:
        args.append(argument.arg)
    if node.args.kwarg is not None:
        args.append(f"**{node.args.kwarg.arg}")
    return args


def evaluate_contract() -> dict[str, Any]:
    top_level_all = _parse_literal___all__(TOP_LEVEL_AKVC)
    sdk_init_all = _parse_literal___all__(SDK_INIT)
    virtual_camera = _parse_public_surface(SDK_VIRTUAL_CAMERA, "VirtualCamera")
    mac_virtual_camera = _parse_public_surface(MACOS_VIRTUAL_CAMERA, "MacVirtualCamera")

    virtual_shared = sorted(name for name in EXPECTED_SHARED_METHODS if name in virtual_camera["methods"])
    mac_shared = sorted(name for name in EXPECTED_SHARED_METHODS if name in mac_virtual_camera["methods"])
    virtual_properties = sorted(name for name in EXPECTED_SHARED_PROPERTIES if name in virtual_camera["properties"])
    mac_properties = sorted(name for name in EXPECTED_SHARED_PROPERTIES if name in mac_virtual_camera["properties"])

    consistency = {
        "shared_lifecycle_methods_complete": all(
            name in virtual_camera["methods"] and name in mac_virtual_camera["methods"]
            for name in ("start", "push_frame", "send", "stop", "close", "shutdown")
        ),
        "shared_pyside6_methods_complete": all(
            name in virtual_camera["methods"] and name in mac_virtual_camera["methods"]
            for name in (
                "create_pyside6_bridge",
                "send_image",
                "send_pixmap",
                "send_widget",
                "send_screen",
                "create_latest_frame_provider",
                "create_pyside6_streamer",
            )
        ),
        "shared_installer_methods_complete": all(
            name in virtual_camera["methods"] and name in mac_virtual_camera["methods"]
            for name in (
                "enumerate_devices",
                "direct_sender_readiness",
                "status",
                "readiness",
                "inspect_installation",
                "ipc_descriptor",
                "stream_capabilities",
                "is_installed",
                "install_extension_result",
                "install_extension",
                "uninstall_extension_result",
                "uninstall_extension",
                "sync_ipc_configuration_result",
                "sync_ipc_configuration",
            )
        ),
        "shared_properties_complete": virtual_properties == EXPECTED_SHARED_PROPERTIES
        and mac_properties == EXPECTED_SHARED_PROPERTIES,
        "start_signature_match": virtual_camera["methods"].get("start") == mac_virtual_camera["methods"].get("start") == ["name"],
        "push_frame_signature_match": virtual_camera["methods"].get("push_frame")
        == mac_virtual_camera["methods"].get("push_frame")
        == ["frame_input"],
        "send_signature_match": virtual_camera["methods"].get("send") == mac_virtual_camera["methods"].get("send") == ["frame_input"],
        "send_image_signature_match": virtual_camera["methods"].get("send_image")
        == mac_virtual_camera["methods"].get("send_image")
        == ["image"],
        "send_pixmap_signature_match": virtual_camera["methods"].get("send_pixmap")
        == mac_virtual_camera["methods"].get("send_pixmap")
        == ["pixmap"],
        "send_widget_signature_match": virtual_camera["methods"].get("send_widget")
        == mac_virtual_camera["methods"].get("send_widget")
        == ["widget"],
        "send_screen_signature_match": virtual_camera["methods"].get("send_screen")
        == mac_virtual_camera["methods"].get("send_screen")
        == ["screen", "window", "x", "y", "width", "height"],
        "create_latest_frame_provider_signature_match": virtual_camera["methods"].get("create_latest_frame_provider")
        == mac_virtual_camera["methods"].get("create_latest_frame_provider")
        == ["repeat_last"],
        "create_pyside6_bridge_signature_match": virtual_camera["methods"].get("create_pyside6_bridge")
        == mac_virtual_camera["methods"].get("create_pyside6_bridge")
        == [],
        "create_pyside6_streamer_signature_match": virtual_camera["methods"].get("create_pyside6_streamer")
        == mac_virtual_camera["methods"].get("create_pyside6_streamer")
        == ["timer_factory"],
        "enumerate_devices_signature_match": virtual_camera["methods"].get("enumerate_devices")
        == mac_virtual_camera["methods"].get("enumerate_devices")
        == [],
        "direct_sender_readiness_signature_match": virtual_camera["methods"].get("direct_sender_readiness")
        == mac_virtual_camera["methods"].get("direct_sender_readiness")
        == ["name", "request_camera_access"],
        "status_signature_match": virtual_camera["methods"].get("status")
        == mac_virtual_camera["methods"].get("status")
        == [],
        "readiness_signature_match": virtual_camera["methods"].get("readiness") == mac_virtual_camera["methods"].get("readiness") == [],
        "inspect_installation_signature_match": virtual_camera["methods"].get("inspect_installation")
        == mac_virtual_camera["methods"].get("inspect_installation")
        == [],
        "ipc_descriptor_signature_match": virtual_camera["methods"].get("ipc_descriptor")
        == mac_virtual_camera["methods"].get("ipc_descriptor")
        == [],
        "stream_capabilities_signature_match": virtual_camera["methods"].get("stream_capabilities")
        == mac_virtual_camera["methods"].get("stream_capabilities")
        == [],
        "is_installed_signature_match": virtual_camera["methods"].get("is_installed")
        == mac_virtual_camera["methods"].get("is_installed")
        == [],
        "install_extension_result_signature_match": virtual_camera["methods"].get("install_extension_result")
        == mac_virtual_camera["methods"].get("install_extension_result")
        == [],
        "install_extension_signature_match": virtual_camera["methods"].get("install_extension")
        == mac_virtual_camera["methods"].get("install_extension")
        == [],
        "uninstall_extension_result_signature_match": virtual_camera["methods"].get("uninstall_extension_result")
        == mac_virtual_camera["methods"].get("uninstall_extension_result")
        == [],
        "uninstall_extension_signature_match": virtual_camera["methods"].get("uninstall_extension")
        == mac_virtual_camera["methods"].get("uninstall_extension")
        == [],
        "sync_ipc_configuration_signature_match": virtual_camera["methods"].get("sync_ipc_configuration")
        == mac_virtual_camera["methods"].get("sync_ipc_configuration")
        == ["shared_memory_name"],
        "sync_ipc_configuration_result_signature_match": virtual_camera["methods"].get("sync_ipc_configuration_result")
        == mac_virtual_camera["methods"].get("sync_ipc_configuration_result")
        == ["shared_memory_name"],
        "constructor_shape_aligned": all(
            name in mac_virtual_camera["methods"].get("__init__", [])
            and name in virtual_camera["methods"].get("__init__", [])
            for name in (
                "width",
                "height",
                "fps",
                "direct_only",
                "helper_exe",
                "host_bundle",
                "host_executable",
                "direct_sender_library",
                "pipeline",
            )
        ),
        "direct_sender_exports_present": all(
            name in top_level_all and name in sdk_init_all
            for name in (
                "MacDirectCameraSender",
                "DirectSenderError",
                "create_direct_sender",
            )
        ),
        "context_manager_complete": "__enter__" in virtual_camera["methods"]
        and "__exit__" in virtual_camera["methods"]
        and "__enter__" in mac_virtual_camera["methods"]
        and "__exit__" in mac_virtual_camera["methods"],
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "top_level_akvc": {
            "__all__": top_level_all,
        },
        "sdk_init": {
            "__all__": sdk_init_all,
        },
        "virtual_camera": {
            "shared_methods": virtual_shared,
            "shared_properties": virtual_properties,
            "method_signatures": {name: virtual_camera["methods"][name] for name in sorted(virtual_camera["methods"])},
        },
        "mac_virtual_camera": {
            "shared_methods": mac_shared,
            "shared_properties": mac_properties,
            "method_signatures": {name: mac_virtual_camera["methods"][name] for name in sorted(mac_virtual_camera["methods"])},
        },
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS Python SDK contract checker")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = evaluate_contract()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    if not bool(payload["consistency"]["all_checks_passed"]):
        print("macOS Python SDK contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
