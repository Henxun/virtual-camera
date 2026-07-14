// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "akvc/framebus.h"

#include <aclapi.h>
#include <sddl.h>
#include <shlobj.h>
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <filesystem>

namespace akvc {

namespace {

constexpr wchar_t kFrameBusMappingName[] = L"Global\\akvc-frames-v1";
constexpr wchar_t kFrameBusEventName[] = L"Global\\akvc-frames-evt-v1";
constexpr wchar_t kFrameBusMutexName[] = L"Global\\akvc-frames-mtx-v1";

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

std::wstring framebus_path_from_env(const wchar_t* name) {
    if (name == nullptr || *name == L'\0') {
        return {};
    }
    const DWORD needed = ::GetEnvironmentVariableW(name, nullptr, 0);
    if (needed == 0) {
        return {};
    }
    std::wstring value(needed - 1, L'\0');
    if (::GetEnvironmentVariableW(name, value.data(), needed) == 0) {
        return {};
    }
    return value;
}

void debug_log_path_resolution(const wchar_t* stage, const std::wstring& detail) {
    wchar_t path[MAX_PATH] = {0};
    HMODULE m = ::GetModuleHandleW(L"akvc-mf");
    if (!m) m = ::GetModuleHandleW(nullptr);
    if (!(m && ::GetModuleFileNameW(m, path, MAX_PATH))) {
        return;
    }
    wchar_t* sep = wcsrchr(path, L'\\');
    if (!sep) {
        return;
    }
    wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
    FILE* f = nullptr;
    if (_wfopen_s(&f, path, L"a") == 0 && f) {
        std::fwprintf(f, L"[FrameBus] %ls %ls\n", stage, detail.c_str());
        fclose(f);
    }
}

void debug_log_consumer_failure(const char* operation, DWORD le, const std::wstring& detail = {}) {
    wchar_t path[MAX_PATH] = {0};
    HMODULE m = ::GetModuleHandleW(L"akvc-mf");
    if (!m) m = ::GetModuleHandleW(nullptr);
    if (!(m && ::GetModuleFileNameW(m, path, MAX_PATH))) {
        return;
    }
    wchar_t* sep = wcsrchr(path, L'\\');
    if (!sep) {
        return;
    }
    wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
    FILE* f = nullptr;
    if (_wfopen_s(&f, path, L"a") == 0 && f) {
        DWORD pid = ::GetCurrentProcessId();
        DWORD sid = 0;
        ::ProcessIdToSessionId(pid, &sid);
        std::fwprintf(f, L"[FrameBusConsumer::open] %hs FAILED le=%lu pid=%lu session=%lu detail=%ls\n",
                      operation,
                      le,
                      pid,
                      sid,
                      detail.c_str());
        fclose(f);
    }
}

std::wstring framebus_base_dir() {
    if (auto explicit_path = framebus_path_from_env(L"AKVC_FRAMEBUS_DIR"); !explicit_path.empty()) {
        debug_log_path_resolution(L"base_dir env", explicit_path);
        return explicit_path;
    }

    wchar_t path[MAX_PATH] = {};
    if (SUCCEEDED(::SHGetFolderPathW(nullptr, CSIDL_COMMON_DOCUMENTS, nullptr, SHGFP_TYPE_CURRENT, path))) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir common_documents", chosen);
        return chosen;
    }

    if (SUCCEEDED(::SHGetFolderPathW(nullptr, CSIDL_COMMON_DOCUMENTS, nullptr, SHGFP_TYPE_DEFAULT, path))) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir common_documents_default", chosen);
        return chosen;
    }

    if (SUCCEEDED(::SHGetFolderPathW(nullptr, CSIDL_COMMON_APPDATA, nullptr, SHGFP_TYPE_CURRENT, path))) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir common_appdata", chosen);
        return chosen;
    }

    if (SUCCEEDED(::SHGetFolderPathW(nullptr, CSIDL_COMMON_APPDATA, nullptr, SHGFP_TYPE_DEFAULT, path))) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir common_appdata_default", chosen);
        return chosen;
    }

    if (::GetEnvironmentVariableW(L"ProgramData", path, MAX_PATH) != 0) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir programdata_env", chosen);
        return chosen;
    }

    if (SUCCEEDED(::SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA, nullptr, SHGFP_TYPE_CURRENT, path))) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir local_appdata", chosen);
        return chosen;
    }

    if (const DWORD needed = ::GetTempPathW(MAX_PATH, path); needed != 0 && needed < MAX_PATH) {
        std::wstring chosen = (std::filesystem::path(path) / L"AKVirtualCamera").wstring();
        debug_log_path_resolution(L"base_dir temp", chosen);
        return chosen;
    }
    debug_log_path_resolution(L"base_dir fallback", L".");
    return L".";
}

std::wstring framebus_file_path() {
    if (auto explicit_path = framebus_path_from_env(L"AKVC_FRAMEBUS_PATH"); !explicit_path.empty()) {
        debug_log_path_resolution(L"file_path env", explicit_path);
        return explicit_path;
    }
    std::wstring chosen = (std::filesystem::path(framebus_base_dir()) / L"akvc-frames-v1.bin").wstring();
    debug_log_path_resolution(L"file_path default", chosen);
    return chosen;
}

bool ensure_parent_dir(const std::wstring& path, SECURITY_ATTRIBUTES* sa = nullptr) {
    const auto parent = std::filesystem::path(path).parent_path();
    if (parent.empty()) {
        return true;
    }

    DWORD attrs = ::GetFileAttributesW(parent.c_str());
    if (attrs != INVALID_FILE_ATTRIBUTES) {
        return (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0;
    }

    const auto grandparent = parent.parent_path();
    if (!grandparent.empty() && !ensure_parent_dir(parent.wstring(), sa)) {
        return false;
    }

    if (::CreateDirectoryW(parent.c_str(), sa)) {
        return true;
    }

    const DWORD le = ::GetLastError();
    if (le == ERROR_ALREADY_EXISTS) {
        attrs = ::GetFileAttributesW(parent.c_str());
        return attrs != INVALID_FILE_ATTRIBUTES && (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0;
    }
    return false;
}

bool apply_security_to_path(const std::wstring& path, PSECURITY_DESCRIPTOR psd) {
    if (!psd || path.empty()) {
        return false;
    }
    PACL dacl = nullptr;
    BOOL dacl_present = FALSE;
    BOOL dacl_defaulted = FALSE;
    if (!::GetSecurityDescriptorDacl(psd, &dacl_present, &dacl, &dacl_defaulted) || !dacl_present || !dacl) {
        return false;
    }
    const DWORD le = ::SetNamedSecurityInfoW(
        const_cast<wchar_t*>(path.c_str()),
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
        nullptr,
        nullptr,
        dacl,
        nullptr);
    return le == ERROR_SUCCESS;
}

HANDLE open_backing_file(DWORD desired_access,
                         bool create_or_reset,
                         std::wstring& path_out,
                         DWORD& error_out,
                         SECURITY_ATTRIBUTES* sa = nullptr) {
    path_out = framebus_file_path();
    error_out = ERROR_SUCCESS;
    if (!ensure_parent_dir(path_out, sa)) {
        error_out = ERROR_PATH_NOT_FOUND;
        return nullptr;
    }

    const DWORD disposition = create_or_reset ? OPEN_ALWAYS : OPEN_EXISTING;
    HANDLE file = ::CreateFileW(
        path_out.c_str(),
        desired_access,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        sa,
        disposition,
        FILE_ATTRIBUTE_NORMAL,
        nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        error_out = ::GetLastError();
        return nullptr;
    }
    return file;
}

bool ensure_file_size(HANDLE file, uint32_t size, DWORD& error_out) {
    LARGE_INTEGER target{};
    target.QuadPart = static_cast<LONGLONG>(size);
    if (!::SetFilePointerEx(file, target, nullptr, FILE_BEGIN)) {
        error_out = ::GetLastError();
        return false;
    }
    if (!::SetEndOfFile(file)) {
        error_out = ::GetLastError();
        return false;
    }
    if (!::SetFilePointerEx(file, LARGE_INTEGER{}, nullptr, FILE_BEGIN)) {
        error_out = ::GetLastError();
        return false;
    }
    return true;
}

}  // namespace

akvc_status_t translate_win32(DWORD le) {
    switch (le) {
        case ERROR_SUCCESS:        return AKVC_OK;
        case ERROR_FILE_NOT_FOUND: return E_AKVC_FRAMEBUS_OPEN_FAILED;
        case ERROR_PATH_NOT_FOUND: return E_AKVC_FRAMEBUS_OPEN_FAILED;
        case ERROR_ACCESS_DENIED:  return E_AKVC_FRAMEBUS_OPEN_FAILED;
        case WAIT_TIMEOUT:         return E_AKVC_FRAMEBUS_TIMEOUT;
        default:                   return E_AKVC_FRAMEBUS_OPEN_FAILED;
    }
}

std::wstring default_framebus_file_path() {
    return framebus_file_path();
}

FrameBusBase::~FrameBusBase() {
    if (base_)    { ::UnmapViewOfFile(base_); base_    = nullptr; }
    if (mapping_) { ::CloseHandle(mapping_);  mapping_ = nullptr; }
    if (file_)    { ::CloseHandle(file_);     file_ = nullptr; }
    if (event_)   { ::CloseHandle(event_);    event_   = nullptr; }
    if (mutex_)   { ::CloseHandle(mutex_);    mutex_   = nullptr; }
}

// ---------------- Producer ----------------

akvc_status_t FrameBusProducer::open_existing() {
    if (is_open()) return AKVC_OK;

    last_error_ = {};
    region_size_ = AKVC_DEFAULT_REGION_SIZE;

    std::wstring file_path;
    DWORD file_error = ERROR_SUCCESS;
    file_ = open_backing_file(GENERIC_READ | GENERIC_WRITE, false, file_path, file_error);
    if (!file_) {
        set_last_error(file_error, "CreateFileW", file_path.empty() ? nullptr : file_path.c_str());
        return translate_win32(file_error);
    }

    mapping_ = ::CreateFileMappingW(file_, nullptr, PAGE_READWRITE, 0, 0, nullptr);
    if (!mapping_) {
        set_last_error(::GetLastError(), "CreateFileMappingW", file_path.c_str());
        close();
        return translate_win32(::GetLastError());
    }

    base_ = reinterpret_cast<uint8_t*>(
        ::MapViewOfFile(mapping_, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, region_size_));
    if (!base_) {
        set_last_error(::GetLastError(), "MapViewOfFile", file_path.c_str());
        close();
        return translate_win32(::GetLastError());
    }

    auto* ctrl = control();
    if (ctrl->magic != AKVC_MAGIC ||
        ctrl->schema_version != AKVC_SCHEMA_VERSION ||
        ctrl->slot_count != AKVC_RING_SLOTS ||
        ctrl->slot_size != AKVC_DEFAULT_SLOT_SIZE) {
        close();
        return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;
    }

    region_size_ = sizeof(akvc_ring_control_t)
                 + ctrl->slot_count * ctrl->slot_size;

    event_ = ::OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, FALSE, kFrameBusEventName);
    if (!event_) {
        set_last_error(::GetLastError(), "OpenEventW", kFrameBusEventName);
        close();
        return translate_win32(::GetLastError());
    }

    mutex_ = ::OpenMutexW(SYNCHRONIZE, FALSE, kFrameBusMutexName);
    if (!mutex_) {
        set_last_error(::GetLastError(), "OpenMutexW", kFrameBusMutexName);
        close();
        return translate_win32(::GetLastError());
    }

    ctrl->writer_pid = ::GetCurrentProcessId();
    return AKVC_OK;
}

akvc_status_t FrameBusProducer::create() {
    if (is_open()) return AKVC_OK;

    last_error_ = {};

    ScopedSecurityDescriptor sd;
    if (!sd.init()) {
        set_last_error(::GetLastError(), "ConvertStringSecurityDescriptorToSecurityDescriptorW", nullptr);
        return translate_win32(::GetLastError());
    }

    region_size_ = AKVC_DEFAULT_REGION_SIZE;

    std::wstring file_path;
    DWORD file_error = ERROR_SUCCESS;
    file_ = open_backing_file(GENERIC_READ | GENERIC_WRITE, true, file_path, file_error, &sd.sa);
    if (!file_) {
        set_last_error(file_error, "CreateFileW", file_path.empty() ? nullptr : file_path.c_str());
        return translate_win32(file_error);
    }
    const auto parent = std::filesystem::path(file_path).parent_path().wstring();
    apply_security_to_path(parent, sd.psd);
    apply_security_to_path(file_path, sd.psd);
    if (!ensure_file_size(file_, region_size_, file_error)) {
        set_last_error(file_error, "SetEndOfFile", file_path.c_str());
        close();
        return translate_win32(file_error);
    }

    mapping_ = ::CreateFileMappingW(
        file_,
        &sd.sa,
        PAGE_READWRITE,
        0,
        region_size_,
        nullptr);
    if (!mapping_) {
        set_last_error(::GetLastError(), "CreateFileMappingW", file_path.c_str());
        return translate_win32(::GetLastError());
    }

    base_ = reinterpret_cast<uint8_t*>(
        ::MapViewOfFile(mapping_, FILE_MAP_ALL_ACCESS, 0, 0, region_size_));
    if (!base_) {
        set_last_error(::GetLastError(), "MapViewOfFile", file_path.c_str());
        return translate_win32(::GetLastError());
    }

    event_ = ::CreateEventW(&sd.sa, /*manualReset*/ FALSE, FALSE,
                            kFrameBusEventName);
    if (!event_) {
        set_last_error(::GetLastError(), "CreateEventW", kFrameBusEventName);
        return translate_win32(::GetLastError());
    }

    mutex_ = ::CreateMutexW(&sd.sa, FALSE, kFrameBusMutexName);
    if (!mutex_) {
        set_last_error(::GetLastError(), "CreateMutexW", kFrameBusMutexName);
        return translate_win32(::GetLastError());
    }

    // Reuse the existing backing file if frameserver still has a mapping.
    std::memset(base_, 0, region_size_);
    auto* ctrl = control();
    ctrl->magic             = AKVC_MAGIC;
    ctrl->schema_version    = AKVC_SCHEMA_VERSION;
    ctrl->slot_count        = AKVC_RING_SLOTS;
    ctrl->slot_size         = AKVC_DEFAULT_SLOT_SIZE;
    ctrl->producer_seq      = 0;
    ctrl->consumer_count    = 0;
    ctrl->writer_pid        = ::GetCurrentProcessId();
    ctrl->created_pts_100ns = now_pts_100ns();
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
    if (file_)    { ::CloseHandle(file_);     file_ = nullptr; }
    if (event_)   { ::CloseHandle(event_);    event_ = nullptr; }
    if (mutex_)   { ::CloseHandle(mutex_);    mutex_ = nullptr; }
    region_size_ = 0;
}

// ---------------- Consumer ----------------

akvc_status_t FrameBusConsumer::open() {
    if (is_open()) return AKVC_OK;

    std::wstring file_path;
    DWORD file_error = ERROR_SUCCESS;
    file_ = open_backing_file(GENERIC_READ, false, file_path, file_error);
    if (!file_) {
        DWORD le = file_error;
        set_last_error(le, "CreateFileW", file_path.empty() ? nullptr : file_path.c_str());
        debug_log_consumer_failure("CreateFileW", le, file_path);
        return translate_win32(le);
    }

    mapping_ = ::CreateFileMappingW(file_, nullptr, PAGE_READONLY, 0, 0, nullptr);
    if (!mapping_) {
        DWORD le = ::GetLastError();
        set_last_error(le, "CreateFileMappingW", file_path.c_str());
        debug_log_consumer_failure("CreateFileMappingW", le, file_path);
        close();
        return translate_win32(le);
    }

    base_ = reinterpret_cast<uint8_t*>(
        ::MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, 0));
    if (!base_) {
        DWORD le = ::GetLastError();
        debug_log_consumer_failure("MapViewOfFile", le, file_path);
        return translate_win32(le);
    }

    // Determine region size from control block, fall back to default.
    auto* ctrl = control();
    if (ctrl->magic != AKVC_MAGIC ||
        ctrl->schema_version != AKVC_SCHEMA_VERSION) {
        debug_log_consumer_failure("SchemaCheck", ERROR_INVALID_DATA, file_path);
        close();
        return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;
    }
    region_size_ = sizeof(akvc_ring_control_t)
                 + ctrl->slot_count * ctrl->slot_size;

    event_ = ::OpenEventW(SYNCHRONIZE, FALSE,
                          L"Global\\akvc-frames-evt-v1");
    if (!event_) {
        DWORD le = ::GetLastError();
        debug_log_consumer_failure("OpenEventW", le, L"Global\\akvc-frames-evt-v1");
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
            out.producer_seq = producer_seq;
            out.writer_pid = ctrl->writer_pid;
            out.helper_pid = ctrl->helper_pid;
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
    if (file_)    { ::CloseHandle(file_);     file_ = nullptr; }
    if (event_)   { ::CloseHandle(event_);    event_ = nullptr; }
    region_size_ = 0;
}

}  // namespace akvc
