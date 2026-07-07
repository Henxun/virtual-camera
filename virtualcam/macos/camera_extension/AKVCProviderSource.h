// SPDX-License-Identifier: Apache-2.0
#import <CoreMediaIO/CoreMediaIO.h>
#import <Foundation/Foundation.h>

@class AKVCDeviceSource;

NS_ASSUME_NONNULL_BEGIN

@interface AKVCProviderSource : NSObject <CMIOExtensionProviderSource>

@property(nonatomic, copy, readonly) NSString* providerName;
@property(nonatomic, copy, readonly) NSString* manufacturer;
@property(nonatomic, strong, readonly) AKVCDeviceSource* deviceSource;
@property(atomic, readonly, copy) NSSet<CMIOExtensionProperty>* availableProperties;
@property(nonatomic, strong, readonly) CMIOExtensionProvider* provider;

- (instancetype)init;
- (instancetype)initWithProviderName:(NSString*)providerName
                        manufacturer:(NSString*)manufacturer
                        deviceSource:(AKVCDeviceSource*)deviceSource;

@end

NS_ASSUME_NONNULL_END
