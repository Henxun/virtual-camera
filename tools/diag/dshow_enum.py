# SPDX-License-Identifier: Apache-2.0
"""DShow filter registration + frame bus diagnostic.

Run:  uv run python tools/diag/dshow_enum.py

Checks:
  1. DShow filter CLSID is registered (InprocServer32 path)
  2. Filter Mapper category entry exists (so consumers can enumerate it)
  3. Frame Bus backing file exists and has fresh frames
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
from ctypes import POINTER, byref, c_int, c_uint8, c_uint32, c_void_p, c_wchar_p
from pathlib import Path

# Frame-bus protocol constants (mirrored from virtualcam/shared/akvc_protocol.h;
# the former akvc._core_native Python wrapper was removed in M7).
FRAMEBUS_PATH_ENV = "AKVC_FRAMEBUS_PATH"
FRAMEBUS_DIR_ENV = "AKVC_FRAMEBUS_DIR"
FRAMEBUS_DEFAULT_SUBDIR = "AKVirtualCamera"
FRAMEBUS_DEFAULT_FILE = "akvc-frames-v1.bin"
# sizeof(akvc_ring_control_t)=128 + AKVC_DEFAULT_SLOT_SIZE(0x300000)*AKVC_RING_SLOTS(4)
FRAMEBUS_REGION_SIZE = 128 + 0x00300000 * 4


def _framebus_default_path() -> Path:
    """Mirror framebus_file_path(): AKVC_FRAMEBUS_PATH env, else <AKVC_FRAMEBUS_DIR
    or CSIDL_COMMON_DOCUMENTS/AKVirtualCamera>/akvc-frames-v1.bin."""
    explicit = os.environ.get(FRAMEBUS_PATH_ENV)
    if explicit:
        return Path(explicit)
    base = os.environ.get(FRAMEBUS_DIR_ENV)
    if not base:
        base = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"),
                            "Documents", FRAMEBUS_DEFAULT_SUBDIR)
    return Path(base) / FRAMEBUS_DEFAULT_FILE


FRAMEBUS_DEFAULT_PATH = _framebus_default_path()


ole32 = ctypes.OleDLL("ole32")
oleaut32 = ctypes.OleDLL("oleaut32")


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]


def guid(value: str) -> GUID:
    g = GUID()
    hr = ole32.CLSIDFromString(c_wchar_p(value), byref(g))
    if _failed(hr):
        raise OSError(f"CLSIDFromString failed for {value}: 0x{hr & 0xFFFFFFFF:08X}")
    return g



def _failed(hr: int) -> bool:
    return hr < 0


CLSID = "{8E14549A-DB61-4309-AFA1-3578E927E933}"
CLSID_SystemDeviceEnum = guid("{62BE5D10-60EB-11D0-BD3B-00A0C911CE86}")
CLSID_VideoInputDeviceCategory = guid("{860BB310-5D01-11D0-BD3B-00A0C911CE86}")
IID_ICreateDevEnum = guid("{29840822-5B84-11D0-BD3B-00A0C911CE86}")
IID_IPropertyBag = guid("{55272A00-42CB-11CE-8135-00AA004BB851}")
COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC_SERVER = 0x1
S_OK = 0
S_FALSE = 1
VT_BSTR = 8


class VARIANT_UNION(ctypes.Union):
    _fields_ = [("llVal", ctypes.c_longlong), ("lVal", ctypes.c_long), ("bstrVal", c_wchar_p)]


class VARIANT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("u", VARIANT_UNION),
    ]


def check_registration() -> bool:
    import winreg
    print("=== DShow Filter Registration ===")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, f"CLSID\\{CLSID}\\InprocServer32"
        )
        path, _ = winreg.QueryValueEx(key, None)
        tm, _ = winreg.QueryValueEx(key, "ThreadingModel")
        winreg.CloseKey(key)
        exists = Path(path).is_file()
        print(f"  InprocServer32: {path}")
        print(f"  ThreadingModel: {tm}")
        print(f"  DLL exists:     {exists}")
        if not exists:
            print("  [FAIL] DLL file missing — run: uv run tools/make.py build")
            return False
    except FileNotFoundError:
        print("  [FAIL] CLSID not registered — run (admin): uv run python -m akvc_cli register")
        return False

    cat = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            f"CLSID\\{cat}\\Instance",
        ) as key:
            subkeys, _, _ = winreg.QueryInfoKey(key)
            for i in range(subkeys):
                name = winreg.EnumKey(key, i)
                with winreg.OpenKey(key, name) as child:
                    try:
                        clsid, _ = winreg.QueryValueEx(child, "CLSID")
                    except FileNotFoundError:
                        continue
                    if clsid.upper() != CLSID.upper():
                        continue
                    friendly, _ = winreg.QueryValueEx(child, "FriendlyName")
                    print(f"  Filter category key: {name}")
                    print(f"  Filter category: registered as '{friendly}'")
                    return True
    except FileNotFoundError:
        pass

    print("  [WARN] Filter not in VideoInputDeviceCategory")
    print("         consumers may not enumerate it — re-register (admin)")
    return False


def check_directshow_enum() -> bool:
    print("\n=== DirectShow Enumeration ===")
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if _failed(hr):
        print(f"  [FAIL] CoInitializeEx failed hr=0x{hr & 0xFFFFFFFF:08X}")
        return False

    dev_enum = c_void_p()
    enum_moniker = c_void_p()
    moniker = c_void_p()
    bind_ctx = c_void_p()
    prop_bag = c_void_p()
    ok = False
    try:
        hr = ole32.CoCreateInstance(
            byref(CLSID_SystemDeviceEnum),
            None,
            CLSCTX_INPROC_SERVER,
            byref(IID_ICreateDevEnum),
            byref(dev_enum),
        )
        if _failed(hr):
            print(f"  [FAIL] CoCreateInstance(ICreateDevEnum) hr=0x{hr & 0xFFFFFFFF:08X}")
            return False

        vtbl = ctypes.cast(dev_enum, POINTER(POINTER(c_void_p))).contents
        create_class_enumerator = ctypes.WINFUNCTYPE(
            ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p), c_uint32
        )(vtbl[3])
        hr = create_class_enumerator(dev_enum, byref(CLSID_VideoInputDeviceCategory), byref(enum_moniker), 0)
        if hr == S_FALSE or not enum_moniker:
            print("  [FAIL] CreateClassEnumerator returned no devices")
            return False
        if _failed(hr):
            print(f"  [FAIL] CreateClassEnumerator hr=0x{hr & 0xFFFFFFFF:08X}")
            return False

        enum_vtbl = ctypes.cast(enum_moniker, POINTER(POINTER(c_void_p))).contents
        enum_next = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint32, POINTER(c_void_p), POINTER(c_uint32))(enum_vtbl[3])
        create_bind_ctx = ole32.CreateBindCtx
        create_bind_ctx.argtypes = [c_uint32, POINTER(c_void_p)]
        create_bind_ctx.restype = ctypes.c_long
        hr = create_bind_ctx(0, byref(bind_ctx))
        if _failed(hr):
            print(f"  [FAIL] CreateBindCtx hr=0x{hr & 0xFFFFFFFF:08X}")
            return False

        fetched = c_uint32()
        names: list[str] = []
        while True:
            moniker = c_void_p()
            hr = enum_next(enum_moniker, 1, byref(moniker), byref(fetched))
            if hr == S_FALSE:
                break
            if _failed(hr):
                print(f"  [FAIL] IEnumMoniker::Next hr=0x{hr & 0xFFFFFFFF:08X}")
                return False

            moniker_vtbl = ctypes.cast(moniker, POINTER(POINTER(c_void_p))).contents
            bind_to_storage = ctypes.WINFUNCTYPE(
                ctypes.c_long, c_void_p, c_void_p, c_void_p, POINTER(GUID), POINTER(c_void_p)
            )(moniker_vtbl[9])
            hr = bind_to_storage(moniker, bind_ctx, None, byref(IID_IPropertyBag), byref(prop_bag))
            if _failed(hr):
                print(f"  [WARN] BindToStorage hr=0x{hr & 0xFFFFFFFF:08X}")
                continue

            bag_vtbl = ctypes.cast(prop_bag, POINTER(POINTER(c_void_p))).contents
            read_prop = ctypes.WINFUNCTYPE(
                ctypes.c_long, c_void_p, c_wchar_p, POINTER(VARIANT), c_void_p
            )(bag_vtbl[3])
            value = VARIANT()
            hr = read_prop(prop_bag, "FriendlyName", byref(value), None)
            if hr == S_OK and value.vt == VT_BSTR and value.bstrVal:
                names.append(value.bstrVal)
            oleaut32.VariantClear(byref(value))
            ctypes.cast(prop_bag, ctypes.POINTER(ctypes.c_void_p))[0]
            ctypes.cast(prop_bag, ctypes.POINTER(POINTER(c_void_p))).contents[2]
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(bag_vtbl[2])
            release(prop_bag)
            prop_bag = c_void_p()

            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(moniker_vtbl[2])
            release(moniker)
            moniker = c_void_p()

        for name in names:
            print(f"  device: {name}")
        ok = "AK Virtual Camera" in names
        if ok:
            print("  [OK] ICreateDevEnum lists 'AK Virtual Camera'")
        else:
            print("  [FAIL] ICreateDevEnum did not list 'AK Virtual Camera'")
        return ok
    finally:
        for ptr in (prop_bag, moniker, bind_ctx, enum_moniker, dev_enum):
            if ptr:
                vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
                release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])
                release(ptr)
        ole32.CoUninitialize()


def check_framebus() -> bool:
    print("\n=== Frame Bus ===")
    if sys.platform != "win32":
        print("  [SKIP] not Windows")
        return False

    if env_path := os.environ.get(FRAMEBUS_PATH_ENV):
        path = Path(env_path)
    else:
        path = FRAMEBUS_DEFAULT_PATH

    print(f"  backing file: {path}")
    if not path.exists():
        print("  [FAIL] backing file not found — start the app and click Start first")
        return False

    size = path.stat().st_size
    print(f"  file size:    {size}")
    if size < FRAMEBUS_REGION_SIZE:
        print("  [FAIL] backing file is smaller than the frame bus region")
        return False

    with path.open("rb") as f:
        region = f.read(FRAMEBUS_REGION_SIZE)

    magic = struct.unpack_from("<I", region, 0)[0]
    schema = struct.unpack_from("<I", region, 4)[0]
    seq = struct.unpack_from("<Q", region, 16)[0]
    writer_pid = struct.unpack_from("<I", region, 24)[0]
    hb = struct.unpack_from("<Q", region, 40)[0]

    print(f"  magic:        0x{magic:08X} ({'OK' if magic == 0x43564B41 else 'BAD'})")
    print(f"  schema:       {schema}")
    print(f"  producer_seq: {seq}")
    print(f"  writer_pid:   {writer_pid}")
    print(f"  heartbeat:    {hb}")

    if seq == 0:
        print("  [WARN] no frames published yet — worker not running?")
        return False

    slot_count = struct.unpack_from("<I", region, 8)[0]
    slot_size = struct.unpack_from("<I", region, 12)[0]
    slot_off = 128 + ((seq - 1) % slot_count) * slot_size
    hdr = region[slot_off:slot_off + 80]
    fc = struct.unpack_from("<I", hdr, 8)[0]
    w, hh = struct.unpack_from("<II", hdr, 12)
    sh, st = struct.unpack_from("<QQ", hdr, 56)
    flags = struct.unpack_from("<I", hdr, 44)[0]
    name = {0x3231564E: "NV12", 0x32595559: "YUY2", 0x20424752: "RGB24"}.get(fc, hex(fc))
    print(f"  latest frame: {w}x{hh} {name} seq={st} flags={flags}")
    print(f"  frame valid:  {sh == st == seq}")
    print("  [OK] frames are flowing")
    return True


def main() -> int:
    reg = check_registration()
    enum_ok = check_directshow_enum()
    bus = check_framebus()
    print("\n=== Summary ===")
    print(f"  Registration: {'PASS' if reg else 'FAIL'}")
    print(f"  DirectShow:   {'PASS' if enum_ok else 'FAIL'}")
    print(f"  Frame Bus:    {'PASS' if bus else 'FAIL'}")
    if reg and enum_ok and bus:
        print("\n  All checks pass. If Chrome still shows no picture,")
        print("  Chrome may be using the Media Foundation path (not DShow).")
        print("  Try OBS Studio (uses DShow) to confirm the DShow path works.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
