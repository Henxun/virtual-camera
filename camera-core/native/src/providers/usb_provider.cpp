#include "akvc/core_native/frame_types.h"

#include <chrono>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace akvc::core_native {

class NativeFpsRegulator {
public:
    NativeFpsRegulator(double target_fps, double jitter_pct)
        : target_fps_(target_fps),
          period_(1.0 / target_fps),
          jitter_(jitter_pct / 100.0) {}

    void reconfigure(const py::dict& cfg) {
        if (cfg.contains("target_fps")) {
            target_fps_ = py::float_(cfg["target_fps"]);
            period_ = 1.0 / target_fps_;
        }
    }

    Frame process(const Frame& frame) {
        const auto now = std::chrono::steady_clock::now();
        if (!last_t_.has_value()) {
            last_t_ = now;
            return frame;
        }
        const double elapsed = std::chrono::duration<double>(now - *last_t_).count();
        const double target = period_ * (1.0 - jitter_);
        if (elapsed < target) {
            std::this_thread::sleep_for(std::chrono::duration<double>(target - elapsed));
        }
        last_t_ = std::chrono::steady_clock::now();
        return frame;
    }

private:
    double target_fps_;
    double period_;
    double jitter_;
    std::optional<std::chrono::steady_clock::time_point> last_t_;
};

class NativeUsbCaptureOpener {
public:
    NativeUsbCaptureOpener(std::int32_t width, std::int32_t height, std::int32_t fps)
        : width_(width),
          height_(height),
          fps_(fps) {}

    py::object open(std::int32_t device_index, const std::string& backend, const py::object& cv2_module, const py::object& capture_factory) const {
        py::list backends = resolve_backends(backend, cv2_module);
        py::object last_err = py::none();
        for (const auto& backend_id : backends) {
            py::object capture;
            try {
                capture = capture_factory(device_index, backend_id);
            } catch (const py::error_already_set& exc) {
                last_err = py::str(exc.value());
                continue;
            }

            if (capture.is_none()) {
                continue;
            }

            bool opened = false;
            try {
                opened = capture.attr("isOpened")().cast<bool>();
            } catch (const py::error_already_set& exc) {
                last_err = py::str(exc.value());
            }
            if (opened) {
                configure_capture(capture, cv2_module);
                return capture;
            }
            safe_release(capture);
        }
        throw std::runtime_error(open_error_message(device_index, last_err));
    }

private:
    py::list resolve_backends(const std::string& backend, const py::object& cv2_module) const {
        const auto cap_msmf = cv2_module.attr("CAP_MSMF");
        const auto cap_dshow = cv2_module.attr("CAP_DSHOW");
        const auto cap_any = cv2_module.attr("CAP_ANY");
        py::list backends;
        if (backend == "msmf") {
            backends.append(cap_msmf);
            backends.append(cap_dshow);
            backends.append(cap_any);
            return backends;
        }
        if (backend == "dshow") {
            backends.append(cap_dshow);
            backends.append(cap_msmf);
            backends.append(cap_any);
            return backends;
        }
        if (backend == "any") {
            backends.append(cap_any);
            backends.append(cap_msmf);
            backends.append(cap_dshow);
            return backends;
        }
        backends.append(cap_any);
        return backends;
    }

    void configure_capture(const py::object& capture, const py::object& cv2_module) const {
        capture.attr("set")(cv2_module.attr("CAP_PROP_FRAME_WIDTH"), width_);
        capture.attr("set")(cv2_module.attr("CAP_PROP_FRAME_HEIGHT"), height_);
        capture.attr("set")(cv2_module.attr("CAP_PROP_FPS"), fps_);
        safe_set(capture, cv2_module.attr("CAP_PROP_BUFFERSIZE"), 1);
        safe_set(capture, cv2_module.attr("CAP_PROP_READ_TIMEOUT_MSEC"), 250);
    }

    static void safe_set(const py::object& capture, const py::object& prop, int value) {
        try {
            capture.attr("set")(prop, value);
        } catch (const py::error_already_set&) {
        }
    }

    static void safe_release(const py::object& capture) {
        try {
            capture.attr("release")();
        } catch (const py::error_already_set&) {
        }
    }

    static std::string open_error_message(std::int32_t device_index, const py::object& last_err) {
        std::ostringstream oss;
        oss << "Cannot open USB camera " << device_index << ": ";
        if (last_err.is_none()) {
            oss << "None";
        } else {
            oss << py::str(last_err).cast<std::string>();
        }
        return oss.str();
    }

    std::int32_t width_;
    std::int32_t height_;
    std::int32_t fps_;
};

class NativeUsbDeviceProber {
public:
    py::list list_indices(std::int32_t max_probe, const py::object& cv2_module, const py::object& capture_factory) const {
        py::list out;
        for (std::int32_t device_index = 0; device_index < max_probe; ++device_index) {
            if (probe_backend(device_index, cv2_module.attr("CAP_MSMF"), capture_factory)) {
                out.append(device_index);
                continue;
            }
            if (probe_backend(device_index, cv2_module.attr("CAP_DSHOW"), capture_factory)) {
                out.append(device_index);
            }
        }
        return out;
    }

private:
    static bool probe_backend(std::int32_t device_index, const py::object& backend_id, const py::object& capture_factory) {
        py::object capture;
        try {
            capture = capture_factory(device_index, backend_id);
        } catch (const py::error_already_set&) {
            return false;
        }
        if (capture.is_none()) {
            return false;
        }

        bool opened = false;
        try {
            opened = capture.attr("isOpened")().cast<bool>();
        } catch (const py::error_already_set&) {
            opened = false;
        }
        safe_release(capture);
        return opened;
    }

    static void safe_release(const py::object& capture) {
        try {
            capture.attr("release")();
        } catch (const py::error_already_set&) {
        }
    }
};

class NativeUsbFrameReader {
public:
    NativeUsbFrameReader(std::int32_t width, std::int32_t height)
        : width_(width),
          height_(height) {}

    void clear_stop() {
        stop_requested_ = false;
    }

    void request_stop() {
        stop_requested_ = true;
    }

    Frame read(const py::object& capture) {
        if (capture.is_none()) {
            return error_frame("not opened");
        }
        if (stop_requested_) {
            return error_frame("stop requested");
        }

        auto frame = read_once(capture);
        if (frame.has_value()) {
            return *frame;
        }
        if (stop_requested_) {
            return error_frame("stop requested");
        }

        {
            py::gil_scoped_release release;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        if (stop_requested_) {
            return error_frame("stop requested");
        }

        frame = read_once(capture);
        if (frame.has_value()) {
            return *frame;
        }
        return error_frame("read failed");
    }

private:
    std::optional<Frame> read_once(const py::object& capture) {
        py::tuple result = capture.attr("read")().cast<py::tuple>();
        if (result.size() != 2) {
            throw py::value_error("VideoCapture.read() must return (ok, frame)");
        }
        if (!result[0].cast<bool>()) {
            return std::nullopt;
        }
        py::object bgr = result[1];
        if (bgr.is_none()) {
            return std::nullopt;
        }
        seq_ += 1;
        return Frame::from_bgr(bgr, py::none(), seq_, FLAG_NONE);
    }

    Frame error_frame(const char* reason) const {
        auto data = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(width_) * height_ * 3);
        std::memset(data.mutable_data(), 0, static_cast<std::size_t>(data.nbytes()));
        py::dict meta;
        meta["reason"] = reason;
        return Frame(
            width_,
            height_,
            FOURCC_RGB24,
            std::move(data),
            now_pts_100ns(),
            seq_,
            FLAG_ERROR,
            {width_ * 3, 0},
            {width_ * height_ * 3, 0},
            std::move(meta));
    }

    std::int32_t width_;
    std::int32_t height_;
    std::uint64_t seq_ = 0;
    bool stop_requested_ = false;
};

void bind_usb_provider(py::module_& m) {
    py::class_<NativeFpsRegulator>(m, "NativeFpsRegulator")
        .def(py::init<double, double>(), py::arg("target_fps"), py::arg("jitter_pct") = 10.0)
        .def("reconfigure", &NativeFpsRegulator::reconfigure)
        .def("process", &NativeFpsRegulator::process);

    py::class_<NativeUsbCaptureOpener>(m, "NativeUsbCaptureOpener")
        .def(py::init<std::int32_t, std::int32_t, std::int32_t>(), py::arg("width"), py::arg("height"), py::arg("fps"))
        .def("open", &NativeUsbCaptureOpener::open, py::arg("device_index"), py::arg("backend"), py::arg("cv2_module"), py::arg("capture_factory"));

    py::class_<NativeUsbDeviceProber>(m, "NativeUsbDeviceProber")
        .def(py::init<>())
        .def("list_indices", &NativeUsbDeviceProber::list_indices, py::arg("max_probe"), py::arg("cv2_module"), py::arg("capture_factory"));

    py::class_<NativeUsbFrameReader>(m, "NativeUsbFrameReader")
        .def(py::init<std::int32_t, std::int32_t>(), py::arg("width"), py::arg("height"))
        .def("clear_stop", &NativeUsbFrameReader::clear_stop)
        .def("request_stop", &NativeUsbFrameReader::request_stop)
        .def("read", &NativeUsbFrameReader::read, py::arg("capture"));
}

}  // namespace akvc::core_native
