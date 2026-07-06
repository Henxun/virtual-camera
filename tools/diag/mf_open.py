from __future__ import annotations

import subprocess

POWERSHELL_SCRIPT = r'''
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime]
$null = [Windows.Media.Capture.MediaCapture, Windows.Media.Capture, ContentType=WindowsRuntime]
$null = [Windows.Media.Capture.MediaCaptureInitializationSettings, Windows.Media.Capture, ContentType=WindowsRuntime]
$null = [Windows.Media.Capture.StreamingCaptureMode, Windows.Media.Capture, ContentType=WindowsRuntime]

function As-Task([object]$op, [type]$resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and
            $_.IsGenericMethodDefinition -and
            $_.GetGenericArguments().Count -eq 1 -and
            $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } |
        Select-Object -First 1
    if (-not $method) {
        throw 'AsTask<TResult>(IAsyncOperation<TResult>) overload not found'
    }
    $closed = $method.MakeGenericMethod($resultType)
    return $closed.Invoke($null, @($op))
}

Write-Host 'STEP=ENUM_START'
$devicesTask = As-Task ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([Windows.Devices.Enumeration.DeviceClass]::VideoCapture)) ([Windows.Devices.Enumeration.DeviceInformationCollection])
if (-not $devicesTask.Wait(5000)) {
    throw 'FindAllAsync timed out'
}
$devices = $devicesTask.Result
$target = $null
foreach ($device in $devices) {
    if ($device.Name -eq 'AK Virtual Camera') {
        $target = $device
        break
    }
}
if (-not $target) { throw 'AK Virtual Camera not found in WinRT VideoCapture enumeration' }
Write-Host ("TARGET=" + $target.Id)

$settings = [Windows.Media.Capture.MediaCaptureInitializationSettings]::new()
$settings.VideoDeviceId = $target.Id
$settings.StreamingCaptureMode = [Windows.Media.Capture.StreamingCaptureMode]::Video
$mc = [Windows.Media.Capture.MediaCapture]::new()

Write-Host 'STEP=INITIALIZE_START'
$initTask = As-Task ($mc.InitializeAsync($settings)) ([object])
if (-not $initTask.Wait(5000)) {
    throw 'MediaCapture.InitializeAsync timed out'
}
$null = $initTask.Result
Write-Host 'INITIALIZE=OK'

Write-Host 'STEP=HOLD_OPEN'
Start-Sleep -Seconds 5
$mc.Dispose()
Write-Host 'DISPOSE=OK'
'''

completed = subprocess.run(
    ["powershell", "-NoProfile", "-Command", POWERSHELL_SCRIPT],
    capture_output=True,
    text=True,
    timeout=20,
)
print(completed.stdout, end="")
if completed.returncode != 0:
    raise SystemExit(completed.stderr.strip() or completed.stdout.strip() or f"powershell failed with exit {completed.returncode}")
