// SPDX-License-Identifier: Apache-2.0
#import <CoreMediaIO/CoreMediaIO.h>
#import <Foundation/Foundation.h>

#import "AKVCProviderSource.h"

int main(int argc, const char* argv[]) {
    (void)argc;
    (void)argv;

    @autoreleasepool {
        AKVCProviderSource* providerSource = [[AKVCProviderSource alloc] init];
        [CMIOExtensionProvider startServiceWithProvider:providerSource.provider];
        CFRunLoopRun();
    }
    return 0;
}
