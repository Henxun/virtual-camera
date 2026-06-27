# 集成 AK Virtual Camera 到你的 PySide6 项目

推荐安装方式：直接从仓库根安装（Python 3.11–3.12）。

```bash
pip install <repo-url>
```

安装后即可使用：

```python
from akvc.sdk import VirtualCamera
```

Windows 包会在安装阶段构建并提供 runtime 二进制：

- `akvc_helper.exe`
- `akvc-mf.dll`
- `akvc-dshow.dll`

> 注意：`pip install` 不会自动完成 DShow 注册，也不会绕过管理员权限要求。

---

## 1. 推荐路径：直接使用 `akvc.sdk.VirtualCamera`

```python
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from akvc.sdk import VirtualCamera

app = QApplication([])
vc = VirtualCamera()
vc.start(name="AK Virtual Camera")

label = QLabel("推流中…打开 OBS/Chrome 选 AK Virtual Camera")
label.show()

seq = [0]

def on_tick() -> None:
    bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
    bgr[:, :] = (seq[0] % 256, 100, 50)
    seq[0] += 4
    vc.push_frame(bgr)

timer = QTimer()
timer.timeout.connect(on_tick)
timer.start(33)

try:
    app.exec()
finally:
    vc.shutdown()
```

### 这层封装会替你完成什么

`VirtualCamera` 默认会：

- 启动 helper 并校验 `ping()`
- 在当前 helper 生命周期里只注册一次 MF 虚拟摄像头
- 自动创建 sink 并打开 frame bus
- 自动应用默认 pipeline：
  - `ResizeStage(1280×720)`
  - `FpsRegulator(30fps)`
  - `ColorConvertStage("NV12")`
- 将 BGR `numpy.ndarray` 发布到系统虚拟摄像头

所以对大多数外部 PySide6 集成来说，只需要：

- `start()`
- `push_frame()`
- `shutdown()`

---

## 2. 验证路径

如果你要让 OBS / Zoom / GraphStudioNext 走 DShow 路径识别设备，仍需管理员注册：

```bash
akvc register
```

检查安装与注册状态：

```bash
akvc status
akvc doctor
```

如果要进一步确认 DirectShow 枚举与 frame bus 是否都正常：

```bash
uv run python tools/diag/dshow_enum.py
```

该脚本会同时检查：

1. `InprocServer32` 注册是否存在
2. `ICreateDevEnum(VideoInputDeviceCategory)` 是否能枚举到 `AK Virtual Camera`
3. frame bus 是否在 `Global\\akvc-frames-v1` 上持续流帧

最近一轮验证里，该脚本已经跑通了这三项检查。

---

## 3. 关键约束

| 约束 | 原因 |
|---|---|
| **DShow 注册仍需管理员权限** | `akvc register` 本质上仍要调用 `regsvr32` |
| **输入必须是 BGR `numpy.ndarray`** | `VirtualCamera.push_frame()` 内部会调用 `Frame.from_bgr()` |
| **默认输出是 1280×720@30 NV12** | 默认 pipeline 会自动 resize / 节流 / 转色彩格式 |
| **`push_frame()` 是同步执行** | 重渲染场景建议从 `QThread` 推帧，避免阻塞 GUI |
| **`stop()` 不会停 helper** | 便于后续重新 `start()`；完全退出时请调用 `shutdown()` |
| **DShow 与 MF friendly name 应保持一致** | 建议统一使用 `AK Virtual Camera`，避免设备重复或聚合异常 |
| **替换 DLL 后可能需重启 FrameServer** | `frameserver.exe` 会缓存 `akvc-mf.dll` |

---

## 4. 推送你的真实画面

### QImage → BGR

```python
def qimage_to_bgr(qimg):
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(qimg.height(), qimg.width(), 4)
    return arr[:, :, :3].copy()
```

### OpenCV → BGR

```python
ok, bgr = cap.read()
if ok:
    vc.push_frame(bgr)
```

---

## 5. 外部 PySide6 项目的打包 / 安装器示例

这一节面向**最终集成项目**，也就是“你的 PySide6 应用”如何把 `akvc` runtime 一起带走并在用户机器上完成安装。

### 5.1 推荐分发策略

推荐把 `akvc` 当作你的应用依赖，并在你的安装包里一并带上它安装后生成的 runtime 资产：

- Python 包：`akvc`
- runtime 二进制：
  - `akvc_helper.exe`
  - `akvc-mf.dll`
  - `akvc-dshow.dll`

推荐安装目标目录：

```text
YourApp/
├── your_app.exe
├── python/...
└── akvc/
    └── _runtime/
        └── windows/
            ├── akvc_helper.exe
            ├── akvc-mf.dll
            └── akvc-dshow.dll
```

如果你采用 wheel / embedded Python / PyInstaller / Nuitka，本质目标都一样：

1. 让 `import akvc` 成功
2. 让包内 `akvc._runtime.windows` 仍能找到这 3 个 runtime 文件
3. 安装阶段或首次管理员启动阶段完成 `akvc register`

### 5.2 安装器流程建议

对最终用户安装器，建议分成两步：

1. **复制应用文件和 Python 运行时**
2. **以管理员权限执行 DShow 注册**

推荐顺序：

```text
安装文件 → 写入应用目录 → 校验 akvc runtime 存在 → 调 akvc register → 可选执行 akvc status / doctor → 完成安装
```

其中：

- `akvc-dshow.dll` 负责 OBS / Zoom / GraphStudioNext 的 DShow 枚举
- `akvc-mf.dll` 和 `akvc_helper.exe` 负责运行时虚拟摄像头与 frame bus
- `akvc register` 仍然需要管理员权限，因为它最终会调用 `regsvr32`

### 5.3 NSIS 示例

如果你的外部 PySide6 项目使用 NSIS，可以参考下面的思路：

```nsis
RequestExecutionLevel admin

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\YourApp\*"

    ; 注册 AKVC DShow filter
    ExecWait '"$INSTDIR\python\python.exe" -m akvc_cli register' $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "AKVC 注册失败（错误码 $0）。请以管理员权限重试安装。"
        Abort
    ${EndIf}

    ; 可选：做一次安装后自检
    ExecWait '"$INSTDIR\python\python.exe" -m akvc_cli status'
    ExecWait '"$INSTDIR\python\python.exe" -m akvc_cli doctor' $1
SectionEnd
```

如果你的安装包里暴露的是控制台脚本 `akvc.exe`，也可以直接调用它；但对安装器来说，直接调用内嵌 Python 的 `-m akvc_cli` 往往更稳，因为路径可控。

### 5.4 首次启动时的应用内策略

如果你的安装器不想在安装阶段就注册，也可以改为：

- 首次启动时检测 `akvc status`
- 未注册则提示用户“需要管理员授权以启用虚拟摄像头”
- 拉起一个 elevated helper 或二次启动注册器完成 `akvc register`

推荐逻辑：

```text
app start
→ check akvc status
→ if not registered: prompt for elevation
→ run akvc register
→ rerun akvc doctor
→ enable camera feature
```

这样可以把“管理员权限”只放在真正使用虚拟摄像头功能的用户路径上。

### 5.5 PyInstaller / Nuitka 打包注意点

如果你的外部项目用 PyInstaller 或 Nuitka 打包，需要额外注意：

- `akvc` 的 Python 包必须完整带上
- `akvc._runtime.windows` 目录必须原样包含
- 不要只打进去 `.py`，却漏掉 3 个 `.exe/.dll` runtime 文件
- 若你重定向过资源目录，要保证 `importlib.resources.files("akvc._runtime.windows")` 仍能解析到真实文件

一个实用检查是：打包后的应用目录里，确认这三个文件实际存在：

- `akvc_helper.exe`
- `akvc-mf.dll`
- `akvc-dshow.dll`

### 5.6 应用内自检脚本示例

你可以在外部 PySide6 项目里加一个安装后诊断入口：

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

如果你还保留了仓库内的诊断脚本，也可以在开发版集成包中增加：

```python
subprocess.run([sys.executable, "tools/diag/dshow_enum.py"], check=True)
```

但对最终用户安装包，通常优先暴露 `status` / `doctor` 即可；`dshow_enum.py` 更适合开发版或支持人员诊断包。

---

## 6. 高级 / 底层路径

仅在你需要自定义 helper / runtime / pipeline 行为时，才建议直接使用底层 API。

可覆盖的环境变量：

- `AKVC_HELPER_EXE`
- `AKVC_DSHOW_DLL`
- `AKVC_MF_DLL`

底层入口：

```python
from akvc.core.helper.client import HelperService
from akvc.core.frame import Frame
from akvc.core.frame_pipeline import FramePipeline, ResizeStage, FpsRegulator, ColorConvertStage
from akvc.core.frame_sink.windows_shm import WindowsShmSink
```

如果只是普通 PySide6 集成，优先继续使用 `akvc.sdk.VirtualCamera`。

---

## 7. 开发态运行时事实

当前实现的真实行为如下：

- runtime 资产查找会**优先使用** `build/bin/Release`
- 只有在开发产物不存在时，才会回退到打包进 wheel 的 runtime 资源
- frame bus 诊断名是 **`Global\\akvc-frames-v1`**，不是 `Local\\...`

因此，在仓库内开发时，重新构建后二进制会优先被 CLI / SDK 使用，不会默认落回旧的包内 DLL。

---

## 8. 故障排查

| 症状 | 检查 |
|---|---|
| `start()` 失败 | 是否管理员运行；helper 是否能从包资源/显式路径找到 |
| `akvc register` 失败 | 是否管理员 shell；`akvc-dshow.dll` 是否存在 |
| Chrome 看不到设备 | helper 是否在运行；必要时重启 FrameServer：`Stop-Service FrameServer; Start-Service FrameServer` |
| OBS 看不到设备 | 是否已执行 `akvc register` |
| 有设备但黑屏 | `push_frame()` 是否持续调用；传入的是否为有效 BGR `uint8` |
| 两个设备 | DShow 和 MF friendly name 是否不一致 |
