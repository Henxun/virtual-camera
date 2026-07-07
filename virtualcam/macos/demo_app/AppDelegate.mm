// SPDX-License-Identifier: Apache-2.0
#import "AppDelegate.h"

#import "MainWindowController.h"

@interface AppDelegate ()
@property(nonatomic, strong) MainWindowController* mainWindowController;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification*)notification {
    (void)notification;
    self.mainWindowController = [[MainWindowController alloc] init];
    [self.mainWindowController showWindow:self];
    [NSApp activateIgnoringOtherApps:YES];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication*)sender {
    (void)sender;
    return YES;
}

@end
