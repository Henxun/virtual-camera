// SPDX-License-Identifier: Apache-2.0
#import "DemoControlService.h"

#import "../control_bridge/AKVCCommandSupport.h"
#import "../control_bridge/AKVCSystemExtensionSupport.h"

#include "akvc/macos_ipc.h"

static NSString* const AKVCDemoAppStatusSummaryKey = @"summary";
static NSString* const AKVCDemoAppStatusDemoModeKey = @"demo_mode_enabled";
static NSString* const AKVCDemoAppStatusDeviceCountKey = @"device_count";
@implementation DemoControlService

- (NSDictionary*)refreshStatusWithError:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    NSMutableDictionary* payload =
        [[AKVCQuerySystemExtensionStatus(AKVCCameraExtensionIdentifier(), 5.0) mutableCopy] ?: [NSMutableDictionary dictionary] mutableCopy];
    NSDictionary* deviceSnapshot = AKVCVideoDeviceSnapshot();
    NSArray* devices = [deviceSnapshot[@"devices"] isKindOfClass:NSArray.class] ? deviceSnapshot[@"devices"] : @[];
    NSArray* allDevices = [deviceSnapshot[@"all_devices"] isKindOfClass:NSArray.class] ? deviceSnapshot[@"all_devices"] : @[];
    payload[@"devices"] = devices;
    payload[@"all_devices"] = allDevices;
    payload[@"device_prefix"] = deviceSnapshot[@"device_prefix"] ?: AKVCDevicePrefix();
    payload[AKVCDemoAppStatusDemoModeKey] = @(akvc_macos_demo_mode_enabled() != 0);
    payload[AKVCDemoAppStatusDeviceCountKey] = @(devices.count);
    payload[@"host_executable_path"] = AKVCResolvedHostExecutablePath();
    payload[@"extension_identifier"] = AKVCCameraExtensionIdentifier();
    payload[@"ipc_ready"] = payload[@"ipc_ready"] ?: [NSNull null];
    payload[@"readiness_stage"] = [self readinessStageForPayload:payload];
    payload[@"next_action"] = [self nextActionForPayload:payload];
    payload[AKVCDemoAppStatusSummaryKey] = [self summaryForPayload:payload];
    return payload;
}

- (NSDictionary*)enableDemoAndActivateWithError:(NSError* _Nullable __autoreleasing*)outError {
    if (!AKVCSetDemoModeEnabled(YES, outError)) {
        return @{};
    }
    if (!AKVCSubmitSystemExtensionRequest(YES, 30.0, outError)) {
        return @{};
    }
    return [self refreshStatusWithError:outError];
}

- (NSDictionary*)disableDemoWithError:(NSError* _Nullable __autoreleasing*)outError {
    if (!AKVCSetDemoModeEnabled(NO, outError)) {
        return @{};
    }
    return [self refreshStatusWithError:outError];
}

- (NSString*)manualAcceptanceInstructions {
    return @"1. 点击“启用 Demo 并激活”。\n"
           @"2. 打开 QuickTime，选择“新建影片录制”。\n"
           @"3. 在摄像头列表中查找当前设备名。\n"
           @"4. 确认能看到 demo 画面后，再去 FaceTime / Zoom 验证枚举。";
}

- (NSString*)summaryForPayload:(NSDictionary*)payload {
    BOOL demoModeEnabled = [payload[AKVCDemoAppStatusDemoModeKey] respondsToSelector:@selector(boolValue)]
        ? [payload[AKVCDemoAppStatusDemoModeKey] boolValue]
        : NO;
    NSString* state = [payload[@"state"] isKindOfClass:NSString.class] ? payload[@"state"] : @"not_installed";
    NSNumber* deviceCount = [payload[AKVCDemoAppStatusDeviceCountKey] isKindOfClass:NSNumber.class]
        ? payload[AKVCDemoAppStatusDeviceCountKey]
        : @0;

    if (deviceCount.integerValue > 0) {
        return @"已检测到虚拟摄像头，可前往 QuickTime 验收";
    }
    if ([state isEqualToString:@"install_failed"]) {
        return @"激活链路失败，先处理 host / entitlement / bundle 条件";
    }
    if ([state isEqualToString:@"install_pending_approval"]) {
        return @"已提交激活请求，等待系统批准";
    }
    if ([state isEqualToString:@"installed"] && demoModeEnabled) {
        if ([payload[@"ipc_ready"] isKindOfClass:NSNumber.class]
            && ![(NSNumber*)payload[@"ipc_ready"] boolValue]) {
            return @"扩展已启用，但 IPC 探针尚未就绪";
        }
        return @"扩展已启用，等待系统摄像头枚举";
    }
    return @"未激活";
}

- (NSString*)readinessStageForPayload:(NSDictionary*)payload {
    NSString* state = [payload[@"state"] isKindOfClass:NSString.class] ? payload[@"state"] : @"not_installed";
    NSNumber* deviceCount = [payload[AKVCDemoAppStatusDeviceCountKey] isKindOfClass:NSNumber.class]
        ? payload[AKVCDemoAppStatusDeviceCountKey]
        : @0;
    BOOL demoModeEnabled = [payload[AKVCDemoAppStatusDemoModeKey] respondsToSelector:@selector(boolValue)]
        ? [payload[AKVCDemoAppStatusDemoModeKey] boolValue]
        : NO;

    if (deviceCount.integerValue > 0) {
        return @"ready_for_app_validation";
    }
    if ([state isEqualToString:@"install_failed"]) {
        return @"host_or_install_blocked";
    }
    if ([state isEqualToString:@"install_pending_approval"]) {
        return @"waiting_user_approval";
    }
    if ([state isEqualToString:@"installed"] && demoModeEnabled) {
        if ([payload[@"ipc_ready"] isKindOfClass:NSNumber.class]
            && ![(NSNumber*)payload[@"ipc_ready"] boolValue]) {
            return @"ipc_not_ready";
        }
        return @"waiting_device_enumeration";
    }
    return @"not_activated";
}

- (NSString*)nextActionForPayload:(NSDictionary*)payload {
    NSString* state = [payload[@"state"] isKindOfClass:NSString.class] ? payload[@"state"] : @"not_installed";
    NSNumber* deviceCount = [payload[AKVCDemoAppStatusDeviceCountKey] isKindOfClass:NSNumber.class]
        ? payload[AKVCDemoAppStatusDeviceCountKey]
        : @0;
    NSString* bundlePath = [payload[@"bundle_path"] isKindOfClass:NSString.class] ? payload[@"bundle_path"] : @"";
    NSString* lastError = [payload[@"last_error"] isKindOfClass:NSString.class] ? payload[@"last_error"] : @"";

    if (deviceCount.integerValue > 0) {
        return @"打开 QuickTime / FaceTime / Zoom，确认能枚举并看到 demo 画面";
    }
    if ([state isEqualToString:@"install_failed"]) {
        if (bundlePath.length == 0) {
            return @"先构建或安装包含 Camera Extension 的 macOS 应用 / VirtualCamera.pkg，再重新点击“刷新状态”";
        }
        if (lastError.length > 0) {
            return [NSString stringWithFormat:@"先处理错误：%@；修复后重新点击“启用 Demo 并激活”", lastError];
        }
        return @"先检查签名、entitlement、provisioning 和 bundle id，再重新激活";
    }
    if ([payload[@"approval_required"] respondsToSelector:@selector(boolValue)]
        && [payload[@"approval_required"] boolValue]) {
        return @"前往“系统设置 -> 隐私与安全性”批准系统扩展，然后回到这里点“刷新状态”";
    }
    if ([state isEqualToString:@"installed"]) {
        if ([payload[@"ipc_ready"] isKindOfClass:NSNumber.class]
            && ![(NSNumber*)payload[@"ipc_ready"] boolValue]) {
            return @"先跑 sync-ipc / direct-push demo，确认 framebus 报告生成后再验证应用枚举";
        }
        return @"打开 QuickTime 新建影片录制，等待系统枚举出当前虚拟摄像头";
    }
    return @"点击“启用 Demo 并激活”，开始系统扩展激活与设备枚举流程";
}

@end
