# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPPORT_IMPL = ROOT / "virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm"


def test_status_query_selects_enabled_entry_before_stale_uninstall_entries() -> None:
    text = SUPPORT_IMPL.read_text(encoding="utf-8")

    assert "AKVCSelectBestSystemExtensionProperty(runner.properties)" in text
    assert "OSSystemExtensionProperties* property = runner.properties.firstObject;" not in text

    helper_start = text.index("static OSSystemExtensionProperties* AKVCSelectBestSystemExtensionProperty")
    helper_end = text.index("NSString* AKVCCameraExtensionIdentifier", helper_start)
    helper = text[helper_start:helper_end]

    enabled_pos = helper.index("property.isEnabled")
    awaiting_pos = helper.index("property.isAwaitingUserApproval")
    uninstalling_pos = helper.index("property.isUninstalling")

    assert enabled_pos < awaiting_pos < uninstalling_pos
    assert "return property;" in helper
    assert "return awaitingApproval;" in helper
    assert "return uninstalling;" in helper
