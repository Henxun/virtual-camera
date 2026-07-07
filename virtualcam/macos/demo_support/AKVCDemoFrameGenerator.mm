// SPDX-License-Identifier: Apache-2.0
#import "AKVCDemoFrameGenerator.h"

#import <CoreVideo/CoreVideo.h>

static NSString* const AKVCDemoFrameGeneratorErrorDomain = @"com.akvc.macos.demo-support.frame-generator";

static NSError* AKVCDemoFrameGeneratorError(NSInteger code, NSString* description) {
    return [NSError errorWithDomain:AKVCDemoFrameGeneratorErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

@interface AKVCDemoFrameGenerator () {
    size_t _width;
    size_t _height;
    OSType _pixelFormat;
    uint64_t _frameIndex;
}
@end

@implementation AKVCDemoFrameGenerator

- (instancetype)initWithWidth:(size_t)width height:(size_t)height {
    self = [super init];
    if (self == nil) {
        return nil;
    }

    _width = width;
    _height = height;
    _pixelFormat = kCVPixelFormatType_32BGRA;
    _frameIndex = 0;
    return self;
}

- (CMSampleBufferRef)copyNextSampleBufferWithPresentationTime:(CMTime)presentationTime
                                                        error:(NSError* _Nullable __autoreleasing*)outError {
    size_t width = 0;
    size_t height = 0;
    OSType pixelFormat = kCVPixelFormatType_32BGRA;
    uint64_t frameIndex = 0;
    @synchronized(self) {
        width = _width;
        height = _height;
        pixelFormat = _pixelFormat;
        frameIndex = _frameIndex;
        _frameIndex += 1;
    }

    if (width == 0 || height == 0) {
        if (outError != nil) {
            *outError = AKVCDemoFrameGeneratorError(1, @"demo frame generator requires a non-zero size");
        }
        return nil;
    }

    CVPixelBufferRef pixelBuffer = nil;
    NSDictionary* attributes = @{
        (id)kCVPixelBufferCGImageCompatibilityKey: @YES,
        (id)kCVPixelBufferCGBitmapContextCompatibilityKey: @YES,
    };
    CVReturn pixelBufferStatus = CVPixelBufferCreate(kCFAllocatorDefault,
                                                     width,
                                                     height,
                                                     pixelFormat,
                                                     (__bridge CFDictionaryRef)attributes,
                                                     &pixelBuffer);
    if (pixelBufferStatus != kCVReturnSuccess || pixelBuffer == nil) {
        if (outError != nil) {
            *outError = AKVCDemoFrameGeneratorError(2, @"failed to allocate demo pixel buffer");
        }
        return nil;
    }

    CVReturn lockStatus = CVPixelBufferLockBaseAddress(pixelBuffer, 0);
    if (lockStatus != kCVReturnSuccess) {
        CFRelease(pixelBuffer);
        if (outError != nil) {
            *outError = AKVCDemoFrameGeneratorError(3, @"failed to lock demo pixel buffer");
        }
        return nil;
    }

    uint8_t* baseAddress = (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
    if (baseAddress == nil) {
        CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
        CFRelease(pixelBuffer);
        if (outError != nil) {
            *outError = AKVCDemoFrameGeneratorError(4, @"demo pixel buffer returned a null base address");
        }
        return nil;
    }

    size_t bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer);
    uint8_t phase = (uint8_t)(frameIndex % 255);
    size_t planeCount = CVPixelBufferGetPlaneCount(pixelBuffer);
    if (planeCount >= 2) {
        uint8_t* lumaBase = (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0);
        uint8_t* chromaBase = (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1);
        if (lumaBase == nil || chromaBase == nil) {
            CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
            CFRelease(pixelBuffer);
            if (outError != nil) {
                *outError = AKVCDemoFrameGeneratorError(5, @"demo NV12 pixel buffer returned a null plane base address");
            }
            return nil;
        }

        size_t lumaBytesPerRow = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0);
        size_t chromaBytesPerRow = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1);
        for (size_t y = 0; y < height; ++y) {
            uint8_t* row = lumaBase + (y * lumaBytesPerRow);
            for (size_t x = 0; x < width; ++x) {
                row[x] = (uint8_t)((x + y + phase) % 255);
            }
        }
        for (size_t y = 0; y < height / 2; ++y) {
            uint8_t* row = chromaBase + (y * chromaBytesPerRow);
            for (size_t x = 0; x < width; x += 2) {
                row[x + 0] = (uint8_t)(0x80 + (phase % 32));
                row[x + 1] = (uint8_t)(0x80 - (phase % 32));
            }
        }
    } else {
        for (size_t y = 0; y < height; ++y) {
            uint8_t* row = baseAddress + (y * bytesPerRow);
            for (size_t x = 0; x < width; ++x) {
                size_t pixelOffset = x * 4;
                row[pixelOffset + 0] = (uint8_t)((x + phase) % 255);
                row[pixelOffset + 1] = (uint8_t)((y + (phase * 2)) % 255);
                row[pixelOffset + 2] = (uint8_t)((x + y + (phase * 3)) % 255);
                row[pixelOffset + 3] = 0xFF;
            }
        }
        // Paint a deterministic corner marker so the generated feed is easy to
        // recognize during manual validation in tools like QuickTime or OBS.
        baseAddress[0] = 0x10;
        baseAddress[1] = 0xA0;
        baseAddress[2] = 0xF0;
        baseAddress[3] = 0xFF;
    }
    CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);

    CMVideoFormatDescriptionRef formatDescription = nil;
    OSStatus formatStatus =
        CMVideoFormatDescriptionCreateForImageBuffer(kCFAllocatorDefault, pixelBuffer, &formatDescription);
    if (formatStatus != noErr || formatDescription == nil) {
        CFRelease(pixelBuffer);
        if (outError != nil) {
            *outError = AKVCDemoFrameGeneratorError(6, @"failed to create demo format description");
        }
        return nil;
    }

    CMSampleTimingInfo timing = {
        .duration = kCMTimeInvalid,
        .presentationTimeStamp = presentationTime,
        .decodeTimeStamp = kCMTimeInvalid,
    };
    CMSampleBufferRef sampleBuffer = nil;
    OSStatus sampleStatus = CMSampleBufferCreateReadyWithImageBuffer(kCFAllocatorDefault,
                                                                     pixelBuffer,
                                                                     formatDescription,
                                                                     &timing,
                                                                     &sampleBuffer);
    CFRelease(formatDescription);
    CFRelease(pixelBuffer);

    if (sampleStatus != noErr || sampleBuffer == nil) {
        if (outError != nil) {
            *outError = AKVCDemoFrameGeneratorError(7, @"failed to create demo sample buffer");
        }
        return nil;
    }

    return sampleBuffer;
}

- (void)updatePreferredWidth:(size_t)width height:(size_t)height pixelFormat:(OSType)pixelFormat {
    @synchronized(self) {
        _width = width;
        _height = height;
        _pixelFormat = pixelFormat;
    }
}

@end
