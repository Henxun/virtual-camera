// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT int AKVCWriteJSONObject(NSDictionary* object);
FOUNDATION_EXPORT NSDictionary* AKVCDefaultStatusPayload(void);
FOUNDATION_EXPORT int AKVCWriteNotImplemented(NSString* actionName);
FOUNDATION_EXPORT NSString* AKVCResolvedBundlePath(void);
FOUNDATION_EXPORT NSString* AKVCResolvedBundleExecutablePath(NSString* bundlePath);
FOUNDATION_EXPORT NSString* AKVCDevicePrefix(void);
FOUNDATION_EXPORT NSArray<NSString*>* AKVCEnumeratedVideoDevices(void);
FOUNDATION_EXPORT NSDictionary* AKVCVideoDeviceSnapshot(void);
FOUNDATION_EXPORT BOOL AKVCPersistDeviceNameOverrideFromEnvironment(NSError* _Nullable* _Nullable outError);
FOUNDATION_EXPORT BOOL AKVCPersistSharedMemoryNameOverrideFromEnvironment(NSError* _Nullable* _Nullable outError);
FOUNDATION_EXPORT BOOL AKVCSetDemoModeEnabled(BOOL enabled, NSError* _Nullable* _Nullable outError);

NS_ASSUME_NONNULL_END
