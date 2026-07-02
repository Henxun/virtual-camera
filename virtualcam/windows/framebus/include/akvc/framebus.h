// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Frame Bus (Windows)
//
// Single-producer / multi-consumer ring buffer over a named file mapping.
// - Producer: created once by the desktop FrameWorker subprocess.
// - Consumers: each DirectShow Source Filter instance (in-proc) opens it
//   read-only and waits on the named event.
//
// Tear protection: each frame slot has seq_head and seq_tail. Readers
// retry up to 3 times if they don't match, then drop the frame.
//
// ACL: kernel objects are created with a SDDL granting:
//   - BUILTIN\Administrators (BA): full
//   - LocalSystem (SY): full
//   - AppContainer (AC): read+write   — for future MF Frame Server (LowBox)
//   - ALL_APP_PACKAGES (S-1-15-2-1): read+write
//
// Phase 2 keeps the broad ACL even though MF is not yet wired up; this avoids
// changing the protocol when Phase 3 lands.

#ifndef AKVC_FRAMEBUS_H
#define AKVC_FRAMEBUS_H

#include <cstdint>
#include <string>
#include <vector>
#include <windows.h>

#include "akvc_errors.h"
#include "akvc_protocol.h"

namespace akvc {

std::wstring default_framebus_file_path();

struct FrameView {
    const akvc_frame_header_t* header = nullptr;
    const uint8_t*             plane0 = nullptr;
    const uint8_t*             plane1 = nullptr;
};

struct FrameBusErrorInfo {
    DWORD       win32_error = ERROR_SUCCESS;
    const char* operation = nullptr;
    const wchar_t* object_name = nullptr;
};

// Common base — opens or creates the named mapping/event/mutex.
class FrameBusBase {
public:
    FrameBusBase()                              = default;
    FrameBusBase(const FrameBusBase&)            = delete;
    FrameBusBase& operator=(const FrameBusBase&) = delete;
    virtual ~FrameBusBase();

    bool is_open() const noexcept { return base_ != nullptr; }

protected:
    HANDLE   mapping_ = nullptr;
    HANDLE   event_   = nullptr;
    HANDLE   mutex_   = nullptr;
    HANDLE   file_    = nullptr;
    uint8_t* base_    = nullptr;   // pointer to mapped region
    uint32_t region_size_ = 0;
    FrameBusErrorInfo last_error_{};

    void set_last_error(DWORD win32_error,
                        const char* operation,
                        const wchar_t* object_name) noexcept {
        last_error_.win32_error = win32_error;
        last_error_.operation = operation;
        last_error_.object_name = object_name;
    }

public:
    const FrameBusErrorInfo& last_error() const noexcept { return last_error_; }

protected:
    akvc_ring_control_t* control() noexcept {
        return reinterpret_cast<akvc_ring_control_t*>(base_);
    }
    const akvc_ring_control_t* control() const noexcept {
        return reinterpret_cast<const akvc_ring_control_t*>(base_);
    }

    uint8_t* slot_ptr(uint32_t index) noexcept {
        return base_
            + sizeof(akvc_ring_control_t)
            + static_cast<size_t>(index) * AKVC_DEFAULT_SLOT_SIZE;
    }
    const uint8_t* slot_ptr(uint32_t index) const noexcept {
        return base_
            + sizeof(akvc_ring_control_t)
            + static_cast<size_t>(index) * AKVC_DEFAULT_SLOT_SIZE;
    }
};

// Producer — only one process should hold this open.
class FrameBusProducer final : public FrameBusBase {
public:
    // Creates / opens the shared region. If the region already exists and
    // schema matches, takes it over (writer_pid is updated).
    akvc_status_t create();

    // Attaches to an existing shared region created by another producer-like
    // owner (for example the elevated helper). Uses open-only semantics.
    akvc_status_t open_existing();

    // Publishes a single frame.
    // header.fourcc / width / height / stride / plane_size must be set.
    // plane data is provided as up to 2 contiguous buffers (NV12 has 2 planes,
    // YUY2/RGB24 use only plane0). plane_data[i] may be nullptr if size==0.
    akvc_status_t publish(const akvc_frame_header_t& header,
                          const uint8_t* const plane_data[2]);

    // Publishes a placeholder (black NV12) frame; useful when the producer
    // wants to keep the device alive while no source is active.
    akvc_status_t publish_placeholder(uint32_t width,
                                      uint32_t height,
                                      uint64_t pts_100ns,
                                      uint64_t seq);

    // Expose the ring control block for direct field reads/writes
    // (e.g. heartbeat monitoring by Helper process).
    akvc_ring_control_t* ctrl() noexcept {
        return reinterpret_cast<akvc_ring_control_t*>(base_);
    }

    void close();
};

// Consumer — multiple processes may open simultaneously.
class FrameBusConsumer final : public FrameBusBase {
public:
    akvc_status_t open();

    // Waits up to timeout_ms for a new frame. On success, fills `out` with
    // pointers into the shared region (no copy). The pointers stay valid
    // until the next `wait_frame` call by THIS consumer (slots may be
    // overwritten by the producer in the meantime; reader copies promptly).
    akvc_status_t wait_frame(uint32_t timeout_ms, FrameView& out);

    void close();

private:
    uint64_t last_seen_seq_ = 0;
};

// Build a SDDL string for our named kernel objects.
std::wstring build_framebus_sddl();

// Translate a Win32 last error / HRESULT to an akvc_status_t (best-effort).
akvc_status_t translate_win32(DWORD last_error);

}  // namespace akvc

#endif  // AKVC_FRAMEBUS_H
