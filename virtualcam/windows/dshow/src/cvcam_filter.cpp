// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "cvcam_filter.h"
#include "cvcam_stream.h"

CUnknown* WINAPI CAKVCFilter::CreateInstance(LPUNKNOWN pUnk, HRESULT* phr) {
    auto* p = new CAKVCFilter(pUnk, phr);
    if (p == nullptr && phr) {
        *phr = E_OUTOFMEMORY;
    }
    return p;
}

CAKVCFilter::CAKVCFilter(LPUNKNOWN pUnk, HRESULT* phr)
    : CSource(NAME("AK Virtual Camera"), pUnk, CLSID_AKVCDShowFilter) {
    m_pStream = new CAKVCStream(phr, this, L"Output");
    // CSource takes ownership of the pin via AddPin in CSourceStream ctor.
}

CAKVCFilter::~CAKVCFilter() = default;

STDMETHODIMP CAKVCFilter::NonDelegatingQueryInterface(REFIID riid, void** ppv) {
    return CSource::NonDelegatingQueryInterface(riid, ppv);
}
