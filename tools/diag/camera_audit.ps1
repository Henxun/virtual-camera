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
Get-PnpDevice -Class Camera,Image,SoftwareDevice |
    Where-Object { $_.FriendlyName -like '*Camera*' -or $_.FriendlyName -like '*AK*' -or $_.InstanceId -like '*VCAM*' -or $_.InstanceId -like '*USB*VID*' } |
    Select-Object FriendlyName, Status, Class, InstanceId | Format-Table -AutoSize
