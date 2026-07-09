# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRAME_PROVIDER = ROOT / "virtualcam/macos/camera_extension/AKVCFrameProvider.mm"
SINK_SOURCE = ROOT / "virtualcam/macos/camera_extension/AKVCSinkStreamSource.mm"


def test_latest_client_frame_is_replayed_between_sink_ticks() -> None:
    text = FRAME_PROVIDER.read_text(encoding="utf-8")
    method_start = text.index("- (CMSampleBufferRef)copyLatestClientSampleBufferWithDiscontinuity:")
    method_end = text.index("- (CMSampleBufferRef)copyNextSampleBufferWithStatus:", method_start)
    method = text[method_start:method_end]

    assert "CMSampleBufferCreateCopyWithNewTiming" in method
    assert "CMClockGetTime(CMClockGetHostTimeClock())" in method
    assert "_latestClientDiscontinuity = CMIOExtensionStreamDiscontinuityFlagNone;" in method
    assert "CFRelease(_latestClientSampleBuffer);" not in method
    assert "_latestClientSampleBuffer = nil;" not in method


def test_sink_stop_clears_latest_client_frame() -> None:
    text = SINK_SOURCE.read_text(encoding="utf-8")
    method_start = text.index("- (BOOL)stopStreamAndReturnError:")
    method_end = text.index("- (void)restartTimer", method_start)
    method = text[method_start:method_end]

    assert "[self.frameProvider clearLatestClientSampleBuffer];" in method


def test_macos_stream_contract_reports_latest_frame_replay() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/macos_stream_contract.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["consistency"]["latest_client_frame_replay_prevents_flicker"] is True
    assert payload["consistency"]["sink_stop_clears_latest_client_frame"] is True
