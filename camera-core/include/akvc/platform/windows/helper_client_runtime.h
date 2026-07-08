// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Windows helper daemon client — RUNTIME CONTROL ONLY.
//
// This is the pure-C++ port of the former NativeWindowsHelperClient, stripped
// of pybind11/numpy and of all installation concerns (register_mf /
// install_autostart / scheduled-task management). The control layer uses only
// runtime operations: ping, status, ensure the daemon is running, quit.
//
// Installation (MF virtual-camera registration, schtasks /create, autostart)
// is intentionally OUT OF SCOPE — it belongs to a separate install step.

#ifndef AKVC_PLATFORM_WINDOWS_HELPER_CLIENT_RUNTIME_H
#define AKVC_PLATFORM_WINDOWS_HELPER_CLIENT_RUNTIME_H

#include <cstdint>
#include <string>
#include <vector>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace akvc::windows {

// Snapshot of the helper daemon's runtime state (CMD_STATUS response).
struct HelperStatus {
    bool valid = false;            // a well-formed status response was received
    std::uint32_t magic = 0;
    std::uint32_t pid = 0;
    std::uint64_t heartbeat_100ns = 0;
    std::uint64_t producer_seq = 0;
};

class HelperClientRuntime {
public:
    HelperClientRuntime();

    // Returns true if the helper daemon answers ping on the control pipe.
    bool ping();

    // Query runtime status (magic / pid / heartbeat / producer seq).
    HelperStatus status();

    // Ensure the helper daemon is running. Tries the installed scheduled task
    // first (if present), then falls back to direct-launching `helper_exe`.
    // Returns true once ping succeeds (within the start timeout).
    bool start_service(const std::string& helper_exe = std::string());

    // ping(); if down, start_service(helper_exe). Convenience wrapper.
    bool ensure_running(const std::string& helper_exe = std::string());

    // Register the Media Foundation virtual camera via MFCreateVirtualCamera
    // (runs in the elevated helper). Required on Windows 11 so MF-based
    // consumers (Chrome/Edge/Teams) see the device. Idempotent.
    bool register_mf(const std::string& name = std::string("AK Virtual Camera"));

    // Ask the helper daemon to exit (CMD_QUIT).
    bool quit();

    bool is_process_elevated() const;

    const std::string& last_error_message() const { return last_error_message_; }
    const std::string& last_pipe_error() const { return last_pipe_error_; }
    const std::string& last_launch_error() const { return last_launch_error_; }

private:
    bool launch(const std::wstring& exe_path, std::uint32_t parent_pid, const std::wstring& log_path);
    bool wait_for_ping(double timeout_s);
    bool start_installed(const std::wstring& task_name, double timeout_s);
    bool scheduled_task_exists(const std::wstring& task_name);
    bool run_schtasks(const std::wstring& args, bool elevate);
    void describe_start_failure(const std::wstring& exe_path);

    std::vector<std::uint8_t> transact(std::uint32_t cmd,
                                       const std::vector<std::uint8_t>& payload = {});

    std::string last_pipe_error_;
    std::string last_launch_error_;
    std::string last_error_message_;
};

}  // namespace akvc::windows

#endif  // AKVC_PLATFORM_WINDOWS_HELPER_CLIENT_RUNTIME_H
