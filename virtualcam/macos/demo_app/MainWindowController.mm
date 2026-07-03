// SPDX-License-Identifier: Apache-2.0
#import "MainWindowController.h"

#import "DemoControlService.h"

@interface MainWindowController ()
@property(nonatomic, strong) DemoControlService* service;
@property(nonatomic, strong) NSTextField* summaryLabel;
@property(nonatomic, strong) NSTextField* statusLabel;
@property(nonatomic, strong) NSTextView* instructionsView;
@property(nonatomic, strong) NSTextView* logView;
@property(nonatomic, strong) NSMutableArray<NSString*>* logLines;
@end

@implementation MainWindowController

- (instancetype)init {
    NSWindow* window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 760, 560)
                                                   styleMask:(NSWindowStyleMaskTitled
                                                            | NSWindowStyleMaskClosable
                                                            | NSWindowStyleMaskMiniaturizable
                                                            | NSWindowStyleMaskResizable)
                                                     backing:NSBackingStoreBuffered
                                                       defer:NO];
    self = [super initWithWindow:window];
    if (self == nil) {
        return nil;
    }

    _service = [[DemoControlService alloc] init];
    _logLines = [NSMutableArray array];
    [self.window center];
    self.window.title = @"AKVC Demo App";
    [self buildInterface];
    [self refreshStatus:nil];
    return self;
}

- (void)buildInterface {
    NSView* contentView = self.window.contentView;
    if (contentView == nil) {
        return;
    }

    NSStackView* stack = [[NSStackView alloc] initWithFrame:contentView.bounds];
    stack.orientation = NSUserInterfaceLayoutOrientationVertical;
    stack.alignment = NSLayoutAttributeLeading;
    stack.distribution = NSStackViewDistributionFill;
    stack.spacing = 14.0;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [contentView addSubview:stack];

    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:contentView.leadingAnchor constant:20.0],
        [stack.trailingAnchor constraintEqualToAnchor:contentView.trailingAnchor constant:-20.0],
        [stack.topAnchor constraintEqualToAnchor:contentView.topAnchor constant:20.0],
        [stack.bottomAnchor constraintEqualToAnchor:contentView.bottomAnchor constant:-20.0],
    ]];

    NSTextField* titleLabel = [self labelWithString:@"AKVC Demo App" fontSize:24.0 weight:NSFontWeightSemibold];
    self.summaryLabel = [self labelWithString:@"未激活" fontSize:13.0 weight:NSFontWeightRegular];
    self.statusLabel = [self wrappingLabel];
    self.instructionsView = [self readOnlyTextViewWithText:self.service.manualAcceptanceInstructions];
    self.logView = [self readOnlyTextViewWithText:@"等待操作..."];

    [stack addArrangedSubview:titleLabel];
    [stack addArrangedSubview:self.summaryLabel];
    [stack addArrangedSubview:[self sectionLabel:@"状态"]];
    [stack addArrangedSubview:self.statusLabel];
    [stack addArrangedSubview:[self buttonRow]];
    [stack addArrangedSubview:[self sectionLabel:@"验收提示"]];
    [stack addArrangedSubview:[self scrollContainerForView:self.instructionsView height:120.0]];
    [stack addArrangedSubview:[self sectionLabel:@"日志"]];
    [stack addArrangedSubview:[self scrollContainerForView:self.logView height:180.0]];
}

- (NSView*)buttonRow {
    NSStackView* row = [[NSStackView alloc] initWithFrame:NSZeroRect];
    row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    row.spacing = 12.0;
    row.alignment = NSLayoutAttributeCenterY;

    [row addArrangedSubview:[self buttonWithTitle:@"刷新状态" action:@selector(refreshStatus:)]];
    [row addArrangedSubview:[self buttonWithTitle:@"启用 Demo 并激活" action:@selector(enableDemoAndActivate:)]];
    [row addArrangedSubview:[self buttonWithTitle:@"停用 Demo" action:@selector(disableDemo:)]];
    [row addArrangedSubview:[self buttonWithTitle:@"复制验收步骤" action:@selector(copyManualAcceptanceInstructions:)]];
    return row;
}

- (NSButton*)buttonWithTitle:(NSString*)title action:(SEL)action {
    NSButton* button = [NSButton buttonWithTitle:title target:self action:action];
    button.bezelStyle = NSBezelStyleRounded;
    return button;
}

- (NSTextField*)labelWithString:(NSString*)stringValue fontSize:(CGFloat)fontSize weight:(NSFontWeight)weight {
    NSTextField* label = [NSTextField labelWithString:stringValue];
    label.font = [NSFont systemFontOfSize:fontSize weight:weight];
    return label;
}

- (NSTextField*)sectionLabel:(NSString*)title {
    return [self labelWithString:title fontSize:14.0 weight:NSFontWeightSemibold];
}

- (NSTextField*)wrappingLabel {
    NSTextField* label = [NSTextField wrappingLabelWithString:@""];
    label.lineBreakMode = NSLineBreakByWordWrapping;
    return label;
}

- (NSTextView*)readOnlyTextViewWithText:(NSString*)text {
    NSTextView* textView = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 100, 100)];
    textView.editable = NO;
    textView.selectable = YES;
    textView.string = text;
    textView.font = [NSFont monospacedSystemFontOfSize:12.0 weight:NSFontWeightRegular];
    textView.drawsBackground = NO;
    return textView;
}

- (NSScrollView*)scrollContainerForView:(NSView*)view height:(CGFloat)height {
    NSScrollView* scrollView = [[NSScrollView alloc] initWithFrame:NSMakeRect(0, 0, 100, height)];
    scrollView.translatesAutoresizingMaskIntoConstraints = NO;
    scrollView.documentView = view;
    scrollView.hasVerticalScroller = YES;
    scrollView.borderType = NSBezelBorder;
    [scrollView.heightAnchor constraintEqualToConstant:height].active = YES;
    return scrollView;
}

- (void)refreshStatus:(id)sender {
    (void)sender;
    NSError* error = nil;
    NSDictionary* payload = [self.service refreshStatusWithError:&error];
    [self applyPayload:payload error:error actionName:@"刷新状态"];
}

- (void)enableDemoAndActivate:(id)sender {
    (void)sender;
    NSError* error = nil;
    NSDictionary* payload = [self.service enableDemoAndActivateWithError:&error];
    [self applyPayload:payload error:error actionName:@"启用 Demo 并激活"];
}

- (void)disableDemo:(id)sender {
    (void)sender;
    NSError* error = nil;
    NSDictionary* payload = [self.service disableDemoWithError:&error];
    [self applyPayload:payload error:error actionName:@"停用 Demo"];
}

- (void)copyManualAcceptanceInstructions:(id)sender {
    (void)sender;
    NSString* instructions = [self.service manualAcceptanceInstructions];
    NSPasteboard* pasteboard = NSPasteboard.generalPasteboard;
    [pasteboard clearContents];
    [pasteboard setString:instructions forType:NSPasteboardTypeString];
    [self appendLog:@"已复制验收步骤到剪贴板"];
}

- (void)applyPayload:(NSDictionary*)payload error:(NSError*)error actionName:(NSString*)actionName {
    NSString* summary = [payload[@"summary"] isKindOfClass:NSString.class] ? payload[@"summary"] : @"未激活";
    self.summaryLabel.stringValue = summary;

    NSString* state = [payload[@"state"] isKindOfClass:NSString.class] ? payload[@"state"] : @"not_installed";
    NSString* bundlePath = [payload[@"bundle_path"] isKindOfClass:NSString.class] ? payload[@"bundle_path"] : @"";
    NSString* hostExecutablePath = [payload[@"host_executable_path"] isKindOfClass:NSString.class]
        ? payload[@"host_executable_path"]
        : @"";
    NSString* extensionIdentifier = [payload[@"extension_identifier"] isKindOfClass:NSString.class]
        ? payload[@"extension_identifier"]
        : @"";
    NSString* readinessStage = [payload[@"readiness_stage"] isKindOfClass:NSString.class]
        ? payload[@"readiness_stage"]
        : @"unknown";
    NSString* nextAction = [payload[@"next_action"] isKindOfClass:NSString.class]
        ? payload[@"next_action"]
        : @"点击“启用 Demo 并激活”";
    NSString* devicePrefix = [payload[@"device_prefix"] isKindOfClass:NSString.class] ? payload[@"device_prefix"] : @"";
    NSString* lastError = error.localizedDescription ?: ([payload[@"last_error"] isKindOfClass:NSString.class] ? payload[@"last_error"] : @"");
    NSString* demoModeEnabled = [payload[@"demo_mode_enabled"] respondsToSelector:@selector(boolValue)]
        && [payload[@"demo_mode_enabled"] boolValue] ? @"YES" : @"NO";
    NSArray* devices = [payload[@"devices"] isKindOfClass:NSArray.class] ? payload[@"devices"] : @[];
    NSArray* allDevices = [payload[@"all_devices"] isKindOfClass:NSArray.class] ? payload[@"all_devices"] : @[];
    NSString* approvalRequired = [payload[@"approval_required"] respondsToSelector:@selector(boolValue)]
        && [payload[@"approval_required"] boolValue] ? @"YES" : @"NO";
    NSString* ipcReady = [payload[@"ipc_ready"] isKindOfClass:NSNumber.class]
        ? ([(NSNumber*)payload[@"ipc_ready"] boolValue] ? @"YES" : @"NO")
        : @"unknown";
    NSString* visibleDeviceList = devices.count > 0 ? [devices componentsJoinedByString:@", "] : @"(none)";
    NSString* allDeviceList = allDevices.count > 0 ? [allDevices componentsJoinedByString:@", "] : @"(none)";

    self.statusLabel.stringValue = [NSString stringWithFormat:
        @"State: %@\nReadiness stage: %@\nNext action: %@\nBundle: %@\nHost executable: %@\nExtension identifier: %@\nDemo mode: %@\nApproval required: %@\nIPC ready: %@\nDevice prefix: %@\nVisible devices: %lu\nFiltered devices: %@\nAll devices: %@\nLast error: %@",
        state,
        readinessStage,
        nextAction,
        bundlePath.length > 0 ? bundlePath : @"(empty)",
        hostExecutablePath.length > 0 ? hostExecutablePath : @"(empty)",
        extensionIdentifier.length > 0 ? extensionIdentifier : @"(empty)",
        demoModeEnabled,
        approvalRequired,
        ipcReady,
        devicePrefix.length > 0 ? devicePrefix : @"(empty)",
        (unsigned long)devices.count,
        visibleDeviceList,
        allDeviceList,
        lastError.length > 0 ? lastError : @"(none)"];

    if (error != nil) {
        [self appendLog:[NSString stringWithFormat:@"%@ 失败: %@", actionName, error.localizedDescription ?: @"unknown error"]];
    } else {
        [self appendLog:[NSString stringWithFormat:@"%@ 完成: %@", actionName, summary]];
    }
}

- (void)appendLog:(NSString*)line {
    if (line.length == 0) {
        return;
    }
    [self.logLines addObject:line];
    while (self.logLines.count > 12) {
        [self.logLines removeObjectAtIndex:0];
    }
    self.logView.string = [self.logLines componentsJoinedByString:@"\n"];
}

@end
