// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

#import "AKVCCommandSupport.h"
#import "AKVCSystemExtensionSupport.h"

static BOOL AKVCInstallStatusConverged(NSDictionary* payload) {
    NSString* state = [payload[@"state"] isKindOfClass:NSString.class] ? payload[@"state"] : @"";
    NSString* lastError =
        [payload[@"last_error"] isKindOfClass:NSString.class] ? payload[@"last_error"] : @"";
    if ([state isEqualToString:@"install_failed"]
        && [lastError isEqualToString:@"system extension status query timed out"]) {
        return NO;
    }
    if ([state isEqualToString:@"installed"]
        || [state isEqualToString:@"install_pending_approval"]
        || [state isEqualToString:@"install_failed"]) {
        return YES;
    }
    if ([payload[@"enabled"] respondsToSelector:@selector(boolValue)] && [payload[@"enabled"] boolValue]) {
        return YES;
    }
    if ([payload[@"approval_required"] respondsToSelector:@selector(boolValue)]
        && [payload[@"approval_required"] boolValue]) {
        return YES;
    }
    return NO;
}

static NSDictionary* AKVCPollInstallStatusUntilDeadline(NSDate* deadline, BOOL* converged) {
    NSDictionary* payload = nil;
    BOOL didConverge = NO;
    while ([deadline timeIntervalSinceNow] > 0) {
        payload = AKVCQuerySystemExtensionStatus(AKVCCameraExtensionIdentifier(), 0.5);
        if (payload != nil && AKVCInstallStatusConverged(payload)) {
            didConverge = YES;
            break;
        }
        [NSThread sleepForTimeInterval:0.25];
    }
    if (converged != NULL) {
        *converged = didConverge;
    }
    return payload;
}

int main(int argc, const char * argv[]) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        NSError* error = nil;
        if (!AKVCPersistDeviceNameOverrideFromEnvironment(&error)) {
            (void)AKVCWriteJSONObject(@{
                @"state": @"install_failed",
                @"last_error": error.localizedDescription ?: @"failed to persist device name override",
            });
            return 1;
        }
        if (!AKVCPersistSharedMemoryNameOverrideFromEnvironment(&error)) {
            (void)AKVCWriteJSONObject(@{
                @"state": @"install_failed",
                @"last_error": error.localizedDescription ?: @"failed to persist shared memory override",
            });
            return 1;
        }
        NSError* hostError = nil;
        BOOL launchedHost = AKVCLaunchHostAgent(@[@"--activate"], &hostError);

        NSDate* deadline = [NSDate dateWithTimeIntervalSinceNow:3.0];
        BOOL converged = NO;
        NSDictionary* payload = nil;
        if (launchedHost) {
            payload = AKVCPollInstallStatusUntilDeadline(deadline, &converged);
            if (converged) {
                return AKVCWriteJSONObject(payload);
            }
        } else {
            NSError* effectiveError = hostError ?: error;
            (void)AKVCWriteJSONObject(@{
                @"state": @"install_failed",
                @"last_error": effectiveError.localizedDescription
                    ?: @"failed to launch container app activation request",
            });
            return 1;
        }
        if (payload == nil) {
            payload = AKVCQuerySystemExtensionStatus(AKVCCameraExtensionIdentifier(), 0.5);
        }

        NSMutableDictionary* fallback = [[payload mutableCopy] ?: [NSMutableDictionary dictionary] mutableCopy];
        fallback[@"state"] = @"install_pending_approval";
        fallback[@"bundle_path"] = fallback[@"bundle_path"] ?: AKVCResolvedBundlePath();
        fallback[@"approval_required"] = fallback[@"approval_required"] ?: @YES;
        return AKVCWriteJSONObject(fallback);
    }
}
