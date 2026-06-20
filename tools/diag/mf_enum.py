# SPDX-License-Identifier: Apache-2.0
"""Enumerate MF video capture devices to check if AK Virtual Camera appears."""
import ctypes
from ctypes import POINTER, byref, c_void_p, c_uint32, c_wchar_p, c_int, c_uint64

class GUID(ctypes.Structure):
    _fields_ = [('Data1', c_uint32), ('Data2', ctypes.c_ushort), ('Data3', ctypes.c_ushort),
                ('Data4', ctypes.c_ubyte * 8)]

# MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = {C8AC933C-DEF8-4F1F-B8E0-E7E64D4324 9D}
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = GUID(0xc8ac933c, 0xdef8, 0x4f1f, (ctypes.c_ubyte*8)(0xb8,0xe0,0xe7,0xe6,0x4d,0x43,0x24,0x9d))
# MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = {8F0E8B68-3F0A-4D05-A927-C45D54BEBCCB}
VIDCAP_GUID = GUID(0x8f0e8b68, 0x3f0a, 0x4d05, (ctypes.c_ubyte*8)(0xa9,0x27,0xc4,0x5d,0x54,0xbe,0xbc,0xcb))
# MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = {60D0E559-52A6-4D32-9F59-2B48391B3656}
FRIENDLY_NAME = GUID(0x60d0e559, 0x52a6, 0x4d32, (ctypes.c_ubyte*8)(0x9f,0x59,0x2b,0x48,0x39,0x1b,0x36,0x56))
# MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK
SYMBOLIC_LINK = GUID(0x58f1b6e0, 0x2b41, 0x4c7b, (ctypes.c_ubyte*8)(0x9b,0xbc,0x71,0xa2,0x5b,0xeb,0xd9,0xb0))

ole32 = ctypes.WinDLL('ole32')
mfplat = ctypes.WinDLL('mfplat')

ole32.CoInitializeEx(None, 2)
mfplat.MFStartup(0x00020070, 1)

# MFCreateAttributes
mfplat.MFCreateAttributes.argtypes = [POINTER(c_void_p), c_uint32]
mfplat.MFCreateAttributes.restype = ctypes.HRESULT
attrs = c_void_p()
mfplat.MFCreateAttributes(byref(attrs), 1)

# Set GUID on attributes via vtable
vtbl = ctypes.cast(attrs.value, POINTER(c_void_p))[0]
set_guid = ctypes.cast(ctypes.cast(vtbl, POINTER(c_void_p))[23],
                       ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p, POINTER(GUID), POINTER(GUID)))
set_guid(attrs.value, byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE), byref(VIDCAP_GUID))

# MFEnumDeviceSources
mfplat.MFEnumDeviceSources.argtypes = [c_void_p, POINTER(POINTER(c_void_p)), POINTER(c_uint32)]
mfplat.MFEnumDeviceSources.restype = ctypes.HRESULT
ppActivate = POINTER(c_void_p)()
count = c_uint32(0)
hr = mfplat.MFEnumDeviceSources(attrs.value, byref(ppActivate), byref(count))
print(f'MFEnumDeviceSources: hr=0x{hr:08X}, count={count.value}')

for i in range(count.value):
    activate = ppActivate[i]
    vtbl = ctypes.cast(activate, POINTER(c_void_p))[0]
    get_str = ctypes.cast(ctypes.cast(vtbl, POINTER(c_void_p))[10],
                          ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p, POINTER(GUID), c_wchar_p, c_uint32, POINTER(c_uint32)))
    name_buf = ctypes.create_unicode_buffer(256)
    nlen = c_uint32(0)
    get_str(activate, byref(FRIENDLY_NAME), name_buf, 256, byref(nlen))
    sym_buf = ctypes.create_unicode_buffer(512)
    get_str(activate, byref(SYMBOLIC_LINK), sym_buf, 512, byref(nlen))
    print(f'  [{i}] {name_buf.value}')
    print(f'       symlink: {sym_buf.value}')
    if 'ak virtual' in name_buf.value.lower() or 'akvc' in sym_buf.value.lower():
        print('       *** AK VIRTUAL CAMERA FOUND ***')

mfplat.MFShutdown()
ole32.CoUninitialize()
