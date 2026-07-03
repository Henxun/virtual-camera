# SPDX-License-Identifier: Apache-2.0
"""Consistency checks for the macOS Camera Extension topology contract.

This helper keeps the Provider / Device / Stream assembly graph aligned around
the same identity defaults, property surface, IPC wiring, and CMIO registration
sequence so a native refactor does not silently break device visibility.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROVIDER_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCProviderSource.h"
PROVIDER_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCProviderSource.mm"
DEVICE_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCDeviceSource.h"
DEVICE_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCDeviceSource.mm"
STREAM_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCStreamSource.h"
STREAM_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCStreamSource.mm"
SINK_STREAM_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCSinkStreamSource.h"
SINK_STREAM_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCSinkStreamSource.mm"
FRAME_PROVIDER_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCFrameProvider.h"
FRAME_PROVIDER_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCFrameProvider.mm"

CAMERA_EXTENSION_HOT_PATH_SOURCES = [
    PROVIDER_H,
    PROVIDER_MM,
    DEVICE_H,
    DEVICE_MM,
    STREAM_H,
    STREAM_MM,
    SINK_STREAM_H,
    SINK_STREAM_MM,
    FRAME_PROVIDER_H,
    FRAME_PROVIDER_MM,
]
HOST_ACTIVATION_TOKENS = [
    "AKVCLaunchHostAgent",
    "AKVCSystemExtensionSupport",
    "OSSystemExtensionRequest",
    "SystemExtensions.framework",
    "systemextensionsctl",
    "virtualcam/macos/host",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_extension_hot_path_contract(source_text_by_path: dict[str, str]) -> dict[str, Any]:
    forbidden_hits = {
        path: sorted(token for token in HOST_ACTIVATION_TOKENS if token in text)
        for path, text in source_text_by_path.items()
    }
    forbidden_hits = {path: hits for path, hits in forbidden_hits.items() if hits}
    combined_text = "\n".join(source_text_by_path.values())
    return {
        "reads_framebus_directly": "akvc/framebus_posix.h" in combined_text,
        "reads_descriptor_directly": "akvc/macos_ipc.h" in combined_text,
        "does_not_launch_host_agent": "AKVCLaunchHostAgent" not in combined_text,
        "does_not_submit_system_extension_requests": "OSSystemExtensionRequest" not in combined_text,
        "does_not_import_host_activation_support": "AKVCSystemExtensionSupport" not in combined_text
        and "virtualcam/macos/host" not in combined_text,
        "forbidden_hits": forbidden_hits,
    }


def _extract_method(text: str, method_name: str) -> str:
    match = re.search(rf"-\s*\([^)]*\){re.escape(method_name)}[^{{]*\{{", text)
    if match is None:
        return ""
    index = match.end() - 1
    depth = 0
    for pos in range(index, len(text)):
        char = text[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[match.start():pos + 1]
    return text[match.start():]


def _parse_string_constant(text: str, name: str) -> str | None:
    match = re.search(rf"{re.escape(name)}\s*=\s*@\"([^\"]+)\";", text)
    return match.group(1) if match else None


def _parse_property_list(text: str, start_marker: str, end_marker: str) -> list[str]:
    start = text.find(start_marker)
    if start < 0:
        return []
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        return []
    block = text[start:end]
    return sorted(set(re.findall(r"CMIOExtensionProperty[A-Za-z]+", block)))


def _parse_property_guards(text: str, method_name: str) -> list[str]:
    method = _extract_method(text, method_name)
    return sorted(set(re.findall(r"\[properties containsObject:(CMIOExtensionProperty[A-Za-z]+)\]", method)))


def _parse_device_property_value(text: str, property_name: str) -> bool | None:
    match = re.search(
        rf"propertyStateWithValue:@(YES|NO)\]\s*forProperty:{re.escape(property_name)}",
        text,
    )
    if match is None:
        return None
    return match.group(1) == "YES"


def _is_valid_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def parse_provider_contract(header_text: str, impl_text: str) -> dict[str, Any]:
    bootstrap = _extract_method(impl_text, "bootstrapProviderGraph")

    return {
        "conforms_provider_protocol": "CMIOExtensionProviderSource" in header_text,
        "default_provider_name": _parse_string_constant(impl_text, "AKVCDefaultProviderName"),
        "default_manufacturer": _parse_string_constant(impl_text, "AKVCDefaultManufacturer"),
        "default_legacy_device_id": _parse_string_constant(impl_text, "AKVCDefaultLegacyDeviceID"),
        "default_device_uuid": _parse_string_constant(impl_text, "AKVCDefaultDeviceUUIDString"),
        "default_source_stream_uuid": _parse_string_constant(impl_text, "AKVCDefaultSourceStreamUUIDString"),
        "default_sink_stream_uuid": _parse_string_constant(impl_text, "AKVCDefaultSinkStreamUUIDString"),
        "available_properties": _parse_property_list(
            impl_text,
            "_availableProperties = [NSSet setWithArray:@[",
            "]];",
        ),
        "readable_properties": _parse_property_guards(impl_text, "providerPropertiesForProperties"),
        "uses_default_ring_descriptor": "akvc_macos_ring_descriptor_default(&descriptor);" in impl_text,
        "frame_provider_uses_shared_memory_name": '[NSString stringWithUTF8String:descriptor.shm_name]' in impl_text,
        "frame_provider_uses_slot_count": "slotCount:descriptor.slot_count" in impl_text,
        "frame_provider_uses_slot_size": "slotSize:descriptor.slot_size" in impl_text,
        "default_ctor_builds_frame_provider": "[[AKVCFrameProvider alloc]" in impl_text,
        "default_ctor_builds_source_stream_source": "[[AKVCStreamSource alloc] initWithFrameProvider:frameProvider]" in impl_text,
        "default_ctor_builds_sink_stream_source": "[[AKVCSinkStreamSource alloc] initWithFrameProvider:frameProvider]" in impl_text,
        "default_ctor_builds_device_source": "[[AKVCDeviceSource alloc]" in impl_text,
        "supports_runtime_device_name_override": "akvc_macos_resolved_device_name()" in impl_text
        and "configuredDeviceName" in impl_text,
        "source_stream_localized_name": _parse_stream_localized_name(bootstrap, "sourceStream"),
        "sink_stream_localized_name": _parse_stream_localized_name(bootstrap, "sinkStream"),
        "stream_directions": _parse_stream_tokens(bootstrap, "direction"),
        "stream_clock_types": _parse_stream_tokens(bootstrap, "clockType"),
        "attaches_source_stream_to_stream_source": "[self.streamSource attachStream:self.sourceStream];" in bootstrap,
        "attaches_sink_stream_to_stream_source": "[self.sinkStreamSource attachStream:self.sinkStream];" in bootstrap,
        "device_uses_source_localized_name": "deviceWithLocalizedName:self.deviceSource.localizedName" in bootstrap,
        "device_uses_source_device_id": "deviceID:self.deviceSource.deviceID" in bootstrap,
        "device_uses_source_legacy_id": "legacyDeviceID:self.deviceSource.legacyDeviceID" in bootstrap,
        "adds_source_stream_to_device": "[self.device addStream:self.sourceStream error:&error]" in bootstrap,
        "adds_sink_stream_to_device": "[self.device addStream:self.sinkStream error:&error]" in bootstrap,
        "adds_device_to_provider": "[self.provider addDevice:self.device error:&error]" in bootstrap,
        "starts_provider_service": "[CMIOExtensionProvider startServiceWithProvider:self.provider];" in bootstrap,
        "logs_stream_add_failure": "AKVC failed to add CMIOExtensionStream" in bootstrap,
        "logs_device_add_failure": "AKVC failed to add CMIOExtensionDevice" in bootstrap,
        "provider_factory_uses_client_queue": "[CMIOExtensionProvider providerWithSource:self clientQueue:self.clientQueue]" in bootstrap,
        "provider_properties_read_only": "provider properties are read-only in the current macOS MVP" in impl_text,
        "retains_device_stream_graph": "_streamSource = deviceSource.sourceStreamSource;" in impl_text
        and "_sinkStreamSource = deviceSource.sinkStreamSource;" in impl_text
        and "_frameProvider = deviceSource.sourceStreamSource.frameProvider;" in impl_text,
    }


def _parse_stream_tokens(method_text: str, label: str) -> list[str]:
    return re.findall(rf"{re.escape(label)}:([A-Za-z0-9_]+)", method_text)


def _parse_stream_localized_name(method_text: str, variable_name: str) -> str | None:
    match = re.search(
        rf"{re.escape(variable_name)}\s*=\s*\[CMIOExtensionStream streamWithLocalizedName:@\"([^\"]+)\"",
        method_text,
    )
    return match.group(1) if match else None


def parse_device_contract(header_text: str, impl_text: str) -> dict[str, Any]:
    readable_properties = _parse_property_guards(impl_text, "devicePropertiesForProperties")
    return {
        "conforms_device_protocol": "CMIOExtensionDeviceSource" in header_text,
        "available_properties": _parse_property_list(
            impl_text,
            "_availableProperties = [NSSet setWithArray:@[",
            "]];",
        ),
        "readable_properties": readable_properties,
        "localized_name_surface_present": "@property(nonatomic, copy, readonly) NSString* localizedName;" in header_text,
        "device_id_surface_present": "@property(nonatomic, copy, readonly) NSUUID* deviceID;" in header_text,
        "legacy_device_id_surface_present": "@property(nonatomic, copy, readonly) NSString* legacyDeviceID;" in header_text,
        "source_stream_source_surface_present": "@property(nonatomic, strong, readonly) AKVCStreamSource* sourceStreamSource;" in header_text,
        "sink_stream_source_surface_present": "@property(nonatomic, strong, readonly) AKVCSinkStreamSource* sinkStreamSource;" in header_text,
        "retains_stream_sources": "_sourceStreamSource = sourceStreamSource;" in impl_text
        and "_sinkStreamSource = sinkStreamSource;" in impl_text,
        "model": _parse_model_string(impl_text),
        "suspended": _parse_suspended_value(impl_text),
        "default_input_capable": _parse_device_property_value(
            impl_text,
            "CMIOExtensionPropertyDeviceCanBeDefaultInputDevice",
        ),
        "default_output_capable": _parse_device_property_value(
            impl_text,
            "CMIOExtensionPropertyDeviceCanBeDefaultOutputDevice",
        ),
        "device_properties_read_only": "device properties are read-only in the current macOS MVP" in impl_text,
    }


def _parse_model_string(text: str) -> str | None:
    match = re.search(r'deviceProperties\.model\s*=\s*@\"([^\"]+)\";', text)
    return match.group(1) if match else None


def _parse_suspended_value(text: str) -> bool | None:
    match = re.search(r"deviceProperties\.suspended\s*=\s*@(YES|NO);", text)
    if match is None:
        return None
    return match.group(1) == "YES"


def evaluate_contract() -> dict[str, Any]:
    provider_h_text = _read_text(PROVIDER_H)
    provider_mm_text = _read_text(PROVIDER_MM)
    device_h_text = _read_text(DEVICE_H)
    device_mm_text = _read_text(DEVICE_MM)
    hot_path_source_text = {
        str(path.relative_to(ROOT)): _read_text(path)
        for path in CAMERA_EXTENSION_HOT_PATH_SOURCES
    }

    provider = parse_provider_contract(provider_h_text, provider_mm_text)
    device = parse_device_contract(device_h_text, device_mm_text)
    extension_hot_path = parse_extension_hot_path_contract(hot_path_source_text)

    expected_provider_properties = [
        "CMIOExtensionPropertyProviderManufacturer",
        "CMIOExtensionPropertyProviderName",
    ]
    expected_device_properties = [
        "CMIOExtensionPropertyDeviceCanBeDefaultInputDevice",
        "CMIOExtensionPropertyDeviceCanBeDefaultOutputDevice",
        "CMIOExtensionPropertyDeviceIsSuspended",
        "CMIOExtensionPropertyDeviceModel",
    ]

    consistency = {
        "identity_defaults_complete": provider["default_provider_name"] == "AK Virtual Camera"
        and provider["default_manufacturer"] == "AKVC"
        and provider["default_legacy_device_id"] == "com.akvc.camera.device"
        and _is_valid_uuid(provider["default_device_uuid"])
        and _is_valid_uuid(provider["default_source_stream_uuid"])
        and _is_valid_uuid(provider["default_sink_stream_uuid"]),
        "provider_surface_complete": provider["conforms_provider_protocol"] is True
        and provider["available_properties"] == expected_provider_properties
        and provider["readable_properties"] == expected_provider_properties
        and provider["provider_properties_read_only"] is True,
        "device_surface_complete": device["conforms_device_protocol"] is True
        and device["available_properties"] == expected_device_properties
        and device["readable_properties"] == expected_device_properties
        and device["localized_name_surface_present"] is True
        and device["device_id_surface_present"] is True
        and device["legacy_device_id_surface_present"] is True
        and device["source_stream_source_surface_present"] is True
        and device["sink_stream_source_surface_present"] is True
        and device["device_properties_read_only"] is True
        and device["model"] == "AKVC CMIO Camera Extension"
        and device["suspended"] is False
        and device["default_input_capable"] is True
        and device["default_output_capable"] is False,
        "ipc_wiring_complete": provider["uses_default_ring_descriptor"] is True
        and provider["frame_provider_uses_shared_memory_name"] is True
        and provider["frame_provider_uses_slot_count"] is True
        and provider["frame_provider_uses_slot_size"] is True
        and provider["retains_device_stream_graph"] is True
        and device["retains_stream_sources"] is True,
        "graph_bootstrap_complete": provider["default_ctor_builds_frame_provider"] is True
        and provider["default_ctor_builds_source_stream_source"] is True
        and provider["default_ctor_builds_sink_stream_source"] is True
        and provider["default_ctor_builds_device_source"] is True
        and provider["supports_runtime_device_name_override"] is True
        and provider["attaches_source_stream_to_stream_source"] is True
        and provider["attaches_sink_stream_to_stream_source"] is True
        and provider["device_uses_source_localized_name"] is True
        and provider["device_uses_source_device_id"] is True
        and provider["device_uses_source_legacy_id"] is True
        and provider["source_stream_localized_name"] == "AKVC Stream"
        and provider["sink_stream_localized_name"] == "AKVC Sink Stream"
        and provider["stream_directions"] == [
            "CMIOExtensionStreamDirectionSource",
            "CMIOExtensionStreamDirectionSink",
        ]
        and provider["stream_clock_types"] == [
            "CMIOExtensionStreamClockTypeHostTime",
            "CMIOExtensionStreamClockTypeHostTime",
        ],
        "system_registration_complete": provider["provider_factory_uses_client_queue"] is True
        and provider["adds_source_stream_to_device"] is True
        and provider["adds_sink_stream_to_device"] is True
        and provider["adds_device_to_provider"] is True
        and provider["logs_stream_add_failure"] is True
        and provider["logs_device_add_failure"] is True
        and provider["starts_provider_service"] is True,
        "extension_hot_path_bypasses_host": extension_hot_path["reads_framebus_directly"] is True
        and extension_hot_path["reads_descriptor_directly"] is True
        and extension_hot_path["does_not_launch_host_agent"] is True
        and extension_hot_path["does_not_submit_system_extension_requests"] is True
        and extension_hot_path["does_not_import_host_activation_support"] is True
        and not extension_hot_path["forbidden_hits"],
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "provider": provider,
        "device": device,
        "extension_hot_path": extension_hot_path,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS Camera Extension topology contract checker")
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
        print("macOS Camera Extension topology contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
