# SPDX-License-Identifier: Apache-2.0
"""Cross-language Frame Bus contract checks for macOS.

Validates that the shared C headers, POSIX consumer, and Python producer-side
protocol constants remain aligned around the same ABI surface.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_H = ROOT / "virtualcam" / "shared" / "akvc_protocol.h"
ERRORS_H = ROOT / "virtualcam" / "shared" / "akvc_errors.h"
FRAMEBUS_H = ROOT / "virtualcam" / "macos" / "ipc" / "include" / "akvc" / "framebus_posix.h"
FRAMEBUS_C = ROOT / "virtualcam" / "macos" / "ipc" / "src" / "framebus_posix.c"
MACOS_IPC_H = ROOT / "virtualcam" / "macos" / "ipc" / "include" / "akvc" / "macos_ipc.h"
MACOS_IPC_CPP = ROOT / "virtualcam" / "macos" / "ipc" / "src" / "macos_ipc.cpp"
HOST_COMMAND_SUPPORT_MM = ROOT / "virtualcam" / "macos" / "control_bridge" / "AKVCCommandSupport.mm"
INSTALL_TOOL_MM = ROOT / "virtualcam" / "macos" / "control_bridge" / "akvc_macos_install.mm"
DEMO_CONTROL_SERVICE_MM = ROOT / "virtualcam" / "macos" / "demo_app" / "DemoControlService.mm"
PY_PROTOCOL = ROOT / "camera-core" / "src" / "akvc" / "core" / "frame_sink" / "_protocol.py"
PY_MACOS_SHM = ROOT / "camera-core" / "src" / "akvc" / "core" / "frame_sink" / "macos_shm.py"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_define_int(text: str, name: str) -> int:
    match = re.search(rf"#define\s+{re.escape(name)}\s+(.+)", text)
    if match is None:
        raise ValueError(f"missing define: {name}")
    token = match.group(1).split("/*", 1)[0].strip()
    token = re.sub(r"(?<=\d)[uUlL]+", "", token)
    return _safe_eval_int_expr(token)


def _parse_define_string(text: str, name: str) -> str:
    match = re.search(rf'#define\s+{re.escape(name)}\s+"([^"]+)"', text)
    if match is None:
        raise ValueError(f"missing string define: {name}")
    return match.group(1)


def _safe_eval_int_expr(expr: str) -> int:
    node = ast.parse(expr, mode="eval")

    def _eval(value):
        if isinstance(value, ast.Expression):
            return _eval(value.body)
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            return int(value.value)
        if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.UAdd, ast.USub)):
            operand = _eval(value.operand)
            return operand if isinstance(value.op, ast.UAdd) else -operand
        if isinstance(value, ast.BinOp) and isinstance(value.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div, ast.Mod, ast.BitOr, ast.BitAnd, ast.LShift, ast.RShift)):
            left = _eval(value.left)
            right = _eval(value.right)
            if isinstance(value.op, ast.Add):
                return left + right
            if isinstance(value.op, ast.Sub):
                return left - right
            if isinstance(value.op, ast.Mult):
                return left * right
            if isinstance(value.op, ast.Div):
                return left // right
            if isinstance(value.op, ast.FloorDiv):
                return left // right
            if isinstance(value.op, ast.Mod):
                return left % right
            if isinstance(value.op, ast.BitOr):
                return left | right
            if isinstance(value.op, ast.BitAnd):
                return left & right
            if isinstance(value.op, ast.LShift):
                return left << right
            if isinstance(value.op, ast.RShift):
                return left >> right
        raise ValueError(f"unsupported integer expression: {expr}")

    return int(_eval(node))


def parse_c_protocol_contract() -> dict[str, Any]:
    protocol_text = _read_text(PROTOCOL_H)
    return {
        "magic": _parse_define_int(protocol_text, "AKVC_MAGIC"),
        "schema_version": _parse_define_int(protocol_text, "AKVC_SCHEMA_VERSION"),
        "ring_slots": _parse_define_int(protocol_text, "AKVC_RING_SLOTS"),
        "default_slot_size": _parse_define_int(protocol_text, "AKVC_DEFAULT_SLOT_SIZE"),
        "posix_shm_name": _parse_define_string(protocol_text, "AKVC_POSIX_SHM_NAME"),
        "heartbeat_timeout": _parse_define_int(protocol_text, "AKVC_HEARTBEAT_TIMEOUT"),
        "frame_header_size_comment": _parse_struct_size_comment(protocol_text, "Frame header"),
        "ring_control_size_comment": _parse_struct_size_comment(protocol_text, "Ring control block"),
    }


def _parse_struct_size_comment(text: str, label: str) -> int:
    match = re.search(rf"/\*\s*{re.escape(label)}\s*[—-]\s*(\d+)\s+bytes", text)
    if match is not None:
        return int(match.group(1))
    if label == "Ring control block":
        fallback = re.search(r"akvc_ring_control_t\s+\|\s+\(cacheline-aligned,\s*(\d+)\s+bytes\)", text)
        if fallback is not None:
            return int(fallback.group(1))
    raise ValueError(f"missing struct size comment for {label}")


def parse_error_codes() -> dict[str, int]:
    errors_text = _read_text(ERRORS_H)
    names = [
        "E_AKVC_FRAMEBUS_OPEN_FAILED",
        "E_AKVC_FRAMEBUS_SCHEMA_MISMATCH",
        "E_AKVC_FRAMEBUS_TIMEOUT",
        "E_AKVC_FRAMEBUS_TORN_FRAME",
        "E_AKVC_FRAMEBUS_NO_PRODUCER",
    ]
    return {name: _parse_define_int(errors_text, name) for name in names}


def parse_python_protocol_contract() -> dict[str, Any]:
    text = _read_text(PY_PROTOCOL)
    ring_fmt = _parse_python_string_constant(text, "RING_CONTROL_FMT")
    frame_fmt = _parse_python_string_constant(text, "FRAME_HEADER_FMT")
    ring_slots = _parse_python_int_constant(text, "AKVC_RING_SLOTS")
    default_slot_size = _parse_python_int_constant(text, "AKVC_DEFAULT_SLOT_SIZE")
    ring_control_size = struct.calcsize(ring_fmt)
    frame_header_size = struct.calcsize(frame_fmt)
    return {
        "magic": _parse_python_int_constant(text, "AKVC_MAGIC"),
        "schema_version": _parse_python_int_constant(text, "AKVC_SCHEMA_VERSION"),
        "ring_slots": ring_slots,
        "default_slot_size": default_slot_size,
        "posix_shm_name": _parse_python_string_constant(text, "AKVC_POSIX_SHM_NAME"),
        "ring_control_size": ring_control_size,
        "frame_header_size": frame_header_size,
        "region_size": ring_control_size + ring_slots * default_slot_size,
        "frame_header_off_seq_head": _parse_python_int_constant(text, "FRAME_HEADER_OFF_SEQ_HEAD"),
        "frame_header_off_seq_tail": _parse_python_int_constant(text, "FRAME_HEADER_OFF_SEQ_TAIL"),
        "off_producer_seq": _parse_python_int_constant(text, "OFF_PRODUCER_SEQ"),
        "off_producer_heartbeat": _parse_python_int_constant(text, "OFF_PRODUCER_HEARTBEAT"),
    }


def parse_python_macos_sink_contract() -> dict[str, Any]:
    text = _read_text(PY_MACOS_SHM)
    return {
        "shm_name": _parse_python_identifier_alias(text, "SHM_NAME", "AKVC_POSIX_SHM_NAME")
    }


def _parse_python_int_constant(text: str, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s*=\s*(.+)$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing Python int constant: {name}")
    return _safe_eval_int_expr(match.group(1).split("#", 1)[0].strip())


def _parse_python_string_constant(text: str, name: str) -> str:
    match = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing Python string constant: {name}")
    return match.group(1)


def _parse_python_identifier_alias(text: str, name: str, expected_identifier: str) -> str:
    match = re.search(rf"^{re.escape(name)}\s*=\s*{re.escape(expected_identifier)}\s*$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing Python identifier alias: {name} -> {expected_identifier}")
    protocol_text = _read_text(PY_PROTOCOL)
    return _parse_python_string_constant(protocol_text, expected_identifier)


def parse_native_usage(text: str) -> dict[str, Any]:
    return {
        "uses_timeout": "E_AKVC_FRAMEBUS_TIMEOUT" in text,
        "uses_torn_frame": "E_AKVC_FRAMEBUS_TORN_FRAME" in text,
        "uses_open_failed": "E_AKVC_FRAMEBUS_OPEN_FAILED" in text,
        "uses_schema_mismatch": "E_AKVC_FRAMEBUS_SCHEMA_MISMATCH" in text,
        "uses_magic_check": "AKVC_MAGIC" in text,
        "uses_schema_check": "AKVC_SCHEMA_VERSION" in text,
        "uses_slot_count_check": "AKVC_RING_SLOTS" in text,
        "uses_slot_size_check": "AKVC_DEFAULT_SLOT_SIZE" in text,
        "supports_named_open": "akvc_fb_open_named" in text
        and "const char* resolved_name = shm_name;" in text,
        "tracks_consumer_count": "__sync_add_and_fetch(consumer_count_ptr(c), 1U)" in text
        and "__sync_sub_and_fetch(count, 1U)" in text,
    }


def parse_macos_descriptor_contract(header_text: str, impl_text: str) -> dict[str, Any]:
    return {
        "exports_app_group_identifier_macro": '#define AKVC_MACOS_APP_GROUP_IDENTIFIER "group.com.sidus.amaran-desktop"' in header_text,
        "exports_shared_state_dir_env_macro": '#define AKVC_MACOS_SHARED_STATE_DIR_ENV "AKVC_MACOS_SHARED_STATE_DIR"' in header_text,
        "exports_shared_state_dir_suffix_macro": '#define AKVC_MACOS_SHARED_STATE_DIR_SUFFIX "Library/Group Containers/group.com.sidus.amaran-desktop/akvc-shared"' in header_text,
        "exports_shm_name_file_env_macro": '#define AKVC_MACOS_SHM_NAME_FILE_ENV "AKVC_MACOS_SHM_NAME_FILE"' in header_text,
        "exports_shm_name_file_name_macro": '#define AKVC_MACOS_SHM_NAME_FILE_NAME "akvc-macos-shm-name.txt"' in header_text,
        "exports_shm_name_env_macro": '#define AKVC_MACOS_SHM_NAME_ENV "AKVC_MACOS_SHM_NAME"' in header_text,
        "reads_shm_name_env_override": "std::getenv(AKVC_MACOS_SHM_NAME_ENV)" in impl_text,
        "reads_shm_name_file_env_override": "std::getenv(AKVC_MACOS_SHM_NAME_FILE_ENV)" in impl_text,
        "reads_shared_state_dir_env_override": "std::getenv(AKVC_MACOS_SHARED_STATE_DIR_ENV)" in impl_text,
        "builds_default_shared_state_path": 'AKVC_MACOS_SHARED_STATE_DIR_SUFFIX' in impl_text
        and "AKVC_MACOS_SHM_NAME_FILE_NAME" in impl_text,
        "falls_back_to_private_tmp_shared_state_dir": 'return std::string("/private/tmp/akvc-shared");' in impl_text,
        "reads_shm_name_from_file": "std::ifstream stream(path);" in impl_text
        and "std::getline(stream, line);" in impl_text,
        "falls_back_to_default_shm_name": "return AKVC_POSIX_SHM_NAME;" in impl_text,
        "validates_override_leading_slash": "candidate[0] != '/'" in impl_text,
        "validates_override_buffer_length": "std::strlen(candidate) < sizeof(((akvc_macos_ring_descriptor_t*)0)->shm_name)" in impl_text,
        "descriptor_uses_resolved_name": "std::strncpy(out_desc->shm_name, akvc_macos_resolved_shm_name()" in impl_text,
    }


def parse_host_persistence_contract(
    command_support_text: str,
    install_tool_text: str,
    demo_control_service_text: str,
) -> dict[str, Any]:
    install_path_persists_before_activation = (
        "AKVCPersistSharedMemoryNameOverrideFromEnvironment" in install_tool_text
        and "AKVCLaunchHostAgent(@[@\"--activate\"]" in install_tool_text
    )
    demo_app_submits_system_extension_request = "AKVCSubmitSystemExtensionRequest(" in demo_control_service_text
    return {
        "exports_persistence_function": "AKVCPersistSharedMemoryNameOverrideFromEnvironment" in command_support_text,
        "reads_host_shm_name_env": "AKVC_MACOS_SHM_NAME_ENV" in command_support_text,
        "reads_host_shm_name_file_env": "AKVC_MACOS_SHM_NAME_FILE_ENV" in command_support_text,
        "uses_default_shared_state_destination": "AKVCDefaultSharedMemoryNameOverridePath" in command_support_text,
        "creates_parent_directory": "createDirectoryAtPath:directoryPath" in command_support_text,
        "persists_utf8_newline_file": 'stringByAppendingString:@"\\n"' in command_support_text
        and "writeToFile:destinationPath" in command_support_text
        and "NSUTF8StringEncoding" in command_support_text,
        "activation_path_persists_before_request": (
            install_path_persists_before_activation
            and demo_app_submits_system_extension_request
        ),
    }


def evaluate_contract() -> dict[str, Any]:
    c_protocol = parse_c_protocol_contract()
    error_codes = parse_error_codes()
    python_protocol = parse_python_protocol_contract()
    python_macos_sink = parse_python_macos_sink_contract()
    framebus_h_text = _read_text(FRAMEBUS_H)
    framebus_c_text = _read_text(FRAMEBUS_C)
    macos_ipc_h_text = _read_text(MACOS_IPC_H)
    macos_ipc_cpp_text = _read_text(MACOS_IPC_CPP)
    host_command_support_text = _read_text(HOST_COMMAND_SUPPORT_MM)
    install_tool_text = _read_text(INSTALL_TOOL_MM)
    demo_control_service_text = _read_text(DEMO_CONTROL_SERVICE_MM)
    macos_descriptor = parse_macos_descriptor_contract(macos_ipc_h_text, macos_ipc_cpp_text)
    host_persistence = parse_host_persistence_contract(
        host_command_support_text,
        install_tool_text,
        demo_control_service_text,
    )

    consistency = {
        "magic_match": c_protocol["magic"] == python_protocol["magic"],
        "schema_version_match": c_protocol["schema_version"] == python_protocol["schema_version"],
        "ring_slots_match": c_protocol["ring_slots"] == python_protocol["ring_slots"],
        "default_slot_size_match": c_protocol["default_slot_size"] == python_protocol["default_slot_size"],
        "posix_shm_name_match": (
            c_protocol["posix_shm_name"] == python_protocol["posix_shm_name"] == python_macos_sink["shm_name"]
        ),
        "ring_control_size_match": c_protocol["ring_control_size_comment"] == python_protocol["ring_control_size"],
        "frame_header_size_match": c_protocol["frame_header_size_comment"] == python_protocol["frame_header_size"],
        "region_size_match": python_protocol["region_size"]
        == python_protocol["ring_control_size"] + python_protocol["ring_slots"] * python_protocol["default_slot_size"],
        "posix_consumer_checks_core_schema": all(parse_native_usage(framebus_c_text).values()),
        "posix_header_exports_core_api": all(
            symbol in framebus_h_text
            for symbol in (
                "akvc_fb_open",
                "akvc_fb_open_named",
                "akvc_fb_close",
                "akvc_fb_poll",
                "akvc_fb_producer_alive",
                "akvc_fb_consumer_count",
            )
        ),
        "framebus_core_error_codes_present": all(
            name in framebus_c_text
            for name in (
                "E_AKVC_FRAMEBUS_OPEN_FAILED",
                "E_AKVC_FRAMEBUS_SCHEMA_MISMATCH",
                "E_AKVC_FRAMEBUS_TIMEOUT",
                "E_AKVC_FRAMEBUS_TORN_FRAME",
            )
        ),
        "consumer_count_tracking_present": parse_native_usage(framebus_c_text)["tracks_consumer_count"],
        "macos_descriptor_env_override_present": all(bool(value) for value in macos_descriptor.values()),
        "host_persists_shm_override_before_activation": all(bool(value) for value in host_persistence.values()),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "c_protocol": c_protocol,
        "python_protocol": python_protocol,
        "python_macos_sink": python_macos_sink,
        "macos_descriptor": macos_descriptor,
        "host_persistence": host_persistence,
        "error_codes": error_codes,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS Frame Bus contract checker")
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
        print("macOS Frame Bus contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
