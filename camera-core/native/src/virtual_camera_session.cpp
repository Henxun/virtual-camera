#define NOMINMAX

#include "akvc/core_native/frame_types.h"

#include <memory>
#include <stdexcept>
#include <string>

namespace akvc::core_native {

class NativeVirtualCameraSession {
public:
    NativeVirtualCameraSession(std::int32_t width,
                               std::int32_t height,
                               double fps,
                               std::string helper_exe = std::string())
        : width_(width),
          height_(height),
          fps_(fps),
          helper_exe_(std::move(helper_exe)) {}

    bool started() const {
        return started_;
    }

    std::int32_t consumer_count() const {
        if (producer_.is_none()) {
            return 0;
        }
        return py::int_(producer_.attr("consumer_count")).cast<std::int32_t>();
    }

    void start(const std::string& name = "AK Virtual Camera") {
        if (started_) {
            return;
        }
        ensure_native_objects();

        const bool helper_started = helper_client_.attr("start_service")(helper_exe_).cast<bool>();
        if (!helper_started) {
            throw std::runtime_error(last_helper_error("failed to start akvc helper"));
        }
        if (!helper_client_.attr("ping")().cast<bool>()) {
            throw std::runtime_error("akvc helper is not responding");
        }
        if (!mf_registered_) {
            if (!helper_client_.attr("register_mf")(name).cast<bool>()) {
                throw std::runtime_error(last_helper_error("failed to register MF virtual camera"));
            }
            mf_registered_ = true;
        }
        producer_.attr("open")();
        started_ = true;
    }

    Frame push_frame(py::array bgr) {
        if (!started_ || producer_.is_none()) {
            throw std::runtime_error("virtual camera is not started");
        }
        Frame frame = Frame::from_bgr(bgr, py::none(), ++seq_, FLAG_NONE);
        frame = resize_rgb24_frame(frame, width_, height_);
        frame = fps_regulator_.attr("process")(py::cast(frame)).cast<Frame>();
        frame = rgb24_to_nv12_frame(frame);
        producer_.attr("publish")(py::cast(frame));
        return frame;
    }

    void stop() {
        if (!started_) {
            return;
        }
        if (!producer_.is_none()) {
            producer_.attr("close")();
        }
        started_ = false;
    }

    void close() {
        stop();
        if (!helper_client_.is_none()) {
            helper_client_.attr("quit")();
        }
        mf_registered_ = false;
    }

private:
    void ensure_native_objects() {
        if (!helper_client_.is_none() && !producer_.is_none() && !fps_regulator_.is_none()) {
            return;
        }
        py::module_ native = py::module_::import("akvc._core_native");
        if (helper_client_.is_none()) {
            helper_client_ = native.attr("NativeWindowsHelperClient")();
        }
        if (producer_.is_none()) {
            producer_ = native.attr("NativeWindowsFrameBusProducer")();
        }
        if (fps_regulator_.is_none()) {
            fps_regulator_ = native.attr("NativeFpsRegulator")(fps_, 10.0);
        }
    }

    std::string last_helper_error(const std::string& fallback) const {
        if (helper_client_.is_none()) {
            return fallback;
        }
        try {
            py::object msg = helper_client_.attr("last_error_message");
            if (!msg.is_none()) {
                return py::str(msg).cast<std::string>();
            }
        } catch (const py::error_already_set&) {
        }
        return fallback;
    }

    std::int32_t width_;
    std::int32_t height_;
    double fps_;
    std::string helper_exe_;
    py::object helper_client_ = py::none();
    py::object producer_ = py::none();
    py::object fps_regulator_ = py::none();
    std::uint64_t seq_ = 0;
    bool started_ = false;
    bool mf_registered_ = false;
};

void bind_virtual_camera_session(py::module_& m) {
    py::class_<NativeVirtualCameraSession>(m, "NativeVirtualCameraSession")
        .def(py::init<std::int32_t, std::int32_t, double, std::string>(),
             py::arg("width"), py::arg("height"), py::arg("fps"), py::arg("helper_exe") = std::string())
        .def("start", &NativeVirtualCameraSession::start, py::arg("name") = std::string("AK Virtual Camera"))
        .def("push_frame", &NativeVirtualCameraSession::push_frame, py::arg("bgr"))
        .def("stop", &NativeVirtualCameraSession::stop)
        .def("close", &NativeVirtualCameraSession::close)
        .def_property_readonly("started", &NativeVirtualCameraSession::started)
        .def_property_readonly("consumer_count", &NativeVirtualCameraSession::consumer_count);
}

}  // namespace akvc::core_native
