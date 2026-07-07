// SPDX-License-Identifier: Apache-2.0
#import <AVFoundation/AVFoundation.h>
#import <CoreMediaIO/CMIOHardware.h>
#import <pwd.h>
#import <sys/types.h>
#import <unistd.h>
#import "AKVCCommandSupport.h"

#include "akvc/macos_ipc.h"

static NSString* const AKVCDefaultExtensionIdentifier = @"com.sidus.amaran-desktop.cameraextension";
static NSString* const AKVCCommandSupportErrorDomain = @"com.akvc.macos.command-support";
static NSString* const AKVCDefaultDevicePrefix = @"AK Virtual Camera";
static NSString* const AKVCCameraExtensionBundleSuffix = @".systemextension";

static NSString* AKVCStringOrNil(id value) {
    return [value isKindOfClass:NSString.class] ? (NSString*)value : nil;
}

static NSNumber* AKVCIntegerOrNil(id value) {
    if ([value isKindOfClass:NSNumber.class]) {
        return (NSNumber*)value;
    }
    if ([value isKindOfClass:NSString.class]) {
        NSInteger parsed = [(NSString*)value integerValue];
        return @((int)parsed);
    }
    return nil;
}

static NSDictionary* AKVCDictionaryOrEmpty(id value) {
    return [value isKindOfClass:NSDictionary.class] ? (NSDictionary*)value : @{};
}

static NSString* AKVCCurrentUserHomeDirectory(void) {
    struct passwd* user = getpwuid(getuid());
    if (user != NULL && user->pw_dir != NULL && user->pw_dir[0] != '\0') {
        return [NSString stringWithUTF8String:user->pw_dir];
    }
    NSString* home = NSProcessInfo.processInfo.environment[@"HOME"];
    if (home.length > 0) {
        return home;
    }
    return @"";
}

static NSString* AKVCBundlePathForExecutablePath(NSString* executablePath) {
    if (executablePath.length == 0) {
        return @"";
    }

    NSString* macOSDirectory = [executablePath stringByDeletingLastPathComponent];
    if (![[macOSDirectory lastPathComponent] isEqualToString:@"MacOS"]) {
        return @"";
    }

    NSString* contentsDirectory = [macOSDirectory stringByDeletingLastPathComponent];
    if (![[contentsDirectory lastPathComponent] isEqualToString:@"Contents"]) {
        return @"";
    }

    NSString* appBundle = [contentsDirectory stringByDeletingLastPathComponent];
    BOOL isDirectory = NO;
    if ([appBundle.pathExtension isEqualToString:@"app"]
        && [NSFileManager.defaultManager fileExistsAtPath:appBundle isDirectory:&isDirectory]
        && isDirectory) {
        return appBundle;
    }
    return @"";
}

static BOOL AKVCIsPreferredContainerBundleName(NSString* bundleName) {
    return ![
        @[@"akvc-host.app", @"akvc-demo-app.app"]
        containsObject:bundleName
    ];
}

static BOOL AKVCBundleEmbedsCameraExtension(NSString* bundlePath) {
    if (bundlePath.length == 0) {
        return NO;
    }
    NSString* extensionBundleName =
        [AKVCDefaultExtensionIdentifier stringByAppendingString:AKVCCameraExtensionBundleSuffix];
    NSString* extensionPath =
        [[bundlePath stringByAppendingPathComponent:@"Contents/Library/SystemExtensions"]
            stringByAppendingPathComponent:extensionBundleName];
    BOOL isDirectory = NO;
    return [NSFileManager.defaultManager fileExistsAtPath:extensionPath isDirectory:&isDirectory] && isDirectory;
}

static NSString* AKVCFindContainerBundleInDirectory(NSString* directoryPath) {
    if (directoryPath.length == 0) {
        return @"";
    }

    NSFileManager* fileManager = NSFileManager.defaultManager;
    BOOL isDirectory = NO;
    if (![fileManager fileExistsAtPath:directoryPath isDirectory:&isDirectory] || !isDirectory) {
        return @"";
    }

    NSError* error = nil;
    NSArray<NSString*>* entries = [fileManager contentsOfDirectoryAtPath:directoryPath error:&error];
    if (error != nil || entries.count == 0) {
        return @"";
    }

    NSArray<NSString*>* sortedEntries = [entries sortedArrayUsingSelector:@selector(localizedCaseInsensitiveCompare:)];
    for (NSString* entry in sortedEntries) {
        if (![entry.pathExtension isEqualToString:@"app"]) {
            continue;
        }
        if (!AKVCIsPreferredContainerBundleName(entry)) {
            continue;
        }
        NSString* candidate = [directoryPath stringByAppendingPathComponent:entry];
        if (AKVCBundleEmbedsCameraExtension(candidate)) {
            return candidate;
        }
    }
    for (NSString* entry in sortedEntries) {
        if (![entry.pathExtension isEqualToString:@"app"]) {
            continue;
        }
        NSString* candidate = [directoryPath stringByAppendingPathComponent:entry];
        if (AKVCBundleEmbedsCameraExtension(candidate)) {
            return candidate;
        }
    }
    return @"";
}

int AKVCWriteJSONObject(NSDictionary* object) {
    NSError* error = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:object options:0 error:&error];
    if (data == nil || error != nil) {
        NSString* message = error.localizedDescription ?: @"failed to encode JSON";
        fprintf(stderr, "%s\n", message.UTF8String);
        return 2;
    }
    fwrite(data.bytes, data.length, 1, stdout);
    fputc('\n', stdout);
    return 0;
}

NSString* AKVCDevicePrefix(void) {
    NSString* prefix = NSProcessInfo.processInfo.environment[@"AKVC_DEVICE_PREFIX"];
    if (prefix.length > 0) {
        return prefix;
    }
    const char* resolvedDeviceName = akvc_macos_resolved_device_name();
    if (resolvedDeviceName != NULL && resolvedDeviceName[0] != '\0') {
        return [NSString stringWithUTF8String:resolvedDeviceName];
    }
    return AKVCDefaultDevicePrefix;
}

static NSString* AKVCCopyCMIODeviceName(CMIODeviceID deviceID) {
    UInt32 dataSize = 0;
    UInt32 dataUsed = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOObjectPropertyName,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyDataSize(deviceID, &address, 0, NULL, &dataSize);
    if (status != noErr || dataSize == 0) {
        return nil;
    }
    CFStringRef name = NULL;
    status = CMIOObjectGetPropertyData(deviceID, &address, 0, NULL, dataSize, &dataUsed, &name);
    if (status != noErr || name == NULL) {
        return nil;
    }
    return (__bridge NSString*)name;
}

static NSArray<NSString*>* AKVCCMIOVideoDevices(void) {
    UInt32 dataSize = 0;
    UInt32 dataUsed = 0;
    CMIOObjectPropertyAddress address = {
        kCMIOHardwarePropertyDevices,
        kCMIOObjectPropertyScopeGlobal,
        kCMIOObjectPropertyElementMain,
    };
    OSStatus status = CMIOObjectGetPropertyDataSize(kCMIOObjectSystemObject, &address, 0, NULL, &dataSize);
    if (status != noErr || dataSize == 0) {
        return @[];
    }

    NSUInteger count = dataSize / sizeof(CMIOObjectID);
    NSMutableData* deviceBuffer = [NSMutableData dataWithLength:count * sizeof(CMIOObjectID)];
    status = CMIOObjectGetPropertyData(
        kCMIOObjectSystemObject,
        &address,
        0,
        NULL,
        dataSize,
        &dataUsed,
        deviceBuffer.mutableBytes
    );
    if (status != noErr) {
        return @[];
    }

    NSMutableArray<NSString*>* names = [NSMutableArray array];
    CMIOObjectID* deviceIDs = (CMIOObjectID*)deviceBuffer.mutableBytes;
    for (NSUInteger index = 0; index < count; ++index) {
        NSString* name = AKVCCopyCMIODeviceName(deviceIDs[index]);
        if (name.length > 0) {
            [names addObject:name];
        }
    }
    return [names copy];
}

static NSArray<NSString*>* AKVCAVFoundationVideoDevices(void) {
    NSMutableArray<NSString*>* names = [NSMutableArray array];
    NSMutableSet<NSString*>* seen = [NSMutableSet set];
    void (^appendName)(NSString*) = ^(NSString* name) {
        if (name.length == 0) {
            return;
        }
        NSString* key = name.lowercaseString;
        if ([seen containsObject:key]) {
            return;
        }
        [seen addObject:key];
        [names addObject:name];
    };
    NSMutableArray<AVCaptureDeviceType>* deviceTypes = [NSMutableArray arrayWithArray:@[
        AVCaptureDeviceTypeBuiltInWideAngleCamera,
        AVCaptureDeviceTypeExternalUnknown,
    ]];
    if (@available(macOS 14.0, *)) {
        [deviceTypes addObject:AVCaptureDeviceTypeExternal];
        [deviceTypes addObject:AVCaptureDeviceTypeContinuityCamera];
    }
    AVCaptureDeviceDiscoverySession* discoverySession =
        [AVCaptureDeviceDiscoverySession discoverySessionWithDeviceTypes:deviceTypes
                                                              mediaType:AVMediaTypeVideo
                                                               position:AVCaptureDevicePositionUnspecified];
    for (AVCaptureDevice* device in discoverySession.devices) {
        NSString* localizedName = device.localizedName ?: @"";
        appendName(localizedName);
    }

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    for (AVCaptureDevice* device in [AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo]) {
        NSString* localizedName = device.localizedName ?: @"";
        appendName(localizedName);
    }
#pragma clang diagnostic pop

    return [names copy];
}

static NSArray<NSString*>* AKVCCombinedUniqueVideoDevices(
    NSArray<NSString*>* avfoundationDevices,
    NSArray<NSString*>* cmioDevices
) {
    NSMutableArray<NSString*>* names = [NSMutableArray array];
    NSMutableSet<NSString*>* seen = [NSMutableSet set];
    void (^appendName)(NSString*) = ^(NSString* name) {
        if (name.length == 0) {
            return;
        }
        NSString* key = name.lowercaseString;
        if ([seen containsObject:key]) {
            return;
        }
        [seen addObject:key];
        [names addObject:name];
    };

    for (NSString* name in avfoundationDevices) {
        appendName(name);
    }
    for (NSString* name in cmioDevices) {
        appendName(name);
    }
    return [names copy];
}

NSArray<NSString*>* AKVCEnumeratedVideoDevices(void) {
    return AKVCCombinedUniqueVideoDevices(
        AKVCAVFoundationVideoDevices(),
        AKVCCMIOVideoDevices()
    );
}

NSDictionary* AKVCVideoDeviceSnapshot(void) {
    NSString* prefix = AKVCDevicePrefix();
    NSArray<NSString*>* avfoundationDevices = AKVCAVFoundationVideoDevices();
    NSArray<NSString*>* cmioDevices = AKVCCMIOVideoDevices();
    NSArray<NSString*>* allDevices = AKVCCombinedUniqueVideoDevices(avfoundationDevices, cmioDevices);
    NSMutableArray<NSString*>* filteredDevices = [NSMutableArray array];
    for (NSString* deviceName in allDevices) {
        if (prefix.length == 0 || [deviceName hasPrefix:prefix]) {
            [filteredDevices addObject:deviceName];
        }
    }
    return @{
        @"devices": [filteredDevices copy],
        @"all_devices": allDevices,
        @"avfoundation_devices": avfoundationDevices,
        @"cmio_devices": cmioDevices,
        @"device_prefix": prefix,
        @"environment_device_enumeration_empty": @(allDevices.count == 0),
    };
}

NSString* AKVCResolvedBundlePath(void) {
    NSString* containerBundle = NSProcessInfo.processInfo.environment[@"AKVC_CONTAINER_APP_BUNDLE"];
    if (containerBundle.length > 0) {
        return containerBundle;
    }

    NSString* explicitBundle = NSProcessInfo.processInfo.environment[@"AKVC_HOST_APP_BUNDLE"];
    if (explicitBundle.length > 0) {
        return explicitBundle;
    }

    NSString* containerExecutable = NSProcessInfo.processInfo.environment[@"AKVC_CONTAINER_APP_EXECUTABLE"];
    if (containerExecutable.length > 0) {
        NSString* bundlePath = AKVCBundlePathForExecutablePath(containerExecutable);
        if (bundlePath.length > 0) {
            return bundlePath;
        }
    }

    NSString* explicitExecutable = NSProcessInfo.processInfo.environment[@"AKVC_HOST_EXECUTABLE"];
    if (explicitExecutable.length > 0) {
        NSString* bundlePath = AKVCBundlePathForExecutablePath(explicitExecutable);
        if (bundlePath.length > 0) {
            return bundlePath;
        }
    }

    NSString* executablePath = NSProcessInfo.processInfo.arguments.firstObject ?: @"";
    NSString* inferredBundlePath = AKVCBundlePathForExecutablePath(executablePath);
    if (inferredBundlePath.length > 0) {
        return inferredBundlePath;
    }

    NSString* binaryDirectory = [executablePath stringByDeletingLastPathComponent];
    NSArray<NSString*>* searchDirectories = @[
        binaryDirectory,
        [binaryDirectory stringByDeletingLastPathComponent],
    ];
    for (NSString* directory in searchDirectories) {
        NSString* detectedBundle = AKVCFindContainerBundleInDirectory(directory);
        if (detectedBundle.length > 0) {
            return detectedBundle;
        }
    }
    return @"";
}

NSString* AKVCResolvedBundleExecutablePath(NSString* bundlePath) {
    if (bundlePath.length == 0) {
        return @"";
    }

    NSString* macOSDirectory = [bundlePath stringByAppendingPathComponent:@"Contents/MacOS"];
    NSFileManager* fileManager = NSFileManager.defaultManager;
    BOOL isDirectory = NO;
    if (![fileManager fileExistsAtPath:macOSDirectory isDirectory:&isDirectory] || !isDirectory) {
        return @"";
    }

    NSString* infoPlistPath = [bundlePath stringByAppendingPathComponent:@"Contents/Info.plist"];
    NSDictionary* info = [NSDictionary dictionaryWithContentsOfFile:infoPlistPath];
    NSString* executableName = AKVCStringOrNil(info[@"CFBundleExecutable"]);
    if (executableName.length > 0) {
        NSString* executablePath = [macOSDirectory stringByAppendingPathComponent:executableName];
        if ([fileManager isExecutableFileAtPath:executablePath]) {
            return executablePath;
        }
    }

    NSError* directoryError = nil;
    NSArray<NSString*>* entries = [fileManager contentsOfDirectoryAtPath:macOSDirectory error:&directoryError];
    if (directoryError != nil || entries.count == 0) {
        return @"";
    }

    NSArray<NSString*>* sortedEntries = [entries sortedArrayUsingSelector:@selector(localizedCaseInsensitiveCompare:)];
    for (NSString* entry in sortedEntries) {
        NSString* candidate = [macOSDirectory stringByAppendingPathComponent:entry];
        BOOL entryIsDirectory = NO;
        if ([fileManager fileExistsAtPath:candidate isDirectory:&entryIsDirectory]
            && !entryIsDirectory
            && [fileManager isExecutableFileAtPath:candidate]) {
            return candidate;
        }
    }
    return @"";
}

static NSArray<NSString*>* AKVCFramebusRoundtripRelativePaths(void) {
    return @[
        @"build/macos/framebus-roundtrip.json",
        @"build/macos/session/framebus-roundtrip.json",
        @"build/macos/validation/framebus-roundtrip.json",
        @"framebus-roundtrip.json",
    ];
}

static NSArray<NSString*>* AKVCFramebusRoundtripSearchRoots(void) {
    NSMutableArray<NSString*>* roots = [NSMutableArray array];
    NSFileManager* fileManager = NSFileManager.defaultManager;
    NSString* currentDirectory = fileManager.currentDirectoryPath ?: @"";
    if (currentDirectory.length > 0) {
        [roots addObject:currentDirectory];
    }

    NSString* executablePath = NSProcessInfo.processInfo.arguments.firstObject ?: @"";
    if (executablePath.length > 0) {
        NSString* binaryDirectory = [executablePath stringByDeletingLastPathComponent];
        if (binaryDirectory.length > 0) {
            [roots addObject:binaryDirectory];
            NSString* parent = [binaryDirectory stringByDeletingLastPathComponent];
            if (parent.length > 0) {
                [roots addObject:parent];
                NSString* grandparent = [parent stringByDeletingLastPathComponent];
                if (grandparent.length > 0) {
                    [roots addObject:grandparent];
                }
            }
        }
    }
    return roots;
}

static NSString* AKVCResolvedFramebusRoundtripReportPath(void) {
    NSString* explicitPath = NSProcessInfo.processInfo.environment[@"AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON"];
    if (explicitPath.length > 0 && [NSFileManager.defaultManager fileExistsAtPath:explicitPath]) {
        return explicitPath;
    }

    NSFileManager* fileManager = NSFileManager.defaultManager;
    for (NSString* root in AKVCFramebusRoundtripSearchRoots()) {
        for (NSString* relativePath in AKVCFramebusRoundtripRelativePaths()) {
            NSString* candidate = [root stringByAppendingPathComponent:relativePath];
            BOOL isDirectory = NO;
            if ([fileManager fileExistsAtPath:candidate isDirectory:&isDirectory] && !isDirectory) {
                return candidate;
            }
        }
    }
    return @"";
}

static NSDictionary* AKVCMergeFramebusRoundtripStatus(NSDictionary* payload) {
    NSMutableDictionary* merged = [payload mutableCopy];
    merged[@"ipc_transport"] = merged[@"ipc_transport"] ?: @"shared_memory_ringbuffer";
    merged[@"ipc_probe_present"] = @NO;
    merged[@"ipc_ready"] = [NSNull null];
    merged[@"ipc_environment_blocked"] = @NO;
    merged[@"ipc_last_error"] = [NSNull null];
    merged[@"ipc_probe_path"] = [NSNull null];
    merged[@"ipc_direct_open_errno"] = [NSNull null];

    NSString* reportPath = AKVCResolvedFramebusRoundtripReportPath();
    if (reportPath.length == 0) {
        return merged;
    }

    merged[@"ipc_probe_present"] = @YES;
    merged[@"ipc_probe_path"] = reportPath;

    NSData* data = [NSData dataWithContentsOfFile:reportPath];
    if (data == nil) {
        merged[@"ipc_ready"] = @NO;
        merged[@"ipc_last_error"] = @"framebus roundtrip report is unreadable";
        return merged;
    }

    NSError* error = nil;
    id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    if (error != nil || ![decoded isKindOfClass:NSDictionary.class]) {
        merged[@"ipc_ready"] = @NO;
        merged[@"ipc_last_error"] = @"framebus roundtrip report is unreadable";
        return merged;
    }

    NSDictionary* roundtrip = (NSDictionary*)decoded;
    NSDictionary* observed = AKVCDictionaryOrEmpty(roundtrip[@"observed"]);
    NSDictionary* consistency = AKVCDictionaryOrEmpty(roundtrip[@"consistency"]);
    NSNumber* directOpenErrno = AKVCIntegerOrNil(observed[@"direct_open_errno"]);
    if (directOpenErrno != nil) {
        merged[@"ipc_direct_open_errno"] = directOpenErrno;
    }

    id allChecksPassed = consistency[@"all_checks_passed"];
    NSString* observedStatus = AKVCStringOrNil(observed[@"status"]);
    if ([allChecksPassed isKindOfClass:NSNumber.class]) {
        merged[@"ipc_ready"] = @([(NSNumber*)allChecksPassed boolValue]);
    } else if (observedStatus.length > 0) {
        merged[@"ipc_ready"] = @([observedStatus isEqualToString:@"ok"]);
    }

    BOOL environmentBlocked = NO;
    if ([roundtrip[@"environment_blocked"] respondsToSelector:@selector(boolValue)]) {
        environmentBlocked = [roundtrip[@"environment_blocked"] boolValue];
    }
    if (!environmentBlocked && [consistency[@"environment_blocked"] respondsToSelector:@selector(boolValue)]) {
        environmentBlocked = [consistency[@"environment_blocked"] boolValue];
    }
    if (!environmentBlocked && directOpenErrno != nil) {
        NSInteger code = directOpenErrno.integerValue;
        environmentBlocked = (code == 1 || code == 13);
    }
    merged[@"ipc_environment_blocked"] = @(environmentBlocked);

    NSString* transport = AKVCStringOrNil(roundtrip[@"transport"]);
    if (transport.length > 0) {
        merged[@"ipc_transport"] = transport;
    }

    NSMutableArray<NSString*>* errorParts = [NSMutableArray array];
    NSString* topLevelError = AKVCStringOrNil(roundtrip[@"error"]);
    if (topLevelError.length > 0) {
        [errorParts addObject:topLevelError];
    }
    if (observedStatus.length > 0 && ![observedStatus isEqualToString:@"ok"]) {
        [errorParts addObject:[NSString stringWithFormat:@"probe status=%@", observedStatus]];
    }
    if (directOpenErrno != nil) {
        [errorParts addObject:[NSString stringWithFormat:@"direct_open_errno=%@", directOpenErrno]];
    }
    if (errorParts.count > 0) {
        merged[@"ipc_last_error"] = [errorParts componentsJoinedByString:@"; "];
    }
    return merged;
}

static NSString* AKVCDefaultSharedMemoryNameOverridePath(void) {
    NSString* explicitDir = NSProcessInfo.processInfo.environment[@"AKVC_MACOS_SHARED_STATE_DIR"];
    NSString* sharedStateDirectory = explicitDir.length > 0
        ? explicitDir
        : [[AKVCCurrentUserHomeDirectory() stringByAppendingPathComponent:@AKVC_MACOS_SHARED_STATE_DIR_SUFFIX] copy];
    if (sharedStateDirectory.length == 0) {
        sharedStateDirectory = @"/private/tmp/akvc-shared";
    }
    return [sharedStateDirectory stringByAppendingPathComponent:@AKVC_MACOS_SHM_NAME_FILE_NAME];
}

static NSString* AKVCDefaultDeviceNameOverridePath(void) {
    NSString* explicitDir = NSProcessInfo.processInfo.environment[@"AKVC_MACOS_SHARED_STATE_DIR"];
    NSString* sharedStateDirectory = explicitDir.length > 0
        ? explicitDir
        : [[AKVCCurrentUserHomeDirectory() stringByAppendingPathComponent:@AKVC_MACOS_SHARED_STATE_DIR_SUFFIX] copy];
    if (sharedStateDirectory.length == 0) {
        sharedStateDirectory = @"/private/tmp/akvc-shared";
    }
    return [sharedStateDirectory stringByAppendingPathComponent:@AKVC_MACOS_DEVICE_NAME_FILE_NAME];
}

static NSString* AKVCDefaultDemoModeOverridePath(void) {
    NSString* explicitDir = NSProcessInfo.processInfo.environment[@"AKVC_MACOS_SHARED_STATE_DIR"];
    NSString* sharedStateDirectory = explicitDir.length > 0
        ? explicitDir
        : [[AKVCCurrentUserHomeDirectory() stringByAppendingPathComponent:@AKVC_MACOS_SHARED_STATE_DIR_SUFFIX] copy];
    if (sharedStateDirectory.length == 0) {
        sharedStateDirectory = @"/private/tmp/akvc-shared";
    }
    return [sharedStateDirectory stringByAppendingPathComponent:@AKVC_MACOS_DEMO_MODE_FILE_NAME];
}

static BOOL AKVCValidateSharedMemoryName(NSString* value, NSError* _Nullable __autoreleasing* outError) {
    NSString* normalized = [value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (normalized.length == 0) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:1
                                        userInfo:@{NSLocalizedDescriptionKey: @"shared memory name must not be empty"}];
        }
        return NO;
    }
    if (![normalized hasPrefix:@"/"]) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:2
                                        userInfo:@{NSLocalizedDescriptionKey: @"shared memory name must start with '/'"}];
        }
        return NO;
    }
    if (normalized.length >= sizeof(((akvc_macos_ring_descriptor_t*)0)->shm_name)) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:3
                                        userInfo:@{NSLocalizedDescriptionKey: @"shared memory name exceeds descriptor buffer"}];
        }
        return NO;
    }
    return YES;
}

static NSString* AKVCReadSharedMemoryNameFromFile(NSString* path, NSError* _Nullable __autoreleasing* outError) {
    NSError* error = nil;
    NSString* content = [NSString stringWithContentsOfFile:path
                                                  encoding:NSUTF8StringEncoding
                                                     error:&error];
    if (content == nil) {
        if (outError != nil) {
            *outError = error ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                     code:4
                                                 userInfo:@{NSLocalizedDescriptionKey: @"failed to read shared memory name override file"}];
        }
        return nil;
    }
    NSString* line = [[content componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet] firstObject] ?: @"";
    NSString* normalized = [line stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!AKVCValidateSharedMemoryName(normalized, outError)) {
        return nil;
    }
    return normalized;
}

static BOOL AKVCValidateDeviceName(NSString* value, NSError* _Nullable __autoreleasing* outError) {
    NSString* normalized = [value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (normalized.length == 0) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:8
                                        userInfo:@{NSLocalizedDescriptionKey: @"device name must not be empty"}];
        }
        return NO;
    }
    if ([normalized rangeOfCharacterFromSet:NSCharacterSet.newlineCharacterSet].location != NSNotFound) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:9
                                        userInfo:@{NSLocalizedDescriptionKey: @"device name must be a single line"}];
        }
        return NO;
    }
    return YES;
}

static NSString* AKVCReadDeviceNameFromFile(NSString* path, NSError* _Nullable __autoreleasing* outError) {
    NSError* error = nil;
    NSString* content = [NSString stringWithContentsOfFile:path
                                                  encoding:NSUTF8StringEncoding
                                                     error:&error];
    if (content == nil) {
        if (outError != nil) {
            *outError = error ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                     code:10
                                                 userInfo:@{NSLocalizedDescriptionKey: @"failed to read device name override file"}];
        }
        return nil;
    }
    NSString* line = [[content componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet] firstObject] ?: @"";
    NSString* normalized = [line stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!AKVCValidateDeviceName(normalized, outError)) {
        return nil;
    }
    return normalized;
}

BOOL AKVCPersistSharedMemoryNameOverrideFromEnvironment(NSError* _Nullable __autoreleasing* outError) {
    NSDictionary* environment = NSProcessInfo.processInfo.environment;
    NSString* sharedMemoryNameKey = [NSString stringWithUTF8String:AKVC_MACOS_SHM_NAME_ENV];
    NSString* sharedMemoryFileKey = [NSString stringWithUTF8String:AKVC_MACOS_SHM_NAME_FILE_ENV];
    NSString* sharedMemoryName = [AKVCStringOrNil(environment[sharedMemoryNameKey])
        stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];

    if (sharedMemoryName.length > 0) {
        if (!AKVCValidateSharedMemoryName(sharedMemoryName, outError)) {
            return NO;
        }
    } else {
        NSString* overridePath = [AKVCStringOrNil(environment[sharedMemoryFileKey])
            stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (overridePath.length == 0) {
            return YES;
        }
        sharedMemoryName = AKVCReadSharedMemoryNameFromFile(overridePath, outError);
        if (sharedMemoryName == nil) {
            return NO;
        }
    }

    NSString* destinationPath = AKVCDefaultSharedMemoryNameOverridePath();
    if (destinationPath.length == 0) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:5
                                        userInfo:@{NSLocalizedDescriptionKey: @"failed to resolve shared memory name override destination"}];
        }
        return NO;
    }

    NSString* directoryPath = [destinationPath stringByDeletingLastPathComponent];
    NSError* directoryError = nil;
    if (directoryPath.length > 0
        && ![NSFileManager.defaultManager createDirectoryAtPath:directoryPath
                                    withIntermediateDirectories:YES
                                                     attributes:nil
                                                          error:&directoryError]) {
        if (outError != nil) {
            *outError = directoryError ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                              code:6
                                                          userInfo:@{NSLocalizedDescriptionKey: @"failed to create shared memory override directory"}];
        }
        return NO;
    }

    NSString* serialized = [sharedMemoryName stringByAppendingString:@"\n"];
    NSError* writeError = nil;
    if (![serialized writeToFile:destinationPath
                      atomically:YES
                        encoding:NSUTF8StringEncoding
                           error:&writeError]) {
        if (outError != nil) {
            *outError = writeError ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                          code:7
                                                      userInfo:@{NSLocalizedDescriptionKey: @"failed to persist shared memory override"}];
        }
        return NO;
    }
    return YES;
}

BOOL AKVCPersistDeviceNameOverrideFromEnvironment(NSError* _Nullable __autoreleasing* outError) {
    NSDictionary* environment = NSProcessInfo.processInfo.environment;
    NSString* deviceNameKey = [NSString stringWithUTF8String:AKVC_MACOS_DEVICE_NAME_ENV];
    NSString* deviceNameFileKey = [NSString stringWithUTF8String:AKVC_MACOS_DEVICE_NAME_FILE_ENV];
    NSString* deviceName = [AKVCStringOrNil(environment[deviceNameKey])
        stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];

    if (deviceName.length > 0) {
        if (!AKVCValidateDeviceName(deviceName, outError)) {
            return NO;
        }
    } else {
        NSString* overridePath = [AKVCStringOrNil(environment[deviceNameFileKey])
            stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (overridePath.length == 0) {
            return YES;
        }
        deviceName = AKVCReadDeviceNameFromFile(overridePath, outError);
        if (deviceName == nil) {
            return NO;
        }
    }

    NSString* destinationPath = AKVCDefaultDeviceNameOverridePath();
    if (destinationPath.length == 0) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:11
                                        userInfo:@{NSLocalizedDescriptionKey: @"failed to resolve device name override destination"}];
        }
        return NO;
    }

    NSString* directoryPath = [destinationPath stringByDeletingLastPathComponent];
    NSError* directoryError = nil;
    if (directoryPath.length > 0
        && ![NSFileManager.defaultManager createDirectoryAtPath:directoryPath
                                    withIntermediateDirectories:YES
                                                     attributes:nil
                                                          error:&directoryError]) {
        if (outError != nil) {
            *outError = directoryError ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                              code:12
                                                          userInfo:@{NSLocalizedDescriptionKey: @"failed to create device name override directory"}];
        }
        return NO;
    }

    NSString* serialized = [deviceName stringByAppendingString:@"\n"];
    NSError* writeError = nil;
    if (![serialized writeToFile:destinationPath
                      atomically:YES
                        encoding:NSUTF8StringEncoding
                           error:&writeError]) {
        if (outError != nil) {
            *outError = writeError ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                          code:13
                                                      userInfo:@{NSLocalizedDescriptionKey: @"failed to persist device name override"}];
        }
        return NO;
    }
    return YES;
}

BOOL AKVCSetDemoModeEnabled(BOOL enabled, NSError* _Nullable __autoreleasing* outError) {
    NSString* explicitPath = [AKVCStringOrNil(
        NSProcessInfo.processInfo.environment[[NSString stringWithUTF8String:AKVC_MACOS_DEMO_MODE_FILE_ENV]]
    )
        stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSString* destinationPath = explicitPath.length > 0 ? explicitPath : AKVCDefaultDemoModeOverridePath();
    if (destinationPath.length == 0) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                            code:14
                                        userInfo:@{NSLocalizedDescriptionKey: @"failed to resolve demo mode override destination"}];
        }
        return NO;
    }

    NSString* directoryPath = [destinationPath stringByDeletingLastPathComponent];
    NSError* directoryError = nil;
    if (directoryPath.length > 0
        && ![NSFileManager.defaultManager createDirectoryAtPath:directoryPath
                                    withIntermediateDirectories:YES
                                                     attributes:nil
                                                          error:&directoryError]) {
        if (outError != nil) {
            *outError = directoryError ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                              code:15
                                                          userInfo:@{NSLocalizedDescriptionKey: @"failed to create demo mode override directory"}];
        }
        return NO;
    }

    NSString* serialized = enabled ? @"1\n" : @"0\n";
    NSError* writeError = nil;
    if (![serialized writeToFile:destinationPath
                      atomically:YES
                        encoding:NSUTF8StringEncoding
                           error:&writeError]) {
        if (outError != nil) {
            *outError = writeError ?: [NSError errorWithDomain:AKVCCommandSupportErrorDomain
                                                          code:16
                                                      userInfo:@{NSLocalizedDescriptionKey: @"failed to persist demo mode override"}];
        }
        return NO;
    }
    return YES;
}

NSDictionary* AKVCDefaultStatusPayload(void) {
    akvc_macos_ring_descriptor_t descriptor = {};
    akvc_macos_ring_descriptor_default(&descriptor);
    NSDictionary* payload = @{
        @"state": @"not_installed",
        @"devices": @[],
        @"all_devices": @[],
        @"enabled": @NO,
        @"approval_required": @NO,
        @"needs_reboot": @NO,
        @"bundle_path": AKVCResolvedBundlePath(),
        @"extension_identifier": AKVCDefaultExtensionIdentifier,
        @"device_prefix": AKVCDevicePrefix(),
        @"shared_memory_name": [NSString stringWithUTF8String:descriptor.shm_name],
        @"supported_formats": @[@"1280x720@30/60 NV12", @"1920x1080@30/60 NV12", @"3840x2160@30/60 NV12"],
        @"supported_frame_rates": @[@30, @60],
        @"mach_service_name": @"group.com.sidus.amaran-desktop.cameraextension",
    };
    return AKVCMergeFramebusRoundtripStatus(payload);
}

int AKVCWriteNotImplemented(NSString* actionName) {
    NSString* message = [NSString stringWithFormat:@"%@ is not implemented yet.", actionName];
    fprintf(stderr, "%s\n", message.UTF8String);
    return 1;
}
