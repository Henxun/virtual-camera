// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Thin pybind11 binding over akvc::VirtualCamera, for the PySide6 desktop app.
// This is NOT the third-party interface (that is the C++ class API); it exists
// solely so apps/desktop can drive the C++ control layer from Python.

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>

#include "akvc/frame_input.h"
#include "akvc/pixel_format.h"
#include "akvc/status.h"
#include "akvc/virtual_camera.h"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include "akvc/platform/windows/helper_client_runtime.h"
#endif

namespace py = pybind11;

#ifdef __APPLE__
extern "C" int akvc_macos_system_extension_status_json(
    double timeout_seconds,
    char* json_buffer,
    size_t json_capacity,
    char* error_buffer,
    size_t error_capacity
);

extern "C" int akvc_macos_activate_system_extension(
    double timeout_seconds,
    char* error_buffer,
    size_t error_capacity
);

extern "C" int akvc_macos_direct_sender_list_devices_json(
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
);
#endif

namespace {

py::object json_loads_py(const std::string& value) {
    return py::module_::import("json").attr("loads")(py::str(value));
}

std::string json_dumps_py(const py::handle& value) {
    return py::module_::import("json").attr("dumps")(value).cast<std::string>();
}

std::vector<std::string> strings_from_py(const py::handle& value) {
    std::vector<std::string> out;
    if (value.is_none()) {
        return out;
    }
    if (!py::isinstance<py::list>(value) && !py::isinstance<py::tuple>(value)) {
        return out;
    }
    for (const py::handle item : value) {
        const std::string text = py::str(item).cast<std::string>();
        if (!text.empty()) {
            out.push_back(text);
        }
    }
    return out;
}

py::list pylist_from_strings(const std::vector<std::string>& values) {
    py::list out;
    for (const auto& value : values) {
        out.append(value);
    }
    return out;
}

// Coerce an array-like to a uint8 contiguous buffer and dispatch to
// VirtualCamera::push_frame. Accepts HxW (gray, expanded to BGR), HxWx3 (BGR24
// by default), HxWx4 (BGRA32 by default). `format` overrides the inferred
// PixelFormat; `pts` is the 100ns presentation timestamp (0 = host clock).
akvc::Status push_frame_py(akvc::VirtualCamera& self,
                           py::array array,
                           py::object format_obj,
                           std::uint64_t pts) {
    py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast> arr(array);
    auto buf = arr.request();

    if (buf.ndim == 2) {
        const int h = static_cast<int>(buf.shape[0]);
        const int w = static_cast<int>(buf.shape[1]);
        const auto* src = static_cast<const std::uint8_t*>(buf.ptr);
        std::vector<std::uint8_t> bgr(static_cast<size_t>(w) * h * 3);
        for (int i = 0; i < w * h; ++i) {
            bgr[i * 3 + 0] = src[i];
            bgr[i * 3 + 1] = src[i];
            bgr[i * 3 + 2] = src[i];
        }
        akvc::FrameInput f{bgr.data(), w, h, w * 3, akvc::PixelFormat::BGR24, pts};
        return self.push_frame(f);
    }

    if (buf.ndim != 3) {
        throw std::runtime_error("frame array must be 2D (HxW) or 3D (HxWxC)");
    }
    const int h = static_cast<int>(buf.shape[0]);
    const int w = static_cast<int>(buf.shape[1]);
    const int c = static_cast<int>(buf.shape[2]);
    if (c != 3 && c != 4) {
        throw std::runtime_error("frame array channels must be 3 or 4");
    }

    akvc::PixelFormat fmt = (c == 4) ? akvc::PixelFormat::BGRA32 : akvc::PixelFormat::BGR24;
    if (!format_obj.is_none()) {
        fmt = format_obj.cast<akvc::PixelFormat>();
    }
    akvc::FrameInput f{static_cast<const std::uint8_t*>(buf.ptr), w, h, w * c, fmt, pts};
    return self.push_frame(f);
}

py::dict apply_payload_flags(py::dict root, bool action_taken) {
    const std::string blocker_code = py::str(root["blocker_code"]).cast<std::string>();
    const bool ready = py::bool_(root["ready"]).cast<bool>();
    const bool requires_user_action = blocker_code == "approval_required"
        || blocker_code == "needs_reboot"
        || blocker_code == "camera_access_denied"
        || blocker_code == "camera_access_restricted"
        || blocker_code == "virtual_camera_not_registered";
    const bool fatal = blocker_code == "diagnostic_failed"
        || blocker_code == "akvc_runtime_missing"
        || blocker_code == "unsupported_platform"
        || blocker_code == "akvc_sdk_unavailable";
    root["action_taken"] = action_taken;
    root["requires_user_action"] = requires_user_action;
    root["can_retry"] = !ready && !fatal && blocker_code != "needs_reboot";
    root["fatal"] = fatal;
    return root;
}

#ifdef __APPLE__
std::string macos_system_extension_status_json_py(double timeout_seconds) {
    std::vector<char> payload(16384, '\0');
    char error[1024] = {0};
    const int rc = akvc_macos_system_extension_status_json(
        timeout_seconds,
        payload.data(),
        payload.size(),
        error,
        sizeof(error)
    );
    if (rc != 0) {
        throw std::runtime_error(error[0] ? error : "macOS system extension status query failed");
    }
    return std::string(payload.data());
}

bool macos_activate_system_extension_py(double timeout_seconds) {
    char error[1024] = {0};
    const int rc = akvc_macos_activate_system_extension(timeout_seconds, error, sizeof(error));
    if (rc != 0) {
        throw std::runtime_error(error[0] ? error : "macOS system extension activation failed");
    }
    return true;
}

std::string macos_list_devices_json_py() {
    std::vector<char> payload(16384, '\0');
    char error[1024] = {0};
    const int rc = akvc_macos_direct_sender_list_devices_json(
        payload.data(),
        payload.size(),
        error,
        sizeof(error)
    );
    if (rc != 0) {
        throw std::runtime_error(error[0] ? error : "macOS device enumeration failed");
    }
    return std::string(payload.data());
}

py::dict macos_probe_payload_py(const std::string& camera_name, double timeout_seconds) {
    py::dict status;
    try {
        status = json_loads_py(macos_system_extension_status_json_py(timeout_seconds)).cast<py::dict>();
    } catch (const std::exception& exc) {
        status["state"] = "install_failed";
        status["enabled"] = false;
        status["approval_required"] = false;
        status["needs_reboot"] = false;
        status["ipc_environment_blocked"] = false;
        status["last_error"] = std::string(exc.what());
    }

    py::dict devices;
    try {
        devices = json_loads_py(macos_list_devices_json_py()).cast<py::dict>();
    } catch (const std::exception& exc) {
        devices["all_devices"] = py::list();
        devices["cmio_devices"] = py::list();
        devices["camera_access_status"] = "unknown";
        devices["camera_access_denied"] = false;
        devices["camera_access_restricted"] = false;
        devices["environment_device_enumeration_empty"] = true;
        devices["last_error"] = std::string(exc.what());
    }

    std::vector<std::string> visible_devices = strings_from_py(devices["all_devices"]);
    if (visible_devices.empty()) {
        visible_devices = strings_from_py(devices["cmio_devices"]);
    }

    const std::string camera_access_status = py::str(status.contains("camera_access_status")
        ? status["camera_access_status"]
        : (devices.contains("camera_access_status") ? devices["camera_access_status"] : py::str(""))).cast<std::string>();
    const bool camera_access_denied = devices.contains("camera_access_denied")
        ? py::bool_(devices["camera_access_denied"]).cast<bool>()
        : camera_access_status == "denied";
    const bool camera_access_restricted = devices.contains("camera_access_restricted")
        ? py::bool_(devices["camera_access_restricted"]).cast<bool>()
        : camera_access_status == "restricted";
    const bool approval_required = status.contains("approval_required")
        ? py::bool_(status["approval_required"]).cast<bool>()
        : false;
    const bool needs_reboot = status.contains("needs_reboot")
        ? py::bool_(status["needs_reboot"]).cast<bool>()
        : false;
    const bool enabled = status.contains("enabled")
        ? py::bool_(status["enabled"]).cast<bool>()
        : false;
    const bool ipc_environment_blocked = status.contains("ipc_environment_blocked")
        ? py::bool_(status["ipc_environment_blocked"]).cast<bool>()
        : false;
    const std::string state = status.contains("state")
        ? py::str(status["state"]).cast<std::string>()
        : std::string();
    const std::string last_error = status.contains("last_error")
        ? py::str(status["last_error"]).cast<std::string>()
        : std::string();
    const bool target_visible = std::find(visible_devices.begin(), visible_devices.end(), camera_name) != visible_devices.end();

    std::string blocker_code = "not_ready";
    std::string detail = last_error;
    if (camera_access_denied || camera_access_status == "denied") {
        blocker_code = "camera_access_denied";
        detail = "Enable camera access for amaran Desktop in System Settings.";
    } else if (camera_access_restricted || camera_access_status == "restricted") {
        blocker_code = "camera_access_restricted";
        detail = "Camera access is restricted by the current system policy.";
    } else if (approval_required || state == "install_pending_approval") {
        blocker_code = "approval_required";
        detail = "Approve the AK Virtual Camera extension in System Settings, then try again.";
    } else if (needs_reboot || state == "waiting_to_uninstall_on_reboot") {
        blocker_code = "needs_reboot";
        detail = "Restart macOS before trying to enable the virtual camera again.";
    } else if (state == "not_installed") {
        blocker_code = "not_installed";
        detail = "The AK Virtual Camera extension is not installed yet.";
    } else if (ipc_environment_blocked) {
        blocker_code = "ipc_environment_blocked";
    } else if (state == "install_failed") {
        blocker_code = "extension_install_failed";
    } else if (enabled && target_visible) {
        blocker_code = "ready";
        detail.clear();
    } else if (enabled) {
        blocker_code = "virtual_camera_device_unavailable";
        detail = "The virtual camera extension is enabled, but the virtual camera device is not visible yet.";
    }

    py::dict root;
    root["platform"] = "macos";
    root["ready"] = blocker_code == "ready";
    root["blocker_code"] = blocker_code;
    root["detail"] = detail;
    root["status"] = status;
    root["devices"] = devices;

    py::dict device;
    device["target_name"] = camera_name;
    device["visible"] = target_visible;
    device["visible_devices"] = pylist_from_strings(visible_devices);
    device["all_devices"] = devices.contains("all_devices") ? devices["all_devices"] : pylist_from_strings(visible_devices);
    device["environment_device_enumeration_empty"] = devices.contains("environment_device_enumeration_empty")
        ? devices["environment_device_enumeration_empty"]
        : py::bool_(visible_devices.empty());
    root["device"] = device;

    py::dict installation;
    installation["extension_state"] = state;
    installation["enabled"] = enabled;
    installation["approval_required"] = approval_required;
    installation["needs_reboot"] = needs_reboot;
    installation["ipc_environment_blocked"] = ipc_environment_blocked;
    root["installation"] = installation;

    py::dict permissions;
    permissions["camera_access_status"] = camera_access_status;
    root["permissions"] = permissions;
    return apply_payload_flags(root, false);
}
#else
std::string macos_system_extension_status_json_py(double timeout_seconds) {
    (void)timeout_seconds;
    throw std::runtime_error("macOS system extension status is only available on macOS");
}

bool macos_activate_system_extension_py(double timeout_seconds) {
    (void)timeout_seconds;
    throw std::runtime_error("macOS system extension activation is only available on macOS");
}

std::string macos_list_devices_json_py() {
    throw std::runtime_error("macOS device enumeration is only available on macOS");
}
#endif

#ifdef _WIN32
std::wstring wide_from_utf8(const std::string& value) {
    if (value.empty()) {
        return std::wstring();
    }
    const int needed = ::MultiByteToWideChar(
        CP_UTF8,
        0,
        value.c_str(),
        static_cast<int>(value.size()),
        nullptr,
        0
    );
    std::wstring out(static_cast<size_t>(needed), L'\0');
    ::MultiByteToWideChar(
        CP_UTF8,
        0,
        value.c_str(),
        static_cast<int>(value.size()),
        out.data(),
        needed
    );
    return out;
}

std::string utf8_from_wide(const std::wstring& value) {
    if (value.empty()) {
        return std::string();
    }
    const int needed = ::WideCharToMultiByte(
        CP_UTF8,
        0,
        value.c_str(),
        static_cast<int>(value.size()),
        nullptr,
        0,
        nullptr,
        nullptr
    );
    std::string out(static_cast<size_t>(needed), '\0');
    ::WideCharToMultiByte(
        CP_UTF8,
        0,
        value.c_str(),
        static_cast<int>(value.size()),
        out.data(),
        needed,
        nullptr,
        nullptr
    );
    return out;
}

bool path_exists_utf8(const std::string& value) {
    if (value.empty()) {
        return false;
    }
    return std::filesystem::is_regular_file(std::filesystem::path(wide_from_utf8(value)));
}

std::string normalize_path_utf8(const std::string& value) {
    if (value.empty()) {
        return std::string();
    }
    std::error_code ec;
    const auto canonical = std::filesystem::weakly_canonical(std::filesystem::path(wide_from_utf8(value)), ec);
    return utf8_from_wide((ec ? std::filesystem::path(wide_from_utf8(value)) : canonical).wstring());
}

std::string resolve_windows_runtime_asset(const std::string& env_key,
                                          const std::wstring& filename,
                                          bool prefer_dshow_layout) {
    if (!env_key.empty()) {
        wchar_t env_buffer[32767]{};
        const std::wstring env_key_wide = wide_from_utf8(env_key);
        const DWORD length = ::GetEnvironmentVariableW(env_key_wide.c_str(), env_buffer, static_cast<DWORD>(std::size(env_buffer)));
        if (length > 0 && length < std::size(env_buffer)) {
            const std::filesystem::path env_path(env_buffer);
            if (std::filesystem::is_regular_file(env_path)) {
                return normalize_path_utf8(utf8_from_wide(env_path.wstring()));
            }
        }
    }

    wchar_t module_path[MAX_PATH]{};
    const DWORD module_length = ::GetModuleFileNameW(nullptr, module_path, MAX_PATH);
    if (module_length == 0 || module_length >= MAX_PATH) {
        return std::string();
    }
    const auto module_dir = std::filesystem::path(module_path).parent_path();
    std::vector<std::filesystem::path> candidates;
    if (prefer_dshow_layout) {
        candidates.push_back(module_dir.parent_path() / L"dshow" / L"Release" / filename);
    }
    candidates.push_back(module_dir / filename);

    for (const auto& candidate : candidates) {
        if (std::filesystem::is_regular_file(candidate)) {
            return normalize_path_utf8(utf8_from_wide(candidate.wstring()));
        }
    }
    return std::string();
}

std::wstring normalize_windows_path(const std::string& value) {
    std::wstring out = wide_from_utf8(value);
    for (wchar_t& ch : out) {
        if (ch == L'/') {
            ch = L'\\';
        }
        ch = static_cast<wchar_t>(::towlower(ch));
    }
    return out;
}

bool is_windows_11_or_later_probe() {
    OSVERSIONINFOEXW osvi{};
    osvi.dwOSVersionInfoSize = sizeof(osvi);
    using RtlGetVersion_t = LONG(WINAPI*)(OSVERSIONINFOEXW*);
    HMODULE ntdll = ::GetModuleHandleW(L"ntdll.dll");
    if (ntdll == nullptr) {
        return false;
    }
    auto pRtlGetVersion = reinterpret_cast<RtlGetVersion_t>(::GetProcAddress(ntdll, "RtlGetVersion"));
    if (pRtlGetVersion == nullptr || pRtlGetVersion(&osvi) != 0) {
        return false;
    }
    return osvi.dwMajorVersion >= 10 && osvi.dwBuildNumber >= 22000;
}

std::string read_registered_inproc_path_for_subkey(const wchar_t* subkey) {
    HKEY key = nullptr;
    LONG rc = ::RegOpenKeyExW(
        HKEY_CLASSES_ROOT,
        subkey,
        0,
        KEY_READ,
        &key
    );
    if (rc != ERROR_SUCCESS) {
        return std::string();
    }
    struct KeyCloser {
        HKEY key;
        ~KeyCloser() { if (key != nullptr) ::RegCloseKey(key); }
    } closer{key};

    wchar_t buffer[4096]{};
    DWORD buffer_size = sizeof(buffer);
    rc = ::RegQueryValueExW(key, nullptr, nullptr, nullptr, reinterpret_cast<LPBYTE>(buffer), &buffer_size);
    if (rc != ERROR_SUCCESS || buffer[0] == L'\0') {
        return std::string();
    }
    return utf8_from_wide(buffer);
}

std::string read_registered_inproc_path() {
    return read_registered_inproc_path_for_subkey(
        L"CLSID\\{8E14549A-DB61-4309-AFA1-3578E927E933}\\InprocServer32"
    );
}

py::dict windows_probe_payload_py(
    const std::string& camera_name,
    double timeout_seconds,
    const std::string& helper_exe,
    const std::string& dshow_dll,
    const std::string& mf_dll
) {
    (void)timeout_seconds;
    const std::string resolved_helper_exe = helper_exe.empty()
        ? akvc::windows::HelperClientRuntime::resolve_default_helper_exe()
        : normalize_path_utf8(helper_exe);
    const std::string resolved_dshow_dll = dshow_dll.empty()
        ? resolve_windows_runtime_asset("AKVC_DSHOW_DLL", L"akvc-dshow.dll", true)
        : normalize_path_utf8(dshow_dll);
    const bool mf_supported = is_windows_11_or_later_probe();
    const std::string resolved_mf_dll = mf_dll.empty()
        ? resolve_windows_runtime_asset("AKVC_MF_DLL", L"akvc-mf.dll", false)
        : normalize_path_utf8(mf_dll);
    const bool helper_present = path_exists_utf8(resolved_helper_exe);
    const bool dshow_present = path_exists_utf8(resolved_dshow_dll);
    const bool mf_present = !mf_supported || path_exists_utf8(resolved_mf_dll);
    const std::string registered_path = read_registered_inproc_path();
    const bool dshow_registered = !registered_path.empty();
    const bool registration_matches = dshow_registered && dshow_present &&
        normalize_windows_path(registered_path) == normalize_windows_path(resolved_dshow_dll);
    const std::string mf_registered_path = read_registered_inproc_path_for_subkey(
        L"CLSID\\{3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}\\InprocServer32"
    );
    const bool mf_registered = !mf_registered_path.empty();
    const bool mf_registration_matches = mf_registered && mf_present &&
        normalize_windows_path(mf_registered_path) == normalize_windows_path(resolved_mf_dll);

    akvc::windows::HelperClientRuntime helper;
    const bool helper_reachable = helper.ping();

    py::dict root;
    py::dict runtime;
    py::dict installation;
    py::dict device;
    py::dict permissions;

    runtime["helper_reachable"] = helper_reachable;
    runtime["last_error"] = !helper.last_pipe_error().empty()
        ? helper.last_pipe_error()
        : helper.last_error_message();
    runtime["helper_target_path"] = helper_present ? py::cast(resolved_helper_exe) : py::none();
    if (helper_reachable) {
        const auto status = helper.status();
        py::dict helper_status;
        helper_status["valid"] = status.valid;
        helper_status["magic"] = status.magic;
        helper_status["pid"] = status.pid;
        helper_status["heartbeat_100ns"] = status.heartbeat_100ns;
        helper_status["producer_seq"] = status.producer_seq;
        helper_status["writer_pid"] = status.writer_pid;
        runtime["helper_status"] = helper_status;
    } else {
        runtime["helper_status"] = py::none();
    }

    installation["dshow_registered"] = dshow_registered;
    installation["registered_path"] = dshow_registered ? py::cast(registered_path) : py::none();
    installation["dshow_target_path"] = dshow_present ? py::cast(resolved_dshow_dll) : py::none();
    installation["registration_matches"] = registration_matches;
    installation["mf_supported"] = mf_supported;
    installation["mf_runtime_present"] = mf_present;
    installation["mf_registered"] = mf_supported ? py::cast(mf_registered) : py::none();
    installation["mf_registered_path"] = mf_registered ? py::cast(mf_registered_path) : py::none();
    installation["mf_target_path"] = mf_present ? py::cast(resolved_mf_dll) : py::none();
    installation["mf_registration_matches"] = mf_supported ? py::cast(mf_registration_matches) : py::none();
    installation["mf_registration_managed_at_start"] = mf_supported;

    device["target_name"] = camera_name;
    device["visible"] = dshow_registered && registration_matches;
    device["visible_devices"] = py::list();
    device["all_devices"] = py::list();

    permissions["camera_access_status"] = "not_applicable";

    std::string blocker_code = "ready";
    std::string detail;
    if (!dshow_present) {
        blocker_code = "akvc_runtime_missing";
        detail = "AKVC DShow runtime is missing from the packaged application.";
    } else if (!helper_present) {
        blocker_code = "akvc_runtime_missing";
        detail = "AKVC helper runtime is missing from the packaged application.";
    } else if (!dshow_registered) {
        blocker_code = "virtual_camera_not_registered";
        detail = "AK Virtual Camera is not registered. Reinstall or run the Windows installer repair flow.";
    } else if (!registration_matches) {
        blocker_code = "diagnostic_failed";
        detail = "AK Virtual Camera is registered to a different DLL path. Reinstall or repair the Windows installation.";
    } else if (mf_supported && !mf_present) {
        blocker_code = "akvc_runtime_missing";
        detail = "AKVC Media Foundation runtime is missing from the packaged application.";
    } else if (mf_supported && !mf_registered) {
        blocker_code = "mf_virtual_camera_not_registered";
        detail = "AK Virtual Camera Media Foundation device is not registered. Start the camera or run the Windows MF repair flow.";
    } else if (mf_supported && !mf_registration_matches) {
        blocker_code = "diagnostic_failed";
        detail = "AK Virtual Camera Media Foundation source is registered to a different DLL path. Reinstall or repair the Windows installation.";
    }

    root["platform"] = "windows";
    root["ready"] = blocker_code == "ready";
    root["blocker_code"] = blocker_code;
    root["detail"] = detail;
    root["device"] = device;
    root["runtime"] = runtime;
    root["installation"] = installation;
    root["permissions"] = permissions;
    return apply_payload_flags(root, false);
}
#endif

std::string virtual_camera_probe_json_py(
    const std::string& camera_name,
    double timeout_seconds,
    const std::string& helper_exe,
    const std::string& dshow_dll,
    const std::string& mf_dll
) {
#ifdef _WIN32
    return json_dumps_py(windows_probe_payload_py(camera_name, timeout_seconds, helper_exe, dshow_dll, mf_dll));
#elif defined(__APPLE__)
    (void)helper_exe;
    (void)dshow_dll;
    (void)mf_dll;
    return json_dumps_py(macos_probe_payload_py(camera_name, timeout_seconds));
#else
    (void)camera_name;
    (void)timeout_seconds;
    (void)helper_exe;
    (void)dshow_dll;
    (void)mf_dll;
    throw std::runtime_error("virtual camera probe is only available on Windows and macOS");
#endif
}

std::string virtual_camera_prepare_json_py(
    const std::string& camera_name,
    double timeout_seconds,
    const std::string& helper_exe,
    const std::string& dshow_dll,
    const std::string& mf_dll
) {
#ifdef _WIN32
    py::dict payload = windows_probe_payload_py(camera_name, timeout_seconds, helper_exe, dshow_dll, mf_dll);
    const bool ready = py::bool_(payload["ready"]).cast<bool>();
    const std::string blocker_code = py::str(payload["blocker_code"]).cast<std::string>();
    bool action_taken = false;
    if (!ready && blocker_code == "mf_virtual_camera_not_registered") {
        akvc::windows::HelperClientRuntime helper;
        const std::string resolved_helper_exe = helper_exe.empty()
            ? akvc::windows::HelperClientRuntime::resolve_default_helper_exe()
            : normalize_path_utf8(helper_exe);
        if (helper.ensure_running(resolved_helper_exe) && helper.register_mf(camera_name)) {
            action_taken = true;
            payload = windows_probe_payload_py(camera_name, timeout_seconds, helper_exe, dshow_dll, mf_dll);
        }
    }
    return json_dumps_py(apply_payload_flags(payload, action_taken));
#elif defined(__APPLE__)
    py::dict payload = macos_probe_payload_py(camera_name, timeout_seconds);
    const std::string blocker_code = py::str(payload["blocker_code"]).cast<std::string>();
    bool action_taken = false;
    if (blocker_code == "not_installed") {
        if (macos_activate_system_extension_py(timeout_seconds)) {
            action_taken = true;
            payload = macos_probe_payload_py(camera_name, timeout_seconds);
        }
    }
    return json_dumps_py(apply_payload_flags(payload, action_taken));
#else
    (void)camera_name;
    (void)timeout_seconds;
    (void)helper_exe;
    (void)dshow_dll;
    (void)mf_dll;
    throw std::runtime_error("virtual camera prepare is only available on Windows and macOS");
#endif
}

}  // namespace

PYBIND11_MODULE(akvc_camera, m) {
    m.doc() = "AK Virtual Camera control layer (C++ binding for the desktop app)";

    py::enum_<akvc::PixelFormat>(m, "PixelFormat")
        .value("BGR24", akvc::PixelFormat::BGR24)
        .value("BGRA32", akvc::PixelFormat::BGRA32)
        .value("RGB24", akvc::PixelFormat::RGB24)
        .value("NV12", akvc::PixelFormat::NV12);

    py::enum_<akvc::Status>(m, "Status")
        .value("Ok", akvc::Status::Ok)
        .value("NotStarted", akvc::Status::NotStarted)
        .value("DeviceNotFound", akvc::Status::DeviceNotFound)
        .value("HelperUnavailable", akvc::Status::HelperUnavailable)
        .value("ShmUnavailable", akvc::Status::ShmUnavailable)
        .value("InvalidFrame", akvc::Status::InvalidFrame)
        .value("ExtensionActivationFailed", akvc::Status::ExtensionActivationFailed)
        .value("StreamStartFailed", akvc::Status::StreamStartFailed)
        .value("Unknown", akvc::Status::Unknown);

    py::class_<akvc::VirtualCamera>(m, "VirtualCamera")
        .def(py::init<int, int, double, std::string, std::string>(),
             py::arg("width"),
             py::arg("height"),
             py::arg("fps"),
             py::arg("camera_name") = std::string("AK Virtual Camera"),
             py::arg("helper_exe") = std::string())
        .def("start", &akvc::VirtualCamera::start,
             py::call_guard<py::gil_scoped_release>())
        .def("stop", &akvc::VirtualCamera::stop,
             py::call_guard<py::gil_scoped_release>())
        .def("push_frame", &push_frame_py,
             py::arg("frame"),
             py::arg("format") = py::none(),
             py::arg("pts") = 0,
             py::call_guard<py::gil_scoped_release>())
        .def_property_readonly("started", &akvc::VirtualCamera::started)
        .def_property_readonly("consumer_count", &akvc::VirtualCamera::consumer_count)
        .def_property_readonly("last_error", &akvc::VirtualCamera::last_error);

    m.def("virtual_camera_probe_json",
          &virtual_camera_probe_json_py,
          py::arg("camera_name") = std::string("AK Virtual Camera"),
          py::arg("timeout_seconds") = 5.0,
          py::arg("helper_exe") = std::string(),
          py::arg("dshow_dll") = std::string(),
          py::arg("mf_dll") = std::string());
    m.def("virtual_camera_prepare_json",
          &virtual_camera_prepare_json_py,
          py::arg("camera_name") = std::string("AK Virtual Camera"),
          py::arg("timeout_seconds") = 30.0,
          py::arg("helper_exe") = std::string(),
          py::arg("dshow_dll") = std::string(),
          py::arg("mf_dll") = std::string());
    m.def("macos_system_extension_status_json",
          &macos_system_extension_status_json_py,
          py::arg("timeout_seconds") = 5.0);
    m.def("macos_activate_system_extension",
          &macos_activate_system_extension_py,
          py::arg("timeout_seconds") = 30.0);
    m.def("macos_list_devices_json",
          &macos_list_devices_json_py);
}
