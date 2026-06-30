#include "akvc/core_native/bindings.h"

namespace akvc::core_native {

}  // namespace akvc::core_native

PYBIND11_MODULE(_core_native, m) {
    m.doc() = "AKVC native core bindings";

    akvc::core_native::bind_frame_types(m);
    akvc::core_native::bind_test_pattern_provider(m);
    akvc::core_native::bind_pipeline_ops(m);
    akvc::core_native::bind_usb_provider(m);
    akvc::core_native::bind_windows_framebus(m);
    akvc::core_native::bind_macos_shm_sink(m);
    akvc::core_native::bind_windows_helper_client(m);
    akvc::core_native::bind_metrics(m);
    akvc::core_native::bind_protocol(m);
}
