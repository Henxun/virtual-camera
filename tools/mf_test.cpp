// SPDX-License-Identifier: Apache-2.0
// Minimal MF VirtualCamera registration test.
#include <stdio.h>
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfvirtualcamera.h>
#include <ks.h>

// {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}
static const GUID CLSID_AKVCMFSource = {
    0x3c2d3a1a, 0x8e5f, 0x4b8f, {0x9c, 0x1a, 0x2d, 0x7e, 0x5f, 0x1a, 0x3b, 0x4c}
};

int main() {
    HRESULT hr;

    hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    printf("CoInitializeEx: 0x%08lx\n", hr);

    hr = MFStartup(MF_VERSION, MFSTARTUP_LITE);
    printf("MFStartup: 0x%08lx\n", hr);

    BOOL supported = FALSE;
    hr = MFIsVirtualCameraTypeSupported(MFVirtualCameraType_SoftwareCameraSource, &supported);
    printf("Supported: hr=0x%08lx, supported=%d\n", hr, supported);

    GUID categories[] = { KSCATEGORY_VIDEO_CAMERA };
    IMFVirtualCamera* vc = nullptr;

    hr = MFCreateVirtualCamera(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_Session,
        MFVirtualCameraAccess_CurrentUser,
        L"AK Virtual Camera",
        L"{8E14549A-DB61-4309-AFA1-3578E927E933}",
        categories, 1,
        &vc);
    printf("MFCreateVirtualCamera: hr=0x%08lx, vc=%p\n", hr, (void*)vc);

    if (vc) {
        wchar_t clsid[64];
        StringFromGUID2(CLSID_AKVCMFSource, clsid, 64);
        hr = vc->AddDeviceSourceInfo(clsid);
        printf("AddDeviceSourceInfo: hr=0x%08lx\n", hr);

        hr = vc->Start(nullptr);
        printf("Start: hr=0x%08lx\n", hr);

        if (SUCCEEDED(hr)) {
            printf("\n=== SUCCESS! Camera registered ===\n");
            printf("Open Chrome -> webrtc samples -> AK Virtual Camera\n");
            printf("Press Enter to quit (camera will unregister)...\n");
            getchar();
        } else {
            printf("\nStart failed. Press Enter...\n");
            getchar();
        }

        vc->Stop();
        vc->Shutdown();
        vc->Release();
    }

    MFShutdown();
    CoUninitialize();
    return 0;
}
