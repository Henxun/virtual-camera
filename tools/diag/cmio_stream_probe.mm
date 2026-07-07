// SPDX-License-Identifier: Apache-2.0
#import <CoreMediaIO/CMIOHardware.h>
#import <Foundation/Foundation.h>

static NSString* CopyObjectStringProperty(CMIOObjectID objectID, CMIOObjectPropertySelector selector) {
    UInt32 dataSize = 0;
    UInt32 dataUsed = 0;
    CMIOObjectPropertyAddress address = {
        selector,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyDataSize(objectID, &address, 0, NULL, &dataSize);
    if (status != noErr || dataSize == 0) {
        return nil;
    }
    CFStringRef value = nil;
    status = CMIOObjectGetPropertyData(objectID, &address, 0, NULL, dataSize, &dataUsed, &value);
    if (status != noErr || value == nil) {
        return nil;
    }
    return (__bridge_transfer NSString*)value;
}

static NSString* StreamDirectionLabel(CMIOStreamID streamID, UInt32* outDirection) {
    UInt32 direction = UINT32_MAX;
    UInt32 dataSize = sizeof(direction);
    UInt32 dataUsed = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOStreamPropertyDirection,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyData(streamID, &address, 0, NULL, dataSize, &dataUsed, &direction);
    if (status != noErr) {
        if (outDirection != NULL) {
            *outDirection = UINT32_MAX;
        }
        return [NSString stringWithFormat:@"unavailable(%d)", (int)status];
    }
    if (outDirection != NULL) {
        *outDirection = direction;
    }
    if (direction == 0) {
        return @"output";
    }
    if (direction == 1) {
        return @"input";
    }
    return [NSString stringWithFormat:@"%u", direction];
}

int main(int argc, const char* argv[]) {
    @autoreleasepool {
        NSString* targetName = argc > 1 ? [NSString stringWithUTF8String:argv[1]] : @"AK Virtual Camera";

        UInt32 dataSize = 0;
        UInt32 dataUsed = 0;
        CMIOObjectPropertyAddress deviceAddress = {
            kCMIOHardwarePropertyDevices,
            kCMIOObjectPropertyScopeGlobal,
            kCMIOObjectPropertyElementMain,
        };
        OSStatus status = CMIOObjectGetPropertyDataSize(kCMIOObjectSystemObject, &deviceAddress, 0, NULL, &dataSize);
        if (status != noErr || dataSize == 0) {
            fprintf(stderr, "failed to enumerate devices: %d\n", (int)status);
            return 1;
        }

        NSUInteger deviceCount = dataSize / sizeof(CMIOObjectID);
        NSMutableData* deviceBuffer = [NSMutableData dataWithLength:deviceCount * sizeof(CMIOObjectID)];
        status = CMIOObjectGetPropertyData(
            kCMIOObjectSystemObject,
            &deviceAddress,
            0,
            NULL,
            dataSize,
            &dataUsed,
            deviceBuffer.mutableBytes
        );
        if (status != noErr) {
            fprintf(stderr, "failed to read devices: %d\n", (int)status);
            return 1;
        }

        CMIOObjectID* deviceIDs = (CMIOObjectID*)deviceBuffer.mutableBytes;
        for (NSUInteger deviceIndex = 0; deviceIndex < deviceCount; ++deviceIndex) {
            CMIODeviceID deviceID = deviceIDs[deviceIndex];
            NSString* deviceName = CopyObjectStringProperty(deviceID, kCMIOObjectPropertyName);
            if (deviceName.length == 0 || ![deviceName containsString:targetName]) {
                continue;
            }

            NSString* deviceUID = CopyObjectStringProperty(deviceID, kCMIODevicePropertyDeviceUID);
            printf("device_id=%u\n", (unsigned)deviceID);
            printf("device_name=%s\n", deviceName.UTF8String);
            printf("device_uid=%s\n", (deviceUID ?: @"").UTF8String);

            CMIOObjectPropertyAddress streamAddress = {
                kCMIODevicePropertyStreams,
                kCMIOObjectPropertyScopeGlobal,
                kCMIOObjectPropertyElementMain,
            };
            dataSize = 0;
            dataUsed = 0;
            status = CMIOObjectGetPropertyDataSize(deviceID, &streamAddress, 0, NULL, &dataSize);
            if (status != noErr || dataSize == 0) {
                fprintf(stderr, "failed to enumerate streams: %d\n", (int)status);
                return 2;
            }

            NSUInteger streamCount = dataSize / sizeof(CMIOStreamID);
            NSMutableData* streamBuffer = [NSMutableData dataWithLength:streamCount * sizeof(CMIOStreamID)];
            status = CMIOObjectGetPropertyData(
                deviceID,
                &streamAddress,
                0,
                NULL,
                dataSize,
                &dataUsed,
                streamBuffer.mutableBytes
            );
            if (status != noErr) {
                fprintf(stderr, "failed to read streams: %d\n", (int)status);
                return 2;
            }

            CMIOStreamID* streamIDs = (CMIOStreamID*)streamBuffer.mutableBytes;
            for (NSUInteger streamIndex = 0; streamIndex < streamCount; ++streamIndex) {
                CMIOStreamID streamID = streamIDs[streamIndex];
                NSString* streamName = CopyObjectStringProperty(streamID, kCMIOObjectPropertyName);
                UInt32 direction = UINT32_MAX;
                NSString* directionLabel = StreamDirectionLabel(streamID, &direction);
                printf(
                    "stream[%lu].id=%u name=%s direction=%s raw_direction=%u\n",
                    (unsigned long)streamIndex,
                    (unsigned)streamID,
                    (streamName ?: @"").UTF8String,
                    directionLabel.UTF8String,
                    (unsigned)direction
                );
            }
            return 0;
        }

        fprintf(stderr, "target device not found: %s\n", targetName.UTF8String);
        return 3;
    }
}
