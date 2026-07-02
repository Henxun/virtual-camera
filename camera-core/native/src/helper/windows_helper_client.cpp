#define NOMINMAX

#include "akvc/core_native/frame_types.h"

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#endif

#include "akvc_protocol.h"

namespace akvc::core_native {

namespace {

constexpr std::uint32_t CMD_QUIT = 0x00000001u;
constexpr std::uint32_t CMD_PING = 0x00000002u;
constexpr std::uint32_t CMD_STATUS = 0x00000003u;
constexpr std::uint32_t CMD_REGISTER_MF = 0x00000004u;
constexpr std::uint32_t CMD_UNREGISTER_MF = 0x00000005u;

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
    return py::str(value).cast<std::wstring>();
}

std::string to_string(const std::wstring& value) {
    return py::cast(value).cast<std::string>();
}

std::wstring default_log_path() {
#ifdef _WIN32
    wchar_t temp_path[MAX_PATH]{};
    DWORD length = ::GetTempPathW(MAX_PATH, temp_path);
    if (length == 0 || length >= MAX_PATH) {
        return std::wstring(DEFAULT_LOG_NAME);
    }
    std::filesystem::path path(temp_path);
    path /= DEFAULT_LOG_NAME;
    return path.wstring();
#else
    return std::wstring(DEFAULT_LOG_NAME);
#endif
}

}  // namespace

class NativeWindowsHelperClient {
public:
    NativeWindowsHelperClient() = default;

    bool ping() {
#ifdef _WIN32
        last_pipe_error_.clear();
        const auto data = transact(CMD_PING);
        if (data.size() < sizeof(std::uint32_t)) {
            return false;
        }
        std::uint32_t rsp = 0;
        std::memcpy(&rsp, data.data(), sizeof(rsp));
        return rsp == RSP_PONG;
#else
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    py::object status() {
#ifdef _WIN32
        last_pipe_error_.clear();
        const auto data = transact(CMD_STATUS);
        if (data.size() < 24) {
            return py::none();
        }

        std::uint32_t magic = 0;
        std::uint32_t pid = 0;
        std::uint64_t heartbeat = 0;
        std::uint32_t seq_lo = 0;
        std::uint32_t seq_hi = 0;
        std::memcpy(&magic, data.data(), sizeof(magic));
        std::memcpy(&pid, data.data() + 4, sizeof(pid));
        std::memcpy(&heartbeat, data.data() + 8, sizeof(heartbeat));
        std::memcpy(&seq_lo, data.data() + 16, sizeof(seq_lo));
        std::memcpy(&seq_hi, data.data() + 20, sizeof(seq_hi));

        py::dict out;
        out["magic"] = py::int_(magic);
        out["pid"] = py::int_(pid);
        out["heartbeat_100ns"] = py::int_(heartbeat);
        out["producer_seq"] = py::int_((static_cast<std::uint64_t>(seq_hi) << 32) | seq_lo);
        return std::move(out);
#else
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool register_mf(const std::string& name) {
#ifdef _WIN32
        last_pipe_error_.clear();
        std::wstring wide = py::str(name).cast<std::wstring>();
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
#else
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool unregister_mf() {
#ifdef _WIN32
        last_pipe_error_.clear();
        const auto data = transact(CMD_UNREGISTER_MF);
        if (data.size() < sizeof(std::uint32_t)) {
            return false;
        }
        std::uint32_t rsp = 0;
        std::memcpy(&rsp, data.data(), sizeof(rsp));
        return rsp == RSP_OK;
#else
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool quit() {
#ifdef _WIN32
        last_pipe_error_.clear();
        const auto data = transact(CMD_QUIT);
        if (data.size() < sizeof(std::uint32_t)) {
            return false;
        }
        std::uint32_t rsp = 0;
        std::memcpy(&rsp, data.data(), sizeof(rsp));
        return rsp == RSP_OK;
#else
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool install_autostart(const std::wstring& exe_path, const std::wstring& log_path, const std::wstring& task_name = DEFAULT_TASK_NAME) {
#ifdef _WIN32
        last_launch_error_.clear();
        if (exe_path.empty()) {
            last_launch_error_ = "helper executable path is empty";
            return false;
        }
        const std::wstring resolved_log = log_path.empty() ? std::wstring(L"%TEMP%\\akvc-helper-persistent.log") : log_path;
        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : task_name;
        std::wstring task_run = quote_for_cmd(exe_path) + L" --persistent --log " + quote_for_cmd(resolved_log);
        std::wstring args =
            L"/create /f /tn " + quote_for_cmd(task) +
            L" /sc onlogon /rl highest /tr " + quote_for_cmd(task_run);
        return run_schtasks(args, true);
#else
        (void)exe_path;
        (void)log_path;
        (void)task_name;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool uninstall_autostart(const std::wstring& task_name = DEFAULT_TASK_NAME) {
#ifdef _WIN32
        last_launch_error_.clear();
        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : task_name;
        std::wstring args = L"/delete /f /tn " + quote_for_cmd(task);
        return run_schtasks(args, true);
#else
        (void)task_name;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool start_installed(const std::wstring& task_name = DEFAULT_TASK_NAME) {
#ifdef _WIN32
        last_launch_error_.clear();
        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : task_name;
        std::wstring args = L"/run /tn " + quote_for_cmd(task);
        return run_schtasks(args, false);
#else
        (void)task_name;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    py::dict scheduled_task_status(const std::wstring& task_name = DEFAULT_TASK_NAME) {
#ifdef _WIN32
        last_launch_error_.clear();
        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : task_name;
        py::dict out;
        out["task_name"] = py::cast(task);
        out["installed"] = py::bool_(scheduled_task_exists(task));
        out["pipe_reachable"] = py::bool_(ping());
        return out;
#else
        (void)task_name;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool start_service(const std::string& helper_exe = std::string(),
                       const std::string& task_name = std::string()) {
#ifdef _WIN32
        if (ping()) {
            last_error_message_.clear();
            return true;
        }

        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : to_wstring(task_name);
        if (scheduled_task_exists(task) && start_installed(task)) {
            if (wait_for_ping(START_TIMEOUT_S)) {
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

        const std::wstring exe = helper_exe.empty() ? std::wstring() : to_wstring(helper_exe);
        if (exe.empty()) {
            last_error_message_ =
                "AKVC helper executable not found. Ensure akvc/_runtime/windows/akvc_helper.exe is packaged with the application or set AKVC_HELPER_EXE explicitly.";
            return false;
        }
        if (!launch(exe, ::GetCurrentProcessId(), default_log_path())) {
            if (last_error_message_.empty()) {
                describe_start_failure(exe);
            }
            return false;
        }
        if (wait_for_ping(START_TIMEOUT_S)) {
            last_error_message_.clear();
            return true;
        }
        describe_start_failure(exe);
        return false;
#else
        (void)helper_exe;
        (void)task_name;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool ensure_running(const std::string& helper_exe = std::string(),
                        const std::string& task_name = std::string(),
                        bool prefer_installed = true) {
#ifdef _WIN32
        if (ping()) {
            last_error_message_.clear();
            return true;
        }
        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : to_wstring(task_name);
        if (prefer_installed && scheduled_task_exists(task)) {
            if (start_installed(task) && wait_for_ping(START_TIMEOUT_S)) {
                last_error_message_.clear();
                return true;
            }
        }
        return start_service(helper_exe, task_name);
#else
        (void)helper_exe;
        (void)task_name;
        (void)prefer_installed;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    py::dict status_summary(const std::string& task_name = std::string()) {
#ifdef _WIN32
        const std::wstring task = task_name.empty() ? std::wstring(DEFAULT_TASK_NAME) : to_wstring(task_name);
        py::dict out = scheduled_task_status(task);
        py::object runtime = status();
        if (runtime.is_none()) {
            out["runtime"] = py::none();
        } else {
            out["runtime"] = runtime;
        }
        return out;
#else
        (void)task_name;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    bool is_process_elevated() const {
#ifdef _WIN32
        HANDLE token = nullptr;
        if (!::OpenProcessToken(::GetCurrentProcess(), TOKEN_QUERY, &token)) {
            return false;
        }
        struct TokenHandleCloser {
            HANDLE token;
            ~TokenHandleCloser() {
                if (token != nullptr) {
                    ::CloseHandle(token);
                }
            }
        } closer{token};
        TOKEN_ELEVATION elevation{};
        DWORD size = 0;
        if (!::GetTokenInformation(token, TokenElevation, &elevation, sizeof(elevation), &size)) {
            return false;
        }
        return elevation.TokenIsElevated != 0;
#else
        return false;
#endif
    }

    bool launch(const std::wstring& exe_path, std::uint32_t parent_pid, const std::wstring& log_path) {
#ifdef _WIN32
        last_launch_error_.clear();
        if (exe_path.empty()) {
            last_launch_error_ = "helper executable path is empty";
            return false;
        }

        std::wostringstream args;
        args << L"--pipe \"" << PIPE_NAME << L"\" --parent-pid " << parent_pid << L" --log \"" << log_path << L"\"";
        if (is_process_elevated()) {
            STARTUPINFOW si{};
            si.cb = sizeof(si);
            PROCESS_INFORMATION pi{};
            std::wstring cmdline = L"\"" + exe_path + L"\" " + args.str();
            const BOOL ok = ::CreateProcessW(
                exe_path.c_str(),
                cmdline.data(),
                nullptr,
                nullptr,
                FALSE,
                CREATE_NO_WINDOW,
                nullptr,
                nullptr,
                &si,
                &pi);
            if (!ok) {
                last_launch_error_ = win32_message("CreateProcessW", ::GetLastError());
                return false;
            }
            ::CloseHandle(pi.hThread);
            ::CloseHandle(pi.hProcess);
            return true;
        }

        const HINSTANCE rc = ::ShellExecuteW(
            nullptr,
            L"runas",
            exe_path.c_str(),
            args.str().c_str(),
            nullptr,
            SW_HIDE);
        if (reinterpret_cast<INT_PTR>(rc) <= 32) {
            std::ostringstream oss;
            oss << "ShellExecuteW rc=" << reinterpret_cast<INT_PTR>(rc);
            last_launch_error_ = oss.str();
            return false;
        }
        return true;
#else
        (void)exe_path;
        (void)parent_pid;
        (void)log_path;
        throw std::runtime_error("Windows helper client is only available on Windows");
#endif
    }

    std::string last_pipe_error() const {
        return last_pipe_error_;
    }

    std::string last_launch_error() const {
        return last_launch_error_;
    }

    std::string last_error_message() const {
        return last_error_message_;
    }

#ifdef _WIN32
    bool run_schtasks(const std::wstring& args, bool elevate) {
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

    bool run_shell_command(const std::wstring& command) {
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        PROCESS_INFORMATION pi{};
        std::wstring cmdline = L"cmd.exe /c " + command;
        const BOOL ok = ::CreateProcessW(
            nullptr,
            cmdline.data(),
            nullptr,
            nullptr,
            FALSE,
            CREATE_NO_WINDOW,
            nullptr,
            nullptr,
            &si,
            &pi);
        if (!ok) {
            last_launch_error_ = win32_message("CreateProcessW", ::GetLastError());
            return false;
        }
        ::CloseHandle(pi.hThread);
        DWORD wait_rc = ::WaitForSingleObject(pi.hProcess, 30000);
        if (wait_rc != WAIT_OBJECT_0) {
            ::TerminateProcess(pi.hProcess, 1);
            ::CloseHandle(pi.hProcess);
            last_launch_error_ = "command timed out";
            return false;
        }
        DWORD exit_code = 1;
        ::GetExitCodeProcess(pi.hProcess, &exit_code);
        ::CloseHandle(pi.hProcess);
        if (exit_code != 0) {
            std::ostringstream oss;
            oss << "command exit=" << exit_code;
            last_launch_error_ = oss.str();
            return false;
        }
        return true;
    }

    bool scheduled_task_exists(const std::wstring& task_name) {
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        PROCESS_INFORMATION pi{};
        std::wstring cmdline = L"cmd.exe /c schtasks /query /tn " + quote_for_cmd(task_name);
        const BOOL ok = ::CreateProcessW(
            nullptr,
            cmdline.data(),
            nullptr,
            nullptr,
            FALSE,
            CREATE_NO_WINDOW,
            nullptr,
            nullptr,
            &si,
            &pi);
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

    std::vector<std::uint8_t> transact(
        std::uint32_t cmd,
        const std::vector<std::uint8_t>& payload = {}) {
        if (!::WaitNamedPipeW(PIPE_NAME, WAIT_TIMEOUT_MS)) {
            last_pipe_error_ = win32_message("WaitNamedPipeW", ::GetLastError());
            return {};
        }

        HANDLE handle = ::CreateFileW(
            PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE,
            0,
            nullptr,
            OPEN_EXISTING,
            0,
            nullptr);
        if (handle == INVALID_HANDLE_VALUE) {
            last_pipe_error_ = win32_message("CreateFileW", ::GetLastError());
            return {};
        }

        struct HandleCloser {
            HANDLE handle;
            ~HandleCloser() {
                if (handle != INVALID_HANDLE_VALUE) {
                    ::CloseHandle(handle);
                }
            }
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

    bool wait_for_ping(double timeout_s) {
#ifdef _WIN32
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_s);
        while (std::chrono::steady_clock::now() < deadline) {
            if (ping()) {
                last_error_message_.clear();
                return true;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
        return false;
#else
        (void)timeout_s;
        return false;
#endif
    }

    void describe_start_failure(const std::wstring& exe_path) {
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

    static std::string win32_message(const char* op, DWORD err) {
        std::ostringstream oss;
        oss << op << " err=" << err;
        return oss.str();
    }
#endif

    std::string last_pipe_error_;
    std::string last_launch_error_;
    std::string last_error_message_;
};

void bind_windows_helper_client(py::module_& m) {
    py::class_<NativeWindowsHelperClient>(m, "NativeWindowsHelperClient")
        .def(py::init<>())
        .def("ping", &NativeWindowsHelperClient::ping)
        .def("status", &NativeWindowsHelperClient::status)
        .def("status_summary", &NativeWindowsHelperClient::status_summary, py::arg("task_name") = std::string())
        .def("register_mf", &NativeWindowsHelperClient::register_mf, py::arg("name"))
        .def("unregister_mf", &NativeWindowsHelperClient::unregister_mf)
        .def("quit", &NativeWindowsHelperClient::quit)
        .def("launch", &NativeWindowsHelperClient::launch, py::arg("exe_path"), py::arg("parent_pid"), py::arg("log_path"))
        .def("install_autostart", &NativeWindowsHelperClient::install_autostart, py::arg("exe_path"), py::arg("log_path"), py::arg("task_name") = std::wstring(DEFAULT_TASK_NAME))
        .def("uninstall_autostart", &NativeWindowsHelperClient::uninstall_autostart, py::arg("task_name") = std::wstring(DEFAULT_TASK_NAME))
        .def("start_installed", &NativeWindowsHelperClient::start_installed, py::arg("task_name") = std::wstring(DEFAULT_TASK_NAME))
        .def("scheduled_task_status", &NativeWindowsHelperClient::scheduled_task_status, py::arg("task_name") = std::wstring(DEFAULT_TASK_NAME))
        .def("start_service", &NativeWindowsHelperClient::start_service, py::arg("helper_exe") = std::string(), py::arg("task_name") = std::string())
        .def("ensure_running", &NativeWindowsHelperClient::ensure_running, py::arg("helper_exe") = std::string(), py::arg("task_name") = std::string(), py::arg("prefer_installed") = true)
        .def("is_process_elevated", &NativeWindowsHelperClient::is_process_elevated)
        .def_property_readonly("last_pipe_error", &NativeWindowsHelperClient::last_pipe_error)
        .def_property_readonly("last_launch_error", &NativeWindowsHelperClient::last_launch_error)
        .def_property_readonly("last_error_message", &NativeWindowsHelperClient::last_error_message);
}

}  // namespace akvc::core_native
