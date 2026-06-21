// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Camera Extension entry point (Phase 4 scaffold).
//
// The Camera Extension's Info.plist names AKVCProvider as the principal
// provider class. CoreMediaIO instantiates it when the extension loads.
// There is no `@main` here — the provider singleton is the entry point.

import Foundation
import os.log

/// Global log subsystem for the extension. Filter Console.app / `log stream`
/// with `subsystem == "com.akvc.camera-extension"`.
let akvcLog = OSLog(subsystem: "com.akvc.camera-extension", category: "ext")

// The provider is registered declaratively via Info.plist; this file exists
// mainly to anchor the log subsystem and document the entry point.
