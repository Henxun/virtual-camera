// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

#import "AKVCCommandSupport.h"

int main(int argc, const char * argv[]) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        NSError* error = nil;
        if (!AKVCPersistSharedMemoryNameOverrideFromEnvironment(&error)) {
            (void)AKVCWriteJSONObject(@{
                @"state": @"install_failed",
                @"last_error": error.localizedDescription ?: @"failed to persist shared memory configuration",
            });
            return 1;
        }

        NSMutableDictionary* payload = [[AKVCDefaultStatusPayload() mutableCopy] ?: [NSMutableDictionary dictionary] mutableCopy];
        payload[@"phase"] = @"ipc_configuration_synced";
        payload[@"synced"] = @YES;
        return AKVCWriteJSONObject(payload);
    }
}
