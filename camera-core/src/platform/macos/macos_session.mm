// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// macOS VirtualCamera session implementation. Reuses the existing pure-ObjC++
// DirectSender (CMIO sink-stream queue injection, the vcam.mm path). Extension
// activation is owned by the container app: an activation step, not frame
// delivery work. See header.

#include "akvc/platform/macos/macos_session.h"

#include <cstring>

#include "akvc/pipeline_ops.h"
#include "akvc/pixel_format.h"

#include "AKVCDirectCameraSender.h"        // C ABI (akvc_macos_direct_sender_*)

namespace akvc::macos {

namespace {

// CLOCK_REALTIME 100ns ticks (Unix epoch). Used only when the caller sets
// frame.pts_100ns != 0; pts==0 lets the DirectSender use the host clock
// (CMClockGetHostTimeClock), matching the vcam.mm reference.
std::int64_t now_pts_100ns() {
    struct timespec ts{};
    clock_gettime(CLOCK_REALTIME, &ts);
    return static_cast<std::int64_t>(ts.tv_sec) * 10000000LL +
           static_cast<std::int64_t>(ts.tv_nsec) / 100;
}

}  // namespace

MacVirtualCameraSession::MacVirtualCameraSession(int width, int height, double fps,
                                                 std::string camera_name)
    : width_(width),
      height_(height),
      fps_(fps),
      camera_name_(std::move(camera_name)) {
    if (camera_name_.empty()) {
        camera_name_ = "AK Virtual Camera";
    }
}

MacVirtualCameraSession::~MacVirtualCameraSession() {
    stop();
}

void MacVirtualCameraSession::set_error(const std::string& msg) {
    last_error_storage_ = msg;
}

const char* MacVirtualCameraSession::last_error() const {
    return last_error_storage_.c_str();
}

int MacVirtualCameraSession::consumer_count() const {
    if (!sender_) {
        return 0;
    }
    return akvc_macos_direct_sender_consumer_count(sender_);
}

akvc::Status MacVirtualCameraSession::start() {
    if (started_) {
        return akvc::Status::Ok;
    }

    // Create + start the DirectSender (CMIO sink-stream queue injection). Do
    // not submit extension activation requests here: repeated requests can
    // replace the live CMIO provider while a Stop/Start cycle is in progress.
    // If the extension is missing, DirectSender.start reports the device lookup
    // failure and the install/readiness layer presents the recovery steps.
    char errbuf[512] = {0};
    sender_ = akvc_macos_direct_sender_create(width_, height_, fps_, errbuf, sizeof(errbuf));
    if (sender_ == nullptr) {
        set_error(std::string("direct sender create failed: ") + errbuf);
        return akvc::Status::Unknown;
    }
    if (akvc_macos_direct_sender_start(sender_, camera_name_.c_str(),
                                       errbuf, sizeof(errbuf)) != 0) {
        set_error(std::string("direct sender start failed: ") + errbuf);
        akvc_macos_direct_sender_destroy(sender_);
        sender_ = nullptr;
        return akvc::Status::StreamStartFailed;
    }

    started_ = true;
    return akvc::Status::Ok;
}

akvc::Status MacVirtualCameraSession::push_frame(const akvc::FrameInput& frame) {
    if (!started_) {
        set_error("virtual camera is not started");
        return akvc::Status::NotStarted;
    }
    if (frame.data == nullptr || frame.width <= 0 || frame.height <= 0 || frame.stride <= 0) {
        set_error("invalid frame: null data or non-positive dimensions");
        return akvc::Status::InvalidFrame;
    }
    if (frame.format == akvc::PixelFormat::NV12) {
        set_error("NV12 input is not supported on the macOS path");
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

    // Resize to target if needed (DirectSender requires exact target dimensions).
    if (src_w != width_ || src_h != height_) {
        resized_buf_.assign(static_cast<size_t>(width_) * height_ * 3, 0);
        akvc::resize_bgr24(bgr, src_w, src_h, bgr_stride,
                           resized_buf_.data(), width_, height_, width_ * 3);
        bgr = resized_buf_.data();
    }

    const std::uint64_t pts = frame.pts_100ns
        ? frame.pts_100ns
        : static_cast<std::uint64_t>(now_pts_100ns());

    char errbuf[512] = {0};
    const int rc = akvc_macos_direct_sender_send_bgr24(
        sender_, bgr, width_, height_, width_ * 3, pts, errbuf, sizeof(errbuf));
    if (rc != 0) {
        set_error(std::string("direct sender send failed: ") + errbuf);
        return akvc::Status::Unknown;
    }
    return akvc::Status::Ok;
}

void MacVirtualCameraSession::stop() {
    if (sender_ != nullptr) {
        akvc_macos_direct_sender_destroy(sender_);
        sender_ = nullptr;
    }
    started_ = false;
}

}  // namespace akvc::macos
