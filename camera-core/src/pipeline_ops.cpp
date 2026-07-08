// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Raw-buffer frame pipeline primitives. Ported from the former pybind11-coupled
// camera-core/native pipeline_ops (resize_rgb24_frame / rgb24_to_nv12_frame),
// preserving the exact color math and sampling so published frames are
// byte-identical to the legacy pipeline.

#include "akvc/pipeline_ops.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

namespace akvc {

std::uint8_t clamp_u8(int value) {
    if (value < 0) return 0;
    if (value > 255) return 255;
    return static_cast<std::uint8_t>(value);
}

void resize_bgr24(const std::uint8_t* src,
                  int src_w, int src_h, int src_stride,
                  std::uint8_t* dst,
                  int dst_w, int dst_h, int dst_stride) {
    if (src == nullptr || dst == nullptr || src_w <= 0 || src_h <= 0 ||
        dst_w <= 0 || dst_h <= 0) {
        return;
    }

    // Identity-size fast path (still respects differing strides).
    if (src_w == dst_w && src_h == dst_h) {
        const int row_bytes = dst_w * 3;
        for (int y = 0; y < dst_h; ++y) {
            std::memcpy(dst + static_cast<size_t>(y) * dst_stride,
                        src + static_cast<size_t>(y) * src_stride,
                        static_cast<size_t>(row_bytes));
        }
        return;
    }

    const float scale_x = static_cast<float>(src_w) / static_cast<float>(dst_w);
    const float scale_y = static_cast<float>(src_h) / static_cast<float>(dst_h);
    const bool downscale = dst_w * dst_h < src_w * src_h;

    for (int y = 0; y < dst_h; ++y) {
        for (int x = 0; x < dst_w; ++x) {
            for (int c = 0; c < 3; ++c) {
                int value = 0;
                if (downscale) {
                    const int src_x0 = std::min(src_w - 1, static_cast<int>(std::floor(x * scale_x)));
                    const int src_x1 = std::min(src_w, std::max(src_x0 + 1, static_cast<int>(std::ceil((x + 1) * scale_x))));
                    const int src_y0 = std::min(src_h - 1, static_cast<int>(std::floor(y * scale_y)));
                    const int src_y1 = std::min(src_h, std::max(src_y0 + 1, static_cast<int>(std::ceil((y + 1) * scale_y))));
                    int sum = 0;
                    int count = 0;
                    for (int sy = src_y0; sy < src_y1; ++sy) {
                        for (int sx = src_x0; sx < src_x1; ++sx) {
                            sum += src[static_cast<size_t>(sy) * src_stride + (sx * 3 + c)];
                            ++count;
                        }
                    }
                    value = count > 0 ? sum / count : 0;
                } else {
                    const float src_fx = (static_cast<float>(x) + 0.5F) * scale_x - 0.5F;
                    const float src_fy = (static_cast<float>(y) + 0.5F) * scale_y - 0.5F;
                    const int x0 = std::clamp(static_cast<int>(std::floor(src_fx)), 0, src_w - 1);
                    const int y0 = std::clamp(static_cast<int>(std::floor(src_fy)), 0, src_h - 1);
                    const int x1 = std::clamp(x0 + 1, 0, src_w - 1);
                    const int y1 = std::clamp(y0 + 1, 0, src_h - 1);
                    const float wx = src_fx - std::floor(src_fx);
                    const float wy = src_fy - std::floor(src_fy);
                    const float p00 = static_cast<float>(src[static_cast<size_t>(y0) * src_stride + (x0 * 3 + c)]);
                    const float p01 = static_cast<float>(src[static_cast<size_t>(y0) * src_stride + (x1 * 3 + c)]);
                    const float p10 = static_cast<float>(src[static_cast<size_t>(y1) * src_stride + (x0 * 3 + c)]);
                    const float p11 = static_cast<float>(src[static_cast<size_t>(y1) * src_stride + (x1 * 3 + c)]);
                    const float top = p00 + (p01 - p00) * wx;
                    const float bottom = p10 + (p11 - p10) * wx;
                    value = static_cast<int>(std::lround(top + (bottom - top) * wy));
                }
                dst[static_cast<size_t>(y) * dst_stride + (x * 3 + c)] = clamp_u8(value);
            }
        }
    }
}

namespace {

// Per-pixel BGR->Y/U/V (BT.601 limited-range), byte-identical to the legacy
// rgb24_to_nv12_frame: b=src[0], g=src[1], r=src[2].
inline void bgr_to_yuv(int b, int g, int r, int& yv, int& u, int& v) {
    yv = ((66 * r + 129 * g + 25 * b + 128) >> 8) + 16;
    u  = ((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128;
    v  = ((112 * r - 94 * g - 18 * b + 128) >> 8) + 128;
}

// Shared NV12 writer for BGR24 (3bpp) and BGRA32 (4bpp) sources.
template <int BytesPerPixel>
void packed_to_nv12(const std::uint8_t* src, int w, int h, int src_stride,
                    std::uint8_t* y_out, int y_stride,
                    std::uint8_t* uv_out, int uv_stride) {
    if (src == nullptr || y_out == nullptr || uv_out == nullptr || w <= 0 || h <= 0) {
        return;
    }

    // Per-pixel U/V, then averaged over 2x2 blocks (matches the legacy
    // implementation exactly: average AFTER the per-pixel shift).
    std::vector<std::uint8_t> cb(static_cast<size_t>(w) * h);
    std::vector<std::uint8_t> cr(static_cast<size_t>(w) * h);

    for (int row = 0; row < h; ++row) {
        const std::uint8_t* src_row = src + static_cast<size_t>(row) * src_stride;
        for (int col = 0; col < w; ++col) {
            const std::uint8_t* px = src_row + static_cast<size_t>(col) * BytesPerPixel;
            const int b = px[0];
            const int g = px[1];
            const int r = px[2];
            int yv = 0, u = 0, v = 0;
            bgr_to_yuv(b, g, r, yv, u, v);
            y_out[static_cast<size_t>(row) * y_stride + col] = clamp_u8(yv);
            cb[static_cast<size_t>(row) * w + col] = clamp_u8(u);
            cr[static_cast<size_t>(row) * w + col] = clamp_u8(v);
        }
    }

    const int uv_h = h / 2;
    for (int row = 0; row < uv_h; ++row) {
        const int r0 = row * 2;
        std::uint8_t* uv_row = uv_out + static_cast<size_t>(row) * uv_stride;
        for (int col = 0; col < w / 2; ++col) {
            const int c0 = col * 2;
            const std::size_t i00 = static_cast<size_t>(r0) * w + c0;
            const std::size_t i01 = i00 + 1;
            const std::size_t i10 = static_cast<size_t>(r0 + 1) * w + c0;
            const std::size_t i11 = i10 + 1;
            uv_row[col * 2]     = static_cast<std::uint8_t>((cb[i00] + cb[i01] + cb[i10] + cb[i11]) / 4);
            uv_row[col * 2 + 1] = static_cast<std::uint8_t>((cr[i00] + cr[i01] + cr[i10] + cr[i11]) / 4);
        }
    }
}

}  // namespace

void bgr24_to_nv12(const std::uint8_t* src, int w, int h, int src_stride,
                   std::uint8_t* y_out, int y_stride,
                   std::uint8_t* uv_out, int uv_stride) {
    packed_to_nv12<3>(src, w, h, src_stride, y_out, y_stride, uv_out, uv_stride);
}

void bgra32_to_nv12(const std::uint8_t* src, int w, int h, int src_stride,
                    std::uint8_t* y_out, int y_stride,
                    std::uint8_t* uv_out, int uv_stride) {
    packed_to_nv12<4>(src, w, h, src_stride, y_out, y_stride, uv_out, uv_stride);
}

void bgr24_to_bgra32(const std::uint8_t* src, int w, int h, int src_stride,
                     std::uint8_t* dst, int dst_stride) {
    if (src == nullptr || dst == nullptr || w <= 0 || h <= 0) {
        return;
    }
    for (int row = 0; row < h; ++row) {
        const std::uint8_t* src_row = src + static_cast<size_t>(row) * src_stride;
        std::uint8_t* dst_row = dst + static_cast<size_t>(row) * dst_stride;
        for (int col = 0; col < w; ++col) {
            const std::uint8_t* sp = src_row + col * 3;
            std::uint8_t* dp = dst_row + col * 4;
            dp[0] = sp[0];
            dp[1] = sp[1];
            dp[2] = sp[2];
            dp[3] = 0xFF;
        }
    }
}

void bgra32_to_bgr24(const std::uint8_t* src, int w, int h, int src_stride,
                     std::uint8_t* dst, int dst_stride) {
    if (src == nullptr || dst == nullptr || w <= 0 || h <= 0) {
        return;
    }
    for (int row = 0; row < h; ++row) {
        const std::uint8_t* src_row = src + static_cast<size_t>(row) * src_stride;
        std::uint8_t* dst_row = dst + static_cast<size_t>(row) * dst_stride;
        for (int col = 0; col < w; ++col) {
            const std::uint8_t* sp = src_row + col * 4;
            std::uint8_t* dp = dst_row + col * 3;
            dp[0] = sp[0];
            dp[1] = sp[1];
            dp[2] = sp[2];
        }
    }
}

void rgb24_to_bgr24(const std::uint8_t* src, int w, int h, int src_stride,
                    std::uint8_t* dst, int dst_stride) {
    if (src == nullptr || dst == nullptr || w <= 0 || h <= 0) {
        return;
    }
    for (int row = 0; row < h; ++row) {
        const std::uint8_t* src_row = src + static_cast<size_t>(row) * src_stride;
        std::uint8_t* dst_row = dst + static_cast<size_t>(row) * dst_stride;
        for (int col = 0; col < w; ++col) {
            const std::uint8_t* sp = src_row + col * 3;
            std::uint8_t* dp = dst_row + col * 3;
            dp[0] = sp[2];  // B <- R
            dp[1] = sp[1];  // G
            dp[2] = sp[0];  // R <- B
        }
    }
}

}  // namespace akvc
