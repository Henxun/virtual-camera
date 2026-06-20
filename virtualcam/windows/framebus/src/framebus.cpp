// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "akvc/framebus.h"

#include <sddl.h>
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>

namespace akvc {

namespace {

struct ScopedSecurityDescriptor {
    PSECURITY_DESCRIPTOR psd = nullptr;
    SECURITY_ATTRIBUTES   sa{};

    ~ScopedSecurityDescriptor() {
        if (psd) ::LocalFree(psd);
    }

    bool init() {
        const auto sddl = build_framebus_sddl();
        if (!::ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.c_str(),
                SDDL_REVISION_1,
                &psd,
                nullptr)) {
            return false;
        }
        sa.nLength              = sizeof(sa);
        sa.lpSecurityDescriptor = psd;
        sa.bInheritHandle       = FALSE;
        return true;
    }
};

uint64_t now_pts_100ns() noexcept {
    FILETIME ft;
    ::GetSystemTimePreciseAsFileTime(&ft);
    ULARGE_INTEGER u;
    u.LowPart  = ft.dwLowDateTime;
    u.HighPart = ft.dwHighDateTime;
    return u.QuadPart;
}

}  // namespace

akvc_status_t translate_win32(DWORD le) {
    switch (le) {
        case ERROR_SUCCESS:        return AKVC_OK;
        case ERROR_FILE_NOT_FOUND: return E_AKVC_FRAMEBUS_OPEN_FAILED;
        case ERROR_ACCESS_DENIED:  return E_AKVC_FRAMEBUS_OPEN_FAILED;
        case WAIT_TIMEOUT:         return E_AKVC_FRAMEBUS_TIMEOUT;
        default:                   return E_AKVC_FRAMEBUS_OPEN_FAILED;
    }
}

FrameBusBase::~FrameBusBase() {
    if (base_)    { ::UnmapViewOfFile(base_); base_    = nullptr; }
    if (mapping_) { ::CloseHandle(mapping_);  mapping_ = nullptr; }
    if (event_)   { ::CloseHandle(event_);    event_   = nullptr; }
    if (mutex_)   { ::CloseHandle(mutex_);    mutex_   = nullptr; }
}

// ---------------- Producer ----------------

akvc_status_t FrameBusProducer::create() {
    if (is_open()) return AKVC_OK;

    ScopedSecurityDescriptor sd;
    if (!sd.init()) return translate_win32(::GetLastError());

    region_size_ = AKVC_DEFAULT_REGION_SIZE;

    // CreateFileMapping returns existing handle if name exists; we tolerate that.
    mapping_ = ::CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        &sd.sa,
        PAGE_READWRITE,
        0,
        region_size_,
        L"Global\\akvc-frames-v1");
    if (!mapping_) return translate_win32(::GetLastError());

    base_ = reinterpret_cast<uint8_t*>(
        ::MapViewOfFile(mapping_, FILE_MAP_ALL_ACCESS, 0, 0, region_size_));
    if (!base_) return translate_win32(::GetLastError());

    event_ = ::CreateEventW(&sd.sa, /*manualReset*/ FALSE, FALSE,
                            L"Global\\akvc-frames-evt-v1");
    if (!event_) return translate_win32(::GetLastError());

    mutex_ = ::CreateMutexW(&sd.sa, FALSE, L"Global\\akvc-frames-mtx-v1");
    if (!mutex_) return translate_win32(::GetLastError());

    // Initialize control block if newly created (zeroed by OS).
    auto* ctrl = control();
    if (ctrl->magic != AKVC_MAGIC) {
        ctrl->magic            = AKVC_MAGIC;
        ctrl->schema_version   = AKVC_SCHEMA_VERSION;
        ctrl->slot_count       = AKVC_RING_SLOTS;
        ctrl->slot_size        = AKVC_DEFAULT_SLOT_SIZE;
        ctrl->producer_seq     = 0;
        ctrl->consumer_count   = 0;
        ctrl->writer_pid       = ::GetCurrentProcessId();
        ctrl->created_pts_100ns = now_pts_100ns();
    } else {
        // Schema check; refuse to take over a mismatched ring.
        if (ctrl->schema_version != AKVC_SCHEMA_VERSION ||
            ctrl->slot_count     != AKVC_RING_SLOTS    ||
            ctrl->slot_size      != AKVC_DEFAULT_SLOT_SIZE) {
            close();
            return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;
        }
        ctrl->writer_pid = ::GetCurrentProcessId();
    }
    return AKVC_OK;
}

akvc_status_t FrameBusProducer::publish(const akvc_frame_header_t& header_in,
                                       const uint8_t* const plane_data[2]) {
    if (!is_open()) return E_AKVC_FRAMEBUS_NO_PRODUCER;

    auto* ctrl  = control();
    const uint64_t next_seq   = ctrl->producer_seq + 1;
    const uint32_t slot_index = static_cast<uint32_t>((next_seq - 1) % ctrl->slot_count);

    // Total payload size check.
    const uint32_t header_bytes = static_cast<uint32_t>(sizeof(akvc_frame_header_t));
    const uint32_t plane_total  = header_in.plane_size[0] + header_in.plane_size[1];
    if (header_bytes + plane_total > AKVC_DEFAULT_SLOT_SIZE) {
        return E_AKVC_FRAMEBUS_PUBLISH_FAILED;
    }

    // Acquire mutex to serialize multi-step writes (defensive; producer is single).
    DWORD wr = ::WaitForSingleObject(mutex_, 50);
    if (wr != WAIT_OBJECT_0 && wr != WAIT_ABANDONED) {
        return E_AKVC_FRAMEBUS_PUBLISH_FAILED;
    }

    uint8_t* slot = slot_ptr(slot_index);
    auto*    hdr  = reinterpret_cast<akvc_frame_header_t*>(slot);

    // Write header_in but rewrite seq fields and offsets.
    *hdr = header_in;
    hdr->magic          = AKVC_MAGIC;
    hdr->schema_version = AKVC_SCHEMA_VERSION;
    hdr->plane_offset[0] = (header_in.plane_size[0] > 0) ? header_bytes : 0;
    hdr->plane_offset[1] = (header_in.plane_size[1] > 0)
                           ? header_bytes + header_in.plane_size[0]
                           : 0;
    hdr->seq_head = next_seq;
    hdr->seq_tail = 0;  // sentinel until copy done

    // Memory fence before payload write (prevents the reader from observing
    // header updates without payload).
    MemoryBarrier();

    if (header_in.plane_size[0] && plane_data[0]) {
        std::memcpy(slot + hdr->plane_offset[0], plane_data[0], header_in.plane_size[0]);
    }
    if (header_in.plane_size[1] && plane_data[1]) {
        std::memcpy(slot + hdr->plane_offset[1], plane_data[1], header_in.plane_size[1]);
    }

    // Publish: write seq_tail, advance producer_seq, update heartbeat, signal.
    MemoryBarrier();
    hdr->seq_tail = next_seq;
    MemoryBarrier();
    ctrl->producer_seq = next_seq;
    ctrl->writer_pid   = ::GetCurrentProcessId();
    ctrl->producer_heartbeat = now_pts_100ns();

    ::ReleaseMutex(mutex_);
    ::SetEvent(event_);
    return AKVC_OK;
}

akvc_status_t FrameBusProducer::publish_placeholder(uint32_t width,
                                                   uint32_t height,
                                                   uint64_t pts_100ns,
                                                   uint64_t seq) {
    akvc_frame_header_t hdr{};
    hdr.fourcc        = AKVC_FOURCC_NV12;
    hdr.width         = width;
    hdr.height        = height;
    hdr.stride[0]     = width;
    hdr.stride[1]     = width;
    hdr.plane_size[0] = width * height;
    hdr.plane_size[1] = width * height / 2;
    hdr.flags         = AKVC_FLAG_PLACEHOLDER;
    hdr.pts_100ns     = pts_100ns;
    (void)seq;  // seq is assigned by publish() based on producer_seq

    static thread_local std::vector<uint8_t> y_buf;
    static thread_local std::vector<uint8_t> uv_buf;
    y_buf.assign(static_cast<size_t>(hdr.plane_size[0]), 0);
    uv_buf.assign(static_cast<size_t>(hdr.plane_size[1]), 128);  // neutral chroma

    const uint8_t* planes[2] = { y_buf.data(), uv_buf.data() };
    return publish(hdr, planes);
}

void FrameBusProducer::close() {
    if (base_)    { ::UnmapViewOfFile(base_); base_ = nullptr; }
    if (mapping_) { ::CloseHandle(mapping_);  mapping_ = nullptr; }
    if (event_)   { ::CloseHandle(event_);    event_ = nullptr; }
    if (mutex_)   { ::CloseHandle(mutex_);    mutex_ = nullptr; }
    region_size_ = 0;
}

// ---------------- Consumer ----------------

akvc_status_t FrameBusConsumer::open() {
    if (is_open()) return AKVC_OK;

    mapping_ = ::OpenFileMappingW(FILE_MAP_READ, FALSE, L"Global\\akvc-frames-v1");
    if (!mapping_) {
        DWORD le = ::GetLastError();
        // Diagnostic: log why the frame server can't open the SHM.
        wchar_t path[MAX_PATH] = {0};
        HMODULE m = ::GetModuleHandleW(L"akvc-mf");
        if (!m) m = ::GetModuleHandleW(nullptr);
        if (m && ::GetModuleFileNameW(m, path, MAX_PATH)) {
            wchar_t* sep = wcsrchr(path, L'\\');
            if (sep) wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
            FILE* f = nullptr;
            if (_wfopen_s(&f, path, L"a") == 0 && f) {
                DWORD pid = ::GetCurrentProcessId();
                DWORD sid = 0;
                ::ProcessIdToSessionId(pid, &sid);
                fprintf(f, "[FrameBusConsumer::open] OpenFileMappingW FAILED le=%lu pid=%lu session=%lu name=Global\\akvc-frames-v1\n",
                        le, pid, sid);
                fclose(f);
            }
        }
        return translate_win32(le);
    }

    base_ = reinterpret_cast<uint8_t*>(
        ::MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, 0));
    if (!base_) return translate_win32(::GetLastError());

    // Determine region size from control block, fall back to default.
    auto* ctrl = control();
    if (ctrl->magic != AKVC_MAGIC ||
        ctrl->schema_version != AKVC_SCHEMA_VERSION) {
        close();
        return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;
    }
    region_size_ = sizeof(akvc_ring_control_t)
                 + ctrl->slot_count * ctrl->slot_size;

    event_ = ::OpenEventW(SYNCHRONIZE | EVENT_MODIFY_STATE, FALSE,
                          L"Global\\akvc-frames-evt-v1");
    if (!event_) {
        DWORD le = ::GetLastError();
        close();
        return translate_win32(le);
    }

    mutex_ = nullptr;  // consumer doesn't need the mutex (lock-free read).

    last_seen_seq_ = 0;
    return AKVC_OK;
}

akvc_status_t FrameBusConsumer::wait_frame(uint32_t timeout_ms, FrameView& out) {
    if (!is_open()) return E_AKVC_FRAMEBUS_OPEN_FAILED;
    out = FrameView{};

    auto* ctrl = control();

    // One-time diagnostic: log the control block the frame server sees.
    static std::atomic<bool> logged_once{false};
    if (!logged_once.exchange(true)) {
        wchar_t path[MAX_PATH] = {0};
        HMODULE m = ::GetModuleHandleW(L"akvc-mf");
        if (m && ::GetModuleFileNameW(m, path, MAX_PATH)) {
            wchar_t* sep = wcsrchr(path, L'\\');
            if (sep) wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
            FILE* f = nullptr;
            if (_wfopen_s(&f, path, L"a") == 0 && f) {
                fprintf(f, "[FrameBusConsumer::wait_frame first call] magic=0x%08X schema=%u slots=%u slot_size=%u pseq=%llu writer_pid=%lu\n",
                        ctrl->magic, ctrl->schema_version, ctrl->slot_count, ctrl->slot_size,
                        (unsigned long long)ctrl->producer_seq, ctrl->writer_pid);
                fclose(f);
            }
        }
    }

    // If a new frame is already available, don't even wait.
    if (ctrl->producer_seq != last_seen_seq_) {
        // fall-through to read
    } else {
        DWORD wr = ::WaitForSingleObject(event_, timeout_ms);
        if (wr == WAIT_TIMEOUT) {
            // Re-check; producer may have updated without signaling (rare).
            if (ctrl->producer_seq == last_seen_seq_) {
                return E_AKVC_FRAMEBUS_TIMEOUT;
            }
        } else if (wr != WAIT_OBJECT_0) {
            return E_AKVC_FRAMEBUS_TIMEOUT;
        }
    }

    // Re-read producer_seq after the wait.
    uint64_t producer_seq = ctrl->producer_seq;
    if (producer_seq == 0) return E_AKVC_FRAMEBUS_NO_PRODUCER;

    const uint32_t slot_count = ctrl->slot_count;
    const uint32_t slot_size  = ctrl->slot_size;

    // Tear-protection: read seq_head/seq_tail with retries. On each retry we
    // re-read producer_seq (the producer may have advanced) and recompute the
    // slot. A frame is valid only when seq_head == seq_tail == producer_seq,
    // i.e. the slot was fully written and is the most recent frame.
    for (int retry = 0; retry < 5; ++retry) {
        producer_seq = ctrl->producer_seq;
        if (producer_seq == 0) return E_AKVC_FRAMEBUS_NO_PRODUCER;

        const uint32_t slot_index = static_cast<uint32_t>((producer_seq - 1) % slot_count);
        const uint8_t* slot = base_
                            + sizeof(akvc_ring_control_t)
                            + static_cast<size_t>(slot_index) * slot_size;
        const auto* hdr = reinterpret_cast<const akvc_frame_header_t*>(slot);

        const uint64_t head = hdr->seq_head;
        MemoryBarrier();
        const uint64_t tail = hdr->seq_tail;
        if (head == tail && tail == producer_seq) {
            // Validate header sanity.
            if (hdr->magic != AKVC_MAGIC ||
                hdr->schema_version != AKVC_SCHEMA_VERSION) {
                wchar_t path[MAX_PATH] = {0};
                HMODULE m = ::GetModuleHandleW(L"akvc-mf");
                if (m && ::GetModuleFileNameW(m, path, MAX_PATH)) {
                    wchar_t* sep = wcsrchr(path, L'\\');
                    if (sep) wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
                    FILE* f = nullptr;
                    if (_wfopen_s(&f, path, L"a") == 0 && f) {
                        fprintf(f, "[FrameBusConsumer] SCHEMA_MISMATCH magic=0x%08X schema=%u (expect %u)\n",
                                hdr->magic, hdr->schema_version, AKVC_SCHEMA_VERSION);
                        fclose(f);
                    }
                }
                return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;
            }

            out.header = hdr;
            if (hdr->plane_offset[0] && hdr->plane_size[0]) {
                out.plane0 = slot + hdr->plane_offset[0];
            }
            if (hdr->plane_offset[1] && hdr->plane_size[1]) {
                out.plane1 = slot + hdr->plane_offset[1];
            }
            last_seen_seq_ = producer_seq;
            // Diagnostic: log which frame seq we delivered.
            {
                wchar_t path[MAX_PATH] = {0};
                HMODULE m = ::GetModuleHandleW(L"akvc-mf");
                if (m && ::GetModuleFileNameW(m, path, MAX_PATH)) {
                    wchar_t* sep = wcsrchr(path, L'\\');
                    if (sep) wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
                    FILE* f = nullptr;
                    if (_wfopen_s(&f, path, L"a") == 0 && f) {
                        fprintf(f, "[FrameBusConsumer] delivered frame pseq=%llu flags=%u\n",
                                (unsigned long long)producer_seq, hdr->flags);
                        fclose(f);
                    }
                }
            }
            return AKVC_OK;
        }
        // Yield briefly and retry.
        ::SwitchToThread();
    }
    // Diagnostic: log the torn-frame values so we can see why.
    {
        wchar_t path[MAX_PATH] = {0};
        HMODULE m = ::GetModuleHandleW(L"akvc-mf");
        if (m && ::GetModuleFileNameW(m, path, MAX_PATH)) {
            wchar_t* sep = wcsrchr(path, L'\\');
            if (sep) wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
            FILE* f = nullptr;
            if (_wfopen_s(&f, path, L"a") == 0 && f) {
                fprintf(f, "[FrameBusConsumer] TORN_FRAME pseq=%llu slot=%u\n",
                        (unsigned long long)producer_seq,
                        static_cast<uint32_t>((producer_seq - 1) % slot_count));
                fclose(f);
            }
        }
    }
    return E_AKVC_FRAMEBUS_TORN_FRAME;
}

void FrameBusConsumer::close() {
    if (base_)    { ::UnmapViewOfFile(base_); base_ = nullptr; }
    if (mapping_) { ::CloseHandle(mapping_);  mapping_ = nullptr; }
    if (event_)   { ::CloseHandle(event_);    event_ = nullptr; }
    region_size_ = 0;
}

}  // namespace akvc
