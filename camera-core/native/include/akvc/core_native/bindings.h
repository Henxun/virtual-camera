#pragma once

#include <pybind11/pybind11.h>

namespace py = pybind11;

namespace akvc::core_native {

void bind_frame_types(py::module_& m);
void bind_test_pattern_provider(py::module_& m);
void bind_pipeline_ops(py::module_& m);
void bind_usb_provider(py::module_& m);
void bind_windows_framebus(py::module_& m);
void bind_macos_shm_sink(py::module_& m);
void bind_windows_helper_client(py::module_& m);
void bind_metrics(py::module_& m);
void bind_protocol(py::module_& m);

}  // namespace akvc::core_native
