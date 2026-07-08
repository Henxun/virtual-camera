// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Windows session smoke tests — validation paths that do not require a running
// helper daemon or registered camera. Registered with CTest.

#include <cstdio>
#include <cstring>

#include "akvc/frame_input.h"
#include "akvc/pixel_format.h"
#include "akvc/platform/windows/windows_session.h"

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

void test_not_started_push() {
    akvc::windows::WindowsVirtualCameraSession s(1280, 720, 30.0);
    if (s.started()) fail("fresh session should not be started");

    // push_frame before start must return NotStarted (not InvalidFrame).
    akvc::FrameInput f{};
    f.data = reinterpret_cast<const unsigned char*>("x");
    f.width = 1280;
    f.height = 720;
    f.stride = 1280 * 3;
    f.format = akvc::PixelFormat::BGR24;
    check_eq(static_cast<int>(s.push_frame(f)), static_cast<int>(akvc::Status::NotStarted),
             "push before start should be NotStarted");

    if (s.last_error() == nullptr || s.last_error()[0] == '\0') {
        fail("last_error should be set after NotStarted");
    }
    check_eq(s.consumer_count(), 0, "consumer_count should be 0 before start");
}

void test_destruct_without_start() {
    // Construction + destruction without start must not crash or leak resources.
    {
        akvc::windows::WindowsVirtualCameraSession s(640, 480, 30.0, "C:/nonexistent/akvc_helper.exe");
    }
}

void test_nv12_input_rejected() {
    // NV12 input is not yet supported on the Windows path. Even though the
    // session is not started, the NotStarted check fires first; this test just
    // confirms the enum value is wired through without crash.
    akvc::windows::WindowsVirtualCameraSession s(1280, 720, 30.0);
    akvc::FrameInput f{};
    f.data = nullptr;
    f.format = akvc::PixelFormat::NV12;
    check_eq(static_cast<int>(s.push_frame(f)), static_cast<int>(akvc::Status::NotStarted),
             "NV12 null push before start");
}

}  // namespace

int main() {
    test_not_started_push();
    test_destruct_without_start();
    test_nv12_input_rejected();

    if (g_failures == 0) {
        std::printf("akvc_camera_windows_tests: all passed\n");
        return 0;
    }
    std::printf("akvc_camera_windows_tests: %d FAILURE(S)\n", g_failures);
    return 1;
}
