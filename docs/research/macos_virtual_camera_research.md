# macOS 虚拟摄像头技术调研

**项目**：Virtual Camera  
**范围**：为现有项目增加 macOS 13+ 原生虚拟摄像头能力，且不影响 Windows/Linux  
**目标架构**：`arm64`、`x86_64`、`universal2`  
**调研日期**：2026-06-26  
**状态**：仅做技术调研，本文件不包含实现代码

## 1. 执行摘要

针对当前仓库，推荐的 macOS 方案为：

**PySide6 App -> 原生 IPC 桥接 -> Frame Producer -> CoreMediaIO Camera Extension -> 系统摄像头设备 -> Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime**

最终建议如下：

1. **CoreMediaIO Camera Extension 作为唯一正式 macOS 虚拟摄像头方案。**
2. **不使用 Swift**，macOS 原生层采用 **Objective-C++ (`.mm`) + C/C++** 实现。
3. IPC 采用**混合架构**：
   - **XPC / Mach Service** 负责控制面
   - **共享内存 RingBuffer 或 IOSurface-backed frame slots** 负责数据面
4. Python 侧接口优先**对齐当前仓库 Windows 已有对外接口**，但**运行时不依赖 OBS 安装**。
5. DAL Plug-In 仅作为历史调研对象，不作为正式交付方案。

推荐这条路线的原因：

- 它是目前最符合 Apple 现行扩展模型的 macOS 虚拟摄像头路径。
- 它是 macOS 13/14/15 上最有希望获得现代应用全面兼容的路线。
- 它天然适配签名、公证、`pkg` 安装和自动化构建流程。
- 相关 API 通过 Objective-C 公共头文件暴露，因此可以在**不使用 Swift**的前提下完成实现。

## 2. 当前仓库上下文

仓库中已经存在一些应当保留的跨平台抽象：

- Python SDK 入口：[camera-core/src/akvc/sdk/virtual_camera.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/sdk/virtual_camera.py)
- 平台 Sink 工厂：[camera-core/src/akvc/core/frame_sink/__init__.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/core/frame_sink/__init__.py)
- 现有 macOS POSIX 共享内存生产者原型：[camera-core/src/akvc/core/frame_sink/macos_shm.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/core/frame_sink/macos_shm.py)
- 桌面层服务门面已经预留了 macOS 路径：[apps/desktop/akvc_app/services/facade.py](/Users/admir/workspace/virtual-camera/apps/desktop/akvc_app/services/facade.py)

当前工作区里还能看到一套被删除中的旧 macOS Swift 原型，位于 `virtualcam/macos/...`。由于新的产品约束是“不要使用 Swift”，这部分只能作为历史参考，不应直接恢复或继续沿用。

## 3. 评估维度

本次调研从以下维度评估候选方案：

1. Apple 在 macOS 13/14/15 上的支持状态。
2. Zoom、Teams、Meet、OBS、QuickTime、FaceTime 的兼容性前景。
3. 是否能支持 PySide6 实时推送视频帧。
4. 是否支持 `QImage`、`QPixmap`、`numpy.ndarray` 和 OpenCV `Mat`。
5. 是否有机会达成 `720p / 1080p / 4K` 与 `30 / 60 fps`。
6. 是否适合签名、公证、`pkg` 安装和 CI/CD。
7. 是否能避免 Swift，并且不影响 Windows/Linux 路径。

## 4. 方案 A：CoreMediaIO Camera Extension

### 4.1 技术原理

CoreMediaIO Camera Extension 是 Apple 现代化的用户态摄像头扩展机制。扩展本身会向系统发布：

- `CMIOExtensionProvider`
- `CMIOExtensionDevice`
- `CMIOExtensionStream`
- 对应的 `...Source` 协议实现

系统随后通过 CoreMediaIO / AVFoundation 采集链路把该流暴露成一个标准摄像头设备，供应用选择。

从本机 Xcode 15.2 的 macOS SDK 可确认：

- `CMIOExtensionProvider`、`CMIOExtensionDevice`、`CMIOExtensionStream` 自 **macOS 12.3+** 开始可用
- 流延迟、设备延迟等属性在 **macOS 14.4+** 仍持续演进
- `legacyDeviceID` 仍被支持，用于兼容旧客户端的设备标识预期

相关本机 SDK 头文件：

- `/Applications/Xcode.app/.../CoreMediaIO.framework/Headers/CMIOExtensionProvider.h`
- `/Applications/Xcode.app/.../CoreMediaIO.framework/Headers/CMIOExtensionDevice.h`
- `/Applications/Xcode.app/.../CoreMediaIO.framework/Headers/CMIOExtensionStream.h`
- `/Applications/Xcode.app/.../CoreMediaIO.framework/Headers/CMIOExtensionProperties.h`
- `/Applications/Xcode.app/.../SystemExtensions.framework/Headers/SystemExtensions.h`

### 4.2 Apple 支持状态

**强支持，且是现代路径。**

本机 SDK 证据表明：

- `CMIOExtension*` 是公开公共头文件，不是私有接口。
- `SystemExtensions.framework` 提供了标准安装激活方式，即 `OSSystemExtensionRequest`。
- 新版 SDK 仍在补充相关属性和能力，说明这条路线仍在被 Apple 主动维护，而不是历史兼容 API。

因此，对 macOS 13+ 来说，Camera Extension 是最明确的 Apple 正向路径。

### 4.3 安装模型

该扩展需要嵌入 App Bundle：

- `Contents/Library/SystemExtensions`

激活通过：

- `OSSystemExtensionRequest.activationRequestForExtension(...)`

根据 `SystemExtensions.h`，需要特别注意：

- 安装可能需要**用户手动批准**
- 完成可能需要**重启**
- 常见失败包括 entitlement 缺失、签名无效、被系统策略拒绝、Bundle 位置不合法
- 发起安装流程时要求提供 `NSSystemExtensionUsageDescription`

这也是为什么 `pkg` 是最合理的主安装形式。

### 4.4 宿主形态说明

需要特别澄清一点：**Camera Extension 并不等于“完全不需要宿主进程”**，只是**不一定需要单独的常驻 daemon host**。

以 `/Users/admir/workspace/cameraextension` 这个参考项目为例，可以看到：

- `samplecamera.xcodeproj` 同时包含 `samplecamera.app` 和 `cameraextension.systemextension`
- `samplecamera.app` 通过 `Embed System Extensions` 把扩展嵌入自己的 `Contents/Library/SystemExtensions`
- `samplecamera/ViewController.swift` 中使用 `OSSystemExtensionRequest.activationRequest(...)` 提交激活
- 同一个 app 还会通过 CoreMediaIO C API 连接扩展暴露出的 sink stream，并把帧送进虚拟摄像头

这说明它的真实形态是：

1. **主 app 充当宿主容器**
2. **主 app 负责激活 / 升级 / 卸载系统扩展**
3. **主 app 负责把自己的帧写入 extension 暴露的 sink stream**
4. **Camera Extension 再把 sink 帧转发到 source stream，供系统应用消费**

因此，这个项目证明的是：

- **可以没有“单独的 host helper/daemon”**
- 但**通常仍然需要某个宿主 app 或宿主可执行体**来承担安装激活和运行期控制职责
- 真正“纯 extension、零宿主、零外部控制面”的产品形态，并不是这个示例所展示的路径
- 对本项目而言，`akvc-host.app` 应定位为容器 / 激活器 / 命令桥，而不是 `1080p60` 帧热路径上的常驻转发进程
- 帧数据面推荐保持为 `Python producer -> shared memory / IOSurface -> Camera Extension`，这样更接近低延迟和 CPU `<10%` 目标

### 4.5 兼容性前景

这条路线的兼容性预期最高，因为它是通过系统摄像头栈暴露设备，而不是绑定在某个特定宿主应用内部。

按应用类型给出当前判断：

| 应用 | Camera Extension 预期表现 | 置信度 |
|---|---|---|
| FaceTime | 可作为系统摄像头显示 | 高 |
| QuickTime Player | 可作为系统摄像头显示 | 高 |
| OBS Studio | 可作为系统摄像头显示 | 高 |
| Zoom | 可作为系统摄像头显示 | 高 |
| Google Meet（Chrome/Safari） | 应可在浏览器摄像头选择器中显示 | 中高 |
| Microsoft Teams | 应可作为系统摄像头显示 | 中高 |

说明：

- 这里的判断是基于平台路径和现有实现经验的推断，不代表已经对每个最新应用版本完成实机认证。
- 最终仍需要在目标版本矩阵上做真实集成验证。

### 4.6 性能适配性

这条路线有机会达到目标性能，但前提是帧数据面必须做到零拷贝或近零拷贝。

以 NV12 原始吞吐量粗估：

| 模式 | 单帧字节数 | 每秒字节数 |
|---|---:|---:|
| 1280x720@60 | 1,382,400 | 82,944,000 |
| 1920x1080@60 | 3,110,400 | 186,624,000 |
| 3840x2160@60 | 12,441,600 | 746,496,000 |

这意味着：

- 在 `1080p60` 下，每多一次全帧 memcpy，就大约增加 **186 MB/s** 内存流量。
- 在 `4K60` 下，每多一次全帧 memcpy，就大约增加 **746 MB/s** 内存流量。

因此：

- **纯 XPC 传帧不推荐**
- **共享内存 Ring 或 IOSurface-backed slot 更合适**
- Python 侧不能在热路径中承担频繁深拷贝

### 4.7 优点

- 最符合 Apple 长期方向。
- 最有希望实现系统级应用全面识别。
- 适合系统扩展安装、签名、公证、`pkg` 分发。
- 可以用 Objective-C++ 与 C/C++ 完成，满足“不使用 Swift”的要求。
- Python 生产者与原生消费者边界清晰。

### 4.8 缺点

- 安装、签名、公证复杂度最高。
- 用户授权流程不可避免。
- 原生调试难度高于普通用户态插件。
- 要达成 `1080p60` 低 CPU，需要非常谨慎地设计 IPC 和内存路径。

## 5. 方案 B：OBS Virtual Camera 实现路径

### 5.1 OBS 当前做法

OBS 是最重要的工程参考，因为它已经在生产环境中支持现代 macOS 虚拟摄像头。

从 OBS 源码可以观察到：

- `plugins/mac-virtualcam/CMakeLists.txt` 会构建：
  - `src/obs-plugin`
  - `src/dal-plugin`
  - `src/camera-extension`
- `plugin-main.mm` 中通过 `@available(macOS 13.0, *)` 优先走 **Camera Extension**
- 同文件把 DAL 标记为 **“deprecated since macOS 12.3”**

因此 OBS 的策略很清晰：

- **macOS 13+**：首选 Camera Extension
- **旧版本兼容**：保留 DAL 作为过渡方案

### 5.2 OBS 的数据路径

OBS 中可见的关键原生组件包括：

- `CVPixelBufferPool`
- CoreMediaIO device/stream 查询
- `CMSimpleQueue`
- `CMSampleBufferCreateForImageBuffer`
- 旧 DAL 路径下的 Mach service 消息协议

OBS 的 Mach 协议头文件中定义了：

- connect message
- frame message
- stop message

这说明它采用的是非常典型的工程模型：

1. 生命周期和控制信号走消息式 IPC
2. 帧数据依赖原生像素缓冲区与队列管理

### 5.3 对本项目的启示

值得借鉴的点：

- macOS 13+ 优先 Camera Extension。
- 原生层围绕 `CVPixelBuffer` / `CMSampleBuffer` 设计，而不是直接传 Python 对象。
- 安装/激活流程与运行期生产帧流程分离。
- 使用原生像素缓冲池与队列，而不是在扩展边界做多次格式转换。

不应直接照搬的点：

- 不能要求用户必须安装 OBS。
- 不能把 DAL 作为正式产品路径继续带着。
- 不能把 Python API 设计绑死在 OBS 当前的运行模型上。

## 6. 方案 C：DAL Plug-In

### 6.1 技术原理

DAL Plug-In 是旧版 CoreMediaIO 设备模型，核心是基于 CFPlugIn 风格的硬件插件接口。当前本机 SDK 里对应头文件为：

- `/Applications/Xcode.app/.../CoreMediaIO.framework/Headers/CMIOHardwarePlugIn.h`

这个头文件依然存在，但它代表的是 Camera Extension 之前的旧接口体系。

### 6.2 Apple 支持状态

**仅具备历史兼容意义，不适合在 macOS 13+ 上作为新产品方案。**

理由：

- DAL 头文件整体风格和 System Extension 新体系明显脱节。
- Camera Extension 才是 Apple 仍在演进的正式接口面。
- OBS 这类成熟开源项目也已经把 DAL 视为兼容负担，而非首选实现。
- `pyvirtualcam` 在 macOS 上的支持方式也已经随着新版本 OBS 迁移，进一步说明生态重心已转向新方案。

### 6.3 兼容性前景

DAL 在部分应用组合里仍可能可用，但它不适合本项目的目标：

- 对沙盒或 Hardened Runtime 应用更不稳定
- 后续 macOS 版本保持良好行为的概率更低
- 更依赖具体应用的加载行为
- 虽然安装比 Camera Extension 简单，但现代应用兼容性明显更差

### 6.4 优点

- 作为历史方案更容易理解。
- 对理解早期 CoreMediaIO 虚拟设备模型仍有参考价值。
- 可用于补充兼容性背景说明。

### 6.5 缺点

- 不是长期产品路线。
- 对现代 macOS 应用兼容性更差。
- 不符合 Apple 当前安全模型和扩展模型。
- 与项目目标中的 macOS 13/14/15 支持要求不匹配。

### 6.6 结论

**不建议在本项目中实现 DAL 正式支持**，最多保留为历史调研与迁移说明。

## 7. 方案 D：其他开源虚拟摄像头项目

### 7.1 `pyvirtualcam`

`pyvirtualcam` 对本项目最重要的价值在于 **生态参考与使用方式参考**，而不是本项目 Python 接口的直接对齐目标，更不是其 macOS 设备后端本身。

根据其 README：

- 支持 Windows、macOS、Linux
- macOS 上依赖 **OBS**
- 在 macOS 13+ 上，新版本通常要求 **OBS 30+**

这说明：

- 它的 Python 接口形态是成熟且被社区验证过的
- Python 调用者无需关心底层 CMIO 细节
- 但其 macOS 后端不是独立系统方案，而是复用 OBS 已安装的虚拟摄像头能力

因此，`pyvirtualcam` 更适合做 **生态和用户习惯参考**，不适合直接作为本项目 macOS 产品架构，也不应成为本项目 Python 接口的首要对齐目标。

### 7.2 `akvirtualcamera`（webcamoid）

`akvirtualcamera` 的 README 描述了：

- Windows 路径为 DirectShow filter
- macOS 路径为 **CoreMediaIO plugin**

它的价值主要在：

- 跨平台设备/服务架构组织方式
- helper / manager 分层
- 早期 macOS CoreMediaIO 插件式实现思路

但对一个面向 macOS 13+ 的新实现来说，它仍更接近旧插件时代，而不是 Camera Extension 时代。

### 7.3 开源项目经验总结

| 项目 | 有价值的部分 | 不足之处 |
|---|---|---|
| OBS | 现代 macOS Camera Extension 工程化路径 | 仍带有 OBS 自身运行时假设 |
| pyvirtualcam | 生态认知度高、用户使用方式成熟 | macOS 上依赖外部虚拟摄像头安装，且不符合本项目接口对齐方向 |
| akvirtualcamera | 跨平台服务/设备分层思路 | macOS 路径偏旧式 CoreMediaIO plugin |

## 8. IPC 调研

本项目对 macOS IPC 的要求不是“能工作就行”，而是必须同时兼顾：

- 低延迟
- 零拷贝或近零拷贝
- 高吞吐量
- `1080p60` 下 CPU `<10%`

### 8.1 纯 XPC

优点：

- 控制语义清晰
- 沙盒边界清楚
- 请求/响应模型易于实现

缺点：

- 帧负载复制成本高
- 不适合 `1080p60`，更不适合 `4K60`
- 难以把 Python 热路径开销压低

**结论**：仅适合控制面，不适合帧数据面。

### 8.2 Shared Memory RingBuffer

优点：

- 内存布局可控
- 可用 C/C++ 实现
- 易于通过薄原生绑定暴露给 Python
- 很适合表达序列号、丢帧策略、slot 所有权和指标

缺点：

- 同步与异常恢复设计要求高
- 容易出现原生内存生命周期问题
- 如果仍按普通字节缓冲做全量复制，严格意义上仍不是完全零拷贝

**结论**：是很好的主数据面候选。

### 8.3 IOSurface-backed Pool

优点：

- macOS 原生零拷贝能力
- 与 `CVPixelBuffer` 适配天然
- 与 CoreVideo / CoreMedia 生态一致
- 更有机会在高分辨率高帧率下降低 CPU 与内存压力

缺点：

- 原生实现复杂度高于普通 POSIX 共享内存
- Python 桥接成本更高

**结论**：是最终性能导向设计里最优的数据面选择。

### 8.4 IPC 最终推荐

推荐采用**混合架构**：

1. **XPC / Mach Service**
   - 生命周期控制
   - 安装状态查询
   - stream 状态
   - 格式协商
   - 指标、错误上报
2. **IOSurface-backed frame ring** 或 **App Group shared-memory ring**
   - 帧描述符
   - slot 所有权
   - 时间戳
   - 序列号

建议的 slot 元数据：

- `seq`
- `width`
- `height`
- `fourcc`
- `stride[2]`
- `pts_ns`
- `flags`
- `slot_state`

建议的 ring 深度：

- `1080p60` 至少 `4` 个 slot
- `4K60` 预研建议 `6-8` 个 slot

建议的丢帧策略：

- latest-frame-wins
- 不因消费端背压阻塞 UI 线程

## 9. 输入格式支持调研

需求要求支持：

- `QImage`
- `QPixmap`
- `numpy.ndarray`
- OpenCV `Mat`

建议的统一归一化路径：

1. `QPixmap` -> 在 GUI 线程转换为 `QImage`
2. `QImage` -> 检查格式，尽量直接暴露字节缓冲
3. `numpy.ndarray` / OpenCV `Mat` -> 要求连续内存 fast path
4. 统一归一化到以下其中一种：
   - `BGRA`
   - `BGR`
   - `RGB`
   - 已经是 `NV12` 的 fast path
5. 再由原生桥接层做一次性转换，进入扩展所需的数据面格式

调研结论：

- Python 公共接口完全可以支持这四类输入
- 真正的高吞吐热路径应优先鼓励使用连续 `numpy` buffer 或原生像素缓冲
- `QPixmap` 更适合作为易用性输入，而不是性能优先输入

## 10. 分辨率与帧率调研

Camera Extension 技术上可以支持目标分辨率与帧率，因为 stream format 与 frame duration 属性本身就是显式可声明的。

建议广告的模式包括：

- `1280x720 @ 30`
- `1280x720 @ 60`
- `1920x1080 @ 30`
- `1920x1080 @ 60`
- `3840x2160 @ 30`
- `3840x2160 @ 60`

需要特别强调：

- `1080p60` 是最合理的主性能验收目标
- `4K60` 应实现，但建议单独 benchmark 与验收，因为内存带宽压力显著更高

## 11. 兼容性对比

| 方案 | Apple 支持状态 | macOS 13+ | Zoom / Teams / Meet / OBS / QuickTime / FaceTime | 分发与签名 | 最终结论 |
|---|---|---|---|---|---|
| CoreMediaIO Camera Extension | 当前正式现代方案 | 优秀 | 最有希望完整覆盖 | 复杂但方向正确 | **推荐** |
| 把 OBS Virtual Camera 当运行时依赖 | 间接可用 | 良好 | 可工作，但依赖 OBS 生命周期 | 原型更快，产品不合适 | 不推荐作为产品后端 |
| DAL Plug-In | 旧式兼容方案 | 弱 | 对现代目标不可靠 | 虽简单但方向错误 | 放弃 |
| 直接复用 `pyvirtualcam` 后端 | 仅生态参考 | 依赖 OBS | 仅在 OBS 路径可用时成立 | 不是独立系统方案 | 不采用 |

## 12. 最终推荐架构

### 12.1 运行时架构

```text
PySide6 App
  -> Python 帧归一化
  -> macOS 原生桥接层
  -> 帧数据面（IOSurface-backed ring / shared-memory ring）
  -> Camera Extension
  -> CMIO device/stream
  -> 系统摄像头客户端
```

安装激活侧另有一条低频控制链路：`pkg / Python SDK / CLI -> container app 或 host tool ->
OSSystemExtensionRequest -> Camera Extension activation`。这条链路不应参与高频视频帧转发。

### 12.2 原生组件建议

建议采用：

- **Objective-C++** 实现 Camera Extension、Host App 与 XPC 边界
- **C/C++** 实现 RingBuffer、帧元数据 ABI、颜色转换和工具函数
- 如性能验证需要，可补充 **Metal** 或 `libyuv` / `vImage` 加速

明确不建议：

- 使用 Swift
- 使用纯 XPC 传输帧数据
- 把 DAL 作为正式交付后端

### 12.3 建议模块布局

按照需求中指定的目标结构，推荐落成。结合当前仓库风格，建议映射为：

```text
virtualcam/macos/camera_extension/
  CMIOExtensionProvider
  CMIOExtensionDevice
  CMIOExtensionStream
  FrameProvider
  StreamSource

virtualcam/macos/ipc/
  ring buffer
  frame metadata ABI
  XPC control protocol
  IOSurface/shared-memory helpers

camera-core/src/akvc/platforms/macos/
  virtual_camera.py
  installation/status helpers
  windows-aligned facade
```

### 12.4 Python API 建议

macOS Python 侧建议**优先复用或对齐现有 Windows 对外类**：

- 当前仓库已有类：`akvc.sdk.virtual_camera.VirtualCamera`
- 当前 Windows 侧对外行为核心包括：
  - `__init__(width, height, fps, helper_exe=None, pipeline=None)`
  - `start(name="AK Virtual Camera")`
  - `push_frame(bgr)`
  - `stop()`
  - `close()`
  - `shutdown()`
  - `started`
  - `consumer_count`

因此，macOS 更推荐的目标不是新增一个完全独立的“类风格”，而是让 darwin 平台尽量落入同一套 SDK 入口；如果阶段性需要平台专用类，也应保持与现有 Windows SDK 语义一致。

阶段性平台类可以设计为：

```python
class MacVirtualCamera:
    def __init__(self, *, width=1280, height=720, fps=30.0, helper_exe=None, pipeline=None): ...
    @property
    def started(self): ...
    @property
    def consumer_count(self): ...
    def start(self, name="AK Virtual Camera"): ...
    def push_frame(self, bgr): ...
    def stop(self): ...
    def close(self): ...
    def shutdown(self): ...
    def enumerate_devices(self): ...
    def is_installed(self): ...
    def install_extension(self): ...
```

行为建议：

- 优先与当前 `akvc.sdk.virtual_camera.VirtualCamera` 语义和命名对齐
- 如需保留 `send(frame)` 这种平台便捷别名，应作为 `push_frame(...)` 的薄封装，而不是新的主接口
- 所有 macOS 特定逻辑都用 `sys.platform == "darwin"` 保护
- Windows/Linux 工厂与调用路径保持不变，只增加 darwin 分支
- 长期目标应是让调用方尽量继续使用统一的 `VirtualCamera` 入口，而不是按平台分裂 SDK

### 12.5 构建、签名与 CI/CD 建议

推荐的 macOS 分发策略：

- 主交付物：**`VirtualCamera.pkg`**
- 次交付物：已签名的 **`.dmg`** 与 **`.zip`**，用于内部测试或应用分发
- App Bundle 安装位置建议固定在 **`/Applications`**，降低 System Extension 位置不合法风险

推荐的二进制策略：

- 分别构建 **`arm64`**
- 分别构建 **`x86_64`**
- 对外分发产物尽量合并为 **`universal2`**
- Extension / Helper / Native Library 在同一发行包内保持架构一致

推荐的签名流程：

1. 签原生二进制
2. 签 system extension
3. 签 host/container app
4. 生成 `pkg`
5. 提交 notarize
6. `staple`
7. `staple` 后执行 smoke test

推荐的自动化策略：

- **GitHub Actions**
  - 使用符合架构要求的 macOS runner
  - 如果托管 runner 的 Intel / Apple Silicon 组合不可持续，则切换为 self-hosted Mac runner
- **Jenkins**
  - 建议使用专用 Mac mini 节点处理：
    - 已签名 release build
    - notarization 凭据
    - Zoom / Teams / Meet / QuickTime / FaceTime / OBS UI 自动化

调研结论：

- 大部分构建、签名、公证可以自动化
- 真正的应用兼容性验证更适合在 **self-hosted macOS 实机**上完成
- System Extension 与 notarization 流程适合自动化，但不应完全依赖临时托管 runner

## 13. 风险与开放问题

### 13.1 主要风险

1. **System Extension 用户授权成本**
   - 缓解：`pkg` 安装、明确 UX、提供状态检测 API 与故障排查文档。
2. **`1080p60` 下 CPU 目标不达标**
   - 缓解：减少复制、优先使用 IOSurface-backed 帧、尽早建立 benchmark。
3. **不同应用版本兼容性差异**
   - 缓解：对 Zoom、Teams、Meet、OBS、QuickTime、FaceTime 做版本矩阵实测。
4. **“不能用 Swift”提高原生开发复杂度**
   - 缓解：Objective-C++ 完全可行，因为相关 API 本身就是 Objective-C 头文件接口。
5. **`4K60` 性能不稳定**
   - 缓解：把 `4K60` 与 `1080p60` 分开验收，单独设定性能阈值。

### 13.2 风险结论

这些风险都是真实存在的，但它们不会改变推荐架构本身。它们影响的是实现顺序、benchmark 策略与测试矩阵，而不是平台路线选择。

## 14. 最终推荐方案

对本项目而言，推荐的 macOS 技术路线是：

1. **正式交付独立的 CoreMediaIO Camera Extension 实现。**
2. **所有 macOS 原生代码使用 Objective-C++ 与 C/C++。**
3. **控制面走 XPC，数据面走共享内存 / IOSurface RingBuffer。**
4. **Python 公共接口优先对齐当前仓库 Windows 已有 `VirtualCamera` SDK，后端完全自研。**
5. **不交付 DAL。**
6. **运行时不依赖 OBS。**

这是当前唯一能较完整满足以下目标的路线：

- macOS 13+
- Apple Silicon + Intel + universal2
- 作为系统摄像头被主流应用识别
- 支持 PySide6 实时推帧
- 支持签名、公证、`pkg` 分发
- 满足低延迟、高吞吐量性能目标
- 不影响 Windows/Linux 既有实现
- 不使用 Swift

## 15. 参考资料

### Apple / 本机 SDK

- 本机 Xcode 15.2 SDK 中的 `CoreMediaIO.framework/Headers/CMIOExtensionProvider.h`
- 本机 Xcode 15.2 SDK 中的 `CoreMediaIO.framework/Headers/CMIOExtensionDevice.h`
- 本机 Xcode 15.2 SDK 中的 `CoreMediaIO.framework/Headers/CMIOExtensionStream.h`
- 本机 Xcode 15.2 SDK 中的 `CoreMediaIO.framework/Headers/CMIOExtensionProperties.h`
- 本机 Xcode 15.2 SDK 中的 `CoreMediaIO.framework/Headers/CMIOHardwarePlugIn.h`
- 本机 Xcode 15.2 SDK 中的 `SystemExtensions.framework/Headers/SystemExtensions.h`

### 仓库内参考

- [docs/phase0/architecture-research.md](/Users/admir/workspace/virtual-camera/docs/phase0/architecture-research.md)
- [docs/phase0/technology-selection.md](/Users/admir/workspace/virtual-camera/docs/phase0/technology-selection.md)
- [docs/phase1/component-diagram.md](/Users/admir/workspace/virtual-camera/docs/phase1/component-diagram.md)
- [docs/phase4/implementation-plan.md](/Users/admir/workspace/virtual-camera/docs/phase4/implementation-plan.md)

### 外部参考链接

- OBS mac virtual camera CMake: [raw.githubusercontent.com/obsproject/obs-studio/master/plugins/mac-virtualcam/CMakeLists.txt](https://raw.githubusercontent.com/obsproject/obs-studio/master/plugins/mac-virtualcam/CMakeLists.txt)
- OBS mac virtual camera implementation: [raw.githubusercontent.com/obsproject/obs-studio/master/plugins/mac-virtualcam/src/obs-plugin/plugin-main.mm](https://raw.githubusercontent.com/obsproject/obs-studio/master/plugins/mac-virtualcam/src/obs-plugin/plugin-main.mm)
- OBS Mach protocol header: [raw.githubusercontent.com/obsproject/obs-studio/master/plugins/mac-virtualcam/src/common/MachProtocol.h](https://raw.githubusercontent.com/obsproject/obs-studio/master/plugins/mac-virtualcam/src/common/MachProtocol.h)
- `pyvirtualcam` README: [raw.githubusercontent.com/letmaik/pyvirtualcam/main/README.md](https://raw.githubusercontent.com/letmaik/pyvirtualcam/main/README.md)
- `akvirtualcamera` README: [raw.githubusercontent.com/webcamoid/akvirtualcamera/master/README.md](https://raw.githubusercontent.com/webcamoid/akvirtualcamera/master/README.md)
