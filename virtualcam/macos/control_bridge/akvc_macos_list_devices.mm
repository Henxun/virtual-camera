// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

#import "AKVCCommandSupport.h"

int main(int argc, const char * argv[]) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        return AKVCWriteJSONObject(AKVCVideoDeviceSnapshot());
    }
}
