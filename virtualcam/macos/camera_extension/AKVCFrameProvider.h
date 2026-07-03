// SPDX-License-Identifier: Apache-2.0
#import <CoreMedia/CoreMedia.h>
#import <CoreMediaIO/CoreMediaIO.h>
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, AKVCFrameReadStatus) {
    AKVCFrameReadStatusFrameReady = 0,
    AKVCFrameReadStatusTimedOut = 1,
    AKVCFrameReadStatusNoProducer = 2,
    AKVCFrameReadStatusTorn = 3,
    AKVCFrameReadStatusError = 4,
};

@protocol AKVCSampleBufferSource <NSObject>

- (void)updatePreferredWidth:(size_t)width height:(size_t)height pixelFormat:(OSType)pixelFormat;
- (CMSampleBufferRef _Nullable)copyNextSampleBufferWithPresentationTime:(CMTime)presentationTime
                                                                  error:(NSError* _Nullable* _Nullable)outError
    CF_RETURNS_RETAINED;

@end

@interface AKVCFrameProvider : NSObject

@property(nonatomic, copy, readonly) NSString* sharedMemoryName;
@property(nonatomic, assign, readonly) uint32_t slotCount;
@property(nonatomic, assign, readonly) uint32_t slotSize;
@property(nonatomic, copy, readonly) NSArray<CMIOExtensionStreamFormat*>* streamFormats;
@property(nonatomic, assign, readonly) NSUInteger activeFormatIndex;
@property(nonatomic, assign, readonly) CMTime activeFrameDuration;
@property(nonatomic, assign, readonly) CMTime minimumFrameDuration;
@property(nonatomic, assign, readonly) CMTime maximumFrameDuration;

- (instancetype)initWithSharedMemoryName:(NSString*)sharedMemoryName
                               slotCount:(uint32_t)slotCount
                                slotSize:(uint32_t)slotSize;
- (BOOL)selectFormatAtIndex:(NSUInteger)formatIndex error:(NSError* _Nullable* _Nullable)outError;
- (BOOL)selectFrameDuration:(CMTime)frameDuration error:(NSError* _Nullable* _Nullable)outError;
- (void)setFallbackSampleBufferSource:(id<AKVCSampleBufferSource> _Nullable)fallbackSampleBufferSource;
- (void)closeFrameReader;
- (void)storeClientSampleBuffer:(CMSampleBufferRef)sampleBuffer
                  discontinuity:(CMIOExtensionStreamDiscontinuityFlags)discontinuity;
- (CMSampleBufferRef _Nullable)copyLatestClientSampleBufferWithDiscontinuity:
                                   (CMIOExtensionStreamDiscontinuityFlags*)outDiscontinuity
                                                                error:(NSError* _Nullable* _Nullable)outError
    CF_RETURNS_RETAINED;
- (CMSampleBufferRef _Nullable)copyNextSampleBufferWithStatus:(AKVCFrameReadStatus*)outStatus
                                                discontinuity:(CMIOExtensionStreamDiscontinuityFlags*)outDiscontinuity
                                                        error:(NSError* _Nullable* _Nullable)outError CF_RETURNS_RETAINED;
- (CMSampleBufferRef _Nullable)copyFallbackSampleBuffer:(NSError* _Nullable* _Nullable)outError CF_RETURNS_RETAINED;
- (CMSampleBufferRef _Nullable)copyPlaceholderSampleBuffer:(NSError* _Nullable* _Nullable)outError CF_RETURNS_RETAINED;
- (uint64_t)nextHostTimeInNanoseconds;

@end

NS_ASSUME_NONNULL_END
