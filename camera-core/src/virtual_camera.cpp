// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// VirtualCamera facade — platform dispatch via pimpl.

#include "akvc/virtual_camera.h"

#if defined(_WIN32)
#  include "akvc/platform/windows/windows_session.h"
#elif defined(__APPLE__)
#  include "akvc/platform/macos/macos_session.h"
#else
#  error "akvc::VirtualCamera: unsupported platform"
#endif

namespace akvc {

#if defined(_WIN32)
struct VirtualCamera::Impl {
    windows::WindowsVirtualCameraSession session;
    Impl(int w, int h, double fps, const std::string& camera_name, const std::string& helper_exe)
        : session(w, h, fps, helper_exe, camera_name) {}
};
#elif defined(__APPLE__)
struct VirtualCamera::Impl {
    macos::MacVirtualCameraSession session;
    Impl(int w, int h, double fps, const std::string& camera_name, const std::string& helper_exe)
        : session(w, h, fps, camera_name) { (void)helper_exe; }
};
#endif

VirtualCamera::VirtualCamera(int width, int height, double fps,
                             std::string camera_name, std::string helper_exe)
    : impl_(std::make_unique<Impl>(width, height, fps, camera_name, helper_exe)) {}

VirtualCamera::~VirtualCamera() = default;

Status VirtualCamera::start() { return impl_->session.start(); }

Status VirtualCamera::push_frame(const FrameInput& frame) {
    return impl_->session.push_frame(frame);
}

void VirtualCamera::stop() { impl_->session.stop(); }

bool VirtualCamera::started() const { return impl_->session.started(); }

int VirtualCamera::consumer_count() const { return impl_->session.consumer_count(); }

const char* VirtualCamera::last_error() const { return impl_->session.last_error(); }

}  // namespace akvc
