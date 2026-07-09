// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// C ABI used by the Python desktop binding for macOS install/activation
// controls. Keeping this out of VirtualCamera.start() prevents stream restarts
// from repeatedly replacing the live CMIO provider.

#include <algorithm>
#include <cstring>

#import <Foundation/Foundation.h>

#import "AKVCSystemExtensionSupport.h"

namespace {

void copy_c_string(const char* text, char* buffer, size_t capacity) {
    if (buffer == nullptr || capacity == 0) {
        return;
    }
    const char* source = text == nullptr ? "" : text;
    const size_t length = std::min(capacity - 1, std::strlen(source));
    std::memcpy(buffer, source, length);
    buffer[length] = '\0';
}

void copy_ns_string(NSString* text, char* buffer, size_t capacity) {
    copy_c_string(text == nil ? "" : text.UTF8String, buffer, capacity);
}

}  // namespace

extern "C" int akvc_macos_system_extension_status_json(
    double timeout_seconds,
    char* json_buffer,
    size_t json_capacity,
    char* error_buffer,
    size_t error_capacity
) {
    @autoreleasepool {
        NSDictionary* status = AKVCQuerySystemExtensionStatus(
            AKVCCameraExtensionIdentifier(),
            timeout_seconds
        );
        if (status == nil) {
            copy_c_string("system extension status query returned nil", error_buffer, error_capacity);
            return -1;
        }

        NSError* serialization_error = nil;
        NSData* data = [NSJSONSerialization dataWithJSONObject:status
                                                       options:0
                                                         error:&serialization_error];
        if (data == nil) {
            copy_ns_string(serialization_error.localizedDescription ?: @"failed to encode status JSON",
                           error_buffer,
                           error_capacity);
            return -2;
        }
        if (json_capacity == 0 || data.length + 1 > json_capacity) {
            copy_c_string("status JSON buffer is too small", error_buffer, error_capacity);
            return -3;
        }
        std::memcpy(json_buffer, data.bytes, data.length);
        json_buffer[data.length] = '\0';
        return 0;
    }
}

extern "C" int akvc_macos_activate_system_extension(
    double timeout_seconds,
    char* error_buffer,
    size_t error_capacity
) {
    @autoreleasepool {
        NSError* error = nil;
        BOOL ok = AKVCSubmitSystemExtensionRequest(YES, timeout_seconds, &error);
        if (!ok) {
            NSString* detail = error.localizedDescription ?: @"system extension activation request failed";
            if (error.domain.length > 0) {
                detail = [NSString stringWithFormat:@"%@ (%@/%ld)",
                                                    detail,
                                                    error.domain,
                                                    static_cast<long>(error.code)];
            }
            copy_ns_string(detail, error_buffer, error_capacity);
            return -1;
        }
        return 0;
    }
}
