// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Frame input descriptor passed to VirtualCamera::push_frame.

#ifndef AKVC_FRAME_INPUT_H
#define AKVC_FRAME_INPUT_H

#include <cstdint>

#include "akvc/pixel_format.h"

namespace akvc {

// A view into an externally-owned frame buffer. The caller retains ownership
// of `data`; push_frame copies/converts it synchronously.
struct FrameInput {
    const std::uint8_t* data = nullptr;

    int width = 0;        // pixels
    int height = 0;       // pixels
    int stride = 0;       // bytes per row (>= width * bytes_per_pixel(format))
    PixelFormat format = PixelFormat::BGR24;

    // 100ns-tick presentation timestamp. 0 means "use the host clock"; the
    // backend stamps the frame at publish time.
    std::uint64_t pts_100ns = 0;
};

}  // namespace akvc

#endif  // AKVC_FRAME_INPUT_H
