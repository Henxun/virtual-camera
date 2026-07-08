// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "akvc/pixel_format.h"
#include "akvc/status.h"

namespace akvc {

const char* pixel_format_name(PixelFormat fmt) {
    switch (fmt) {
        case PixelFormat::BGR24:  return "BGR24";
        case PixelFormat::BGRA32: return "BGRA32";
        case PixelFormat::RGB24:  return "RGB24";
        case PixelFormat::NV12:   return "NV12";
    }
    return "Unknown";
}

std::uint32_t bytes_per_pixel(PixelFormat fmt) {
    switch (fmt) {
        case PixelFormat::BGR24:  return 3;
        case PixelFormat::BGRA32: return 4;
        case PixelFormat::RGB24:  return 3;
        case PixelFormat::NV12:   return 0;  // planar
    }
    return 0;
}

const char* status_name(Status s) {
    switch (s) {
        case Status::Ok:                       return "Ok";
        case Status::NotStarted:               return "NotStarted";
        case Status::DeviceNotFound:           return "DeviceNotFound";
        case Status::HelperUnavailable:        return "HelperUnavailable";
        case Status::ShmUnavailable:           return "ShmUnavailable";
        case Status::InvalidFrame:             return "InvalidFrame";
        case Status::ExtensionActivationFailed:return "ExtensionActivationFailed";
        case Status::StreamStartFailed:        return "StreamStartFailed";
        case Status::Unknown:                  return "Unknown";
    }
    return "Unknown";
}

}  // namespace akvc
