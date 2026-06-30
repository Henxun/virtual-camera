#define NOMINMAX

#include "akvc/core_native/frame_types.h"

#include <cstdlib>
#include <memory>
#include <sstream>
#include <stdexcept>

#ifdef _WIN32
#include <windows.h>
#endif

#include "akvc/framebus.h"

namespace akvc::core_native {

class NativeWindowsFrameBusProducer {
public:
    NativeWindowsFrameBusProducer() = default;

    void open() {
        ensure_windows();
        producer_ = std::make_unique<akvc::FrameBusProducer>();
        auto st = producer_->open_existing();
        if (st != AKVC_OK && allow_create_fallback()) {
            producer_->close();
            st = producer_->create();
        }
        if (st != AKVC_OK) {
            raise_on_status(st, "failed to open Windows frame bus");
        }
    }

    void close() {
        if (producer_) {
            producer_->close();
            producer_.reset();
        }
    }

    int consumer_count() const {
        if (!producer_ || !producer_->ctrl()) {
            return 0;
        }
        return static_cast<int>(producer_->ctrl()->consumer_count);
    }

    void publish(const Frame& frame) {
        ensure_open();
        if (frame.fourcc != FOURCC_NV12) {
            throw py::value_error("only NV12 supported in Phase 2");
        }

        akvc_frame_header_t hdr{};
        hdr.fourcc = frame.fourcc;
        hdr.width = static_cast<uint32_t>(frame.width);
        hdr.height = static_cast<uint32_t>(frame.height);
        hdr.stride[0] = static_cast<uint32_t>(frame.stride.first ? frame.stride.first : frame.width);
        hdr.stride[1] = static_cast<uint32_t>(frame.stride.second ? frame.stride.second : frame.width);
        hdr.plane_size[0] = static_cast<uint32_t>(frame.plane_size.first ? frame.plane_size.first : frame.width * frame.height);
        hdr.plane_size[1] = static_cast<uint32_t>(frame.plane_size.second ? frame.plane_size.second : frame.width * frame.height / 2);
        hdr.flags = frame.flags;
        hdr.pts_100ns = static_cast<uint64_t>(frame.pts_100ns);

        auto data = frame.data.unchecked<1>();
        const uint8_t* planes[2] = {
            reinterpret_cast<const uint8_t*>(data.data(0)),
            reinterpret_cast<const uint8_t*>(data.data(0)) + hdr.plane_size[0],
        };
        const auto st = producer_->publish(hdr, planes);
        if (st != AKVC_OK) {
            raise_on_status(st, "failed to publish frame to Windows frame bus");
        }
    }

private:
    static bool allow_create_fallback() {
        const char* value = std::getenv("AKVC_ALLOW_FRAMEBUS_CREATE_FALLBACK");
        if (value == nullptr) {
            return false;
        }
        return value[0] == '1' || value[0] == 't' || value[0] == 'T' || value[0] == 'y' || value[0] == 'Y';
    }

    static void ensure_windows() {
#ifdef _WIN32
        return;
#else
        throw std::runtime_error("Windows frame bus is only available on Windows");
#endif
    }

    void ensure_open() const {
        if (!producer_) {
            throw std::runtime_error("frame bus producer is not open");
        }
    }

    [[noreturn]] void raise_on_status(akvc_status_t st, const char* message) const {
        std::ostringstream oss;
        oss << message << " (status=" << st;
        if (producer_) {
            const auto& err = producer_->last_error();
            if (err.operation) {
                oss << ", op=" << err.operation;
            }
            if (err.object_name) {
                oss << ", object=" << py::cast(err.object_name).cast<std::string>();
            }
            oss << ", win32=" << err.win32_error;
        }
        oss << ")";
        throw py::value_error(oss.str());
    }

    std::unique_ptr<akvc::FrameBusProducer> producer_;
};

void bind_windows_framebus(py::module_& m) {
    py::class_<NativeWindowsFrameBusProducer>(m, "NativeWindowsFrameBusProducer")
        .def(py::init<>())
        .def("open", &NativeWindowsFrameBusProducer::open)
        .def("close", &NativeWindowsFrameBusProducer::close)
        .def("publish", &NativeWindowsFrameBusProducer::publish)
        .def_property_readonly("consumer_count", &NativeWindowsFrameBusProducer::consumer_count);
}

}  // namespace akvc::core_native
