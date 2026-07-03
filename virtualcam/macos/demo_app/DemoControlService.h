// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface DemoControlService : NSObject

- (NSDictionary*)refreshStatusWithError:(NSError* _Nullable* _Nullable)outError;
- (NSDictionary*)enableDemoAndActivateWithError:(NSError* _Nullable* _Nullable)outError;
- (NSDictionary*)disableDemoWithError:(NSError* _Nullable* _Nullable)outError;
- (NSString*)manualAcceptanceInstructions;

@end

NS_ASSUME_NONNULL_END
