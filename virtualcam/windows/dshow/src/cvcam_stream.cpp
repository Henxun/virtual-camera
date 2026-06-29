// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#include "cvcam_stream.h"
#include "cvcam_filter.h"

#include <dvdmedia.h>
#include <ks.h>
#include <ksmedia.h>
#include <uuids.h>

#include <algorithm>
#include <cstring>

#include "akvc_protocol.h"

// 30 fps reference time = 10,000,000 / 30 = 333,333.33...
static constexpr REFERENCE_TIME kFt30 = 333333;

const AKVCMediaTypeEntry g_akvcMediaTypes[] = {
    // NV12 720p first (matches worker output — avoids resolution mismatch)
    { MEDIASUBTYPE_NV12,  AKVC_FOURCC_NV12, 12, 1280,  720, kFt30 },
    { MEDIASUBTYPE_NV12,  AKVC_FOURCC_NV12, 12, 1920, 1080, kFt30 },
    // YUY2 fallback
    { MEDIASUBTYPE_YUY2,  AKVC_FOURCC_YUY2, 16, 1280,  720, kFt30 },
    { MEDIASUBTYPE_YUY2,  AKVC_FOURCC_YUY2, 16, 1920, 1080, kFt30 },
    // RGB24 last-resort
    { MEDIASUBTYPE_RGB24, BI_RGB,           24, 1280,  720, kFt30 },
};
const int g_akvcMediaTypeCount = static_cast<int>(
    sizeof(g_akvcMediaTypes) / sizeof(g_akvcMediaTypes[0]));

// ---------------- Construction ----------------

CAKVCStream::CAKVCStream(HRESULT* phr, CAKVCFilter* pParent, LPCWSTR pPinName)
    : CSourceStream(NAME("AKVCStream"), phr, pParent, pPinName)
    , m_pParent(pParent) {
    // Default: NV12 720p30 (matches worker output)
    m_currentSubtype  = MEDIASUBTYPE_NV12;
    m_lCurrentWidth   = 1280;
    m_lCurrentHeight  = 720;
    m_rtFrameLength   = kFt30;
}

CAKVCStream::~CAKVCStream() {
    if (m_busOpen) {
        m_bus.close();
        m_busOpen = false;
    }
}

// ---------------- IUnknown ----------------

STDMETHODIMP CAKVCStream::NonDelegatingQueryInterface(REFIID riid, void** ppv) {
    if (riid == IID_IAMStreamConfig) {
        return GetInterface(static_cast<IAMStreamConfig*>(this), ppv);
    }
    if (riid == IID_IKsPropertySet) {
        return GetInterface(static_cast<IKsPropertySet*>(this), ppv);
    }
    return CSourceStream::NonDelegatingQueryInterface(riid, ppv);
}

// ---------------- Helpers ----------------

void CAKVCStream::FillMediaTypeFromEntry(CMediaType& mt,
                                         const AKVCMediaTypeEntry& e) const {
    VIDEOINFOHEADER* pvi =
        reinterpret_cast<VIDEOINFOHEADER*>(mt.AllocFormatBuffer(sizeof(VIDEOINFOHEADER)));
    if (pvi == nullptr) return;
    ZeroMemory(pvi, sizeof(VIDEOINFOHEADER));

    pvi->bmiHeader.biSize        = sizeof(BITMAPINFOHEADER);
    pvi->bmiHeader.biWidth       = e.width;
    pvi->bmiHeader.biHeight      = e.height;
    pvi->bmiHeader.biPlanes      = 1;
    pvi->bmiHeader.biBitCount    = e.biBitCount;
    pvi->bmiHeader.biCompression = e.biCompression;

    // size in bytes
    if (e.subtype == MEDIASUBTYPE_NV12) {
        pvi->bmiHeader.biSizeImage = e.width * e.height * 3 / 2;
    } else if (e.subtype == MEDIASUBTYPE_YUY2) {
        pvi->bmiHeader.biSizeImage = e.width * e.height * 2;
    } else {
        pvi->bmiHeader.biSizeImage = e.width * e.height * (e.biBitCount / 8);
    }

    pvi->AvgTimePerFrame = e.avgTimePerFrame;
    pvi->dwBitRate       = pvi->bmiHeader.biSizeImage * 8 *
                           (DWORD)(10'000'000 / e.avgTimePerFrame);

    mt.SetType(&MEDIATYPE_Video);
    mt.SetSubtype(&e.subtype);
    mt.SetFormatType(&FORMAT_VideoInfo);
    mt.SetTemporalCompression(FALSE);
    mt.SetSampleSize(pvi->bmiHeader.biSizeImage);
    mt.SetVariableSize();
    mt.SetVariableSize();  // calling twice is harmless; ensures fixed-size off
    mt.SetSampleSize(pvi->bmiHeader.biSizeImage);
}

// ---------------- CSourceStream ----------------

HRESULT CAKVCStream::GetMediaType(int iPosition, CMediaType* pmt) {
    CheckPointer(pmt, E_POINTER);
    if (iPosition < 0)                             return E_INVALIDARG;
    if (iPosition >= g_akvcMediaTypeCount)         return VFW_S_NO_MORE_ITEMS;

    FillMediaTypeFromEntry(*pmt, g_akvcMediaTypes[iPosition]);
    return S_OK;
}

HRESULT CAKVCStream::CheckMediaType(const CMediaType* pmt) {
    CheckPointer(pmt, E_POINTER);
    if (*pmt->Type() != MEDIATYPE_Video)        return E_INVALIDARG;
    if (*pmt->FormatType() != FORMAT_VideoInfo) return E_INVALIDARG;

    const VIDEOINFOHEADER* pvi =
        reinterpret_cast<const VIDEOINFOHEADER*>(pmt->Format());
    if (!pvi) return E_INVALIDARG;

    const GUID& sub = *pmt->Subtype();
    if (sub != MEDIASUBTYPE_NV12 &&
        sub != MEDIASUBTYPE_YUY2 &&
        sub != MEDIASUBTYPE_RGB24) {
        return E_INVALIDARG;
    }

    if (pvi->bmiHeader.biWidth <= 0 || pvi->bmiHeader.biHeight == 0) {
        return E_INVALIDARG;
    }

    // Accept any of our enumerated formats; sync internal state in SetMediaType.
    return S_OK;
}

HRESULT CAKVCStream::DecideBufferSize(IMemAllocator* pAlloc,
                                      ALLOCATOR_PROPERTIES* pProps) {
    CheckPointer(pAlloc, E_POINTER);
    CheckPointer(pProps, E_POINTER);

    const VIDEOINFOHEADER* pvi =
        reinterpret_cast<const VIDEOINFOHEADER*>(m_mt.Format());
    if (!pvi) return E_FAIL;

    pProps->cBuffers = std::max(2L, pProps->cBuffers);
    pProps->cbBuffer = std::max<long>(
        static_cast<long>(pvi->bmiHeader.biSizeImage), pProps->cbBuffer);

    ALLOCATOR_PROPERTIES Actual{};
    HRESULT hr = pAlloc->SetProperties(pProps, &Actual);
    if (FAILED(hr)) return hr;
    if (Actual.cbBuffer < pProps->cbBuffer) return E_FAIL;

    // Cache current state from negotiated mt.
    m_lCurrentWidth   = pvi->bmiHeader.biWidth;
    m_lCurrentHeight  = std::abs(pvi->bmiHeader.biHeight);
    m_rtFrameLength   = pvi->AvgTimePerFrame > 0 ? pvi->AvgTimePerFrame : kFt30;
    m_currentSubtype  = *m_mt.Subtype();

    return S_OK;
}

HRESULT CAKVCStream::OnThreadCreate() {
    m_rtNextStart = 0;
    m_frameCount  = 0;

    if (!m_busOpen) {
        const auto rc = m_bus.open();
        m_busOpen = (rc == AKVC_OK);
        // Not fatal if the producer isn't running yet; we'll output placeholder.
    }
    return S_OK;
}

HRESULT CAKVCStream::OnThreadDestroy() {
    if (m_busOpen) {
        m_bus.close();
        m_busOpen = false;
    }
    return S_OK;
}

HRESULT CAKVCStream::FillBuffer(IMediaSample* pSample) {
    CheckPointer(pSample, E_POINTER);

    REFERENCE_TIME rtStart = m_rtNextStart;
    REFERENCE_TIME rtEnd   = rtStart + m_rtFrameLength;

    // Try to read from frame bus; on miss, output placeholder.
    HRESULT hr = E_FAIL;
    if (m_busOpen) {
        hr = FillFromFrameBus(pSample, rtStart, rtEnd);
    } else {
        // Try to (re)open lazily.
        if (m_bus.open() == AKVC_OK) {
            m_busOpen = true;
            hr = FillFromFrameBus(pSample, rtStart, rtEnd);
        }
    }

    if (FAILED(hr)) {
        hr = FillPlaceholder(pSample, rtStart, rtEnd);
    }

    if (SUCCEEDED(hr)) {
        pSample->SetTime(&rtStart, &rtEnd);
        pSample->SetSyncPoint(TRUE);
        m_rtNextStart = rtEnd;
        ++m_frameCount;
    }
    return hr;
}

HRESULT CAKVCStream::FillFromFrameBus(IMediaSample* pSample,
                                      REFERENCE_TIME& rtStart,
                                      REFERENCE_TIME& rtEnd) {
    BYTE* pData = nullptr;
    HRESULT hr = pSample->GetPointer(&pData);
    if (FAILED(hr) || !pData) return hr;
    const long lSize = pSample->GetSize();

    akvc::FrameView view{};
    auto rc = m_bus.wait_frame(/*timeout_ms*/ 100, view);
    if (rc != AKVC_OK || !view.header) return E_FAIL;

    const auto* hdr = view.header;
    const long  expected = static_cast<long>(hdr->plane_size[0] + hdr->plane_size[1]);
    if (expected > lSize) return E_FAIL;

    // Resolution must match the negotiated media type; otherwise fall through
    // to placeholder (which renders at the negotiated size).
    if (static_cast<long>(hdr->width) != m_lCurrentWidth ||
        static_cast<long>(hdr->height) != m_lCurrentHeight) {
        return E_FAIL;
    }

    // FourCC mapping check: ensure consumer-side mt matches producer-side fourcc.
    const GUID& sub = m_currentSubtype;
    const bool match =
        (sub == MEDIASUBTYPE_NV12  && hdr->fourcc == AKVC_FOURCC_NV12) ||
        (sub == MEDIASUBTYPE_YUY2  && hdr->fourcc == AKVC_FOURCC_YUY2) ||
        (sub == MEDIASUBTYPE_RGB24 && hdr->fourcc == AKVC_FOURCC_RGB24);
    if (!match) return E_FAIL;  // graph re-negotiation handles this on stop/start

    // Copy planes contiguously (DShow buffers are flat).
    BYTE* dst = pData;
    if (view.plane0 && hdr->plane_size[0]) {
        std::memcpy(dst, view.plane0, hdr->plane_size[0]);
        dst += hdr->plane_size[0];
    }
    if (view.plane1 && hdr->plane_size[1]) {
        std::memcpy(dst, view.plane1, hdr->plane_size[1]);
        dst += hdr->plane_size[1];
    }
    pSample->SetActualDataLength(static_cast<long>(dst - pData));

    return S_OK;
}

HRESULT CAKVCStream::FillPlaceholder(IMediaSample* pSample,
                                     REFERENCE_TIME& rtStart,
                                     REFERENCE_TIME& rtEnd) {
    BYTE* pData = nullptr;
    HRESULT hr = pSample->GetPointer(&pData);
    if (FAILED(hr) || !pData) return hr;

    const VIDEOINFOHEADER* pvi =
        reinterpret_cast<const VIDEOINFOHEADER*>(m_mt.Format());
    if (!pvi) return E_FAIL;

    const long  lSize = pSample->GetSize();
    const GUID& sub   = m_currentSubtype;

    // Render an animated placeholder so the user sees the device "alive".
    const long w = m_lCurrentWidth;
    const long h = m_lCurrentHeight;

    if (sub == MEDIASUBTYPE_NV12) {
        const long ySize  = w * h;
        const long uvSize = w * h / 2;
        if (ySize + uvSize > lSize) return E_FAIL;
        // Y plane: dim ramp + moving bar
        const int bar = static_cast<int>(m_frameCount % h);
        for (long y = 0; y < h; ++y) {
            unsigned char val = (y == bar) ? 235 : 16;
            std::memset(pData + (size_t)y * w, val, w);
        }
        // UV plane: neutral
        std::memset(pData + ySize, 128, uvSize);
        pSample->SetActualDataLength(ySize + uvSize);
    } else if (sub == MEDIASUBTYPE_YUY2) {
        // YUY2: pack [Y0 U Y1 V]; black = Y=16, U=V=128
        const long bytes = w * h * 2;
        if (bytes > lSize) return E_FAIL;
        for (long y = 0; y < h; ++y) {
            for (long x = 0; x < w; x += 2) {
                BYTE* p = pData + (size_t)y * w * 2 + x * 2;
                p[0] = 16;  p[1] = 128;  p[2] = 16;  p[3] = 128;
            }
        }
        pSample->SetActualDataLength(bytes);
    } else if (sub == MEDIASUBTYPE_RGB24) {
        const long bytes = w * h * 3;
        if (bytes > lSize) return E_FAIL;
        std::memset(pData, 0, bytes);
        pSample->SetActualDataLength(bytes);
    } else {
        return E_FAIL;
    }
    (void)rtStart; (void)rtEnd;
    return S_OK;
}

// ---------------- IAMStreamConfig ----------------

STDMETHODIMP CAKVCStream::SetFormat(AM_MEDIA_TYPE* pmt) {
    CheckPointer(pmt, E_POINTER);
    CAutoLock lock(&m_cs);

    CMediaType cmt(*pmt);
    if (CheckMediaType(&cmt) != S_OK) return VFW_E_INVALIDMEDIATYPE;

    if (IsConnected()) {
        // Reconnection during running graph; require disconnect by app
        // (most apps will Stop → SetFormat → Start).
        return VFW_E_INVALIDMEDIATYPE;
    }

    SetMediaType(&cmt);

    const VIDEOINFOHEADER* pvi =
        reinterpret_cast<const VIDEOINFOHEADER*>(cmt.Format());
    if (pvi) {
        m_lCurrentWidth   = pvi->bmiHeader.biWidth;
        m_lCurrentHeight  = std::abs(pvi->bmiHeader.biHeight);
        m_rtFrameLength   = pvi->AvgTimePerFrame > 0 ? pvi->AvgTimePerFrame : kFt30;
        m_currentSubtype  = *cmt.Subtype();
    }
    return S_OK;
}

STDMETHODIMP CAKVCStream::GetFormat(AM_MEDIA_TYPE** ppmt) {
    CheckPointer(ppmt, E_POINTER);
    CAutoLock lock(&m_cs);
    *ppmt = CreateMediaType(&m_mt);
    return (*ppmt) ? S_OK : E_OUTOFMEMORY;
}

STDMETHODIMP CAKVCStream::GetNumberOfCapabilities(int* piCount, int* piSize) {
    CheckPointer(piCount, E_POINTER);
    CheckPointer(piSize,  E_POINTER);
    *piCount = g_akvcMediaTypeCount;
    *piSize  = sizeof(VIDEO_STREAM_CONFIG_CAPS);
    return S_OK;
}

STDMETHODIMP CAKVCStream::GetStreamCaps(int iIndex,
                                       AM_MEDIA_TYPE** ppmt,
                                       BYTE* pSCC) {
    CheckPointer(ppmt, E_POINTER);
    CheckPointer(pSCC, E_POINTER);
    if (iIndex < 0 || iIndex >= g_akvcMediaTypeCount) return S_FALSE;

    const auto& e = g_akvcMediaTypes[iIndex];
    CMediaType cmt;
    FillMediaTypeFromEntry(cmt, e);
    *ppmt = CreateMediaType(&cmt);
    if (!*ppmt) return E_OUTOFMEMORY;

    auto* caps = reinterpret_cast<VIDEO_STREAM_CONFIG_CAPS*>(pSCC);
    ZeroMemory(caps, sizeof(*caps));
    caps->guid = FORMAT_VideoInfo;
    caps->VideoStandard = AnalogVideo_None;
    caps->InputSize.cx  = e.width;
    caps->InputSize.cy  = e.height;
    caps->MinCroppingSize.cx = e.width;
    caps->MinCroppingSize.cy = e.height;
    caps->MaxCroppingSize.cx = e.width;
    caps->MaxCroppingSize.cy = e.height;
    caps->CropGranularityX = 1;
    caps->CropGranularityY = 1;
    caps->CropAlignX       = 1;
    caps->CropAlignY       = 1;
    caps->MinOutputSize.cx = e.width;
    caps->MinOutputSize.cy = e.height;
    caps->MaxOutputSize.cx = e.width;
    caps->MaxOutputSize.cy = e.height;
    caps->OutputGranularityX = 1;
    caps->OutputGranularityY = 1;
    caps->MinFrameInterval   = e.avgTimePerFrame;
    caps->MaxFrameInterval   = e.avgTimePerFrame;
    caps->MinBitsPerSecond   = 0;
    caps->MaxBitsPerSecond   = 0;
    return S_OK;
}

// ---------------- IKsPropertySet ----------------

STDMETHODIMP CAKVCStream::Set(REFGUID, DWORD, void*, DWORD, void*, DWORD) {
    return E_NOTIMPL;
}

STDMETHODIMP CAKVCStream::Get(REFGUID guidPropSet, DWORD dwPropID,
                              void* /*pInstanceData*/, DWORD /*cbInstanceData*/,
                              void* pPropData, DWORD cbPropData,
                              DWORD* pcbReturned) {
    if (guidPropSet != AMPROPSETID_Pin) return E_PROP_SET_UNSUPPORTED;
    if (dwPropID    != AMPROPERTY_PIN_CATEGORY) return E_PROP_ID_UNSUPPORTED;
    if (pPropData == nullptr && pcbReturned == nullptr) return E_POINTER;
    if (pcbReturned) *pcbReturned = sizeof(GUID);
    if (pPropData == nullptr) return S_OK;
    if (cbPropData < sizeof(GUID)) return E_UNEXPECTED;
    *reinterpret_cast<GUID*>(pPropData) = PIN_CATEGORY_CAPTURE;
    return S_OK;
}

STDMETHODIMP CAKVCStream::QuerySupported(REFGUID guidPropSet, DWORD dwPropID,
                                         DWORD* pTypeSupport) {
    if (guidPropSet != AMPROPSETID_Pin) return E_PROP_SET_UNSUPPORTED;
    if (dwPropID    != AMPROPERTY_PIN_CATEGORY) return E_PROP_ID_UNSUPPORTED;
    if (pTypeSupport) *pTypeSupport = KSPROPERTY_SUPPORT_GET;
    return S_OK;
}
