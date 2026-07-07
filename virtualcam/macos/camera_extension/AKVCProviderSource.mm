// SPDX-License-Identifier: Apache-2.0
#import "AKVCProviderSource.h"

#import <os/log.h>

#import "../demo_support/AKVCDemoFrameGenerator.h"
#import "AKVCDeviceSource.h"
#import "AKVCFrameProvider.h"
#import "AKVCSinkStreamSource.h"
#import "AKVCStreamSource.h"
#include "akvc/macos_ipc.h"

static NSString* const AKVCDefaultProviderName = @"AK Virtual Camera";
static NSString* const AKVCDefaultManufacturer = @"AKVC";
static NSString* const AKVCDefaultLegacyDeviceID = @"com.akvc.camera.device";
static NSString* const AKVCDefaultDeviceUUIDString = @"BB1AFDA4-6E12-46AF-98E2-86CB2D11B708";
static NSString* const AKVCDefaultSourceStreamUUIDString = @"3FCD5F1B-8F45-428D-913B-65767394A0A8";
static NSString* const AKVCDefaultSinkStreamUUIDString = @"D7EB1D5A-D545-4A86-8D33-0A0F79018C44";

@interface AKVCProviderSource ()
@property(nonatomic, copy, readwrite) NSString* providerName;
@property(nonatomic, copy, readwrite) NSString* manufacturer;
@property(nonatomic, strong, readwrite) AKVCDeviceSource* deviceSource;
@property(atomic, copy, readwrite) NSSet<CMIOExtensionProperty>* availableProperties;
@property(nonatomic, strong, readwrite) CMIOExtensionProvider* provider;
@property(nonatomic, strong) AKVCFrameProvider* frameProvider;
@property(nonatomic, strong) AKVCStreamSource* streamSource;
@property(nonatomic, strong) AKVCSinkStreamSource* sinkStreamSource;
@property(nonatomic, strong) CMIOExtensionDevice* device;
@property(nonatomic, strong) CMIOExtensionStream* sourceStream;
@property(nonatomic, strong) CMIOExtensionStream* sinkStream;
@property(nonatomic) dispatch_queue_t clientQueue;
@end

@implementation AKVCProviderSource

- (instancetype)init {
    akvc_macos_ring_descriptor_t descriptor = {};
    akvc_macos_ring_descriptor_default(&descriptor);
    NSString* configuredDeviceName = [NSString stringWithUTF8String:akvc_macos_resolved_device_name()];
    if (configuredDeviceName.length == 0) {
        configuredDeviceName = AKVCDefaultProviderName;
    }

    AKVCFrameProvider* frameProvider = [[AKVCFrameProvider alloc]
        initWithSharedMemoryName:[NSString stringWithUTF8String:descriptor.shm_name]
                       slotCount:descriptor.slot_count
                        slotSize:descriptor.slot_size];
    AKVCDemoFrameGenerator* demoFrameGenerator =
        [[AKVCDemoFrameGenerator alloc] initWithWidth:1280 height:720];
    [frameProvider setFallbackSampleBufferSource:(id<AKVCSampleBufferSource>)demoFrameGenerator];
    AKVCStreamSource* streamSource = [[AKVCStreamSource alloc] initWithFrameProvider:frameProvider];
    AKVCSinkStreamSource* sinkStreamSource = [[AKVCSinkStreamSource alloc] initWithFrameProvider:frameProvider];
    AKVCDeviceSource* deviceSource = [[AKVCDeviceSource alloc]
        initWithLocalizedName:configuredDeviceName
                     deviceID:[[NSUUID alloc] initWithUUIDString:AKVCDefaultDeviceUUIDString]
               legacyDeviceID:AKVCDefaultLegacyDeviceID
           sourceStreamSource:streamSource
             sinkStreamSource:sinkStreamSource];

    return [self initWithProviderName:configuredDeviceName
                         manufacturer:AKVCDefaultManufacturer
                         deviceSource:deviceSource];
}

- (instancetype)initWithProviderName:(NSString*)providerName
                        manufacturer:(NSString*)manufacturer
                        deviceSource:(AKVCDeviceSource*)deviceSource {
    self = [super init];
    if (self == nil) {
        return nil;
    }
    _providerName = [providerName copy];
    _manufacturer = [manufacturer copy];
    _deviceSource = deviceSource;
    _streamSource = deviceSource.sourceStreamSource;
    _sinkStreamSource = deviceSource.sinkStreamSource;
    _frameProvider = deviceSource.sourceStreamSource.frameProvider;
    _availableProperties = [NSSet setWithArray:@[
        CMIOExtensionPropertyProviderName,
        CMIOExtensionPropertyProviderManufacturer,
    ]];
    _clientQueue = dispatch_queue_create("com.akvc.macos.camera-extension.provider", DISPATCH_QUEUE_SERIAL);

    [self bootstrapProviderGraph];
    return self;
}

- (BOOL)connectClient:(CMIOExtensionClient*)client error:(NSError* _Nullable __autoreleasing*)outError {
    (void)client;
    (void)outError;
    return YES;
}

- (void)disconnectClient:(CMIOExtensionClient*)client {
    (void)client;
}

- (CMIOExtensionProviderProperties*)providerPropertiesForProperties:(NSSet<CMIOExtensionProperty>*)properties
                                                              error:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    CMIOExtensionProviderProperties* providerProperties =
        [CMIOExtensionProviderProperties providerPropertiesWithDictionary:@{}];

    if ([properties containsObject:CMIOExtensionPropertyProviderName]) {
        providerProperties.name = self.providerName;
    }
    if ([properties containsObject:CMIOExtensionPropertyProviderManufacturer]) {
        providerProperties.manufacturer = self.manufacturer;
    }
    return providerProperties;
}

- (BOOL)setProviderProperties:(CMIOExtensionProviderProperties*)providerProperties
                        error:(NSError* _Nullable __autoreleasing*)outError {
    if (providerProperties.propertiesDictionary.count == 0) {
        return YES;
    }
    if (outError != nil) {
        *outError = [NSError errorWithDomain:@"com.akvc.macos.camera-extension.provider"
                                        code:1
                                    userInfo:@{
                                        NSLocalizedDescriptionKey: @"provider properties are read-only in the current macOS MVP"
                                    }];
    }
    return NO;
}

- (void)bootstrapProviderGraph {
    self.provider = [CMIOExtensionProvider providerWithSource:self clientQueue:self.clientQueue];

    self.sourceStream = [CMIOExtensionStream streamWithLocalizedName:@"AKVC Stream"
                                                            streamID:[[NSUUID alloc] initWithUUIDString:AKVCDefaultSourceStreamUUIDString]
                                                           direction:CMIOExtensionStreamDirectionSource
                                                           clockType:CMIOExtensionStreamClockTypeHostTime
                                                              source:self.streamSource];
    [self.streamSource attachStream:self.sourceStream];

    self.sinkStream = [CMIOExtensionStream streamWithLocalizedName:@"AKVC Sink Stream"
                                                          streamID:[[NSUUID alloc] initWithUUIDString:AKVCDefaultSinkStreamUUIDString]
                                                         direction:CMIOExtensionStreamDirectionSink
                                                         clockType:CMIOExtensionStreamClockTypeHostTime
                                                            source:self.sinkStreamSource];
    [self.sinkStreamSource attachStream:self.sinkStream];

    self.device = [CMIOExtensionDevice deviceWithLocalizedName:self.deviceSource.localizedName
                                                      deviceID:self.deviceSource.deviceID
                                                legacyDeviceID:self.deviceSource.legacyDeviceID
                                                        source:self.deviceSource];

    NSError* error = nil;
    if (![self.device addStream:self.sourceStream error:&error]) {
        os_log_error(OS_LOG_DEFAULT, "AKVC failed to add CMIOExtensionStream: %{public}@", error.localizedDescription);
    }
    error = nil;
    if (![self.device addStream:self.sinkStream error:&error]) {
        os_log_error(OS_LOG_DEFAULT, "AKVC failed to add CMIOExtensionStream: %{public}@", error.localizedDescription);
    }
    error = nil;
    if (![self.provider addDevice:self.device error:&error]) {
        os_log_error(OS_LOG_DEFAULT, "AKVC failed to add CMIOExtensionDevice: %{public}@", error.localizedDescription);
    }

    [CMIOExtensionProvider startServiceWithProvider:self.provider];
}

@end
