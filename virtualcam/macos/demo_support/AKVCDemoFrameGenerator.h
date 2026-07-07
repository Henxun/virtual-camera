// SPDX-License-Identifier: Apache-2.0
#import <CoreMedia/CoreMedia.h>
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@protocol AKVCSampleBufferSource;

@interface AKVCDemoFrameGenerator : NSObject

- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithWidth:(size_t)width height:(size_t)height NS_DESIGNATED_INITIALIZER;
- (void)updatePreferredWidth:(size_t)width height:(size_t)height pixelFormat:(OSType)pixelFormat;
- (CMSampleBufferRef _Nullable)copyNextSampleBufferWithPresentationTime:(CMTime)presentationTime
                                                                  error:(NSError* _Nullable* _Nullable)outError
    CF_RETURNS_RETAINED;

@end

NS_ASSUME_NONNULL_END
