#pragma once

#include <pybind11/pybind11.h>

#include <cstdint>
#include <string>
#include <vector>

namespace py = pybind11;

namespace akvc::core_native {

struct NativeFormatSpec {
    std::int32_t fourcc;
    std::int32_t width;
    std::int32_t height;
    std::int32_t fps_num;
    std::int32_t fps_den;
};

struct NativeProviderInfo {
    std::string id;
    std::string name;
    std::vector<NativeFormatSpec> formats;
};

void bind_frame_types(py::module_& m);
void bind_test_pattern_provider(py::module_& m);
void bind_pipeline_ops(py::module_& m);
void bind_usb_provider(py::module_& m);
void bind_windows_framebus(py::module_& m);
void bind_macos_shm_sink(py::module_& m);
void bind_windows_helper_client(py::module_& m);
void bind_metrics(py::module_& m);
void bind_protocol(py::module_& m);
void bind_provider_factory(py::module_& m);
void bind_virtual_camera_session(py::module_& m);
void bind_runtime_host(py::module_& m);

}  // namespace akvc::core_native
