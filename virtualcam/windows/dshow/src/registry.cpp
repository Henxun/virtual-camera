// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Registry helpers for AK Virtual Camera DirectShow filter.

#include <dshow.h>
#include <strmif.h>
#include <streams.h>
#include <uuids.h>
#include <windows.h>
#include <string>

#include "cvcam_filter.h"
#include "cvcam_stream.h"
#include "akvc_version.h"

extern HINSTANCE g_hInst;

namespace {

// Default friendly name, injected at compile time via -DAKVC_CAMERA_NAME=L"My Camera".
// Falls back to the runtime registry value HKLM\SOFTWARE\AKVC\FriendlyName (written
// by the helper), then to a hardcoded default.
#ifndef AKVC_CAMERA_NAME
#define AKVC_CAMERA_NAME_STR nullptr  // use registry / default
#else
#define AKVC_CAMERA_NAME_STR _T(AKVC_CAMERA_NAME)
#endif

LPCWSTR GetFriendlyName() {
#ifdef AKVC_CAMERA_NAME
    return AKVC_CAMERA_NAME;  // compile-time injected, always wins
#else
    static wchar_t name_buf[256] = {};
    if (name_buf[0]) return name_buf;
    HKEY hk = nullptr;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\AKVC", 0, KEY_READ, &hk) == ERROR_SUCCESS) {
        DWORD type = 0, size = sizeof(name_buf);
        if (RegQueryValueExW(hk, L"FriendlyName", nullptr, &type,
                             reinterpret_cast<LPBYTE>(name_buf), &size) == ERROR_SUCCESS
            && type == REG_SZ) {
            RegCloseKey(hk);
            return name_buf;
        }
        RegCloseKey(hk);
    }
    wcscpy_s(name_buf, L"AK Virtual Camera");
    return name_buf;
#endif
}

HRESULT WriteRegStringW(HKEY root, LPCWSTR sub, LPCWSTR name, LPCWSTR value) {
    HKEY h{};
    LONG rc = RegCreateKeyExW(root, sub, 0, nullptr, 0, KEY_WRITE, nullptr, &h, nullptr);
    if (rc != ERROR_SUCCESS) return HRESULT_FROM_WIN32(rc);
    rc = RegSetValueExW(h, name, 0, REG_SZ,
                        reinterpret_cast<const BYTE*>(value),
                        static_cast<DWORD>((wcslen(value) + 1) * sizeof(wchar_t)));
    RegCloseKey(h);
    return HRESULT_FROM_WIN32(rc);
}

HRESULT GetSelfPath(std::wstring& out) {
    wchar_t buf[MAX_PATH] = {};
    DWORD n = ::GetModuleFileNameW(g_hInst, buf, MAX_PATH);
    if (n == 0 || n == MAX_PATH) return HRESULT_FROM_WIN32(::GetLastError());
    out.assign(buf, n);
    return S_OK;
}

}  // namespace

extern "C" HRESULT AKVCRegisterServer() {
    // 1. CLSID InprocServer32 (always register the COM class so the filter
    //    can be instantiated programmatically / via the MF↔DShow bridge).
    {
        std::wstring sub = L"CLSID\\";
        sub += AKVC_DSHOW_FILTER_CLSID_GUID_STR;

        HRESULT hr = WriteRegStringW(HKEY_CLASSES_ROOT, sub.c_str(), nullptr,
                                     GetFriendlyName());
        if (FAILED(hr)) return hr;

        std::wstring inproc = sub + L"\\InprocServer32";
        std::wstring dllPath;
        hr = GetSelfPath(dllPath);
        if (FAILED(hr)) return hr;

        hr = WriteRegStringW(HKEY_CLASSES_ROOT, inproc.c_str(), nullptr, dllPath.c_str());
        if (FAILED(hr)) return hr;
        hr = WriteRegStringW(HKEY_CLASSES_ROOT, inproc.c_str(),
                             L"ThreadingModel", L"Both");
        if (FAILED(hr)) return hr;
    }

    // 2. Register filter in Video Capture category.
    //
    //    This is needed for DirectShow-only consumers (older OBS, Zoom,
    //    GraphStudioNext) that do not enumerate MF VirtualCameras. The MF
    //    VirtualCamera (akvc-mf.dll) covers Chrome/Edge/Teams/Windows Camera.
    //    Two PnP device nodes will exist, but both carry the friendly name
    //    "AK Virtual Camera" so the user experience is consistent.
    IFilterMapper2* pMapper = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_FilterMapper2, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_PPV_ARGS(&pMapper));
    if (FAILED(hr)) return hr;

    REGPINTYPES types[3] = {
        { &MEDIATYPE_Video, &MEDIASUBTYPE_NV12  },
        { &MEDIATYPE_Video, &MEDIASUBTYPE_YUY2  },
        { &MEDIATYPE_Video, &MEDIASUBTYPE_RGB24 },
    };

    REGFILTERPINS pin1{};
    pin1.strName        = const_cast<LPWSTR>(L"Output");
    pin1.bRendered      = FALSE;
    pin1.bOutput        = TRUE;
    pin1.bZero          = FALSE;
    pin1.bMany          = FALSE;
    pin1.clsConnectsToFilter = nullptr;
    pin1.strConnectsToPin    = nullptr;
    pin1.nMediaTypes    = 3;
    pin1.lpMediaType    = types;

    REGFILTER2 rf2{};
    rf2.dwVersion = 1;
    rf2.cPins = 1;
    rf2.rgPins = &pin1;

    hr = pMapper->RegisterFilter(
        CLSID_AKVCDShowFilter,
        GetFriendlyName(),
        nullptr,
        &CLSID_VideoInputDeviceCategory,
        GetFriendlyName(),
        &rf2);

    pMapper->Release();
    return hr;
}

extern "C" HRESULT AKVCUnregisterServer() {
    // Remove from category
    IFilterMapper2* pMapper = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_FilterMapper2, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_PPV_ARGS(&pMapper));
    if (SUCCEEDED(hr) && pMapper) {
        pMapper->UnregisterFilter(&CLSID_VideoInputDeviceCategory,
                                  GetFriendlyName(),
                                  CLSID_AKVCDShowFilter);
        pMapper->Release();
    }

    // Remove CLSID subtree.
    std::wstring sub = L"CLSID\\";
    sub += AKVC_DSHOW_FILTER_CLSID_GUID_STR;
    std::wstring inproc = sub + L"\\InprocServer32";
    RegDeleteKeyW(HKEY_CLASSES_ROOT, inproc.c_str());
    RegDeleteKeyW(HKEY_CLASSES_ROOT, sub.c_str());
    return S_OK;
}
