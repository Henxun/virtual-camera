// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString* AKVCCameraExtensionIdentifier(void);
FOUNDATION_EXPORT NSDictionary* AKVCQuerySystemExtensionStatus(NSString* extensionIdentifier, NSTimeInterval timeoutSeconds);
FOUNDATION_EXPORT NSString* AKVCResolvedHostExecutablePath(void);
FOUNDATION_EXPORT BOOL AKVCLaunchHostAgent(NSArray<NSString*>* arguments, NSError* _Nullable* _Nullable outError);
FOUNDATION_EXPORT void AKVCSubmitSystemExtensionRequestAsync(
    BOOL activate,
    void (^completion)(BOOL succeeded, NSError* _Nullable error)
);
FOUNDATION_EXPORT BOOL AKVCSubmitSystemExtensionRequest(BOOL activate, NSTimeInterval timeoutSeconds, NSError* _Nullable* _Nullable outError);

NS_ASSUME_NONNULL_END
