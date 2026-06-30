// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Helper Service implementation.

#include "akvc/helper.h"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <fcntl.h>
#include <io.h>
#include <limits>
#include <thread>
#include <vector>

#include <ks.h>
#include <mfapi.h>
#include <mfvirtualcamera.h>
#include <sddl.h>
#include <strsafe.h>

// CLSID for our MF Media Source (same as in virtualcam/windows/mf).
// {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}
static const CLSID CLSID_AKVCMFSource = {
    0x3c2d3a1a, 0x8e5f, 0x4b8f, {0x9c, 0x1a, 0x2d, 0x7e, 0x5f, 0x1a, 0x3b, 0x4c}
};

namespace akvc {

namespace {

uint64_t now_100ns() noexcept {
    FILETIME ft;
    ::GetSystemTimePreciseAsFileTime(&ft);
    ULARGE_INTEGER u;
    u.LowPart  = ft.dwLowDateTime;
    u.HighPart = ft.dwHighDateTime;
    return u.QuadPart;
}

const wchar_t* kDefaultPipeName = L"\\\\.\\pipe\\akvc-helper-ctrl";

constexpr DWORD kHeartbeatCheckMs = 50;
constexpr wchar_t kDefaultScheduledTaskName[] = L"AKVirtualCameraHelper";

enum PipeCommand : uint32_t {
    CMD_QUIT         = 0x00000001u,
    CMD_PING         = 0x00000002u,
    CMD_STATUS       = 0x00000003u,
    CMD_REGISTER_MF  = 0x00000004u,
};

enum PipeResponse : uint32_t {
    RSP_OK       = 0x00000000u,
    RSP_PONG     = 0x00000001u,
    RSP_UNKNOWN  = 0xFFFFFFFFu,
};

Helper* g_helper_instance = nullptr;

BOOL WINAPI console_ctrl_handler(DWORD ctrl_type) {
    if ((ctrl_type == CTRL_C_EVENT || ctrl_type == CTRL_BREAK_EVENT || ctrl_type == CTRL_CLOSE_EVENT) &&
        g_helper_instance != nullptr) {
        g_helper_instance->stop();
        return TRUE;
    }
    return FALSE;
}

bool read_exact(HANDLE handle, void* buffer, DWORD size) {
    auto* out = static_cast<uint8_t*>(buffer);
    DWORD total = 0;
    while (total < size) {
        DWORD chunk = 0;
        if (!::ReadFile(handle, out + total, size - total, &chunk, nullptr) || chunk == 0) {
            return false;
        }
        total += chunk;
    }
    return true;
}

bool write_exact(HANDLE handle, const void* buffer, DWORD size) {
    const auto* in = static_cast<const uint8_t*>(buffer);
    DWORD total = 0;
    while (total < size) {
        DWORD chunk = 0;
        if (!::WriteFile(handle, in + total, size - total, &chunk, nullptr) || chunk == 0) {
            return false;
        }
        total += chunk;
    }
    return true;
}

struct ScopedSecurityDescriptor {
    PSECURITY_DESCRIPTOR sd = nullptr;
    ~ScopedSecurityDescriptor() {
        if (sd != nullptr) {
            ::LocalFree(sd);
        }
    }
};

bool build_pipe_security_attributes(SECURITY_ATTRIBUTES& sa, ScopedSecurityDescriptor& scoped) {
    constexpr wchar_t kPipeSddl[] =
        L"D:(A;;GA;;;BA)(A;;GA;;;SY)(A;;GRGW;;;AU)(A;;GRGW;;;AC)(A;;GRGW;;;S-1-15-2-1)(A;;GRGW;;;S-1-15-2-2)";
    if (!::ConvertStringSecurityDescriptorToSecurityDescriptorW(
            kPipeSddl,
            SDDL_REVISION_1,
            &scoped.sd,
            nullptr)) {
        return false;
    }
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = scoped.sd;
    sa.bInheritHandle = FALSE;
    return true;
}

bool parse_parent_pid_arg(const wchar_t* value, DWORD& parent_pid) {
    if (value == nullptr || *value == L'\0') {
        return false;
    }

    wchar_t* end = nullptr;
    errno = 0;
    const unsigned long long parsed = std::wcstoull(value, &end, 10);
    if (end == value || end == nullptr || *end != L'\0' || errno == ERANGE ||
        parsed == 0 || parsed > std::numeric_limits<DWORD>::max()) {
        return false;
    }

    parent_pid = static_cast<DWORD>(parsed);
    return true;
}

bool parse_bool_flag(const wchar_t* value, bool& out) {
    if (value == nullptr || *value == L'\0') {
        return false;
    }
    if (_wcsicmp(value, L"1") == 0 || _wcsicmp(value, L"true") == 0 ||
        _wcsicmp(value, L"yes") == 0 || _wcsicmp(value, L"on") == 0) {
        out = true;
        return true;
    }
    if (_wcsicmp(value, L"0") == 0 || _wcsicmp(value, L"false") == 0 ||
        _wcsicmp(value, L"no") == 0 || _wcsicmp(value, L"off") == 0) {
        out = false;
        return true;
    }
    return false;
}

}  // namespace

Helper::~Helper() {
    stop();
    wait();
}

bool Helper::start() {
    if (pipe_name_.empty()) {
        pipe_name_ = kDefaultPipeName;
    }

    if (parent_pid_ != 0 && !persistent_) {
        parent_process_ = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, parent_pid_);
        if (parent_process_ == nullptr) {
            const DWORD win32 = ::GetLastError();
            std::fprintf(
                stderr,
                "[helper] parent_watch_disabled pid=%lu op=OpenProcess win32=%lu\n",
                static_cast<unsigned long>(parent_pid_),
                static_cast<unsigned long>(win32));
            parent_pid_ = 0;
        }
    }

    akvc_status_t st = producer_.create();
    if (st != AKVC_OK) {
        const auto& err = producer_.last_error();
        const char* hint = (err.win32_error == ERROR_ACCESS_DENIED)
            ? "run elevated"
            : "check runtime environment";
        std::fprintf(
            stderr,
            "[helper] startup_error status=%d op=%s win32=%lu object=%S hint=%s\n",
            st,
            err.operation ? err.operation : "(unknown)",
            static_cast<unsigned long>(err.win32_error),
            err.object_name ? err.object_name : L"(none)",
            hint);
        std::fprintf(stderr, "[helper] FrameBusProducer::create failed: %d\n", st);
        if (parent_process_ != nullptr) {
            ::CloseHandle(parent_process_);
            parent_process_ = nullptr;
        }
        return false;
    }

    producer_.ctrl()->helper_pid = ::GetCurrentProcessId();
    running_ = true;

    heartbeat_thread_ = std::thread(&Helper::heartbeat_loop, this);
    pipe_thread_ = std::thread(&Helper::pipe_loop, this);

    std::fprintf(
        stderr,
        "[helper] started (PID=%lu pipe=%S parent_pid=%lu persistent=%d)\n",
        ::GetCurrentProcessId(),
        pipe_name_.c_str(),
        static_cast<unsigned long>(parent_pid_),
        persistent_ ? 1 : 0);
    return true;
}

#ifndef AKVC_CAMERA_NAME
#define AKVC_CAMERA_NAME L"AK Virtual Camera"
#endif

bool Helper::register_mf_virtual_camera(const wchar_t* name) {
    if (!name || !*name) {
        name = AKVC_CAMERA_NAME;
    }

    if (mf_camera_ != nullptr) {
        if (mf_camera_name_.empty() || _wcsicmp(mf_camera_name_.c_str(), name) == 0) {
            std::fprintf(stderr, "[helper] MF Virtual Camera already registered\n");
            return true;
        }
        std::fprintf(
            stderr,
            "[helper] MF Virtual Camera name mismatch existing=%S requested=%S\n",
            mf_camera_name_.c_str(),
            name);
        return false;
    }

    wchar_t dll_path[MAX_PATH];
    DWORD n = ::GetModuleFileNameW(nullptr, dll_path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return false;
    wchar_t* sep = wcsrchr(dll_path, L'\\');
    if (!sep) return false;
    wcscpy_s(sep + 1, MAX_PATH - (sep - dll_path) - 1, L"akvc-mf.dll");

    if (::GetFileAttributesW(dll_path) == INVALID_FILE_ATTRIBUTES) {
        std::fprintf(stderr, "[helper] MF DLL not found at %S\n", dll_path);
        return false;
    }

    HRESULT hr = ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) return false;
    hr = ::MFStartup(MF_VERSION, MFSTARTUP_FULL);
    if (FAILED(hr)) { ::CoUninitialize(); return false; }

    wchar_t clsid_str[64];
    StringFromGUID2(CLSID_AKVCMFSource, clsid_str, 64);
    wchar_t subkey[256];
    wcscpy_s(subkey, L"CLSID\\");
    wcscat_s(subkey, clsid_str);
    wcscat_s(subkey, L"\\InprocServer32");
    HKEY key = nullptr;
    if (::RegCreateKeyExW(HKEY_CLASSES_ROOT, subkey, 0, nullptr,
                          REG_OPTION_NON_VOLATILE, KEY_SET_VALUE,
                          nullptr, &key, nullptr) == ERROR_SUCCESS) {
        ::RegSetValueExW(key, nullptr, 0, REG_SZ,
                         reinterpret_cast<const BYTE*>(dll_path),
                         (wcslen(dll_path) + 1) * sizeof(wchar_t));
        wchar_t tm[] = L"Both";
        ::RegSetValueExW(key, L"ThreadingModel", 0, REG_SZ,
                         reinterpret_cast<const BYTE*>(tm), sizeof(tm));
        ::RegCloseKey(key);
    }

    IMFVirtualCamera* vc = nullptr;
    wchar_t source_id[64];
    StringFromGUID2(CLSID_AKVCMFSource, source_id, 64);
    GUID categories[] = { KSCATEGORY_VIDEO_CAMERA };

    {
        for (int stale_attempt = 0; stale_attempt < 8; ++stale_attempt) {
            IMFVirtualCamera* stale = nullptr;
            HRESULT hrStale = ::MFCreateVirtualCamera(
                MFVirtualCameraType_SoftwareCameraSource,
                MFVirtualCameraLifetime_System,
                MFVirtualCameraAccess_CurrentUser,
                name, source_id, categories, 1, &stale);
            if (FAILED(hrStale) || stale == nullptr) {
                break;
            }
            HRESULT hrR = stale->Remove();
            std::fprintf(stderr, "[helper] removed stale MF device #%d hr=0x%08lx\n", stale_attempt + 1, hrR);
            stale->Release();
            if (FAILED(hrR)) {
                break;
            }
            ::Sleep(1000);
        }
    }

    hr = ::MFCreateVirtualCamera(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_System,
        MFVirtualCameraAccess_CurrentUser,
        name,
        source_id,
        categories, 1,
        &vc);
    if (FAILED(hr)) {
        std::fprintf(stderr, "[helper] MFCreateVirtualCamera failed: 0x%08lx\n", hr);
        ::MFShutdown(); ::CoUninitialize();
        return false;
    }

    {
        HKEY hk = nullptr;
        if (::RegCreateKeyExW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\AKVC", 0, nullptr,
                              0, KEY_SET_VALUE, nullptr, &hk, nullptr) == ERROR_SUCCESS) {
            ULONG nb = static_cast<ULONG>((wcslen(name) + 1) * sizeof(wchar_t));
            ::RegSetValueExW(hk, L"FriendlyName", 0, REG_SZ,
                             reinterpret_cast<const BYTE*>(name), nb);
            ::RegCloseKey(hk);
        }
    }

    static const DEVPROPKEY DEVPKEY_Device_FriendlyName = {
        { 0xa45c254e, 0xdf1c, 0x4efd, { 0x80, 0x20, 0x67, 0xd1, 0x46, 0xa8, 0x50, 0xe0 } }, 14 };
    ULONG friendly_bytes = static_cast<ULONG>((wcslen(name) + 1) * sizeof(wchar_t));
    hr = vc->AddProperty(&DEVPKEY_Device_FriendlyName, DEVPROP_TYPE_STRING,
                         reinterpret_cast<const BYTE*>(name), friendly_bytes);
    std::fprintf(stderr, "[helper] AddProperty(FriendlyName) hr=0x%08lx\n", hr);
    hr = vc->AddRegistryEntry(L"FriendlyName", nullptr, REG_SZ,
                              reinterpret_cast<const BYTE*>(name), friendly_bytes);
    std::fprintf(stderr, "[helper] AddRegistryEntry(FriendlyName) hr=0x%08lx\n", hr);

    static const GUID VCAM_KIND = {
        0xd4a12c09, 0x2c2a, 0x4fc3,
        {0xab, 0xd7, 0xab, 0xe8, 0x6b, 0xba, 0x9a, 0x3d}
    };
    vc->SetUINT32(VCAM_KIND, 0);

    hr = vc->Start(nullptr);
    if (FAILED(hr)) {
        std::fprintf(stderr, "[helper] Start failed: 0x%08lx\n", hr);
        vc->Release();
        ::MFShutdown(); ::CoUninitialize();
        return false;
    }

    mf_camera_ = vc;
    mf_camera_name_ = name;
    std::fprintf(stderr, "[helper] MF Virtual Camera registered successfully\n");
    return true;
}

void Helper::stop() {
    running_ = false;
}

void Helper::wait() {
    if (heartbeat_thread_.joinable()) heartbeat_thread_.join();
    if (pipe_thread_.joinable()) pipe_thread_.join();

    if (mf_camera_) {
        HRESULT hrCo = ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
        HRESULT hrMf = ::MFStartup(MF_VERSION, MFSTARTUP_FULL);
        mf_camera_->Stop();
        mf_camera_->Release();
        mf_camera_ = nullptr;
        mf_camera_name_.clear();
        if (SUCCEEDED(hrMf)) ::MFShutdown();
        if (SUCCEEDED(hrCo)) ::CoUninitialize();
        std::fprintf(stderr, "[helper] MF Virtual Camera stopped (node retained)\n");
    }

    if (parent_process_ != nullptr) {
        ::CloseHandle(parent_process_);
        parent_process_ = nullptr;
    }

    producer_.close();
    std::fprintf(stderr, "[helper] stopped\n");
}

void Helper::heartbeat_loop() {
    uint64_t last_placeholder_100ns = 0;
    const uint64_t placeholder_interval = 10000000ULL / kPlaceholderFps;

    while (running_) {
        if (!persistent_ && !is_parent_alive()) {
            std::fprintf(stderr, "[helper] parent exited, shutting down\n");
            stop();
            break;
        }

        auto* ctrl = producer_.ctrl();
        uint64_t hb = ctrl->producer_heartbeat;
        uint32_t wp = ctrl->writer_pid;

        uint64_t now = now_100ns();
        uint64_t elapsed = now - hb;

        if (wp != 0 && elapsed < AKVC_HEARTBEAT_TIMEOUT) {
            ui_connected_ = true;
        } else {
            if (now - last_placeholder_100ns >= placeholder_interval) {
                publish_placeholder();
                last_placeholder_100ns = now;
            }
            ui_connected_ = false;
        }

        ctrl->helper_pid = ::GetCurrentProcessId();
        std::this_thread::sleep_for(std::chrono::milliseconds(kHeartbeatCheckMs));
    }
}

void Helper::publish_placeholder() {
    constexpr uint32_t w = 1280;
    constexpr uint32_t h = 720;
    uint64_t now = now_100ns();

    akvc_frame_header_t hdr{};
    hdr.fourcc        = AKVC_FOURCC_NV12;
    hdr.width         = w;
    hdr.height        = h;
    hdr.stride[0]     = w;
    hdr.stride[1]     = w;
    hdr.plane_size[0] = w * h;
    hdr.plane_size[1] = w * h / 2;
    hdr.flags         = AKVC_FLAG_PLACEHOLDER;
    hdr.pts_100ns     = now;

    static thread_local std::vector<uint8_t> y_buf(w * h, 0);
    static thread_local std::vector<uint8_t> uv_buf(w * h / 2, 128);

    const uint8_t* planes[2] = { y_buf.data(), uv_buf.data() };
    producer_.publish(hdr, planes);
}

bool Helper::is_parent_alive() const {
    if (parent_pid_ == 0) {
        return true;
    }
    if (parent_process_ == nullptr) {
        std::fprintf(stderr, "[helper] parent handle missing for pid=%lu\n", static_cast<unsigned long>(parent_pid_));
        return false;
    }

    DWORD exit_code = 0;
    if (!::GetExitCodeProcess(parent_process_, &exit_code)) {
        std::fprintf(stderr, "[helper] GetExitCodeProcess(parent=%lu) failed err=%lu\n", static_cast<unsigned long>(parent_pid_), static_cast<unsigned long>(::GetLastError()));
        return false;
    }
    if (exit_code != STILL_ACTIVE) {
        std::fprintf(stderr, "[helper] parent pid=%lu exit_code=%lu\n", static_cast<unsigned long>(parent_pid_), static_cast<unsigned long>(exit_code));
        return false;
    }
    return true;
}

bool Helper::handle_client(HANDLE pipe) {
    uint32_t cmd = 0;
    if (!read_exact(pipe, &cmd, sizeof(cmd))) {
        return false;
    }

    switch (static_cast<PipeCommand>(cmd)) {
        case CMD_QUIT: {
            const uint32_t response = RSP_OK;
            write_exact(pipe, &response, sizeof(response));
            stop();
            return false;
        }

        case CMD_PING: {
            const uint32_t response = RSP_PONG;
            return write_exact(pipe, &response, sizeof(response));
        }

        case CMD_REGISTER_MF: {
            uint32_t name_len = 0;
            if (!read_exact(pipe, &name_len, sizeof(name_len))) {
                return false;
            }

            wchar_t name_buf[256] = {};
            if (name_len > 0 && name_len < 256) {
                if (!read_exact(pipe, name_buf, name_len * sizeof(wchar_t))) {
                    return false;
                }
                name_buf[name_len] = L'\0';
            } else {
                StringCchCopyW(name_buf, 256, AKVC_CAMERA_NAME);
            }

            const uint32_t response = register_mf_virtual_camera(name_buf) ? RSP_OK : RSP_UNKNOWN;
            return write_exact(pipe, &response, sizeof(response));
        }

        case CMD_STATUS: {
            auto* ctrl = producer_.ctrl();
            uint8_t buf[24];
            uint32_t magic = AKVC_MAGIC;
            uint32_t pid = ::GetCurrentProcessId();
            uint64_t hb = ctrl->producer_heartbeat;
            uint32_t seq_lo = static_cast<uint32_t>(ctrl->producer_seq & 0xFFFFFFFF);
            uint32_t seq_hi = static_cast<uint32_t>(ctrl->producer_seq >> 32);
            memcpy(buf + 0,  &magic, 4);
            memcpy(buf + 4,  &pid, 4);
            memcpy(buf + 8,  &hb, 8);
            memcpy(buf + 16, &seq_lo, 4);
            memcpy(buf + 20, &seq_hi, 4);
            return write_exact(pipe, buf, sizeof(buf));
        }

        default: {
            const uint32_t response = RSP_UNKNOWN;
            return write_exact(pipe, &response, sizeof(response));
        }
    }
}

void Helper::pipe_loop() {
    SECURITY_ATTRIBUTES sa{};
    ScopedSecurityDescriptor scoped_sd;
    SECURITY_ATTRIBUTES* pipe_sa = nullptr;
    if (build_pipe_security_attributes(sa, scoped_sd)) {
        pipe_sa = &sa;
    } else {
        std::fprintf(stderr, "[helper] ConvertStringSecurityDescriptorToSecurityDescriptorW(pipe) failed err=%lu\n", static_cast<unsigned long>(::GetLastError()));
    }

    HANDLE pipe = ::CreateNamedPipeW(
        pipe_name_.c_str(),
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
        1,
        4096,
        4096,
        0,
        pipe_sa);
    if (pipe == INVALID_HANDLE_VALUE) {
        std::fprintf(stderr, "[helper] CreateNamedPipeW failed err=%lu\n", static_cast<unsigned long>(::GetLastError()));
        stop();
        return;
    }

    HANDLE event = ::CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (event == nullptr) {
        std::fprintf(stderr, "[helper] CreateEventW failed err=%lu\n", static_cast<unsigned long>(::GetLastError()));
        ::CloseHandle(pipe);
        stop();
        return;
    }

    std::fprintf(stderr, "[helper] listening on %S\n", pipe_name_.c_str());

    while (running_) {
        OVERLAPPED ov{};
        ov.hEvent = event;
        ::ResetEvent(event);

        BOOL ok = ::ConnectNamedPipe(pipe, &ov);
        DWORD err = ok ? ERROR_SUCCESS : ::GetLastError();
        if (!ok && err == ERROR_PIPE_CONNECTED) {
            ::SetEvent(event);
        } else if (!ok && err != ERROR_IO_PENDING) {
            std::fprintf(stderr, "[helper] ConnectNamedPipe failed err=%lu\n", static_cast<unsigned long>(err));
            stop();
            break;
        }

        bool connection_ready = false;
        while (running_) {
            if (!persistent_ && !is_parent_alive()) {
                stop();
                break;
            }

            DWORD wait = ::WaitForSingleObject(event, kPipeWaitTimeoutMs);
            if (wait == WAIT_OBJECT_0) {
                connection_ready = true;
                break;
            }
            if (wait != WAIT_TIMEOUT) {
                std::fprintf(stderr, "[helper] WaitForSingleObject(pipe) failed wait=%lu\n", static_cast<unsigned long>(wait));
                stop();
                break;
            }
        }

        if (!running_) {
            ::CancelIoEx(pipe, &ov);
            break;
        }

        if (!connection_ready) {
            ::CancelIoEx(pipe, &ov);
            continue;
        }

        DWORD transferred = 0;
        if (!::GetOverlappedResult(pipe, &ov, &transferred, FALSE)) {
            err = ::GetLastError();
            if (err != ERROR_PIPE_CONNECTED) {
                std::fprintf(stderr, "[helper] GetOverlappedResult failed err=%lu\n", static_cast<unsigned long>(err));
                stop();
                break;
            }
        }

        const bool keep_serving = handle_client(pipe);
        ::FlushFileBuffers(pipe);
        ::DisconnectNamedPipe(pipe);
        if (!keep_serving) {
            break;
        }
    }

    ::CloseHandle(event);
    ::CloseHandle(pipe);
}

}  // namespace akvc

int wmain(int argc, wchar_t* argv[]) {
    akvc::Helper helper;
    std::wstring log_path;

    for (int i = 1; i < argc; ++i) {
        if (wcscmp(argv[i], L"--pipe") == 0 && i + 1 < argc) {
            helper.set_pipe_name(argv[++i]);
            continue;
        }
        if (wcscmp(argv[i], L"--parent-pid") == 0) {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "[helper] ignoring invalid --parent-pid argument: missing value\n");
                continue;
            }
            DWORD parent_pid = 0;
            const wchar_t* value = argv[++i];
            if (!akvc::parse_parent_pid_arg(value, parent_pid)) {
                std::fprintf(stderr, "[helper] ignoring invalid --parent-pid value: %S\n", value);
                continue;
            }
            helper.set_parent_pid(parent_pid);
            continue;
        }
        if (wcscmp(argv[i], L"--persistent") == 0) {
            bool persistent = true;
            if (i + 1 < argc && argv[i + 1][0] != L'-') {
                if (!akvc::parse_bool_flag(argv[i + 1], persistent)) {
                    std::fprintf(stderr, "[helper] ignoring invalid --persistent value: %S\n", argv[i + 1]);
                    continue;
                }
                ++i;
            }
            helper.set_persistent(persistent);
            continue;
        }
        if (wcscmp(argv[i], L"--log") == 0 && i + 1 < argc) {
            log_path = argv[++i];
            helper.set_log_path(log_path);
            continue;
        }
        std::fprintf(stderr, "[helper] ignoring unknown argument: %S\n", argv[i]);
    }

    if (!log_path.empty()) {
        FILE* log_fp = nullptr;
        if (_wfreopen_s(&log_fp, log_path.c_str(), L"a", stderr) == 0 && log_fp != nullptr) {
            setvbuf(stderr, nullptr, _IONBF, 0);
        }
    }

    akvc::g_helper_instance = &helper;
    ::SetConsoleCtrlHandler(akvc::console_ctrl_handler, TRUE);

    if (!helper.start()) {
        std::fprintf(stderr, "[helper] failed to start\n");
        akvc::g_helper_instance = nullptr;
        return 1;
    }

    helper.wait();
    akvc::g_helper_instance = nullptr;
    return 0;
}
