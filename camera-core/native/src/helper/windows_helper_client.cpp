#define NOMINMAX

#include "akvc/core_native/frame_types.h"

#include <cstdint>
#include <cstring>
#include <sstream>
#include <stdexcept>

#ifdef _WIN32
#include <windows.h>
#endif

#include "akvc_protocol.h"

namespace akvc::core_native {

namespace {

constexpr std::uint32_t CMD_QUIT = 0x00000001u;
constexpr std::uint32_t CMD_PING = 0x00000002u;
constexpr std::uint32_t CMD_STATUS = 0x00000003u;
constexpr std::uint32_t CMD_REGISTER_MF = 0x00000004u;

constexpr std::uint32_t RSP_OK = 0x00000000u;
constexpr std::uint32_t RSP_PONG = 0x00000001u;

constexpr const wchar_t* PIPE_NAME = L"\\\\.\\pipe\\akvc-helper-ctrl";
constexpr std::uint32_t WAIT_TIMEOUT_MS = 250;

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

private:
#ifdef _WIN32
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

    static std::string win32_message(const char* op, DWORD err) {
        std::ostringstream oss;
        oss << op << " err=" << err;
        return oss.str();
    }
#endif

    std::string last_pipe_error_;
    std::string last_launch_error_;
};

void bind_windows_helper_client(py::module_& m) {
    py::class_<NativeWindowsHelperClient>(m, "NativeWindowsHelperClient")
        .def(py::init<>())
        .def("ping", &NativeWindowsHelperClient::ping)
        .def("status", &NativeWindowsHelperClient::status)
        .def("register_mf", &NativeWindowsHelperClient::register_mf, py::arg("name"))
        .def("quit", &NativeWindowsHelperClient::quit)
        .def("launch", &NativeWindowsHelperClient::launch, py::arg("exe_path"), py::arg("parent_pid"), py::arg("log_path"))
        .def("is_process_elevated", &NativeWindowsHelperClient::is_process_elevated)
        .def_property_readonly("last_pipe_error", &NativeWindowsHelperClient::last_pipe_error)
        .def_property_readonly("last_launch_error", &NativeWindowsHelperClient::last_launch_error);
}

}  // namespace akvc::core_native
