// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Self-contained tests for the raw-buffer pipeline primitives. Registered with
// CTest; exit code 0 = pass. No external test framework dependency.

#include <cstdio>
#include <cstring>
#include <vector>

#include "akvc/pixel_format.h"
#include "akvc/pipeline_ops.h"
#include "akvc/status.h"

namespace {

int g_failures = 0;

void fail(const char* msg, int got, int want) {
    std::printf("FAIL: %s (got=%d want=%d)\n", msg, got, want);
    ++g_failures;
}

void fail(const char* msg) {
    std::printf("FAIL: %s\n", msg);
    ++g_failures;
}

void check_eq(int got, int want, const char* msg) {
    if (got != want) fail(msg, got, want);
}

// Fill a packed BGR24 buffer of w*h with a solid color.
std::vector<unsigned char> solid_bgr24(int w, int h, int b, int g, int r) {
    std::vector<unsigned char> buf(static_cast<size_t>(w) * h * 3);
    for (int i = 0; i < w * h; ++i) {
        buf[i * 3 + 0] = static_cast<unsigned char>(b);
        buf[i * 3 + 1] = static_cast<unsigned char>(g);
        buf[i * 3 + 2] = static_cast<unsigned char>(r);
    }
    return buf;
}

void test_clamp() {
    check_eq(akvc::clamp_u8(-5), 0, "clamp negative");
    check_eq(akvc::clamp_u8(300), 255, "clamp overflow");
    check_eq(akvc::clamp_u8(128), 128, "clamp in-range");
}

void test_resize_identity() {
    auto src = solid_bgr24(2, 2, 10, 20, 30);
    std::vector<unsigned char> dst(2 * 2 * 3, 0);
    akvc::resize_bgr24(src.data(), 2, 2, 6, dst.data(), 2, 2, 6);
    if (src != dst) fail("resize identity should equal copy");
}

void test_resize_upscale_1x1_to_2x2() {
    // 1x1 solid red upscaled to 2x2 must fill every pixel with the source.
    std::vector<unsigned char> src = {0, 0, 255};  // BGR red
    std::vector<unsigned char> dst(2 * 2 * 3, 0);
    akvc::resize_bgr24(src.data(), 1, 1, 3, dst.data(), 2, 2, 6);
    for (int i = 0; i < 4; ++i) {
        check_eq(dst[i * 3 + 0], 0, "upscale red B");
        check_eq(dst[i * 3 + 1], 0, "upscale red G");
        check_eq(dst[i * 3 + 2], 255, "upscale red R");
    }
}

void test_resize_downscale_2x2_to_1x1() {
    // Diagonal black/white 2x2 averaged to 1x1 -> (0+255+255+0)/4 = 127.
    std::vector<unsigned char> src(2 * 2 * 3);
    // (0,0)=black, (1,0)=white, (0,1)=white, (1,1)=black
    src[0] = 0;   src[1] = 0;   src[2] = 0;       // (0,0)
    src[3] = 255; src[4] = 255; src[5] = 255;     // (1,0)
    src[6] = 255; src[7] = 255; src[8] = 255;     // (0,1)
    src[9] = 0;   src[10] = 0;  src[11] = 0;      // (1,1)
    std::vector<unsigned char> dst(3, 0);
    akvc::resize_bgr24(src.data(), 2, 2, 6, dst.data(), 1, 1, 3);
    check_eq(dst[0], 127, "downscale B");
    check_eq(dst[1], 127, "downscale G");
    check_eq(dst[2], 127, "downscale R");
}

void test_nv12_solid(int b, int g, int r, int want_y, int want_u, int want_v, const char* name) {
    const int w = 2, h = 2;
    auto src = solid_bgr24(w, h, b, g, r);
    std::vector<unsigned char> y_plane(static_cast<size_t>(w) * h, 0);
    std::vector<unsigned char> uv_plane(static_cast<size_t>(w) * (h / 2), 0);
    akvc::bgr24_to_nv12(src.data(), w, h, w * 3,
                        y_plane.data(), w, uv_plane.data(), w);
    // All Y samples equal want_y.
    for (int i = 0; i < w * h; ++i) check_eq(y_plane[i], want_y, name);
    // Single 2x2 block -> one (U,V) pair.
    check_eq(uv_plane[0], want_u, name);
    check_eq(uv_plane[1], want_v, name);
}

void test_bgr24_to_nv12() {
    // BT.709 limited-range for HD virtual-camera output.
    test_nv12_solid(0,   0,   0,   16,  128, 128, "black");
    test_nv12_solid(255, 255, 255, 235, 128, 128, "white");
    test_nv12_solid(0,   255, 0,   172, 42,  26,  "green");
    test_nv12_solid(255, 0,   0,   32,  240, 118, "blue");
    test_nv12_solid(0,   0,   255, 63,  102, 240, "red");
}

void test_bgra32_to_nv12_matches_bgr24() {
    // Same color in BGRA32 must produce identical NV12 as BGR24 (alpha ignored).
    const int w = 2, h = 2;
    std::vector<unsigned char> bgra(static_cast<size_t>(w) * h * 4);
    for (int i = 0; i < w * h; ++i) {
        bgra[i * 4 + 0] = 10; bgra[i * 4 + 1] = 200; bgra[i * 4 + 2] = 60;
        bgra[i * 4 + 3] = 0xFF;
    }
    std::vector<unsigned char> y_a(static_cast<size_t>(w) * h, 0);
    std::vector<unsigned char> uv_a(static_cast<size_t>(w) * (h / 2), 0);
    akvc::bgra32_to_nv12(bgra.data(), w, h, w * 4, y_a.data(), w, uv_a.data(), w);

    auto bgr = solid_bgr24(w, h, 10, 200, 60);
    std::vector<unsigned char> y_b(static_cast<size_t>(w) * h, 0);
    std::vector<unsigned char> uv_b(static_cast<size_t>(w) * (h / 2), 0);
    akvc::bgr24_to_nv12(bgr.data(), w, h, w * 3, y_b.data(), w, uv_b.data(), w);

    if (y_a != y_b) fail("BGRA32 vs BGR24 Y plane mismatch");
    if (uv_a != uv_b) fail("BGRA32 vs BGR24 UV plane mismatch");
}

void test_bgr24_to_bgra32() {
    const int w = 2, h = 1;
    std::vector<unsigned char> src = {1, 2, 3, 4, 5, 6};
    std::vector<unsigned char> dst(w * h * 4, 0);
    akvc::bgr24_to_bgra32(src.data(), w, h, w * 3, dst.data(), w * 4);
    check_eq(dst[0], 1, "bgra B0");
    check_eq(dst[1], 2, "bgra G0");
    check_eq(dst[2], 3, "bgra R0");
    check_eq(dst[3], 255, "bgra A0");
    check_eq(dst[4], 4, "bgra B1");
    check_eq(dst[5], 5, "bgra G1");
    check_eq(dst[6], 6, "bgra R1");
    check_eq(dst[7], 255, "bgra A1");
}

void test_bgra32_to_bgr24() {
    const int w = 2, h = 1;
    // BGRA: (1,2,3,0xFF) (4,5,6,0x80) -> BGR (1,2,3)(4,5,6) (alpha dropped)
    std::vector<unsigned char> src = {1, 2, 3, 255, 4, 5, 6, 128};
    std::vector<unsigned char> dst(w * h * 3, 0);
    akvc::bgra32_to_bgr24(src.data(), w, h, w * 4, dst.data(), w * 3);
    check_eq(dst[0], 1, "bgr B0");
    check_eq(dst[1], 2, "bgr G0");
    check_eq(dst[2], 3, "bgr R0");
    check_eq(dst[3], 4, "bgr B1");
    check_eq(dst[4], 5, "bgr G1");
    check_eq(dst[5], 6, "bgr R1");
}

void test_rgb24_to_bgr24() {
    const int w = 2, h = 1;
    // RGB (R,G,B): (1,2,3)(4,5,6) -> BGR (3,2,1)(6,5,4)
    std::vector<unsigned char> src = {1, 2, 3, 4, 5, 6};
    std::vector<unsigned char> dst(w * h * 3, 0);
    akvc::rgb24_to_bgr24(src.data(), w, h, w * 3, dst.data(), w * 3);
    check_eq(dst[0], 3, "swap B0");
    check_eq(dst[1], 2, "swap G0");
    check_eq(dst[2], 1, "swap R0");
    check_eq(dst[3], 6, "swap B1");
    check_eq(dst[4], 5, "swap G1");
    check_eq(dst[5], 4, "swap R1");
}

void test_format_status_helpers() {
    check_eq(std::strcmp(akvc::pixel_format_name(akvc::PixelFormat::BGR24), "BGR24"), 0, "name BGR24");
    check_eq(std::strcmp(akvc::pixel_format_name(akvc::PixelFormat::NV12), "NV12"), 0, "name NV12");
    check_eq(static_cast<int>(akvc::bytes_per_pixel(akvc::PixelFormat::BGR24)), 3, "bpp BGR24");
    check_eq(static_cast<int>(akvc::bytes_per_pixel(akvc::PixelFormat::BGRA32)), 4, "bpp BGRA32");
    check_eq(static_cast<int>(akvc::bytes_per_pixel(akvc::PixelFormat::NV12)), 0, "bpp NV12");
    check_eq(std::strcmp(akvc::status_name(akvc::Status::Ok), "Ok"), 0, "status Ok");
    check_eq(std::strcmp(akvc::status_name(akvc::Status::ShmUnavailable), "ShmUnavailable"), 0, "status Shm");
}

}  // namespace

int main() {
    test_clamp();
    test_resize_identity();
    test_resize_upscale_1x1_to_2x2();
    test_resize_downscale_2x2_to_1x1();
    test_bgr24_to_nv12();
    test_bgra32_to_nv12_matches_bgr24();
    test_bgr24_to_bgra32();
    test_bgra32_to_bgr24();
    test_rgb24_to_bgr24();
    test_format_status_helpers();

    if (g_failures == 0) {
        std::printf("akvc_camera_pipeline_tests: all passed\n");
        return 0;
    }
    std::printf("akvc_camera_pipeline_tests: %d FAILURE(S)\n", g_failures);
    return 1;
}
