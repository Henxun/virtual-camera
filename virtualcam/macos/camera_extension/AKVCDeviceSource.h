// SPDX-License-Identifier: Apache-2.0
#import <CoreMediaIO/CoreMediaIO.h>
#import <Foundation/Foundation.h>

@class AKVCStreamSource;
@class AKVCSinkStreamSource;

NS_ASSUME_NONNULL_BEGIN

@interface AKVCDeviceSource : NSObject <CMIOExtensionDeviceSource>

@property(nonatomic, copy, readonly) NSString* localizedName;
@property(nonatomic, copy, readonly) NSUUID* deviceID;
@property(nonatomic, copy, readonly) NSString* legacyDeviceID;
@property(nonatomic, strong, readonly) AKVCStreamSource* sourceStreamSource;
@property(nonatomic, strong, readonly) AKVCSinkStreamSource* sinkStreamSource;
@property(atomic, readonly, copy) NSSet<CMIOExtensionProperty>* availableProperties;

- (instancetype)initWithLocalizedName:(NSString*)localizedName
                             deviceID:(NSUUID*)deviceID
                       legacyDeviceID:(NSString*)legacyDeviceID
                   sourceStreamSource:(AKVCStreamSource*)sourceStreamSource
                     sinkStreamSource:(AKVCSinkStreamSource*)sinkStreamSource;

@end

NS_ASSUME_NONNULL_END
