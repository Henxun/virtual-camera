// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Thin pybind11 binding over akvc::VirtualCamera, for the PySide6 desktop app.
// This is NOT the third-party interface (that is the C++ class API); it exists
// solely so apps/desktop can drive the C++ control layer from Python.

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>

#include "akvc/frame_input.h"
#include "akvc/pixel_format.h"
#include "akvc/status.h"
#include "akvc/virtual_camera.h"

namespace py = pybind11;

#ifdef __APPLE__
extern "C" int akvc_macos_system_extension_status_json(
    double timeout_seconds,
    char* json_buffer,
    size_t json_capacity,
    char* error_buffer,
    size_t error_capacity
);

extern "C" int akvc_macos_activate_system_extension(
    double timeout_seconds,
    char* error_buffer,
    size_t error_capacity
);

extern "C" int akvc_macos_direct_sender_list_devices_json(
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
);
#endif

namespace {

// Coerce an array-like to a uint8 contiguous buffer and dispatch to
// VirtualCamera::push_frame. Accepts HxW (gray, expanded to BGR), HxWx3 (BGR24
// by default), HxWx4 (BGRA32 by default). `format` overrides the inferred
// PixelFormat; `pts` is the 100ns presentation timestamp (0 = host clock).
akvc::Status push_frame_py(akvc::VirtualCamera& self,
                           py::array array,
                           py::object format_obj,
                           std::uint64_t pts) {
    py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast> arr(array);
    auto buf = arr.request();

    if (buf.ndim == 2) {
        const int h = static_cast<int>(buf.shape[0]);
        const int w = static_cast<int>(buf.shape[1]);
        const auto* src = static_cast<const std::uint8_t*>(buf.ptr);
        std::vector<std::uint8_t> bgr(static_cast<size_t>(w) * h * 3);
        for (int i = 0; i < w * h; ++i) {
            bgr[i * 3 + 0] = src[i];
            bgr[i * 3 + 1] = src[i];
            bgr[i * 3 + 2] = src[i];
        }
        akvc::FrameInput f{bgr.data(), w, h, w * 3, akvc::PixelFormat::BGR24, pts};
        return self.push_frame(f);
    }

    if (buf.ndim != 3) {
        throw std::runtime_error("frame array must be 2D (HxW) or 3D (HxWxC)");
    }
    const int h = static_cast<int>(buf.shape[0]);
    const int w = static_cast<int>(buf.shape[1]);
    const int c = static_cast<int>(buf.shape[2]);
    if (c != 3 && c != 4) {
        throw std::runtime_error("frame array channels must be 3 or 4");
    }

    akvc::PixelFormat fmt = (c == 4) ? akvc::PixelFormat::BGRA32 : akvc::PixelFormat::BGR24;
    if (!format_obj.is_none()) {
        fmt = format_obj.cast<akvc::PixelFormat>();
    }
    akvc::FrameInput f{static_cast<const std::uint8_t*>(buf.ptr), w, h, w * c, fmt, pts};
    return self.push_frame(f);
}

#ifdef __APPLE__
std::string macos_system_extension_status_json_py(double timeout_seconds) {
    std::vector<char> payload(16384, '\0');
    char error[1024] = {0};
    const int rc = akvc_macos_system_extension_status_json(
        timeout_seconds,
        payload.data(),
        payload.size(),
        error,
        sizeof(error)
    );
    if (rc != 0) {
        throw std::runtime_error(error[0] ? error : "macOS system extension status query failed");
    }
    return std::string(payload.data());
}

bool macos_activate_system_extension_py(double timeout_seconds) {
    char error[1024] = {0};
    const int rc = akvc_macos_activate_system_extension(timeout_seconds, error, sizeof(error));
    if (rc != 0) {
        throw std::runtime_error(error[0] ? error : "macOS system extension activation failed");
    }
    return true;
}

std::string macos_list_devices_json_py() {
    std::vector<char> payload(16384, '\0');
    char error[1024] = {0};
    const int rc = akvc_macos_direct_sender_list_devices_json(
        payload.data(),
        payload.size(),
        error,
        sizeof(error)
    );
    if (rc != 0) {
        throw std::runtime_error(error[0] ? error : "macOS device enumeration failed");
    }
    return std::string(payload.data());
}
#else
std::string macos_system_extension_status_json_py(double timeout_seconds) {
    (void)timeout_seconds;
    throw std::runtime_error("macOS system extension status is only available on macOS");
}

bool macos_activate_system_extension_py(double timeout_seconds) {
    (void)timeout_seconds;
    throw std::runtime_error("macOS system extension activation is only available on macOS");
}

std::string macos_list_devices_json_py() {
    throw std::runtime_error("macOS device enumeration is only available on macOS");
}
#endif

}  // namespace

PYBIND11_MODULE(akvc_camera, m) {
    m.doc() = "AK Virtual Camera control layer (C++ binding for the desktop app)";

    py::enum_<akvc::PixelFormat>(m, "PixelFormat")
        .value("BGR24", akvc::PixelFormat::BGR24)
        .value("BGRA32", akvc::PixelFormat::BGRA32)
        .value("RGB24", akvc::PixelFormat::RGB24)
        .value("NV12", akvc::PixelFormat::NV12);

    py::enum_<akvc::Status>(m, "Status")
        .value("Ok", akvc::Status::Ok)
        .value("NotStarted", akvc::Status::NotStarted)
        .value("DeviceNotFound", akvc::Status::DeviceNotFound)
        .value("HelperUnavailable", akvc::Status::HelperUnavailable)
        .value("ShmUnavailable", akvc::Status::ShmUnavailable)
        .value("InvalidFrame", akvc::Status::InvalidFrame)
        .value("ExtensionActivationFailed", akvc::Status::ExtensionActivationFailed)
        .value("StreamStartFailed", akvc::Status::StreamStartFailed)
        .value("Unknown", akvc::Status::Unknown);

    py::class_<akvc::VirtualCamera>(m, "VirtualCamera")
        .def(py::init<int, int, double, std::string, std::string>(),
             py::arg("width"),
             py::arg("height"),
             py::arg("fps"),
             py::arg("camera_name") = std::string("AK Virtual Camera"),
             py::arg("helper_exe") = std::string())
        .def("start", &akvc::VirtualCamera::start,
             py::call_guard<py::gil_scoped_release>())
        .def("stop", &akvc::VirtualCamera::stop,
             py::call_guard<py::gil_scoped_release>())
        .def("push_frame", &push_frame_py,
             py::arg("frame"),
             py::arg("format") = py::none(),
             py::arg("pts") = 0,
             py::call_guard<py::gil_scoped_release>())
        .def_property_readonly("started", &akvc::VirtualCamera::started)
        .def_property_readonly("consumer_count", &akvc::VirtualCamera::consumer_count)
        .def_property_readonly("last_error", &akvc::VirtualCamera::last_error);

    m.def("macos_system_extension_status_json",
          &macos_system_extension_status_json_py,
          py::arg("timeout_seconds") = 5.0);
    m.def("macos_activate_system_extension",
          &macos_activate_system_extension_py,
          py::arg("timeout_seconds") = 30.0);
    m.def("macos_list_devices_json",
          &macos_list_devices_json_py);
}
