# SPDX-License-Identifier: Apache-2.0
"""Test MF Virtual Camera - minimal registration test."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from ctypes import POINTER, byref, c_void_p, c_ulong, c_int, c_wchar_p

if sys.platform != "win32":
    sys.exit(0)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


KSCATEGORY_VIDEO_CAMERA = GUID(
    0xe631a6e1, 0xccfc, 0x43a0,
    (ctypes.c_ubyte * 8)(0x92, 0x66, 0xf6, 0x16, 0x3c, 0x78, 0xf0, 0x6f)
)

ole32 = ctypes.WinDLL("ole32")
mfplat = ctypes.WinDLL("mfplat")
mfsg = ctypes.WinDLL("mfsensorgroup")

ole32.CoInitializeEx(None, 2)
print("CoInitializeEx OK")

MF_VERSION = 0x00020070
mfplat.MFStartup(ctypes.c_uint32(MF_VERSION), 1)
print("MFStartup OK")

# Check if type is supported
mfsg.MFIsVirtualCameraTypeSupported.argtypes = [c_int, POINTER(c_int)]
mfsg.MFIsVirtualCameraTypeSupported.restype = ctypes.HRESULT
supported = c_int(0)
hr = mfsg.MFIsVirtualCameraTypeSupported(0, byref(supported))
print(f"MF VirtualCamera supported: hr=0x{hr:08X}, supported={bool(supported.value)}")

# Try to create the virtual camera
mfsg.MFCreateVirtualCamera.argtypes = [
    c_int, c_int, c_int, c_wchar_p, c_wchar_p,
    POINTER(GUID), c_ulong, POINTER(c_void_p),
]
mfsg.MFCreateVirtualCamera.restype = ctypes.HRESULT

vc = c_void_p()
hr = mfsg.MFCreateVirtualCamera(
    0,  # SoftwareCameraSource
    0,  # Session
    0,  # CurrentUser
    "AK Virtual Camera (PyTest)",
    "{8E14549A-DB61-4309-AFA1-3578E927E933}",
    byref(KSCATEGORY_VIDEO_CAMERA), 1,
    byref(vc),
)
print(f"MFCreateVirtualCamera: hr=0x{hr:08X}, vc={vc}")

if vc.value:
    print("SUCCESS! Camera registered.")
    print("Open Chrome -> webrtc samples -> check camera list")
    input("Press Enter to quit and unregister...")
    # Release
    vtbl = ctypes.cast(vc.value, POINTER(c_void_p))[0]
    release = ctypes.cast(ctypes.cast(vtbl, POINTER(c_void_p))[1],
                          ctypes.CFUNCTYPE(c_ulong, c_void_p))
    release(vc.value)
    print("Released")
else:
    print("FAILED to create virtual camera")

mfplat.MFShutdown()
ole32.CoUninitialize()
