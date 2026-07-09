# macOS 架构设计

**项目**：Virtual Camera  
**阶段**：macOS 原生支持设计阶段  
**适用范围**：macOS 13+（Ventura / Sonoma / Sequoia）  
**目标架构**：Apple Silicon `arm64`、Intel `x86_64`、`universal2`

## 1. 文档目的

本文档用于定义本项目 macOS 虚拟摄像头能力的正式架构基线，作为后续测试、实现、重构和验收的统一依据。

本文档明确替代仓库中旧的 Phase 4 Swift 方向约束，新的 macOS 基线为：

1. 使用 **CoreMediaIO Camera Extension**
2. 不使用 Swift
3. 原生层使用 **Objective-C++ + C/C++**
4. Python 对外接口优先**对齐当前 Windows 已有 `akvc.sdk.virtual_camera.VirtualCamera`**
5. 先完成设计与任务拆分，再按 TDD 分阶段实现

## 2. 设计目标

### 2.1 功能目标

1. 在 macOS 13+ 上把虚拟摄像头作为系统摄像头暴露给应用。
2. 支持 Zoom、Teams、Google Meet、OBS、QuickTime、FaceTime 识别。
3. 支持 PySide6 实时推送视频帧。
4. 支持 `QImage`、`QPixmap`、`numpy.ndarray`、OpenCV `Mat` 输入。
5. 支持 `720p / 1080p / 4K`，`30fps / 60fps`。
6. 支持签名、公证、`pkg` 安装和自动化构建。

### 2.2 架构目标

1. 不影响 Windows/Linux 已有实现。
2. 最大化复用现有 Python SDK 抽象。
3. 控制面与帧数据面分离。
4. 帧路径零拷贝优先、低延迟优先。
5. 保持后续 CI/CD、安装、排障与测试矩阵可维护。

## 3. 关键约束

### 3.1 平台约束

1. Camera Extension 是 macOS 13+ 上唯一长期可行的正式方案。
2. System Extension 安装需要用户批准，并受签名、公证、Bundle 位置等限制。
3. Camera Extension 为独立进程，不能直接依赖 Python 运行时。
4. 构建侧需要同时覆盖 `arm64` 与 `x86_64`，并以 `universal2` 作为正式分发目标。

### 3.2 项目约束

1. 不使用 Swift。
2. Python SDK 不以 `pyvirtualcam` 为接口目标。
3. SDK 优先与现有 Windows `VirtualCamera` 类对齐。
4. 每一步必须尽量保持“可编译、可测试、可运行”。

### 3.3 性能约束

1. 目标性能：`1080p60` 下 CPU `<10%`
2. `4K60` 作为增强目标，需要单独 benchmark
3. UI 线程不能因消费端阻塞而卡死

## 4. 总体架构

```text
PySide6 App
  -> Python SDK / Frame Pipeline
  -> macOS Python-Native Bridge
  -> IPC Frame Plane (IOSurface-backed ring or shared-memory ring)
  -> Camera Extension
  -> CoreMediaIO Device / Stream
  -> System Camera Clients
```

container app 不在上述帧热路径中。它是容器 / 激活器 / 命令桥，用于嵌入
`.systemextension`、提交 `OSSystemExtensionRequest`、持有交互式安装请求生命周期、
查询状态和卸载；真正的运行时视频帧路径应直接从 Python producer 进入共享内存或
IOSurface 数据面，再由 Camera Extension 读取并发布为系统摄像头流。

## 5. 组件设计

### 5.1 Python 层

#### `camera-core/src/akvc/sdk/virtual_camera.py`

继续作为 Python 兼容层对外入口，目标不是引入第二套完全独立的 macOS SDK，而是：

1. 让同一个 `VirtualCamera` 在 `win32` 和 `darwin` 下走不同平台实现
2. 对外保持尽量一致的构造与生命周期语义
3. 把 PySide6 直推入口直接上浮到 Python 兼容层 / macOS backend，而不是只停留在 helper 层

当前对齐基线：

- `__init__(width, height, fps, helper_exe=None, pipeline=None)`
- `start(name="AK Virtual Camera")`
- `push_frame(bgr)`
- `send(frame_input)`
- `send_image(image)`
- `send_pixmap(pixmap)`
- `send_widget(widget)`
- `send_screen(screen, window=0, x=0, y=0, width=-1, height=-1)`
- `create_pyside6_bridge()`
- `create_latest_frame_provider(repeat_last=True)`
- `create_pyside6_streamer(timer_factory=None)`
- `stop()`
- `close()`
- `shutdown()`
- `status()`
- `readiness()`
- `inspect_installation()`
- `started`
- `consumer_count`

其中 `start(name="AK Virtual Camera")` 当前已不再只是 Python 侧占位参数：

1. `VirtualCamera.start(name=...)` 会先把目标设备名持久化到默认 App Group 共享文件
2. Camera Extension `AKVCProviderSource` 启动时会读取同一份共享配置，并把它作为 Provider / Device 的默认可见名称
3. 原生 `status / list-devices` 侧的默认 `device_prefix` 也会读取同一份配置
4. `installer.py` 生成的人工验收步骤、检查项和 `manual-results.template.json` 现在也会优先使用该 `device_prefix`
5. 这样 Python 兼容层、原生命令桥、系统摄像头枚举和人工验收模板现在开始共享同一条“设备名配置”来源，不再固定写死为 `AK Virtual Camera`

其中 `helper_exe` 在 macOS 路径下当前也已具备实际意义：

1. 如果传入 `.app` 路径，会作为 container app 覆盖入口
2. 如果传入可执行文件路径，会作为原生控制面二进制覆盖入口
3. 这样外部调用方可以继续沿用 Windows 侧“传 backend 可执行文件路径”的调用习惯，而不必额外切换到一组全新的 macOS 专用构造参数

#### `camera-core/src/akvc/core/frame_sink`

macOS 路径继续作为 FrameSink 模式下的平台实现，职责是：

1. 接收经过 pipeline 处理后的标准帧
2. 写入原生数据面
3. 维护基本 producer 指标
4. 不承担 Camera Extension 安装逻辑

### 5.2 macOS 原生层

#### `platforms/macos/camera_extension`

在当前仓库中，建议实际落点为：

- 原生 Camera Extension 代码：`virtualcam/macos/camera_extension/`
- Python 平台骨架：`camera-core/src/akvc/platforms/macos/`

职责：

1. 向 CoreMediaIO 暴露虚拟摄像头 Provider
2. 创建设备 Device
3. 创建 Stream
4. 从 IPC 数据面取帧
5. 生成 `CVPixelBuffer` / `CMSampleBuffer`
6. 推送给系统摄像头流

建议组件：

- `Provider`
- `Device`
- `Stream`
- `FrameProvider`
- `StreamSource`

#### `platforms/macos/ipc`

在当前仓库中，建议实际落点为：

- Python 协议与 sink：`camera-core/src/akvc/core/frame_sink/`
- Python 平台 IPC 抽象：`camera-core/src/akvc/platforms/macos/`
- 原生 IPC 实现：`virtualcam/macos/ipc/`

当前 Python 侧已补充一层 typed IPC surface：

- `camera-core/src/akvc/platforms/macos/ipc.py`
- 对外导出 `MacFrameBusLayout / MacIPCDescriptor / MacStreamCapabilities`
- 用于把 `shared_memory_name / ipc_transport / mach_service_name / supported_formats / supported_frame_rates`
  从原始状态 JSON 收敛成 SDK / Desktop / 验证工具可直接消费的稳定对象
- 当前 `VirtualCamera.start()` 也已开始优先读取 `ipc_descriptor().framebus.shared_memory_name` 并把它继续传给
  Python `MacOsShmSink`；原生 `AKVCFrameProvider` 与 `framebus_posix.c` 当前也已支持按运行时 shm 名称打开，
  不再只依赖硬编码 `/akvc-frames-v1`
- 当前 `VirtualCamera.start()` 还已调整为“两阶段就绪检查”：
  - 先确认扩展已安装、已批准、且系统摄像头设备已可见
  - 然后先执行一次显式 `sync_ipc_configuration_result(...)`
  - 最后才对 `ipc_not_ready / ipc_environment_blocked` 做最终阻断
  - 这样“配置尚未同步”不会在真正尝试同步之前就被过早拦截
- 当前 `virtualcam/macos/ipc/src/macos_ipc.cpp` 还已补充两级 shm 名称 override：
  - 一级：`AKVC_MACOS_SHM_NAME`
  - 二级：`AKVC_MACOS_SHM_NAME_FILE`，或默认 App Group 路径
    `~/Library/Group Containers/group.com.akvc.shared/akvc-macos-shm-name.txt`
  - 当 override 缺失或非法时，仍会安全回退到默认 `/akvc-frames-v1`
- 当前 Python `VirtualCamera.start()` 也会把最终 `shared_memory_name` 写入同一份 App Group 共享文件，
  让 host/status/provider 与 Python producer 至少开始共享同一条持久化配置通道
- 当前 `AKVCFrameProvider` 已继续改为在每次读帧前轻量刷新一次 descriptor：
  - 如果 App Group 共享文件里的 shm 名称变化，会先关闭旧 consumer
  - 然后在后续轮询中按新 shm 名称重新打开 reader
  - 首帧切换会额外标记 `CMIOExtensionStreamDiscontinuityFlagTime`
- 当前剩余边界：
  - 这是“轮询式热切换”，不是事件驱动控制面
  - 因此配置变更的生效时机仍取决于 Extension 下一次拉帧周期
  - 后续仍建议补一条显式重载/重连控制面，减少切换抖动与状态不透明性

职责：

1. 提供控制面协议
2. 提供高吞吐低延迟数据面
3. 提供 RingBuffer 元数据 ABI
4. 提供 slot 生命周期管理
5. 提供健康检查、序列号和时间戳

建议组件：

- `control_protocol`
- `ring_buffer`
- `frame_metadata`
- `iosurface_pool` 或 `shared_memory_region`
- `metrics`

### 5.3 宿主安装层

需要一层 macOS Host / Container 载体负责：

1. 提交 `OSSystemExtensionRequest`
2. 查询扩展安装状态
3. 驱动安装、升级、卸载工作流
4. 向 Python 层暴露安装状态

这里的“Host”需要明确区分为“职责”而不是“必须单独拆分出的常驻 daemon”：

1. 它可以是主 GUI App
2. 也可以是专门的 helper App / headless App Bundle
3. 但通常不能假设“只有 `.systemextension` 本体就足够完成安装激活和运行期控制”

参考 `/Users/admir/workspace/cameraextension`：

1. `samplecamera.app` 自身就承担了宿主职责
2. 它把 `cameraextension.systemextension` 嵌入到 `Contents/Library/SystemExtensions`
3. 然后由 app 内代码提交 `OSSystemExtensionRequest`
4. 再通过 CoreMediaIO / sink stream 把帧写进 Camera Extension

因此，对当前仓库来说：

1. **“需要宿主职责”** 是成立的
2. **“必须是独立 daemon host”** 并不成立
3. 当前实现仍兼容 legacy `akvc-host.app`，但推荐方向已经转向“由主 GUI App 自身承担 container app 职责”，而不是把独立 host 当成最终产品前提
4. 无论 container app 具体叫什么，它都不承担高频帧转发；`1080p60 / 4K` 数据面必须绕过控制面容器，直接由 Camera Extension 消费共享内存或 IOSurface

进一步澄清：

1. `/Users/admir/workspace/cameraextension` 证明的是“Camera Extension 运行后可以自己作为系统摄像头服务，帧数据面不需要额外常驻 host daemon”
2. 它并不证明“无需容器 App”，因为该项目仍然通过 `samplecamera.app` 嵌入 `.systemextension` 并提交 `OSSystemExtensionRequest`
3. 该参考项目使用 Swift；当前项目仍坚持 Objective-C++ / C++ / Python 路线，不引入 Swift
4. 当前推荐把 legacy host 严格限制为兼容/开发态角色，正式跨平台集成时优先让 GUI App 自身成为 container app，而不是让独立 host 参与帧转发

当前实现基线中，Python 与原生安装层先通过命令桥接收口：

1. `akvc-macos-status` 通过 `OSSystemExtensionRequest.propertiesRequestForExtension` 查询系统扩展状态并输出 JSON
2. `akvc-macos-install` 负责拉起已解析出的 container app 可执行入口并提交激活请求
3. `akvc-macos-uninstall` 负责拉起已解析出的 container app 可执行入口并提交停用请求
4. `akvc-macos-list-devices` 通过 `AVFoundation` 枚举当前系统视频设备，并按 `AKVC_DEVICE_PREFIX` 过滤出虚拟摄像头候选
5. container app 负责真正持有 `OSSystemExtensionRequest` 生命周期，避免命令行工具退出后请求立即丢失
6. `akvc-macos-status` 当前还会主动读取 `AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON` 或默认 `build/macos/.../framebus-roundtrip.json`，把 Python producer 与原生 consumer 的 IPC 自检结果直接并入同一份状态 JSON
7. container app 的 `--activate` 入口当前还会在提交 `OSSystemExtensionRequest` 之前，把 `AKVC_MACOS_SHM_NAME` 或 `AKVC_MACOS_SHM_NAME_FILE`
   指向的 shm 名称持久化到默认 App Group 共享文件，尽量保证系统拉起的 Camera Extension 首次读取到的就是与 Python producer 一致的目标 shm 名称
8. `akvc-macos-sync-ipc` 当前作为显式控制面命令存在：
   - Python / CLI / Desktop 可以直接把目标 shm 名称通过环境变量交给原生命令
   - 该命令会复用原生校验与持久化逻辑，把 shm 配置同步到 App Group 共享文件
   - 结合 `AKVCFrameProvider` 的轮询式热切换，可形成“显式同步 -> Extension 后续拉帧时重连”的最小闭环
   - 当前 Python 兼容层 `VirtualCamera` 也已上浮：
     - `sync_ipc_configuration_result(shared_memory_name=None)`
     - `sync_ipc_configuration(shared_memory_name=None)`
   - CLI 当前也已补充 `akvc sync-ipc [--shared-memory-name ...] [--json]`

Python 侧当前安装收敛策略：

1. `install_extension()` 不再只以安装命令退出码为准
2. 如果状态命令可用，会继续轮询直到进入：
   - `installed`
   - `install_pending_approval`
   - `install_failed`
3. 如果状态已进入 `installed` 且设备枚举命令可用，会继续等待 `enumerate_devices()` 返回至少一个虚拟摄像头候选
4. 这样可以把“安装命令调用成功”和“系统里真正出现可见摄像头”尽量区分开

当前仓库内已落地的基线实现：

1. `AKVCProviderSource` 已改为真实 `CMIOExtensionProviderSource` 协议实现
2. `AKVCDeviceSource` 已改为真实 `CMIOExtensionDeviceSource` 协议实现
3. `AKVCStreamSource` 已改为真实 `CMIOExtensionStreamSource` 协议实现
4. `AKVCFrameProvider` 已内建 `720p / 1080p / 4K` 与 `30 / 60 fps` 格式元数据
5. 当前 `FrameProvider` 已接入 POSIX Shared Memory Ring 读帧路径，可把 Python 侧写入的 NV12 帧转换为 `CMSampleBuffer`
6. 当前 `StreamSource` 的出流策略为：
   - 有新帧：发送真实共享内存帧
   - 无新帧但生产者仍存活：保持上一帧，不插占位
   - 生产者未启动或心跳超时：退回占位帧

## 6. IPC 设计

### 6.1 控制面

控制面采用 **XPC / Mach Service**。

负责内容：

1. 扩展安装状态查询
2. Stream start/stop
3. 格式协商
4. 健康检查
5. 错误上报
6. 指标采集

理由：

1. 适合请求/响应语义
2. 适合跨进程边界
3. 适合控制而不适合高频大帧数据

在真正 XPC 通道接通前，安装/状态类控制面先用**命令桥接 + JSON**占位，确保 SDK 与原生层先围绕稳定协议收口。

## 6.2 数据面

数据面采用两层决策：

### 首选方案：IOSurface-backed Ring

优先级最高，原因：

1. 最符合 macOS 原生图像管线
2. 最有机会逼近零拷贝
3. 易于转换为 `CVPixelBuffer`
4. 更适合 `1080p60` 与 `4K60`

### 备选方案：Shared Memory RingBuffer

适合作为实现早期的简化 baseline，原因：

1. 更容易与当前 `macos_shm.py` 原型衔接
2. 更容易从 Python 直接写入
3. 更容易先建立可测试热路径
4. 当前仓库已经具备 POSIX consumer + Python producer 的共享协议骨架，并开始用单测固定 `producer_seq / seq_head / seq_tail / heartbeat / slot wrap` 行为

缺点：

1. 更容易出现一次或多次全帧复制
2. 对 `4K60` 更不友好

### 结论

实施顺序建议：

1. **架构上以 IOSurface-backed Ring 为目标设计**
2. **若首轮实现复杂度过高，可先用 Shared Memory Ring 建立端到端闭环**
3. **性能阶段再视 benchmark 升级到 IOSurface 主路径**
4. **当前仓库已经在 Shared Memory baseline 上新增 `framebus-roundtrip` 工具，开始用真实 Python producer + C consumer 互通校验替代纯文本契约**

这不改变最终架构方向，只改变实现顺序。

## 7. 帧数据模型

建议统一帧元数据：

```c
struct FrameSlotHeader {
  uint32_t magic;
  uint32_t version;
  uint32_t width;
  uint32_t height;
  uint32_t fourcc;
  uint32_t stride0;
  uint32_t stride1;
  uint64_t pts_ns;
  uint64_t seq;
  uint32_t flags;
  uint32_t slot_state;
};
```

建议支持的主格式：

1. `NV12` 作为主交付格式
2. `BGRA` 作为原生桥接和调试常用格式
3. `BGR/RGB` 作为 Python 输入归一化中间态
4. Shared Memory baseline 当前要求 producer 在写入前先校验 payload 长度足够覆盖 `plane_size[0] + plane_size[1]`，避免异常帧推进 `producer_seq` 或污染 ring slot
5. 当前 `framebus_consumer_probe.c` 会把 `plane_size / checksum / producer_alive / producer_seq / view_seq` 输出为 JSON，供 `tools/macos_framebus_roundtrip.py` 做跨语言回归

## 8. Python 输入归一化

输入支持策略：

1. `QPixmap`
   - 先转 `QImage`
2. `QImage`
   - 根据 format 直接取 bytes，优先走 `BGR888 / RGB888 / BGRA / RGBA / RGB32 / ARGB32`
   - 单通道 `Grayscale8 / Indexed8` 当前也直接支持，并会在 Python 适配层扩展成三通道 BGR
3. `numpy.ndarray`
   - 优先要求连续内存
4. OpenCV `Mat`
   - 按 `numpy.ndarray` 处理

当前仓库已落地的 Python 适配基线：

1. 已新增统一 `frame_input` 适配层
2. `VirtualCamera.push_frame()` 已改为共用该适配层
3. `numpy.ndarray`
   - 支持 `HxW` 灰度
   - 支持 `HxWx3` BGR
   - 支持 `HxWx4` BGRA（丢弃 alpha）
   - 浮点/整型数组统一裁剪并归一化到 `uint8`
4. `QImage / QPixmap`
   - 采用鸭子类型探测，不在 SDK 顶层强依赖 PySide6
   - 支持 `convertToFormat(...)` 回退
   - 支持 `constBits()` 与 `bits()` 两类底层缓冲读取路径
5. 已新增 `akvc.integrations.pyside6`
   - `push_qimage(...)`
   - `push_qpixmap(...)`
   - `push_widget(...)`
   - `push_screen(...)`
   - `LatestFrameProvider`
     - `submit(frame)`：供 WebRTC / AI Avatar / 推理线程提交最新帧
     - `repeat_last=True`：在没有新帧到达时复用上一帧，维持稳定输出节奏
   - `PySide6VirtualCameraStreamer`
     - `start_widget_stream(...)`
     - `start_screen_stream(...)`
     - `start_provider_stream(...)`
     - `start_latest_frame_stream(...)`
     - `start_video_file_stream(...)`
     - `stop()`
     - 普通 provider 如果当前 tick 没有新帧，可直接返回 `None` 或抛 `LookupError`
     - 对由 streamer 内部创建的 `OpenCVVideoFileProvider` 负责关闭，避免视频文件推流切换/停止后泄漏底层 `VideoCapture`
6. 已新增 `tools/pyside6_virtual_camera_demo.py`
   - `provider`：自定义 `QImage` / AI Avatar / WebRTC provider 实时推流
   - `latest-provider`：`LatestFrameProvider.submit(frame)` 异步产帧，再由 Qt 定时器稳定拉帧
   - `widget`：`QWidget.grab()` 实时推流
   - `screen`：`QScreen.grabWindow()` 实时推流
   - `video-file`：OpenCV `VideoCapture` 视频文件实时推流
   - `--report-json`：输出一次示例运行结果，便于纳入统一验证报告
7. 已新增 `tools/macos_topology_contract.py`
   - 持续校验 `AKVCProviderSource -> AKVCDeviceSource -> AKVCStreamSource -> AKVCFrameProvider` 的装配拓扑
   - 持续校验默认 `provider/device/stream` 标识、属性面与 `startServiceWithProvider` 注册链路
   - 持续校验共享内存 ring descriptor 到 `FrameProvider` 的 IPC 接线不会被后续重构破坏
8. 已新增 `tools/macos_input_contract.py`
   - 持续校验输入矩阵
   - 持续校验 PySide6 bridge / streamer 表面
   - 持续校验 demo 模式面
9. 已新增 `tools/macos_build_contract.py`
   - 持续校验 `macOS 13.0` 最低版本声明
   - 持续校验 `arm64 + x86_64` 构建架构声明
   - 持续校验 `tools/make.py build` 是否把双架构约束继续透传给 `xcodebuild`

WebRTC / AI Avatar 推荐桥接方式：

```python
from akvc.integrations.pyside6 import LatestFrameProvider, PySide6VirtualCameraStreamer

provider = LatestFrameProvider(repeat_last=True)
streamer = PySide6VirtualCameraStreamer(camera)
streamer.start_provider_stream(provider, interval_ms=16)

# 在 WebRTC 解码回调或 AI 推理线程中：
provider.submit(frame)
```

统一建议：

1. SDK 对外仍以 `push_frame(...)` 为主入口
2. 输入类型归一化后统一交给 pipeline
3. 如需 `send(frame)` 兼容写法，只作为 `push_frame(...)` 别名，不作为主接口

## 9. Python SDK 对齐策略

macOS 路径的设计原则不是“仿 pyvirtualcam”，而是“对齐当前 Windows SDK”。

### 9.1 目标接口

长期目标：

```python
from akvc.sdk.virtual_camera import VirtualCamera

cam = VirtualCamera(width=1920, height=1080, fps=60)
cam.start()
cam.push_frame(frame)
cam.stop()
cam.close()
```

### 9.2 平台特有能力

macOS 仍会需要额外能力：

- `enumerate_devices()`
- `is_installed()`
- `install_extension()`
- `install_extension_result()`
- `status() / readiness() / inspect_installation()`
- `ipc_descriptor() / stream_capabilities()`

建议这些能力以两种方式提供：

1. 作为内部平台服务挂到 `VirtualCamera` 背后
2. 不再把额外的 macOS 专用辅助类当作当前架构真值；如未来确有需要新增，也应保持与 `VirtualCamera` 生命周期语义一致
3. 用自动化契约固定 `start / push_frame / send / stop / close / shutdown / __enter__ / __exit__`，以及 `enumerate_devices / status / readiness / inspect_installation / ipc_descriptor / stream_capabilities / install_extension_result / sync_ipc_configuration*` 等接口，避免后续原生实现阶段发生 Python API 漂移
4. 用入口链契约继续固定 `tools/pyside6_virtual_camera_demo.py`、`tools/macos_direct_push_demo.py`、CLI 和桌面端 facade 都必须走 `VirtualCamera` 兼容表面，而不是各自绕到平台私有实现

### 9.3 不建议的做法

1. 引入和 Windows 完全不同的一套 macOS SDK 主接口
2. 用 `send()` 替代 `push_frame()` 作为主入口
3. 让调用方必须感知 Camera Extension 细节

## 10. 安装与分发架构

主分发物：

1. `VirtualCamera.pkg`

次分发物：

1. `.dmg`
2. `.zip`

构成建议：

1. Container App
2. System Extension
3. Native helper / launcher
4. Python runtime 与业务代码
5. 安装脚本
6. 卸载脚本

## 11. 测试架构

按 TDD 分层：

### 11.1 单元测试

覆盖：

1. Python 输入归一化
2. Frame metadata 打包/解析
3. RingBuffer 写入/读取
4. 安装状态判断逻辑
5. SDK 生命周期语义

### 11.2 集成测试

覆盖：

1. Python -> IPC 数据面
2. IPC -> Camera Extension
3. Camera Extension -> System Camera
4. 安装/卸载流程

### 11.3 端到端测试

覆盖：

1. Zoom 识别
2. Teams 识别
3. Meet 识别
4. OBS 识别
5. QuickTime 识别
6. FaceTime 识别

### 11.4 性能测试

覆盖：

1. `720p30`
2. `720p60`
3. `1080p30`
4. `1080p60`
5. `4K30`
6. `4K60`

关键指标：

1. CPU
2. 内存
3. 平均帧间延迟
4. P95 / P99 帧延迟
5. 丢帧率
6. 连续稳定性

## 12. 验收工件架构

当前仓库的 macOS 验收链路已经开始收敛到统一会话工件，而不是分散依赖多条命令输出。

推荐把以下工件视为同一条证据链：

1. `preflight.json`
   - 证明当前机器是否具备 `xcodegen / xcodebuild / pkgbuild / codesign / notarytool / stapler`
   - 证明签名、公证环境变量是否已配置
2. `release-diagnostics.json`
   - 证明 Host App / Camera Extension / pkg / dmg / zip 的结构、架构、签名状态和安装位置
3. `smoke-report.json`
   - 证明 `status / install / uninstall` 命令桥接、设备枚举与基础 IPC 摘要
4. `install-session-report.json`
   - 证明 “Python 自动装包 -> Host App -> 激活扩展 -> 安装后状态收敛” 这条更接近真实 SDK 的链路
5. `framebus-roundtrip.json`
   - 证明 Python producer 与原生 consumer 的真实跨语言 IPC 互通
6. `status-binary-check.json`
   - 证明真实 `akvc-macos-status` 二进制会把 `ipc_*` 诊断字段正确合并进状态 JSON
7. `validation-report.json`
   - 证明当前会话对外暴露的安装、能力、runtime assets、demo、benchmark、人工应用验证摘要
8. `session-manifest.json`
   - 作为顶层会话索引，统一收敛 artifacts、steps、summary
9. `session-manifest-check.json`
   - 证明 `session-manifest.json` 自身与其引用工件结构自洽
10. `session-acceptance.json`
    - 证明当前会话距离最终验收标准还差哪些已知缺口、哪些只是证据缺失

当前推荐的阅读顺序：

1. 先看 `session-manifest.json.summary`
2. 再看 `session-manifest-check.json`
3. 再看 `session-acceptance.json`
4. 最后按需要展开 `validation-report / install-session / smoke / benchmark / release-diagnostics`

其中 `session-manifest.json.summary` 当前已开始保留：

1. `effective_start_ready / effective_start_blocker_code`
2. `effective_supported_formats / effective_supported_frame_rates`
3. `artifact_check_present / artifact_check_passed`
4. `acceptance_present / acceptance_ready / acceptance_failed_criteria / acceptance_unknown_criteria`
5. `release_pkg_payload_appledouble_clean`

这让 CI 页面、人工验收和桌面端诊断开始共享同一套“当前是否真的可交付”的摘要口径。

## 13. 风险

主要风险：

1. Camera Extension 安装和批准流程复杂
2. 不用 Swift 会增加原生层样板代码
3. Shared Memory 实现可能无法稳定满足 `1080p60 <10% CPU`
4. 各应用对摄像头枚举行为存在版本差异

缓解策略：

1. 先建立最小闭环，再逐层压性能
2. 先把接口和测试固定，再替换内部 IPC 实现
3. 用 benchmark 驱动 Shared Memory 与 IOSurface 的取舍

## 14. 当前状态（2026-06-27）

当前仓库已经不再停留在“只有架构图”的阶段，而是开始具备可回归的实现与证据骨架：

1. Camera Extension 原生骨架已经切到真实 `CMIOExtensionProviderSource / DeviceSource / StreamSource`
2. Python 侧 `VirtualCamera`、`frame_input` 与 `akvc.integrations.pyside6` 已开始围绕统一入口收口
3. Shared Memory baseline 已具备 `framebus contract + roundtrip + consumer_count` 三层验证
4. 安装、状态、设备枚举、自动装包、runtime assets、release diagnostics、validation session 已开始形成统一工具链
5. `validation-session -> artifact-check -> acceptance` 当前已成为顶层验收会话的正式链路

当前最重要的未完成项仍然是：

1. 真实签名、公证与系统批准链路尚未完成真机闭环
2. Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime 尚未形成完整的实机通过证据
3. `1080p60 CPU <10%` 仍需要在真实 Camera Extension 路径上补全强证据
4. Shared Memory baseline 是否最终升级到 IOSurface 主路径，仍要由 benchmark 与真机稳定性来决定

## 15. 任务拆分原则

实现顺序严格遵循：

1. 设计
2. 测试
3. 实现
4. 重构
5. 文档

详细任务拆分见 [task-breakdown.md](/Users/admir/workspace/virtual-camera/docs/macos/task-breakdown.md)。

## 16. 阶段出口

进入编码前，至少需要完成：

1. 本文档确认
2. 任务拆分确认
3. `build/install/signing/troubleshooting/benchmark` 文档基线完成
4. 明确“首轮数据面是 Shared Memory 还是 IOSurface”
5. 明确首轮 SDK 是否直接接入统一 `VirtualCamera`
