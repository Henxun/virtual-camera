# SPDX-License-Identifier: Apache-2.0
"""Repository-level checks for the macOS native skeleton."""

from __future__ import annotations

import plistlib
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MACOS_ROOT = ROOT / "virtualcam" / "macos"


def _top_level_named_block(text: str, section_name: str, block_name: str) -> str:
    section = text.split(f"{section_name}:\n", 1)[1]
    block_header = f"  {block_name}:\n"
    block_start = section.split(block_header, 1)[1]

    next_header_offset: int | None = None
    for line in block_start.splitlines(keepends=True):
        if line.startswith("  ") and not line.startswith("    "):
            next_header_offset = block_start.index(line)
            break

    if next_header_offset is None:
        return block_start
    return block_start[:next_header_offset]


def _objective_c_method_block(text: str, selector: str) -> str:
    start = text.index(selector)
    remainder = text[start:]
    next_method = remainder.find("\n- (", 1)
    next_class_boundary = remainder.find("\n@end", 1)
    boundaries = [index for index in (next_method, next_class_boundary) if index != -1]
    if not boundaries:
        return remainder
    return remainder[: min(boundaries)]


def test_macos_project_yml_exists_and_declares_expected_targets() -> None:
    project_yml = MACOS_ROOT / "project.yml"
    text = project_yml.read_text(encoding="utf-8")

    assert "akvc-macos-all:" in text
    assert "akvc-camera-extension:" in text
    assert "akvc-demo-app:" in text
    assert "akvc-macos-status:" in text
    assert "akvc-macos-install:" in text
    assert "akvc-macos-uninstall:" in text
    assert "akvc-macos-list-devices:" in text
    assert "akvc-macos-sync-ipc:" in text
    assert "akvc-macos-direct-sender:" in text
    assert "SWIFT_VERSION" not in text
    assert "AVFoundation.framework" in text
    assert "CoreMediaIO.framework" in text
    assert "CoreMedia.framework" in text
    assert "CoreVideo.framework" in text
    assert "SystemExtensions.framework" in text
    assert "APPLICATION_EXTENSION_API_ONLY: YES" in text
    assert 'macOS: "13.0"' in text
    assert 'MACOSX_DEPLOYMENT_TARGET: "13.0"' in text
    assert 'ARCHS: "arm64 x86_64"' in text
    assert 'ONLY_ACTIVE_ARCH: NO' in text

    status_section = text.split("  akvc-macos-status:")[1].split("  akvc-macos-install:")[0]
    install_section = text.split("  akvc-macos-install:")[1].split("  akvc-macos-uninstall:")[0]
    uninstall_section = text.split("  akvc-macos-uninstall:")[1].split("  akvc-macos-list-devices:")[0]
    list_devices_section = text.split("  akvc-macos-list-devices:")[1].split("  akvc-macos-sync-ipc:")[0]
    sync_ipc_section = text.split("  akvc-macos-sync-ipc:")[1].split("schemes:")[0]
    direct_sender_section = text.split("  akvc-macos-direct-sender:")[1].split("schemes:")[0]
    demo_app_section = text.split("  akvc-demo-app:")[1].split("  akvc-macos-status:")[0]

    assert "- target: akvc-macos-ipc" in status_section
    assert "- target: akvc-macos-ipc" in install_section
    assert "- target: akvc-macos-ipc" in uninstall_section
    assert "- target: akvc-macos-ipc" in list_devices_section
    assert "- target: akvc-macos-ipc" in sync_ipc_section
    assert "type: library.dynamic" in direct_sender_section
    assert "direct_sender" in direct_sender_section
    assert "CoreMediaIO.framework" in direct_sender_section
    assert "- target: akvc-camera-extension" in demo_app_section
    assert "demo_app/Info.plist" in demo_app_section
    assert "akvc-macos-sync-ipc: all" in text
    assert "akvc-macos-direct-sender: all" in text
    assert 'PRODUCT_BUNDLE_IDENTIFIER: com.sidus.amaran-desktop.cameraextension' in text


def test_macos_native_skeleton_files_exist() -> None:
    expected = [
        MACOS_ROOT / "camera_extension" / "AKVCProviderSource.h",
        MACOS_ROOT / "camera_extension" / "AKVCProviderSource.mm",
        MACOS_ROOT / "camera_extension" / "AKVCDeviceSource.h",
        MACOS_ROOT / "camera_extension" / "AKVCDeviceSource.mm",
        MACOS_ROOT / "camera_extension" / "AKVCStreamSource.h",
        MACOS_ROOT / "camera_extension" / "AKVCStreamSource.mm",
        MACOS_ROOT / "camera_extension" / "AKVCSinkStreamSource.h",
        MACOS_ROOT / "camera_extension" / "AKVCSinkStreamSource.mm",
        MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.h",
        MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm",
        MACOS_ROOT / "camera_extension" / "main.mm",
        MACOS_ROOT / "camera_extension" / "Info.plist",
        MACOS_ROOT / "camera_extension" / "CameraExtension.entitlements",
        MACOS_ROOT / "control_bridge" / "AKVCCommandSupport.h",
        MACOS_ROOT / "control_bridge" / "AKVCCommandSupport.mm",
        MACOS_ROOT / "control_bridge" / "AKVCSystemExtensionSupport.h",
        MACOS_ROOT / "control_bridge" / "AKVCSystemExtensionSupport.mm",
        MACOS_ROOT / "control_bridge" / "akvc_macos_status.mm",
        MACOS_ROOT / "control_bridge" / "akvc_macos_install.mm",
        MACOS_ROOT / "control_bridge" / "akvc_macos_uninstall.mm",
        MACOS_ROOT / "control_bridge" / "akvc_macos_list_devices.mm",
        MACOS_ROOT / "control_bridge" / "akvc_macos_sync_ipc.mm",
        MACOS_ROOT / "direct_sender" / "AKVCDirectCameraSender.h",
        MACOS_ROOT / "direct_sender" / "AKVCDirectCameraSender.mm",
        MACOS_ROOT / "ipc" / "include" / "akvc" / "macos_ipc.h",
        MACOS_ROOT / "ipc" / "include" / "akvc" / "framebus_posix.h",
        MACOS_ROOT / "ipc" / "src" / "macos_ipc.cpp",
        MACOS_ROOT / "ipc" / "src" / "framebus_posix.c",
    ]

    for path in expected:
        assert path.is_file(), path


def test_macos_project_yml_removes_camera_demo_host_target_and_keeps_demo_support() -> None:
    project_yml = MACOS_ROOT / "project.yml"
    text = project_yml.read_text(encoding="utf-8")
    all_scheme_section = _top_level_named_block(text, "schemes", "akvc-macos-all")

    assert "akvc-camera-demo-host:" not in text
    assert "demo_support/AKVCDemoFrameGenerator.h" in text
    assert "demo_support/AKVCDemoFrameGenerator.mm" in text
    assert "akvc-camera-demo-host: all" not in all_scheme_section


def test_macos_demo_support_files_exist() -> None:
    expected = [
        MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.h",
        MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.mm",
    ]

    for path in expected:
        assert path.is_file(), path

    header = (MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.h").read_text(encoding="utf-8")
    implementation = (MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.mm").read_text(encoding="utf-8")

    assert "@interface AKVCDemoFrameGenerator" in header
    assert "copyNextSampleBufferWithPresentationTime" in header
    assert "CMSampleBufferCreateReadyWithImageBuffer" in implementation


def test_macos_project_yml_declares_demo_app_target() -> None:
    project_yml = MACOS_ROOT / "project.yml"
    text = project_yml.read_text(encoding="utf-8")
    demo_app_section = _top_level_named_block(text, "targets", "akvc-demo-app")
    all_scheme_section = _top_level_named_block(text, "schemes", "akvc-macos-all")

    assert "akvc-demo-app:" in text
    assert "type: application" in demo_app_section
    assert "demo_app" in demo_app_section
    assert "demo_app/Info.plist" in demo_app_section
    assert "demo_app/DemoApp.entitlements" in demo_app_section
    assert "control_bridge/AKVCCommandSupport.mm" in demo_app_section
    assert "control_bridge/AKVCSystemExtensionSupport.mm" in demo_app_section
    assert "AppKit.framework" in demo_app_section
    assert "SystemExtensions.framework" in demo_app_section
    assert "akvc-demo-app: all" in all_scheme_section


def test_macos_demo_app_files_exist() -> None:
    expected = [
        MACOS_ROOT / "demo_app" / "main.mm",
        MACOS_ROOT / "demo_app" / "AppDelegate.h",
        MACOS_ROOT / "demo_app" / "AppDelegate.mm",
        MACOS_ROOT / "demo_app" / "MainWindowController.h",
        MACOS_ROOT / "demo_app" / "MainWindowController.mm",
        MACOS_ROOT / "demo_app" / "DemoControlService.h",
        MACOS_ROOT / "demo_app" / "DemoControlService.mm",
        MACOS_ROOT / "demo_app" / "Info.plist",
        MACOS_ROOT / "demo_app" / "DemoApp.entitlements",
    ]

    for path in expected:
        assert path.is_file(), path

    info_plist_data = plistlib.loads((MACOS_ROOT / "demo_app" / "Info.plist").read_bytes())
    entitlements_data = plistlib.loads((MACOS_ROOT / "demo_app" / "DemoApp.entitlements").read_bytes())

    assert info_plist_data["CFBundlePackageType"] == "APPL"
    assert info_plist_data["LSMinimumSystemVersion"] == "13.0"
    assert info_plist_data["NSSystemExtensionUsageDescription"]
    assert entitlements_data["com.apple.developer.system-extension.install"] is True


def test_macos_demo_app_source_contract_is_present() -> None:
    main_mm = (MACOS_ROOT / "demo_app" / "main.mm").read_text(encoding="utf-8")
    delegate_h = (MACOS_ROOT / "demo_app" / "AppDelegate.h").read_text(encoding="utf-8")
    delegate_mm = (MACOS_ROOT / "demo_app" / "AppDelegate.mm").read_text(encoding="utf-8")
    window_h = (MACOS_ROOT / "demo_app" / "MainWindowController.h").read_text(encoding="utf-8")
    window_mm = (MACOS_ROOT / "demo_app" / "MainWindowController.mm").read_text(encoding="utf-8")
    service_h = (MACOS_ROOT / "demo_app" / "DemoControlService.h").read_text(encoding="utf-8")
    service_mm = (MACOS_ROOT / "demo_app" / "DemoControlService.mm").read_text(encoding="utf-8")

    assert "NSApplicationMain" in main_mm or "sharedApplication" in main_mm
    assert "@interface AppDelegate" in delegate_h
    assert "NSApplicationDelegate" in delegate_h
    assert "MainWindowController" in delegate_mm
    assert "@interface MainWindowController" in window_h
    assert "refreshStatus" in window_mm
    assert "enableDemoAndActivate" in window_mm
    assert "disableDemo" in window_mm
    assert "manualAcceptanceInstructions" in window_mm
    assert "approval_required" in window_mm
    assert "all_devices" in window_mm
    assert "ipc_ready" in window_mm
    assert "readiness_stage" in window_mm
    assert "next_action" in window_mm
    assert "@interface DemoControlService" in service_h
    assert "refreshStatusWithError" in service_h
    assert "enableDemoAndActivateWithError" in service_h
    assert "disableDemoWithError" in service_h
    assert "manualAcceptanceInstructions" in service_h
    assert "AKVCSetDemoModeEnabled" in service_mm
    assert "AKVCSubmitSystemExtensionRequest" in service_mm
    assert "AKVCQuerySystemExtensionStatus" in service_mm
    assert "AKVCVideoDeviceSnapshot" in service_mm
    assert "AKVCResolvedHostExecutablePath" in service_mm
    assert "AKVCCameraExtensionIdentifier()" in service_mm
    assert 'payload[@"all_devices"]' in service_mm
    assert 'payload[@"host_executable_path"]' in service_mm
    assert 'payload[@"extension_identifier"]' in service_mm
    assert 'payload[@"ipc_ready"]' in service_mm
    assert 'payload[@"readiness_stage"]' in service_mm
    assert 'payload[@"next_action"]' in service_mm
    assert "readinessStageForPayload" in service_mm
    assert "nextActionForPayload" in service_mm
    assert "包含 Camera Extension 的 macOS 应用 / VirtualCamera.pkg" in service_mm


def test_macos_demo_app_doc_exists_and_covers_manual_acceptance() -> None:
    doc = (ROOT / "docs" / "macos" / "demo_app.md").read_text(encoding="utf-8")

    assert "macOS Demo App" in doc
    assert "akvc-demo-app" in doc
    assert "开发者模式" in doc
    assert "container app" in doc
    assert "QuickTime" in doc
    assert "FaceTime" in doc
    assert "Zoom" in doc
    assert "启用 Demo 并激活" in doc
    assert "下一步动作" in doc
    assert "ipc_ready" in doc


def test_macos_demo_app_control_service_owns_activation_request_and_demo_mode() -> None:
    service_mm = (MACOS_ROOT / "demo_app" / "DemoControlService.mm").read_text(encoding="utf-8")

    assert "AKVCSetDemoModeEnabled(YES, outError)" in service_mm
    assert "AKVCSubmitSystemExtensionRequest(YES, 30.0, outError)" in service_mm
    assert 'return @"激活链路失败，先处理 host / entitlement / bundle 条件";' in service_mm


def test_macos_demo_frame_generator_contract_is_present() -> None:
    header = (MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.h").read_text(encoding="utf-8")
    implementation = (MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.mm").read_text(encoding="utf-8")

    assert "@interface AKVCDemoFrameGenerator" in header
    assert "init NS_UNAVAILABLE" in header
    assert "new NS_UNAVAILABLE" in header
    assert "NS_DESIGNATED_INITIALIZER" in header
    assert "copyNextSampleBufferWithPresentationTime" in header
    assert "CMSampleBufferCreateReadyWithImageBuffer" in implementation
    assert "CVPixelBufferLockBaseAddress(" in implementation
    assert "CVPixelBufferGetBaseAddress(" in implementation
    assert "CVPixelBufferUnlockBaseAddress(" in implementation


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only demo frame generator smoke test")
def test_macos_demo_frame_generator_runtime_contract(tmp_path) -> None:
    if shutil.which("clang++") is None or shutil.which("xcrun") is None:
        pytest.skip("clang++/xcrun not available")

    sdk = subprocess.run(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if sdk.returncode != 0:
        raise AssertionError(sdk.stderr or sdk.stdout)

    source = tmp_path / "demo_frame_generator_smoke.mm"
    binary = tmp_path / "demo_frame_generator_smoke"
    source.write_text(
        textwrap.dedent(
            """
            #import <CoreMedia/CoreMedia.h>
            #import <CoreVideo/CoreVideo.h>
            #import <Foundation/Foundation.h>

            #import "AKVCDemoFrameGenerator.h"

            static int VerifyBuffer(
                CMSampleBufferRef sampleBuffer,
                CMTime expectedPTS,
                size_t expectedWidth,
                size_t expectedHeight,
                OSType expectedPixelFormat,
                uint8_t* outAnimatedBlue
            ) {
                if (sampleBuffer == nil) {
                    return 30;
                }

                if (CMSampleBufferGetNumSamples(sampleBuffer) != 1) {
                    return 31;
                }

                if (CMTimeCompare(CMSampleBufferGetPresentationTimeStamp(sampleBuffer), expectedPTS) != 0) {
                    return 32;
                }

                CVImageBufferRef imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer);
                if (imageBuffer == nil) {
                    return 33;
                }

                CVPixelBufferRef pixelBuffer = (CVPixelBufferRef)imageBuffer;
                if (CVPixelBufferGetWidth(pixelBuffer) != expectedWidth) {
                    return 34;
                }

                if (CVPixelBufferGetHeight(pixelBuffer) != expectedHeight) {
                    return 35;
                }

                if (CVPixelBufferGetPixelFormatType(pixelBuffer) != expectedPixelFormat) {
                    return 36;
                }

                CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                if (lockStatus != kCVReturnSuccess) {
                    return 37;
                }

                uint8_t* baseAddress = (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
                if (baseAddress == nil) {
                    CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                    return 38;
                }

                *outAnimatedBlue = baseAddress[4];
                CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                return 0;
            }

            int main(void) {
                @autoreleasepool {
                    NSError* error = nil;
                    AKVCDemoFrameGenerator* invalidGenerator =
                        [[AKVCDemoFrameGenerator alloc] initWithWidth:0 height:0];
                    CMSampleBufferRef invalidSampleBuffer =
                        [invalidGenerator copyNextSampleBufferWithPresentationTime:CMTimeMake(0, 60)
                                                                             error:&error];
                    if (invalidSampleBuffer != nil) {
                        CFRelease(invalidSampleBuffer);
                        return 10;
                    }
                    if (error == nil || error.code != 1) {
                        return 11;
                    }

                    error = nil;
                    AKVCDemoFrameGenerator* generator =
                        [[AKVCDemoFrameGenerator alloc] initWithWidth:64 height:36];
                    CMTime firstPTS = CMTimeMake(0, 60);
                    CMTime secondPTS = CMTimeMake(1, 60);
                    CMSampleBufferRef firstSampleBuffer =
                        [generator copyNextSampleBufferWithPresentationTime:firstPTS error:&error];
                    if (firstSampleBuffer == nil || error != nil) {
                        if (firstSampleBuffer != nil) {
                            CFRelease(firstSampleBuffer);
                        }
                        return 20;
                    }

                    error = nil;
                    CMSampleBufferRef secondSampleBuffer =
                        [generator copyNextSampleBufferWithPresentationTime:secondPTS error:&error];
                    if (secondSampleBuffer == nil || error != nil) {
                        CFRelease(firstSampleBuffer);
                        if (secondSampleBuffer != nil) {
                            CFRelease(secondSampleBuffer);
                        }
                        return 21;
                    }

                    uint8_t firstAnimatedBlue = 0;
                    uint8_t secondAnimatedBlue = 0;
                    int firstCheck = VerifyBuffer(
                        firstSampleBuffer,
                        firstPTS,
                        64,
                        36,
                        kCVPixelFormatType_32BGRA,
                        &firstAnimatedBlue
                    );
                    int secondCheck = VerifyBuffer(
                        secondSampleBuffer,
                        secondPTS,
                        64,
                        36,
                        kCVPixelFormatType_32BGRA,
                        &secondAnimatedBlue
                    );
                    CFRelease(firstSampleBuffer);
                    CFRelease(secondSampleBuffer);

                    if (firstCheck != 0) {
                        return firstCheck;
                    }
                    if (secondCheck != 0) {
                        return secondCheck;
                    }
                    if (firstAnimatedBlue == secondAnimatedBlue) {
                        return 40;
                    }
                    return 0;
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "clang++",
            "-std=gnu++20",
            "-fobjc-arc",
            "-x",
            "objective-c++",
            "-isysroot",
            sdk.stdout.strip(),
            "-mmacosx-version-min=13.0",
            "-I",
            str(MACOS_ROOT / "demo_support"),
            str(source),
            str(MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.mm"),
            "-framework",
            "Foundation",
            "-framework",
            "CoreMedia",
            "-framework",
            "CoreVideo",
            "-o",
            str(binary),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)

    executed = subprocess.run(
        [str(binary)],
        cwd=str(ROOT),
        env={
            **dict(os.environ),
            "AKVC_MACOS_SHARED_STATE_DIR": str(tmp_path / "akvc-shared"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if executed.returncode != 0:
        raise AssertionError(
            f"demo frame generator smoke failed with exit {executed.returncode}: "
            f"{executed.stderr or executed.stdout}"
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only frame provider smoke test")
def test_macos_frame_provider_consumes_client_sample_buffer_once_runtime_contract(tmp_path) -> None:
    if shutil.which("clang++") is None or shutil.which("xcrun") is None:
        pytest.skip("clang++/xcrun not available")

    sdk = subprocess.run(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if sdk.returncode != 0:
        raise AssertionError(sdk.stderr or sdk.stdout)

    source = tmp_path / "frame_provider_client_buffer_smoke.mm"
    binary = tmp_path / "frame_provider_client_buffer_smoke"
    source.write_text(
        textwrap.dedent(
            """
            #import <CoreMedia/CoreMedia.h>
            #import <CoreMediaIO/CoreMediaIO.h>
            #import <CoreVideo/CoreVideo.h>
            #import <Foundation/Foundation.h>

            #import "AKVCFrameProvider.h"

            static CMSampleBufferRef CreateClientSampleBuffer(void) {
                NSDictionary* attributes = @{
                    (NSString*)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA),
                    (NSString*)kCVPixelBufferWidthKey: @1280,
                    (NSString*)kCVPixelBufferHeightKey: @720,
                    (NSString*)kCVPixelBufferIOSurfacePropertiesKey: @{},
                };

                CVPixelBufferRef pixelBuffer = nil;
                CVReturn pixelStatus = CVPixelBufferCreate(
                    kCFAllocatorDefault,
                    1280,
                    720,
                    kCVPixelFormatType_32BGRA,
                    (__bridge CFDictionaryRef)attributes,
                    &pixelBuffer
                );
                if (pixelStatus != kCVReturnSuccess || pixelBuffer == nil) {
                    return nil;
                }

                CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, 0);
                if (lockStatus != kCVReturnSuccess) {
                    CFRelease(pixelBuffer);
                    return nil;
                }

                uint8_t* baseAddress = (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
                if (baseAddress == nil) {
                    CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
                    CFRelease(pixelBuffer);
                    return nil;
                }

                memset(baseAddress, 0x00, CVPixelBufferGetBytesPerRow(pixelBuffer) * CVPixelBufferGetHeight(pixelBuffer));
                baseAddress[0] = 0xAB;
                baseAddress[3] = 0xFF;
                CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);

                CMVideoFormatDescriptionRef formatDescription = nil;
                OSStatus formatStatus = CMVideoFormatDescriptionCreateForImageBuffer(
                    kCFAllocatorDefault,
                    pixelBuffer,
                    &formatDescription
                );
                if (formatStatus != noErr || formatDescription == nil) {
                    CFRelease(pixelBuffer);
                    return nil;
                }

                CMSampleTimingInfo timing = {
                    .duration = CMTimeMake(1, 60),
                    .presentationTimeStamp = CMTimeMake(3, 60),
                    .decodeTimeStamp = kCMTimeInvalid,
                };
                CMSampleBufferRef sampleBuffer = nil;
                OSStatus sampleStatus = CMSampleBufferCreateReadyWithImageBuffer(
                    kCFAllocatorDefault,
                    pixelBuffer,
                    formatDescription,
                    &timing,
                    &sampleBuffer
                );
                CFRelease(formatDescription);
                CFRelease(pixelBuffer);
                if (sampleStatus != noErr) {
                    return nil;
                }
                return sampleBuffer;
            }

            static int VerifyClientSampleBuffer(CMSampleBufferRef sampleBuffer) {
                if (sampleBuffer == nil) {
                    return 30;
                }

                CVImageBufferRef imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer);
                if (imageBuffer == nil) {
                    return 31;
                }

                CVPixelBufferRef pixelBuffer = (CVPixelBufferRef)imageBuffer;
                if (CVPixelBufferGetWidth(pixelBuffer) != 1280) {
                    return 32;
                }
                if (CVPixelBufferGetHeight(pixelBuffer) != 720) {
                    return 33;
                }
                if (CVPixelBufferGetPixelFormatType(pixelBuffer) != kCVPixelFormatType_32BGRA) {
                    return 34;
                }
                if (CMTimeCompare(CMSampleBufferGetDuration(sampleBuffer), CMTimeMake(1, 60)) != 0) {
                    return 35;
                }

                CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                if (lockStatus != kCVReturnSuccess) {
                    return 36;
                }

                uint8_t* baseAddress = (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
                if (baseAddress == nil) {
                    CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                    return 37;
                }

                uint8_t firstByte = baseAddress[0];
                CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                if (firstByte != 0xAB) {
                    return 38;
                }
                return 0;
            }

            int main(void) {
                @autoreleasepool {
                    AKVCFrameProvider* frameProvider =
                        [[AKVCFrameProvider alloc] initWithSharedMemoryName:@"/akvc-client-smoke"
                                                                   slotCount:4
                                                                    slotSize:4096];
                    CMSampleBufferRef inputSampleBuffer = CreateClientSampleBuffer();
                    if (inputSampleBuffer == nil) {
                        return 50;
                    }

                    [frameProvider storeClientSampleBuffer:inputSampleBuffer
                                              discontinuity:CMIOExtensionStreamDiscontinuityFlagTime];
                    CFRelease(inputSampleBuffer);

                    NSError* error = nil;
                    CMIOExtensionStreamDiscontinuityFlags discontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
                    CMSampleBufferRef firstSampleBuffer =
                        [frameProvider copyLatestClientSampleBufferWithDiscontinuity:&discontinuity error:&error];
                    int firstCheck = VerifyClientSampleBuffer(firstSampleBuffer);
                    if (firstSampleBuffer != nil) {
                        CFRelease(firstSampleBuffer);
                    }
                    if (firstCheck != 0 || error != nil || discontinuity != CMIOExtensionStreamDiscontinuityFlagTime) {
                        return firstCheck != 0 ? firstCheck : 11;
                    }

                    discontinuity = CMIOExtensionStreamDiscontinuityFlagUnknown;
                    error = nil;
                    CMSampleBufferRef secondSampleBuffer =
                        [frameProvider copyLatestClientSampleBufferWithDiscontinuity:&discontinuity error:&error];
                    if (secondSampleBuffer != nil) {
                        CFRelease(secondSampleBuffer);
                        return 12;
                    }
                    if (error != nil) {
                        return 13;
                    }
                    if (discontinuity != CMIOExtensionStreamDiscontinuityFlagNone) {
                        return 14;
                    }

                    return 0;
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "clang++",
            "-std=gnu++20",
            "-fobjc-arc",
            "-x",
            "objective-c++",
            "-isysroot",
            sdk.stdout.strip(),
            "-mmacosx-version-min=13.0",
            "-I",
            str(MACOS_ROOT / "ipc" / "include"),
            "-I",
            str(ROOT / "virtualcam" / "shared"),
            "-I",
            str(MACOS_ROOT / "camera_extension"),
            str(source),
            str(MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm"),
            str(MACOS_ROOT / "ipc" / "src" / "macos_ipc.cpp"),
            str(MACOS_ROOT / "ipc" / "src" / "framebus_posix.c"),
            "-framework",
            "Foundation",
            "-framework",
            "CoreMedia",
            "-framework",
            "CoreMediaIO",
            "-framework",
            "CoreVideo",
            "-framework",
            "AVFoundation",
            "-o",
            str(binary),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)

    executed = subprocess.run(
        [str(binary)],
        cwd=str(ROOT),
        env={
            **dict(os.environ),
            "AKVC_MACOS_SHARED_STATE_DIR": str(tmp_path / "akvc-shared"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if executed.returncode == 50:
        pytest.skip("current macOS environment does not support the frame-provider client-buffer smoke path")
    if executed.returncode != 0:
        raise AssertionError(
            f"frame provider consume-once smoke failed with exit {executed.returncode}: "
            f"{executed.stderr or executed.stdout}"
        )


def test_macos_demo_mode_bridge_contract_is_present() -> None:
    project_yml = (MACOS_ROOT / "project.yml").read_text(encoding="utf-8")
    host_header = (MACOS_ROOT / "control_bridge" / "AKVCCommandSupport.h").read_text(encoding="utf-8")
    host_support = (MACOS_ROOT / "control_bridge" / "AKVCCommandSupport.mm").read_text(encoding="utf-8")
    demo_app_main = (MACOS_ROOT / "demo_app" / "main.mm").read_text(encoding="utf-8")
    demo_app_delegate_header = (MACOS_ROOT / "demo_app" / "AppDelegate.h").read_text(encoding="utf-8")
    demo_app_delegate_impl = (MACOS_ROOT / "demo_app" / "AppDelegate.mm").read_text(encoding="utf-8")
    demo_control_service = (MACOS_ROOT / "demo_app" / "DemoControlService.mm").read_text(encoding="utf-8")
    macos_ipc_header = (MACOS_ROOT / "ipc" / "include" / "akvc" / "macos_ipc.h").read_text(encoding="utf-8")
    macos_ipc_impl = (MACOS_ROOT / "ipc" / "src" / "macos_ipc.cpp").read_text(encoding="utf-8")
    provider_header = (MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.h").read_text(encoding="utf-8")
    provider_impl = (MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm").read_text(encoding="utf-8")
    provider_source = (MACOS_ROOT / "camera_extension" / "AKVCProviderSource.mm").read_text(encoding="utf-8")
    stream_source = (MACOS_ROOT / "camera_extension" / "AKVCStreamSource.mm").read_text(encoding="utf-8")

    assert "AKVC_MACOS_DEMO_MODE_FILE_NAME" in macos_ipc_header
    assert "AKVC_MACOS_DEMO_MODE_FILE_ENV" in macos_ipc_header
    assert "AKVC_MACOS_DEMO_MODE_ENV" in macos_ipc_header
    assert "akvc_macos_demo_mode_enabled" in macos_ipc_header
    assert "akvc_macos_demo_mode_enabled" in macos_ipc_impl
    assert 'AKVC_MACOS_APP_GROUP_IDENTIFIER "group.com.sidus.amaran-desktop"' in macos_ipc_header
    assert 'AKVC_MACOS_SHARED_STATE_DIR_ENV "AKVC_MACOS_SHARED_STATE_DIR"' in macos_ipc_header
    assert 'AKVC_MACOS_SHARED_STATE_DIR_SUFFIX "Library/Group Containers/group.com.sidus.amaran-desktop/akvc-shared"' in macos_ipc_header
    assert 'AKVC_MACOS_SHARED_STATE_DIR_ENV' in macos_ipc_impl
    assert 'AKVC_MACOS_SHARED_STATE_DIR_SUFFIX' in macos_ipc_impl
    assert 'return std::string("/private/tmp/akvc-shared");' in macos_ipc_impl

    assert "AKVCSetDemoModeEnabled" in host_header
    assert "AKVCSetDemoModeEnabled" in host_support
    assert 'AKVC_MACOS_SHARED_STATE_DIR' in host_support
    assert "[NSApplication sharedApplication]" in demo_app_main
    assert "AppDelegate" in demo_app_main
    assert "NSApplicationMain" in demo_app_main
    assert "AKVCSetDemoModeEnabled(YES, outError)" in demo_control_service
    assert "AKVCSubmitSystemExtensionRequest(YES, 30.0, outError)" in demo_control_service
    assert "NSApplicationDelegate" in demo_app_delegate_header
    assert "MainWindowController" in demo_app_delegate_impl
    assert "applicationDidFinishLaunching" in demo_app_delegate_impl
    assert "[self.mainWindowController showWindow:self]" in demo_app_delegate_impl
    assert "[NSApp activateIgnoringOtherApps:YES]" in demo_app_delegate_impl

    assert "AKVCSampleBufferSource" in provider_header
    assert "updatePreferredWidth" in provider_header
    assert "setFallbackSampleBufferSource" in provider_header
    assert "copyFallbackSampleBuffer" in provider_header
    assert "setFallbackSampleBufferSource" in provider_impl
    assert "copyFallbackSampleBuffer" in provider_impl
    assert "synchronizeFallbackSampleBufferSourceToActiveFormat" in provider_impl
    assert "ensureFormatForClientSampleBuffer" in provider_impl
    assert "akvc_macos_demo_mode_enabled() != 0" in provider_impl
    assert "CVPixelBufferLockBaseAddress(pixelBuffer, 0)" in provider_impl
    assert "CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) == NULL" in provider_impl

    assert "AKVCDemoFrameGenerator" in provider_source
    assert "setFallbackSampleBufferSource" in provider_source
    assert "demo_support/AKVCDemoFrameGenerator.mm" in project_yml

    assert "copyFallbackSampleBuffer" in stream_source


def test_macos_demo_host_doc_removed_after_container_app_consolidation() -> None:
    assert not (ROOT / "docs" / "macos" / "demo_host.md").exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only demo bridge smoke test")
def test_macos_demo_mode_bridge_runtime_contract(tmp_path) -> None:
    if shutil.which("clang++") is None or shutil.which("xcrun") is None:
        pytest.skip("clang++/xcrun not available")

    sdk = subprocess.run(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if sdk.returncode != 0:
        raise AssertionError(sdk.stderr or sdk.stdout)

    source = tmp_path / "demo_mode_bridge_smoke.mm"
    binary = tmp_path / "demo_mode_bridge_smoke"
    source.write_text(
        textwrap.dedent(
            """
            #import <CoreMedia/CoreMedia.h>
            #import <CoreVideo/CoreVideo.h>
            #import <CoreMediaIO/CoreMediaIO.h>
            #import <Foundation/Foundation.h>

            #include "akvc/macos_ipc.h"

            #import "AKVCCommandSupport.h"
            #import "AKVCFrameProvider.h"
            #import "AKVCDemoFrameGenerator.h"

            static NSUInteger FindFormatIndex(
                AKVCFrameProvider* frameProvider,
                uint32_t width,
                uint32_t height,
                OSType pixelFormat
            ) {
                for (NSUInteger index = 0; index < frameProvider.streamFormats.count; ++index) {
                    CMIOExtensionStreamFormat* format = frameProvider.streamFormats[index];
                    CMVideoDimensions dimensions =
                        CMVideoFormatDescriptionGetDimensions((CMVideoFormatDescriptionRef)format.formatDescription);
                    OSType candidatePixelFormat =
                        CMFormatDescriptionGetMediaSubType((CMFormatDescriptionRef)format.formatDescription);
                    if ((uint32_t)dimensions.width == width
                        && (uint32_t)dimensions.height == height
                        && candidatePixelFormat == pixelFormat) {
                        return index;
                    }
                }
                return NSNotFound;
            }

            static int VerifyBufferDimensions(
                CMSampleBufferRef sampleBuffer,
                uint32_t expectedWidth,
                uint32_t expectedHeight,
                OSType expectedPixelFormat,
                uint8_t* outFirstByte
            ) {
                if (sampleBuffer == nil) {
                    return 50;
                }
                CVImageBufferRef imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer);
                if (imageBuffer == nil) {
                    return 51;
                }
                CVPixelBufferRef pixelBuffer = (CVPixelBufferRef)imageBuffer;
                if (CVPixelBufferGetWidth(pixelBuffer) != expectedWidth) {
                    return 52;
                }
                if (CVPixelBufferGetHeight(pixelBuffer) != expectedHeight) {
                    return 53;
                }
                if (CVPixelBufferGetPixelFormatType(pixelBuffer) != expectedPixelFormat) {
                    return 54;
                }
                CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                if (lockStatus != kCVReturnSuccess) {
                    return 55;
                }
                size_t planeCount = CVPixelBufferGetPlaneCount(pixelBuffer);
                uint8_t* baseAddress = planeCount >= 1
                    ? (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0)
                    : (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
                if (baseAddress == nil) {
                    CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                    return 56;
                }
                *outFirstByte = baseAddress[0];
                CVPixelBufferUnlockBaseAddress(pixelBuffer, kCVPixelBufferLock_ReadOnly);
                return 0;
            }

            int main(void) {
                @autoreleasepool {
                    NSError* error = nil;
                    if (!AKVCSetDemoModeEnabled(YES, &error)) {
                        return 10;
                    }
                    if (akvc_macos_demo_mode_enabled() != 1) {
                        return 11;
                    }

                    AKVCFrameProvider* frameProvider =
                        [[AKVCFrameProvider alloc] initWithSharedMemoryName:@"/akvc-demo-smoke"
                                                                   slotCount:4
                                                                    slotSize:4096];
                    AKVCDemoFrameGenerator* generator =
                        [[AKVCDemoFrameGenerator alloc] initWithWidth:1280 height:720];
                    [frameProvider setFallbackSampleBufferSource:(id<AKVCSampleBufferSource>)generator];

                    NSUInteger bgraFormatIndex =
                        FindFormatIndex(frameProvider, 1280, 720, kCVPixelFormatType_32BGRA);
                    if (bgraFormatIndex == NSNotFound) {
                        return 12;
                    }
                    if (![frameProvider selectFormatAtIndex:bgraFormatIndex error:&error]) {
                        return 13;
                    }

                    uint8_t demoFirstByte = 0;
                    CMSampleBufferRef firstSampleBuffer = [frameProvider copyFallbackSampleBuffer:&error];
                    int firstCheck = VerifyBufferDimensions(
                        firstSampleBuffer,
                        1280,
                        720,
                        kCVPixelFormatType_32BGRA,
                        &demoFirstByte
                    );
                    if (firstSampleBuffer != nil) {
                        CFRelease(firstSampleBuffer);
                    }
                    if (firstCheck != 0 || error != nil || demoFirstByte != 0x10) {
                        return firstCheck != 0 ? firstCheck : 14;
                    }

                    if (!AKVCSetDemoModeEnabled(NO, &error)) {
                        return 15;
                    }
                    if (akvc_macos_demo_mode_enabled() != 0) {
                        return 16;
                    }

                    uint8_t placeholderFirstByte = 0;
                    CMSampleBufferRef placeholderSampleBuffer = [frameProvider copyFallbackSampleBuffer:&error];
                    int placeholderCheck = VerifyBufferDimensions(
                        placeholderSampleBuffer,
                        1280,
                        720,
                        kCVPixelFormatType_32BGRA,
                        &placeholderFirstByte
                    );
                    if (placeholderSampleBuffer != nil) {
                        CFRelease(placeholderSampleBuffer);
                    }
                    if (placeholderCheck != 0 || error != nil || placeholderFirstByte != 0x00) {
                        return placeholderCheck != 0 ? placeholderCheck : 17;
                    }

                    if (!AKVCSetDemoModeEnabled(YES, &error)) {
                        return 18;
                    }
                    if (akvc_macos_demo_mode_enabled() != 1) {
                        return 19;
                    }

                    NSUInteger nv12FormatIndex =
                        FindFormatIndex(frameProvider, 1920, 1080, kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange);
                    if (nv12FormatIndex == NSNotFound) {
                        return 20;
                    }
                    if (![frameProvider selectFormatAtIndex:nv12FormatIndex error:&error]) {
                        return 21;
                    }

                    uint8_t nv12FirstByte = 0;
                    CMSampleBufferRef secondSampleBuffer = [frameProvider copyFallbackSampleBuffer:&error];
                    int secondCheck = VerifyBufferDimensions(
                        secondSampleBuffer,
                        1920,
                        1080,
                        kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
                        &nv12FirstByte
                    );
                    if (secondSampleBuffer != nil) {
                        CFRelease(secondSampleBuffer);
                    }
                    if (secondCheck != 0 || error != nil) {
                        return secondCheck != 0 ? secondCheck : 22;
                    }

                    return 0;
                }
            }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "clang++",
            "-std=gnu++20",
            "-fobjc-arc",
            "-x",
            "objective-c++",
            "-isysroot",
            sdk.stdout.strip(),
            "-mmacosx-version-min=13.0",
            "-I",
            str(MACOS_ROOT / "ipc" / "include"),
            "-I",
            str(ROOT / "virtualcam" / "shared"),
            "-I",
            str(MACOS_ROOT / "control_bridge"),
            "-I",
            str(MACOS_ROOT / "camera_extension"),
            "-I",
            str(MACOS_ROOT / "demo_support"),
            str(source),
            str(MACOS_ROOT / "control_bridge" / "AKVCCommandSupport.mm"),
            str(MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm"),
            str(MACOS_ROOT / "demo_support" / "AKVCDemoFrameGenerator.mm"),
            str(MACOS_ROOT / "ipc" / "src" / "macos_ipc.cpp"),
            str(MACOS_ROOT / "ipc" / "src" / "framebus_posix.c"),
            "-framework",
            "Foundation",
            "-framework",
            "CoreMedia",
            "-framework",
            "CoreMediaIO",
            "-framework",
            "CoreVideo",
            "-framework",
            "AVFoundation",
            "-o",
            str(binary),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)

    executed = subprocess.run(
        [str(binary)],
        cwd=str(ROOT),
        env={
            **dict(os.environ),
            "AKVC_MACOS_SHARED_STATE_DIR": str(tmp_path / "akvc-shared"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if executed.returncode == 50:
        pytest.skip("current macOS environment does not support the frame-provider demo bridge smoke path")
    if executed.returncode != 0:
        raise AssertionError(
            f"demo mode bridge smoke failed with exit {executed.returncode}: "
            f"{executed.stderr or executed.stdout}"
        )
    assert (
        tmp_path
        / "akvc-shared"
        / "akvc-macos-demo-mode.txt"
    ).is_file()


def test_macos_status_tool_skeleton_emits_installer_bridge_shape() -> None:
    status_tool = (MACOS_ROOT / "control_bridge" / "akvc_macos_status.mm").read_text(encoding="utf-8")
    install_tool = (MACOS_ROOT / "control_bridge" / "akvc_macos_install.mm").read_text(encoding="utf-8")
    list_devices_tool = (MACOS_ROOT / "control_bridge" / "akvc_macos_list_devices.mm").read_text(encoding="utf-8")
    support = (MACOS_ROOT / "control_bridge" / "AKVCCommandSupport.mm").read_text(encoding="utf-8")
    system_ext_support = (MACOS_ROOT / "control_bridge" / "AKVCSystemExtensionSupport.mm").read_text(encoding="utf-8")

    assert "AKVCDefaultStatusPayload" in support
    assert '@"state": @"not_installed"' in support
    assert '@"devices": @[]' in support
    assert '@"bundle_path"' in support
    assert '@"shared_memory_name"' in support
    assert "3840x2160@30/60 NV12" in support
    assert '@"ipc_transport"' in support
    assert '@"ipc_probe_present"' in support
    assert '@"ipc_ready"' in support
    assert '@"ipc_environment_blocked"' in support
    assert '@"ipc_last_error"' in support
    assert '@"ipc_probe_path"' in support
    assert '@"ipc_direct_open_errno"' in support
    assert "AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON" in support
    assert "build/macos/framebus-roundtrip.json" in support
    assert "build/macos/session/framebus-roundtrip.json" in support
    assert "build/macos/validation/framebus-roundtrip.json" in support
    assert "AKVCResolvedBundleExecutablePath" in support
    assert "CFBundleExecutable" in support
    assert "contentsOfDirectoryAtPath:macOSDirectory" in support
    assert "NSJSONSerialization JSONObjectWithData" in support
    assert "framebus roundtrip report is unreadable" in support
    assert "AKVCPersistSharedMemoryNameOverrideFromEnvironment" in support
    assert "AKVC_MACOS_SHM_NAME_ENV" in support
    assert "AKVC_MACOS_SHM_NAME_FILE_ENV" in support
    assert "AKVC_MACOS_DEVICE_NAME_ENV" in support
    assert "AKVC_MACOS_DEVICE_NAME_FILE_ENV" in support
    assert "AKVCDefaultSharedMemoryNameOverridePath" in support
    assert "AKVCDefaultDeviceNameOverridePath" in support
    assert "AKVCPersistDeviceNameOverrideFromEnvironment" in support
    assert "createDirectoryAtPath:directoryPath" in support
    assert "writeToFile:destinationPath" in support
    assert "NSUTF8StringEncoding" in support
    assert "AKVCVideoDeviceSnapshot" in support
    assert "AKVCEnumeratedVideoDevices" in support
    assert "AVCaptureDeviceDiscoverySession" in support
    assert "AKVCDefaultDevicePrefix" in support
    assert "AKVCQuerySystemExtensionStatus" in status_tool
    assert "AKVCQuerySystemExtensionStatus" in install_tool
    assert "AKVCInstallStatusConverged" in install_tool
    assert "AKVCPollInstallStatusUntilDeadline" in install_tool
    assert "AKVCLaunchHostAgent(@[@\"--activate\"]" in install_tool
    assert "BOOL launchedHost = AKVCLaunchHostAgent" in install_tool
    assert "AKVCSubmitSystemExtensionRequest(YES" not in install_tool
    assert '@"system extension status query timed out"' in install_tool
    assert "return NO;" in install_tool
    uninstall_tool = (MACOS_ROOT / "control_bridge" / "akvc_macos_uninstall.mm").read_text(encoding="utf-8")
    assert "AKVCUninstallStatusConverged" in uninstall_tool
    assert "AKVCPollUninstallStatusUntilDeadline" in uninstall_tool
    assert "AKVCQuerySystemExtensionStatus" in uninstall_tool
    assert "AKVCLaunchHostAgent(@[@\"--deactivate\"]" in uninstall_tool
    assert "BOOL launchedHost = AKVCLaunchHostAgent" in uninstall_tool
    assert "AKVCSubmitSystemExtensionRequest(NO" not in uninstall_tool
    assert '@"system extension status query timed out"' in uninstall_tool
    assert '[NSThread sleepForTimeInterval:0.25];' in uninstall_tool
    assert '@"timed out waiting for extension deactivation"' in uninstall_tool
    assert '[NSThread sleepForTimeInterval:0.25];' in install_tool
    assert '@"state"] = @"install_pending_approval"' in install_tool
    assert "AKVCVideoDeviceSnapshot" in list_devices_tool
    assert "propertiesRequestForExtension" in system_ext_support
    assert "AKVCStatusQueryErrorIndicatesMissingExtension" in system_ext_support
    assert "OSSystemExtensionErrorExtensionNotFound" in system_ext_support
    assert "OSSystemExtensionErrorUnknown" in system_ext_support
    assert "dispatch_semaphore_create(0)" in system_ext_support
    assert "dispatch_semaphore_wait" in system_ext_support
    assert 'dispatch_queue_create("com.sidus.amaran-desktop.system-extension"' in system_ext_support
    assert "AKVCSubmitSystemExtensionRequestAsync" in system_ext_support
    assert "AKVCRetainSystemExtensionRunner" in system_ext_support
    assert "AKVCReleaseSystemExtensionRunner" in system_ext_support
    assert 'NSProcessInfo.processInfo.environment[@"AKVC_CONTAINER_APP_EXECUTABLE"]' in system_ext_support
    assert 'task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/open"];' in system_ext_support
    assert '[openArguments addObject:@"--args"];' in system_ext_support
    assert "fall back to the direct executable launch path" in system_ext_support
    assert "bundleLaunchError" in system_ext_support
    assert "failed to launch container app bundle" in system_ext_support
    assert '@"container app executable not found"' in system_ext_support
    assert "AKVCSubmitSystemExtensionRequest" in system_ext_support
    assert 'payload[@"state"] = @"installed";' in system_ext_support
    assert 'payload[@"devices"] = @[@"AK Virtual Camera"];' not in system_ext_support
    assert 'payload[@"devices"] = deviceSnapshot[@"devices"] ?: @[];' in system_ext_support
    assert 'payload[@"all_devices"] = deviceSnapshot[@"all_devices"] ?: @[];' in system_ext_support
    assert 'payload[@"device_prefix"] = deviceSnapshot[@"device_prefix"] ?: AKVCDevicePrefix();' in system_ext_support


def test_macos_demo_app_entitlements_include_system_extension_install_capability() -> None:
    entitlements = (MACOS_ROOT / "demo_app" / "DemoApp.entitlements").read_text(encoding="utf-8")

    assert "com.apple.developer.system-extension.install" in entitlements
    assert "com.apple.security.app-sandbox" in entitlements
    assert "com.apple.security.application-groups" in entitlements
    assert "group.com.sidus.amaran-desktop" in entitlements
    assert "com.apple.security.device.camera" in entitlements


def test_macos_camera_extension_entitlements_include_app_group_and_camera_access() -> None:
    entitlements = (MACOS_ROOT / "camera_extension" / "CameraExtension.entitlements").read_text(
        encoding="utf-8"
    )

    assert "<dict>" in entitlements
    assert "com.apple.security.app-sandbox" in entitlements
    assert "com.apple.security.application-groups" in entitlements
    assert "group.com.sidus.amaran-desktop" in entitlements
    assert "com.apple.security.device.camera" in entitlements


def test_macos_camera_extension_info_plist_declares_group_prefixed_mach_service() -> None:
    info_plist = (MACOS_ROOT / "camera_extension" / "Info.plist").read_text(encoding="utf-8")

    assert "CMIOExtensionMachServiceName" in info_plist
    assert "group.com.sidus.amaran-desktop.cameraextension" in info_plist
    assert "NSExtensionPointIdentifier" not in info_plist
    assert "com.apple.coremediaio.extension" not in info_plist


def test_macos_camera_extension_sources_conform_to_cmio_protocols() -> None:
    provider_h = (MACOS_ROOT / "camera_extension" / "AKVCProviderSource.h").read_text(encoding="utf-8")
    extension_main = (MACOS_ROOT / "camera_extension" / "main.mm").read_text(encoding="utf-8")
    device_h = (MACOS_ROOT / "camera_extension" / "AKVCDeviceSource.h").read_text(encoding="utf-8")
    stream_h = (MACOS_ROOT / "camera_extension" / "AKVCStreamSource.h").read_text(encoding="utf-8")
    stream_mm = (MACOS_ROOT / "camera_extension" / "AKVCStreamSource.mm").read_text(encoding="utf-8")
    sink_stream_h = (MACOS_ROOT / "camera_extension" / "AKVCSinkStreamSource.h").read_text(encoding="utf-8")
    sink_stream_mm = (MACOS_ROOT / "camera_extension" / "AKVCSinkStreamSource.mm").read_text(encoding="utf-8")
    direct_sender_mm = (MACOS_ROOT / "direct_sender" / "AKVCDirectCameraSender.mm").read_text(encoding="utf-8")
    frame_provider_mm = (MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm").read_text(encoding="utf-8")
    framebus_h = (MACOS_ROOT / "ipc" / "include" / "akvc" / "framebus_posix.h").read_text(encoding="utf-8")
    framebus_c = (MACOS_ROOT / "ipc" / "src" / "framebus_posix.c").read_text(encoding="utf-8")
    macos_ipc_h = (MACOS_ROOT / "ipc" / "include" / "akvc" / "macos_ipc.h").read_text(encoding="utf-8")
    macos_ipc_cpp = (MACOS_ROOT / "ipc" / "src" / "macos_ipc.cpp").read_text(encoding="utf-8")

    assert "CMIOExtensionProviderSource" in provider_h
    assert "CMIOExtensionProvider" in extension_main
    assert "AKVCProviderSource" in extension_main
    assert "startServiceWithProvider" in extension_main
    assert "CFRunLoopRun" in extension_main
    assert "NSExtensionMain" not in extension_main
    assert "CMIOExtensionDeviceSource" in device_h
    assert "CMIOExtensionStreamSource" in stream_h
    assert "CMIOExtensionStreamSource" in sink_stream_h
    assert "sendSampleBuffer" in stream_mm
    assert "copyNextSampleBufferWithStatus" in stream_mm
    assert "copyLatestClientSampleBufferWithDiscontinuity" in stream_mm
    assert "CMIOExtensionStreamDiscontinuityFlagNone" in stream_mm
    assert "AKVCFrameReadStatusTimedOut" in stream_mm
    assert "AKVCFrameReadStatusTorn" in stream_mm
    assert "copyFallbackSampleBuffer" in stream_mm
    assert "consumeSampleBufferFromClient" in sink_stream_mm
    assert "CMIOExtensionPropertyStreamSinkBufferQueueSize" in sink_stream_mm
    assert "storeClientSampleBuffer" in sink_stream_mm
    assert "devicesWithMediaType:AVMediaTypeVideo" in direct_sender_mm
    assert "AKVCCopyCMIOObjectName" in direct_sender_mm
    assert 'localizedCaseInsensitiveContainsString:@"sink"' in direct_sender_mm
    assert "0 = output stream and 1 = input stream" in direct_sender_mm
    assert 'return @"source-output";' in direct_sender_mm
    assert 'return @"sink-input";' in direct_sender_mm
    assert '[direction isEqualToString:@"sink-input"]' in direct_sender_mm
    assert "AKVCPresentationTimeFromPTS100ns" in direct_sender_mm
    assert "CMTimeMake(pts_value, 10000000)" in direct_sender_mm
    assert "CMIODeviceStopStream(device_id_, sink_stream_)" in direct_sender_mm
    assert "CFRelease(sink_queue_)" in direct_sender_mm
    assert "CMSimpleQueueGetCount(sink_queue_) >= capacity" in direct_sender_mm
    assert "CMSimpleQueueDequeue(sink_queue_)" in direct_sender_mm
    assert "3840, 2160" in frame_provider_mm
    assert "CMTimeMake(1, 60)" in frame_provider_mm
    assert "CMTimeMake(1, 30)" in frame_provider_mm
    assert "kCVPixelFormatType_32BGRA" in frame_provider_mm
    assert "akvc_fb_open" in frame_provider_mm
    assert "akvc_fb_open_named" in frame_provider_mm
    assert "refreshSharedMemoryConfigurationIfNeeded" in frame_provider_mm
    assert "akvc_macos_ring_descriptor_default(&descriptor);" in frame_provider_mm
    assert "currentSharedMemoryName" in frame_provider_mm
    assert "![currentSharedMemoryName isEqualToString:self.sharedMemoryName]" in frame_provider_mm
    assert "[self closeFrameReader];" in frame_provider_mm
    assert "_pendingConfigurationDiscontinuity = YES;" in frame_provider_mm
    assert "_pendingConfigurationDiscontinuity = NO;" in frame_provider_mm
    assert "storeClientSampleBuffer" in frame_provider_mm
    assert "copyLatestClientSampleBufferWithDiscontinuity" in frame_provider_mm
    assert "self.sharedMemoryName.UTF8String" in frame_provider_mm
    assert "copySampleBufferFromView" in frame_provider_mm
    assert "memset(base, 0x10" in frame_provider_mm
    assert "memset(base, 0x80" in frame_provider_mm
    assert "CMIOExtensionStreamDiscontinuityFlagTime" in frame_provider_mm
    assert "CMIOExtensionStreamDiscontinuityFlagSampleDropped" in frame_provider_mm
    assert "CMIOExtensionStreamDiscontinuityFlagUnknown" in frame_provider_mm
    assert "akvc_fb_poll" in framebus_h
    assert "akvc_fb_consumer_count" in framebus_h
    assert "akvc_fb_open_named" in framebus_h
    assert "const char* shm_name" in framebus_h
    assert "akvc_status_t akvc_fb_open_named(akvc_fb_consumer_t** out, const char* shm_name)" in framebus_c
    assert "const char* resolved_name = shm_name;" in framebus_c
    assert 'AKVC_MACOS_APP_GROUP_IDENTIFIER "group.com.sidus.amaran-desktop"' in macos_ipc_h
    assert 'AKVC_MACOS_SHARED_STATE_DIR_ENV "AKVC_MACOS_SHARED_STATE_DIR"' in macos_ipc_h
    assert 'AKVC_MACOS_SHARED_STATE_DIR_SUFFIX "Library/Group Containers/group.com.sidus.amaran-desktop/akvc-shared"' in macos_ipc_h
    assert 'AKVC_MACOS_SHM_NAME_FILE_ENV "AKVC_MACOS_SHM_NAME_FILE"' in macos_ipc_h
    assert 'AKVC_MACOS_SHM_NAME_FILE_NAME "akvc-macos-shm-name.txt"' in macos_ipc_h
    assert 'AKVC_MACOS_SHM_NAME_ENV "AKVC_MACOS_SHM_NAME"' in macos_ipc_h
    assert 'AKVC_MACOS_DEVICE_NAME_FILE_ENV "AKVC_DEVICE_NAME_FILE"' in macos_ipc_h
    assert 'AKVC_MACOS_DEVICE_NAME_FILE_NAME "akvc-macos-device-name.txt"' in macos_ipc_h
    assert 'AKVC_MACOS_DEVICE_NAME_ENV "AKVC_DEVICE_NAME"' in macos_ipc_h
    assert "const char* akvc_macos_resolved_device_name(void);" in macos_ipc_h
    assert "std::getenv(AKVC_MACOS_SHM_NAME_ENV)" in macos_ipc_cpp
    assert "std::getenv(AKVC_MACOS_SHM_NAME_FILE_ENV)" in macos_ipc_cpp
    assert "std::getenv(AKVC_MACOS_DEVICE_NAME_ENV)" in macos_ipc_cpp
    assert "std::getenv(AKVC_MACOS_DEVICE_NAME_FILE_ENV)" in macos_ipc_cpp
    assert "akvc_macos_default_device_name_file_path" in macos_ipc_cpp
    assert 'stat("/dev/console", &console_stat)' in macos_ipc_cpp
    assert "getpwuid(console_stat.st_uid)" in macos_ipc_cpp
    assert 'return "AK Virtual Camera";' in macos_ipc_cpp
    assert "AKVC_MACOS_SHARED_STATE_DIR" in macos_ipc_cpp
    assert "std::ifstream stream(path);" in macos_ipc_cpp
    assert "std::getline(stream, line);" in macos_ipc_cpp
    assert "candidate[0] != '/'" in macos_ipc_cpp
    assert "std::strncpy(out_desc->shm_name, akvc_macos_resolved_shm_name()" in macos_ipc_cpp
    assert "__sync_add_and_fetch" in framebus_c
    assert "__sync_sub_and_fetch" in framebus_c
    assert "E_AKVC_FRAMEBUS_TORN_FRAME" in framebus_c


def test_macos_frame_provider_synchronization_contract_is_present() -> None:
    frame_provider_mm = (MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm").read_text(encoding="utf-8")

    select_format_block = _objective_c_method_block(frame_provider_mm, "- (BOOL)selectFormatAtIndex:")
    select_frame_duration_block = _objective_c_method_block(frame_provider_mm, "- (BOOL)selectFrameDuration:")
    close_reader_block = _objective_c_method_block(frame_provider_mm, "- (void)closeFrameReader")
    store_client_block = _objective_c_method_block(frame_provider_mm, "- (void)storeClientSampleBuffer:")
    copy_latest_block = _objective_c_method_block(
        frame_provider_mm, "- (CMSampleBufferRef)copyLatestClientSampleBufferWithDiscontinuity:"
    )
    copy_next_block = _objective_c_method_block(frame_provider_mm, "- (CMSampleBufferRef)copyNextSampleBufferWithStatus:")
    copy_fallback_block = _objective_c_method_block(frame_provider_mm, "- (CMSampleBufferRef)copyFallbackSampleBuffer:")
    copy_placeholder_block = _objective_c_method_block(
        frame_provider_mm, "- (CMSampleBufferRef)copyPlaceholderSampleBuffer:"
    )
    sync_fallback_block = _objective_c_method_block(
        frame_provider_mm, "- (void)synchronizeFallbackSampleBufferSourceToActiveFormat"
    )

    for block in (
        select_format_block,
        select_frame_duration_block,
        close_reader_block,
        store_client_block,
        copy_latest_block,
        copy_next_block,
        copy_fallback_block,
        copy_placeholder_block,
        sync_fallback_block,
    ):
        assert "@synchronized(self)" in block

    assert re.search(
        r"if \(outDiscontinuity != nil\) \{\s*\*outDiscontinuity = "
        r"CMIOExtensionStreamDiscontinuityFlagNone;\s*\}\s*if \(_latestClientSampleBuffer == nil\)",
        copy_latest_block,
        re.S,
    )
    assert "CFRelease(_latestClientSampleBuffer);" in copy_latest_block
    assert "_latestClientSampleBuffer = nil;" in copy_latest_block
    assert "_latestClientDiscontinuity = CMIOExtensionStreamDiscontinuityFlagNone;" in copy_latest_block
    assert re.search(
        r"@synchronized\(self\)\s*\{[^}]*format = self\.streamFormats\[self\.activeFormatIndex\];",
        sync_fallback_block,
        re.S,
    )
    assert "CMVideoDimensions dimensions =" in sync_fallback_block
    assert "[fallbackSampleBufferSource updatePreferredWidth:(size_t)dimensions.width" in sync_fallback_block
