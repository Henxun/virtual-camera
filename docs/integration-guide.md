# 集成 AK Virtual Camera 到你的 PySide6 项目

推荐安装方式：直接从仓库根安装（Python 3.11–3.14）。

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

macOS 补充说明：

- 直接使用 `akvc.sdk.VirtualCamera` 时，`start()` 现在会先校验 Camera Extension 是否已安装、已获系统批准、且系统设备列表里已经出现虚拟摄像头
- 在 macOS 路径下，Python 应用本身就是 producer：`VirtualCamera/MacVirtualCamera -> FramePipeline -> shared_memory_ringbuffer -> Camera Extension`
- 也就是说，日常推帧热路径**不会经过单独 helper 进程**；macOS 的 container app 只承担安装激活容器、状态命令桥和分发锚点
- `start()` 在最终阻止 `ipc_not_ready / ipc_environment_blocked` 之前，还会先尝试执行一次显式 `sync_ipc_configuration()`，把共享内存名称同步到原生控制面
- 如果仍处于 `未安装 / 待批准 / 已安装但设备未出现` 任一阶段，`start()` 会直接抛出带引导信息的异常，而不会进入“假启动”
- 现在也可以在构造时传 `camera_name="AK Virtual Camera"`；在 macOS 路径下，首次 `send()` / `push_frame()` 若尚未 `start()`，会用这个默认名触发一次隐式启动
- 推荐在首次推流前先调用 `install_extension_result()` 或 `status()` 做一次安装态检查
- 如果你要把 IPC 配置同步单独作为诊断步骤，也可以显式调用 `sync_ipc_configuration_result()` 或 CLI `akvc sync-ipc --json`
- 如果你需要把 SDK 绑定到指定构建产物，也可以继续沿用 `helper_exe=...`：
  - 传入 `.app` 路径时会覆盖 container app 路径
  - 传入 `.app/Contents/MacOS/<executable>` 时会覆盖原生控制面可执行文件路径
- 如果是新的 macOS 集成，优先推荐显式传 `app_bundle=...` 或 `app_executable=...`
  - `host_bundle=...` / `host_executable=...` 仍可继续使用，但现在只作为兼容别名映射到 `app_*`
  - `helper_exe=...` 在 macOS 路径里只保留为兼容旧调用方的别名语义，不代表推帧热路径依赖单独 helper 进程

### 这层封装会替你完成什么

`VirtualCamera` 默认会：

- Windows：启动 helper 并校验 `ping()`
- Windows：在当前 helper 生命周期里只注册一次 MF 虚拟摄像头
- macOS：直接创建 Python producer，并在 `start()` 前校验 Extension 安装/批准/设备可见性
- 自动创建 sink 并打开 frame bus
- 自动应用默认 pipeline：
  - `ResizeStage(1280×720)`
  - `FpsRegulator(30fps)`
  - `ColorConvertStage("NV12")`
- 将 `numpy/QImage/QPixmap` 等输入发布到系统虚拟摄像头

所以对大多数外部 PySide6 集成来说，只需要：

- `start()`
- `push_frame()`
- `shutdown()`

如果你走 `create_pyside6_streamer().start_provider_stream(...)` 这条路径：

- provider 返回一帧对象时会正常推流
- provider 暂时没有新帧时，可以抛 `LookupError`
- 现在也可以直接返回 `None`，streamer 会把它视为“本 tick 跳过”，不会把空值继续传给 `VirtualCamera`

如果你想让外部 PySide6 应用只依赖 SDK 主入口，而不额外 import integration 层，现在也可以直接：

```python
bridge = vc.create_pyside6_bridge()
bridge.send_image(qimage)
bridge.send_pixmap(qpixmap)
bridge.send_widget(widget)
bridge.send_screen(screen)
```

如果你不需要 Qt，想走最接近 `/Users/admir/workspace/cameraextension/vcam.mm` 的“Python 直接推 BGR 帧”路径，当前也可以直接：

```python
import numpy as np
from akvc.sdk import VirtualCamera

vc = VirtualCamera(
    width=1280,
    height=720,
    fps=30,
    camera_name="AK Virtual Camera",
    direct_only=True,
)
try:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:, :] = (32, 96, 180)
    vc.send(frame)
finally:
    vc.shutdown()
```

这条路径的推荐验收点是：

- `vc.using_direct_sender == True`
- `vc.helper_hot_path_used == False`
- `vc.shared_memory_fallback_used == False`

现在这条 `direct_only=True` 路径还额外收紧了一点：

- 如果 native direct sender 已可见并能直接打开目标系统摄像头，`VirtualCamera` / `MacVirtualCamera` 不会再先去初始化 installer/status/pkg 控制面
- 也就是说，最小“Python 直接建对象并推帧”路径已经更接近 `vcam.mm` 风格：先尝试直接打开系统虚拟摄像头，再按需触碰安装控制面

如果你希望“必须是纯直连，不允许自动退回 shared memory producer”，建议显式传 `direct_only=True`。
当前仓库里也已经开始接入更贴近 `/Users/admir/workspace/cameraextension/vcam.mm` 的 direct sender 后端：

- `MacVirtualCamera` 现在会优先尝试加载 `libakvc-macos-direct-sender.dylib`
- 如果该 native sender 可用并能成功打开系统虚拟摄像头的 sink stream，`push_frame()` 会直接走 `Python -> native direct sender -> CMIO sink stream`
- 如果 native sender 当前不可用，或者打开 sink stream 失败，会自动回退到现有 `shared memory -> Camera Extension` 路线

也就是说，当前对外 Python API 不变，但 macOS 运行时已经开始具备“优先 direct sender、失败再回退”的能力收口。

如果你希望像 `/Users/admir/workspace/cameraextension/vcam.mm` 那样，直接创建一个更贴近 native sender 的 Python 对象，而不是通过 `VirtualCamera` 包装层，现在也可以：

```python
from akvc import MacDirectCameraSender

sender = MacDirectCameraSender(
    width=1280,
    height=720,
    fps=30.0,
    camera_name="AK Virtual Camera",
)
try:
    sender.send(frame)  # 支持 Frame / numpy.ndarray / QImage / QPixmap
finally:
    sender.stop()
```

这条路径的语义是：

- 直接走 `Python -> MacDirectCameraSender -> native dylib -> CMIO sink stream`
- 不走 helper 热路径
- 不做 shared-memory fallback
- 更适合做“最小对象直推验证”或对照 `vcam.mm` 的低层调试
- 首次 `send()` / `send_image()` / `send_pixmap()` 会自动打开目标摄像头；如果你更喜欢显式生命周期控制，仍然可以继续调用 `start(name=...)`

如果你想最小化验证这条“直接对象”路径，而不自己写示例代码，也可以直接运行：

```bash
python3 tools/macos_direct_sender_object_demo.py --frames 90 --report-json build/macos/direct-sender-object-report.json
```

如果当前机器还没有相机权限，或者系统里暂时还没枚举出可直连的 CMIO 设备，这条命令现在会以非零退出，但仍然把最新 inspect snapshot 和 `direct_sender_last_error` 写进 `--report-json`，方便保留人工验收证据。

如果只想先看设备快照和相机权限状态：

```bash
python3 tools/macos_direct_sender_object_demo.py --inspect-only --request-camera-access --report-json build/macos/direct-sender-object-inspect.json
```

建议优先看这几个字段：

- `direct_sender_ready`
- `direct_sender_blocker_code`
- `direct_sender_readiness_message`
- `device_snapshot`

如果你在外部 Python 应用里想先做一次可发送性判断，而不是自己手动解释 snapshot，也可以直接调用：

```python
readiness = sender.direct_sender_readiness(request_camera_access=True)
if not readiness["ready"]:
    print(readiness["blocker_code"], readiness["message"])
```

如果你需要一份更短、更偏人工验收的操作单，可以直接看：

- [docs/macos/manual_acceptance.md](/Users/admir/workspace/virtual-camera/docs/macos/manual_acceptance.md)

如果你想继续走统一的仓库命令封装，也可以直接：

```bash
python3 tools/make.py direct-sender-object-demo --frames 90 --output build/macos/direct-sender-object-report.json
```

如果你只想最小化验证“Python 直接建对象推帧”而不写自己的示例代码，当前也可以直接运行：

```bash
python3 tools/make.py direct-push-demo --frames 90 --output build/macos/direct-push-report.json
```

它会走公开 `VirtualCamera.start() -> push_frame(numpy.ndarray)` 路径，并输出结构化报告。

如果你希望这条命令在“不是纯直连”时直接失败，而不是事后再翻 JSON，看 `using_direct_sender` / fallback 字段，也可以直接加：

```bash
python3 tools/make.py direct-push-demo --frames 90 --require-direct-runtime --output build/macos/direct-push-report.json
```

这会额外强制检查：

- `using_direct_sender == true`
- `helper_hot_path_used == false`
- `shared_memory_fallback_used == false`
- `runtime_host_in_frame_hot_path != true`

如果你当前还没拿到相机权限，或者只想先确认 Python 进程能否看到系统视频设备，也可以先运行：

```bash
python3 tools/make.py direct-push-demo --inspect-only --request-camera-access --output build/macos/direct-push-inspect.json
```

这条命令不会真正开始推帧，但会走公开 SDK 路径生成 direct sender 设备快照，并把当前 `camera_access_status`、`cmio_devices`、`avfoundation_devices` 等信息写入 JSON，适合做人工验收前的权限自检。

如果你想进一步验证“公开对象路径已经真的写入共享内存”，当前还可以运行：

```bash
python3 tools/make.py framebus-roundtrip --producer-kind mac-virtual-camera --output build/macos/framebus-roundtrip-sdk.json
```

这会通过公开 `VirtualCamera.start()+push_frame()` 路径发布一帧，再由原生 consumer probe 读回并输出结构化 JSON。

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

`VirtualCamera.send_image()` / `push_frame()` 当前已经直接接受 `QImage`：

- 常见彩色格式会自动归一化
- `Grayscale8 / Indexed8` 这类单通道 `QImage` 也会自动扩展成 BGR
- `QPixmap` 会先转成 `QImage` 再走同一条路径

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
2. 让包内 `akvc/_runtime/windows` 仍能找到这 3 个 runtime 文件
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
- `akvc/_runtime/windows` 目录必须原样包含
- 不要只打进去 `.py`，却漏掉 3 个 `.exe/.dll` runtime 文件
- 若你重定向过资源目录，要保证包内 `akvc/_runtime/windows` 仍能被 `akvc.runtime` 解析到真实文件

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

仅在你需要自定义 Windows helper / macOS runtime / pipeline 行为时，才建议直接使用底层 API。

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

## 9. macOS 分发态 runtime 资产

macOS 当前的 Python 安装链路同样支持从包内 runtime 目录发现安装资产。

建议在生成 `VirtualCamera.pkg` 后执行：

```bash
python3 tools/make.py sync-macos-runtime --require-pkg
```

或直接：

```bash
python3 tools/make.py package --sync-runtime
```

这会把以下文件同步到 `camera-core/src/akvc/_runtime/macos`：

- `akvc-macos-status`
- `akvc-macos-install`
- `akvc-macos-uninstall`
- `akvc-macos-list-devices`
- `akvc-macos-sync-ipc`
- `VirtualCamera.pkg`

当前 GitHub Actions / Jenkins 归档的 runtime 资产也已包含 `akvc-macos-sync-ipc`，因此：

1. SDK 显式 `sync_ipc_configuration_result()`
2. CLI `akvc sync-ipc --json`

这两条诊断路径在开发态与分发态现在都共享同一份原生产物约定。

这样在 wheel、外部 PySide6 打包目录或嵌入式 Python 环境里，`akvc.runtime` 仍能优先按以下顺序定位 macOS 安装资产：

1. 显式传入路径
2. `AKVC_MACOS_*` / `AKVC_HOST_*` 环境变量
3. 当前开发构建目录 `build/macos/...`
4. 包内 `akvc/_runtime/macos`

如果你的外部项目不是直接安装仓库根包，而是单独依赖 `akvc-core`，当前 `camera-core/pyproject.toml` 也已显式声明这些 macOS runtime 资产。也就是说：

1. 根包 `amaran-virtual-camera`
2. Core 包 `akvc-core`

这两条分发路径现在都会把 `_runtime/macos` 目录纳入 package data，而不再只有仓库根安装路径可见。

---

## 8. 故障排查

| 症状 | 检查 |
|---|---|
| Windows `start()` 失败 | 是否管理员运行；helper 是否能从包资源/显式路径找到 |
| macOS `start()` 直接报“未安装/待批准/设备未出现” | 先执行 `install_extension_result()` 或 `status()`，确认是否已完成 pkg 安装、系统批准和设备枚举收敛 |
| macOS `start()` 报 IPC 未就绪 / 环境阻塞 | 先执行 `status()` 查看 `ipc_ready / ipc_last_error`，再尝试 `sync_ipc_configuration_result()` 或 `akvc sync-ipc --json`，确认共享内存名称已同步到原生控制面 |
| `akvc register` 失败 | 是否管理员 shell；`akvc-dshow.dll` 是否存在 |
| Chrome 看不到设备 | helper 是否在运行；必要时重启 FrameServer：`Stop-Service FrameServer; Start-Service FrameServer` |
| OBS 看不到设备 | 是否已执行 `akvc register` |
| 有设备但黑屏 | `push_frame()` 是否持续调用；传入的是否为有效 BGR `uint8` |
| 两个设备 | DShow 和 MF friendly name 是否不一致 |
