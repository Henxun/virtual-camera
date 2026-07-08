// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// VirtualCamera facade smoke tests — validation paths only (no start(), which
// needs the platform runtime). Cross-platform; registered with CTest.

#include <cstdio>
#include <cstring>

#include "akvc/frame_input.h"
#include "akvc/pixel_format.h"
#include "akvc/virtual_camera.h"

namespace {

int g_failures = 0;

void fail(const char* msg) {
    std::printf("FAIL: %s\n", msg);
    ++g_failures;
}

void check_eq(int got, int want, const char* msg) {
    if (got != want) {
        std::printf("FAIL: %s (got=%d want=%d)\n", msg, got, want);
        ++g_failures;
    }
}

void test_fresh_state() {
    akvc::VirtualCamera vc(1280, 720, 30.0);
    if (vc.started()) fail("fresh VirtualCamera should not be started");
    check_eq(vc.consumer_count(), 0, "consumer_count should be 0 when not started");
}

void test_push_before_start() {
    akvc::VirtualCamera vc(1280, 720, 30.0);
    unsigned char dummy[1] = {0};
    akvc::FrameInput f{};
    f.data = dummy;
    f.width = 1280;
    f.height = 720;
    f.stride = 1280 * 3;
    f.format = akvc::PixelFormat::BGR24;
    check_eq(static_cast<int>(vc.push_frame(f)), static_cast<int>(akvc::Status::NotStarted),
             "push before start should be NotStarted");
    if (vc.last_error() == nullptr || vc.last_error()[0] == '\0') {
        fail("last_error should be set after NotStarted");
    }
}

void test_invalid_frame_rejected() {
    // Even after start fails / before start, a null-data frame on a not-started
    // session returns NotStarted (started check precedes validation). This just
    // confirms the facade wires frame.format through without crashing.
    akvc::VirtualCamera vc(640, 480, 30.0);
    akvc::FrameInput f{};
    f.data = nullptr;
    f.format = akvc::PixelFormat::BGRA32;
    check_eq(static_cast<int>(vc.push_frame(f)), static_cast<int>(akvc::Status::NotStarted),
             "null frame before start should be NotStarted");
}

}  // namespace

int main() {
    test_fresh_state();
    test_push_before_start();
    test_invalid_frame_rejected();

    if (g_failures == 0) {
        std::printf("akvc_camera_facade_tests: all passed\n");
        return 0;
    }
    std::printf("akvc_camera_facade_tests: %d FAILURE(S)\n", g_failures);
    return 1;
}
