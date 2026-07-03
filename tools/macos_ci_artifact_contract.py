# SPDX-License-Identifier: Apache-2.0
"""Contract checks for macOS CI/Jenkins artifact publishing.

The macOS pipeline is only useful for manual acceptance when it preserves the
release packages, runtime command tools, device-enumeration evidence, validation
reports, and manual-results template together. This checker keeps GitHub
Actions and Jenkins aligned around that acceptance bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GITHUB_WORKFLOW = ROOT / ".github/workflows/macos.yml"
JENKINSFILE = ROOT / "jenkins/macos.Jenkinsfile"

RELEASE_ARTIFACTS = [
    "build/macos/VirtualCamera.pkg",
    "build/macos/VirtualCamera.dmg",
    "build/macos/VirtualCamera.zip",
]
RUNTIME_ARTIFACTS = [
    "camera-core/src/akvc/_runtime/macos/VirtualCamera.pkg",
    "camera-core/src/akvc/_runtime/macos/akvc-macos-status",
    "camera-core/src/akvc/_runtime/macos/akvc-macos-install",
    "camera-core/src/akvc/_runtime/macos/akvc-macos-uninstall",
    "camera-core/src/akvc/_runtime/macos/akvc-macos-list-devices",
    "camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc",
]
VALIDATION_ARTIFACTS = [
    "build/macos/benchmark.json",
    "build/macos/framebus-roundtrip.json",
    "build/macos/session/preflight.json",
    "build/macos/session/release-diagnostics.json",
    "build/macos/session/status-binary-check.json",
    "build/macos/session/list-devices-binary-check.json",
    "build/macos/session/entrypoints-contract.json",
    "build/macos/session/install-session-report.json",
    "build/macos/session/smoke-report.json",
    "build/macos/session/session-manifest.json",
    "build/macos/session/session-manifest-check.json",
    "build/macos/session/session-acceptance.json",
    "build/macos/session/session-acceptance-contract.json",
    "build/macos/session/session-summary.md",
    "build/macos/session/manual-results.template.json",
    "build/macos/session/validation-report.json",
]
REQUIRED_ARTIFACTS = RELEASE_ARTIFACTS + RUNTIME_ARTIFACTS + VALIDATION_ARTIFACTS

REQUIRED_VALIDATION_COMMANDS = [
    "validation-session",
    "--run-status-binary-check",
    "--run-list-devices-binary-check",
    "validation-session-artifact-check",
    "--require-existing-artifacts",
    "validation-session-summary",
    "validation-session-acceptance-contract",
]
REQUIRED_BENCHMARK_COMMAND_FRAGMENTS = [
    "tools/macos_benchmark.py",
    "--output build/macos/benchmark.json",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _presence_map(text: str, needles: list[str]) -> dict[str, bool]:
    return {needle: needle in text for needle in needles}


def _all_present(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _evaluate_surface(text: str, *, publisher_token: str) -> dict[str, Any]:
    artifact_presence = _presence_map(text, REQUIRED_ARTIFACTS)
    command_presence = _presence_map(text, REQUIRED_VALIDATION_COMMANDS)
    benchmark_command_presence = _presence_map(text, REQUIRED_BENCHMARK_COMMAND_FRAGMENTS)
    return {
        "uses_upload_artifact": "actions/upload-artifact@v4" in text,
        "uses_archive_artifacts": "archiveArtifacts" in text,
        "uses_required_publisher": publisher_token in text,
        "archives_release_artifacts": _all_present(text, RELEASE_ARTIFACTS),
        "archives_runtime_artifacts": _all_present(text, RUNTIME_ARTIFACTS),
        "archives_validation_artifacts": _all_present(text, VALIDATION_ARTIFACTS),
        "runs_validation_session": "validation-session" in text,
        "runs_status_binary_check": "--run-status-binary-check" in text,
        "runs_list_devices_binary_check": "--run-list-devices-binary-check" in text,
        "runs_benchmark_smoke": _all_present(text, REQUIRED_BENCHMARK_COMMAND_FRAGMENTS),
        "runs_validation_artifact_replay": "validation-session-artifact-check" in text
        and "--require-existing-artifacts" in text,
        "renders_session_summary": "validation-session-summary" in text
        and "session-summary.md" in text,
        "runs_acceptance_contract_replay": "validation-session-acceptance-contract" in text,
        "artifact_presence": artifact_presence,
        "validation_command_presence": command_presence,
        "benchmark_command_presence": benchmark_command_presence,
    }


def _surface_passes(surface: dict[str, Any], *, expected_publisher_key: str) -> bool:
    return (
        surface["uses_required_publisher"] is True
        and surface[expected_publisher_key] is True
        and surface["archives_release_artifacts"] is True
        and surface["archives_runtime_artifacts"] is True
        and surface["archives_validation_artifacts"] is True
        and surface["runs_validation_session"] is True
        and surface["runs_status_binary_check"] is True
        and surface["runs_list_devices_binary_check"] is True
        and surface["runs_benchmark_smoke"] is True
        and surface["runs_validation_artifact_replay"] is True
        and surface["renders_session_summary"] is True
        and surface["runs_acceptance_contract_replay"] is True
        and all(bool(value) for value in surface["artifact_presence"].values())
        and all(bool(value) for value in surface["validation_command_presence"].values())
        and all(bool(value) for value in surface["benchmark_command_presence"].values())
    )


def evaluate_contract() -> dict[str, Any]:
    github_text = _read_text(GITHUB_WORKFLOW)
    jenkins_text = _read_text(JENKINSFILE)
    github = _evaluate_surface(github_text, publisher_token="actions/upload-artifact@v4")
    jenkins = _evaluate_surface(jenkins_text, publisher_token="archiveArtifacts")

    github_missing = [
        artifact for artifact, present in github["artifact_presence"].items() if not present
    ]
    jenkins_missing = [
        artifact for artifact, present in jenkins["artifact_presence"].items() if not present
    ]
    consistency = {
        "github_complete": _surface_passes(github, expected_publisher_key="uses_upload_artifact"),
        "jenkins_complete": _surface_passes(jenkins, expected_publisher_key="uses_archive_artifacts"),
        "github_missing_required_artifacts": github_missing,
        "jenkins_missing_required_artifacts": jenkins_missing,
        "github_and_jenkins_archive_same_required_artifacts": not github_missing
        and not jenkins_missing
        and set(github["artifact_presence"]) == set(jenkins["artifact_presence"]),
    }
    consistency["all_checks_passed"] = (
        consistency["github_complete"] is True
        and consistency["jenkins_complete"] is True
        and consistency["github_and_jenkins_archive_same_required_artifacts"] is True
    )

    return {
        "required": {
            "release_artifacts": RELEASE_ARTIFACTS,
            "runtime_artifacts": RUNTIME_ARTIFACTS,
            "validation_artifacts": VALIDATION_ARTIFACTS,
            "validation_commands": REQUIRED_VALIDATION_COMMANDS,
            "benchmark_command_fragments": REQUIRED_BENCHMARK_COMMAND_FRAGMENTS,
        },
        "github": github,
        "jenkins": jenkins,
        "consistency": consistency,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AKVC macOS CI artifact contract checker")
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
        print("macOS CI artifact publishing contract mismatch detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
