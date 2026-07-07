# AKVC macOS Runtime Assets

This directory is populated by macOS packaging builds and may contain:

- `akvc-macos-status`
- `akvc-macos-install`
- `akvc-macos-uninstall`
- `akvc-macos-list-devices`
- `akvc-macos-sync-ipc`
- `libakvc-macos-direct-sender.dylib`
- `VirtualCamera.pkg`

External host apps can use `akvc.distribution` to copy these assets into their
own bundle and generate the matching environment variables.
