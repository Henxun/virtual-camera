# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MACOS_SESSION_IMPL = ROOT / "camera-core/src/platform/macos/macos_session.mm"
MACOS_SESSION_HEADER = ROOT / "camera-core/include/akvc/platform/macos/macos_session.h"
PUBLIC_CAMERA_HEADER = ROOT / "camera-core/include/akvc/virtual_camera.h"


def _macos_start_body() -> str:
    text = MACOS_SESSION_IMPL.read_text(encoding="utf-8")
    start = text.index("akvc::Status MacVirtualCameraSession::start()")
    end = text.index("akvc::Status MacVirtualCameraSession::push_frame", start)
    return text[start:end]


def test_macos_start_does_not_submit_system_extension_requests() -> None:
    text = MACOS_SESSION_IMPL.read_text(encoding="utf-8")
    body = _macos_start_body()

    assert "AKVCSystemExtensionSupport.h" not in text
    assert "AKVCSubmitSystemExtensionRequest(" not in body
    assert "AKVCQuerySystemExtensionStatus(" not in body


def test_macos_start_contract_documents_activation_as_container_app_step() -> None:
    impl_text = MACOS_SESSION_IMPL.read_text(encoding="utf-8")
    session_header = MACOS_SESSION_HEADER.read_text(encoding="utf-8")
    public_header = PUBLIC_CAMERA_HEADER.read_text(encoding="utf-8")

    assert "activation step, not frame" in impl_text
    assert "delivery work" in impl_text
    assert "Camera Extension activation/approval is owned by" in session_header
    assert "Extension activation/approval" in public_header
    assert "container app before" in public_header
