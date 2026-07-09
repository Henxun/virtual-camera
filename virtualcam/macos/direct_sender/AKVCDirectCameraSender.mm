// SPDX-License-Identifier: Apache-2.0
#import "AKVCDirectCameraSender.h"

#import <AVFoundation/AVFoundation.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreMediaIO/CMIOHardware.h>
#import <CoreMediaIO/CMIOHardwareStream.h>
#import <CoreMediaIO/CoreMediaIO.h>
#import <CoreVideo/CoreVideo.h>
#import <dispatch/dispatch.h>
#import <Foundation/Foundation.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>

namespace {

static int const kAKVCDirectPixelFormat = kCVPixelFormatType_32BGRA;

static NSDictionary* AKVCCameraAuthorizationSnapshot(void) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
    NSString* status_name = @"unknown";
    switch (status) {
        case AVAuthorizationStatusAuthorized:
            status_name = @"authorized";
            break;
        case AVAuthorizationStatusDenied:
            status_name = @"denied";
            break;
        case AVAuthorizationStatusRestricted:
            status_name = @"restricted";
            break;
        case AVAuthorizationStatusNotDetermined:
            status_name = @"not_determined";
            break;
    }
    return @{
        @"camera_access_status": status_name,
        @"camera_access_authorized": @(status == AVAuthorizationStatusAuthorized),
        @"camera_access_denied": @(status == AVAuthorizationStatusDenied),
        @"camera_access_restricted": @(status == AVAuthorizationStatusRestricted),
        @"camera_access_not_determined": @(status == AVAuthorizationStatusNotDetermined),
    };
}

static void AKVCWriteError(char* out_error, size_t capacity, NSString* message) {
    if (out_error == nullptr || capacity == 0) {
        return;
    }
    out_error[0] = '\0';
    if (message == nil || message.length == 0) {
        return;
    }
    NSData* data = [message dataUsingEncoding:NSUTF8StringEncoding];
    if (data == nil || data.length == 0) {
        return;
    }
    size_t copy_length = std::min(capacity - 1, static_cast<size_t>(data.length));
    std::memcpy(out_error, data.bytes, copy_length);
    out_error[copy_length] = '\0';
}

static NSString* AKVCStreamDirectionString(CMIOStreamID stream_id) {
    UInt32 direction = 0;
    UInt32 data_size = sizeof(direction);
    UInt32 data_used = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOStreamPropertyDirection,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyData(stream_id, &address, 0, nullptr, data_size, &data_used, &direction);
    if (status != noErr) {
        return nil;
    }
    // CoreMediaIO reports 0 = output stream and 1 = input stream. For the
    // Camera Extension topology we publish frames into the input/sink stream.
    if (direction == 0) {
        return @"source-output";
    }
    if (direction == 1) {
        return @"sink-input";
    }
    return [NSString stringWithFormat:@"%u", direction];
}

static NSString* AKVCCopyCMIODeviceName(CMIODeviceID device_id) {
    UInt32 data_size = 0;
    UInt32 data_used = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOObjectPropertyName,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyDataSize(device_id, &address, 0, nullptr, &data_size);
    if (status != noErr || data_size == 0) {
        return nil;
    }
    CFStringRef name = nullptr;
    status = CMIOObjectGetPropertyData(device_id, &address, 0, nullptr, data_size, &data_used, &name);
    if (status != noErr || name == nullptr) {
        return nil;
    }
    return (__bridge NSString*)name;
}

static NSString* AKVCCopyCMIOObjectName(CMIOObjectID object_id) {
    UInt32 data_size = 0;
    UInt32 data_used = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOObjectPropertyName,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyDataSize(object_id, &address, 0, nullptr, &data_size);
    if (status != noErr || data_size == 0) {
        return nil;
    }

    CFStringRef name = nullptr;
    status = CMIOObjectGetPropertyData(object_id, &address, 0, nullptr, data_size, &data_used, &name);
    if (status != noErr || name == nullptr) {
        return nil;
    }
    return (__bridge NSString*)name;
}

static NSArray<NSString*>* AKVCCopyCMIODeviceNames(void) {
    UInt32 data_size = 0;
    UInt32 data_used = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOHardwarePropertyDevices,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyDataSize(kCMIOObjectSystemObject, &address, 0, nullptr, &data_size);
    if (status != noErr || data_size == 0) {
        return @[];
    }

    NSUInteger device_count = data_size / sizeof(CMIOObjectID);
    std::unique_ptr<CMIOObjectID[]> device_ids(new CMIOObjectID[device_count]);
    status = CMIOObjectGetPropertyData(
        kCMIOObjectSystemObject,
        &address,
        0,
        nullptr,
        data_size,
        &data_used,
        device_ids.get()
    );
    if (status != noErr) {
        return @[];
    }

    NSMutableArray<NSString*>* names = [NSMutableArray array];
    for (NSUInteger index = 0; index < device_count; ++index) {
        NSString* name = AKVCCopyCMIODeviceName(device_ids[index]);
        if (name.length > 0) {
            [names addObject:name];
        }
    }
    return [names copy];
}

static NSArray<NSString*>* AKVCCopyAVFoundationCameraNames(void) {
    NSMutableArray<AVCaptureDeviceType>* device_types = [NSMutableArray arrayWithArray:@[
        AVCaptureDeviceTypeBuiltInWideAngleCamera,
    ]];
    BOOL allow_continuity_camera = NO;
    if (NSBundle.mainBundle != nil) {
        id continuity_value = [NSBundle.mainBundle objectForInfoDictionaryKey:@"NSCameraUseContinuityCameraDeviceType"];
        if ([continuity_value respondsToSelector:@selector(boolValue)]) {
            allow_continuity_camera = [continuity_value boolValue];
        }
    }

    if (@available(macOS 14.0, *)) {
        [device_types addObject:AVCaptureDeviceTypeExternal];
        if (allow_continuity_camera) {
            [device_types addObject:AVCaptureDeviceTypeContinuityCamera];
        }
    } else {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
        [device_types addObject:AVCaptureDeviceTypeExternalUnknown];
#pragma clang diagnostic pop
    }
    if (![device_types containsObject:AVCaptureDeviceTypeExternalUnknown]) {
        [device_types addObject:AVCaptureDeviceTypeExternalUnknown];
    }

    NSMutableArray<NSString*>* names = [NSMutableArray array];
    NSMutableSet<NSString*>* seen = [NSMutableSet set];
    void (^append_name)(NSString*) = ^(NSString* name) {
        if (name == nil || name.length == 0) {
            return;
        }
        NSString* key = name.lowercaseString;
        if ([seen containsObject:key]) {
            return;
        }
        [seen addObject:key];
        [names addObject:name];
    };

    AVCaptureDeviceDiscoverySession* discovery_session =
        [AVCaptureDeviceDiscoverySession discoverySessionWithDeviceTypes:device_types
                                                               mediaType:AVMediaTypeVideo
                                                                position:AVCaptureDevicePositionUnspecified];
    for (AVCaptureDevice* device in discovery_session.devices) {
        append_name(device.localizedName);
    }

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    for (AVCaptureDevice* device in [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo]) {
        append_name(device.localizedName);
    }
#pragma clang diagnostic pop

    return [names copy];
}

static NSArray<NSString*>* AKVCCopyCombinedCameraNames(
    NSArray<NSString*>* avfoundation_names,
    NSArray<NSString*>* cmio_names
) {
    NSMutableArray<NSString*>* names = [NSMutableArray array];
    NSMutableSet<NSString*>* seen = [NSMutableSet set];
    void (^append_name)(NSString*) = ^(NSString* name) {
        if (name == nil || name.length == 0) {
            return;
        }
        NSString* key = name.lowercaseString;
        if ([seen containsObject:key]) {
            return;
        }
        [seen addObject:key];
        [names addObject:name];
    };

    for (NSString* name in avfoundation_names) {
        append_name(name);
    }
    for (NSString* name in cmio_names) {
        append_name(name);
    }
    return [names copy];
}

static NSDictionary* AKVCBuildCameraSnapshot(void) {
    NSArray<NSString*>* avfoundation_names = AKVCCopyAVFoundationCameraNames();
    NSArray<NSString*>* cmio_names = AKVCCopyCMIODeviceNames();
    NSArray<NSString*>* names = AKVCCopyCombinedCameraNames(avfoundation_names, cmio_names);
    NSMutableDictionary* snapshot = [NSMutableDictionary dictionaryWithDictionary:AKVCCameraAuthorizationSnapshot()];
    snapshot[@"all_devices"] = names;
    snapshot[@"avfoundation_devices"] = avfoundation_names;
    snapshot[@"cmio_devices"] = cmio_names;
    snapshot[@"environment_device_enumeration_empty"] = @(names.count == 0);
    return [snapshot copy];
}

static int AKVCWriteSnapshotJSON(
    NSDictionary* snapshot,
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
) {
    if (json_buffer == nullptr || json_capacity == 0) {
        AKVCWriteError(error_message, error_capacity, @"json buffer is null");
        return -1;
    }

    NSError* serialization_error = nil;
    NSData* payload = [NSJSONSerialization dataWithJSONObject:snapshot options:0 error:&serialization_error];
    if (payload == nil) {
        NSString* detail = serialization_error.localizedDescription ?: @"failed to encode device list as JSON";
        AKVCWriteError(error_message, error_capacity, detail);
        return -1;
    }

    size_t copy_length = std::min(json_capacity - 1, static_cast<size_t>(payload.length));
    std::memcpy(json_buffer, payload.bytes, copy_length);
    json_buffer[copy_length] = '\0';
    return 0;
}

static NSDictionary* AKVCRequestCameraAccessSnapshot(NSString** error) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
    if (status == AVAuthorizationStatusNotDetermined) {
        __block BOOL completed = NO;
        dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(
            BOOL granted
        ) {
            (void)granted;
            completed = YES;
            dispatch_semaphore_signal(semaphore);
        }];
        dispatch_time_t timeout = dispatch_time(DISPATCH_TIME_NOW, 30LL * NSEC_PER_SEC);
        long wait_status = dispatch_semaphore_wait(semaphore, timeout);
        if (wait_status != 0 || !completed) {
            if (error != nullptr) {
                *error = @"timed out while waiting for camera access prompt";
            }
            return nil;
        }
    }
    return AKVCBuildCameraSnapshot();
}

static CMTime AKVCPresentationTimeFromPTS100ns(uint64_t pts_100ns) {
    if (pts_100ns == 0) {
        return CMClockGetTime(CMClockGetHostTimeClock());
    }
    int64_t pts_value = 0;
    if (pts_100ns > static_cast<uint64_t>(INT64_MAX)) {
        pts_value = INT64_MAX;
    } else {
        pts_value = static_cast<int64_t>(pts_100ns);
    }
    return CMTimeMake(pts_value, 10000000);
}

class DirectSender final {
public:
    DirectSender(int width, int height, double fps)
        : width_(width),
          height_(height),
          fps_(fps) {
    }

    ~DirectSender() {
        teardown();
    }

    bool start(NSString* camera_name, NSString** error) {
        teardown();

        if (camera_name == nil || camera_name.length == 0) {
            if (error != nullptr) {
                *error = @"camera name must not be empty";
            }
            return false;
        }

        // Request camera permission (TCC) on the main thread before any
        // AVCaptureDevice access. Without permission,
        // AVCaptureDeviceDiscoverySession returns empty -> "camera device not
        // found". A repackaged ad-hoc-signed app is treated as a new identity,
        // so this re-triggers the prompt each rebuild.
        __block BOOL camera_granted = NO;
        dispatch_semaphore_t cam_sem = dispatch_semaphore_create(0);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (@available(macOS 14.0, *)) {
                [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
                    camera_granted = granted;
                    dispatch_semaphore_signal(cam_sem);
                }];
            } else {
                #pragma clang diagnostic push
                #pragma clang diagnostic ignored "-Wdeprecated-declarations"
                [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
                    camera_granted = granted;
                    dispatch_semaphore_signal(cam_sem);
                }];
                #pragma clang diagnostic pop
            }
        });
        dispatch_semaphore_wait(cam_sem, dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_SEC));
        std::fprintf(stderr, "[akvc] camera permission granted=%d\n", (int)camera_granted);
        if (!camera_granted) {
            if (error != nullptr) {
                *error = @"camera permission not granted (System Settings -> Privacy & Security -> Camera)";
            }
            return false;
        }

        AVCaptureDevice* device = findDevice(camera_name);
        if (device != nil) {
            device_id_ = findDeviceObject(device.uniqueID, error);
            if (device_id_ == kCMIOObjectUnknown) {
                return false;
            }
        } else {
            device_id_ = findDeviceObjectByName(camera_name, error);
            if (device_id_ == kCMIOObjectUnknown) {
                if (error != nullptr && (*error == nil || (*error).length == 0)) {
                    *error = [NSString stringWithFormat:@"camera device not found: %@", camera_name];
                }
                return false;
            }
        }

        sink_stream_ = findSinkStream(device_id_, error);
        if (sink_stream_ == kCMIOObjectUnknown) {
            return false;
        }

        if (!createBufferPool(error)) {
            return false;
        }

        OSStatus status = CMIOStreamCopyBufferQueue(
            sink_stream_,
            [](CMIOStreamID, void*, void*) {},
            nullptr,
            &sink_queue_
        );
        if (status != noErr || sink_queue_ == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOStreamCopyBufferQueue failed (%d)", static_cast<int>(status)];
            }
            teardown();
            return false;
        }

        // Negotiate the stream format (BGRA) before StartStream. The
        // CMIOExtension sink stream requires the client to select a format, or
        // CMIODeviceStartStream fails before reaching the extension's
        // startStreamAndReturnError (observed as -7).
        CMIOObjectPropertyAddress fmtAddr = {
            kCMIOStreamPropertyFormatDescription,
            kCMIOObjectPropertyScopeGlobal,
            kCMIOObjectPropertyElementMain,
        };
        CMFormatDescriptionRef fmt = format_description_;
        OSStatus fmtStatus = CMIOObjectSetPropertyData(sink_stream_, &fmtAddr, 0, nullptr,
                                                       sizeof(fmt), &fmt);
        std::fprintf(stderr, "[akvc] sink stream format set (BGRA) status=%d device=0x%x stream=0x%x\n",
                     static_cast<int>(fmtStatus),
                     static_cast<unsigned>(device_id_),
                     static_cast<unsigned>(sink_stream_));

        status = CMIODeviceStartStream(device_id_, sink_stream_);
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIODeviceStartStream failed (%d)", static_cast<int>(status)];
            }
            teardown();
            return false;
        }

        started_ = true;
        consumer_count_ = 1;
        return true;
    }

    bool sendBGR24(
        const uint8_t* data,
        int width,
        int height,
        int bytes_per_row,
        uint64_t pts_100ns,
        NSString** error
    ) {
        if (!started_ || sink_queue_ == nullptr || buffer_pool_ == nullptr || format_description_ == nullptr) {
            if (error != nullptr) {
                *error = @"direct sender is not started";
            }
            return false;
        }
        if (data == nullptr) {
            if (error != nullptr) {
                *error = @"frame data pointer is null";
            }
            return false;
        }
        if (width != width_ || height != height_) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:
                    @"frame size %dx%d does not match configured direct sender size %dx%d",
                    width, height, width_, height_];
            }
            return false;
        }
        if (bytes_per_row < width * 3) {
            if (error != nullptr) {
                *error = @"frame bytes_per_row is smaller than width*3";
            }
            return false;
        }

        CVPixelBufferRef pixel_buffer = nullptr;
        CVReturn cv_error = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, buffer_pool_, &pixel_buffer);
        if (cv_error != kCVReturnSuccess || pixel_buffer == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CVPixelBufferPoolCreatePixelBuffer failed (%d)", static_cast<int>(cv_error)];
            }
            return false;
        }

        CVPixelBufferLockBaseAddress(pixel_buffer, 0);
        uint8_t* destination = static_cast<uint8_t*>(CVPixelBufferGetBaseAddress(pixel_buffer));
        size_t destination_stride = CVPixelBufferGetBytesPerRow(pixel_buffer);
        for (int row = 0; row < height; ++row) {
            const uint8_t* source_row = data + static_cast<size_t>(row) * static_cast<size_t>(bytes_per_row);
            uint8_t* destination_row = destination + static_cast<size_t>(row) * destination_stride;
            for (int column = 0; column < width; ++column) {
                const uint8_t* src = source_row + static_cast<size_t>(column) * 3;
                uint8_t* dst = destination_row + static_cast<size_t>(column) * 4;
                dst[0] = src[0];
                dst[1] = src[1];
                dst[2] = src[2];
                dst[3] = 0xFF;
            }
        }
        CVPixelBufferUnlockBaseAddress(pixel_buffer, 0);

        CMSampleTimingInfo timing_info = {};
        int32_t fps_timescale = static_cast<int32_t>(std::max(1.0, std::round(fps_)));
        timing_info.duration = CMTimeMake(1, fps_timescale);
        timing_info.presentationTimeStamp = AKVCPresentationTimeFromPTS100ns(pts_100ns);

        CMSampleBufferRef sample_buffer = nullptr;
        OSStatus status = CMSampleBufferCreateForImageBuffer(
            kCFAllocatorDefault,
            pixel_buffer,
            YES,
            nullptr,
            nullptr,
            format_description_,
            &timing_info,
            &sample_buffer
        );
        if (status != noErr || sample_buffer == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMSampleBufferCreateForImageBuffer failed (%d)", static_cast<int>(status)];
            }
            CVPixelBufferRelease(pixel_buffer);
            return false;
        }

        if (!ensureSinkQueueCapacity(error)) {
            CFRelease(sample_buffer);
            CVPixelBufferRelease(pixel_buffer);
            return false;
        }

        status = CMSimpleQueueEnqueue(sink_queue_, sample_buffer);
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMSimpleQueueEnqueue failed (%d)", static_cast<int>(status)];
            }
            CFRelease(sample_buffer);
            CVPixelBufferRelease(pixel_buffer);
            return false;
        }

        CVPixelBufferRelease(pixel_buffer);
        return true;
    }

    bool sendBGRA32(
        const uint8_t* data,
        int width,
        int height,
        int bytes_per_row,
        uint64_t pts_100ns,
        NSString** error
    ) {
        if (!started_ || sink_queue_ == nullptr || buffer_pool_ == nullptr || format_description_ == nullptr) {
            if (error != nullptr) {
                *error = @"direct sender is not started";
            }
            return false;
        }
        if (data == nullptr) {
            if (error != nullptr) {
                *error = @"frame data pointer is null";
            }
            return false;
        }
        if (width != width_ || height != height_) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:
                    @"frame size %dx%d does not match configured direct sender size %dx%d",
                    width, height, width_, height_];
            }
            return false;
        }
        if (bytes_per_row < width * 4) {
            if (error != nullptr) {
                *error = @"frame bytes_per_row is smaller than width*4";
            }
            return false;
        }

        CVPixelBufferRef pixel_buffer = nullptr;
        CVReturn cv_error = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, buffer_pool_, &pixel_buffer);
        if (cv_error != kCVReturnSuccess || pixel_buffer == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CVPixelBufferPoolCreatePixelBuffer failed (%d)", static_cast<int>(cv_error)];
            }
            return false;
        }

        CVPixelBufferLockBaseAddress(pixel_buffer, 0);
        uint8_t* destination = static_cast<uint8_t*>(CVPixelBufferGetBaseAddress(pixel_buffer));
        size_t destination_stride = CVPixelBufferGetBytesPerRow(pixel_buffer);
        for (int row = 0; row < height; ++row) {
            const uint8_t* source_row = data + static_cast<size_t>(row) * static_cast<size_t>(bytes_per_row);
            uint8_t* destination_row = destination + static_cast<size_t>(row) * destination_stride;
            std::memcpy(destination_row, source_row, static_cast<size_t>(width) * 4);
        }
        CVPixelBufferUnlockBaseAddress(pixel_buffer, 0);

        CMSampleTimingInfo timing_info = {};
        int32_t fps_timescale = static_cast<int32_t>(std::max(1.0, std::round(fps_)));
        timing_info.duration = CMTimeMake(1, fps_timescale);
        timing_info.presentationTimeStamp = AKVCPresentationTimeFromPTS100ns(pts_100ns);

        CMSampleBufferRef sample_buffer = nullptr;
        OSStatus status = CMSampleBufferCreateForImageBuffer(
            kCFAllocatorDefault,
            pixel_buffer,
            YES,
            nullptr,
            nullptr,
            format_description_,
            &timing_info,
            &sample_buffer
        );
        if (status != noErr || sample_buffer == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMSampleBufferCreateForImageBuffer failed (%d)", static_cast<int>(status)];
            }
            CVPixelBufferRelease(pixel_buffer);
            return false;
        }

        if (!ensureSinkQueueCapacity(error)) {
            CFRelease(sample_buffer);
            CVPixelBufferRelease(pixel_buffer);
            return false;
        }

        status = CMSimpleQueueEnqueue(sink_queue_, sample_buffer);
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMSimpleQueueEnqueue failed (%d)", static_cast<int>(status)];
            }
            CFRelease(sample_buffer);
            CVPixelBufferRelease(pixel_buffer);
            return false;
        }

        CVPixelBufferRelease(pixel_buffer);
        return true;
    }

    int consumerCount() const {
        return consumer_count_;
    }

private:
    bool ensureSinkQueueCapacity(NSString** error) {
        if (sink_queue_ == nullptr) {
            if (error != nullptr) {
                *error = @"sink queue is not available";
            }
            return false;
        }

        int32_t capacity = CMSimpleQueueGetCapacity(sink_queue_);
        if (capacity <= 0) {
            return true;
        }

        while (CMSimpleQueueGetCount(sink_queue_) >= capacity) {
            const void* stale_element = CMSimpleQueueDequeue(sink_queue_);
            if (stale_element == nullptr) {
                break;
            }
            CFRelease(static_cast<CFTypeRef>(const_cast<void*>(stale_element)));
        }

        if (CMSimpleQueueGetCount(sink_queue_) >= capacity) {
            if (error != nullptr) {
                *error = @"sink queue remained full after dropping stale frames";
            }
            return false;
        }
        return true;
    }

    AVCaptureDevice* matchDeviceByName(NSArray<AVCaptureDevice*>* devices, NSString* name) const {
        for (AVCaptureDevice* device in devices) {
            if ([device.localizedName isEqualToString:name]) {
                return device;
            }
        }
        return nil;
    }

    AVCaptureDevice* findDevice(NSString* name) const {
        NSMutableArray<AVCaptureDeviceType>* device_types = [NSMutableArray arrayWithArray:@[
            AVCaptureDeviceTypeBuiltInWideAngleCamera,
        ]];
        BOOL allow_continuity_camera = NO;
        if (NSBundle.mainBundle != nil) {
            id continuity_value = [NSBundle.mainBundle objectForInfoDictionaryKey:@"NSCameraUseContinuityCameraDeviceType"];
            if ([continuity_value respondsToSelector:@selector(boolValue)]) {
                allow_continuity_camera = [continuity_value boolValue];
            }
        }
        if (@available(macOS 14.0, *)) {
            [device_types addObject:AVCaptureDeviceTypeExternal];
            if (allow_continuity_camera) {
                [device_types addObject:AVCaptureDeviceTypeContinuityCamera];
            }
        } else {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
            [device_types addObject:AVCaptureDeviceTypeExternalUnknown];
#pragma clang diagnostic pop
        }
        if (![device_types containsObject:AVCaptureDeviceTypeExternalUnknown]) {
            [device_types addObject:AVCaptureDeviceTypeExternalUnknown];
        }
        // The camera-extension device is exposed asynchronously (the extension
        // process starts on-demand). A one-shot .devices query races the
        // extension startup - poll AVFoundation for up to ~8s until the device
        // appears. (FaceTime's live session sees it; a single background-thread
        // query often does not.)
        const int kMaxAttempts = 16;
        const NSTimeInterval kPollInterval = 0.5;
        for (int attempt = 0; attempt < kMaxAttempts; ++attempt) {
            @autoreleasepool {
                AVCaptureDeviceDiscoverySession* discovery_session =
                    [AVCaptureDeviceDiscoverySession discoverySessionWithDeviceTypes:device_types
                                                                           mediaType:AVMediaTypeVideo
                                                                            position:AVCaptureDevicePositionUnspecified];
                NSMutableString* discovered_names = [NSMutableString string];
                for (AVCaptureDevice* d in discovery_session.devices) {
                    [discovered_names appendFormat:@"[%@] ", d.localizedName];
                }
                std::fprintf(stderr, "[akvc] findDevice attempt %d: %lu device(s): %s (looking for '%s')\n",
                             attempt + 1, (unsigned long)discovery_session.devices.count,
                             [discovered_names UTF8String], [name UTF8String]);
                AVCaptureDevice* matched = matchDeviceByName(discovery_session.devices, name);
                if (matched == nil) {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
                    matched = matchDeviceByName([AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo], name);
#pragma clang diagnostic pop
                }
                if (matched != nil) {
                    return matched;
                }
            }
            if (attempt + 1 < kMaxAttempts) {
                [NSThread sleepForTimeInterval:kPollInterval];
            }
        }
        return nil;
    }

    CMIODeviceID findDeviceObjectByName(NSString* name, NSString** error) const {
        UInt32 data_size = 0;
        UInt32 data_used = 0;
        CMIOObjectPropertyAddress address = {
            kCMIOHardwarePropertyDevices,
            kCMIOObjectPropertyScopeGlobal,
            kCMIOObjectPropertyElementMain,
        };
        OSStatus status = CMIOObjectGetPropertyDataSize(kCMIOObjectSystemObject, &address, 0, nullptr, &data_size);
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOObjectGetPropertyDataSize(devices) failed (%d)", static_cast<int>(status)];
            }
            return kCMIOObjectUnknown;
        }
        if (data_size == 0) {
            if (error != nullptr) {
                *error = @"no system video devices were enumerated via CMIO";
            }
            return kCMIOObjectUnknown;
        }

        NSUInteger device_count = data_size / sizeof(CMIOObjectID);
        std::unique_ptr<CMIOObjectID[]> device_ids(new CMIOObjectID[device_count]);
        status = CMIOObjectGetPropertyData(
            kCMIOObjectSystemObject,
            &address,
            0,
            nullptr,
            data_size,
            &data_used,
            device_ids.get()
        );
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOObjectGetPropertyData(devices) failed (%d)", static_cast<int>(status)];
            }
            return kCMIOObjectUnknown;
        }

        for (NSUInteger index = 0; index < device_count; ++index) {
            CMIODeviceID candidate = device_ids[index];
            NSString* candidate_name = AKVCCopyCMIODeviceName(candidate);
            if ([candidate_name isEqualToString:name]) {
                return candidate;
            }
        }

        if (error != nullptr) {
            *error = [NSString stringWithFormat:@"camera device not found: %@", name];
        }
        return kCMIOObjectUnknown;
    }

    CMIODeviceID findDeviceObject(NSString* unique_id, NSString** error) const {
        UInt32 data_size = 0;
        UInt32 data_used = 0;
        CMIOObjectPropertyAddress address = {
            kCMIOHardwarePropertyDevices,
            kCMIOObjectPropertyScopeGlobal,
            kCMIOObjectPropertyElementMain,
        };
        OSStatus status = CMIOObjectGetPropertyDataSize(kCMIOObjectSystemObject, &address, 0, nullptr, &data_size);
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOObjectGetPropertyDataSize(devices) failed (%d)", static_cast<int>(status)];
            }
            return kCMIOObjectUnknown;
        }
        if (data_size == 0) {
            if (error != nullptr) {
                *error = @"no system video devices were enumerated via CMIO";
            }
            return kCMIOObjectUnknown;
        }

        NSUInteger device_count = data_size / sizeof(CMIOObjectID);
        std::unique_ptr<CMIOObjectID[]> device_ids(new CMIOObjectID[device_count]);
        status = CMIOObjectGetPropertyData(
            kCMIOObjectSystemObject,
            &address,
            0,
            nullptr,
            data_size,
            &data_used,
            device_ids.get()
        );
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOObjectGetPropertyData(devices) failed (%d)", static_cast<int>(status)];
            }
            return kCMIOObjectUnknown;
        }

        for (NSUInteger index = 0; index < device_count; ++index) {
            CMIOObjectID candidate = device_ids[index];
            address.mSelector = kCMIODevicePropertyDeviceUID;
            data_size = 0;
            data_used = 0;
            status = CMIOObjectGetPropertyDataSize(candidate, &address, 0, nullptr, &data_size);
            if (status != noErr || data_size == 0) {
                continue;
            }
            CFStringRef uid = nullptr;
            status = CMIOObjectGetPropertyData(candidate, &address, 0, nullptr, data_size, &data_used, &uid);
            if (status != noErr || uid == nullptr) {
                continue;
            }
            NSString* candidate_uid = (__bridge NSString*)uid;
            if ([candidate_uid isEqualToString:unique_id]) {
                return candidate;
            }
        }

        if (error != nullptr) {
            *error = [NSString stringWithFormat:@"CMIO device UID not found: %@", unique_id];
        }
        return kCMIOObjectUnknown;
    }

    CMIOStreamID findSinkStream(CMIODeviceID device_id, NSString** error) const {
        UInt32 data_size = 0;
        UInt32 data_used = 0;
        CMIOObjectPropertyAddress address = {
            kCMIODevicePropertyStreams,
            kCMIOObjectPropertyScopeGlobal,
            kCMIOObjectPropertyElementMain,
        };
        OSStatus status = CMIOObjectGetPropertyDataSize(device_id, &address, 0, nullptr, &data_size);
        if (status != noErr || data_size == 0) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOObjectGetPropertyDataSize(streams) failed (%d)", static_cast<int>(status)];
            }
            return kCMIOObjectUnknown;
        }

        NSUInteger stream_count = data_size / sizeof(CMIOStreamID);
        std::unique_ptr<CMIOStreamID[]> stream_ids(new CMIOStreamID[stream_count]);
        status = CMIOObjectGetPropertyData(device_id, &address, 0, nullptr, data_size, &data_used, stream_ids.get());
        if (status != noErr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMIOObjectGetPropertyData(streams) failed (%d)", static_cast<int>(status)];
            }
            return kCMIOObjectUnknown;
        }

        for (NSUInteger index = 0; index < stream_count; ++index) {
            CMIOStreamID candidate = stream_ids[index];
            NSString* stream_name = AKVCCopyCMIOObjectName(candidate);
            if ([stream_name localizedCaseInsensitiveContainsString:@"sink"]) {
                return candidate;
            }
        }

        for (NSUInteger index = 0; index < stream_count; ++index) {
            CMIOStreamID candidate = stream_ids[index];
            NSString* direction = AKVCStreamDirectionString(candidate);
            if ([direction isEqualToString:@"sink-input"]) {
                return candidate;
            }
        }

        if (stream_count >= 2) {
            return stream_ids[1];
        }

        if (error != nullptr) {
            *error = @"sink stream not found on CMIO device";
        }
        return kCMIOObjectUnknown;
    }

    bool createBufferPool(NSString** error) {
        teardownBufferResources();

        NSDictionary* pixel_buffer_attributes = @{
            (id)kCVPixelBufferWidthKey: @(width_),
            (id)kCVPixelBufferHeightKey: @(height_),
            (id)kCVPixelBufferPixelFormatTypeKey: @(kAKVCDirectPixelFormat),
            (id)kCVPixelBufferIOSurfacePropertiesKey: @{},
        };
        CVReturn cv_error = CVPixelBufferPoolCreate(
            kCFAllocatorDefault,
            nullptr,
            (__bridge CFDictionaryRef)pixel_buffer_attributes,
            &buffer_pool_
        );
        if (cv_error != kCVReturnSuccess || buffer_pool_ == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CVPixelBufferPoolCreate failed (%d)", static_cast<int>(cv_error)];
            }
            return false;
        }

        OSStatus status = CMVideoFormatDescriptionCreate(
            kCFAllocatorDefault,
            kAKVCDirectPixelFormat,
            width_,
            height_,
            nullptr,
            &format_description_
        );
        if (status != noErr || format_description_ == nullptr) {
            if (error != nullptr) {
                *error = [NSString stringWithFormat:@"CMVideoFormatDescriptionCreate failed (%d)", static_cast<int>(status)];
            }
            teardownBufferResources();
            return false;
        }
        return true;
    }

    void teardownBufferResources() {
        if (format_description_ != nullptr) {
            CFRelease(format_description_);
            format_description_ = nullptr;
        }
        if (buffer_pool_ != nullptr) {
            CVPixelBufferPoolRelease(buffer_pool_);
            buffer_pool_ = nullptr;
        }
    }

    void teardown() {
        if (started_ && device_id_ != kCMIOObjectUnknown && sink_stream_ != kCMIOObjectUnknown) {
            CMIODeviceStopStream(device_id_, sink_stream_);
        }
        if (sink_queue_ != nullptr) {
            CFRelease(sink_queue_);
        }
        started_ = false;
        consumer_count_ = 0;
        sink_stream_ = kCMIOObjectUnknown;
        device_id_ = kCMIOObjectUnknown;
        sink_queue_ = nullptr;
        teardownBufferResources();
    }

    int width_ = 0;
    int height_ = 0;
    double fps_ = 0.0;
    CMIODeviceID device_id_ = kCMIOObjectUnknown;
    CMIOStreamID sink_stream_ = kCMIOObjectUnknown;
    CMSimpleQueueRef sink_queue_ = nullptr;
    CMFormatDescriptionRef format_description_ = nullptr;
    CVPixelBufferPoolRef buffer_pool_ = nullptr;
    bool started_ = false;
    int consumer_count_ = 0;
};

}  // namespace

akvc_macos_direct_sender_ref akvc_macos_direct_sender_create(
    int width,
    int height,
    double fps,
    char* error_message,
    size_t error_capacity
) {
    if (width <= 0 || height <= 0 || fps <= 0.0) {
        AKVCWriteError(error_message, error_capacity, @"invalid width/height/fps for direct sender");
        return nullptr;
    }
    DirectSender* sender = new DirectSender(width, height, fps);
    return reinterpret_cast<akvc_macos_direct_sender_ref>(sender);
}

void akvc_macos_direct_sender_destroy(akvc_macos_direct_sender_ref sender) {
    if (sender == nullptr) {
        return;
    }
    delete reinterpret_cast<DirectSender*>(sender);
}

int akvc_macos_direct_sender_start(
    akvc_macos_direct_sender_ref sender,
    const char* camera_name,
    char* error_message,
    size_t error_capacity
) {
    if (sender == nullptr) {
        AKVCWriteError(error_message, error_capacity, @"direct sender handle is null");
        return -1;
    }
    DirectSender* direct_sender = reinterpret_cast<DirectSender*>(sender);
    NSString* name = camera_name != nullptr ? [NSString stringWithUTF8String:camera_name] : nil;
    NSString* error = nil;
    if (!direct_sender->start(name, &error)) {
        AKVCWriteError(error_message, error_capacity, error);
        return -1;
    }
    return 0;
}

int akvc_macos_direct_sender_send_bgr24(
    akvc_macos_direct_sender_ref sender,
    const void* data,
    int width,
    int height,
    int bytes_per_row,
    uint64_t pts_100ns,
    char* error_message,
    size_t error_capacity
) {
    if (sender == nullptr) {
        AKVCWriteError(error_message, error_capacity, @"direct sender handle is null");
        return -1;
    }
    DirectSender* direct_sender = reinterpret_cast<DirectSender*>(sender);
    NSString* error = nil;
    if (!direct_sender->sendBGR24(
            static_cast<const uint8_t*>(data),
            width,
            height,
            bytes_per_row,
            pts_100ns,
            &error)) {
        AKVCWriteError(error_message, error_capacity, error);
        return -1;
    }
    return 0;
}

int akvc_macos_direct_sender_send_bgra32(
    akvc_macos_direct_sender_ref sender,
    const void* data,
    int width,
    int height,
    int bytes_per_row,
    uint64_t pts_100ns,
    char* error_message,
    size_t error_capacity
) {
    if (sender == nullptr) {
        AKVCWriteError(error_message, error_capacity, @"direct sender handle is null");
        return -1;
    }
    DirectSender* direct_sender = reinterpret_cast<DirectSender*>(sender);
    NSString* error = nil;
    if (!direct_sender->sendBGRA32(
            static_cast<const uint8_t*>(data),
            width,
            height,
            bytes_per_row,
            pts_100ns,
            &error)) {
        AKVCWriteError(error_message, error_capacity, error);
        return -1;
    }
    return 0;
}

int akvc_macos_direct_sender_consumer_count(akvc_macos_direct_sender_ref sender) {
    if (sender == nullptr) {
        return 0;
    }
    DirectSender* direct_sender = reinterpret_cast<DirectSender*>(sender);
    return direct_sender->consumerCount();
}

int akvc_macos_direct_sender_list_devices_json(
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
) {
    return AKVCWriteSnapshotJSON(
        AKVCBuildCameraSnapshot(),
        json_buffer,
        json_capacity,
        error_message,
        error_capacity
    );
}

int akvc_macos_direct_sender_request_camera_access_json(
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
) {
    NSString* request_error = nil;
    NSDictionary* snapshot = AKVCRequestCameraAccessSnapshot(&request_error);
    if (snapshot == nil) {
        AKVCWriteError(error_message, error_capacity, request_error);
        return -1;
    }
    return AKVCWriteSnapshotJSON(
        snapshot,
        json_buffer,
        json_capacity,
        error_message,
        error_capacity
    );
}
