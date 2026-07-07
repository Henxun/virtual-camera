// SPDX-License-Identifier: Apache-2.0
#import "AKVCDeviceSource.h"

#import "AKVCSinkStreamSource.h"
#import "AKVCStreamSource.h"

static NSString* const AKVCDeviceSourceErrorDomain = @"com.akvc.macos.camera-extension.device-source";

static NSError* AKVCDeviceSourceError(NSInteger code, NSString* description) {
    return [NSError errorWithDomain:AKVCDeviceSourceErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

@interface AKVCDeviceSource ()
@property(nonatomic, copy, readwrite) NSString* localizedName;
@property(nonatomic, copy, readwrite) NSUUID* deviceID;
@property(nonatomic, copy, readwrite) NSString* legacyDeviceID;
@property(nonatomic, strong, readwrite) AKVCStreamSource* sourceStreamSource;
@property(nonatomic, strong, readwrite) AKVCSinkStreamSource* sinkStreamSource;
@property(atomic, copy, readwrite) NSSet<CMIOExtensionProperty>* availableProperties;
@end

@implementation AKVCDeviceSource

- (instancetype)initWithLocalizedName:(NSString*)localizedName
                             deviceID:(NSUUID*)deviceID
                       legacyDeviceID:(NSString*)legacyDeviceID
                   sourceStreamSource:(AKVCStreamSource*)sourceStreamSource
                     sinkStreamSource:(AKVCSinkStreamSource*)sinkStreamSource {
    self = [super init];
    if (self == nil) {
        return nil;
    }
    _localizedName = [localizedName copy];
    _deviceID = [deviceID copy];
    _legacyDeviceID = [legacyDeviceID copy];
    _sourceStreamSource = sourceStreamSource;
    _sinkStreamSource = sinkStreamSource;
    _availableProperties = [NSSet setWithArray:@[
        CMIOExtensionPropertyDeviceModel,
        CMIOExtensionPropertyDeviceIsSuspended,
        CMIOExtensionPropertyDeviceCanBeDefaultInputDevice,
        CMIOExtensionPropertyDeviceCanBeDefaultOutputDevice,
    ]];
    return self;
}

- (CMIOExtensionDeviceProperties*)devicePropertiesForProperties:(NSSet<CMIOExtensionProperty>*)properties
                                                          error:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    CMIOExtensionDeviceProperties* deviceProperties =
        [CMIOExtensionDeviceProperties devicePropertiesWithDictionary:@{}];

    if ([properties containsObject:CMIOExtensionPropertyDeviceModel]) {
        deviceProperties.model = @"AKVC CMIO Camera Extension";
    }
    if ([properties containsObject:CMIOExtensionPropertyDeviceIsSuspended]) {
        deviceProperties.suspended = @NO;
    }
    if ([properties containsObject:CMIOExtensionPropertyDeviceCanBeDefaultInputDevice]) {
        [deviceProperties setPropertyState:[CMIOExtensionPropertyState propertyStateWithValue:@YES]
                               forProperty:CMIOExtensionPropertyDeviceCanBeDefaultInputDevice];
    }
    if ([properties containsObject:CMIOExtensionPropertyDeviceCanBeDefaultOutputDevice]) {
        [deviceProperties setPropertyState:[CMIOExtensionPropertyState propertyStateWithValue:@NO]
                               forProperty:CMIOExtensionPropertyDeviceCanBeDefaultOutputDevice];
    }
    return deviceProperties;
}

- (BOOL)setDeviceProperties:(CMIOExtensionDeviceProperties*)deviceProperties
                      error:(NSError* _Nullable __autoreleasing*)outError {
    if (deviceProperties.propertiesDictionary.count == 0) {
        return YES;
    }
    if (outError != nil) {
        *outError = AKVCDeviceSourceError(1, @"device properties are read-only in the current macOS MVP");
    }
    return NO;
}

@end
