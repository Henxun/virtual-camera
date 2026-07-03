// SPDX-License-Identifier: Apache-2.0
#import <CoreMediaIO/CoreMediaIO.h>
#import <Foundation/Foundation.h>

@class AKVCFrameProvider;

NS_ASSUME_NONNULL_BEGIN

@interface AKVCStreamSource : NSObject <CMIOExtensionStreamSource>

@property(nonatomic, strong, readonly) AKVCFrameProvider* frameProvider;
@property(nonatomic, assign, readonly, getter=isStreaming) BOOL streaming;
@property(atomic, readonly) NSArray<CMIOExtensionStreamFormat*>* formats;
@property(atomic, readonly, copy) NSSet<CMIOExtensionProperty>* availableProperties;

- (instancetype)initWithFrameProvider:(AKVCFrameProvider*)frameProvider;
- (void)attachStream:(CMIOExtensionStream*)stream;

@end

NS_ASSUME_NONNULL_END
