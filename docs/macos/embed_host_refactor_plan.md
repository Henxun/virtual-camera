# macOS 去独立 Host 化重构方案

## 目标

把当前 macOS 虚拟摄像头方案从：

`独立 akvc-host.app -> Camera Extension -> System Camera Device`

重构为：

`你的跨平台 PySide6 主程序.app -> Camera Extension -> System Camera Device`

也就是：

- 不再要求最终产品额外安装一个独立 `akvc-host.app`
- 由你的主程序 `.app` 自身充当 Camera Extension 的 container app
- Python 推帧热路径保持不变，仍然走：
  - `PySide6/Python -> VirtualCamera -> direct sender / shared memory -> Camera Extension`
- Windows / Linux 对外接口不受影响

## 结论

可以去掉“独立 host 产品形态”，但不能去掉“container app”这一角色。

在 macOS Camera Extension 模型下：

- `Camera Extension` 必须内嵌在一个签名正确的 `.app` 中
- 激活 / 升级 / 卸载必须由这个 `.app` 发起
- 运行时视频帧热路径不需要单独 host 进程常驻

因此，正确目标不是“没有 host 角色”，而是“host 角色并入你的 PySide6 主程序”。

## 当前代码现状

本仓库当前把 `akvc-host.app` 当成默认容器，耦合点主要有四类。

### 1. 运行时发现逻辑写死 `akvc-host.app`

关键文件：

- [camera-core/src/akvc/runtime.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/runtime.py)
- [camera-core/src/akvc/platforms/macos/installer.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/platforms/macos/installer.py)

当前行为：

- `find_macos_host_app_bundle()` 默认查找：
  - `build/macos/Build/Products/Release/akvc-host.app`
  - `/Applications/akvc-host.app`
- `find_macos_host_executable()` 默认查找：
  - `.../akvc-host.app/Contents/MacOS/akvc-host`

这意味着 SDK 默认假设最终容器永远叫 `akvc-host.app`。

### 2. 安装 / 激活控制面默认通过独立 host 发起

关键文件：

- [camera-core/src/akvc/platforms/macos/installer.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/platforms/macos/installer.py)
- [virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm](/Users/admir/workspace/virtual-camera/virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm)

当前行为：

- `MacInstallerService` 内部维护：
  - `host_bundle`
  - `host_executable`
- 激活命令默认构造成：
  - `open -n -a <host bundle> --args --activate`
  - 或 `<host executable> --activate`
- pkg 安装后还会检查 `/Applications/akvc-host.app` 是否出现

这意味着控制面把“独立 host app 存在”当成成功标准。

### 3. 工具链 / 文档 / 验收工件默认围绕 `akvc-host.app`

关键位置：

- `tools/macos_*`
- `tests/unit/test_macos_*`
- `docs/*`

当前行为：

- `host_bundle` / `host_executable` 参数语义都默认指向 `akvc-host`
- 验收 JSON / summary / troubleshooting 文档大量写死：
  - `/Applications/akvc-host.app`

### 4. SDK 语义还是“host override”，不是“container app identity”

关键文件：

- [camera-core/src/akvc/sdk/virtual_camera.py](/Users/admir/workspace/virtual-camera/camera-core/src/akvc/sdk/virtual_camera.py)

当前公开参数：

- `host_bundle`
- `host_executable`

这更像是“临时覆盖独立 host 路径”，而不是“告诉 SDK 当前主程序就是容器 app”。

## 目标形态

### 运行时拓扑

最终产品形态建议统一为：

`YourApp.app`

内部包含：

- `Contents/MacOS/<你的主程序启动器>`
- `Contents/Library/SystemExtensions/<camera extension>.systemextension`
- 可选：
  - `Contents/MacOS/akvc-macos-status`
  - `Contents/MacOS/akvc-macos-install`
  - `Contents/MacOS/akvc-macos-uninstall`
  - `Contents/MacOS/akvc-macos-sync-ipc`

其中：

- 主程序 `.app` 是唯一面向用户的 macOS 产品
- `Camera Extension` 内嵌在主程序 bundle 中
- 诊断工具可以作为同一 bundle 内的附属二进制保留
- 不再单独分发 `akvc-host.app`

### Python 侧目标语义

Python 层应该从“host override”提升为“container app descriptor”。

建议新语义：

- `app_bundle`
- `app_executable`
- `extension_bundle`
- `container_app_mode`

兼容策略：

- 第一阶段保留 `host_bundle` / `host_executable`
- 但内部统一映射到新的“container app”模型
- 文档标记旧参数为兼容别名

## 推荐重构方向

## A. 先抽象“Container App”，再去掉 `akvc-host` 假设

新增一个明确的运行时描述模型，例如：

```python
@dataclass
class MacContainerAppDescriptor:
    app_bundle_path: Path | None
    app_executable_path: Path | None
    extension_bundle_path: Path | None
    installed_in_applications: bool
    source: str
```

它的职责：

- 表示“当前哪个 `.app` 是 Camera Extension 的 container”
- 不关心它叫不叫 `akvc-host`
- 允许来自：
  - 显式传参
  - 环境变量
  - 当前主程序 bundle 推断
  - 构建产物推断

### 推断优先级建议

1. 显式传入的 app bundle / executable
2. 当前运行中的主程序 bundle
3. 环境变量
4. 构建树中的 demo / host bundle
5. 旧兼容路径 `akvc-host.app`

这样做的核心收益是：

- 对你的跨平台主程序友好
- 对现有 demo / 旧工具链兼容

## B. 让 installer/status 以“container app”工作，而不是以 `akvc-host` 工作

`MacInstallerService` 的构造语义建议改成：

```python
MacInstallerService(
    app_bundle=None,
    app_executable=None,
    ...
)
```

内部行为改造为：

- `_refresh_host_runtime()` -> `_refresh_container_runtime()`
- `_host_control_command()` -> `_container_control_command()`
- `_has_installed_host_runtime()` -> `_has_installed_container_app()`

成功标准从：

- “`/Applications/akvc-host.app` 出现”

改为：

- “目标 container app 已存在，且其 `Contents/Library/SystemExtensions/...` 内能找到目标扩展”

## C. 把“激活入口”做成主程序内命令通道

你的 PySide6 主程序最终需要支持内部激活命令，例如：

- `--akvc-activate-extension`
- `--akvc-deactivate-extension`
- `--akvc-status-json`

实现方式有两种：

### 方案 1：主程序可执行文件直接支持这些参数

优点：

- 产品形态最干净
- 没有额外可见 host app

缺点：

- 你的主程序启动器必须很早进入 native 参数分发
- 打包器若把 Python 放在主入口里，命令模式要设计清楚

### 方案 2：主程序 bundle 内保留一个隐藏 helper 可执行文件

例如：

- `YourApp.app/Contents/MacOS/akvc-container-helper`

优点：

- 不需要单独分发独立 `.app`
- 容易复用现有 `akvc-host` 命令逻辑

缺点：

- 形式上仍有 helper binary，但它已经不是独立 host app

对你的需求，我更推荐 **方案 2 作为过渡阶段**：

- 用户视角只有一个主程序 `.app`
- 工程上最容易把现有 `akvc-host` 逻辑迁进去
- 后面再视情况合并到主程序入口

## D. 把 Camera Extension target 从“绑定 akvc-host”改成“可嵌入任意 container app”

这一步不是改扩展逻辑，而是改产物装配关系：

- 当前 `akvc-host.app` 内嵌扩展
- 后面应支持：
  - `YourPySide6App.app` 内嵌扩展
  - `akvc-demo-app.app` 作为开发态 GUI 容器

也就是说：

- `Camera Extension` target 保留
- `akvc-host` 由“正式产品容器”降级为“开发辅助 target / 兼容 target”

## 分阶段实施建议

## Phase 1：抽象层改名，不改产品行为

目标：

- 代码内部从 `host_*` 语义迁移到 `container app` 语义
- 对外仍保持现状可运行

任务：

1. 引入 `MacContainerAppDescriptor`
2. 在 `runtime.py` 中新增：
   - `find_macos_container_app_bundle()`
   - `find_macos_container_app_executable()`
3. `installer.py` 内部从 host 术语改成 container 术语
4. 保留 `host_bundle` / `host_executable` 参数作为兼容入口
5. 新增测试，验证旧参数仍可工作

TDD：

- 先补 contract tests
- 再改 runtime / installer
- 最后修文档

## Phase 2：支持“当前主程序就是 container app”

目标：

- SDK 不再默认依赖 `akvc-host.app`
- 当主程序 bundle 明确传入时，安装 / 激活 / 状态检查都走主程序

任务：

1. `VirtualCamera` 兼容层构造参数增加：
   - `app_bundle`
   - `app_executable`
2. 兼容映射：
   - `host_bundle -> app_bundle`
   - `host_executable -> app_executable`
3. installer/status/devices/sync-ipc 命令通过新的 container descriptor 注入环境变量
4. 所有 `/Applications/akvc-host.app` 成功判断改成“目标 app bundle”

TDD：

- 先补 `test_macos_container_app_runtime.py`
- 再补 installer result 测试
- 再补 CLI / demo 工具兼容测试

## Phase 3：主程序 bundle 内嵌 helper / 原生桥

目标：

- 你的主程序 `.app` 自己可发起扩展激活
- 不再需要独立 `akvc-host.app`

任务：

1. 在 macOS 原生工程中新增“container helper” target
2. helper 使用现有：
   - `AKVCCommandSupport`
   - `AKVCSystemExtensionSupport`
3. 主程序 bundle 中包含：
   - helper
   - extension
   - status/install/uninstall/sync-ipc 工具
4. Python 层默认把主程序 bundle 作为 container app

## Phase 4：产品分发切换

目标：

- pkg/dmg/zip 只分发主程序 `.app`
- `akvc-host.app` 仅保留开发态

任务：

1. `build_pkg.sh` 支持目标 app bundle 参数化
2. pkg 成功标准改为检查目标主程序 app
3. 文档 / 验收 / troubleshooting 全量替换
4. CI 产物切到：
   - `YourApp.pkg`
   - 内嵌 camera extension

## 对 Windows / Linux 的影响控制

这次重构应严格限制在 macOS：

- `VirtualCamera` 对外方法名不变
- Windows helper / MF virtual camera 逻辑不动
- Linux 分支不动
- 新参数只在 macOS 消费

建议原则：

- 不改现有跨平台默认行为
- 新增参数时必须是可选参数
- 平台判断只在 macOS backend 内展开

## 推荐接口演进

最终希望保留的 Python 对外接口：

```python
vc = VirtualCamera(
    width=1280,
    height=720,
    fps=30,
    app_bundle="/Applications/YourApp.app",
)

vc.install_extension()
vc.start()
vc.send(frame)
vc.stop()
```

兼容阶段：

```python
vc = VirtualCamera(
    host_bundle="...",
)
```

内部自动映射到：

- `app_bundle`

## 风险

### 1. 当前主程序是否一定是标准 `.app`

如果你的 PySide6 项目在开发态只是：

- `python main.py`

那么它本身不能充当正式 container app。

需要区分两种运行模式：

- 开发态：
  - 继续允许 demo host / build tree 容器存在
- 发布态：
  - 必须由你的正式 `.app` 充当 container

### 2. 打包方式会影响主入口设计

如果你使用：

- PyInstaller
- Briefcase
- 自定义 launcher

则“主程序如何接收 `--akvc-activate-extension`”要和打包方式一起设计。

### 3. 现有测试大量写死 `akvc-host`

这是好事，因为它会把所有隐性耦合点都暴露出来。

但实施时要分两步：

1. 先把测试改成支持“参数化 container app”
2. 再逐个去掉默认 `akvc-host` 假设

## 下一步建议

下一轮直接进入 **Phase 1**，先做纯重构准备，不碰你的 Xcode signing 配置：

1. 新增 container app descriptor 与 runtime 发现函数
2. 把 `installer.py` 内部 host 术语收敛成 container 术语
3. 保留旧参数兼容
4. 补齐对应单测

这样做完之后，仓库层面就具备“让主程序接管 container app 角色”的基础了。
