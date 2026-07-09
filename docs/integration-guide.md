# 集成 AK Virtual Camera

## 当前真值

本仓库当前的标准分层是：

- `virtualcam/`：原生虚拟摄像头驱动层
- `camera-core/`：pure C++ / ObjC++ 控制层
- Python / PySide6：桌面 app 与外部集成的薄兼容层

因此，架构决策应优先以原生 `virtualcam/` + `camera-core/` 为准。
旧 `akvc.sdk` 与 `akvc` CLI 仍可作为兼容/集成入口继续使用，但不再是本项目的主架构定义。

macOS 架构真值见：
- [docs/macos/architecture.md](docs/macos/architecture.md)
- [docs/phase4/implementation-plan.md](docs/phase4/implementation-plan.md)

---

## 1. 推荐的集成理解方式

### 1.1 如果你在做原生/跨平台宿主接入

优先围绕 `camera-core/` 的 `akvc::VirtualCamera` 控制层设计：

- `start()` / `stop()`
- `push_frame(...)`
- 平台侧 runtime / session 管理

这条路径代表当前仓库的主实现方向。

### 1.2 如果你在做 Python / PySide6 集成

可以继续使用现有 Python 兼容层，但要把它理解为：

- 桌面 app 使用的 bridge
- 诊断 / demo / 迁移期外部集成入口
- 对原生控制层的薄封装

而不是独立于原生层的“另一套主 SDK”。

---

## 2. Python 兼容层用法

如果你的宿主当前仍是 Python / PySide6，可以继续复用现有兼容接口。
这对桌面 app、诊断脚本和迁移期项目仍然有用。

典型能力包括：

- 启动/停止虚拟摄像头
- 推送 `numpy.ndarray` 帧
- 作为 PySide6 桌面应用的桥接层

在这类集成里，推荐同时参考当前桌面 app 实现：
- [apps/desktop/README.md](apps/desktop/README.md)
- [apps/desktop/akvc_app/services/runtime_host.py](apps/desktop/akvc_app/services/runtime_host.py)
- [apps/desktop/akvc_app/services/facade.py](apps/desktop/akvc_app/services/facade.py)

---

## 3. macOS 集成说明

### 3.1 当前推荐认知

macOS 当前采用：

- CoreMediaIO Camera Extension
- Objective-C++ + C/C++ 原生实现
- 容器 app 负责扩展激活/打包/签名相关职责
- 帧热路径由 producer 直达原生控制/发送路径，不把 container app 当作热路径组件

这与早期 Phase 4 文档里的 Swift 骨架方向不同；如遇冲突，以当前架构文档和代码为准。

### 3.2 打包与验收

当前仓库内用于 macOS 验证的打包脚本是：
- [tools/package_nuitka.py](tools/package_nuitka.py)

它负责：

- 构建/定位 `akvc_camera` Python binding
- 生成 Nuitka `.app`
- patch `Info.plist`
- embed `.systemextension`
- codesign bundle

配套验证入口见：
- [docs/phase4/run-debug-guide.md](docs/phase4/run-debug-guide.md)
- [docs/phase4/verification-plan.md](docs/phase4/verification-plan.md)

---

## 4. Windows 集成说明

Windows 仍保留兼容层和诊断入口，用于：

- DShow 注册
- MF 可见性检查
- DirectShow 枚举与诊断

常用入口：

```bash
python tools/make.py register
uv run python tools/diag/dshow_enum.py
```

如果你使用 CLI 或旧 Python 接口，请把它们视为对当前 runtime/control-layer 的封装，而不是独立架构层。

---

## 5. 对文档冲突的处理原则

如果你在仓库里看到以下旧表述，请优先按当前代码与新文档理解：

- `akvc.sdk.VirtualCamera` 被写成唯一主入口
- `akvc` CLI 被写成唯一控制入口
- macOS 被写成 Swift 主实现
- macOS 被写成“无 Mac / 全 BLOCKED / 仅骨架”

这些内容属于历史阶段残留；当前应以：

- `virtualcam/` 原生驱动层
- `camera-core/` pure C++ / ObjC++ 控制层
- Python/CLI 兼容层

为新的统一真值。
