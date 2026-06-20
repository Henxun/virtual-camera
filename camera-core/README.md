# AK Virtual Camera — Camera Core

Pure-Python frame pipeline: providers, pipeline stages, and platform-specific frame sinks.

This package is consumed by:

- `apps/desktop` (PySide6 UI + FrameWorker)
- `apps/cli` (akvc CLI)
- third-party Python applications (Phase 6 SDK)

It contains **no Qt or OS-native code**; the only OS-specific module is the
frame sink (`frame_sink.windows_shm`), which is loaded lazily on Windows.
