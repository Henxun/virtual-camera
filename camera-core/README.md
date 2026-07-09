# AK Virtual Camera — Camera Core

Cross-platform control-layer source tree for AK Virtual Camera.

## Current role

`camera-core/` is part of the repo's canonical architecture.
It is where the cross-platform control API and platform session logic live, including the newer pure C++ / ObjC++ direction used to control the native virtual-camera runtime.

## Relationship to Python

Python remains in this repo as a compatibility/integration layer for:

- the desktop app
- diagnostics and demos
- migration-period external integrations

That Python surface should not be read as meaning `camera-core/` is primarily a Python SDK package.
The architecture truth is the native split described in the root [README](../README.md):

- `virtualcam/` — native driver/runtime
- `camera-core/` — control layer
- Python / PySide6 — thin binding and compatibility helpers

## Consumers

Today this tree is consumed by:

- native/platform runtime code
- the desktop app binding/integration path
- compatibility-oriented Python integrations that have not yet moved fully to the native API

## Guidance

When documenting or extending this area:

- treat the control-layer API as the primary contract
- treat Python helpers as adapters on top of that contract
- avoid reintroducing the old “Python SDK is the main architecture” story in docs or tests
