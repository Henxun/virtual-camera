// SPDX-License-Identifier: Apache-2.0
#import "AKVCFrameProvider.h"

#import <CoreVideo/CoreVideo.h>

#include "akvc/macos_ipc.h"
#include "akvc/framebus_posix.h"

static NSString* const AKVCFrameProviderErrorDomain = @"com.akvc.macos.camera-extension.frame-provider";

static NSDictionary* AKVCCopyTimeDictionary(CMTime time) {
    return CFBridgingRelease(CMTimeCopyAsDictionary(time, kCFAllocatorDefault));
}

static NSError* AKVCFrameProviderError(NSInteger code, NSString* description) {
    return [NSError errorWithDomain:AKVCFrameProviderErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

static NSError* AKVCFrameProviderPixelBufferAccessError(NSInteger code, NSString* description) {
    return AKVCFrameProviderError(code, description);
}

@interface AKVCFrameProvider () {
    CVPixelBufferPoolRef _pixelBufferPool;
    akvc_fb_consumer_t* _consumer;
    BOOL _pendingConfigurationDiscontinuity;
    CMSampleBufferRef _latestClientSampleBuffer;
    CMIOExtensionStreamDiscontinuityFlags _latestClientDiscontinuity;
    id<AKVCSampleBufferSource> _fallbackSampleBufferSource;
}
@property(nonatomic, copy, readwrite) NSString* sharedMemoryName;
@property(nonatomic, assign, readwrite) uint32_t slotCount;
@property(nonatomic, assign, readwrite) uint32_t slotSize;
@property(nonatomic, copy, readwrite) NSArray<CMIOExtensionStreamFormat*>* streamFormats;
@property(nonatomic, assign, readwrite) NSUInteger activeFormatIndex;
@property(nonatomic, assign, readwrite) CMTime activeFrameDuration;
@property(nonatomic, assign, readwrite) CMTime minimumFrameDuration;
@property(nonatomic, assign, readwrite) CMTime maximumFrameDuration;
@end

@implementation AKVCFrameProvider

- (instancetype)initWithSharedMemoryName:(NSString*)sharedMemoryName
                               slotCount:(uint32_t)slotCount
                                slotSize:(uint32_t)slotSize {
    self = [super init];
    if (self == nil) {
        return nil;
    }

    _sharedMemoryName = [sharedMemoryName copy];
    _slotCount = slotCount;
    _slotSize = slotSize;
    _minimumFrameDuration = CMTimeMake(1, 60);
    _maximumFrameDuration = CMTimeMake(1, 30);
    _activeFrameDuration = _maximumFrameDuration;
    _streamFormats = [self buildDefaultFormats];
    _activeFormatIndex = 0;
    _pixelBufferPool = nil;
    _consumer = NULL;
    _pendingConfigurationDiscontinuity = NO;
    _latestClientSampleBuffer = nil;
    _latestClientDiscontinuity = CMIOExtensionStreamDiscontinuityFlagNone;

    NSError* poolError = nil;
    [self rebuildPixelBufferPool:&poolError];
    return self;
}

- (void)dealloc {
    if (_pixelBufferPool != nil) {
        CFRelease(_pixelBufferPool);
        _pixelBufferPool = nil;
    }
    if (_consumer != NULL) {
        akvc_fb_close(_consumer);
        _consumer = NULL;
    }
    if (_latestClientSampleBuffer != nil) {
        CFRelease(_latestClientSampleBuffer);
        _latestClientSampleBuffer = nil;
    }
}

- (BOOL)selectFormatAtIndex:(NSUInteger)formatIndex error:(NSError* _Nullable __autoreleasing*)outError {
    @synchronized(self) {
        if (formatIndex >= self.streamFormats.count) {
            if (outError != nil) {
                *outError = AKVCFrameProviderError(1, @"unsupported stream format index");
            }
            return NO;
        }

        _activeFormatIndex = formatIndex;
        if (![self rebuildPixelBufferPool:outError]) {
            return NO;
        }
    }
    [self synchronizeFallbackSampleBufferSourceToActiveFormat];
    return YES;
}

- (BOOL)selectFrameDuration:(CMTime)frameDuration error:(NSError* _Nullable __autoreleasing*)outError {
    @synchronized(self) {
        if (![self isSupportedFrameDuration:frameDuration]) {
            if (outError != nil) {
                *outError = AKVCFrameProviderError(2, @"unsupported frame duration");
            }
            return NO;
        }
        _activeFrameDuration = frameDuration;
    }
    return YES;
}

- (void)setFallbackSampleBufferSource:(id<AKVCSampleBufferSource>)fallbackSampleBufferSource {
    @synchronized(self) {
        _fallbackSampleBufferSource = fallbackSampleBufferSource;
    }
    [self synchronizeFallbackSampleBufferSourceToActiveFormat];
}

- (void)closeFrameReader {
    @synchronized(self) {
        if (_consumer != NULL) {
            akvc_fb_close(_consumer);
            _consumer = NULL;
        }
    }
}

- (void)storeClientSampleBuffer:(CMSampleBufferRef)sampleBuffer
                  discontinuity:(CMIOExtensionStreamDiscontinuityFlags)discontinuity {
    if (sampleBuffer == nil) {
        return;
    }

    @synchronized(self) {
        NSError* formatError = nil;
        if (![self ensureFormatForClientSampleBuffer:sampleBuffer error:&formatError]) {
            return;
        }
        if (_latestClientSampleBuffer != nil) {
            CFRelease(_latestClientSampleBuffer);
        }
        _latestClientSampleBuffer = (CMSampleBufferRef)CFRetain(sampleBuffer);
        _latestClientDiscontinuity = discontinuity;
    }
}

- (CMSampleBufferRef)copyLatestClientSampleBufferWithDiscontinuity:
                           (CMIOExtensionStreamDiscontinuityFlags*)outDiscontinuity
                                                        error:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    @synchronized(self) {
        if (outDiscontinuity != nil) {
            *outDiscontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
        }
        if (_latestClientSampleBuffer == nil) {
            return nil;
        }
        CMSampleBufferRef retainedSampleBuffer = (CMSampleBufferRef)CFRetain(_latestClientSampleBuffer);
        if (outDiscontinuity != nil) {
            *outDiscontinuity = _latestClientDiscontinuity;
        }
        CFRelease(_latestClientSampleBuffer);
        _latestClientSampleBuffer = nil;
        _latestClientDiscontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
        return retainedSampleBuffer;
    }
}

- (CMSampleBufferRef)copyNextSampleBufferWithStatus:(AKVCFrameReadStatus*)outStatus
                                      discontinuity:(CMIOExtensionStreamDiscontinuityFlags*)outDiscontinuity
                                              error:(NSError* _Nullable __autoreleasing*)outError {
    @synchronized(self) {
        if (outStatus != nil) {
            *outStatus = AKVCFrameReadStatusError;
        }
        if (outDiscontinuity != nil) {
            *outDiscontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
        }

        NSError* openError = nil;
        [self refreshSharedMemoryConfigurationIfNeeded];
        if (![self ensureFrameReaderOpen:&openError]) {
            if (outStatus != nil) {
                *outStatus = AKVCFrameReadStatusNoProducer;
            }
            if (outError != nil) {
                *outError = openError;
            }
            return nil;
        }

        akvc_fb_view_t view = {};
        akvc_status_t status = akvc_fb_poll(_consumer, &view);
        if (status == AKVC_OK) {
            CMSampleBufferRef sampleBuffer = [self copySampleBufferFromView:&view
                                                              discontinuity:outDiscontinuity
                                                                      error:outError];
            if (sampleBuffer != nil && outStatus != nil) {
                *outStatus = AKVCFrameReadStatusFrameReady;
            }
            return sampleBuffer;
        }

        if (status == E_AKVC_FRAMEBUS_TIMEOUT) {
            if (outStatus != nil) {
                *outStatus = akvc_fb_producer_alive(_consumer) ? AKVCFrameReadStatusTimedOut : AKVCFrameReadStatusNoProducer;
            }
            return nil;
        }

        if (status == E_AKVC_FRAMEBUS_TORN_FRAME) {
            if (outStatus != nil) {
                *outStatus = AKVCFrameReadStatusTorn;
            }
            return nil;
        }

        if (status == E_AKVC_FRAMEBUS_OPEN_FAILED) {
            [self closeFrameReader];
            if (outStatus != nil) {
                *outStatus = AKVCFrameReadStatusNoProducer;
            }
            return nil;
        }

        if (outError != nil) {
            *outError = AKVCFrameProviderError(3, @"shared frame reader returned an unexpected error");
        }
        if (outStatus != nil) {
            *outStatus = AKVCFrameReadStatusError;
        }
    }
    return nil;
}

- (CMSampleBufferRef)copyFallbackSampleBuffer:(NSError* _Nullable __autoreleasing*)outError {
    @synchronized(self) {
        id<AKVCSampleBufferSource> fallbackSampleBufferSource = _fallbackSampleBufferSource;
        if (fallbackSampleBufferSource != nil && akvc_macos_demo_mode_enabled() != 0) {
            CMSampleBufferRef sampleBuffer =
                [fallbackSampleBufferSource copyNextSampleBufferWithPresentationTime:CMClockGetTime(CMClockGetHostTimeClock())
                                                                               error:outError];
            if (sampleBuffer == nil) {
                return nil;
            }

            NSError* formatError = nil;
            if (![self ensureFormatForClientSampleBuffer:sampleBuffer error:&formatError]) {
                CFRelease(sampleBuffer);
                if (outError != nil) {
                    *outError = formatError;
                }
                return nil;
            }
            return sampleBuffer;
        }

        return [self copyPlaceholderSampleBuffer:outError];
    }
}

- (CMSampleBufferRef)copyPlaceholderSampleBuffer:(NSError* _Nullable __autoreleasing*)outError {
    @synchronized(self) {
        if (_pixelBufferPool == nil) {
            if (![self rebuildPixelBufferPool:outError]) {
                return nil;
            }
        }

        CVPixelBufferRef pixelBuffer = nil;
        CVReturn createStatus = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, _pixelBufferPool, &pixelBuffer);
        if (createStatus != kCVReturnSuccess || pixelBuffer == nil) {
            if (outError != nil) {
                *outError = AKVCFrameProviderError(4, @"failed to allocate placeholder pixel buffer");
            }
            return nil;
        }

        CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, 0);
        if (lockStatus != kCVReturnSuccess) {
            if (outError != nil) {
                *outError = AKVCFrameProviderPixelBufferAccessError(16, @"failed to lock placeholder pixel buffer");
            }
            CFRelease(pixelBuffer);
            return nil;
        }

        size_t planeCount = CVPixelBufferGetPlaneCount(pixelBuffer);
        if (planeCount >= 1) {
            void* base = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0);
            if (base == NULL) {
                CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
                CFRelease(pixelBuffer);
                if (outError != nil) {
                    *outError = AKVCFrameProviderPixelBufferAccessError(17, @"placeholder luma plane returned a null base address");
                }
                return nil;
            }
            size_t height = CVPixelBufferGetHeightOfPlane(pixelBuffer, 0);
            size_t bytesPerRow = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0);
            memset(base, 0x10, bytesPerRow * height);
        }
        if (planeCount >= 2) {
            void* base = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1);
            if (base == NULL) {
                CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
                CFRelease(pixelBuffer);
                if (outError != nil) {
                    *outError = AKVCFrameProviderPixelBufferAccessError(18, @"placeholder chroma plane returned a null base address");
                }
                return nil;
            }
            size_t height = CVPixelBufferGetHeightOfPlane(pixelBuffer, 1);
            size_t bytesPerRow = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1);
            memset(base, 0x80, bytesPerRow * height);
        } else if (planeCount == 0) {
            uint8_t* base = (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
            if (base == NULL) {
                CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
                CFRelease(pixelBuffer);
                if (outError != nil) {
                    *outError = AKVCFrameProviderPixelBufferAccessError(19, @"placeholder pixel buffer returned a null base address");
                }
                return nil;
            }
            size_t height = CVPixelBufferGetHeight(pixelBuffer);
            size_t bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer);
            memset(base, 0x00, bytesPerRow * height);
            for (size_t row = 0; row < height; ++row) {
                uint8_t* rowBase = base + (row * bytesPerRow);
                for (size_t column = 0; column < CVPixelBufferGetWidth(pixelBuffer); ++column) {
                    rowBase[(column * 4) + 3] = 0xFF;
                }
            }
        }
        CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);

        CMSampleBufferRef sampleBuffer = [self copySampleBufferFromPixelBuffer:pixelBuffer
                                                                           pts:CMClockGetTime(CMClockGetHostTimeClock())
                                                                         error:outError];
        CFRelease(pixelBuffer);
        return sampleBuffer;
    }
}

- (uint64_t)nextHostTimeInNanoseconds {
    CMTime hostTime = CMClockGetTime(CMClockGetHostTimeClock());
    CMTime nanos = CMTimeConvertScale(hostTime, 1000000000, kCMTimeRoundingMethod_Default);
    if (!CMTIME_IS_NUMERIC(nanos)) {
        return 0;
    }
    return (uint64_t)MAX((int64_t)0, nanos.value);
}

- (NSArray<CMIOExtensionStreamFormat*>*)buildDefaultFormats {
    NSMutableArray<CMIOExtensionStreamFormat*>* formats = [NSMutableArray arrayWithCapacity:6];
    NSArray<NSValue*>* sizes = @[
        [NSValue valueWithSize:NSMakeSize(1280, 720)],
        [NSValue valueWithSize:NSMakeSize(1920, 1080)],
        [NSValue valueWithSize:NSMakeSize(3840, 2160)],
    ];
    NSArray<NSNumber*>* pixelFormats = @[
        @(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange),
        @(kCVPixelFormatType_32BGRA),
    ];

    NSArray<NSDictionary*>* validFrameDurations = @[
        AKVCCopyTimeDictionary(CMTimeMake(1, 60)),
        AKVCCopyTimeDictionary(CMTimeMake(1, 30)),
    ];

    for (NSNumber* pixelFormatValue in pixelFormats) {
        OSType pixelFormat = (OSType)pixelFormatValue.unsignedIntValue;
        for (NSValue* sizeValue in sizes) {
            NSSize size = sizeValue.sizeValue;
            CMVideoFormatDescriptionRef formatDescription = nil;
            OSStatus status = CMVideoFormatDescriptionCreate(
                kCFAllocatorDefault,
                pixelFormat,
                (int32_t)size.width,
                (int32_t)size.height,
                nil,
                &formatDescription
            );
            if (status != noErr || formatDescription == nil) {
                continue;
            }

            CMIOExtensionStreamFormat* format = [[CMIOExtensionStreamFormat alloc]
                initWithFormatDescription:formatDescription
                         maxFrameDuration:self.maximumFrameDuration
                         minFrameDuration:self.minimumFrameDuration
                      validFrameDurations:validFrameDurations];
            [formats addObject:format];
            CFRelease(formatDescription);
        }
    }

    return [formats copy];
}

- (BOOL)rebuildPixelBufferPool:(NSError* _Nullable __autoreleasing*)outError {
    if (_pixelBufferPool != nil) {
        CFRelease(_pixelBufferPool);
        _pixelBufferPool = nil;
    }

    CMIOExtensionStreamFormat* format = self.streamFormats[self.activeFormatIndex];
    CMVideoDimensions dimensions = CMVideoFormatDescriptionGetDimensions((CMVideoFormatDescriptionRef)format.formatDescription);
    OSType pixelFormat = CMFormatDescriptionGetMediaSubType((CMFormatDescriptionRef)format.formatDescription);
    NSDictionary* attributes = @{
        (NSString*)kCVPixelBufferPixelFormatTypeKey: @(pixelFormat),
        (NSString*)kCVPixelBufferWidthKey: @(dimensions.width),
        (NSString*)kCVPixelBufferHeightKey: @(dimensions.height),
        (NSString*)kCVPixelBufferIOSurfacePropertiesKey: @{},
    };

    CVReturn createStatus = CVPixelBufferPoolCreate(
        kCFAllocatorDefault,
        nil,
        (__bridge CFDictionaryRef)attributes,
        &_pixelBufferPool
    );
    if (createStatus != kCVReturnSuccess || _pixelBufferPool == nil) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(5, @"failed to create pixel buffer pool");
        }
        return NO;
    }
    return YES;
}

- (void)refreshSharedMemoryConfigurationIfNeeded {
    akvc_macos_ring_descriptor_t descriptor = {};
    akvc_macos_ring_descriptor_default(&descriptor);

    NSString* currentSharedMemoryName = [NSString stringWithUTF8String:descriptor.shm_name];
    if (currentSharedMemoryName.length == 0) {
        return;
    }

    BOOL sharedMemoryNameChanged = ![currentSharedMemoryName isEqualToString:self.sharedMemoryName];
    BOOL slotShapeChanged = descriptor.slot_count != self.slotCount || descriptor.slot_size != self.slotSize;
    if (!sharedMemoryNameChanged && !slotShapeChanged) {
        return;
    }

    _slotCount = descriptor.slot_count;
    _slotSize = descriptor.slot_size;
    if (sharedMemoryNameChanged) {
        _sharedMemoryName = [currentSharedMemoryName copy];
        [self closeFrameReader];
        _pendingConfigurationDiscontinuity = YES;
    }
}

- (BOOL)ensureFrameReaderOpen:(NSError* _Nullable __autoreleasing*)outError {
    if (_consumer != NULL) {
        return YES;
    }

    akvc_fb_consumer_t* consumer = NULL;
    const char* shmName = self.sharedMemoryName.UTF8String;
    akvc_status_t status = akvc_fb_open_named(&consumer, shmName);
    if (status == AKVC_OK) {
        _consumer = consumer;
        return YES;
    }

    if (outError == nil) {
        return NO;
    }
    switch (status) {
        case E_AKVC_FRAMEBUS_OPEN_FAILED:
            *outError = AKVCFrameProviderError(6, @"shared frame region is not available yet");
            return NO;
        case E_AKVC_FRAMEBUS_SCHEMA_MISMATCH:
            *outError = AKVCFrameProviderError(7, @"shared frame region schema mismatch");
            return NO;
        default:
            *outError = AKVCFrameProviderError(8, @"failed to open shared frame reader");
            return NO;
    }
}

- (CMSampleBufferRef)copySampleBufferFromView:(const akvc_fb_view_t*)view
                                discontinuity:(CMIOExtensionStreamDiscontinuityFlags*)outDiscontinuity
                                        error:(NSError* _Nullable __autoreleasing*)outError {
    if (view == NULL || view->header == NULL) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(9, @"frame view is empty");
        }
        return nil;
    }

    const akvc_frame_header_t* header = view->header;
    if (header->fourcc != AKVC_FOURCC_NV12) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(10, @"only NV12 frames are supported by the current macOS camera extension path");
        }
        return nil;
    }

    NSError* formatError = nil;
    if (![self ensureFormatForDimensionsWithWidth:header->width height:header->height error:&formatError]) {
        if (outError != nil) {
            *outError = formatError;
        }
        return nil;
    }

    if (_pixelBufferPool == nil && ![self rebuildPixelBufferPool:outError]) {
        return nil;
    }

    CVPixelBufferRef pixelBuffer = nil;
    CVReturn createStatus = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, _pixelBufferPool, &pixelBuffer);
    if (createStatus != kCVReturnSuccess || pixelBuffer == nil) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(11, @"failed to allocate pixel buffer for shared frame");
        }
        return nil;
    }

    CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, 0);
    if (lockStatus != kCVReturnSuccess) {
        if (outError != nil) {
            *outError = AKVCFrameProviderPixelBufferAccessError(20, @"failed to lock shared-frame pixel buffer");
        }
        CFRelease(pixelBuffer);
        return nil;
    }

    if (CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) == NULL
        || CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1) == NULL) {
        CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
        CFRelease(pixelBuffer);
        if (outError != nil) {
            *outError = AKVCFrameProviderPixelBufferAccessError(21, @"shared-frame pixel buffer returned a null plane base address");
        }
        return nil;
    }
    [self copyNV12FrameHeader:header plane0:view->plane0 plane1:view->plane1 pixelBuffer:pixelBuffer];
    CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);

    if (outDiscontinuity != nil) {
        *outDiscontinuity = [self discontinuityForFrameFlags:header->flags];
        if (_pendingConfigurationDiscontinuity) {
            *outDiscontinuity |= CMIOExtensionStreamDiscontinuityFlagTime;
        }
    }
    _pendingConfigurationDiscontinuity = NO;

    CMSampleBufferRef sampleBuffer = [self copySampleBufferFromPixelBuffer:pixelBuffer
                                                                       pts:CMClockGetTime(CMClockGetHostTimeClock())
                                                                     error:outError];
    CFRelease(pixelBuffer);
    return sampleBuffer;
}

- (void)synchronizeFallbackSampleBufferSourceToActiveFormat {
    id<AKVCSampleBufferSource> fallbackSampleBufferSource = nil;
    CMIOExtensionStreamFormat* format = nil;
    @synchronized(self) {
        fallbackSampleBufferSource = _fallbackSampleBufferSource;
        format = self.streamFormats[self.activeFormatIndex];
    }
    if (fallbackSampleBufferSource == nil) {
        return;
    }

    CMVideoDimensions dimensions =
        CMVideoFormatDescriptionGetDimensions((CMVideoFormatDescriptionRef)format.formatDescription);
    OSType pixelFormat = CMFormatDescriptionGetMediaSubType((CMFormatDescriptionRef)format.formatDescription);
    [fallbackSampleBufferSource updatePreferredWidth:(size_t)dimensions.width
                                             height:(size_t)dimensions.height
                                        pixelFormat:pixelFormat];
}

- (void)copyNV12FrameHeader:(const akvc_frame_header_t*)header
                     plane0:(const uint8_t*)plane0
                     plane1:(const uint8_t*)plane1
                pixelBuffer:(CVPixelBufferRef)pixelBuffer {
    size_t yRows = header->height;
    size_t uvRows = header->height / 2;

    uint8_t* yDestination = (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0);
    uint8_t* uvDestination = (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1);
    size_t yDestinationStride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0);
    size_t uvDestinationStride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1);

    [self copyPlane:plane0 srcStride:header->stride[0] dst:yDestination dstStride:yDestinationStride height:yRows];
    if (plane1 != NULL) {
        [self copyPlane:plane1 srcStride:header->stride[1] dst:uvDestination dstStride:uvDestinationStride height:uvRows];
    }
}

- (void)copyPlane:(const uint8_t*)src
        srcStride:(size_t)srcStride
              dst:(uint8_t*)dst
        dstStride:(size_t)dstStride
           height:(size_t)height {
    if (src == NULL || dst == NULL) {
        return;
    }
    size_t rowBytes = MIN(srcStride, dstStride);
    for (size_t row = 0; row < height; ++row) {
        memcpy(dst + (row * dstStride), src + (row * srcStride), rowBytes);
    }
}

- (CMSampleBufferRef)copySampleBufferFromPixelBuffer:(CVPixelBufferRef)pixelBuffer
                                                 pts:(CMTime)presentationTimeStamp
                                               error:(NSError* _Nullable __autoreleasing*)outError {
    CMIOExtensionStreamFormat* format = self.streamFormats[self.activeFormatIndex];
    CMSampleTimingInfo timing = {
        .duration = self.activeFrameDuration,
        .presentationTimeStamp = presentationTimeStamp,
        .decodeTimeStamp = kCMTimeInvalid,
    };

    CMSampleBufferRef sampleBuffer = nil;
    OSStatus sampleStatus = CMSampleBufferCreateReadyWithImageBuffer(
        kCFAllocatorDefault,
        pixelBuffer,
        (CMVideoFormatDescriptionRef)format.formatDescription,
        &timing,
        &sampleBuffer
    );
    if (sampleStatus != noErr || sampleBuffer == nil) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(12, @"failed to create CMSampleBuffer");
        }
        return nil;
    }
    return sampleBuffer;
}

- (CMIOExtensionStreamDiscontinuityFlags)discontinuityForFrameFlags:(uint32_t)flags {
    CMIOExtensionStreamDiscontinuityFlags discontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
    if ((flags & AKVC_FLAG_DISCONTINUITY) != 0) {
        discontinuity |= CMIOExtensionStreamDiscontinuityFlagTime;
    }
    if ((flags & AKVC_FLAG_STALE) != 0) {
        discontinuity |= CMIOExtensionStreamDiscontinuityFlagSampleDropped;
    }
    if ((flags & AKVC_FLAG_ERROR) != 0) {
        discontinuity |= CMIOExtensionStreamDiscontinuityFlagUnknown;
    }
    return discontinuity;
}

- (BOOL)ensureFormatForDimensionsWithWidth:(uint32_t)width
                                    height:(uint32_t)height
                                     error:(NSError* _Nullable __autoreleasing*)outError {
    NSUInteger matchedIndex = NSNotFound;
    for (NSUInteger index = 0; index < self.streamFormats.count; ++index) {
        CMIOExtensionStreamFormat* format = self.streamFormats[index];
        CMVideoDimensions dimensions =
            CMVideoFormatDescriptionGetDimensions((CMVideoFormatDescriptionRef)format.formatDescription);
        OSType pixelFormat = CMFormatDescriptionGetMediaSubType((CMFormatDescriptionRef)format.formatDescription);
        if ((uint32_t)dimensions.width == width
            && (uint32_t)dimensions.height == height
            && pixelFormat == kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange) {
            matchedIndex = index;
            break;
        }
    }

    if (matchedIndex == NSNotFound) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(13, @"incoming shared-memory frame dimensions are not in the supported CMIO format set");
        }
        return NO;
    }

    if (matchedIndex == self.activeFormatIndex) {
        return YES;
    }

    return [self selectFormatAtIndex:matchedIndex error:outError];
}

- (BOOL)ensureFormatForClientSampleBuffer:(CMSampleBufferRef)sampleBuffer
                                    error:(NSError* _Nullable __autoreleasing*)outError {
    CVImageBufferRef imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer);
    if (imageBuffer == nil) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(14, @"client sample buffer does not contain an image buffer");
        }
        return NO;
    }

    OSType pixelFormat = CVPixelBufferGetPixelFormatType(imageBuffer);
    uint32_t width = (uint32_t)CVPixelBufferGetWidth(imageBuffer);
    uint32_t height = (uint32_t)CVPixelBufferGetHeight(imageBuffer);

    NSUInteger matchedIndex = NSNotFound;
    for (NSUInteger index = 0; index < self.streamFormats.count; ++index) {
        CMIOExtensionStreamFormat* format = self.streamFormats[index];
        CMVideoDimensions dimensions =
            CMVideoFormatDescriptionGetDimensions((CMVideoFormatDescriptionRef)format.formatDescription);
        OSType candidatePixelFormat = CMFormatDescriptionGetMediaSubType((CMFormatDescriptionRef)format.formatDescription);
        if ((uint32_t)dimensions.width == width
            && (uint32_t)dimensions.height == height
            && candidatePixelFormat == pixelFormat) {
            matchedIndex = index;
            break;
        }
    }

    if (matchedIndex == NSNotFound) {
        if (outError != nil) {
            *outError = AKVCFrameProviderError(15, @"incoming client frame dimensions or pixel format are not in the supported CMIO format set");
        }
        return NO;
    }

    if (matchedIndex != self.activeFormatIndex && ![self selectFormatAtIndex:matchedIndex error:outError]) {
        return NO;
    }

    CMTime duration = CMSampleBufferGetDuration(sampleBuffer);
    if ([self isSupportedFrameDuration:duration]) {
        [self selectFrameDuration:duration error:nil];
    }
    return YES;
}

- (BOOL)isSupportedFrameDuration:(CMTime)frameDuration {
    if (!CMTIME_IS_NUMERIC(frameDuration)) {
        return NO;
    }
    return CMTimeCompare(frameDuration, CMTimeMake(1, 30)) == 0
        || CMTimeCompare(frameDuration, CMTimeMake(1, 60)) == 0;
}

@end
