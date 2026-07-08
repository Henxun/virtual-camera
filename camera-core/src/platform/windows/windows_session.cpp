// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "akvc/platform/windows/windows_session.h"

#include <cstring>
#include <sstream>
#include <stdexcept>

#include "akvc/pipeline_ops.h"
#include "akvc/pixel_format.h"
#include "akvc_protocol.h"  // AKVC_FOURCC_NV12, akvc_frame_header_t

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace akvc::windows {

namespace {

std::int64_t now_pts_100ns() {
    FILETIME ft{};
    ::GetSystemTimePreciseAsFileTime(&ft);
    ULARGE_INTEGER ul;
    ul.LowPart = ft.dwLowDateTime;
    ul.HighPart = ft.dwHighDateTime;
    return static_cast<std::int64_t>(ul.QuadPart);
}

// Windows 11+ = build >= 22000. RtlGetVersion is not affected by the manifest
// compatibility lies that GetVersionEx tells.
bool is_windows_11_or_later() {
    OSVERSIONINFOEXW osvi{};
    osvi.dwOSVersionInfoSize = sizeof(osvi);
    using RtlGetVersion_t = LONG(WINAPI*)(OSVERSIONINFOEXW*);
    HMODULE ntdll = ::GetModuleHandleW(L"ntdll.dll");
    if (ntdll == nullptr) {
        return false;
    }
    auto pRtlGetVersion = reinterpret_cast<RtlGetVersion_t>(::GetProcAddress(ntdll, "RtlGetVersion"));
    if (pRtlGetVersion == nullptr || pRtlGetVersion(&osvi) != 0) {
        return false;
    }
    return osvi.dwMajorVersion >= 10 && osvi.dwBuildNumber >= 22000;
}

}  // namespace

WindowsVirtualCameraSession::WindowsVirtualCameraSession(int width, int height, double fps,
                                                         std::string helper_exe,
                                                         std::string camera_name)
    : width_(width),
      height_(height),
      fps_(fps),
      helper_exe_(std::move(helper_exe)),
      camera_name_(std::move(camera_name)) {
    if (camera_name_.empty()) {
        camera_name_ = "AK Virtual Camera";
    }
}

WindowsVirtualCameraSession::~WindowsVirtualCameraSession() {
    stop();
}

void WindowsVirtualCameraSession::set_error(const std::string& msg) {
    last_error_storage_ = msg;
}

const char* WindowsVirtualCameraSession::last_error() const {
    return last_error_storage_.c_str();
}

int WindowsVirtualCameraSession::consumer_count() const {
    if (producer_) {
        return producer_->consumer_count();
    }
    return 0;
}

akvc::Status WindowsVirtualCameraSession::start() {
    if (started_) {
        return akvc::Status::Ok;
    }
    if (!helper_) {
        helper_ = std::make_unique<HelperClientRuntime>();
    }
    // Runtime: ensure the helper daemon is running. This does NOT register the
    // MF virtual camera — registration is an install step, out of scope here.
    if (!helper_->ensure_running(helper_exe_)) {
        std::string msg = "akvc helper unavailable";
        if (!helper_->last_error_message().empty()) {
            msg += ": ";
            msg += helper_->last_error_message();
        }
        set_error(msg);
        return akvc::Status::HelperUnavailable;
    }
    if (is_windows_11_or_later()) {
        // Win11: register the MF virtual camera (MFCreateVirtualCamera via the
        // elevated helper) so MF-based consumers (Chrome/Edge/Teams) see the
        // device. Idempotent. DShow (OBS/Zoom) works regardless.
        if (!helper_->register_mf(camera_name_)) {
            std::string msg = "MF virtual camera registration failed";
            if (!helper_->last_error_message().empty()) {
                msg += ": ";
                msg += helper_->last_error_message();
            }
            set_error(msg);
            return akvc::Status::HelperUnavailable;
        }
    }
    if (!producer_) {
        producer_ = std::make_unique<FramebusProducer>();
    }
    try {
        producer_->open();
    } catch (const std::runtime_error& e) {
        set_error(e.what());
        return akvc::Status::ShmUnavailable;
    }
    started_ = true;
    return akvc::Status::Ok;
}

akvc::Status WindowsVirtualCameraSession::push_frame(const akvc::FrameInput& frame) {
    if (!started_) {
        set_error("virtual camera is not started");
        return akvc::Status::NotStarted;
    }

    // Validate input.
    if (frame.data == nullptr || frame.width <= 0 || frame.height <= 0 || frame.stride <= 0) {
        set_error("invalid frame: null data or non-positive dimensions");
        return akvc::Status::InvalidFrame;
    }
    if (frame.format == akvc::PixelFormat::NV12) {
        set_error("NV12 input is not supported on the Windows path yet");
        return akvc::Status::InvalidFrame;
    }
    const std::uint32_t bpp = akvc::bytes_per_pixel(frame.format);
    if (frame.stride < frame.width * static_cast<int>(bpp)) {
        set_error("invalid frame: stride smaller than width * bytes_per_pixel");
        return akvc::Status::InvalidFrame;
    }

    // Normalize to BGR24 at source resolution.
    const int src_w = frame.width;
    const int src_h = frame.height;
    const int bgr_stride = src_w * 3;
    const std::uint8_t* bgr = nullptr;
    if (frame.format == akvc::PixelFormat::BGR24) {
        bgr = frame.data;
    } else {
        bgr_buf_.assign(static_cast<size_t>(src_w) * src_h * 3, 0);
        if (frame.format == akvc::PixelFormat::BGRA32) {
            akvc::bgra32_to_bgr24(frame.data, src_w, src_h, frame.stride,
                                  bgr_buf_.data(), bgr_stride);
        } else {  // RGB24
            akvc::rgb24_to_bgr24(frame.data, src_w, src_h, frame.stride,
                                 bgr_buf_.data(), bgr_stride);
        }
        bgr = bgr_buf_.data();
    }

    // Resize to target if needed.
    if (src_w != width_ || src_h != height_) {
        resized_buf_.assign(static_cast<size_t>(width_) * height_ * 3, 0);
        akvc::resize_bgr24(bgr, src_w, src_h, bgr_stride,
                           resized_buf_.data(), width_, height_, width_ * 3);
        bgr = resized_buf_.data();
    }

    // Convert BGR24 -> NV12.
    y_plane_.assign(static_cast<size_t>(width_) * height_, 0);
    uv_plane_.assign(static_cast<size_t>(width_) * (height_ / 2), 0);
    akvc::bgr24_to_nv12(bgr, width_, height_, width_ * 3,
                        y_plane_.data(), width_, uv_plane_.data(), width_);

    // Build header (publish() fills magic/schema_version/seq_head/seq_tail/
    // plane_offset/heartbeat internally).
    akvc_frame_header_t hdr{};
    hdr.fourcc = AKVC_FOURCC_NV12;
    hdr.width = static_cast<std::uint32_t>(width_);
    hdr.height = static_cast<std::uint32_t>(height_);
    hdr.stride[0] = static_cast<std::uint32_t>(width_);
    hdr.stride[1] = static_cast<std::uint32_t>(width_);
    hdr.plane_size[0] = static_cast<std::uint32_t>(width_ * height_);
    hdr.plane_size[1] = static_cast<std::uint32_t>(width_ * height_ / 2);
    hdr.flags = AKVC_FLAG_NONE;
    hdr.pts_100ns = frame.pts_100ns ? frame.pts_100ns
                                    : static_cast<std::uint64_t>(now_pts_100ns());

    try {
        producer_->publish(hdr, y_plane_.data(), uv_plane_.data());
    } catch (const std::runtime_error& e) {
        set_error(e.what());
        return akvc::Status::ShmUnavailable;
    }
    return akvc::Status::Ok;
}

void WindowsVirtualCameraSession::stop() {
    if (!started_) {
        return;
    }
    if (producer_) {
        producer_->close();
    }
    started_ = false;
}

}  // namespace akvc::windows
