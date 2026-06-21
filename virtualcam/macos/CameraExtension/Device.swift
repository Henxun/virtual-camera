// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Camera Extension device (Phase 4 scaffold, VERIFY).

import CoreMediaIO
import Foundation

let AKVCCameraName = "AK Virtual Camera"
let AKVCDeviceUID  = "com.akvc.camera"        // stable device UID
let AKVCStreamUID  = "com.akvc.camera.stream"

final class AKVCDevice: CMIOExtensionDevice {

    private var stream: AKVCStream?

    init(localizedName: String, deviceUID: String) throws {
        // VERIFY: the exact CMIOExtensionDevice initializer and the property
        // container type. Apple's sample builds a dictionary of
        // CMIOExtensionProperty → property-state; the keys include
        // kCMIOHardwarePropertyDeviceModelUID, transport type, etc.
        // Confirm against CMIOExtensionDevice.h.
        let properties: [CMIOExtensionProperty: Any] = [:]
        super.init(localizedName: localizedName,
                   deviceUID: deviceUID,
                   properties: properties)
    }

    override func start() throws {
        os_log("akvc.ext.device.start", type: .info)
        let stream = try AKVCStream(localizedName: "AK Virtual Camera Stream",
                                    streamUID: AKVCStreamUID)
        self.stream = stream
        // VERIFY: `self.attach(stream)` — confirm API name.
        self.attach(stream)
    }

    override func stop() {
        os_log("akvc.ext.device.stop", type: .info)
        if let stream = stream {
            // VERIFY: `self.detach(stream)`.
            self.detach(stream)
        }
        stream = nil
    }
}
