# SPDX-License-Identifier: Apache-2.0
"""Camera device audit — enumerate every camera interface on the system.

Dumps:
  1. PnP virtual-camera device nodes (SWD\VCAMDEVAPI) with friendly name,
     container ID, symbolic link, and the IsVirtualCamera flag.
  2. DirectShow VideoInputDeviceCategory instances (what OBS/GraphStudioNext
     enumerate) with their backing CLSID / device path.
  3. The registered COM CLSIDs for our DShow filter and MF source.

Run:  powershell -ExecutionPolicy Bypass -File tools\diag\camera_audit.ps1
"""

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "============================================================"
Write-Host " 1. PnP Virtual Camera device nodes (SWD\VCAMDEVAPI)"
Write-Host "============================================================"
$vcams = Get-PnpDevice | Where-Object { $_.InstanceId -like '*VCAMDEVAPI*' -or $_.FriendlyName -like '*Virtual Camera*' -or $_.FriendlyName -like '*AK Virtual*' }
if (-not $vcams) { Write-Host "  (none)" }
foreach ($d in $vcams) {
    Write-Host ""
    Write-Host ("  FriendlyName : " + $d.FriendlyName)
    Write-Host ("  Status       : " + $d.Status)
    Write-Host ("  Class        : " + $d.Class)
    Write-Host ("  InstanceId   : " + $d.InstanceId)
    $props = Get-PnpDeviceProperty -InstanceId $d.InstanceId
    foreach ($p in $props) {
        if ($p.KeyName -in 'DEVPKEY_Device_FriendlyName','DEVPKEY_Device_ContainerId','DEVPKEY_DeviceInterface_SymbolicLink','DEVPKEY_NAME','DEVPKEY_DeviceInterface_IsVirtualCamera') {
            Write-Host ("    " + $p.KeyName + " = " + $p.Data)
        }
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host " 2. DirectShow VideoInputDeviceCategory instances (OBS view)"
Write-Host "    {860BB310-5D01-11d0-BD3B-00A0C911CE86}\Instance"
Write-Host "============================================================"
$cat = 'Registry::HKEY_CLASSES_ROOT\CLSID\{860BB310-5D01-11d0-BD3B-00A0C911CE86}\Instance'
Get-ChildItem $cat | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath
    $clsid = (Get-ItemProperty ($_.PSPath + '\CLSID')).'(default)'
    $dp = (Get-ItemProperty ($_.PSPath + '\DevicePath')).'(default)'
    Write-Host ""
    Write-Host ("  Instance : " + $_.PSChildName)
    Write-Host ("    FriendlyName = " + $p.FriendlyName)
    Write-Host ("    FilterCLSID  = " + $clsid)
    Write-Host ("    DevicePath   = " + $dp)
}

Write-Host ""
Write-Host "============================================================"
Write-Host " 3. Our COM CLSID registrations"
Write-Host "============================================================"
$pairs = @{
    'DShow filter (8E14549A)' = '{8E14549A-DB61-4309-AFA1-3578E927E933}'
    'MF source   (3C2D3A1A)' = '{3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}'
}
foreach ($k in $pairs.Keys) {
    $path = 'HKLM:\SOFTWARE\Classes\CLSID\' + $pairs[$k] + '\InprocServer32'
    $v = (Get-ItemProperty $path).'(default)'
    $tm = (Get-ItemProperty $path).ThreadingModel
    Write-Host ("  " + $k + "  =>  " + $v + "  (ThreadingModel=" + $tm + ")")
}

Write-Host ""
Write-Host "============================================================"
Write-Host " 4. All camera-class PnP devices (Camera / Image)"
Write-Host "============================================================"
Write-Host ""
Write-Host "============================================================"
Write-Host " 5. Quick health summary"
Write-Host "============================================================"
$akDevices = @($vcams | Where-Object { $_.FriendlyName -like '*AK Virtual*' -or $_.InstanceId -like '*VCAMDEVAPI*' })
$mfPath = (Get-ItemProperty 'HKLM:\SOFTWARE\Classes\CLSID\{3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}\InprocServer32').'(default)'
$dshowPath = (Get-ItemProperty 'HKLM:\SOFTWARE\Classes\CLSID\{8E14549A-DB61-4309-AFA1-3578E927E933}\InprocServer32').'(default)'
$mfDir = if ($mfPath) { Split-Path -Parent $mfPath } else { '' }
$dshowDir = if ($dshowPath) { Split-Path -Parent $dshowPath } else { '' }
Write-Host ("  AK logical devices : " + $akDevices.Count)
Write-Host ("  MF DLL path        : " + $mfPath)
Write-Host ("  DShow DLL path     : " + $dshowPath)
if ($akDevices.Count -gt 1) {
    Write-Host "  WARNING            : duplicate AK virtual camera logical devices detected"
} elseif ($akDevices.Count -eq 0) {
    Write-Host "  WARNING            : no AK virtual camera logical device found"
} else {
    Write-Host "  Device summary     : one AK virtual camera logical device found"
}
if ($mfDir -and $dshowDir -and $mfDir -ne $dshowDir) {
    Write-Host "  NOTE               : MF and DShow DLL directories differ; verify this is intentional"
}
