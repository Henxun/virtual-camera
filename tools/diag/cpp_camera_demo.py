#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""AK Virtual Camera — C++ control layer demo / user verification.

Pushes a recognizable animated test pattern through the C++ akvc_camera binding
so a human can confirm the device shows live video in a consumer app
(OBS / Zoom / Chrome / GraphStudioNext) — gates VC-2 / VC-4 / VC-5 / VC-6.

Usage (from the repo root, after `tools/make.py build`):

    set PYTHONPATH=build\\bin\\Release
    .venv\\Scripts\\python.exe tools\\diag\\cpp_camera_demo.py

Then open the consumer app and select "AK Virtual Camera". You should see a
moving color gradient with a frame counter overlay (pure numpy, no Qt needed).

Press Ctrl-C to stop.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

import akvc_camera


def make_frame(width: int, height: int, t: int) -> np.ndarray:
    """A recognizable animated pattern: diagonal color gradient + moving bar."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    xs = np.arange(width, dtype=np.int32)
    ys = np.arange(height, dtype=np.int32)
    # BGR gradient (broadcast to HxW)
    frame[:, :, 0] = (xs * 255 // max(width - 1, 1))[None, :]                        # B
    frame[:, :, 1] = (ys * 255 // max(height - 1, 1))[:, None]                       # G
    frame[:, :, 2] = ((xs[None, :] + ys[:, None]) * 255 // (width + height - 2))     # R
    # moving vertical white bar
    bar_x = (t * 12) % width
    frame[:, max(0, bar_x - 8):bar_x + 8, :] = 255
    return frame


def main() -> int:
    width, height, fps = 1280, 720, 30.0
    helper_exe = os.environ.get("AKVC_HELPER_EXE", "")
    vc = akvc_camera.VirtualCamera(width, height, fps, "AK Virtual Camera", helper_exe)
    st = vc.start()
    print(f"start -> {st}  last_error={vc.last_error!r}")
    if st != akvc_camera.Status.Ok:
        return 1
    print("Pushing animated test pattern. Open OBS/Zoom/Chrome and select "
          "'AK Virtual Camera'. Ctrl-C to stop.")
    try:
        t = 0
        while True:
            frame = make_frame(width, height, t)
            r = vc.push_frame(frame)
            if r != akvc_camera.Status.Ok:
                print(f"push failed: {r} {vc.last_error}")
                break
            t += 1
            if t % 30 == 0:
                print(f"  frame {t}, consumer_count={vc.consumer_count}")
            time.sleep(1.0 / fps)
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        vc.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
