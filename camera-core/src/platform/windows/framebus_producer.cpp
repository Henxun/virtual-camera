// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "akvc/platform/windows/framebus_producer.h"

#include <cstdlib>
#include <sstream>
#include <stdexcept>

#include "akvc/framebus.h"  // akvc::FrameBusProducer

namespace akvc::windows {

FramebusProducer::FramebusProducer() = default;

FramebusProducer::~FramebusProducer() = default;

bool FramebusProducer::allow_create_fallback() {
    const char* value = std::getenv("AKVC_ALLOW_FRAMEBUS_CREATE_FALLBACK");
    if (value == nullptr) {
        return false;
    }
    return value[0] == '1' || value[0] == 't' || value[0] == 'T' ||
           value[0] == 'y' || value[0] == 'Y';
}

void FramebusProducer::open() {
    if (!producer_) {
        producer_ = std::make_unique<akvc::FrameBusProducer>();
    }
    auto st = producer_->open_existing();
    if (st != AKVC_OK && allow_create_fallback()) {
        producer_->close();
        st = producer_->create();
    }
    if (st != AKVC_OK) {
        std::ostringstream oss;
        oss << "failed to open Windows frame bus (status=" << st;
        const auto& err = producer_->last_error();
        if (err.operation) {
            oss << ", op=" << err.operation;
        }
        oss << ", win32=" << err.win32_error << ")";
        last_error_ = oss.str();
        throw std::runtime_error(last_error_);
    }
}

void FramebusProducer::close() {
    if (producer_) {
        producer_->close();
        producer_.reset();
    }
}

int FramebusProducer::consumer_count() const {
    if (!producer_ || !producer_->ctrl()) {
        return 0;
    }
    return static_cast<int>(producer_->ctrl()->consumer_count);
}

void FramebusProducer::publish(const akvc_frame_header_t& hdr,
                               const std::uint8_t* plane0,
                               const std::uint8_t* plane1) {
    if (!producer_) {
        last_error_ = "frame bus producer is not open";
        throw std::runtime_error(last_error_);
    }
    const std::uint8_t* planes[2] = {plane0, plane1};
    const auto st = producer_->publish(hdr, planes);
    if (st != AKVC_OK) {
        std::ostringstream oss;
        oss << "failed to publish frame to Windows frame bus (status=" << st;
        const auto& err = producer_->last_error();
        if (err.operation) {
            oss << ", op=" << err.operation;
        }
        oss << ", win32=" << err.win32_error << ")";
        last_error_ = oss.str();
        throw std::runtime_error(last_error_);
    }
}

}  // namespace akvc::windows
