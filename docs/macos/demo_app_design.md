# macOS Demo App 设计

日期：2026-07-01

## 目标

在现有 [virtualcam/macos](/Users/admir/workspace/virtual-camera/virtualcam/macos) 工程内新增一个独立的原生 macOS AppKit demo app，用于开发者模式下的虚拟摄像头人工验收。

目标链路：

`AKVC Demo App -> Demo Mode / Camera Extension Activation -> System Camera Device -> QuickTime / FaceTime / Zoom`

这个 app 的定位是“原生验收控制台”，不是正式产品 UI，也不是 PySide6 推帧入口。

## 范围

本次 demo app 仅包含以下能力：

- 新增一个独立原生 `.app` target，例如 `akvc-demo-app`
- 打开后展示 Camera Extension / container app / demo mode / 设备可见状态
- 提供“刷新状态”“启用 Demo 并激活”“停用 Demo”“复制验收步骤”四个核心操作
- 复用现有 Objective-C++ native bridge 能力，不重写 system extension 激活协议
- 提供中文构建与人工验收文档

## 非目标

本次 demo app 不做以下事情：

- 不实现 PySide6 推帧
- 不实现本地视频预览窗口
- 不取代正式跨平台 GUI App 作为最终 container app
- 不新增新的 IPC、安装协议或控制协议
- 不影响 Windows/Linux 平台实现
- 不覆盖独立分发模式

## 设计原则

- 独立 target，但复用现有 native container/demo bridge 能力
- 第一版优先服务“开发者模式”而不是“产品化交付”
- 窗口结构简单，信息可见，操作可重复
- 所有错误必须直接呈现 native 错误文本
- 严格 TDD：先契约测试，再最小实现，再补文档

## 方案对比

### 方案 A：独立 AppKit 控制台 app

特点：

- 新增一个真正独立的图形 `.app`
- UI 负责状态展示和操作入口
- 底层直接复用现有 `AKVCCommandSupport` / `AKVCSystemExtensionSupport`

优点：

- 最贴合当前“开发者模式 + 人工验收”的目标
- 用户体验完整，不是二次包一层脚本
- 结构清晰，后续可持续扩展

缺点：

- 比纯命令行 demo host 多一层 UI 代码

### 方案 B：图形 launcher 外壳

特点：

- 新 app 负责容器内的激活与状态控制，不再依赖独立 demo host target
- 自身不直接调用底层支持代码

优点：

- 初始改动最小

缺点：

- 体验割裂
- 更像“按钮壳子”而不是独立 app
- 错误定位会在 UI 与外部进程之间分叉

### 方案 C：重型仪表盘 app

特点：

- 首版就带日志面板、设备枚举、自动轮询、更多诊断面

优点：

- 调试信息最全

缺点：

- 第一版范围过大
- 容易偏离“先可验收”的主目标

## 推荐方案

采用方案 A。

原因：

- 它能在“独立原生 app”与“复用现有稳定 native bridge”之间取得最好平衡
- 不需要再发明第三套激活逻辑
- 能快速形成一个可构建、可点击、可人工验收的原生入口

## 工程结构

在现有 [virtualcam/macos/project.yml](/Users/admir/workspace/virtual-camera/virtualcam/macos/project.yml) 中新增一个 target：

- `akvc-demo-app`

建议目录结构：

- `virtualcam/macos/demo_app/main.mm`
- `virtualcam/macos/demo_app/AppDelegate.h`
- `virtualcam/macos/demo_app/AppDelegate.mm`
- `virtualcam/macos/demo_app/MainWindowController.h`
- `virtualcam/macos/demo_app/MainWindowController.mm`
- `virtualcam/macos/demo_app/DemoControlService.h`
- `virtualcam/macos/demo_app/DemoControlService.mm`
- `virtualcam/macos/demo_app/Info.plist`
- `virtualcam/macos/demo_app/DemoApp.entitlements`
- `docs/macos/demo_app.md`

## 组件职责

### 1. `AppDelegate`

职责：

- 启动 AppKit 应用
- 创建主窗口控制器
- 处理应用生命周期的最小胶水逻辑

约束：

- 不直接承载业务逻辑

### 2. `MainWindowController`

职责：

- 构建和管理单窗口 UI
- 响应按钮点击
- 把 `DemoControlService` 的状态与错误映射到界面

UI 区块：

1. 标题区
2. 状态区
3. 操作按钮区
4. 验收提示区
5. 日志区

约束：

- 第一版只做单窗口
- 不做多页，不做 sidebar

### 3. `DemoControlService`

职责：

- 提供统一的原生控制接口：
  - `refreshStatus`
  - `enableDemoAndActivate`
  - `disableDemo`
  - `manualAcceptanceInstructions`
- 对外输出结构化状态摘要

约束：

- 不重新实现 system extension 协议
- 只封装现有 support 代码

### 4. 现有 native support 复用层

必须直接复用以下现有能力：

- [virtualcam/macos/control_bridge/AKVCCommandSupport.h](/Users/admir/workspace/virtual-camera/virtualcam/macos/control_bridge/AKVCCommandSupport.h)
- [virtualcam/macos/control_bridge/AKVCCommandSupport.mm](/Users/admir/workspace/virtual-camera/virtualcam/macos/control_bridge/AKVCCommandSupport.mm)
- [virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.h](/Users/admir/workspace/virtual-camera/virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.h)
- [virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm](/Users/admir/workspace/virtual-camera/virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm)
- `AKVCSetDemoModeEnabled(...)`
- `AKVCSubmitSystemExtensionRequest(...)`

禁止：

- 再新增一套独立激活协议
- 把核心逻辑退化成简单 shell 外壳去拉起外部进程

## 窗口交互流

### 初始状态

窗口启动后显示：

- app 名称：`AKVC Demo App`
- 一句总体状态摘要
- 当前 host / extension / demo mode / 设备可见摘要

### 按钮行为

#### `刷新状态`

行为：

- 重新读取当前状态摘要
- 更新状态区与日志区

#### `启用 Demo 并激活`

行为：

1. 调用 `AKVCSetDemoModeEnabled(YES, ...)`
2. 调用 `AKVCSubmitSystemExtensionRequest(YES, ...)`
3. 刷新状态
4. 记录结果到日志区

#### `停用 Demo`

行为：

1. 调用 `AKVCSetDemoModeEnabled(NO, ...)`
2. 刷新状态
3. 记录结果到日志区

说明：

- 第一版不自动执行卸载
- 它的目标只是退出 demo 分支，而不是重置整机安装状态

#### `复制验收步骤`

行为：

- 将 QuickTime / FaceTime / Zoom 最小人工验收步骤复制到剪贴板
- 并在日志区追加一条成功提示

## 状态模型

第一版状态区展示这些字段：

- Host 路径
- Camera Extension bundle identifier
- Demo mode 当前状态
- 目标设备名
- 已检测系统摄像头数量
- 当前最后错误

状态摘要文案示例：

- `未激活`
- `已提交激活请求，等待系统批准`
- `已检测到虚拟摄像头，可前往 QuickTime 验收`

## 数据流

```text
MainWindowController
  -> DemoControlService
  -> AKVCCommandSupport / AKVCSystemExtensionSupport
  -> Demo mode file + SystemExtension request
  -> Camera Extension
  -> System camera device visibility
  -> MainWindowController refreshes status
```

## 测试策略

### 1. 工程契约测试

在 [tests/unit/test_macos_native_skeleton.py](/Users/admir/workspace/virtual-camera/tests/unit/test_macos_native_skeleton.py) 中先锁定：

- `akvc-demo-app` target 存在
- `demo_app` 目录和文件存在
- target 依赖正确的 frameworks 与 support 源文件

### 2. 源码契约测试

锁定：

- `AppDelegate`
- `MainWindowController`
- `DemoControlService`
- 四个核心动作入口
- 复用了 `AKVCSetDemoModeEnabled(...)`
- 复用了 `AKVCSubmitSystemExtensionRequest(...)`

### 3. 文档契约测试

锁定：

- 存在 `docs/macos/demo_app.md`
- 文档包含构建方法、运行方式和人工验收步骤

### 4. 第一版验收标准

- 能构建出独立 `akvc-demo-app.app`
- app 能打开窗口
- 能点击“启用 Demo 并激活”
- 状态文本和错误文本会更新
- 能按提示前往 QuickTime 做人工验收

## 风险

### 风险 1：本机 system extension 条件未完全打通

影响：

- app 即使实现完成，也可能仍然因为签名、公证、授权或系统批准问题无法顺利完成激活

缓解：

- 明确展示 native 错误文本
- 保持与现有控制桥接逻辑同一套底层实现，方便对照排查

### 风险 2：首版做太重

影响：

- UI、轮询、诊断信息膨胀，拖慢“先交付可验收 app”的进度

缓解：

- 第一版只做单窗口 + 四个按钮 + 简明日志

### 风险 3：逻辑重复

影响：

- 若在 demo app 内再次发明新的控制流程，后续维护会出现三套分叉逻辑

缓解：

- 强制复用现有 host support 能力

## 分阶段实现

### 阶段 1：target 与文件骨架

- 新增 `akvc-demo-app` target
- 新增 `demo_app/` 目录和最小 AppKit 入口
- 让工程契约测试通过

### 阶段 2：单窗口 UI

- 建立主窗口
- 加入状态区、按钮区、验收提示区、日志区
- 让源码契约测试通过

### 阶段 3：native bridge 接线

- 通过 `DemoControlService` 封装现有 support 调用
- 打通“刷新状态 / 启用 Demo 并激活 / 停用 Demo / 复制验收步骤”

### 阶段 4：文档与人工验收

- 新增 `docs/macos/demo_app.md`
- 写明构建、运行、人工验收流程

## 验收结论

本次设计的最终目标不是“做一个完整产品 UI”，而是：

- 在当前工程内新增一个真正独立的原生 macOS demo app
- 让开发者可以通过图形界面完成虚拟摄像头 demo 激活与人工验收
- 同时保持底层逻辑与现有 native bridge 完全对齐
