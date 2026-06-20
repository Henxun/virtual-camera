// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#ifndef AKVC_DSHOW_FILTER_H
#define AKVC_DSHOW_FILTER_H

// DirectShow BaseClasses
#include <streams.h>

#include "akvc_version.h"

// {8E14549A-DB61-4309-AFA1-3578E927E933}
// CLSID for AK Virtual Camera DirectShow Source Filter.
DEFINE_GUID(CLSID_AKVCDShowFilter,
    0x8E14549A, 0xDB61, 0x4309, 0xAF, 0xA1, 0x35, 0x78, 0xE9, 0x27, 0xE9, 0x33);

class CAKVCStream;

class CAKVCFilter : public CSource {
public:
    static CUnknown* WINAPI CreateInstance(LPUNKNOWN pUnk, HRESULT* phr);

    // IUnknown
    STDMETHODIMP NonDelegatingQueryInterface(REFIID riid, void** ppv) override;
    DECLARE_IUNKNOWN

private:
    CAKVCFilter(LPUNKNOWN pUnk, HRESULT* phr);
    ~CAKVCFilter() override;
    CAKVCStream* m_pStream = nullptr;
};

#endif  // AKVC_DSHOW_FILTER_H
