# macOS Demo App

本文档说明如何使用独立原生 `akvc-demo-app` 验证当前 macOS 虚拟摄像头 demo 链路。

这是一个面向开发者模式的图形化验收控制台，不是独立分发版，也不替代正式 container app。

## 适用范围

- 目标 target：`akvc-demo-app`
- 目标系统：macOS 13+
- 目标用途：用图形界面完成 demo mode 激活和 QuickTime / FaceTime / Zoom 人工验收

## 与正式 container app 的关系

- `akvc-demo-app` 负责图形化验收入口
- 正式分发时应由你的主应用自身承担 container app 角色
- 两者复用同一套 native bridge，而不是各自维护独立激活逻辑

## 构建方式

```bash
xcodebuild \
  -project virtualcam/macos/akvc-macos.xcodeproj \
  -scheme akvc-demo-app \
  -configuration Release \
  build
```

## 运行方式

```bash
build/macos/Build/Products/Release/akvc-demo-app.app/Contents/MacOS/akvc-demo-app
```

## 主要操作

app 首版提供四个核心动作：

- `刷新状态`
- `启用 Demo 并激活`
- `停用 Demo`
- `复制验收步骤`

其中“启用 Demo 并激活”会复用现有 native bridge：

- `AKVCSetDemoModeEnabled(...)`
- `AKVCSubmitSystemExtensionRequest(...)`

## 状态阅读方式

状态区除了原始字段，还会给出两条更适合人工验收的导向信息：

- `Readiness stage`：表示当前卡在哪个阶段，例如等待批准、等待设备枚举、IPC 未就绪
- `Next action`：表示当前最建议的下一步动作

常见判断方式：

- 如果 `approval_required=YES`，优先去系统设置批准扩展
- 如果 `ipc_ready=NO`，优先补跑 `sync-ipc` 或 direct push demo，再看应用枚举
- 如果 `Visible devices > 0`，就可以直接进入 QuickTime / FaceTime / Zoom 验收

## 人工验收

1. 打开 `akvc-demo-app`
2. 点击 `启用 Demo 并激活`
3. 观察状态摘要、`Readiness stage`、`Next action` 与错误文本是否更新
4. 打开 QuickTime，选择“新建影片录制”
5. 在摄像头列表中查找目标设备名
6. 确认看到 demo 画面后，再去 FaceTime 和 Zoom 验证枚举

## 排查建议

- 如果激活失败，先看 app 内最后错误文本
- 如果 QuickTime 看不到设备，先确认状态区里的 `State` 和 `Visible devices`
- 如果仍不稳定，再结合 [manual_acceptance.md](/Users/admir/workspace/virtual-camera/docs/macos/manual_acceptance.md) 与状态/签名排查文档一起定位
