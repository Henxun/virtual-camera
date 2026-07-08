// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Frame pipeline primitives operating on raw byte buffers (no numpy/pybind11).
// These are the C++ counterparts of the former camera-core/native pipeline_ops;
// algorithms are ported bit-for-bit to preserve runtime frame behavior.

#ifndef AKVC_PIPELINE_OPS_H
#define AKVC_PIPELINE_OPS_H

#include <cstdint>

namespace akvc {

std::uint8_t clamp_u8(int value);

// Resize a packed 3-channel (BGR24/RGB24) buffer. Bilinear on upscale,
// box-average on downscale (matches the legacy resize_rgb24_frame).
// `src` holds src_h rows of `src_stride` bytes (>= src_w*3).
// `dst` holds dst_h rows of `dst_stride` bytes (>= dst_w*3).
void resize_bgr24(const std::uint8_t* src,
                  int src_w, int src_h, int src_stride,
                  std::uint8_t* dst,
                  int dst_w, int dst_h, int dst_stride);

// Convert BGR24 to NV12. Produces a full-res Y plane and a half-res
// interleaved UV plane (standard NV12). cb/cr are computed per pixel then
// averaged over each 2x2 block — identical to the legacy rgb24_to_nv12_frame.
//   y_out:  y_stride * h bytes (y_stride >= w)
//   uv_out: uv_stride * (h/2) bytes (uv_stride >= w; interleaved U,V pairs)
void bgr24_to_nv12(const std::uint8_t* src, int w, int h, int src_stride,
                   std::uint8_t* y_out, int y_stride,
                   std::uint8_t* uv_out, int uv_stride);

// Convert BGRA32 to NV12 (alpha ignored; identical color math to bgr24_to_nv12).
void bgra32_to_nv12(const std::uint8_t* src, int w, int h, int src_stride,
                    std::uint8_t* y_out, int y_stride,
                    std::uint8_t* uv_out, int uv_stride);

// Convert BGR24 to BGRA32 (alpha = 0xFF). macOS CMIO sink accepts BGRA32.
void bgr24_to_bgra32(const std::uint8_t* src, int w, int h, int src_stride,
                     std::uint8_t* dst, int dst_stride);

// Convert BGRA32 to BGR24 (drops alpha). Used to normalize input before resize.
void bgra32_to_bgr24(const std::uint8_t* src, int w, int h, int src_stride,
                     std::uint8_t* dst, int dst_stride);

// Convert RGB24 (R,G,B) to BGR24 (B,G,R) by swapping R/B.
void rgb24_to_bgr24(const std::uint8_t* src, int w, int h, int src_stride,
                    std::uint8_t* dst, int dst_stride);

}  // namespace akvc

#endif  // AKVC_PIPELINE_OPS_H
