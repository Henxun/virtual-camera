// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Helper Service implementation.

#include "akvc/helper.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>

#include <mfapi.h>
#include <mfvirtualcamera.h>
#include <ks.h>
#include <strsafe.h>
#include <io.h>
#include <fcntl.h>

// CLSID for our MF Media Source (same as in virtualcam/windows/mf).
// {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}
static const CLSID CLSID_AKVCMFSource = {
    0x3c2d3a1a, 0x8e5f, 0x4b8f, {0x9c, 0x1a, 0x2d, 0x7e, 0x5f, 0x1a, 0x3b, 0x4c}
};

namespace akvc {

namespace {

// Helper-local clock helpers (avoid pulling in system clock headers).
uint64_t now_100ns() noexcept {
    FILETIME ft;
    ::GetSystemTimePreciseAsFileTime(&ft);
    ULARGE_INTEGER u;
    u.LowPart  = ft.dwLowDateTime;
    u.HighPart = ft.dwHighDateTime;
    return u.QuadPart;
}

// Named pipe name (local scope, single-instance).
const wchar_t* kPipeName = L"\\\\.\\pipe\\akvc-helper-ctrl";

// Time between heartbeat checks.
constexpr DWORD kHeartbeatCheckMs = 50;

// ── Pipe command protocol ──
// Commands are sent as a single uint32_t (little-endian):
enum PipeCommand : uint32_t {
    CMD_QUIT         = 0x00000001u,   // Graceful shutdown
    CMD_PING         = 0x00000002u,   // Health check (reply: "PONG")
    CMD_STATUS       = 0x00000003u,   // Return status info
    CMD_REGISTER_MF  = 0x00000004u,   // Register MF virtual camera
};

// Response codes
enum PipeResponse : uint32_t {
    RSP_OK       = 0x00000000u,
    RSP_PONG     = 0x00000001u,
    RSP_UNKNOWN  = 0xFFFFFFFFu,
};

}  // namespace

Helper::~Helper() {
    stop();
    wait();
}

bool Helper::start() {
    // 1. Create the Frame Bus (producer role).
    akvc_status_t st = producer_.create();
    if (st != AKVC_OK) {
        std::fprintf(stderr, "[helper] FrameBusProducer::create failed: %d\n", st);
        return false;
    }

    // 2. Mark helper_pid in control block.
    producer_.ctrl()->helper_pid = ::GetCurrentProcessId();

    // 3. Set stdin to binary mode for control commands.
    _setmode(_fileno(stdin), _O_BINARY);

    running_ = true;

    // 4. Start threads.
    heartbeat_thread_ = std::thread(&Helper::heartbeat_loop, this);
    pipe_thread_ = std::thread(&Helper::pipe_loop, this);

    std::fprintf(stderr, "[helper] started (PID=%lu)\n", ::GetCurrentProcessId());
    return true;
}

bool Helper::register_mf_virtual_camera() {
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
    hr = ::MFStartup(MF_VERSION, MFSTARTUP_FULL);  // FULL needed for sensor group APIs
    if (FAILED(hr)) { ::CoUninitialize(); return false; }

    // Register CLSID in registry so frameserver can find our DLL.
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

    // Create the virtual camera (Synthetic / non-wrapping).
    // Per the MS VirtualCamera sample:
    //   - sourceId = the MediaSource CLSID string
    //   - categories = nullptr, count = 0
    //   - do NOT call AddDeviceSourceInfo (that's only for wrapping a physical
    //     camera, and takes the physical camera's symbolic link)
    //   - set VCAM_KIND = Synthetic so the activate creates a SimpleMediaSource
    IMFVirtualCamera* vc = nullptr;
    wchar_t source_id[64];
    StringFromGUID2(CLSID_AKVCMFSource, source_id, 64);

    hr = ::MFCreateVirtualCamera(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_Session,
        MFVirtualCameraAccess_CurrentUser,
        L"AK Virtual Camera",
        source_id,
        nullptr, 0,
        &vc);
    if (FAILED(hr)) {
        std::fprintf(stderr, "[helper] MFCreateVirtualCamera failed: 0x%08lx\n", hr);
        ::MFShutdown(); ::CoUninitialize();
        return false;
    }

    // VCAM_KIND custom attribute (must match the DLL's definition).
    // {D4A12C09-2C2A-4FC3-ABD7-ABE86BBA9A3D}, value 0 = Synthetic.
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

    std::fprintf(stderr, "[helper] MF Virtual Camera registered successfully\n");
    // NOTE: we intentionally leak the vc reference. The Session-lifetime
    // virtual camera must stay alive for the helper process's lifetime;
    // releasing it would tear down the PnP device. The OS reclaims handles
    // when the helper process exits.
    ::MFShutdown(); ::CoUninitialize();
    return true;
}

void Helper::stop() {
    running_ = false;
}

void Helper::wait() {
    if (heartbeat_thread_.joinable()) heartbeat_thread_.join();
    if (pipe_thread_.joinable()) pipe_thread_.join();
    producer_.close();
    std::fprintf(stderr, "[helper] stopped\n");
}

// ── Heartbeat monitor ──

void Helper::heartbeat_loop() {
    // Initial placeholder frames until UI connects.
    uint64_t last_placeholder_100ns = 0;
    const uint64_t placeholder_interval = 10000000ULL / kPlaceholderFps;  // 100ms in 100ns

    while (running_) {
        // Read heartbeat from control block.
        auto* ctrl = producer_.ctrl();
        uint64_t hb = ctrl->producer_heartbeat;
        uint32_t wp = ctrl->writer_pid;

        uint64_t now = now_100ns();
        uint64_t elapsed = now - hb;

        if (wp != 0 && elapsed < AKVC_HEARTBEAT_TIMEOUT) {
            // UI is alive.
            ui_connected_ = true;
        } else {
            // UI has gone away (or never connected) — publish placeholders.
            if (now - last_placeholder_100ns >= placeholder_interval) {
                publish_placeholder();
                last_placeholder_100ns = now;
            }
            ui_connected_ = false;
        }

        // Update helper_pid in control block.
        ctrl->helper_pid = ::GetCurrentProcessId();

        std::this_thread::sleep_for(std::chrono::milliseconds(kHeartbeatCheckMs));
    }
}

void Helper::publish_placeholder() {
    // 1280x720 NV12
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

    // Y=0 (black), UV=128 (neutral chroma)
    static thread_local std::vector<uint8_t> y_buf(w * h, 0);
    static thread_local std::vector<uint8_t> uv_buf(w * h / 2, 128);

    const uint8_t* planes[2] = { y_buf.data(), uv_buf.data() };
    producer_.publish(hdr, planes);
}

// ── stdin command reader ──

void Helper::pipe_loop() {
    while (running_) {
        uint32_t cmd;
        DWORD bytes_read = 0;
        BOOL ok = ::ReadFile(::GetStdHandle(STD_INPUT_HANDLE),
                             &cmd, sizeof(cmd), &bytes_read, nullptr);
        if (!ok || bytes_read != sizeof(cmd)) {
            if (running_) {
                // EOF or error — just wait and retry.
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
            continue;
        }

        uint32_t response = RSP_UNKNOWN;

        switch (static_cast<PipeCommand>(cmd)) {
            case CMD_QUIT:
                response = RSP_OK;
                ::WriteFile(::GetStdHandle(STD_OUTPUT_HANDLE),
                            &response, sizeof(response), &bytes_read, nullptr);
                stop();
                return;

            case CMD_PING:
                response = RSP_PONG;
                break;

            case CMD_REGISTER_MF: {
                bool ok = register_mf_virtual_camera();
                response = ok ? RSP_OK : RSP_UNKNOWN;
                break;
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
                ::WriteFile(::GetStdHandle(STD_OUTPUT_HANDLE),
                            buf, sizeof(buf), &bytes_read, nullptr);
                continue;  // already wrote response
            }

            default:
                response = RSP_UNKNOWN;
                break;
        }

        ::WriteFile(::GetStdHandle(STD_OUTPUT_HANDLE),
                    &response, sizeof(response), &bytes_read, nullptr);
    }
}

}  // namespace akvc

// ── Main entry point ──

int main(int, char*[]) {
    akvc::Helper helper;
    if (!helper.start()) {
        std::fprintf(stderr, "[helper] failed to start\n");
        return 1;
    }

    // Block until stop is requested (from pipe or stdin close).
    // We use a simple console event handler for CTRL+C.
    ::SetConsoleCtrlHandler([](DWORD ctrl_type) -> BOOL {
        if (ctrl_type == CTRL_C_EVENT || ctrl_type == CTRL_BREAK_EVENT) {
            // The handler returns TRUE and the process exits via stop().
            return FALSE;  // allow default handler
        }
        return FALSE;
    }, TRUE);

    helper.wait();
    return 0;
}
