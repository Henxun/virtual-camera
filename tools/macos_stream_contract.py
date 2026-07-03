# SPDX-License-Identifier: Apache-2.0
"""Camera Extension stream-behavior contract checks for macOS.

Validates that the native frame provider and CMIO stream source keep the same
runtime expectations around supported formats, placeholder behavior, frame-read
status handling, discontinuity mapping, and timer-driven delivery semantics.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FRAME_PROVIDER_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCFrameProvider.h"
FRAME_PROVIDER_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCFrameProvider.mm"
STREAM_SOURCE_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCStreamSource.h"
STREAM_SOURCE_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCStreamSource.mm"
SINK_STREAM_SOURCE_H = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCSinkStreamSource.h"
SINK_STREAM_SOURCE_MM = ROOT / "virtualcam" / "macos" / "camera_extension" / "AKVCSinkStreamSource.mm"

STATUS_NAME_MAP = {
    "AKVCFrameReadStatusFrameReady": "frame_ready",
    "AKVCFrameReadStatusTimedOut": "timed_out",
    "AKVCFrameReadStatusNoProducer": "no_producer",
    "AKVCFrameReadStatusTorn": "torn",
    "AKVCFrameReadStatusError": "error",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_status_enum(text: str) -> dict[str, int]:
    match = re.search(r"typedef\s+NS_ENUM\(NSInteger,\s*AKVCFrameReadStatus\)\s*\{(.*?)\};", text, re.DOTALL)
    if match is None:
        raise ValueError("missing AKVCFrameReadStatus enum")

    enum_block = match.group(1)
    values: dict[str, int] = {}
    for name, raw_value in re.findall(r"(AKVCFrameReadStatus[A-Za-z]+)\s*=\s*(\d+)", enum_block):
        slug = STATUS_NAME_MAP.get(name)
        if slug is not None:
            values[slug] = int(raw_value)
    return values


def _extract_status_list(expression: str) -> list[str]:
    names = []
    for token in re.findall(r"AKVCFrameReadStatus[A-Za-z]+", expression):
        slug = STATUS_NAME_MAP.get(token)
        if slug is not None and slug not in names:
            names.append(slug)
    return names


def parse_frame_provider_contract(header_text: str, impl_text: str) -> dict[str, Any]:
    status_enum = parse_status_enum(header_text)
    resolutions = sorted(
        {
            (int(width), int(height))
            for width, height in re.findall(r"NSMakeSize\((\d+),\s*(\d+)\)", impl_text)
        }
    )
    frame_rates = sorted({int(rate) for rate in re.findall(r"CMTimeMake\(1,\s*(\d+)\)", impl_text)})
    placeholder_y = _parse_first_hex_literal(
        impl_text,
        r"planeCount\s*>?=\s*1.*?memset\(base,\s*(0x[0-9a-fA-F]+),",
    )
    placeholder_uv = _parse_first_hex_literal(
        impl_text,
        r"planeCount\s*>?=\s*2.*?memset\(base,\s*(0x[0-9a-fA-F]+),",
    )
    timeout_block = _extract_switch_branch(
        impl_text,
        "if (status == E_AKVC_FRAMEBUS_TIMEOUT)",
        "if (status == E_AKVC_FRAMEBUS_TORN_FRAME)",
    )
    open_failed_block = _extract_switch_branch(
        impl_text,
        "if (status == E_AKVC_FRAMEBUS_OPEN_FAILED)",
        "if (outError != nil)",
    )
    discontinuity_mappings = {
        "discontinuity": _parse_discontinuity_mapping(impl_text, "AKVC_FLAG_DISCONTINUITY"),
        "stale": _parse_discontinuity_mapping(impl_text, "AKVC_FLAG_STALE"),
        "error": _parse_discontinuity_mapping(impl_text, "AKVC_FLAG_ERROR"),
    }

    return {
        "status_enum": status_enum,
        "supported_resolutions": [
            {"width": width, "height": height}
            for width, height in resolutions
        ],
        "supported_frame_rates": frame_rates,
        "placeholder_fill": {
            "y": placeholder_y,
            "uv": placeholder_uv,
        },
        "timeout_result_statuses": sorted(
            set(
                _extract_status_list(timeout_block)
                + _extract_status_list(_extract_ternary_branches(timeout_block))
            )
        ),
        "open_failed_status": _extract_first_status(open_failed_block),
        "torn_status": _extract_first_status(
            _extract_switch_branch(
                impl_text,
                "if (status == E_AKVC_FRAMEBUS_TORN_FRAME)",
                "if (status == E_AKVC_FRAMEBUS_OPEN_FAILED)",
            )
        ),
        "reloads_shared_memory_name_from_descriptor": "akvc_macos_ring_descriptor_default(&descriptor);" in impl_text
        and "currentSharedMemoryName" in impl_text
        and "![currentSharedMemoryName isEqualToString:self.sharedMemoryName]" in impl_text,
        "closes_reader_on_shared_memory_name_change": "[self closeFrameReader];" in impl_text
        and "_pendingConfigurationDiscontinuity = YES;" in impl_text,
        "reload_change_marks_discontinuity": "_pendingConfigurationDiscontinuity" in impl_text
        and "CMIOExtensionStreamDiscontinuityFlagTime" in _extract_switch_branch(
            impl_text,
            "if (outDiscontinuity != nil)",
            "_pendingConfigurationDiscontinuity = NO;",
        ),
        "discontinuity_mappings": discontinuity_mappings,
    }


def parse_stream_source_contract(header_text: str, impl_text: str) -> dict[str, Any]:
    del header_text
    available_properties = _parse_property_list(impl_text, "_availableProperties = [NSSet setWithArray:@[", "]];")
    readable_properties = _parse_property_guards(
        impl_text,
        "streamPropertiesForProperties",
        "if ([properties containsObject:",
    )
    settable_properties = _parse_property_updates(impl_text)
    drop_condition = _extract_switch_branch(
        impl_text,
        "if (sampleBuffer == nil)",
        "error = nil;",
    )
    drop_statuses = _extract_status_list(drop_condition)
    all_statuses = list(parse_status_enum(_read_text(FRAME_PROVIDER_H)).keys())
    placeholder_statuses = [
        status
        for status in all_statuses
        if status not in {"frame_ready", *drop_statuses}
    ]

    return {
        "available_properties": available_properties,
        "readable_properties": readable_properties,
        "settable_properties": settable_properties,
        "drop_statuses": sorted(drop_statuses),
        "placeholder_statuses": sorted(placeholder_statuses),
        "start_requires_attached_stream": "if (self.stream == nil)" in impl_text,
        "timer_follows_active_frame_duration": "self.frameProvider.activeFrameDuration" in _extract_method(
            impl_text, "timerIntervalInNanoseconds"
        ),
        "timer_default_fps": 30 if "NSEC_PER_SEC / 30" in _extract_method(impl_text, "timerIntervalInNanoseconds") else None,
        "restarts_timer_when_streaming": "if (self.streaming) {\n        [self restartTimer];" in impl_text,
        "closes_reader_on_stop": "[self.frameProvider closeFrameReader];" in _extract_method(
            impl_text, "stopStreamAndReturnError"
        ),
        "notifies_format_change_on_auto_switch": "notifyPropertiesChanged" in _extract_switch_branch(
            impl_text,
            "if (self.frameProvider.activeFormatIndex != previousFormatIndex)",
            "[self.stream sendSampleBuffer:",
        ),
        "sends_sample_buffer": "[self.stream sendSampleBuffer:" in impl_text,
    }


def parse_sink_stream_source_contract(header_text: str, impl_text: str) -> dict[str, Any]:
    del header_text
    available_properties = _parse_property_list(impl_text, "_availableProperties = [NSSet setWithArray:@[", "]];")
    readable_properties = _parse_property_guards(
        impl_text,
        "streamPropertiesForProperties",
        "if ([properties containsObject:",
    )
    settable_properties = _parse_property_updates(impl_text)
    return {
        "available_properties": available_properties,
        "readable_properties": readable_properties,
        "settable_properties": settable_properties,
        "start_requires_attached_stream": "if (self.stream == nil)" in impl_text,
        "consumes_client_buffers": "consumeSampleBufferFromClient" in impl_text,
        "stores_client_buffers": "storeClientSampleBuffer" in impl_text,
        "polls_streaming_clients": "self.stream.streamingClients" in impl_text,
        "tracks_sink_queue_depth_properties": "CMIOExtensionPropertyStreamSinkBufferQueueSize" in impl_text
        and "CMIOExtensionPropertyStreamSinkBuffersRequiredForStartup" in impl_text
        and "CMIOExtensionPropertyStreamSinkBufferUnderrunCount" in impl_text
        and "CMIOExtensionPropertyStreamSinkEndOfData" in impl_text,
    }


def _parse_first_hex_literal(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.DOTALL)
    if match is None:
        return None
    return int(match.group(1), 16)


def _extract_switch_branch(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        end = len(text)
    return text[start:end]


def _extract_ternary_branches(text: str) -> str:
    match = re.search(r"\?\s*(AKVCFrameReadStatus[A-Za-z]+)\s*:\s*(AKVCFrameReadStatus[A-Za-z]+)", text)
    if match is None:
        return ""
    return f"{match.group(1)} {match.group(2)}"


def _extract_first_status(text: str) -> str | None:
    statuses = _extract_status_list(text)
    return statuses[0] if statuses else None


def _parse_discontinuity_mapping(text: str, flag_name: str) -> str | None:
    match = re.search(
        rf"if\s*\(\(flags\s*&\s*{re.escape(flag_name)}\)\s*!=\s*0\)\s*\{{\s*discontinuity\s*\|=\s*(CMIOExtensionStreamDiscontinuityFlag[A-Za-z]+);",
        text,
        re.DOTALL,
    )
    if match is None:
        return None
    return match.group(1)


def _parse_property_list(text: str, start_marker: str, end_marker: str) -> list[str]:
    start = text.find(start_marker)
    if start < 0:
        return []
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        return []
    block = text[start:end]
    return sorted(set(re.findall(r"CMIOExtensionProperty[A-Za-z]+", block)))


def _parse_property_guards(text: str, method_name: str, prefix: str) -> list[str]:
    method = _extract_method(text, method_name)
    return sorted(set(re.findall(rf"{re.escape(prefix)}(CMIOExtensionProperty[A-Za-z]+)", method)))


def _parse_property_updates(text: str) -> list[str]:
    method = _extract_method(text, "setStreamProperties")
    states = re.findall(r"updates\[(CMIOExtensionProperty[A-Za-z]+)\]", method)
    return sorted(set(states))


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


def evaluate_contract() -> dict[str, Any]:
    frame_provider_h_text = _read_text(FRAME_PROVIDER_H)
    frame_provider_mm_text = _read_text(FRAME_PROVIDER_MM)
    stream_source_h_text = _read_text(STREAM_SOURCE_H)
    stream_source_mm_text = _read_text(STREAM_SOURCE_MM)
    sink_stream_source_h_text = _read_text(SINK_STREAM_SOURCE_H)
    sink_stream_source_mm_text = _read_text(SINK_STREAM_SOURCE_MM)

    frame_provider = parse_frame_provider_contract(frame_provider_h_text, frame_provider_mm_text)
    stream_source = parse_stream_source_contract(stream_source_h_text, stream_source_mm_text)
    sink_stream = parse_sink_stream_source_contract(sink_stream_source_h_text, sink_stream_source_mm_text)

    expected_status_enum = {
        "frame_ready": 0,
        "timed_out": 1,
        "no_producer": 2,
        "torn": 3,
        "error": 4,
    }
    expected_resolutions = [
        {"width": 1280, "height": 720},
        {"width": 1920, "height": 1080},
        {"width": 3840, "height": 2160},
    ]
    expected_properties = [
        "CMIOExtensionPropertyStreamActiveFormatIndex",
        "CMIOExtensionPropertyStreamFrameDuration",
        "CMIOExtensionPropertyStreamMaxFrameDuration",
    ]
    expected_sink_properties = sorted([
        "CMIOExtensionPropertyStreamActiveFormatIndex",
        "CMIOExtensionPropertyStreamFrameDuration",
        "CMIOExtensionPropertyStreamMaxFrameDuration",
        "CMIOExtensionPropertyStreamSinkBufferQueueSize",
        "CMIOExtensionPropertyStreamSinkBuffersRequiredForStartup",
        "CMIOExtensionPropertyStreamSinkBufferUnderrunCount",
        "CMIOExtensionPropertyStreamSinkEndOfData",
    ])

    consistency = {
        "status_enum_complete": frame_provider["status_enum"] == expected_status_enum,
        "supported_resolutions_complete": frame_provider["supported_resolutions"] == expected_resolutions,
        "supported_frame_rates_complete": frame_provider["supported_frame_rates"] == [30, 60],
        "placeholder_nv12_black_like": frame_provider["placeholder_fill"] == {"y": 16, "uv": 128},
        "timeout_maps_to_timed_out_or_no_producer": sorted(frame_provider["timeout_result_statuses"])
        == ["no_producer", "timed_out"],
        "open_failed_maps_to_no_producer": frame_provider["open_failed_status"] == "no_producer",
        "torn_maps_to_torn": frame_provider["torn_status"] == "torn",
        "shared_memory_reload_supported": frame_provider["reloads_shared_memory_name_from_descriptor"] is True
        and frame_provider["closes_reader_on_shared_memory_name_change"] is True
        and frame_provider["reload_change_marks_discontinuity"] is True,
        "discontinuity_mappings_complete": frame_provider["discontinuity_mappings"] == {
            "discontinuity": "CMIOExtensionStreamDiscontinuityFlagTime",
            "stale": "CMIOExtensionStreamDiscontinuityFlagSampleDropped",
            "error": "CMIOExtensionStreamDiscontinuityFlagUnknown",
        },
        "property_surface_complete": stream_source["available_properties"] == expected_properties
        and stream_source["readable_properties"] == expected_properties
        and stream_source["settable_properties"]
        == [
            "CMIOExtensionPropertyStreamActiveFormatIndex",
            "CMIOExtensionPropertyStreamFrameDuration",
        ],
        "sink_property_surface_complete": sink_stream["available_properties"] == expected_sink_properties
        and sink_stream["readable_properties"] == expected_sink_properties
        and sink_stream["settable_properties"]
        == [
            "CMIOExtensionPropertyStreamActiveFormatIndex",
            "CMIOExtensionPropertyStreamFrameDuration",
            "CMIOExtensionPropertyStreamSinkEndOfData",
        ],
        "placeholder_on_no_producer_only": stream_source["placeholder_statuses"] == ["no_producer"],
        "drop_statuses_match_expected": stream_source["drop_statuses"] == ["error", "timed_out", "torn"],
        "timer_behavior_complete": stream_source["timer_follows_active_frame_duration"] is True
        and stream_source["timer_default_fps"] == 30
        and stream_source["restarts_timer_when_streaming"] is True,
        "stream_lifecycle_complete": stream_source["start_requires_attached_stream"] is True
        and stream_source["closes_reader_on_stop"] is True
        and stream_source["notifies_format_change_on_auto_switch"] is True
        and stream_source["sends_sample_buffer"] is True,
        "sink_stream_consumes_client_buffers": sink_stream["start_requires_attached_stream"] is True
        and sink_stream["consumes_client_buffers"] is True
        and sink_stream["stores_client_buffers"] is True
        and sink_stream["polls_streaming_clients"] is True
        and sink_stream["tracks_sink_queue_depth_properties"] is True,
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "frame_provider": frame_provider,
        "stream_source": stream_source,
        "sink_stream": sink_stream,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS Camera Extension stream contract checker")
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
        print("macOS Camera Extension stream contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
