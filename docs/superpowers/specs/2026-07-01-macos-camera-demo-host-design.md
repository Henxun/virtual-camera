# macOS Camera Extension Demo Host 设计

日期：2026-07-01

## 目标

在现有 [virtualcam/macos](/Users/admir/workspace/virtual-camera/virtualcam/macos) 工程中新增一个独立的 macOS demo target，按照 Apple CoreMediaIO Camera Extension 的最小示例思路，提供一个可编译、可运行、可人工验收的原生演示链路：

`Demo Host App -> Camera Extension -> System Camera Device -> QuickTime / FaceTime / Zoom`

这个 demo 只负责验证最小系统链路，不引入 PySide6、不引入共享内存热路径、不依赖外部视频源。

## 范围

本次 demo 只包含以下能力：

- 新增一个独立 host target，例如 `akvc-camera-demo-host`
- 通过独立入口激活现有 Camera Extension
- 在 extension 侧输出固定测试画面
- 测试画面包含稳定可辨识的视觉元素：
  - 彩条或渐变背景
  - 帧计数
  - 时间戳
- 支持最小人工验收：
  - 构建 demo
  - 启动 demo
  - 在 QuickTime / FaceTime 中看到虚拟摄像头

## 非目标

本次 demo 不做以下事情：

- 不修改 Windows/Linux 平台逻辑
- 不实现 PySide6 帧推送
- 不引入共享内存或 XPC 新数据面
- 不覆盖最终生产级安装、pkg、公证分发
- 不替代现有主 host 或正式 Python SDK 接口

## 设计原则

- 独立 target，避免和正式 host 的安装/调试语义混在一起
- 复用现有 Objective-C++ Camera Extension 骨架
- 先跑通最小系统识别链路，再逐步接入更复杂帧源
- 保持 TDD 节奏：测试先行，最小实现，逐步扩展

## 方案选择

### 备选方案 A：在现有主 host 上增加 demo 模式

优点：

- 改动目标数少
- 复用现有启动入口

缺点：

- 正式路径和 demo 路径耦合
- 调试日志、签名和启动逻辑更难隔离
- 不利于后续对照苹果官方最小示例排查问题

### 备选方案 B：独立 demo 目录和独立工程

优点：

- 隔离性最好
- 最像单独 sample

缺点：

- 会复制现有构建、签名和 target 设置
- 后续维护成本更高

### 推荐方案 C：在现有 Xcode 工程内新增独立 demo target

优点：

- 和正式 host 隔离，但仍复用现有工程、签名和 extension 产物
- 方便持续验证 Camera Extension 主链路
- 便于后续把 demo 作为排障工具长期保留

结论：

采用方案 C。

## 目标结构

计划新增或扩展以下部分：

- `virtualcam/macos/demo_host/`
  - `main.mm`
  - `AKVCDemoFrameGenerator.h`
  - `AKVCDemoFrameGenerator.mm`
  - `Info.plist`
  - `DemoHost.entitlements`
- `virtualcam/macos/project.yml`
  - 新增 `akvc-camera-demo-host` target
- `tests/unit/`
  - 新增 demo target 和 demo 帧生成器相关契约测试
- `docs/macos/`
  - 增补 demo 构建和运行说明

## 组件设计

### 1. Demo Host Target

职责：

- 独立启动
- 调用现有 system extension 激活桥接能力
- 提供 demo 专用运行模式标志

约束：

- 不承载正式 Python 集成逻辑
- 不承载未来生产数据面

### 2. Demo Frame Generator

职责：

- 以固定帧率生成测试画面
- 画面内容稳定、易辨识

输出格式：

- 优先复用当前 extension 已支持的像素格式
- 初版以最容易接入现有 `AKVCFrameProvider` 路径的格式为准

画面元素：

- 背景彩条或 HSV 渐变
- 左上角 demo 标识
- 帧号
- 当前时间戳

### 3. Extension Demo Data Hook

职责：

- 在 demo 模式启用时，从 demo 生成器读取帧
- 把帧送入现有 `AKVCStreamSource` / `AKVCFrameProvider` 输出链

约束：

- 不破坏当前正式 extension 代码结构
- demo 模式开关必须显式，不影响默认路径

## 数据流

```text
akvc-camera-demo-host
  -> 激活 Camera Extension
  -> 设置 demo 模式
  -> DemoFrameGenerator 周期生成测试帧
  -> AKVCFrameProvider 提供帧
  -> AKVCStreamSource 输出到 CMIOExtensionStream
  -> 系统注册为摄像头
  -> QuickTime / FaceTime / Zoom 读取画面
```

## 启动与运行模型

初版采用最小运行模型：

- demo host 启动后立即进入测试画面循环
- 默认 1280x720@30fps
- 通过环境变量或命令行参数切换：
  - 设备名
  - 分辨率
  - 帧率

初版不追求复杂配置，只保留最小可验证参数面。

## 测试策略

### 单元测试

- demo target 是否出现在 `project.yml`
- demo 入口是否包含明确的 demo 模式标识
- demo 帧生成器是否暴露稳定的契约面
- demo 文案和运行说明是否写入文档

### 集成测试

- 构建 `akvc-camera-demo-host`
- 运行 demo host 后，状态工具能够查询到 extension 基本状态

### 人工验收

- 构建成功
- host 能启动
- QuickTime 能看到虚拟摄像头
- 画面可见彩条/渐变和时间戳

## 风险

### 风险 1：当前本机签名与 provisioning 条件仍未打通

影响：

- demo target 即使实现完成，也可能仍然因为本机签名环境无法被 LaunchServices 拉起

缓解：

- demo 与正式 host 隔离
- 保留最小日志与诊断输出
- 优先把问题缩小到签名/激活层，而不是数据面

### 风险 2：extension 现有实现默认依赖正式数据面

影响：

- demo 测试帧可能难以无侵入接入

缓解：

- 用显式 demo 模式分支
- 只在 extension 帧源选择层加最小 hook

### 风险 3：多个 host target 增加签名配置复杂度

影响：

- 构建配置和分发脚本需要后续补充

缓解：

- 初版 demo 仅作为开发和人工验收辅助 target
- 不立即进入 pkg 分发范围

## 分阶段实现

### 阶段 1：骨架

- 新增 demo target
- 新增 demo 入口
- 让工程可编译

### 阶段 2：固定帧源

- 新增 demo 帧生成器
- 接入 extension demo 模式

### 阶段 3：验收链路

- 增加运行说明
- 补充最小 smoke / 人工验收步骤

## 验收标准

- 工程新增独立 `akvc-camera-demo-host` target
- demo target 可编译
- demo 模式下 extension 能输出固定测试画面
- 不影响现有 Windows/Linux 平台
- 不改变当前正式 Python 接口面

## 下一步

下一步进入实现计划时，优先做以下工作：

1. 为 demo target 和 demo 帧生成器写失败测试
2. 在 `project.yml` 中加入新 target 骨架
3. 新增 demo host 最小入口
4. 接入 demo 测试帧源
5. 补充运行文档
