// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — DLL entry points & DShow factory table.

#include <initguid.h>   // must precede streams.h to emit GUID definitions
#include <streams.h>
#include <windows.h>

#include "cvcam_filter.h"

// BaseClasses provides this in dllentry.cpp but doesn't expose a header
// declaration in some snapshots; we forward-declare it here.
extern "C" BOOL WINAPI DllEntryPoint(HINSTANCE hinstDLL, DWORD dwReason, LPVOID lpReserved);

// g_hInst is defined by strmbase (dllentry.cpp) — we just reference it.
extern HINSTANCE g_hInst;

extern "C" HRESULT AKVCRegisterServer();
extern "C" HRESULT AKVCUnregisterServer();

// DShow factory table — referenced by baseclasses (strmbase) DllGet/RegisterServer.
CFactoryTemplate g_Templates[] = {
    {
        L"AK Virtual Camera",
        &CLSID_AKVCDShowFilter,
        CAKVCFilter::CreateInstance,
        nullptr,
        nullptr
    }
};
int g_cTemplates = sizeof(g_Templates) / sizeof(g_Templates[0]);

STDAPI DllRegisterServer() {
    HRESULT hr = AMovieDllRegisterServer2(TRUE);
    if (FAILED(hr)) return hr;
    return AKVCRegisterServer();
}

STDAPI DllUnregisterServer() {
    AKVCUnregisterServer();
    return AMovieDllRegisterServer2(FALSE);
}

extern "C" BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID lpv) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_hInst = hinst;
        DisableThreadLibraryCalls(hinst);
    }
    return DllEntryPoint(hinst, reason, lpv);
}
