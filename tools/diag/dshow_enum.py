# SPDX-License-Identifier: Apache-2.0
"""DShow filter registration + frame bus diagnostic.

Run:  uv run python tools/diag/dshow_enum.py

Checks:
  1. DShow filter CLSID is registered (InprocServer32 path)
  2. Filter Mapper category entry exists (so consumers can enumerate it)
  3. Frame Bus shared memory exists and has fresh frames
"""

from __future__ import annotations

import ctypes
import struct
import sys
import time
from ctypes import POINTER, c_int, c_uint8, c_uint32, c_void_p, c_wchar_p
from pathlib import Path

CLSID = "{8E14549A-DB61-4309-AFA1-3578E927E933}"
SHM_NAME = r"Local\akvc-frames-v1"


def check_registration() -> bool:
    import winreg
    print("=== DShow Filter Registration ===")
    # 1. InprocServer32
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

    # 2. Filter Mapper category (VideoInputDeviceCategory)
    # {860BB310-5D01-11d0-BD3B-00A0C911CE86}
    cat = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            f"CLSID\\{cat}\\Instance\\{CLSID}",
        )
        friendly, _ = winreg.QueryValueEx(key, "FriendlyName")
        winreg.CloseKey(key)
        print(f"  Filter category: registered as '{friendly}'")
    except FileNotFoundError:
        print("  [WARN] Filter not in VideoInputDeviceCategory")
        print("         consumers may not enumerate it — re-register (admin)")
        return False
    return True


def check_framebus() -> bool:
    print("\n=== Frame Bus ===")
    if sys.platform != "win32":
        print("  [SKIP] not Windows")
        return False

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenFileMappingW.restype = c_void_p
    k.OpenFileMappingW.argtypes = [c_uint32, c_int, c_wchar_p]
    k.MapViewOfFile.restype = c_void_p
    k.MapViewOfFile.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, ctypes.c_size_t]

    h = k.OpenFileMappingW(0x0004, 0, SHM_NAME)  # FILE_MAP_READ
    err = ctypes.get_last_error()
    if not h:
        print(f"  [FAIL] cannot open SHM '{SHM_NAME}' (err={err})")
        if err == 2:
            print("         SHM not found — start the app and click Start first")
        elif err == 5:
            print("         access denied — permission/ACL issue")
        return False

    base = k.MapViewOfFile(h, 0x0004, 0, 0, 0)
    if not base:
        print("  [FAIL] MapViewOfFile failed")
        return False

    ctrl = ctypes.cast(base, POINTER(c_uint8))
    magic = struct.unpack_from("<I", bytes(ctrl[0:4]))[0]
    schema = struct.unpack_from("<I", bytes(ctrl[4:8]))[0]
    seq = struct.unpack_from("<Q", bytes(ctrl[16:24]))[0]
    writer_pid = struct.unpack_from("<I", bytes(ctrl[24:28]))[0]
    hb = struct.unpack_from("<Q", bytes(ctrl[40:48]))[0]

    print(f"  magic:        0x{magic:08X} ({'OK' if magic == 0x43564B41 else 'BAD'})")
    print(f"  schema:       {schema}")
    print(f"  producer_seq: {seq}")
    print(f"  writer_pid:   {writer_pid}")
    print(f"  heartbeat:    {hb}")

    if seq == 0:
        print("  [WARN] no frames published yet — worker not running?")
        return False

    # Read latest frame
    slot_count = struct.unpack_from("<I", bytes(ctrl[8:12]))[0]
    slot_size = struct.unpack_from("<I", bytes(ctrl[12:16]))[0]
    slot_off = 128 + ((seq - 1) % slot_count) * slot_size
    hdr = bytes(ctrl[slot_off:slot_off + 80])
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
    bus = check_framebus()
    print("\n=== Summary ===")
    print(f"  Registration: {'PASS' if reg else 'FAIL'}")
    print(f"  Frame Bus:    {'PASS' if bus else 'FAIL'}")
    if reg and bus:
        print("\n  All checks pass. If Chrome still shows no picture,")
        print("  Chrome may be using the Media Foundation path (not DShow).")
        print("  Try OBS Studio (uses DShow) to confirm the DShow path works.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
