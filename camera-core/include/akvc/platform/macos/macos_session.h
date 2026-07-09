// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// macOS VirtualCamera session — CMIO sink-stream queue injection.
//
// start(): attach a DirectSender to the extension's CMIO sink stream (the
//          vcam.mm path). Camera Extension activation/approval is owned by the
//          container app before frame delivery starts.
// push_frame(): normalize input to BGR24, resize to target, enqueue a
//          CMSampleBuffer via the DirectSender.
//
// This header is pure C++ (no ObjC) so the M4 facade can hold it via pimpl
// without leaking ObjC into the public API.

#ifndef AKVC_PLATFORM_MACOS_MACOS_SESSION_H
#define AKVC_PLATFORM_MACOS_MACOS_SESSION_H

#include <cstdint>
#include <string>
#include <vector>

#include "akvc/frame_input.h"
#include "akvc/status.h"

namespace akvc::macos {

class MacVirtualCameraSession {
public:
    MacVirtualCameraSession(int width, int height, double fps,
                            std::string camera_name = std::string("AK Virtual Camera"));
    ~MacVirtualCameraSession();

    MacVirtualCameraSession(const MacVirtualCameraSession&) = delete;
    MacVirtualCameraSession& operator=(const MacVirtualCameraSession&) = delete;

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
    std::string camera_name_;

    void* sender_ = nullptr;  // akvc_macos_direct_sender_ref (opaque)

    bool started_ = false;
    std::vector<std::uint8_t> bgr_buf_;      // normalized BGR24 at source res
    std::vector<std::uint8_t> resized_buf_;  // BGR24 at target res
    std::string last_error_storage_;
};

}  // namespace akvc::macos

#endif  // AKVC_PLATFORM_MACOS_MACOS_SESSION_H
