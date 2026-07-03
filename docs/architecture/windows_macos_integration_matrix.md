# Windows / macOS 接入对照表

## 文档目标

本文档用于给跨平台 PySide6 主程序做接入设计时，快速对照 Windows 与 macOS 的职责划分、接口语义和注意事项。

## 总览

| 维度 | Windows | macOS | 业务层是否需要关心 |
|---|---|---|---|
| 系统能力模型 | MF Virtual Camera | CoreMediaIO Camera Extension | 否 |
| 是否需要 container app | 否 | 是 | 否 |
| 是否可能存在 helper | 是 | 可选，仅开发辅助 | 否 |
| 推帧热路径 | Python -> sink/helper -> MF | Python -> direct sender/shared memory -> Camera Extension | 否 |
| 首次安装是否要用户批准 | 常见情况下不需要系统扩展开关 | 需要批准 Camera Extension | 只关心结果，不关心机制 |
| 对外统一入口 | `VirtualCamera` | `VirtualCamera` | 是 |

## 生命周期对照

| 生命周期阶段 | Windows | macOS | 统一建议 |
|---|---|---|---|
| 构造 | 创建 facade，准备 helper/runtime | 创建 facade，准备 installer/runtime descriptor | `vc = VirtualCamera(...)` |
| 安装检查 | helper / MF 注册可用性检查 | extension/container/status 检查 | `vc.install_extension_result()` |
| 启动 | 启动 helper，确保 MF camera ready | 确保 extension enabled 且设备已枚举 | `vc.start(name=...)` |
| 推帧 | `push_frame/send` | `push_frame/send` | 同一套调用 |
| 停止 | 停 worker/sink/helper session | 停 producer/sink | `vc.stop()` |
| 释放 | 清理资源 | 清理资源 | `vc.close()/shutdown()` |

## 业务层推荐只使用的接口

| 接口 | 用途 | Windows | macOS |
|---|---|---|---|
| `start(name=...)` | 启动虚拟摄像头推流会话 | 支持 | 支持 |
| `send(frame)` | 通用发送入口 | 支持 | 支持 |
| `push_frame(frame)` | numpy / 标准帧发送 | 支持 | 支持 |
| `send_image(image)` | QImage 输入 | 支持 | 支持 |
| `send_pixmap(pixmap)` | QPixmap 输入 | 支持 | 支持 |
| `send_widget(widget)` | QWidget 抓帧 | 支持 | 支持 |
| `send_screen(screen)` | 屏幕抓帧 | 支持 | 支持 |
| `stop()` | 停止推流 | 支持 | 支持 |
| `install_extension_result()` | 查询安装/激活状态 | 可返回平台特定结果 | 可返回平台特定结果 |
| `enumerate_devices()` | 查询设备枚举 | 支持 | 支持 |

## 不建议让业务层直接依赖的内容

| 项目 | 原因 |
|---|---|
| `akvc-host.app` 路径 | macOS 产品形态会变 |
| helper 可执行文件路径 | Windows/macOS 形态不同 |
| system extension 激活命令 | 属于平台控制面细节 |
| pkg / notarize / codesign 判断逻辑 | 属于分发层 |

## 平台后端真正应该承担的事情

### Windows 后端

- helper 生命周期管理
- MF 注册
- sink 发布
- 平台专属错误解释

### macOS 后端

- container app 发现
- Camera Extension 激活/状态/卸载
- direct sender / shared memory 选择
- system camera 可见性判断
- 平台专属错误解释

## 参数语义建议

### 业务层长期推荐参数

| 参数 | 作用 | 备注 |
|---|---|---|
| `width` | 输出宽度 | 跨平台统一 |
| `height` | 输出高度 | 跨平台统一 |
| `fps` | 输出帧率 | 跨平台统一 |
| `camera_name` | 设备显示名 | 跨平台统一 |

### 平台后端专属参数

| 参数 | 平台 | 说明 |
|---|---|---|
| `helper_exe` | Windows | helper/runtime 覆盖 |
| `app_bundle` | macOS | 主程序 container app |
| `app_executable` | macOS | container 内可执行入口 |
| `direct_sender_library` | macOS | direct sender dylib 覆盖 |

### 兼容参数

| 参数 | 现状 | 未来建议 |
|---|---|---|
| `host_bundle` | macOS 历史参数 | 兼容保留，内部映射到 `app_bundle` |
| `host_executable` | macOS 历史参数 | 兼容保留，内部映射到 `app_executable` |

## 错误模型建议

统一建议让业务层只处理这些高层状态：

| 状态 | 说明 |
|---|---|
| `not_installed` | 平台能力尚未安装完成 |
| `approval_required` | 需要用户授权或批准 |
| `device_not_visible` | 系统里还没出现设备 |
| `runtime_not_ready` | 后端未就绪 |
| `streaming` | 已可正常推流 |

平台后端再把更细的错误映射到这些状态：

- Windows：
  - helper 启动失败
  - MF 注册失败
- macOS：
  - extension 未启用
  - bundle 签名问题
  - container app 不在预期位置

## 主程序打包建议

| 平台 | 推荐产品形态 |
|---|---|
| Windows | 主程序 + helper/runtime |
| macOS | 主程序 `.app` + 内嵌 Camera Extension |

## 你后面真正需要写的业务代码应该像这样

```python
from akvc.sdk import VirtualCamera

vc = VirtualCamera(width=1280, height=720, fps=30, camera_name="AK Virtual Camera")

status = vc.install_extension_result()
if status is not None and not status.success:
    print(status.phase)

vc.start()
vc.send(frame)
vc.stop()
```

这段代码应当尽量不区分：

- `if sys.platform == "win32": ...`
- `if sys.platform == "darwin": ...`

平台判断应该尽可能收敛在 SDK 后端内部。

## 最终建议

对于你的跨平台 PySide6 项目，推荐遵守这三条原则：

1. 业务层只依赖统一的 `VirtualCamera` facade。
2. 平台差异只在 backend 内吸收。
3. macOS 不再把独立 `akvc-host.app` 当作产品前提，而是让主程序自己成为 container app；legacy host 只保留兼容与开发态用途。
