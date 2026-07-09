// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Public C++ API for controlling the AK virtual camera. This is the primary
// third-party interface.
//
//   akvc::VirtualCamera vc(1280, 720, 30.0);
//   if (vc.start() == akvc::Status::Ok) {
//       akvc::FrameInput f{ buf, 1280, 720, 1280*3, akvc::PixelFormat::BGR24, 0 };
//       vc.push_frame(f);
//   }
//
// Platform behavior of start():
//   - Windows: ensure the helper daemon is running (runtime), then open the
//     shared-memory frame bus. Does NOT register the MF virtual camera
//     (installation is a separate step).
//   - macOS: attach a CMIO sink-stream DirectSender (the vcam.mm path). Camera
//     Extension activation/approval is handled by the container app before
//     frame delivery starts.
//
// The header is pure C++ (no windows.h / ObjC); platform state is held via pimpl.

#ifndef AKVC_VIRTUAL_CAMERA_H
#define AKVC_VIRTUAL_CAMERA_H

#include <memory>
#include <string>

#include "akvc/frame_input.h"
#include "akvc/status.h"

namespace akvc {

class VirtualCamera {
public:
    // `camera_name` is used on macOS (CMIO device lookup). `helper_exe` is used
    // on Windows (helper daemon path; empty = rely on scheduled task / packaged
    // akvc_helper.exe). Unused args are ignored per platform.
    explicit VirtualCamera(int width,
                           int height,
                           double fps,
                           std::string camera_name = std::string("AK Virtual Camera"),
                           std::string helper_exe = std::string());
    ~VirtualCamera();

    VirtualCamera(const VirtualCamera&) = delete;
    VirtualCamera& operator=(const VirtualCamera&) = delete;

    Status start();
    Status push_frame(const FrameInput& frame);
    void stop();

    bool started() const;
    int consumer_count() const;
    const char* last_error() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace akvc

#endif  // AKVC_VIRTUAL_CAMERA_H
