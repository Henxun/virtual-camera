---
name: integrate-virtual-camera
description: 将 AK Virtual Camera 集成到外部 PySide6/Python 项目。优先按当前 `virtualcam/` + `camera-core/` 原生驱动/控制层架构理解；Python 入口仅作为桌面 app 与迁移期集成的兼容层。
---

# 集成 AK Virtual Camera 到外部项目

本 skill 面向**消费端**：你已有一个 PySide6（或任意 Python）应用能产出视频帧，想把帧推送到系统级虚拟摄像头，让 Chrome / OBS / Zoom 等应用看到。

## 推荐路径

先明确当前真值：

- `virtualcam/` 是原生虚拟摄像头驱动层
- `camera-core/` 是 pure C++ / ObjC++ 控制层
- Python / PySide6 入口是桌面 app 与迁移期外部项目的兼容层

因此，这个 skill 的默认目标不是继续把旧 `akvc.sdk` 写成主架构，而是：

1. 先按当前原生驱动/控制层架构解释系统如何工作
2. 如果外部项目当前确实是 Python / PySide6，再提供兼容层接入建议
3. 只有在调用方明确依赖旧 Python 表面时，才继续给出对应兼容入口

## 一次性注册与验证

如果外部项目当前仍通过兼容层接入 Windows 路径，且你要让 OBS / Zoom / GraphStudioNext 通过 DirectShow 发现设备，仍需先在**管理员 shell**中完成注册。

优先使用当前仓库维护的入口：

```bash
python tools/make.py register
uv run python tools/diag/dshow_enum.py
```

如果调用方仍保留旧 CLI 包装，可将其视为兼容命令，而不是架构真值。

## 最小 PySide6 示例

```python
import sys

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from akvc.sdk import VirtualCamera

app = QApplication(sys.argv)
vc = VirtualCamera()
vc.start(name="AK Virtual Camera")

timer = QTimer()
seq = [0]

def on_tick() -> None:
    bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
    bgr[:, :] = (seq[0] % 256, 100, 50)
    seq[0] += 4
    vc.push_frame(bgr)

timer.timeout.connect(on_tick)
timer.start(33)

try:
    app.exec()
finally:
    vc.shutdown()
```

## `VirtualCamera` 已经帮你做了什么

`akvc.sdk.VirtualCamera` 默认会完成这些工作：

- 启动 helper 并检查 `ping()`
- 在当前 helper 生命周期内只注册一次 MF 虚拟摄像头
- 打开系统 sink
- 对输入 BGR 帧自动执行默认 pipeline：
  - `ResizeStage(target_w=1280, target_h=720)`
  - `FpsRegulator(target_fps=30.0)`
  - `ColorConvertStage(dst="NV12")`
- 将结果发布到系统虚拟摄像头

因此，普通集成只需要：

- `start()`
- `push_frame()`
- `shutdown()`

## 关键约束

| 约束 | 说明 |
|---|---|
| DShow 注册仍需管理员权限 | `pip install` 不会自动执行 `regsvr32` |
| 输入应为 BGR `numpy.ndarray` | `push_frame()` 内部调用 `Frame.from_bgr()` |
| 默认输出为 1280×720@30 NV12 | 默认 pipeline 自动 resize / 节流 / 转色彩格式 |
| `push_frame()` 是同步调用 | 重渲染场景建议从工作线程推帧 |
| `stop()` 只停 sink，不停 helper | 彻底退出时调用 `shutdown()` |
| DShow 与 MF 设备名应保持一致 | 建议统一使用 `AK Virtual Camera` |
| 替换 DLL 后可能需重启 `FrameServer` | `frameserver.exe` 会缓存 `akvc-mf.dll` |

## 开发态 / 诊断事实

当前项目的真实行为与文档需要保持一致：

- 开发态 runtime 查找**优先使用** `build/bin/Release`
- frame bus 诊断名是 **`Global\\akvc-frames-v1`**，不是 `Local\\...`

如果你是在仓库内开发并刚完成新构建，CLI / runtime 会优先使用新的 `build/bin/Release` 产物，而不是旧的打包资源。

## 外部 PySide6 项目的打包 / 安装器

如果你是在做**最终集成项目**，除了能跑通 `VirtualCamera`，还需要考虑如何把 `akvc` runtime 一起分发到最终用户机器。

### 推荐分发策略

推荐把 `akvc` 作为你的应用依赖一起打包，并确保以下 runtime 文件随应用分发：

- `akvc_helper.exe`
- `akvc-mf.dll`
- `akvc-dshow.dll`

无论你采用 wheel、embedded Python、PyInstaller 还是 Nuitka，本质目标都一样：

1. `import akvc` 成功
2. `akvc._runtime.windows` 中的 runtime 文件实际存在
3. 安装阶段或首次管理员启动阶段完成 `akvc register`

### 安装器流程建议

推荐安装顺序：

```text
安装文件 → 写入应用目录 → 校验 akvc runtime 存在 → 调 akvc register → 可选执行 akvc status / doctor → 完成安装
```

说明：

- `akvc-dshow.dll` 负责 OBS / Zoom / GraphStudioNext 的 DShow 枚举
- `akvc-mf.dll` 和 `akvc_helper.exe` 负责运行时虚拟摄像头与 frame bus
- `akvc register` 仍需要管理员权限，因为最终会调用 `regsvr32`

### NSIS 示例

```nsis
RequestExecutionLevel admin

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\YourApp\*"

    ExecWait '"$INSTDIR\python\python.exe" -m akvc register' $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "AKVC 注册失败（错误码 $0）。请以管理员权限重试安装。"
        Abort
    ${EndIf}

    ExecWait '"$INSTDIR\python\python.exe" -m akvc status'
    ExecWait '"$INSTDIR\python\python.exe" -m akvc doctor' $1
SectionEnd
```

对安装器来说，直接调用内嵌 Python 的 `-m akvc` 通常比依赖 PATH 里的 `akvc.exe` 更稳。

### 首次启动时再注册

如果你不想在安装阶段就申请管理员权限，也可以改成：

```text
app start
→ check akvc status
→ if not registered: prompt for elevation
→ run akvc register
→ rerun akvc doctor
→ enable camera feature
```

这样可以把管理员权限请求延后到用户真正启用虚拟摄像头功能时。

### PyInstaller / Nuitka 注意点

如果你的外部项目用 PyInstaller 或 Nuitka 打包，需要额外确认：

- `akvc` Python 包被完整带上
- `akvc._runtime.windows` 目录被完整带上
- 不是只带了 `.py`，却漏掉 `akvc_helper.exe` / `akvc-mf.dll` / `akvc-dshow.dll`
- 如果你重定向了资源目录，`importlib.resources.files("akvc._runtime.windows")` 仍然能解析到真实文件

### 应用内自检脚本示例

```python
import subprocess
import sys


def run_akvc_self_check() -> None:
    commands = [
        [sys.executable, "-m", "akvc_cli", "status"],
        [sys.executable, "-m", "akvc_cli", "doctor"],
    ]
    for cmd in commands:
        subprocess.run(cmd, check=True)
```

`tools/diag/dshow_enum.py` 更适合开发版或支持人员诊断包；最终用户安装包通常优先暴露 `status` / `doctor` 即可。

## 高级路径（仅在需要自定义时使用）

只有在这些场景下，才建议直接使用底层 API：

- 你要自己指定 helper / DLL 路径
- 你要自定义 pipeline
- 你要直接控制 helper 生命周期
- 你要绕过默认 `VirtualCamera` 封装

相关入口：

```python
from akvc.core.helper.client import HelperService
from akvc.core.frame import Frame
from akvc.core.frame_pipeline import FramePipeline, ResizeStage, FpsRegulator, ColorConvertStage
from akvc.core.frame_sink.windows_shm import WindowsShmSink
```

环境变量覆盖入口：

- `AKVC_HELPER_EXE`
- `AKVC_DSHOW_DLL`
- `AKVC_MF_DLL`

## 常见问题

| 症状 | 检查 |
|---|---|
| `start()` 失败 | helper 是否可定位；是否具备所需权限 |
| `akvc register` 失败 | 是否在管理员 shell；`akvc-dshow.dll` 是否存在 |
| OBS 看不到设备 | 是否已执行 `akvc register` |
| Chrome 看不到画面 | helper 是否运行；必要时重启 `FrameServer` |
| 设备存在但黑屏 | 是否持续调用 `push_frame()`；输入是否为有效 BGR `uint8` |
| 设备重复出现 | DShow 与 MF friendly name 是否不一致 |

## 何时不需要本 skill

以下内容不是外部消费端的默认必需品：

- desktop app（`apps/desktop/`）
- 参考 worker 进程逻辑
- 手工复制三个 native 文件到 `bin/`
- 先从底层 `akvc.core.*` 自己拼装一套 `VirtualCamera`

如果你的目标只是“把 PySide6 画面推到系统虚拟摄像头”，优先走 **root install + `akvc.sdk.VirtualCamera`**。
