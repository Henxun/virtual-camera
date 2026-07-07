// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

#import "AKVCCommandSupport.h"
#import "AKVCSystemExtensionSupport.h"

int main(int argc, const char * argv[]) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        return AKVCWriteJSONObject(AKVCQuerySystemExtensionStatus(AKVCCameraExtensionIdentifier(), 5.0));
    }
}
