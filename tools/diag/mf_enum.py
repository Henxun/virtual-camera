# SPDX-License-Identifier: Apache-2.0
"""Enumerate WinRT video capture devices and call out AKVC visibility/duplicates."""

from __future__ import annotations

import json
import subprocess
from collections import Counter

POWERSHELL_SCRIPT = r'''
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime]
$op = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([Windows.Devices.Enumeration.DeviceClass]::VideoCapture)
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
$closed = $method.MakeGenericMethod([Windows.Devices.Enumeration.DeviceInformationCollection])
$task = $closed.Invoke($null, @($op))
$task.Wait()
$devices = $task.Result
$result = @()
foreach ($device in $devices) {
    $result += [PSCustomObject]@{
        Name = $device.Name
        Id = $device.Id
    }
}
$result | ConvertTo-Json -Depth 3 -Compress
'''

completed = subprocess.run(
    ["powershell", "-NoProfile", "-Command", POWERSHELL_SCRIPT],
    capture_output=True,
    text=True,
)
if completed.returncode != 0:
    raise SystemExit(completed.stderr.strip() or completed.stdout.strip() or f"powershell failed with exit {completed.returncode}")

raw = completed.stdout.strip()
decoded = json.loads(raw) if raw else []
if isinstance(decoded, dict):
    decoded = [decoded]

devices = [(str(item.get("Name", "")), str(item.get("Id", ""))) for item in decoded]
print(f"WinRT VideoCapture devices: count={len(devices)}")
for i, (name, device_id) in enumerate(devices):
    print(f"  [{i}] {name}")
    print(f"       id: {device_id}")
    if "ak virtual" in name.lower() or "akvc" in device_id.lower():
        print("       *** AK VIRTUAL CAMERA FOUND ***")

name_counts = Counter(name for name, _ in devices)
duplicates = {name: n for name, n in name_counts.items() if n > 1}
if duplicates:
    print("Duplicate friendly names detected:")
    for name, n in sorted(duplicates.items()):
        print(f"  {name}: {n}")
else:
    print("Duplicate friendly names detected: none")

ak_count = sum(1 for name, device_id in devices if "ak virtual" in name.lower() or "akvc" in device_id.lower())
print(f"AKVC logical devices found: {ak_count}")
