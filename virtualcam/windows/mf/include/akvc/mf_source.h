// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — MF Virtual Camera Media Source
//
// This DLL is loaded by Windows Camera Frame Server (frameserver.exe). It
// reads frames from the shared memory Frame Bus and delivers them as IMFSample.
//
// Registration is done via MFCreateVirtualCamera() at runtime (by Helper or
// desktop app), NOT via regsvr32.

#ifndef AKVC_MF_SOURCE_H
#define AKVC_MF_SOURCE_H

#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mfvirtualcamera.h>
#include <ks.h>
#include <ksmedia.h>
#include <ksproxy.h>

#include <atomic>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>
#include <thread>
#include <vector>

#include <windows.h>

#include "akvc/framebus.h"
#include "akvc_protocol.h"

namespace akvc::mf {

// Debug logging helpers (defined in mf_source.cpp).
void Log(const char* fmt, ...);
std::wstring GuidToString(REFGUID g);

// {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}
extern const CLSID CLSID_AKVCMFSource;

constexpr DWORD kStreamIdVideo = 0;

// Supported media types
struct MediaTypeDesc {
    UINT32 width;
    UINT32 height;
    UINT32 fps_num;
    UINT32 fps_den;
    GUID   subtype;
};

extern const MediaTypeDesc kMediaTypes[];
extern const UINT32 kMediaTypeCount;

// ── Ref-counted COM base template ──

template <typename T>
class ComBase : public T {
public:
    STDMETHODIMP_(ULONG) AddRef() override { return ++ref_count_; }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

protected:
    virtual ~ComBase() = default;
    std::atomic<ULONG> ref_count_{1};
};

// ── Forward declarations ──

class MediaSource;
class MediaStream;

// ── Media Stream ──

class MediaStream final : public ComBase<IMFMediaStream> {
public:
    MediaStream(MediaSource* source, DWORD stream_id, IMFMediaType* media_type);
    ~MediaStream() override;

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override;

    // IMFMediaEventGenerator
    STDMETHODIMP BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) override;
    STDMETHODIMP EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) override;
    STDMETHODIMP GetEvent(DWORD flags, IMFMediaEvent** event) override;
    STDMETHODIMP QueueEvent(MediaEventType type, REFGUID ext, HRESULT status,
                            const PROPVARIANT* value) override;

    // IMFMediaStream
    STDMETHODIMP GetMediaSource(IMFMediaSource** out) override;
    STDMETHODIMP GetStreamDescriptor(IMFStreamDescriptor** out) override;
    STDMETHODIMP RequestSample(IUnknown* token) override;

    void Shutdown();
    void DeliverSample(IMFSample* sample);
    bool IsShutdown() const { return shutdown_; }

    // Build an IMFSample from a Frame Bus frame view. Uses the frame-server
    // allocator (2D buffer) if available, else a plain memory buffer.
    bool BuildSample(const akvc::FrameView& fv, IMFSample** out);

    // Sample allocator provided by the frame server (via
    // IMFSampleAllocatorControl::SetDefaultAllocator). When set, RequestSample
    // uses it to allocate a 2D buffer that the frame server can render.
    void SetAllocator(IUnknown* allocator);
    IMFSampleAllocatorControl* GetAllocatorControl() { return allocator_control_; }
    void SetAllocatorControl(IMFSampleAllocatorControl* c) { allocator_control_ = c; }

private:
    MediaSource* source_;
    DWORD stream_id_;
    IMFMediaType* media_type_;
    IMFStreamDescriptor* descriptor_;
    IMFMediaEventQueue* event_queue_ = nullptr;
    IMFVideoSampleAllocator* allocator_ = nullptr;  // frame-server-provided
    IMFSampleAllocatorControl* allocator_control_ = nullptr;
    std::atomic<bool> shutdown_{false};
};

// ── Media Source ──

class MediaSource final : public IMFMediaSourceEx, public IMFGetService, public IKsControl, public IMFSampleAllocatorControl {
    friend class MediaSourceActivate;
public:
    MediaSource();
    ~MediaSource();

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    STDMETHODIMP_(ULONG) AddRef() override { return ++ref_count_; }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    // IMFMediaEventGenerator
    STDMETHODIMP BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) override;
    STDMETHODIMP EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) override;
    STDMETHODIMP GetEvent(DWORD flags, IMFMediaEvent** event) override;
    STDMETHODIMP QueueEvent(MediaEventType type, REFGUID ext, HRESULT status,
                            const PROPVARIANT* value) override;

    // IMFMediaSource
    STDMETHODIMP CreatePresentationDescriptor(IMFPresentationDescriptor** desc) override;
    STDMETHODIMP GetCharacteristics(DWORD* characteristics) override;
    STDMETHODIMP Pause() override;
    STDMETHODIMP Shutdown() override;
    STDMETHODIMP Start(IMFPresentationDescriptor* desc, const GUID* format,
                       const PROPVARIANT* start_pos) override;
    STDMETHODIMP Stop() override;

    // IMFMediaSourceEx
    STDMETHODIMP GetSourceAttributes(IMFAttributes** ppAttributes) override;
    STDMETHODIMP GetStreamAttributes(DWORD dwStreamIdentifier,
                                     IMFAttributes** ppAttributes) override;
    STDMETHODIMP SetD3DManager(IUnknown* pManager) override;

    // IMFGetService
    STDMETHODIMP GetService(REFGUID guidService, REFIID riid, LPVOID* ppvObject) override;

    // IKsControl — frame server probes camera capabilities via KS properties.
    // Return ERROR_SET_NOT_FOUND for anything we don't implement (matches
    // the AVStream driver behavior expected by the frame server).
    STDMETHODIMP KsProperty(PKSPROPERTY pProperty, ULONG ulPropertyLength,
                            LPVOID pPropertyData, ULONG ulDataLength,
                            ULONG* pBytesReturned) override;
    STDMETHODIMP KsMethod(PKSMETHOD pMethod, ULONG ulMethodLength,
                          LPVOID pMethodData, ULONG ulDataLength,
                          ULONG* pBytesReturned) override;
    STDMETHODIMP KsEvent(PKSEVENT pEvent, ULONG ulEventLength,
                         LPVOID pEventData, ULONG ulDataLength,
                         ULONG* pBytesReturned) override;

    // IMFSampleAllocatorControl — the frame server provides its own sample
    // allocator (via SetDefaultAllocator); we use it in RequestSample so the
    // sample buffer format matches what the frame server expects (2D NV12
    // buffer with correct stride). This is the key to Chrome rendering.
    STDMETHODIMP GetAllocatorUsage(DWORD dwOutputStreamID, DWORD* pdwInputStreamID,
                                   MFSampleAllocatorUsage* peUsage) override;
    STDMETHODIMP SetDefaultAllocator(DWORD dwOutputStreamID, IUnknown* pAllocator) override;

    // Called by stream
    void OnSampleRequested();
    // Pull one frame from the Frame Bus (used by MediaStream::RequestSample).
    akvc_status_t WaitFrame(akvc::FrameView& fv) { return fb_consumer_.wait_frame(200, fv); }

private:
    DWORD ReaderThread();
    HRESULT CreateStreamFromPresentation(IMFPresentationDescriptor* desc);

    std::atomic<ULONG> ref_count_{1};
    std::atomic<bool> shutdown_{false};
    std::atomic<bool> started_{false};
    std::atomic<bool> paused_{false};

    MediaStream* stream_ = nullptr;
    IMFMediaEventQueue* event_queue_ = nullptr;
    IMFPresentationDescriptor* presentation_desc_ = nullptr;
    IMFAttributes* source_attributes_ = nullptr;  // returned by GetSourceAttributes

    std::thread reader_thread_;
    FrameBusConsumer fb_consumer_;
};

// ── Media Source Activate ──
//
// The frame server instantiates our CLSID and queries for IMFActivate.
// This class wraps an IMFAttributes store (for the IMFAttributes methods
// inherited by IMFActivate) and creates the real MediaSource on
// ActivateObject().

class MediaSourceActivate final : public IMFActivate {
public:
    MediaSourceActivate();
    ~MediaSourceActivate();

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    STDMETHODIMP_(ULONG) AddRef() override;
    STDMETHODIMP_(ULONG) Release() override;

    // IMFAttributes — all delegate to the internal store.
    STDMETHODIMP GetItem(REFGUID key, PROPVARIANT* value) override;
    STDMETHODIMP GetItemType(REFGUID key, MF_ATTRIBUTE_TYPE* type) override;
    STDMETHODIMP CompareItem(REFGUID key, REFPROPVARIANT value, BOOL* result) override;
    STDMETHODIMP Compare(IMFAttributes* pTheirs, MF_ATTRIBUTES_MATCH_TYPE type, BOOL* result) override;
    STDMETHODIMP GetUINT32(REFGUID key, UINT32* value) override;
    STDMETHODIMP GetUINT64(REFGUID key, UINT64* value) override;
    STDMETHODIMP GetDouble(REFGUID key, double* value) override;
    STDMETHODIMP GetGUID(REFGUID key, GUID* value) override;
    STDMETHODIMP GetStringLength(REFGUID key, UINT32* pcchLength) override;
    STDMETHODIMP GetString(REFGUID key, LPWSTR pwszValue, UINT32 cchBufSize, UINT32* pcchLength) override;
    STDMETHODIMP GetAllocatedString(REFGUID key, LPWSTR* ppwszValue, UINT32* pcchLength) override;
    STDMETHODIMP GetBlobSize(REFGUID key, UINT32* pcbBlobSize) override;
    STDMETHODIMP GetBlob(REFGUID key, UINT8* pBuf, UINT32 cbBufSize, UINT32* pcbBlobSize) override;
    STDMETHODIMP GetAllocatedBlob(REFGUID key, UINT8** ppBuf, UINT32* pcbSize) override;
    STDMETHODIMP GetUnknown(REFGUID key, REFIID riid, LPVOID* ppv) override;
    STDMETHODIMP SetItem(REFGUID key, REFPROPVARIANT value) override;
    STDMETHODIMP DeleteItem(REFGUID key) override;
    STDMETHODIMP DeleteAllItems() override;
    STDMETHODIMP SetUINT32(REFGUID key, UINT32 value) override;
    STDMETHODIMP SetUINT64(REFGUID key, UINT64 value) override;
    STDMETHODIMP SetDouble(REFGUID key, double value) override;
    STDMETHODIMP SetGUID(REFGUID key, REFGUID value) override;
    STDMETHODIMP SetString(REFGUID key, LPCWSTR value) override;
    STDMETHODIMP SetBlob(REFGUID key, const UINT8* pBuf, UINT32 cbBufSize) override;
    STDMETHODIMP SetUnknown(REFGUID key, IUnknown* pUnknown) override;
    STDMETHODIMP LockStore() override;
    STDMETHODIMP UnlockStore() override;
    STDMETHODIMP GetCount(UINT32* pcItems) override;
    STDMETHODIMP GetItemByIndex(UINT32 unIndex, GUID* pguidKey, PROPVARIANT* pValue) override;
    STDMETHODIMP CopyAllItems(IMFAttributes* pDest) override;

    // IMFActivate
    STDMETHODIMP ActivateObject(REFIID riid, void** ppv) override;
    STDMETHODIMP ShutdownObject() override;
    STDMETHODIMP DetachObject() override;

private:
    std::atomic<ULONG> ref_count_{1};
    IMFAttributes* attributes_ = nullptr;
    MediaSource* source_ = nullptr;
};

// ── Class Factory ──

class ClassFactory final : public ComBase<IClassFactory> {
public:
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    STDMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override;
    STDMETHODIMP LockServer(BOOL lock) override;
};

// ── Module globals ──

extern LONG g_lock_count;
extern LONG g_object_count;

}  // namespace akvc::mf

#endif  // AKVC_MF_SOURCE_H
