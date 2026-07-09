// SPDX-License-Identifier: Apache-2.0
#import "AKVCSinkStreamSource.h"

#import <dispatch/dispatch.h>

#import "AKVCFrameProvider.h"

static NSString* const AKVCSinkStreamSourceErrorDomain = @"com.akvc.macos.camera-extension.sink-stream-source";

static NSError* AKVCSinkStreamSourceError(NSInteger code, NSString* description) {
    return [NSError errorWithDomain:AKVCSinkStreamSourceErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

@interface AKVCSinkStreamSource ()
@property(nonatomic, strong, readwrite) AKVCFrameProvider* frameProvider;
@property(nonatomic, assign, readwrite, getter=isStreaming) BOOL streaming;
@property(atomic, copy, readwrite) NSSet<CMIOExtensionProperty>* availableProperties;
@property(nonatomic, weak) CMIOExtensionStream* stream;
@property(nonatomic) dispatch_queue_t sinkQueue;
@property(nonatomic) dispatch_source_t timer;
@property(nonatomic, strong) NSNumber* sinkBufferQueueSize;
@property(nonatomic, strong) NSNumber* sinkBuffersRequiredForStartup;
@property(nonatomic, strong) NSNumber* sinkBufferUnderrunCount;
@property(nonatomic, strong) NSNumber* sinkEndOfData;
@end

@implementation AKVCSinkStreamSource

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
        CMIOExtensionPropertyStreamSinkBufferQueueSize,
        CMIOExtensionPropertyStreamSinkBuffersRequiredForStartup,
        CMIOExtensionPropertyStreamSinkBufferUnderrunCount,
        CMIOExtensionPropertyStreamSinkEndOfData,
    ]];
    _sinkQueue = dispatch_queue_create("com.akvc.macos.camera-extension.sink-stream", DISPATCH_QUEUE_SERIAL);
    _sinkBufferQueueSize = @8;
    _sinkBuffersRequiredForStartup = @1;
    _sinkBufferUnderrunCount = @0;
    _sinkEndOfData = @NO;
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
    if ([properties containsObject:CMIOExtensionPropertyStreamSinkBufferQueueSize]) {
        streamProperties.sinkBufferQueueSize = self.sinkBufferQueueSize;
    }
    if ([properties containsObject:CMIOExtensionPropertyStreamSinkBuffersRequiredForStartup]) {
        streamProperties.sinkBuffersRequiredForStartup = self.sinkBuffersRequiredForStartup;
    }
    if ([properties containsObject:CMIOExtensionPropertyStreamSinkBufferUnderrunCount]) {
        streamProperties.sinkBufferUnderrunCount = self.sinkBufferUnderrunCount;
    }
    if ([properties containsObject:CMIOExtensionPropertyStreamSinkEndOfData]) {
        streamProperties.sinkEndOfData = self.sinkEndOfData;
    }
    return streamProperties;
}

- (BOOL)setStreamProperties:(CMIOExtensionStreamProperties*)streamProperties
                      error:(NSError* _Nullable __autoreleasing*)outError {
    NSDictionary<CMIOExtensionProperty, CMIOExtensionPropertyState*>* updates =
        streamProperties.propertiesDictionary ?: @{};

    CMIOExtensionPropertyState* formatState = updates[CMIOExtensionPropertyStreamActiveFormatIndex];
    if ([formatState.value isKindOfClass:[NSNumber class]]) {
        if (![self.frameProvider selectFormatAtIndex:[(NSNumber*)formatState.value unsignedIntegerValue] error:outError]) {
            return NO;
        }
    }

    CMIOExtensionPropertyState* durationState = updates[CMIOExtensionPropertyStreamFrameDuration];
    if ([durationState.value isKindOfClass:[NSDictionary class]]) {
        CMTime duration = CMTimeMakeFromDictionary((__bridge CFDictionaryRef)durationState.value);
        if (![self.frameProvider selectFrameDuration:duration error:outError]) {
            return NO;
        }
    }

    CMIOExtensionPropertyState* endOfDataState = updates[CMIOExtensionPropertyStreamSinkEndOfData];
    if ([endOfDataState.value isKindOfClass:[NSNumber class]]) {
        self.sinkEndOfData = (NSNumber*)endOfDataState.value;
    }

    return YES;
}

- (BOOL)authorizedToStartStreamForClient:(CMIOExtensionClient*)client {
    (void)client;
    NSLog(@"AKVC SINK authorizedToStartStream");
    return YES;
}

- (BOOL)startStreamAndReturnError:(NSError* _Nullable __autoreleasing*)outError {
    NSLog(@"AKVC SINK startStream entry stream=%p streaming=%d", self.stream, self.streaming);
    if (self.stream == nil) {
        if (outError != nil) {
            *outError = AKVCSinkStreamSourceError(1, @"backing stream is not attached");
        }
        NSLog(@"AKVC SINK startStream -> NO (stream nil)");
        return NO;
    }
    if (self.streaming) {
        NSLog(@"AKVC SINK startStream -> YES (already streaming)");
        return YES;
    }

    self.streaming = YES;
    self.sinkEndOfData = @NO;
    [self restartTimer];
    [self pollStreamingClients];
    NSLog(@"AKVC SINK startStream -> YES");
    return YES;
}

- (BOOL)stopStreamAndReturnError:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    if (!self.streaming) {
        return YES;
    }
    self.streaming = NO;
    self.sinkEndOfData = @YES;
    if (self.timer != nil) {
        dispatch_source_cancel(self.timer);
        self.timer = nil;
    }
    return YES;
}

- (void)restartTimer {
    if (self.timer != nil) {
        dispatch_source_cancel(self.timer);
        self.timer = nil;
    }

    __weak typeof(self) weakSelf = self;
    dispatch_source_t timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, self.sinkQueue);
    uint64_t interval = MAX((uint64_t)(NSEC_PER_SEC / 240), (uint64_t)1000000);
    dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, 0), interval, interval / 2);
    dispatch_source_set_event_handler(timer, ^{
        [weakSelf pollStreamingClients];
    });
    dispatch_resume(timer);
    self.timer = timer;
}

- (void)pollStreamingClients {
    if (!self.streaming || self.stream == nil) {
        return;
    }

    for (CMIOExtensionClient* client in self.stream.streamingClients) {
        [self consumeBuffersForClient:client];
    }
}

- (void)consumeBuffersForClient:(CMIOExtensionClient*)client {
    if (!self.streaming || self.stream == nil || client == nil) {
        return;
    }

    __weak typeof(self) weakSelf = self;
    [self.stream consumeSampleBufferFromClient:client
                             completionHandler:^(CMSampleBufferRef _Nullable sampleBuffer,
                                                 uint64_t sampleBufferSequenceNumber,
                                                 CMIOExtensionStreamDiscontinuityFlags discontinuity,
                                                 BOOL hasMoreSampleBuffers,
                                                 NSError* _Nullable error) {
        (void)sampleBufferSequenceNumber;
        typeof(self) strongSelf = weakSelf;
        if (strongSelf == nil || !strongSelf.streaming) {
            return;
        }
        if (sampleBuffer != nil && error == nil) {
            [strongSelf.frameProvider storeClientSampleBuffer:sampleBuffer discontinuity:discontinuity];
        } else if (error != nil) {
            NSInteger underruns = strongSelf.sinkBufferUnderrunCount.integerValue + 1;
            strongSelf.sinkBufferUnderrunCount = @(underruns);
        }
        if (hasMoreSampleBuffers) {
            [strongSelf consumeBuffersForClient:client];
        }
    }];
}

@end

