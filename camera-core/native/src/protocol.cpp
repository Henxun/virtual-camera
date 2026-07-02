#include "akvc/core_native/bindings.h"

#include <cstddef>
#include <cstdint>

#include "akvc/framebus.h"
#include "akvc_protocol.h"

namespace akvc::core_native {

void bind_protocol(py::module_& m) {
    py::dict protocol;
    protocol["AKVC_MAGIC"] = py::int_(AKVC_MAGIC);
    protocol["AKVC_SCHEMA_VERSION"] = py::int_(AKVC_SCHEMA_VERSION);
    protocol["AKVC_RING_SLOTS"] = py::int_(AKVC_RING_SLOTS);
    protocol["AKVC_DEFAULT_SLOT_SIZE"] = py::int_(AKVC_DEFAULT_SLOT_SIZE);
    protocol["RING_CONTROL_SIZE"] = py::int_(sizeof(akvc_ring_control_t));
    protocol["FRAME_HEADER_SIZE"] = py::int_(sizeof(akvc_frame_header_t));
    protocol["REGION_SIZE"] = py::int_(AKVC_DEFAULT_REGION_SIZE);
    protocol["FRAMEBUS_PATH_ENV"] = py::str(AKVC_FRAMEBUS_PATH_ENV);
    protocol["FRAMEBUS_DIR_ENV"] = py::str(AKVC_FRAMEBUS_DIR_ENV);
    protocol["FRAMEBUS_DEFAULT_SUBDIR"] = py::str(AKVC_FRAMEBUS_DEFAULT_SUBDIR);
    protocol["FRAMEBUS_DEFAULT_FILE"] = py::str(AKVC_FRAMEBUS_DEFAULT_FILE);
    protocol["FRAMEBUS_DEFAULT_PATH"] = py::cast(default_framebus_file_path());
    protocol["OFF_PRODUCER_SEQ"] = py::int_(offsetof(akvc_ring_control_t, producer_seq));
    protocol["OFF_WRITER_PID"] = py::int_(offsetof(akvc_ring_control_t, writer_pid));
    protocol["OFF_PRODUCER_HEARTBEAT"] = py::int_(offsetof(akvc_ring_control_t, producer_heartbeat));
    protocol["FRAME_HEADER_OFF_SEQ_HEAD"] = py::int_(offsetof(akvc_frame_header_t, seq_head));
    protocol["FRAME_HEADER_OFF_SEQ_TAIL"] = py::int_(offsetof(akvc_frame_header_t, seq_tail));
    m.attr("NativeFrameBusProtocol") = protocol;
}

}  // namespace akvc::core_native
