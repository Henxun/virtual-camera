// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — CoreMediaIO Camera Extension (macOS, Phase 4).
//
// This is a SCAFFOLD. It cannot be compiled or verified without a Mac +
// Xcode + the CoreMediaIO headers. Every API call site that I could not
// confirm offline is marked `// VERIFY:` with what to check against the
// Apple "CameraExtension" sample and the CoreMediaIO/CMIOExtension*.h
// headers. Do NOT assume this builds as-is.
//
// Architecture:
//   Provider  (CMIOExtensionProvider)   — owns the extension lifecycle
//   Device    (CMIOExtensionDevice)     — one virtual camera device
//   Stream    (CMIOExtensionStream)     — one NV12 video stream
//   FrameBusReader — wraps framebus_posix.c, builds CVPixelBuffer
//
// Frame flow:
//   Python producer → POSIX shm ring → framebus_posix.c → FrameBusReader
//   → CVPixelBuffer → CMSampleBuffer → CMIOExtensionStream → client app.
//
// See docs/phase4/implementation-plan.md for the full design.

import CoreMediaIO
import CoreMedia
import CoreVideo
import Foundation

/// Camera Extension provider singleton. This is the principal class named
/// in Info.plist under `CMIOExtension → Provider`.
final class AKVCProvider: CMIOExtensionProvider {

    static let instance = AKVCProvider()

    private var device: AKVCDevice?

    override init() {
        super.init()
    }

    override func start() throws {
        os_log("akvc.ext.provider.start", type: .info)
        let device = try AKVCDevice(localizedName: AKVCCameraName,
                                    deviceUID: AKVCDeviceUID)
        self.device = device
        // VERIFY: exact attach API name. Apple sample uses
        // `self.attach(device)` — confirm against CMIOExtensionProvider.h.
        self.attach(device)
    }

    override func stop() {
        os_log("akvc.ext.provider.stop", type: .info)
        if let device = device {
            // VERIFY: `self.detach(device)` — confirm API name.
            self.detach(device)
        }
        device = nil
    }
}
