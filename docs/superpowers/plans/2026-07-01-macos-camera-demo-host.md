# macOS Camera Demo Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 macOS 工程中新增一个独立 `akvc-camera-demo-host` target，按 Apple Camera Extension 最小示例思路输出固定测试画面，并形成可编译、可运行、可人工验收的系统摄像头 demo。

**Architecture:** 复用现有 `akvc-camera-extension`、`AKVCFrameProvider` 和 `AKVCStreamSource` 骨架，在 XcodeGen 工程里新增独立 demo host target。demo host 只负责激活和声明 demo 运行模式，固定测试画面通过 extension 内的 demo 帧源 hook 输出到 `CMIOExtensionStream`，不改动 Windows/Linux 逻辑，也不引入新的 Python 或 IPC 热路径。

**Tech Stack:** Objective-C++、CoreMediaIO Camera Extension、XcodeGen (`project.yml`)、pytest 合同测试、现有 macOS host/extension 骨架。

---

## 文件结构

**Create**

- `virtualcam/macos/demo_host/main.mm`
  - demo host 独立入口，调用现有激活桥接逻辑；Task 1 骨架只提交 activation request，不承担长期驻留或 demo 数据面开关
- `virtualcam/macos/demo_host/Info.plist`
  - demo host bundle 元数据
- `virtualcam/macos/demo_host/DemoHost.entitlements`
  - demo host entitlement，保持和 system extension 安装能力对齐
- `virtualcam/macos/demo_host/AKVCDemoFrameGenerator.h`
  - demo 帧生成器接口
- `virtualcam/macos/demo_host/AKVCDemoFrameGenerator.mm`
  - 生成 BGRA 或 provider 可直接消费的固定测试画面
- `docs/macos/demo_host.md`
  - 构建、运行、人工验收说明

**Modify**

- `virtualcam/macos/project.yml`
  - 新增 `akvc-camera-demo-host` target 和 scheme 引用；初版复用现有 host/system-extension 支撑代码，因此会连带引用 `AKVCCommandSupport`、`akvc-macos-ipc` 以及其所需的 framework
- `virtualcam/macos/camera_extension/AKVCFrameProvider.h`
  - 暴露 demo 模式输入接口
- `virtualcam/macos/camera_extension/AKVCFrameProvider.mm`
  - 增加 demo sample buffer 注入与固定帧源读取分支
- `virtualcam/macos/camera_extension/AKVCStreamSource.mm`
  - 保持现有发送链路，允许 demo 帧优先输出
- `tests/unit/test_macos_native_skeleton.py`
  - 新增 target / demo host 文件 / extension demo hook 合同断言

**Test**

- `tests/unit/test_macos_native_skeleton.py`
- 需要时补充 `tests/unit/test_macos_status_contract_tool.py` 中的运行说明合同，但初版优先只改 skeleton 合同

## Task 1: 新增 Demo Target 骨架

**Files:**
- Modify: `virtualcam/macos/project.yml`
- Modify: `tests/unit/test_macos_native_skeleton.py`
- Create: `virtualcam/macos/demo_host/Info.plist`
- Create: `virtualcam/macos/demo_host/DemoHost.entitlements`
- Create: `virtualcam/macos/demo_host/main.mm`

- [ ] **Step 1: 写失败测试，锁定 demo target 和 demo_host 目录契约**

```python
def test_macos_project_yml_declares_camera_demo_host_target() -> None:
    project_yml = MACOS_ROOT / "project.yml"
    text = project_yml.read_text(encoding="utf-8")

    assert "akvc-camera-demo-host:" in text
    assert "demo_host" in text
    assert "DemoHost.entitlements" in text
    assert "demo_host/Info.plist" in text
    assert "akvc-camera-demo-host: all" in text


def test_macos_demo_host_files_exist() -> None:
    expected = [
        MACOS_ROOT / "demo_host" / "main.mm",
        MACOS_ROOT / "demo_host" / "Info.plist",
        MACOS_ROOT / "demo_host" / "DemoHost.entitlements",
    ]
    for path in expected:
        assert path.is_file(), path
```

- [ ] **Step 2: 运行测试，确认按预期失败**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_host or camera_demo_host"
```

Expected:

- FAIL
- 报 `akvc-camera-demo-host` 不存在
- 报 `virtualcam/macos/demo_host/...` 文件不存在

- [ ] **Step 3: 在 `project.yml` 中加入最小可编译 target 骨架**

```yaml
  akvc-camera-demo-host:
    type: application
    platform: macOS
    sources:
      - path: demo_host
        excludes:
          - "Info.plist"
          - "DemoHost.entitlements"
      - path: host/AKVCCommandSupport.h
      - path: host/AKVCCommandSupport.mm
      - path: host/AKVCSystemExtensionSupport.h
      - path: host/AKVCSystemExtensionSupport.mm
      - path: ipc/include
      - path: ipc/src
        excludes:
          - "framebus_consumer_probe.c"
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.sidus.amaran-desktop.demo-host
        PRODUCT_NAME: akvc-camera-demo-host
        INFOPLIST_FILE: demo_host/Info.plist
        CODE_SIGN_ENTITLEMENTS: demo_host/DemoHost.entitlements
        CODE_SIGN_IDENTITY: "-"
        CODE_SIGN_STYLE: Manual
    dependencies:
      - target: akvc-camera-extension
      - target: akvc-macos-ipc
      - sdk: Foundation.framework
      - sdk: AVFoundation.framework
      - sdk: CoreMediaIO.framework
      - sdk: SystemExtensions.framework
```

- [ ] **Step 4: 创建最小 demo host 文件**

`virtualcam/macos/demo_host/main.mm`

```objective-c++
// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

#import "../host/AKVCCommandSupport.h"
#import "../host/AKVCSystemExtensionSupport.h"

int main(int argc, const char* argv[]) {
    @autoreleasepool {
        (void)argc;
        (void)argv;
        NSError* error = nil;
        if (!AKVCSubmitSystemExtensionRequest(YES, 30.0, &error)) {
            NSLog(@"AKVC demo host activation failed: %@",
                  error.localizedDescription ?: @"unknown error");
            return 1;
        }
        return 0;
    }
}
```

`virtualcam/macos/demo_host/DemoHost.entitlements`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.developer.system-extension.install</key>
    <true/>
</dict>
</plist>
```

`virtualcam/macos/demo_host/Info.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundleIdentifier</key>
    <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>0.5.0</string>
    <key>CFBundleExecutable</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSSystemExtensionUsageDescription</key>
    <string>Install AKVC Camera Extension demo to provide a virtual camera device.</string>
</dict>
</plist>
```

- [ ] **Step 5: 运行测试，确认骨架通过**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_host or camera_demo_host"
```

Expected:

- PASS

- [ ] **Step 6: 提交骨架改动**

```bash
git add virtualcam/macos/project.yml \
        virtualcam/macos/demo_host/main.mm \
        virtualcam/macos/demo_host/Info.plist \
        virtualcam/macos/demo_host/DemoHost.entitlements \
        tests/unit/test_macos_native_skeleton.py
git commit -m "feat: add macOS camera demo host skeleton"
```

## Task 2: 新增固定测试画面生成器

**Files:**
- Create: `virtualcam/macos/demo_host/AKVCDemoFrameGenerator.h`
- Create: `virtualcam/macos/demo_host/AKVCDemoFrameGenerator.mm`
- Modify: `virtualcam/macos/project.yml`
- Modify: `tests/unit/test_macos_native_skeleton.py`

- [ ] **Step 1: 写失败测试，锁定 demo frame generator 契约**

```python
def test_macos_demo_frame_generator_contract_is_present() -> None:
    header = (MACOS_ROOT / "demo_host" / "AKVCDemoFrameGenerator.h").read_text(encoding="utf-8")
    impl = (MACOS_ROOT / "demo_host" / "AKVCDemoFrameGenerator.mm").read_text(encoding="utf-8")

    assert "@interface AKVCDemoFrameGenerator" in header
    assert "copyNextSampleBufferWithPresentationTime" in header
    assert "CVPixelBufferCreate" in impl or "CVPixelBufferPoolCreatePixelBuffer" in impl
    assert "CMSampleBufferCreateReadyWithImageBuffer" in impl
    assert "AKVC Demo" in impl
    assert "frameIndex" in impl
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_frame_generator"
```

Expected:

- FAIL
- 报缺少 `AKVCDemoFrameGenerator.h/.mm`

- [ ] **Step 3: 添加最小生成器接口**

`virtualcam/macos/demo_host/AKVCDemoFrameGenerator.h`

```objective-c++
// SPDX-License-Identifier: Apache-2.0
#import <CoreMedia/CoreMedia.h>
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface AKVCDemoFrameGenerator : NSObject

- (instancetype)initWithWidth:(size_t)width height:(size_t)height;
- (CMSampleBufferRef _Nullable)copyNextSampleBufferWithPresentationTime:(CMTime)presentationTime
                                                                  error:(NSError* _Nullable* _Nullable)outError
    CF_RETURNS_RETAINED;

@end

NS_ASSUME_NONNULL_END
```

- [ ] **Step 4: 添加最小固定测试画面实现**

`virtualcam/macos/demo_host/AKVCDemoFrameGenerator.mm`

```objective-c++
// SPDX-License-Identifier: Apache-2.0
#import "AKVCDemoFrameGenerator.h"

#import <CoreVideo/CoreVideo.h>

@interface AKVCDemoFrameGenerator ()
@property(nonatomic, assign) size_t width;
@property(nonatomic, assign) size_t height;
@property(nonatomic, assign) uint64_t frameIndex;
@end

@implementation AKVCDemoFrameGenerator

- (instancetype)initWithWidth:(size_t)width height:(size_t)height {
    self = [super init];
    if (self == nil) {
        return nil;
    }
    _width = width;
    _height = height;
    _frameIndex = 0;
    return self;
}

- (CMSampleBufferRef)copyNextSampleBufferWithPresentationTime:(CMTime)presentationTime
                                                        error:(NSError* _Nullable __autoreleasing*)outError {
    (void)outError;
    self.frameIndex += 1;
    // 初版只要求生成可发送的 BGRA 帧；文字绘制可在后续小步补上。
    return nil;
}

@end
```

说明：

- 本步允许测试继续失败，只建立类型和方法骨架
- 真正返回可用 `CMSampleBufferRef` 放在下一任务步完成

- [ ] **Step 5: 把生成器加入 demo target**

在 `virtualcam/macos/project.yml` 的 `akvc-camera-demo-host` sources 中加入：

```yaml
      - path: demo_host
        excludes:
          - "Info.plist"
          - "DemoHost.entitlements"
```

Expected:

- `AKVCDemoFrameGenerator.h/.mm` 被同一 target 编译

- [ ] **Step 6: 运行测试，确认契约通过**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_frame_generator"
```

Expected:

- PASS

- [ ] **Step 7: 提交生成器骨架**

```bash
git add virtualcam/macos/demo_host/AKVCDemoFrameGenerator.h \
        virtualcam/macos/demo_host/AKVCDemoFrameGenerator.mm \
        virtualcam/macos/project.yml \
        tests/unit/test_macos_native_skeleton.py
git commit -m "feat: add macOS demo frame generator skeleton"
```

## Task 3: 接入 Extension Demo 帧源

**Files:**
- Modify: `virtualcam/macos/camera_extension/AKVCFrameProvider.h`
- Modify: `virtualcam/macos/camera_extension/AKVCFrameProvider.mm`
- Modify: `virtualcam/macos/camera_extension/AKVCStreamSource.mm`
- Modify: `tests/unit/test_macos_native_skeleton.py`

- [ ] **Step 1: 写失败测试，锁定 demo 模式 hook**

```python
def test_macos_frame_provider_supports_demo_mode_hook() -> None:
    header = (MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.h").read_text(encoding="utf-8")
    impl = (MACOS_ROOT / "camera_extension" / "AKVCFrameProvider.mm").read_text(encoding="utf-8")

    assert "AKVC_MACOS_DEMO_MODE" in impl
    assert "setDemoSampleBufferGenerator" in header
    assert "copyDemoSampleBuffer" in impl
    assert "copyLatestClientSampleBufferWithDiscontinuity" in impl
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_mode_hook"
```

Expected:

- FAIL
- 报 `AKVC_MACOS_DEMO_MODE` 或 `setDemoSampleBufferGenerator` 不存在

- [ ] **Step 3: 在 frame provider 中加入 demo 帧生成接口**

`virtualcam/macos/camera_extension/AKVCFrameProvider.h`

```objective-c++
typedef CMSampleBufferRef _Nullable (^AKVCDemoSampleBufferGenerator)(CMTime presentationTime,
                                                                     NSError* _Nullable* _Nullable outError);

- (void)setDemoSampleBufferGenerator:(AKVCDemoSampleBufferGenerator _Nullable)generator;
```

`virtualcam/macos/camera_extension/AKVCFrameProvider.mm`

```objective-c++
@property(nonatomic, copy) AKVCDemoSampleBufferGenerator demoSampleBufferGenerator;

- (void)setDemoSampleBufferGenerator:(AKVCDemoSampleBufferGenerator)generator {
    @synchronized(self) {
        _demoSampleBufferGenerator = [generator copy];
    }
}

- (CMSampleBufferRef)copyDemoSampleBuffer:(NSError* _Nullable __autoreleasing*)outError {
    @synchronized(self) {
        if (_demoSampleBufferGenerator == nil) {
            return nil;
        }
        return _demoSampleBufferGenerator(CMClockGetTime(CMClockGetHostTimeClock()), outError);
    }
}
```

- [ ] **Step 4: 让 stream source 在 demo 模式优先读 demo 帧**

在 `virtualcam/macos/camera_extension/AKVCStreamSource.mm` 的 `emitNextFrame` 中，在读取 client/sample 之前加入：

```objective-c++
NSError* error = nil;
CMIOExtensionStreamDiscontinuityFlags discontinuity = CMIOExtensionStreamDiscontinuityFlagNone;
CMSampleBufferRef sampleBuffer = nil;

if (getenv("AKVC_MACOS_DEMO_MODE") != NULL) {
    sampleBuffer = [self.frameProvider copyDemoSampleBuffer:&error];
}
```

并保留现有 fallback 顺序：

1. demo sample buffer
2. latest client sample buffer
3. shared memory frame
4. placeholder

- [ ] **Step 5: 在 demo host 中初始化 demo 帧生成器**

在 `virtualcam/macos/demo_host/main.mm` 中增加：

```objective-c++
setenv("AKVC_MACOS_DEMO_MODE", "1", 1);
setenv("AKVC_MACOS_DEMO_WIDTH", "1280", 1);
setenv("AKVC_MACOS_DEMO_HEIGHT", "720", 1);
setenv("AKVC_MACOS_DEMO_FPS", "30", 1);
```

说明：

- 初版先用环境变量把 demo 模式显式打通
- 后续如需更干净的 provider 装配，再拆下一步

- [ ] **Step 6: 运行测试，确认 hook 契约通过**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_mode_hook or demo_frame_generator"
```

Expected:

- PASS

- [ ] **Step 7: 运行完整 skeleton 合同测试**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py
```

Expected:

- 现有 macOS skeleton 合同通过
- 如果出现与 demo 无关的既有失败，单独记录，不在本任务扩散修复

- [ ] **Step 8: 提交 extension demo hook**

```bash
git add virtualcam/macos/camera_extension/AKVCFrameProvider.h \
        virtualcam/macos/camera_extension/AKVCFrameProvider.mm \
        virtualcam/macos/camera_extension/AKVCStreamSource.mm \
        virtualcam/macos/demo_host/main.mm \
        tests/unit/test_macos_native_skeleton.py
git commit -m "feat: add macOS camera extension demo frame hook"
```

## Task 4: 文档与最小验收链路

**Files:**
- Create: `docs/macos/demo_host.md`
- Modify: `tests/unit/test_macos_native_skeleton.py`
- Modify: `virtualcam/macos/README.md`

- [ ] **Step 1: 写失败测试，锁定 demo 文档入口**

```python
def test_macos_demo_host_docs_exist_and_reference_manual_validation() -> None:
    text = (ROOT / "docs" / "macos" / "demo_host.md").read_text(encoding="utf-8")
    readme = (MACOS_ROOT / "README.md").read_text(encoding="utf-8")

    assert "akvc-camera-demo-host" in text
    assert "QuickTime Player" in text
    assert "FaceTime" in text
    assert "xcodebuild" in text or "python3 tools/make.py build" in text
    assert "demo_host.md" in readme
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_host_docs"
```

Expected:

- FAIL
- 报 `docs/macos/demo_host.md` 不存在

- [ ] **Step 3: 写最小运行与人工验收文档**

`docs/macos/demo_host.md`

```markdown
# macOS Camera Demo Host

## Build

```bash
python3 tools/make.py build
```

## Run

```bash
./build/macos/Build/Products/Release/akvc-camera-demo-host.app/Contents/MacOS/akvc-camera-demo-host
```

## Manual Validation

1. 打开 QuickTime Player，新建影片录制。
2. 在摄像头列表中选择 AKVC 虚拟摄像头。
3. 确认可见固定测试画面。
4. 可选：在 FaceTime 中确认设备可选。
```

- [ ] **Step 4: 在 macOS README 中挂 demo 文档链接**

在 `virtualcam/macos/README.md` 中加入一行：

```markdown
- Demo host runbook: [docs/macos/demo_host.md](/Users/admir/workspace/virtual-camera/docs/macos/demo_host.md)
```

- [ ] **Step 5: 运行测试，确认文档合同通过**

Run:

```bash
PYTHONPATH=camera-core/src:apps/desktop ./.venv/bin/pytest -q tests/unit/test_macos_native_skeleton.py -k "demo_host_docs"
```

Expected:

- PASS

- [ ] **Step 6: 提交文档与验收链路**

```bash
git add docs/macos/demo_host.md \
        virtualcam/macos/README.md \
        tests/unit/test_macos_native_skeleton.py
git commit -m "docs: add macOS camera demo host runbook"
```

## 自检

### Spec 覆盖

- 独立 demo target：Task 1
- 固定测试画面帧源：Task 2、Task 3
- extension demo hook：Task 3
- 最小人工验收链路：Task 4

没有未覆盖的 spec 条目。

### Placeholder 扫描

- 已避免 `TODO`、`TBD`、`implement later`
- 所有步骤都给出了明确文件、命令和最小代码块

### 类型一致性

- demo target 名称统一使用 `akvc-camera-demo-host`
- demo 模式环境变量统一使用 `AKVC_MACOS_DEMO_MODE`
- demo 帧接口统一使用 `setDemoSampleBufferGenerator` / `copyDemoSampleBuffer`
