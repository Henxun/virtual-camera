// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Public pixel-format enum for the AKVC control layer.

#ifndef AKVC_PIXEL_FORMAT_H
#define AKVC_PIXEL_FORMAT_H

#include <cstdint>

namespace akvc {

// Input pixel formats accepted by VirtualCamera::push_frame. Enum values are
// stable identifiers (not wire FourCCs); the platform backend translates to
// the wire format when publishing (Windows: NV12; macOS: BGRA32 via CMIO).
enum class PixelFormat : std::uint32_t {
    BGR24 = 1,   // packed B,G,R per pixel (3 bytes) — numpy/Qt/cv2 default
    BGRA32 = 2,  // packed B,G,R,A per pixel (4 bytes)
    RGB24 = 3,   // packed R,G,B per pixel (3 bytes)
    NV12 = 4,    // already NV12 (Y plane + interleaved UV); passed through
};

const char* pixel_format_name(PixelFormat fmt);

// Bytes per pixel for packed formats. Returns 0 for planar formats (NV12).
std::uint32_t bytes_per_pixel(PixelFormat fmt);

}  // namespace akvc

#endif  // AKVC_PIXEL_FORMAT_H
