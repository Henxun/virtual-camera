// SPDX-License-Identifier: Apache-2.0
#import "AKVCSystemExtensionSupport.h"

#import <dispatch/dispatch.h>
#import <SystemExtensions/SystemExtensions.h>

#import "AKVCCommandSupport.h"

static NSString* const AKVCCameraExtensionBundleIdentifier = @"com.sidus.amaran-desktop.cameraextension";

@interface AKVCSystemExtensionQueryRunner : NSObject <OSSystemExtensionRequestDelegate>
@property(nonatomic, strong) NSArray<OSSystemExtensionProperties*>* properties;
@property(nonatomic, strong) NSError* error;
@property(nonatomic, strong) dispatch_semaphore_t completionSignal;
@property(nonatomic, assign) BOOL finished;
@end

@implementation AKVCSystemExtensionQueryRunner

- (instancetype)init {
    self = [super init];
    if (self == nil) {
        return nil;
    }
    _properties = @[];
    _completionSignal = dispatch_semaphore_create(0);
    _finished = NO;
    return self;
}

- (OSSystemExtensionReplacementAction)request:(OSSystemExtensionRequest*)request
                 actionForReplacingExtension:(OSSystemExtensionProperties*)existing
                               withExtension:(OSSystemExtensionProperties*)ext {
    (void)request;
    (void)existing;
    (void)ext;
    return OSSystemExtensionReplacementActionReplace;
}

- (void)requestNeedsUserApproval:(OSSystemExtensionRequest*)request {
    (void)request;
}

- (void)request:(OSSystemExtensionRequest*)request foundProperties:(NSArray<OSSystemExtensionProperties*>*)properties {
    (void)request;
    self.properties = properties ?: @[];
}

- (void)request:(OSSystemExtensionRequest*)request didFinishWithResult:(OSSystemExtensionRequestResult)result {
    (void)request;
    (void)result;
    self.finished = YES;
    if (self.completionSignal != nil) {
        dispatch_semaphore_signal(self.completionSignal);
    }
}

- (void)request:(OSSystemExtensionRequest*)request didFailWithError:(NSError*)error {
    (void)request;
    self.error = error;
    self.finished = YES;
    if (self.completionSignal != nil) {
        dispatch_semaphore_signal(self.completionSignal);
    }
}

@end

@interface AKVCSystemExtensionRequestRunner : NSObject <OSSystemExtensionRequestDelegate>
@property(nonatomic, strong) NSError* error;
@property(nonatomic, strong) dispatch_semaphore_t completionSignal;
@property(nonatomic, assign) BOOL finished;
@property(nonatomic, assign) BOOL succeeded;
@property(nonatomic, assign) BOOL needsApproval;
@property(nonatomic, copy) void (^completionHandler)(BOOL succeeded, NSError* _Nullable error);
@end

@implementation AKVCSystemExtensionRequestRunner

- (instancetype)init {
    self = [super init];
    if (self == nil) {
        return nil;
    }
    _completionSignal = dispatch_semaphore_create(0);
    _finished = NO;
    _succeeded = NO;
    _needsApproval = NO;
    return self;
}

- (OSSystemExtensionReplacementAction)request:(OSSystemExtensionRequest*)request
                 actionForReplacingExtension:(OSSystemExtensionProperties*)existing
                               withExtension:(OSSystemExtensionProperties*)ext {
    (void)request;
    (void)existing;
    (void)ext;
    return OSSystemExtensionReplacementActionReplace;
}

- (void)requestNeedsUserApproval:(OSSystemExtensionRequest*)request {
    (void)request;
    self.needsApproval = YES;
    self.succeeded = YES;
    self.finished = YES;
    if (self.completionHandler != nil) {
        self.completionHandler(YES, nil);
    }
    if (self.completionSignal != nil) {
        dispatch_semaphore_signal(self.completionSignal);
    }
}

- (void)request:(OSSystemExtensionRequest*)request didFinishWithResult:(OSSystemExtensionRequestResult)result {
    (void)request;
    (void)result;
    self.succeeded = YES;
    self.finished = YES;
    if (self.completionHandler != nil) {
        self.completionHandler(YES, nil);
    }
    if (self.completionSignal != nil) {
        dispatch_semaphore_signal(self.completionSignal);
    }
}

- (void)request:(OSSystemExtensionRequest*)request didFailWithError:(NSError*)error {
    (void)request;
    self.error = error;
    self.finished = YES;
    if (self.completionHandler != nil) {
        self.completionHandler(NO, error);
    }
    if (self.completionSignal != nil) {
        dispatch_semaphore_signal(self.completionSignal);
    }
}

@end

static dispatch_queue_t AKVCSystemExtensionCallbackQueue(void) {
    static dispatch_queue_t queue = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        queue = dispatch_queue_create("com.sidus.amaran-desktop.system-extension", DISPATCH_QUEUE_SERIAL);
    });
    return queue;
}

static NSMutableSet<AKVCSystemExtensionRequestRunner*>* AKVCInFlightSystemExtensionRunners(void) {
    static NSMutableSet<AKVCSystemExtensionRequestRunner*>* runners = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        runners = [NSMutableSet set];
    });
    return runners;
}

static void AKVCRetainSystemExtensionRunner(AKVCSystemExtensionRequestRunner* runner) {
    if (runner == nil) {
        return;
    }
    @synchronized(AKVCInFlightSystemExtensionRunners()) {
        [AKVCInFlightSystemExtensionRunners() addObject:runner];
    }
}

static void AKVCReleaseSystemExtensionRunner(AKVCSystemExtensionRequestRunner* runner) {
    if (runner == nil) {
        return;
    }
    @synchronized(AKVCInFlightSystemExtensionRunners()) {
        [AKVCInFlightSystemExtensionRunners() removeObject:runner];
    }
}

static BOOL AKVCWaitForSystemExtensionSignal(dispatch_semaphore_t signal, NSTimeInterval timeoutSeconds) {
    if (signal == nil) {
        return NO;
    }
    double clampedTimeout = timeoutSeconds < 0 ? 0 : timeoutSeconds;
    int64_t timeoutNanos = (int64_t)(clampedTimeout * (double)NSEC_PER_SEC);
    return dispatch_semaphore_wait(signal, dispatch_time(DISPATCH_TIME_NOW, timeoutNanos)) == 0;
}

static BOOL AKVCStatusQueryErrorIndicatesMissingExtension(NSError* error) {
    if (error == nil || ![error.domain isEqualToString:OSSystemExtensionErrorDomain]) {
        return NO;
    }

    // On current Ventura/Sonoma/Sequoia builds, a properties request for an
    // extension that has never been activated can surface as either
    // `ExtensionNotFound` or the generic `Unknown`. Treat both as
    // "not installed yet" in the status command so diagnostics stay aligned
    // with what users should do next: install or activate the container app bundle.
    return error.code == OSSystemExtensionErrorExtensionNotFound
        || error.code == OSSystemExtensionErrorUnknown;
}

static OSSystemExtensionRequest* AKVCMakeSystemExtensionRequest(BOOL activate) {
    NSString* identifier = AKVCCameraExtensionIdentifier();
    dispatch_queue_t queue = AKVCSystemExtensionCallbackQueue();
    if (activate) {
        return [OSSystemExtensionRequest activationRequestForExtension:identifier queue:queue];
    }
    return [OSSystemExtensionRequest deactivationRequestForExtension:identifier queue:queue];
}

NSString* AKVCCameraExtensionIdentifier(void) {
    return AKVCCameraExtensionBundleIdentifier;
}

NSString* AKVCResolvedHostExecutablePath(void) {
    NSString* bundlePath = AKVCResolvedBundlePath();
    if (bundlePath.length > 0) {
        NSString* executable = AKVCResolvedBundleExecutablePath(bundlePath);
        if (executable.length > 0) {
            return executable;
        }
    }

    NSString* containerExecutable = NSProcessInfo.processInfo.environment[@"AKVC_CONTAINER_APP_EXECUTABLE"];
    if (containerExecutable.length > 0) {
        return containerExecutable;
    }

    NSString* explicitExecutable = NSProcessInfo.processInfo.environment[@"AKVC_HOST_EXECUTABLE"];
    if (explicitExecutable.length > 0) {
        return explicitExecutable;
    }

    NSString* executablePath = NSProcessInfo.processInfo.arguments.firstObject ?: @"";
    NSString* binaryDirectory = [executablePath stringByDeletingLastPathComponent];
    NSString* siblingExecutable = [binaryDirectory stringByAppendingPathComponent:@"akvc-host"];
    if ([NSFileManager.defaultManager isExecutableFileAtPath:siblingExecutable]) {
        return siblingExecutable;
    }
    return @"";
}

static NSString* AKVCResolvedHostBundlePathForLaunch(void) {
    NSString* bundlePath = AKVCResolvedBundlePath();
    if (bundlePath.length > 0) {
        return bundlePath;
    }

    NSString* executablePath = AKVCResolvedHostExecutablePath();
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

NSDictionary* AKVCQuerySystemExtensionStatus(NSString* extensionIdentifier, NSTimeInterval timeoutSeconds) {
    NSMutableDictionary* payload = [AKVCDefaultStatusPayload() mutableCopy];
    payload[@"bundle_path"] = AKVCResolvedBundlePath();

    AKVCSystemExtensionQueryRunner* runner = [[AKVCSystemExtensionQueryRunner alloc] init];
    OSSystemExtensionRequest* request =
        [OSSystemExtensionRequest propertiesRequestForExtension:extensionIdentifier
                                                          queue:AKVCSystemExtensionCallbackQueue()];
    request.delegate = runner;
    [OSSystemExtensionManager.sharedManager submitRequest:request];

    if (!AKVCWaitForSystemExtensionSignal(runner.completionSignal, timeoutSeconds) || !runner.finished) {
        payload[@"state"] = @"install_failed";
        payload[@"last_error"] = @"system extension status query timed out";
        return payload;
    }

    if (runner.error != nil) {
        if (AKVCStatusQueryErrorIndicatesMissingExtension(runner.error)) {
            return payload;
        }
        payload[@"state"] = @"install_failed";
        payload[@"last_error"] = runner.error.localizedDescription ?: @"system extension status query failed";
        return payload;
    }

    OSSystemExtensionProperties* property = runner.properties.firstObject;
    if (property == nil) {
        return payload;
    }

    NSURL* parentURL = [property.URL URLByDeletingLastPathComponent];
    NSURL* grandparentURL = [parentURL URLByDeletingLastPathComponent];
    payload[@"bundle_path"] = grandparentURL.path ?: payload[@"bundle_path"];
    payload[@"enabled"] = @(property.isEnabled);
    payload[@"approval_required"] = @(property.isAwaitingUserApproval);

    if (property.isEnabled) {
        NSDictionary* deviceSnapshot = AKVCVideoDeviceSnapshot();
        payload[@"state"] = @"installed";
        payload[@"devices"] = deviceSnapshot[@"devices"] ?: @[];
        payload[@"all_devices"] = deviceSnapshot[@"all_devices"] ?: @[];
        payload[@"device_prefix"] = deviceSnapshot[@"device_prefix"] ?: AKVCDevicePrefix();
        return payload;
    }

    if (property.isAwaitingUserApproval) {
        payload[@"state"] = @"install_pending_approval";
        return payload;
    }

    if (property.isUninstalling) {
        payload[@"state"] = @"not_installed";
        payload[@"needs_reboot"] = @YES;
        return payload;
    }

    return payload;
}

BOOL AKVCLaunchHostAgent(NSArray<NSString*>* arguments, NSError* _Nullable __autoreleasing* outError) {
    NSString* bundlePath = AKVCResolvedHostBundlePathForLaunch();
    NSError* bundleLaunchError = nil;
    if (bundlePath.length > 0) {
        NSTask* task = [[NSTask alloc] init];
        task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/open"];
        NSMutableArray<NSString*>* openArguments = [NSMutableArray arrayWithObjects:@"-n", @"-a", bundlePath, nil];
        if (arguments.count > 0) {
            [openArguments addObject:@"--args"];
            [openArguments addObjectsFromArray:arguments];
        }
        task.arguments = openArguments;
        NSError* openLaunchError = nil;
        if ([task launchAndReturnError:&openLaunchError]) {
            [task waitUntilExit];
            if (task.terminationStatus == 0) {
                return YES;
            }
            bundleLaunchError = [NSError errorWithDomain:@"com.akvc.macos.host"
                                                    code:(NSInteger)task.terminationStatus
                                                userInfo:@{
                                                    NSLocalizedDescriptionKey:
                                                        [NSString stringWithFormat:@"failed to launch container app bundle %@", bundlePath]
                                                }];
        } else {
            bundleLaunchError = openLaunchError;
        }
        // If LaunchServices rejects the app bundle, fall back to the direct executable launch path.
    }

    NSString* executablePath = AKVCResolvedHostExecutablePath();
    if (executablePath.length == 0) {
        if (outError != nil) {
            *outError = bundleLaunchError ?: [NSError errorWithDomain:@"com.akvc.macos.host"
                                                                 code:1
                                                             userInfo:@{
                                                                 NSLocalizedDescriptionKey: @"container app executable not found"
                                                             }];
        }
        return NO;
    }

    NSTask* task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:executablePath];
    task.arguments = arguments;
    task.standardOutput = nil;
    task.standardError = nil;
    NSError* executableLaunchError = nil;
    BOOL launched = [task launchAndReturnError:&executableLaunchError];
    if (!launched && outError != nil) {
        if (bundleLaunchError != nil) {
            *outError = [NSError errorWithDomain:@"com.akvc.macos.host"
                                            code:bundleLaunchError.code
                                        userInfo:@{
                                            NSLocalizedDescriptionKey:
                                                [NSString stringWithFormat:
                                                    @"failed to launch container app bundle %@ and direct executable %@",
                                                    bundlePath,
                                                    executablePath],
                                            NSUnderlyingErrorKey: executableLaunchError ?: bundleLaunchError,
                                        }];
        } else {
            *outError = executableLaunchError;
        }
    } else if (launched && bundleLaunchError != nil) {
        NSLog(@"AKVC container app bundle launch failed (%@); direct executable launch succeeded.",
              bundleLaunchError.localizedDescription ?: @"unknown error");
    }
    return launched;
}

void AKVCSubmitSystemExtensionRequestAsync(
    BOOL activate,
    void (^completion)(BOOL succeeded, NSError* _Nullable error)
) {
    AKVCSystemExtensionRequestRunner* runner = [[AKVCSystemExtensionRequestRunner alloc] init];
    AKVCRetainSystemExtensionRunner(runner);
    runner.completionHandler = ^(BOOL succeeded, NSError* _Nullable error) {
        AKVCReleaseSystemExtensionRunner(runner);
        if (completion == nil) {
            return;
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            completion(succeeded, error);
        });
    };
    OSSystemExtensionRequest* request = AKVCMakeSystemExtensionRequest(activate);
    request.delegate = runner;
    [OSSystemExtensionManager.sharedManager submitRequest:request];
}

BOOL AKVCSubmitSystemExtensionRequest(
    BOOL activate,
    NSTimeInterval timeoutSeconds,
    NSError* _Nullable __autoreleasing* outError
) {
    AKVCSystemExtensionRequestRunner* runner = [[AKVCSystemExtensionRequestRunner alloc] init];
    OSSystemExtensionRequest* request = AKVCMakeSystemExtensionRequest(activate);
    request.delegate = runner;
    [OSSystemExtensionManager.sharedManager submitRequest:request];

    if (!AKVCWaitForSystemExtensionSignal(runner.completionSignal, timeoutSeconds) || !runner.finished) {
        if (outError != nil) {
            *outError = [NSError errorWithDomain:@"com.akvc.macos.host"
                                            code:2
                                        userInfo:@{
                                            NSLocalizedDescriptionKey:
                                                @"timed out while waiting for system extension request"
                                        }];
        }
        return NO;
    }

    if (runner.error != nil) {
        if (outError != nil) {
            *outError = runner.error;
        }
        return NO;
    }

    return runner.succeeded;
}
