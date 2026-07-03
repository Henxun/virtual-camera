// SPDX-License-Identifier: Apache-2.0
#import "AKVCStreamSource.h"

#import <dispatch/dispatch.h>

#import "AKVCFrameProvider.h"

static NSString* const AKVCStreamSourceErrorDomain = @"com.akvc.macos.camera-extension.stream-source";

static NSError* AKVCStreamSourceError(NSInteger code, NSString* description) {
    return [NSError errorWithDomain:AKVCStreamSourceErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

@interface AKVCStreamSource ()
@property(nonatomic, strong, readwrite) AKVCFrameProvider* frameProvider;
@property(nonatomic, assign, readwrite, getter=isStreaming) BOOL streaming;
@property(atomic, copy, readwrite) NSSet<CMIOExtensionProperty>* availableProperties;
@property(nonatomic, weak) CMIOExtensionStream* stream;
@property(nonatomic) dispatch_queue_t streamQueue;
@property(nonatomic) dispatch_source_t timer;
@end

@implementation AKVCStreamSource

- (instancetype)initWithFrameProvider:(AKVCFrameProvider*)frameProvider {
    self = [super init];
    if (self == nil) {
        return nil;
    }
    _frameProvider = frameProvider;
    _streaming = NO;
    _availableProperties = [NSSet setWithArray:@[
        CMIOExtensionPropertyStreamActiveFormatIndex,
        CMIOExtensionPropertyStreamFrameDuration,
        CMIOExtensionPropertyStreamMaxFrameDuration,
    ]];
    _streamQueue = dispatch_queue_create("com.akvc.macos.camera-extension.stream", DISPATCH_QUEUE_SERIAL);
    return self;
}

- (NSArray<CMIOExtensionStreamFormat*>*)formats {
    return self.frameProvider.streamFormats;
}

- (void)attachStream:(CMIOExtensionStream*)stream {
    self.stream = stream;
}

- (CMIOExtensionStreamProperties*)streamPropertiesForProperties:(NSSet<CMIOExtensionProperty>*)properties
                                                          error:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    CMIOExtensionStreamProperties* streamProperties =
        [CMIOExtensionStreamProperties streamPropertiesWithDictionary:@{}];

    if ([properties containsObject:CMIOExtensionPropertyStreamActiveFormatIndex]) {
        streamProperties.activeFormatIndex = @(self.frameProvider.activeFormatIndex);
    }
    if ([properties containsObject:CMIOExtensionPropertyStreamFrameDuration]) {
        streamProperties.frameDuration = CFBridgingRelease(
            CMTimeCopyAsDictionary(self.frameProvider.activeFrameDuration, kCFAllocatorDefault)
        );
    }
    if ([properties containsObject:CMIOExtensionPropertyStreamMaxFrameDuration]) {
        streamProperties.maxFrameDuration = CFBridgingRelease(
            CMTimeCopyAsDictionary(self.frameProvider.maximumFrameDuration, kCFAllocatorDefault)
        );
    }
    return streamProperties;
}

- (BOOL)setStreamProperties:(CMIOExtensionStreamProperties*)streamProperties
                      error:(NSError* _Nullable __autoreleasing*)outError {
    NSDictionary<CMIOExtensionProperty, CMIOExtensionPropertyState*>* updates =
        streamProperties.propertiesDictionary ?: @{};
    NSMutableDictionary<CMIOExtensionProperty, CMIOExtensionPropertyState*>* changed =
        [NSMutableDictionary dictionary];

    CMIOExtensionPropertyState* formatState = updates[CMIOExtensionPropertyStreamActiveFormatIndex];
    if ([formatState.value isKindOfClass:[NSNumber class]]) {
        if (![self.frameProvider selectFormatAtIndex:[(NSNumber*)formatState.value unsignedIntegerValue] error:outError]) {
            return NO;
        }
        changed[CMIOExtensionPropertyStreamActiveFormatIndex] =
            [CMIOExtensionPropertyState propertyStateWithValue:@(self.frameProvider.activeFormatIndex)];
    }

    CMIOExtensionPropertyState* durationState = updates[CMIOExtensionPropertyStreamFrameDuration];
    if ([durationState.value isKindOfClass:[NSDictionary class]]) {
        CMTime duration = CMTimeMakeFromDictionary((__bridge CFDictionaryRef)durationState.value);
        if (![self.frameProvider selectFrameDuration:duration error:outError]) {
            return NO;
        }
        changed[CMIOExtensionPropertyStreamFrameDuration] =
            [CMIOExtensionPropertyState propertyStateWithValue:(id)CFBridgingRelease(
                CMTimeCopyAsDictionary(self.frameProvider.activeFrameDuration, kCFAllocatorDefault)
            )];
    }

    if (self.streaming) {
        [self restartTimer];
    }

    if (self.stream != nil && changed.count > 0) {
        [self.stream notifyPropertiesChanged:changed];
    }

    return YES;
}

- (BOOL)authorizedToStartStreamForClient:(CMIOExtensionClient*)client {
    (void)client;
    return YES;
}

- (BOOL)startStreamAndReturnError:(NSError* _Nullable __autoreleasing*)outError {
    if (self.stream == nil) {
        if (outError != nil) {
            *outError = AKVCStreamSourceError(1, @"backing stream is not attached");
        }
        return NO;
    }
    if (self.streaming) {
        return YES;
    }

    self.streaming = YES;
    [self restartTimer];
    [self emitNextFrame];
    return YES;
}

- (BOOL)stopStreamAndReturnError:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    if (!self.streaming) {
        return YES;
    }
    self.streaming = NO;
    if (self.timer != nil) {
        dispatch_source_cancel(self.timer);
        self.timer = nil;
    }
    [self.frameProvider closeFrameReader];
    return YES;
}

- (void)restartTimer {
    if (self.timer != nil) {
        dispatch_source_cancel(self.timer);
        self.timer = nil;
    }

    __weak typeof(self) weakSelf = self;
    dispatch_source_t timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, self.streamQueue);
    uint64_t interval = [self timerIntervalInNanoseconds];
    dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, 0), interval, interval / 4);
    dispatch_source_set_event_handler(timer, ^{
        [weakSelf emitNextFrame];
    });
    dispatch_resume(timer);
    self.timer = timer;
}

- (uint64_t)timerIntervalInNanoseconds {
    CMTime duration = self.frameProvider.activeFrameDuration;
    CMTime nanos = CMTimeConvertScale(duration, 1000000000, kCMTimeRoundingMethod_Default);
    if (!CMTIME_IS_NUMERIC(nanos) || nanos.value <= 0) {
        return (uint64_t)(NSEC_PER_SEC / 30);
    }
    return (uint64_t)nanos.value;
}

- (void)emitNextFrame {
    if (!self.streaming || self.stream == nil) {
        return;
    }

    NSUInteger previousFormatIndex = self.frameProvider.activeFormatIndex;
    CMTime previousFrameDuration = self.frameProvider.activeFrameDuration;
    NSError* error = nil;
    CMIOExtensionStreamDiscontinuityFlags discontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
    CMSampleBufferRef sampleBuffer =
        [self.frameProvider copyLatestClientSampleBufferWithDiscontinuity:&discontinuity error:&error];

    AKVCFrameReadStatus status = AKVCFrameReadStatusError;
    if (sampleBuffer == nil) {
        sampleBuffer = [self.frameProvider copyNextSampleBufferWithStatus:&status
                                                            discontinuity:&discontinuity
                                                                    error:&error];
    }

    if (sampleBuffer == nil) {
        if (status == AKVCFrameReadStatusTimedOut
            || status == AKVCFrameReadStatusTorn
            || status == AKVCFrameReadStatusError) {
            return;
        }

        error = nil;
        sampleBuffer = [self.frameProvider copyFallbackSampleBuffer:&error];
        discontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
    }

    if (sampleBuffer == nil || error != nil) {
        return;
    }

    if (self.frameProvider.activeFormatIndex != previousFormatIndex) {
        [self.stream notifyPropertiesChanged:@{
            CMIOExtensionPropertyStreamActiveFormatIndex:
                [CMIOExtensionPropertyState propertyStateWithValue:@(self.frameProvider.activeFormatIndex)]
        }];
    }
    if (CMTimeCompare(self.frameProvider.activeFrameDuration, previousFrameDuration) != 0) {
        [self.stream notifyPropertiesChanged:@{
            CMIOExtensionPropertyStreamFrameDuration:
                [CMIOExtensionPropertyState propertyStateWithValue:(id)CFBridgingRelease(
                    CMTimeCopyAsDictionary(self.frameProvider.activeFrameDuration, kCFAllocatorDefault)
                )]
        }];
    }

    [self.stream sendSampleBuffer:sampleBuffer
                    discontinuity:discontinuity
            hostTimeInNanoseconds:[self.frameProvider nextHostTimeInNanoseconds]];
    CFRelease(sampleBuffer);
}

@end
