// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors

#ifndef AKVC_DSHOW_STREAM_H
#define AKVC_DSHOW_STREAM_H

#include <streams.h>
#include <strmif.h>
#include <ks.h>
#include <ksmedia.h>
#include <vector>

#include "akvc/framebus.h"

class CAKVCFilter;

// Supported media-type entries (FourCC + dimensions + fps).
struct AKVCMediaTypeEntry {
    GUID         subtype;
    DWORD        biCompression;
    WORD         biBitCount;
    LONG         width;
    LONG         height;
    REFERENCE_TIME avgTimePerFrame;   // 100ns
};

class CAKVCStream final
    : public CSourceStream
    , public IAMStreamConfig
    , public IKsPropertySet {
public:
    CAKVCStream(HRESULT* phr, CAKVCFilter* pParent, LPCWSTR pPinName);
    ~CAKVCStream() override;

    // CSourceStream
    HRESULT GetMediaType(int iPosition, CMediaType* pmt) override;
    HRESULT CheckMediaType(const CMediaType* pmt) override;
    HRESULT DecideBufferSize(IMemAllocator* pAlloc, ALLOCATOR_PROPERTIES* pProps) override;
    HRESULT FillBuffer(IMediaSample* pSample) override;
    HRESULT OnThreadCreate() override;
    HRESULT OnThreadDestroy() override;

    // IUnknown
    DECLARE_IUNKNOWN
    STDMETHODIMP NonDelegatingQueryInterface(REFIID riid, void** ppv) override;

    // IAMStreamConfig
    STDMETHODIMP SetFormat(AM_MEDIA_TYPE* pmt) override;
    STDMETHODIMP GetFormat(AM_MEDIA_TYPE** ppmt) override;
    STDMETHODIMP GetNumberOfCapabilities(int* piCount, int* piSize) override;
    STDMETHODIMP GetStreamCaps(int iIndex,
                               AM_MEDIA_TYPE** ppmt,
                               BYTE* pSCC) override;

    // IKsPropertySet (basic — Pin Category = Capture)
    STDMETHODIMP Set(REFGUID guidPropSet, DWORD dwID,
                     void* pInstanceData, DWORD cbInstanceData,
                     void* pPropData, DWORD cbPropData) override;
    STDMETHODIMP Get(REFGUID guidPropSet, DWORD dwPropID,
                     void* pInstanceData, DWORD cbInstanceData,
                     void* pPropData, DWORD cbPropData,
                     DWORD* pcbReturned) override;
    STDMETHODIMP QuerySupported(REFGUID guidPropSet, DWORD dwPropID,
                                DWORD* pTypeSupport) override;

private:
    HRESULT FillFromFrameBus(IMediaSample* pSample);
    HRESULT FillPlaceholder(IMediaSample* pSample,
                            REFERENCE_TIME& rtStart,
                            REFERENCE_TIME& rtEnd);
    void    FillMediaTypeFromEntry(CMediaType& mt,
                                   const AKVCMediaTypeEntry& e) const;

    CAKVCFilter* m_pParent = nullptr;

    // Negotiated current format
    int                 m_iCurrentEntry = 0;
    LONG                m_lCurrentWidth = 1920;
    LONG                m_lCurrentHeight = 1080;
    REFERENCE_TIME      m_rtFrameLength = 333333;  // 30fps default
    GUID                m_currentSubtype{ MEDIASUBTYPE_NV12 };

    // Frame counter for placeholder generation
    REFERENCE_TIME      m_rtNextStart = 0;
    int64_t             m_frameCount  = 0;

    // FrameBus
    akvc::FrameBusConsumer m_bus;
    bool                m_busOpen = false;

    // Critical section for IAMStreamConfig access
    CCritSec            m_cs;
};

extern const AKVCMediaTypeEntry g_akvcMediaTypes[];
extern const int                g_akvcMediaTypeCount;

#endif  // AKVC_DSHOW_STREAM_H
