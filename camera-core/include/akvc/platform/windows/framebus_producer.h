// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Windows frame-bus producer wrapper. Thin C++ shell around
// akvc::FrameBusProducer (from virtualcam/windows/framebus) that takes raw
// uint8_t* plane pointers instead of numpy arrays. Errors raise std::runtime_error.

#ifndef AKVC_PLATFORM_WINDOWS_FRAMEBUS_PRODUCER_H
#define AKVC_PLATFORM_WINDOWS_FRAMEBUS_PRODUCER_H

#include <cstdint>
#include <memory>
#include <string>

#include "akvc_protocol.h"  // akvc_frame_header_t

namespace akvc {
class FrameBusProducer;
}

namespace akvc::windows {

class FramebusProducer {
public:
    FramebusProducer();
    ~FramebusProducer();

    FramebusProducer(const FramebusProducer&) = delete;
    FramebusProducer& operator=(const FramebusProducer&) = delete;

    // Open the shared-memory ring. Tries open_existing first (attach to a region
    // created by the elevated helper); on failure, falls back to create() if
    // AKVC_ALLOW_FRAMEBUS_CREATE_FALLBACK is set. Throws on failure.
    void open();

    void close();

    int consumer_count() const;

    // Publish one frame. plane0 = Y, plane1 = UV (may be nullptr if unused).
    // Throws on publish failure.
    void publish(const akvc_frame_header_t& hdr,
                 const std::uint8_t* plane0,
                 const std::uint8_t* plane1);

    const std::string& last_error() const { return last_error_; }

private:
    static bool allow_create_fallback();

    std::unique_ptr<akvc::FrameBusProducer> producer_;
    std::string last_error_;
};

}  // namespace akvc::windows

#endif  // AKVC_PLATFORM_WINDOWS_FRAMEBUS_PRODUCER_H
