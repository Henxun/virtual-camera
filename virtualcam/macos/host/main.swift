// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Host app (Phase 4 scaffold, VERIFY).
//
// The host app is responsible for activating the Camera Extension system
// extension on first run (and for publishing placeholder frames while no
// Python producer is connected — TODO Phase 4). On launch it posts an
// OSSystemExtensionRequest; the user approves in System Settings.
//
// This is a scaffold: the OSSystemExtensionRequest / CMIOExtensionActivation
// API surface is marked VERIFY. Confirm against the Apple sample and the
// SystemExtensions/CoreMediaIO headers.

import CoreMediaIO
import Foundation
import OSLog
import SystemExtensions

let hostLog = OSLog(subsystem: "com.akvc.host", category: "host")

final class AKVCHostDelegate: NSObject, OSSystemExtensionRequestDelegate {

    func request(_ request: OSSystemExtensionRequest,
                 didFinishWithResult result: OSSystemExtensionRequest.Result) {
        os_log("akvc.host: extension request finished result=%d", log: hostLog, type: .info, result.rawValue)
    }

    func request(_ request: OSSystemExtensionRequest,
                 didFailWithError error: Error) {
        os_log("akvc.host: extension request failed: %{public}@", log: hostLog, type: .error, error.localizedDescription)
    }

    func requestNeedsUserApproval(_ request: OSSystemExtensionRequest) {
        os_log("akvc.host: extension needs user approval (System Settings)", log: hostLog, type: .info)
    }

    func request(_ request: OSSystemExtensionRequest,
                 actionForReplacingExtension existing: OSSystemExtensionProperties,
                 withExtension ext: OSSystemExtensionProperties) -> OSSystemExtensionRequest.ReplacementAction {
        return .replace
    }
}

/// Activate the Camera Extension. VERIFY: the exact activation API.
/// Apple's CMIO Camera Extension flow is:
///   1. OSSystemExtensionRequest.activationRequest(forExtensionWithIdentifier:queue:)
///      → installs the system extension (user approves).
///   2. CMIOExtensionActivationRequest / CMIOExtensionCameras to register
///      the extension's camera with CoreMediaIO (VERIFY the exact type —
///      it may be `CMIOExtensionActivationRequest` or handled implicitly
///      once the system extension is installed).
func activateExtension() {
    let delegate = AKVCHostDelegate()
    // VERIFY: extension bundle identifier (must match project.yml).
    let extID = "com.akvc.camera-extension"
    let req = OSSystemExtensionRequest.activationRequest(
        forExtensionWithIdentifier: extID,
        queue: .main
    )
    req.requiresApproval = true
    OSSystemExtensionManager.shared.submitRequest(req, delegate: delegate)

    // VERIFY: whether a separate CMIOExtensionActivationRequest is needed.
    // Apple's sample calls something like:
    //   CMIOExtensionActivationRequest.create(...) / .submit(...)
    // Confirm and add here. Left as a documented gap for the Mac pass.
    os_log("akvc.host: TODO — wire CMIOExtensionActivationRequest", log: hostLog, type: .info)
}

// ---- entry point ----
// The host app is a CLI-style launcher for now; wire into a Cocoa
// NSApplicationDelegate when a UI is needed.
activateExtension()
RunLoop.main.run(until: Date(timeIntervalSinceNow: 5))  // let the request land
