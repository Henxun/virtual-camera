// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — MF Virtual Camera Media Source implementation.

#include "akvc/mf_source.h"

#include <assert.h>
#include <chrono>
#include <cstdarg>
#include <cwchar>
#include <cstdio>
#include <string>
#include <thread>

namespace akvc::mf {

// ── Helpers ──

namespace {

// Debug logging: writes to both OutputDebugString (visible in DebugView)
// and a log file for diagnosis inside frameserver.exe.
}  // namespace

void Log(const char* fmt, ...) {
    char buf[1024];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    ::OutputDebugStringA("[akvc-mf] ");
    ::OutputDebugStringA(buf);
    ::OutputDebugStringA("\n");

    // Also append to a log file next to the DLL.
    static HMODULE g_mod = [] {
        HMODULE m = nullptr;
        ::GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                             GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                             reinterpret_cast<LPCWSTR>(&Log), &m);
        return m;
    }();
    wchar_t path[MAX_PATH];
    if (g_mod && ::GetModuleFileNameW(g_mod, path, MAX_PATH)) {
        wchar_t* sep = wcsrchr(path, L'\\');
        if (sep) wcscpy_s(sep + 1, MAX_PATH - (sep - path) - 1, L"akvc-mf.log");
        FILE* f = nullptr;
        if (_wfopen_s(&f, path, L"a") == 0 && f) {
            SYSTEMTIME st;
            ::GetLocalTime(&st);
            fprintf(f, "[%02d:%02d:%02d.%03d][%lu] %s\n",
                    st.wHour, st.wMinute, st.wSecond, st.wMilliseconds,
                    ::GetCurrentProcessId(), buf);
            fclose(f);
        }
    }
}

std::wstring GuidToString(REFGUID g) {
    wchar_t buf[64];
    StringFromGUID2(g, buf, 64);
    return buf;
}


// Module-level globals
LONG g_lock_count = 0;
LONG g_object_count = 0;

// {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}
const CLSID CLSID_AKVCMFSource = {
    0x3c2d3a1a, 0x8e5f, 0x4b8f, {0x9c, 0x1a, 0x2d, 0x7e, 0x5f, 0x1a, 0x3b, 0x4c}
};

const MediaTypeDesc kMediaTypes[] = {
    {1920, 1080, 30, 1, MFVideoFormat_NV12},
    {1280,  720, 30, 1, MFVideoFormat_NV12},
    {1920, 1080, 30, 1, MFVideoFormat_YUY2},
    {1280,  720, 30, 1, MFVideoFormat_YUY2},
};
const UINT32 kMediaTypeCount = sizeof(kMediaTypes) / sizeof(kMediaTypes[0]);

// ── Helpers ──

namespace {

HRESULT HrFromAkvc(akvc_status_t st) {
    switch (st) {
        case AKVC_OK:                     return S_OK;
        case E_AKVC_FRAMEBUS_OPEN_FAILED: return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
        case E_AKVC_FRAMEBUS_TIMEOUT:     return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
        case E_AKVC_FRAMEBUS_TORN_FRAME:  return E_FAIL;
        default:                           return E_FAIL;
    }
}

HRESULT MakeMediaType(const MediaTypeDesc& desc, IMFMediaType** out) {
    *out = nullptr;
    IMFMediaType* mt = nullptr;
    HRESULT hr;

    hr = MFCreateMediaType(&mt);
    if (FAILED(hr)) return hr;

    hr = mt->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
    if (FAILED(hr)) { mt->Release(); return hr; }

    hr = mt->SetGUID(MF_MT_SUBTYPE, desc.subtype);
    if (FAILED(hr)) { mt->Release(); return hr; }

    hr = MFSetAttributeSize(mt, MF_MT_FRAME_SIZE, desc.width, desc.height);
    if (FAILED(hr)) { mt->Release(); return hr; }

    hr = MFSetAttributeRatio(mt, MF_MT_FRAME_RATE, desc.fps_num, desc.fps_den);
    if (FAILED(hr)) { mt->Release(); return hr; }

    hr = MFSetAttributeRatio(mt, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
    if (FAILED(hr)) { mt->Release(); return hr; }

    hr = mt->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
    if (FAILED(hr)) { mt->Release(); return hr; }

    hr = mt->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE);
    if (FAILED(hr)) { mt->Release(); return hr; }

    // Default stride for NV12/YUY2 = width in bytes (no padding). Without
    // this, the frame server may assume a misaligned stride and render garbled.
    hr = mt->SetUINT32(MF_MT_DEFAULT_STRIDE, desc.width);
    if (FAILED(hr)) { mt->Release(); return hr; }

    *out = mt;
    return S_OK;
}

}  // namespace

// ══════════════════════════════════════════════════════════════════════════
//  MediaStream
// ══════════════════════════════════════════════════════════════════════════

MediaStream::MediaStream(MediaSource* source, DWORD stream_id, IMFMediaType* media_type)
    : source_(source), stream_id_(stream_id), media_type_(media_type) {
    media_type_->AddRef();
    InterlockedIncrement(&g_object_count);
    MFCreateEventQueue(&event_queue_);

    IMFMediaType* types[] = { media_type_ };
    MFCreateStreamDescriptor(stream_id_, 1, types, &descriptor_);
    if (descriptor_) {
        descriptor_->SetString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME,
                               L"AK Virtual Camera Stream");
        // Set the current media type on the descriptor's type handler —
        // without this the frame server cannot negotiate a format.
        IMFMediaTypeHandler* handler = nullptr;
        if (SUCCEEDED(descriptor_->GetMediaTypeHandler(&handler)) && handler) {
            handler->SetCurrentMediaType(media_type_);
            handler->Release();
        }
    }
}

MediaStream::~MediaStream() {
    Shutdown();
    InterlockedDecrement(&g_object_count);
}

STDMETHODIMP MediaStream::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator) {
        *ppv = static_cast<IMFMediaEventGenerator*>(this);
    } else if (riid == IID_IMFMediaStream) {
        *ppv = static_cast<IMFMediaStream*>(this);
    } else {
        return E_NOINTERFACE;
    }
    AddRef();
    return S_OK;
}

STDMETHODIMP MediaStream::BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) {
    Log("MediaStream::BeginGetEvent");
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->BeginGetEvent(callback, state);
}

STDMETHODIMP MediaStream::EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) {
    Log("MediaStream::EndGetEvent");
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->EndGetEvent(result, event);
}

STDMETHODIMP MediaStream::GetEvent(DWORD flags, IMFMediaEvent** event) {
    Log("MediaStream::GetEvent flags=0x%lx", flags);
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->GetEvent(flags, event);
}

STDMETHODIMP MediaStream::QueueEvent(MediaEventType type, REFGUID ext, HRESULT status,
                                      const PROPVARIANT* value) {
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->QueueEventParamVar(type, ext, status, value);
}

STDMETHODIMP MediaStream::GetMediaSource(IMFMediaSource** out) {
    if (!out) return E_POINTER;
    *out = source_;
    source_->AddRef();
    return S_OK;
}

STDMETHODIMP MediaStream::GetStreamDescriptor(IMFStreamDescriptor** out) {
    if (!out) return E_POINTER;
    *out = descriptor_;
    descriptor_->AddRef();
    return S_OK;
}

void MediaStream::SetAllocator(IUnknown* allocator) {
    Log("MediaStream::SetAllocator");
    if (allocator_) { allocator_->Release(); allocator_ = nullptr; }
    if (allocator) {
        IMFVideoSampleAllocator* va = nullptr;
        HRESULT qhr = allocator->QueryInterface(__uuidof(IMFVideoSampleAllocator),
                                                 reinterpret_cast<void**>(&va));
        if (SUCCEEDED(qhr) && va) {
            HRESULT ihr = va->InitializeSampleAllocator(10, media_type_);
            Log("MediaStream::SetAllocator QI OK, InitializeSampleAllocator hr=0x%08lx", ihr);
            if (SUCCEEDED(ihr)) {
                allocator_ = va;
            } else {
                va->Release();
            }
        } else {
            Log("MediaStream::SetAllocator QI IMFVideoSampleAllocator FAILED hr=0x%08lx (will use fallback)", qhr);
        }
    }
}

STDMETHODIMP MediaStream::RequestSample(IUnknown* token) {
    Log("MediaStream::RequestSample CALLED token=%p", (void*)token);
    if (shutdown_) return MF_E_SHUTDOWN;

    // Pull one frame from the Frame Bus and deliver it synchronously.
    akvc::FrameView fv{};
    akvc_status_t st = source_->WaitFrame(fv);
    if (st != AKVC_OK || !fv.header) {
        Log("MediaStream::RequestSample WaitFrame failed: %d", st);
        return S_OK;  // return OK; just don't deliver a sample this time
    }

    IMFSample* sample = nullptr;
    if (!BuildSample(fv, &sample)) {
        return S_OK;
    }
    // Use MFGetSystemTime() for the sample time — the frame server expects
    // MF system time (not the worker's perf_counter-based pts).
    sample->SetSampleTime(MFGetSystemTime());
    sample->SetSampleDuration(333333);

    // Attach the request token so the frame server can match request→sample.
    if (token) {
        sample->SetUnknown(MFSampleExtension_Token, token);
    }

    HRESULT qhr = event_queue_->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, sample);
    Log("MediaStream::RequestSample delivered QueueEventParamUnk hr=0x%08lx", qhr);
    sample->Release();
    return S_OK;
}

bool MediaStream::BuildSample(const FrameView& fv, IMFSample** out) {
    *out = nullptr;
    DWORD buf_size = fv.header->plane_size[0] + fv.header->plane_size[1];
    UINT32 h = fv.header->height;
    UINT32 w = fv.header->width;

    // Prefer the frame-server-provided allocator (creates a 2D NV12 buffer
    // with the correct stride that the frame server can render directly).
    if (allocator_) {
        Log("MediaStream::BuildSample using allocator");
        IMFSample* sample = nullptr;
        if (SUCCEEDED(allocator_->AllocateSample(&sample)) && sample) {
            IMFMediaBuffer* buf = nullptr;
            if (SUCCEEDED(sample->GetBufferByIndex(0, &buf)) && buf) {
                IMF2DBuffer2* buf2d = nullptr;
                if (SUCCEEDED(buf->QueryInterface(&buf2d)) && buf2d) {
                    BYTE* scanline0 = nullptr;
                    LONG pitch = 0;
                    BYTE* data = nullptr;
                    DWORD len = 0;
                    if (SUCCEEDED(buf2d->Lock2DSize(MF2DBuffer_LockFlags_Write,
                                                     &scanline0, &pitch, &data, &len))) {
                        Log("MediaStream::BuildSample 2D pitch=%ld len=%lu w=%u h=%u psize0=%u psize1=%u",
                            pitch, len, w, h, fv.header->plane_size[0], fv.header->plane_size[1]);
                        if (pitch >= (LONG)w) {
                            // Y plane (row by row, respecting pitch).
                            if (fv.plane0) {
                                for (UINT32 y = 0; y < h; ++y)
                                    std::memcpy(scanline0 + y * pitch,
                                                fv.plane0 + y * w, w);
                            }
                            // UV plane (interleaved, half height).
                            if (fv.plane1) {
                                BYTE* uv = scanline0 + (LONG)(pitch * h);
                                for (UINT32 y = 0; y < h / 2; ++y)
                                    std::memcpy(uv + y * pitch,
                                                fv.plane1 + y * w, w);
                            }
                        } else {
                            Log("MediaStream::BuildSample pitch < width, skipping copy");
                        }
                        buf2d->Unlock2D();
                    } else {
                        Log("MediaStream::BuildSample Lock2DSize FAILED");
                    }
                    buf2d->Release();
                } else {
                    Log("MediaStream::BuildSample QI IMF2DBuffer2 FAILED");
                }
                buf->Release();
            }
            *out = sample;
            Log("MediaStream::BuildSample allocator sample built OK");
            return true;
        }
    }

    // Fallback: plain 1D memory buffer (contiguous Y || UV).
    IMFSample* sample = nullptr;
    if (FAILED(MFCreateSample(&sample))) return false;
    IMFMediaBuffer* buffer = nullptr;
    if (FAILED(MFCreateMemoryBuffer(buf_size, &buffer))) {
        sample->Release();
        return false;
    }
    BYTE* data = nullptr;
    if (FAILED(buffer->Lock(&data, nullptr, nullptr))) {
        buffer->Release();
        sample->Release();
        return false;
    }
    if (fv.plane0 && fv.header->plane_size[0] > 0)
        std::memcpy(data, fv.plane0, fv.header->plane_size[0]);
    if (fv.plane1 && fv.header->plane_size[1] > 0)
        std::memcpy(data + fv.header->plane_size[0], fv.plane1, fv.header->plane_size[1]);
    buffer->Unlock();
    buffer->SetCurrentLength(buf_size);
    sample->AddBuffer(buffer);
    buffer->Release();
    *out = sample;
    return true;
}

void MediaStream::Shutdown() {
    shutdown_ = true;
    if (event_queue_) {
        event_queue_->Shutdown();
        event_queue_->Release();
        event_queue_ = nullptr;
    }
    if (media_type_) { media_type_->Release(); media_type_ = nullptr; }
    if (descriptor_) { descriptor_->Release(); descriptor_ = nullptr; }
}

void MediaStream::DeliverSample(IMFSample* sample) {
    if (shutdown_ || !event_queue_) return;
    // Queue the sample event. Use QueueEventParamUnk (the canonical way to
    // deliver an IMFSample via MEMediaSample), matching the MS VirtualCamera
    // sample.
    event_queue_->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, sample);
}

// ══════════════════════════════════════════════════════════════════════════
//  MediaSource
// ══════════════════════════════════════════════════════════════════════════

MediaSource::MediaSource() {
    InterlockedIncrement(&g_object_count);
    MFCreateEventQueue(&event_queue_);

    // Eagerly create the stream + presentation descriptor (matches the MS
    // VirtualCamera sample's Initialize flow). The frame server probes the
    // source via CreatePresentationDescriptor during device enumeration,
    // before Start() — so the stream must exist and be wired into the PD.
    // Use 720p (index 1) to match the worker's actual output resolution.
    IMFMediaType* mt = nullptr;
    if (SUCCEEDED(MakeMediaType(kMediaTypes[1], &mt)) && mt) {
        stream_ = new MediaStream(this, kStreamIdVideo, mt);
        mt->Release();

        if (stream_) {
            IMFStreamDescriptor* sd = nullptr;
            if (SUCCEEDED(stream_->GetStreamDescriptor(&sd)) && sd) {
                IMFStreamDescriptor* sds[] = { sd };
                MFCreatePresentationDescriptor(1, sds, &presentation_desc_);
                if (presentation_desc_) {
                    presentation_desc_->SelectStream(kStreamIdVideo);
                }
                sd->Release();
            }
        }
    }
    Log("MediaSource::ctor pd=%p stream=%p", (void*)presentation_desc_, (void*)stream_);
}

MediaSource::~MediaSource() {
    Shutdown();
    InterlockedDecrement(&g_object_count);
}

STDMETHODIMP MediaSource::QueryInterface(REFIID riid, void** ppv) {
    std::wstring iid = GuidToString(riid);
    Log("MediaSource::QueryInterface iid=%ls", iid.c_str());
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator) {
        *ppv = static_cast<IMFMediaEventGenerator*>(this);
    } else if (riid == IID_IMFMediaSource) {
        *ppv = static_cast<IMFMediaSource*>(this);
    } else if (riid == IID_IMFMediaSourceEx) {
        *ppv = static_cast<IMFMediaSourceEx*>(this);
    } else if (riid == IID_IMFGetService) {
        // MS sample implements IMFGetService; returns MF_E_UNSUPPORTED_SERVICE.
        *ppv = static_cast<IMFGetService*>(this);
    } else if (riid == __uuidof(IKsControl)) {
        // Frame server probes camera capabilities via IKsControl.
        *ppv = static_cast<IKsControl*>(this);
    } else if (riid == __uuidof(IMFSampleAllocatorControl)) {
        // Frame server sets its sample allocator via this interface.
        *ppv = static_cast<IMFSampleAllocatorControl*>(this);
    } else {
        Log("MediaSource::QueryInterface E_NOINTERFACE for %ls", iid.c_str());
        return E_NOINTERFACE;
    }
    AddRef();
    return S_OK;
}

STDMETHODIMP MediaSource::BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) {
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->BeginGetEvent(callback, state);
}

STDMETHODIMP MediaSource::EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) {
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->EndGetEvent(result, event);
}

STDMETHODIMP MediaSource::GetEvent(DWORD flags, IMFMediaEvent** event) {
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->GetEvent(flags, event);
}

STDMETHODIMP MediaSource::QueueEvent(MediaEventType type, REFGUID ext, HRESULT status,
                                      const PROPVARIANT* value) {
    if (!event_queue_) return MF_E_SHUTDOWN;
    return event_queue_->QueueEventParamVar(type, ext, status, value);
}

STDMETHODIMP MediaSource::CreatePresentationDescriptor(IMFPresentationDescriptor** out) {
    Log("MediaSource::CreatePresentationDescriptor");
    if (!out) return E_POINTER;
    if (shutdown_) return MF_E_SHUTDOWN;
    if (!presentation_desc_) return MF_E_NOT_INITIALIZED;
    *out = presentation_desc_;
    (*out)->AddRef();
    return S_OK;
}

STDMETHODIMP MediaSource::GetCharacteristics(DWORD* characteristics) {
    Log("MediaSource::GetCharacteristics");
    if (!characteristics) return E_POINTER;
    *characteristics = MFMEDIASOURCE_CAN_PAUSE;
    return S_OK;
}

STDMETHODIMP MediaSource::Pause() {
    if (shutdown_) return MF_E_SHUTDOWN;
    paused_ = true;
    return S_OK;
}

STDMETHODIMP MediaSource::Shutdown() {
    if (shutdown_) return S_OK;
    shutdown_ = true;

    if (reader_thread_.joinable()) reader_thread_.join();

    if (stream_) { stream_->Shutdown(); stream_->Release(); stream_ = nullptr; }
    if (presentation_desc_) { presentation_desc_->Release(); presentation_desc_ = nullptr; }
    if (source_attributes_) { source_attributes_->Release(); source_attributes_ = nullptr; }
    if (event_queue_) { event_queue_->Shutdown(); event_queue_->Release(); event_queue_ = nullptr; }
    fb_consumer_.close();
    return S_OK;
}

// IMFMediaSourceEx
// Per the MS VirtualCamera sample: return the source's persistent attribute
// store, which must include a sensor profile collection (mandatory for
// VideoCapture sources).
STDMETHODIMP MediaSource::GetSourceAttributes(IMFAttributes** ppAttributes) {
    Log("MediaSource::GetSourceAttributes");
    if (!ppAttributes) return E_POINTER;
    *ppAttributes = nullptr;

    if (source_attributes_ == nullptr) {
        HRESULT hr = MFCreateAttributes(&source_attributes_, 4);
        if (FAILED(hr)) return hr;

        // Build a sensor profile collection with a Legacy profile (mandatory).
        // Without this, Start() returns MF_E_ATTRIBUTENOTFOUND.
        IMFSensorProfileCollection* profiles = nullptr;
        if (SUCCEEDED(MFCreateSensorProfileCollection(&profiles)) && profiles) {
            IMFSensorProfile* profile = nullptr;
            // Legacy profile — mandatory for non-profile-aware apps.
            if (SUCCEEDED(MFCreateSensorProfile(KSCAMERAPROFILE_Legacy, 0, nullptr, &profile)) && profile) {
                profile->AddProfileFilter(kStreamIdVideo, L"((RES==;FRT<=30,1;SUT==))");
                profiles->AddProfile(profile);
                profile->Release();
            }
            source_attributes_->SetUnknown(MF_DEVICEMFT_SENSORPROFILE_COLLECTION, profiles);
            profiles->Release();
        }
    }

    source_attributes_->AddRef();
    *ppAttributes = source_attributes_;
    return S_OK;
}

STDMETHODIMP MediaSource::GetStreamAttributes(DWORD streamId, IMFAttributes** ppAttributes) {
    Log("MediaSource::GetStreamAttributes streamId=%lu", streamId);
    if (!ppAttributes) return E_POINTER;
    *ppAttributes = nullptr;
    if (streamId != kStreamIdVideo) return MF_E_INVALIDSTREAMNUMBER;

    // Build per-stream attributes matching the MS sample.
    IMFAttributes* attrs = nullptr;
    HRESULT hr = MFCreateAttributes(&attrs, 5);
    if (FAILED(hr)) return hr;
    attrs->SetGUID(MF_DEVICESTREAM_STREAM_CATEGORY, PINNAME_VIDEO_CAPTURE);
    attrs->SetUINT32(MF_DEVICESTREAM_STREAM_ID, streamId);
    attrs->SetUINT32(MF_DEVICESTREAM_FRAMESERVER_SHARED, 1);
    attrs->SetUINT32(MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES,
                     MFFrameSourceTypes_Color);
    *ppAttributes = attrs;
    return S_OK;
}

STDMETHODIMP MediaSource::SetD3DManager(IUnknown*) {
    return E_NOTIMPL;
}

// IMFGetService
STDMETHODIMP MediaSource::GetService(REFGUID, REFIID, LPVOID* ppvObject) {
    if (ppvObject) *ppvObject = nullptr;
    return MF_E_UNSUPPORTED_SERVICE;
}

// IKsControl — the frame server probes camera controls (exposure, focus,
// white balance, etc.) via KS properties. We support none of them, so we
// return ERROR_SET_NOT_FOUND, which is the AVStream-driver convention for
// "no handler registered". This lets the frame server proceed gracefully.
STDMETHODIMP MediaSource::KsProperty(PKSPROPERTY pProperty, ULONG ulPropertyLength,
                                      LPVOID pPropertyData, ULONG ulDataLength,
                                      ULONG* pBytesReturned) {
    Log("MediaSource::KsProperty set=%ls id=%lu flags=0x%lx",
        GuidToString(pProperty->Set).c_str(), pProperty->Id, pProperty->Flags);
    if (ulPropertyLength < sizeof(KSPROPERTY)) return E_INVALIDARG;
    if (pBytesReturned) *pBytesReturned = 0;
    return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

STDMETHODIMP MediaSource::KsMethod(PKSMETHOD, ULONG, LPVOID, ULONG, ULONG* pBytesReturned) {
    if (pBytesReturned) *pBytesReturned = 0;
    return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

STDMETHODIMP MediaSource::KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG* pBytesReturned) {
    if (pBytesReturned) *pBytesReturned = 0;
    return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

// IMFSampleAllocatorControl
STDMETHODIMP MediaSource::GetAllocatorUsage(DWORD dwOutputStreamID, DWORD* pdwInputStreamID,
                                            MFSampleAllocatorUsage* peUsage) {
    Log("MediaSource::GetAllocatorUsage");
    if (!pdwInputStreamID || !peUsage) return E_POINTER;
    *pdwInputStreamID = dwOutputStreamID;
    *peUsage = MFSampleAllocatorUsage_UsesProvidedAllocator;
    return S_OK;
}

STDMETHODIMP MediaSource::SetDefaultAllocator(DWORD dwOutputStreamID, IUnknown* pAllocator) {
    Log("MediaSource::SetDefaultAllocator streamID=%lu alloc=%p", dwOutputStreamID, (void*)pAllocator);
    if (!pAllocator) return E_POINTER;
    if (stream_) {
        stream_->SetAllocator(pAllocator);
    }
    return S_OK;
}

STDMETHODIMP MediaSource::Start(IMFPresentationDescriptor* desc,
                                 const GUID*, const PROPVARIANT*) {
    Log("MediaSource::Start CALLED");
    if (shutdown_) return MF_E_SHUTDOWN;

    // Open Frame Bus (created by Helper process).
    akvc_status_t st = fb_consumer_.open();
    if (st != AKVC_OK) {
        Log("MediaSource::Start FrameBusConsumer::open failed: %d", st);
        QueueEvent(MEError, GUID_NULL, HrFromAkvc(st), nullptr);
        return HrFromAkvc(st);
    }
    Log("MediaSource::Start FrameBus opened OK");

    (void)desc;
    if (!stream_ || !presentation_desc_) {
        QueueEvent(MEError, GUID_NULL, MF_E_NOT_INITIALIZED, nullptr);
        return MF_E_NOT_INITIALIZED;
    }

    started_ = true;
    paused_ = false;

    // Per the MS VirtualCamera sample: the source must announce the stream to
    // the frame server via MENewStream (carrying the IMFMediaStream), then
    // MEStreamStarted, then MESourceStarted. Without MENewStream the frame
    // server never calls RequestSample and Chrome times out.
    IUnknown* streamUnk = nullptr;
    if (SUCCEEDED(stream_->QueryInterface(IID_PPV_ARGS(&streamUnk))) && streamUnk) {
        event_queue_->QueueEventParamUnk(MENewStream, GUID_NULL, S_OK, streamUnk);
        streamUnk->Release();
    }
    stream_->QueueEvent(MEStreamStarted, GUID_NULL, S_OK, nullptr);
    QueueEvent(MESourceStarted, GUID_NULL, S_OK, nullptr);

    Log("MediaSource::Start completed, events queued");
    return S_OK;
}

STDMETHODIMP MediaSource::Stop() {
    if (shutdown_) return MF_E_SHUTDOWN;
    started_ = false;
    paused_ = false;
    if (reader_thread_.joinable()) reader_thread_.join();
    QueueEvent(MESourceStopped, GUID_NULL, S_OK, nullptr);
    return S_OK;
}

HRESULT MediaSource::CreateStreamFromPresentation(IMFPresentationDescriptor* desc) {
    // Create the presentation descriptor for our media types.
    IMFStreamDescriptor* sd = nullptr;
    IMFMediaType* mt = nullptr;

    HRESULT hr = MakeMediaType(kMediaTypes[0], &mt);
    if (FAILED(hr)) return hr;

    // Create the stream.
    stream_ = new MediaStream(this, kStreamIdVideo, mt);
    mt->Release();

    if (!stream_) return E_OUTOFMEMORY;

    // Create presentation descriptor with this stream.
    IMFStreamDescriptor* stream_descs[] = { nullptr };
    hr = stream_->GetStreamDescriptor(&stream_descs[0]);
    if (FAILED(hr)) return hr;

    hr = MFCreatePresentationDescriptor(1, stream_descs, &presentation_desc_);
    stream_descs[0]->Release();

    if (FAILED(hr)) return hr;

    presentation_desc_->SelectStream(kStreamIdVideo);
    return S_OK;
}

void MediaSource::OnSampleRequested() {
    // Called by MediaStream::RequestSample. Synchronously read one frame
    // from the Frame Bus and deliver it to the stream's event queue as a
    // MEMediaSample (matches the MS VirtualCamera sample's pull model).
    if (shutdown_ || !started_ || !stream_) return;

    FrameView fv{};
    akvc_status_t st = fb_consumer_.wait_frame(200, fv);
    if (st != AKVC_OK || !fv.header) {
        Log("MediaSource::OnSampleRequested wait_frame failed: %d", st);
        return;
    }

    IMFSample* sample = nullptr;
    // Prefer the frame-server-provided allocator (creates a 2D NV12 buffer
    // with correct stride). Fall back to a plain memory buffer.
    if (!stream_->BuildSample(fv, &sample)) {
        return;
    }
    sample->SetSampleTime(MFGetSystemTime());
    sample->SetSampleDuration(333333);

    stream_->DeliverSample(sample);
    sample->Release();
}

DWORD MediaSource::ReaderThread() {
    // Unused in the pull model (RequestSample drives delivery). Kept for
    // reference / future push-model work.
    Log("reader thread (unused) started");
    return 0;
}

// ══════════════════════════════════════════════════════════════════════════
//  ClassFactory
// ══════════════════════════════════════════════════════════════════════════

STDMETHODIMP ClassFactory::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_IClassFactory) {
        *ppv = static_cast<IClassFactory*>(this);
        AddRef();
        return S_OK;
    }
    return E_NOINTERFACE;
}

STDMETHODIMP ClassFactory::CreateInstance(IUnknown* outer, REFIID riid, void** ppv) {
    std::wstring iid = GuidToString(riid);
    Log("ClassFactory::CreateInstance iid=%ls", iid.c_str());
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (outer) return CLASS_E_NOAGGREGATION;

    // The frame server queries for IMFActivate, so we create the activate
    // wrapper (which owns the real MediaSource).
    MediaSourceActivate* obj = new (std::nothrow) MediaSourceActivate();
    if (!obj) return E_OUTOFMEMORY;

    HRESULT hr = obj->QueryInterface(riid, ppv);
    Log("ClassFactory::CreateInstance QI hr=0x%08lx", hr);
    obj->Release();
    return hr;
}

STDMETHODIMP ClassFactory::LockServer(BOOL lock) {
    if (lock) InterlockedIncrement(&g_lock_count);
    else      InterlockedDecrement(&g_lock_count);
    return S_OK;
}

// ══════════════════════════════════════════════════════════════════════════
//  MediaSourceActivate
// ══════════════════════════════════════════════════════════════════════════

MediaSourceActivate::MediaSourceActivate() {
    InterlockedIncrement(&g_object_count);
    MFCreateAttributes(&attributes_, 8);
    Log("MediaSourceActivate::ctor attrs=%p", (void*)attributes_);

    // Set the device stream attributes the frame server reads during Start.
    // MF_DEVICESTREAM_STREAM_CATEGORY = KSCATEGORY_VIDEO_CAMERA so the
    // device shows up under video capture.
    attributes_->SetGUID(MF_DEVICESTREAM_STREAM_CATEGORY, KSCATEGORY_VIDEO_CAMERA);
    attributes_->SetUINT32(MF_DEVICESTREAM_STREAM_ID, kStreamIdVideo);
    attributes_->SetUINT32(MF_DEVICESTREAM_IMAGE_STREAM, FALSE);
    attributes_->SetUINT32(MF_DEVICESTREAM_FRAMESERVER_SHARED, TRUE);
    attributes_->SetUINT32(MF_DEVICESTREAM_MAX_FRAME_BUFFERS, 4);
}

MediaSourceActivate::~MediaSourceActivate() {
    Log("MediaSourceActivate::dtor");
    // Do NOT Shutdown the source here — the frame server may still hold a
    // reference to it. The source is ref-counted and self-destructs when its
    // last reference is released. (Matches the MS VirtualCamera sample.)
    if (source_) {
        source_->Release();
        source_ = nullptr;
    }
    if (attributes_) { attributes_->Release(); attributes_ = nullptr; }
    InterlockedDecrement(&g_object_count);
}

STDMETHODIMP_(ULONG) MediaSourceActivate::AddRef() { return ++ref_count_; }
STDMETHODIMP_(ULONG) MediaSourceActivate::Release() {
    ULONG c = --ref_count_;
    if (c == 0) delete this;
    return c;
}

STDMETHODIMP MediaSourceActivate::QueryInterface(REFIID riid, void** ppv) {
    Log("MediaSourceActivate::QueryInterface iid=%ls", GuidToString(riid).c_str());
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_IMFAttributes || riid == IID_IMFActivate) {
        *ppv = static_cast<IMFActivate*>(this);
    } else {
        Log("MediaSourceActivate::QueryInterface E_NOINTERFACE for %ls",
            GuidToString(riid).c_str());
        return E_NOINTERFACE;
    }
    AddRef();
    return S_OK;
}

// IMFAttributes — delegate to internal store.
STDMETHODIMP MediaSourceActivate::GetItem(REFGUID k, PROPVARIANT* v) { return attributes_->GetItem(k, v); }
STDMETHODIMP MediaSourceActivate::GetItemType(REFGUID k, MF_ATTRIBUTE_TYPE* t) { return attributes_->GetItemType(k, t); }
STDMETHODIMP MediaSourceActivate::CompareItem(REFGUID k, REFPROPVARIANT v, BOOL* r) { return attributes_->CompareItem(k, v, r); }
STDMETHODIMP MediaSourceActivate::Compare(IMFAttributes* p, MF_ATTRIBUTES_MATCH_TYPE t, BOOL* r) { return attributes_->Compare(p, t, r); }
STDMETHODIMP MediaSourceActivate::GetUINT32(REFGUID k, UINT32* v) { return attributes_->GetUINT32(k, v); }
STDMETHODIMP MediaSourceActivate::GetUINT64(REFGUID k, UINT64* v) { return attributes_->GetUINT64(k, v); }
STDMETHODIMP MediaSourceActivate::GetDouble(REFGUID k, double* v) { return attributes_->GetDouble(k, v); }
STDMETHODIMP MediaSourceActivate::GetGUID(REFGUID k, GUID* v) { return attributes_->GetGUID(k, v); }
STDMETHODIMP MediaSourceActivate::GetStringLength(REFGUID k, UINT32* c) { return attributes_->GetStringLength(k, c); }
STDMETHODIMP MediaSourceActivate::GetString(REFGUID k, LPWSTR v, UINT32 s, UINT32* c) { return attributes_->GetString(k, v, s, c); }
STDMETHODIMP MediaSourceActivate::GetAllocatedString(REFGUID k, LPWSTR* v, UINT32* c) { return attributes_->GetAllocatedString(k, v, c); }
STDMETHODIMP MediaSourceActivate::GetBlobSize(REFGUID k, UINT32* c) { return attributes_->GetBlobSize(k, c); }
STDMETHODIMP MediaSourceActivate::GetBlob(REFGUID k, UINT8* b, UINT32 s, UINT32* c) { return attributes_->GetBlob(k, b, s, c); }
STDMETHODIMP MediaSourceActivate::GetAllocatedBlob(REFGUID k, UINT8** b, UINT32* c) { return attributes_->GetAllocatedBlob(k, b, c); }
STDMETHODIMP MediaSourceActivate::GetUnknown(REFGUID k, REFIID r, LPVOID* p) { return attributes_->GetUnknown(k, r, p); }
STDMETHODIMP MediaSourceActivate::SetItem(REFGUID k, REFPROPVARIANT v) { return attributes_->SetItem(k, v); }
STDMETHODIMP MediaSourceActivate::DeleteItem(REFGUID k) { return attributes_->DeleteItem(k); }
STDMETHODIMP MediaSourceActivate::DeleteAllItems() { return attributes_->DeleteAllItems(); }
STDMETHODIMP MediaSourceActivate::SetUINT32(REFGUID k, UINT32 v) { return attributes_->SetUINT32(k, v); }
STDMETHODIMP MediaSourceActivate::SetUINT64(REFGUID k, UINT64 v) { return attributes_->SetUINT64(k, v); }
STDMETHODIMP MediaSourceActivate::SetDouble(REFGUID k, double v) { return attributes_->SetDouble(k, v); }
STDMETHODIMP MediaSourceActivate::SetGUID(REFGUID k, REFGUID v) { return attributes_->SetGUID(k, v); }
STDMETHODIMP MediaSourceActivate::SetString(REFGUID k, LPCWSTR v) { return attributes_->SetString(k, v); }
STDMETHODIMP MediaSourceActivate::SetBlob(REFGUID k, const UINT8* b, UINT32 s) { return attributes_->SetBlob(k, b, s); }
STDMETHODIMP MediaSourceActivate::SetUnknown(REFGUID k, IUnknown* p) { return attributes_->SetUnknown(k, p); }
STDMETHODIMP MediaSourceActivate::LockStore() { return attributes_->LockStore(); }
STDMETHODIMP MediaSourceActivate::UnlockStore() { return attributes_->UnlockStore(); }
STDMETHODIMP MediaSourceActivate::GetCount(UINT32* c) { return attributes_->GetCount(c); }
STDMETHODIMP MediaSourceActivate::GetItemByIndex(UINT32 i, GUID* k, PROPVARIANT* v) { return attributes_->GetItemByIndex(i, k, v); }
STDMETHODIMP MediaSourceActivate::CopyAllItems(IMFAttributes* d) { return attributes_->CopyAllItems(d); }

// IMFActivate
STDMETHODIMP MediaSourceActivate::ActivateObject(REFIID riid, void** ppv) {
    Log("MediaSourceActivate::ActivateObject iid=%ls", GuidToString(riid).c_str());
    if (!ppv) return E_POINTER;
    *ppv = nullptr;

    if (source_ == nullptr) {
        source_ = new (std::nothrow) MediaSource();
        if (!source_) return E_OUTOFMEMORY;
    }
    HRESULT hr = source_->QueryInterface(riid, ppv);
    Log("MediaSourceActivate::ActivateObject QI hr=0x%08lx", hr);
    return hr;
}

STDMETHODIMP MediaSourceActivate::ShutdownObject() {
    // Per the MS VirtualCamera sample: ShutdownObject is a no-op (the source
    // is kept alive; only DetachObject tears it down). Shutting down here
    // causes the frame server's subsequent operations to fail with
    // MF_E_SHUTDOWN.
    Log("MediaSourceActivate::ShutdownObject (no-op)");
    return S_OK;
}

STDMETHODIMP MediaSourceActivate::DetachObject() {
    Log("MediaSourceActivate::DetachObject");
    if (source_) {
        source_->Release();
        source_ = nullptr;
    }
    return S_OK;
}


}  // namespace akvc::mf

// ══════════════════════════════════════════════════════════════════════════
//  DLL entry points
// ══════════════════════════════════════════════════════════════════════════

extern "C" {

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
        akvc::mf::Log("DllMain DLL_PROCESS_ATTACH pid=%lu", ::GetCurrentProcessId());
    } else if (reason == DLL_PROCESS_DETACH) {
        akvc::mf::Log("DllMain DLL_PROCESS_DETACH pid=%lu", ::GetCurrentProcessId());
    }
    return TRUE;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    akvc::mf::Log("DllGetClassObject riid=%ls", akvc::mf::GuidToString(riid).c_str());
    if (rclsid != akvc::mf::CLSID_AKVCMFSource) {
        akvc::mf::Log("DllGetClassObject CLASS_E_CLASSNOTAVAILABLE (wrong CLSID)");
        return CLASS_E_CLASSNOTAVAILABLE;
    }
    auto* factory = new (std::nothrow) akvc::mf::ClassFactory();
    if (!factory) return E_OUTOFMEMORY;

    HRESULT hr = factory->QueryInterface(riid, ppv);
    akvc::mf::Log("DllGetClassObject factory QI hr=0x%08lx", hr);
    factory->Release();
    return hr;
}

STDAPI DllCanUnloadNow() {
    return (akvc::mf::g_lock_count == 0 && akvc::mf::g_object_count == 0)
           ? S_OK : S_FALSE;
}

// Registration is done via MFCreateVirtualCamera() at runtime.
STDAPI DllRegisterServer() { return S_OK; }
STDAPI DllUnregisterServer() { return S_OK; }

}  // extern "C"
