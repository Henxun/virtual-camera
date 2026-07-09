# Phase 4 — macOS Camera Extension — Implementation Plan

**项目代号**：AK Virtual Camera  
**阶段**：Phase 4 — macOS Camera Extension  
**当前状态**：已完成一轮 macOS 实机验收；本文记录当前基线、回归重点与后续演进方向。

> 本文档不再把 macOS 路径视为“无 Mac / 仅骨架 / 全 BLOCKED”的前置状态。
> 历史上以 Swift skeleton 为中心的早期方案已经被当前 **Objective-C++ + C/C++ control layer + Camera Extension** 基线取代；如需保留历史背景，应明确视为 superseded，而不是当前实现真值。

---

## 1. 当前基线

### 1.1 已确立的实现方向

| 模块 | 当前基线 |
|---|---|
| `virtualcam/macos/camera_extension/` | Camera Extension 原生实现 |
| `virtualcam/macos/direct_sender/` | 直连 sink-stream / 帧发送路径 |
| `virtualcam/macos/control_bridge/` | 容器/命令/扩展控制桥 |
| `camera-core/src/platform/macos/` | C++ / ObjC++ 控制层会话实现 |
| `camera-core/bindings/python/` | 桌面 app 与兼容集成使用的 thin binding |
| `tools/package_nuitka.py` | macOS `.app` 打包、plist patch、extension embed、codesign 验证入口 |

### 1.2 架构定位

当前分层如下：

1. `virtualcam/` 负责原生虚拟摄像头驱动与平台运行时
2. `camera-core/` 负责跨平台控制 API
3. Python 层仅作为桌面 app 与外部迁移期集成的薄兼容层

因此，后续文档、规则与测试都应围绕这条主线展开，而不是继续把 `akvc.sdk` / CLI 叙事当作架构中心。

---

## 2. 技术决策

### 2.1 扩展类型：CoreMediaIO Camera Extension

macOS 12.3+ 唯一长期可行的正式虚拟摄像头路径。旧 DAL / QuickTime 插件不再作为当前方案。

### 2.2 原生语言栈

当前仓库基线：

- Camera Extension / bridge / sender：**Objective-C++ + C/C++**
- 控制层：**pure C++** 对外 API + 平台实现
- Python：仅 thin binding / desktop compatibility layer

### 2.3 IPC / 数据面

默认仍以共享内存 / 现有 native frame path 为主；`shm_open` 沙盒可用性仍然是设计上的高风险点。若后续切 XPC + IOSurface，属于新的架构演进，而不是恢复旧方案。

### 2.4 容器 app 职责

容器 app 负责：

- `OSSystemExtensionRequest` 激活链路
- 打包 / 签名 / 扩展嵌入相关职责
- 状态与控制面桥接

它不是视频帧热路径定义本身。

---

## 3. 当前已验证能力

### 3.1 已通过的方向

- macOS Camera Extension 可进入验收路径
- 设备可被系统/消费端识别并完成实机验收
- 打包验证采用 Nuitka `.app` bundle 路径
- `tools/package_nuitka.py` 已覆盖：
  - binding 定位/构建
  - `Info.plist` patch
  - `.systemextension` embed
  - codesign 验证

### 3.2 当前文档应如何理解

- 早期 Phase 4 文档中的 `Swift`、`skeleton`、`VERIFY-first` 等描述，只能视为历史阶段痕迹。
- 当前实现与回归应以现有 ObjC++ / C++ 路径、桌面 app 绑定路径和打包脚本为准。

---

## 4. 后续演进项（不是当前基线阻塞项）

| 方向 | 说明 |
|---|---|
| XPC + IOSurface Plan B | 仅当 `shm_open`/当前数据面在目标环境受限时推进 |
| 更强的自动化回归 | 把当前实机验收经验进一步沉淀成脚本/报告模板 |
| 签名/公证生产化 | 从开发验证级 codesign 进一步收敛到正式分发流水线 |
| 兼容层瘦身 | 在不破坏桌面 app / 外部集成前提下，继续降低旧 Python SDK/CLI 的架构中心性 |

---

## 5. 文档与规则协同要求

后续任何改动若涉及：

- macOS 架构分层
- 打包/签名/验收流程
- 共享协议 / control surface

必须同步更新：

- `docs/macos/architecture.md`
- `docs/phase4/verification-plan.md`
- `.claude/rules/macos.md`
- 相关打包/验收脚本说明

否则会再次出现“代码现实”与“工作流真值”分裂的问题。

---

## 6. 回归重点

每次后续 macOS 改动，至少重新确认：

1. Camera Extension 激活链路正常
2. 打包后的 `.app` 仍具备正确的 `Info.plist` / extension embed / codesign 行为
3. 设备在目标消费端可见
4. 推帧路径仍可稳定工作
5. 兼容层不会重新变成主架构叙事

---

## 7. 出口定义

当前 Phase 4 的完成语义，不再是“是否终于拿到 Mac”，而是：

- 回归验证是否保持通过
- 文档/规则/验收脚本是否持续反映当前实现真值
- 新改动是否没有把架构叙事重新拉回过期的 Swift / skeleton / BLOCKED 状态
