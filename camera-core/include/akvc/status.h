// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Status codes returned by VirtualCamera operations.

#ifndef AKVC_STATUS_H
#define AKVC_STATUS_H

namespace akvc {

enum class Status {
    Ok = 0,
    NotStarted,
    DeviceNotFound,            // macOS: CMIO device not found
    HelperUnavailable,         // Windows: helper daemon could not start/respond
    ShmUnavailable,            // Windows: frame bus shared memory open failed
    InvalidFrame,              // bad FrameInput (null/size mismatch/stride)
    ExtensionActivationFailed, // macOS: OSSystemExtensionRequest failed
    StreamStartFailed,         // macOS: CMIODeviceStartStream failed
    Unknown,
};

const char* status_name(Status s);

}  // namespace akvc

#endif  // AKVC_STATUS_H
