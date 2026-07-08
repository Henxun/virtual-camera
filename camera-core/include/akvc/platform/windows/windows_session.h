// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Windows VirtualCamera session — runtime control path.
//
// start(): ensure the helper daemon is running (runtime; does NOT register the
//          MF virtual camera — that is an install step), then open the shared
//          memory frame bus.
// push_frame(): normalize input to BGR24, resize to target, convert to NV12,
//          publish to the frame bus.

#ifndef AKVC_PLATFORM_WINDOWS_WINDOWS_SESSION_H
#define AKVC_PLATFORM_WINDOWS_WINDOWS_SESSION_H

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "akvc/frame_input.h"
#include "akvc/status.h"
#include "akvc/platform/windows/helper_client_runtime.h"
#include "akvc/platform/windows/framebus_producer.h"

namespace akvc::windows {

class WindowsVirtualCameraSession {
public:
    WindowsVirtualCameraSession(int width, int height, double fps,
                                std::string helper_exe = std::string(),
                                std::string camera_name = std::string("AK Virtual Camera"));
    ~WindowsVirtualCameraSession();

    WindowsVirtualCameraSession(const WindowsVirtualCameraSession&) = delete;
    WindowsVirtualCameraSession& operator=(const WindowsVirtualCameraSession&) = delete;

    akvc::Status start();
    akvc::Status push_frame(const akvc::FrameInput& frame);
    void stop();

    bool started() const { return started_; }
    int consumer_count() const;
    const char* last_error() const;

private:
    void set_error(const std::string& msg);

    int width_;
    int height_;
    double fps_;
    std::string helper_exe_;
    std::string camera_name_;

    std::unique_ptr<HelperClientRuntime> helper_;
    std::unique_ptr<FramebusProducer> producer_;
    bool started_ = false;

    // Reusable conversion buffers (avoid per-frame allocation).
    std::vector<std::uint8_t> bgr_buf_;       // normalized BGR24 at source res
    std::vector<std::uint8_t> resized_buf_;   // BGR24 at target res
    std::vector<std::uint8_t> y_plane_;       // NV12 Y plane
    std::vector<std::uint8_t> uv_plane_;      // NV12 UV plane

    std::uint64_t seq_ = 0;
    std::string last_error_storage_;
};

}  // namespace akvc::windows

#endif  // AKVC_PLATFORM_WINDOWS_WINDOWS_SESSION_H
