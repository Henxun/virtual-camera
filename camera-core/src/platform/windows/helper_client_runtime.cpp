// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Pure-C++ port of NativeWindowsHelperClient (runtime subset). See header.

#include "akvc/platform/windows/helper_client_runtime.h"

#include <chrono>
#include <cstring>
#include <filesystem>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>

#include <shellapi.h>  // ShellExecuteW / ShellExecuteExW (WIN32_LEAN_AND_MEAN excludes it)

#include "akvc_protocol.h"  // AKVC_HELPER_PIPE

namespace akvc::windows {

namespace {

constexpr std::uint32_t CMD_QUIT = 0x00000001u;
constexpr std::uint32_t CMD_PING = 0x00000002u;
constexpr std::uint32_t CMD_STATUS = 0x00000003u;
constexpr std::uint32_t CMD_REGISTER_MF = 0x00000004u;  // MFCreateVirtualCamera (Win11+)
// CMD_REGISTER_MF / CMD_UNREGISTER_MF deliberately absent — installation is
// out of scope for the control layer.

constexpr std::uint32_t RSP_OK = 0x00000000u;
constexpr std::uint32_t RSP_PONG = 0x00000001u;

constexpr const wchar_t* PIPE_NAME = L"\\\\.\\pipe\\akvc-helper-ctrl";
constexpr const wchar_t* DEFAULT_TASK_NAME = L"AKVirtualCameraHelper";
constexpr const wchar_t* DEFAULT_LOG_NAME = L"akvc-helper-persistent.log";
constexpr double START_TIMEOUT_S = 8.0;
constexpr std::uint32_t WAIT_TIMEOUT_MS = 250;

std::wstring quote_for_cmd(const std::wstring& value) {
    std::wstring out;
    out.reserve(value.size() + 2);
    out.push_back(L'"');
    for (wchar_t ch : value) {
        if (ch == L'"') {
            out.push_back(L'\\');
        }
        out.push_back(ch);
    }
    out.push_back(L'"');
    return out;
}

std::wstring to_wstring(const std::string& value) {
    if (value.empty()) {
        return std::wstring();
    }
    int needed = ::MultiByteToWideChar(CP_UTF8, 0, value.c_str(),
                                       static_cast<int>(value.size()), nullptr, 0);
    std::wstring out(needed, L'\0');
    ::MultiByteToWideChar(CP_UTF8, 0, value.c_str(),
                          static_cast<int>(value.size()), out.data(), needed);
    return out;
}

std::string to_string(const std::wstring& value) {
    if (value.empty()) {
        return std::string();
    }
    int needed = ::WideCharToMultiByte(CP_UTF8, 0, value.c_str(),
                                       static_cast<int>(value.size()), nullptr, 0,
                                       nullptr, nullptr);
    std::string out(needed, '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, value.c_str(),
                          static_cast<int>(value.size()), out.data(), needed,
                          nullptr, nullptr);
    return out;
}

std::wstring default_log_path() {
    wchar_t temp_path[MAX_PATH]{};
    DWORD length = ::GetTempPathW(MAX_PATH, temp_path);
    if (length == 0 || length >= MAX_PATH) {
        return std::wstring(DEFAULT_LOG_NAME);
    }
    std::filesystem::path path(temp_path);
    path /= DEFAULT_LOG_NAME;
    return path.wstring();
}

std::string win32_message(const char* op, DWORD err) {
    std::ostringstream oss;
    oss << op << " err=" << err;
    return oss.str();
}

}  // namespace

HelperClientRuntime::HelperClientRuntime() = default;

bool HelperClientRuntime::ping() {
    last_pipe_error_.clear();
    const auto data = transact(CMD_PING);
    if (data.size() < sizeof(std::uint32_t)) {
        return false;
    }
    std::uint32_t rsp = 0;
    std::memcpy(&rsp, data.data(), sizeof(rsp));
    return rsp == RSP_PONG;
}

HelperStatus HelperClientRuntime::status() {
    last_pipe_error_.clear();
    HelperStatus out{};
    const auto data = transact(CMD_STATUS);
    if (data.size() < 24) {
        return out;
    }
    std::uint32_t magic = 0, pid = 0, seq_lo = 0, seq_hi = 0;
    std::uint64_t heartbeat = 0;
    std::memcpy(&magic, data.data(), sizeof(magic));
    std::memcpy(&pid, data.data() + 4, sizeof(pid));
    std::memcpy(&heartbeat, data.data() + 8, sizeof(heartbeat));
    std::memcpy(&seq_lo, data.data() + 16, sizeof(seq_lo));
    std::memcpy(&seq_hi, data.data() + 20, sizeof(seq_hi));
    out.valid = true;
    out.magic = magic;
    out.pid = pid;
    out.heartbeat_100ns = heartbeat;
    out.producer_seq = (static_cast<std::uint64_t>(seq_hi) << 32) | seq_lo;
    return out;
}

bool HelperClientRuntime::start_service(const std::string& helper_exe) {
    if (ping()) {
        last_error_message_.clear();
        return true;
    }

    const std::wstring task = DEFAULT_TASK_NAME;
    std::string installed_task_error;
    if (scheduled_task_exists(task)) {
        if (start_installed(task, START_TIMEOUT_S)) {
            last_error_message_.clear();
            return true;
        }
        installed_task_error = last_error_message_;
    }

    const std::wstring exe = helper_exe.empty() ? std::wstring() : to_wstring(helper_exe);
    if (exe.empty()) {
        if (!installed_task_error.empty()) {
            last_error_message_ = installed_task_error;
        } else {
            last_error_message_ =
                "AKVC helper executable not found. Ensure akvc_helper.exe is "
                "packaged with the application or set the helper path explicitly.";
        }
        return false;
    }
    if (!launch(exe, ::GetCurrentProcessId(), default_log_path())) {
        if (installed_task_error.empty()) {
            if (last_error_message_.empty()) {
                describe_start_failure(exe);
            }
            return false;
        }
        const std::string direct_launch_error = last_error_message_.empty()
            ? std::string("failed to direct-launch helper executable")
            : last_error_message_;
        std::ostringstream oss;
        oss << installed_task_error << " Fallback direct launch also failed. " << direct_launch_error;
        last_error_message_ = oss.str();
        return false;
    }
    if (wait_for_ping(START_TIMEOUT_S)) {
        last_error_message_.clear();
        return true;
    }
    describe_start_failure(exe);
    if (!installed_task_error.empty()) {
        std::ostringstream oss;
        oss << installed_task_error << " Fallback direct launch also failed. " << last_error_message_;
        last_error_message_ = oss.str();
    }
    return false;
}

bool HelperClientRuntime::quit() {
    last_pipe_error_.clear();
    const auto data = transact(CMD_QUIT);
    if (data.size() < sizeof(std::uint32_t)) {
        return false;
    }
    std::uint32_t rsp = 0;
    std::memcpy(&rsp, data.data(), sizeof(rsp));
    return rsp == RSP_OK;
}

bool HelperClientRuntime::is_process_elevated() const {
    HANDLE token = nullptr;
    if (!::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY, &token)) {
        return false;
    }
    struct TokenHandleCloser {
        HANDLE token;
        ~TokenHandleCloser() { if (token != nullptr) ::CloseHandle(token); }
    } closer{token};
    TOKEN_ELEVATION elevation{};
    DWORD size = 0;
    if (!::GetTokenInformation(token, TokenElevation, &elevation, sizeof(elevation), &size)) {
        return false;
    }
    return elevation.TokenIsElevated != 0;
}

bool HelperClientRuntime::launch(const std::wstring& exe_path, std::uint32_t parent_pid,
                                 const std::wstring& log_path) {
    last_launch_error_.clear();
    if (exe_path.empty()) {
        last_launch_error_ = "helper executable path is empty";
        return false;
    }

    std::wostringstream args;
    args << L"--pipe \"" << PIPE_NAME << L"\" --parent-pid " << parent_pid
         << L" --log \"" << log_path << L"\"";
    if (is_process_elevated()) {
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        PROCESS_INFORMATION pi{};
        std::wstring cmdline = L"\"" + exe_path + L"\" " + args.str();
        const BOOL ok = ::CreateProcessW(
            exe_path.c_str(), cmdline.data(), nullptr, nullptr, FALSE,
            CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
        if (!ok) {
            last_launch_error_ = win32_message("CreateProcessW", ::GetLastError());
            return false;
        }
        ::CloseHandle(pi.hThread);
        ::CloseHandle(pi.hProcess);
        return true;
    }

    const HINSTANCE rc = ::ShellExecuteW(
        nullptr, L"runas", exe_path.c_str(), args.str().c_str(), nullptr, SW_HIDE);
    if (reinterpret_cast<INT_PTR>(rc) <= 32) {
        std::ostringstream oss;
        oss << "ShellExecuteW rc=" << reinterpret_cast<INT_PTR>(rc);
        last_launch_error_ = oss.str();
        return false;
    }
    return true;
}

bool HelperClientRuntime::wait_for_ping(double timeout_s) {
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::duration<double>(timeout_s);
    while (std::chrono::steady_clock::now() < deadline) {
        if (ping()) {
            last_error_message_.clear();
            return true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    return false;
}

bool HelperClientRuntime::start_installed(const std::wstring& task_name, double timeout_s) {
    last_launch_error_.clear();
    const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : task_name;
    std::wstring args = L"/run /tn " + quote_for_cmd(task);
    if (!run_schtasks(args, false)) {
        return false;
    }
    if (wait_for_ping(timeout_s)) {
        last_error_message_.clear();
        return true;
    }
    if (last_error_message_.empty()) {
        std::ostringstream oss;
        oss << "Installed AKVC helper task " << to_string(task)
            << " started but did not expose pipe in time.";
        last_error_message_ = oss.str();
    }
    return false;
}

bool HelperClientRuntime::scheduled_task_exists(const std::wstring& task_name) {
    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    std::wstring cmdline = L"cmd.exe /c schtasks /query /tn " + quote_for_cmd(task_name);
    const BOOL ok = ::CreateProcessW(
        nullptr, cmdline.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
        nullptr, nullptr, &si, &pi);
    if (!ok) {
        return false;
    }
    ::CloseHandle(pi.hThread);
    DWORD wait_rc = ::WaitForSingleObject(pi.hProcess, 15000);
    if (wait_rc != WAIT_OBJECT_0) {
        ::TerminateProcess(pi.hProcess, 1);
        ::CloseHandle(pi.hProcess);
        return false;
    }
    DWORD exit_code = 1;
    ::GetExitCodeProcess(pi.hProcess, &exit_code);
    ::CloseHandle(pi.hProcess);
    return exit_code == 0;
}

bool HelperClientRuntime::run_schtasks(const std::wstring& args, bool elevate) {
    SHELLEXECUTEINFOW sei{};
    sei.cbSize = sizeof(sei);
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb = elevate && !is_process_elevated() ? L"runas" : L"open";
    sei.lpFile = L"schtasks.exe";
    sei.lpParameters = args.c_str();
    sei.nShow = SW_HIDE;
    if (!::ShellExecuteExW(&sei)) {
        last_launch_error_ = win32_message("ShellExecuteExW", ::GetLastError());
        return false;
    }
    DWORD wait_rc = ::WaitForSingleObject(sei.hProcess, 30000);
    if (wait_rc != WAIT_OBJECT_0) {
        ::TerminateProcess(sei.hProcess, 1);
        ::CloseHandle(sei.hProcess);
        last_launch_error_ = "command timed out";
        return false;
    }
    DWORD exit_code = 1;
    ::GetExitCodeProcess(sei.hProcess, &exit_code);
    ::CloseHandle(sei.hProcess);
    if (exit_code != 0) {
        std::ostringstream oss;
        oss << "command exit=" << exit_code;
        last_launch_error_ = oss.str();
        return false;
    }
    return true;
}

void HelperClientRuntime::describe_start_failure(const std::wstring& exe_path) {
    std::ostringstream oss;
    oss << "AKVC helper at " << to_string(exe_path)
        << " did not start or the control pipe " << to_string(PIPE_NAME)
        << " is not ready.";
    if (!last_launch_error_.empty()) {
        oss << " " << last_launch_error_;
    }
    if (!last_pipe_error_.empty()) {
        oss << " " << last_pipe_error_;
    }
    last_error_message_ = oss.str();
}

bool HelperClientRuntime::ensure_running(const std::string& helper_exe) {
    if (ping()) {
        last_error_message_.clear();
        return true;
    }
    return start_service(helper_exe);
}

bool HelperClientRuntime::register_mf(const std::string& name) {
    last_pipe_error_.clear();
    std::wstring wide = to_wstring(name);
    if (wide.size() > 255) {
        wide.resize(255);
    }
    std::vector<std::uint8_t> payload(sizeof(std::uint32_t) + wide.size() * sizeof(wchar_t));
    const auto wchar_count = static_cast<std::uint32_t>(wide.size());
    std::memcpy(payload.data(), &wchar_count, sizeof(wchar_count));
    if (!wide.empty()) {
        std::memcpy(payload.data() + sizeof(wchar_count), wide.data(), wide.size() * sizeof(wchar_t));
    }
    const auto data = transact(CMD_REGISTER_MF, payload);
    if (data.size() < sizeof(std::uint32_t)) {
        return false;
    }
    std::uint32_t rsp = 0;
    std::memcpy(&rsp, data.data(), sizeof(rsp));
    return rsp == RSP_OK;
}

std::vector<std::uint8_t> HelperClientRuntime::transact(
    std::uint32_t cmd, const std::vector<std::uint8_t>& payload) {
    if (!::WaitNamedPipeW(PIPE_NAME, WAIT_TIMEOUT_MS)) {
        last_pipe_error_ = win32_message("WaitNamedPipeW", ::GetLastError());
        return {};
    }
    HANDLE handle = ::CreateFileW(
        PIPE_NAME, GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        last_pipe_error_ = win32_message("CreateFileW", ::GetLastError());
        return {};
    }
    struct HandleCloser {
        HANDLE handle;
        ~HandleCloser() { if (handle != INVALID_HANDLE_VALUE) ::CloseHandle(handle); }
    } closer{handle};

    std::vector<std::uint8_t> request(sizeof(std::uint32_t) + payload.size());
    std::memcpy(request.data(), &cmd, sizeof(cmd));
    if (!payload.empty()) {
        std::memcpy(request.data() + sizeof(cmd), payload.data(), payload.size());
    }

    DWORD written = 0;
    if (!::WriteFile(handle, request.data(), static_cast<DWORD>(request.size()), &written, nullptr) ||
        written != request.size()) {
        last_pipe_error_ = win32_message("WriteFile", ::GetLastError());
        return {};
    }

    const DWORD expected = cmd == CMD_STATUS ? 24u : 4u;
    std::vector<std::uint8_t> response(expected);
    DWORD read = 0;
    if (!::ReadFile(handle, response.data(), expected, &read, nullptr) || read != expected) {
        last_pipe_error_ = win32_message("ReadFile", ::GetLastError());
        return {};
    }
    return response;
}

}  // namespace akvc::windows
