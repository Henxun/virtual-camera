// SPDX-License-Identifier: Apache-2.0
// Standalone MF VirtualCamera registration test.
// Builds with the project's toolchain via make.py.
#include <stdio.h>
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfvirtualcamera.h>
#include <ks.h>

// {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}  — our MediaSource CLSID
static const GUID CLSID_AKVCMFSource = {
    0x3c2d3a1a, 0x8e5f, 0x4b8f, {0x9c, 0x1a, 0x2d, 0x7e, 0x5f, 0x1a, 0x3b, 0x4c}
};

int main() {
    HRESULT hr;

    hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    printf("CoInitializeEx: 0x%08lx\n", hr);

    hr = MFStartup(MF_VERSION, MFSTARTUP_FULL);
    printf("MFStartup: 0x%08lx\n", hr);

    BOOL supported = FALSE;
    hr = MFIsVirtualCameraTypeSupported(MFVirtualCameraType_SoftwareCameraSource, &supported);
    printf("Supported: hr=0x%08lx supported=%d\n", hr, supported);

    // Create the virtual camera. For a Synthetic (non-wrapping) virtual camera:
    //   - sourceId = the MediaSource CLSID string
    //   - categories = nullptr, count = 0
    //   - do NOT call AddDeviceSourceInfo (that's only for wrapping a physical
    //     camera, and takes the physical camera's symbolic link, not a CLSID)
    //   - set VCAM_KIND = Synthetic (custom attribute the activate reads)
    GUID categories_unused[] = { KSCATEGORY_VIDEO_CAMERA };
    IMFVirtualCamera* vc = nullptr;
    wchar_t sourceId[80];
    StringFromGUID2(CLSID_AKVCMFSource, sourceId, 80);

    hr = MFCreateVirtualCamera(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_Session,
        MFVirtualCameraAccess_CurrentUser,
        L"AK Virtual Camera (MF Test)",
        sourceId,
        nullptr, 0,  // no categories
        &vc);
    printf("MFCreateVirtualCamera(sourceId=%ls): hr=0x%08lx vc=%p\n", sourceId, hr, (void*)vc);
    if (FAILED(hr)) goto done;

    // Set VCAM_KIND = Synthetic (0). The activate object reads this in
    // ActivateObject to decide which source type to create.
    // {D4A12C09-2C2A-4FC3-ABD7-ABE86BBA9A3D} — matches our DLL's VCAM_KIND.
    static const GUID VCAM_KIND = {
        0xd4a12c09, 0x2c2a, 0x4fc3, {0xab, 0xd7, 0xab, 0xe8, 0x6b, 0xba, 0x9a, 0x3d}
    };
    hr = vc->SetUINT32(VCAM_KIND, 0 /*Synthetic*/);
    printf("SetUINT32(VCAM_KIND=Synthetic): hr=0x%08lx\n", hr);

    hr = vc->Start(nullptr);
    printf("Start: hr=0x%08lx\n", hr);

    if (SUCCEEDED(hr)) {
        printf("\nSUCCESS! Check Chrome/Edge camera list for 'AK Virtual Camera (MF Test)'\n");
    } else {
        printf("\nStart returned 0x%08lx (may still register the PnP device).\n", hr);
    }
    printf("Keeping alive 30 seconds for PnP enumeration / Chrome testing...\n");
    Sleep(30000);

    if (vc) {
        vc->Stop();
        vc->Shutdown();
        vc->Release();
    }

done:
    MFShutdown();
    CoUninitialize();
    return 0;
}
