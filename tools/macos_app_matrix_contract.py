# SPDX-License-Identifier: Apache-2.0
"""Contract checks for the macOS target-application validation matrix."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "camera-core/src/akvc/platforms/macos/installer.py"
VALIDATION_REPORT = ROOT / "tools/macos_validation_report.py"
VALIDATION_SESSION_ACCEPTANCE = ROOT / "tools" / "macos_validation_session_acceptance.py"
VALIDATION_SESSION = ROOT / "tools" / "macos_validation_session.py"
VALIDATION_SESSION_SUMMARY = ROOT / "tools" / "macos_validation_session_summary.py"
SMOKE = ROOT / "tools/macos_smoke.py"
EXAMPLE_TEMPLATE = ROOT / "docs/macos/manual_validation_results.example.json"

EXPECTED_IDS = ["facetime", "google_meet", "obs", "quicktime", "teams", "zoom"]
EXPECTED_NAMES = ["FaceTime", "Google Meet", "OBS", "QuickTime", "Teams", "Zoom"]
EXPECTED_TEMPLATE_FIELDS = [
    "checks",
    "evidence",
    "name",
    "notes",
    "ready",
    "result",
    "status",
    "steps",
    "validated",
]
EXPECTED_EVIDENCE_FIELDS = [
    "device_listed",
    "device_selected",
    "preview_visible",
    "screenshot",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_targets(text: str) -> dict[str, list[str]]:
    ids = sorted(re.findall(r'"id":\s*"([^"]+)"', text))
    names = sorted(re.findall(r'"name":\s*"([^"]+)"', text))
    return {"ids": ids, "names": names}


def parse_manual_result_ids(text: str) -> list[str]:
    module = ast.parse(text, filename=str(VALIDATION_REPORT))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ALLOWED_MANUAL_RESULT_IDS":
                    value = ast.literal_eval(node.value)
                    return sorted(str(item) for item in value)
    raise ValueError("ALLOWED_MANUAL_RESULT_IDS not found")


def parse_example_template_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manual validation example must be an object")
    return sorted(str(key) for key in payload)


def parse_example_template_shape(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manual validation example must be an object")
    fields_by_id: dict[str, list[str]] = {}
    shape_complete = True
    check_lists_present = True
    step_lists_present = True
    evidence_shape_complete = True
    for key, value in payload.items():
        if not isinstance(value, dict):
            raise ValueError(f"manual validation example entry must be object: {key}")
        fields = sorted(str(item) for item in value.keys())
        fields_by_id[str(key)] = fields
        if fields != EXPECTED_TEMPLATE_FIELDS:
            shape_complete = False
        if not isinstance(value.get("checks"), list) or not value.get("checks"):
            check_lists_present = False
        if not isinstance(value.get("steps"), list) or not value.get("steps"):
            step_lists_present = False
        evidence = value.get("evidence")
        if not isinstance(evidence, dict) or sorted(str(item) for item in evidence.keys()) != EXPECTED_EVIDENCE_FIELDS:
            evidence_shape_complete = False
    return {
        "fields_by_id": fields_by_id,
        "shape_complete": shape_complete,
        "check_lists_present": check_lists_present,
        "step_lists_present": step_lists_present,
        "evidence_shape_complete": evidence_shape_complete,
    }


def parse_expected_app_count(text: str) -> int:
    module = ast.parse(text, filename=str(VALIDATION_SESSION_ACCEPTANCE))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "EXPECTED_APP_COUNT":
                    value = ast.literal_eval(node.value)
                    return int(value)
    raise ValueError("EXPECTED_APP_COUNT not found")


def parse_expected_app_ids(text: str) -> list[str]:
    module = ast.parse(text, filename=str(VALIDATION_SESSION_ACCEPTANCE))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "EXPECTED_APP_IDS":
                    value = ast.literal_eval(node.value)
                    return sorted(str(item) for item in value)
    raise ValueError("EXPECTED_APP_IDS not found")


def evaluate_contract() -> dict[str, Any]:
    installer_text = _read_text(INSTALLER)
    validation_report_text = _read_text(VALIDATION_REPORT)
    validation_session_acceptance_text = _read_text(VALIDATION_SESSION_ACCEPTANCE)
    validation_session_text = _read_text(VALIDATION_SESSION)
    validation_session_summary_text = _read_text(VALIDATION_SESSION_SUMMARY)
    smoke_text = _read_text(SMOKE)

    targets = parse_targets(installer_text)
    manual_results = {"ids": parse_manual_result_ids(validation_report_text)}
    example_template = {
        "ids": parse_example_template_ids(EXAMPLE_TEMPLATE),
        **parse_example_template_shape(EXAMPLE_TEMPLATE),
    }
    acceptance = {
        "expected_app_ids": parse_expected_app_ids(validation_session_acceptance_text),
        "expected_app_count": parse_expected_app_count(validation_session_acceptance_text),
    }

    consistency = {
        "target_ids_complete": targets["ids"] == EXPECTED_IDS and targets["names"] == EXPECTED_NAMES,
        "manual_result_ids_match_targets": manual_results["ids"] == targets["ids"],
        "example_template_ids_match_targets": example_template["ids"] == targets["ids"],
        "example_template_fields_complete": bool(example_template["shape_complete"]),
        "example_template_checks_present": bool(example_template["check_lists_present"]),
        "example_template_steps_present": bool(example_template["step_lists_present"]),
        "example_template_evidence_shape_complete": bool(example_template["evidence_shape_complete"]),
        "acceptance_expected_app_ids_match_targets": acceptance["expected_app_ids"] == targets["ids"],
        "acceptance_expected_app_count_matches_targets": acceptance["expected_app_count"] == len(targets["ids"]),
        "smoke_uses_shared_targets": "inspect_extension" in smoke_text
        and '"verification_targets"' in smoke_text,
        "validation_report_uses_shared_targets": "inspect_extension" in validation_report_text
        and "_merge_manual_results" in validation_report_text
        and '"verification_targets"' in validation_report_text,
        "validation_session_exports_target_identity_fields": all(
            needle in validation_session_text
            for needle in (
                '"validation_observed_target_app_ids"',
                '"validation_missing_target_app_ids"',
                '"validation_unexpected_target_app_ids"',
                '"validation_app_matrix"',
            )
        ),
        "validation_session_summary_surfaces_target_identity_fields": all(
            needle in validation_session_summary_text
            for needle in (
                "## Target Apps",
                "## Target App Details",
                "validation_observed_target_app_ids",
                "validation_missing_target_app_ids",
                "validation_unexpected_target_app_ids",
                "validation_app_matrix",
            )
        ),
    }
    consistency["all_checks_passed"] = all(bool(value) for value in consistency.values())

    return {
        "targets": targets,
        "manual_results": manual_results,
        "example_template": example_template,
        "acceptance": acceptance,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS app-matrix contract checker")
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
        print("macOS app-matrix contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
