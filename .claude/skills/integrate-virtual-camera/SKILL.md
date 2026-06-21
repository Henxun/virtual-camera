---
name: integrate-virtual-camera
description: 将 AK Virtual Camera（DShow + MF 双栈）集成到外部 PySide6/Python 项目。最小依赖方案：akvc-core 包 + 3 个 native 二进制文件。适用于已有自有视频源、需要将画面推送到系统虚拟摄像头的应用。
---

# 集成 AK Virtual Camera 到外部项目

本 skill 面向**消费端**：你已有一个 PySide6（或任意 Python）应用能产出视频帧，想把帧推送到系统级虚拟摄像头，让 Chrome/OBS/Teams/Zoom 都能看到。**不需要** desktop app 或 worker 子进程——只需 `akvc-core` 包 + 三个 native 二进制文件。

构建/调试/内部架构知识在配套 skill `windows-virtual-camera` 中；本 skill 是集成捷径。

## 1. 前置准备（一次性，在开发/构建机器上）

从 AK Virtual Camera 项目构建三个 native 二进制（管理员 VS 命令行）：
```bash
cd /path/to/amaran-virtual-camera
uv run tools/make.py configure
uv run tools/make.py build
```

产物在 `build/bin/Release/`：
| 文件 | 作用 |
|---|---|
| `akvc_helper.exe` | 拥有 `Global\` 共享内存；注册 MF 虚拟摄像头；无生产者时发布占位帧。 |
| `akvc-mf.dll` | MF VirtualCamera MediaSource DLL（由 `frameserver.exe` 加载）。 |
| `akvc-dshow.dll` | DirectShow source filter（供 OBS/Zoom/GraphStudioNext 使用）。 |

一次性 DShow 注册（管理员）：
```bash
uv run python -m akvc_cli register
```

将 Python 包安装到你的项目：
```bash
pip install -e /path/to/amaran-virtual-camera/camera-core
```

## 2. 复制二进制文件到你的项目

把三个文件放到固定目录（如 `bin/`）：
```
your-project/
├── bin/
│   ├── akvc_helper.exe
│   ├── akvc-mf.dll
│   └── akvc-dshow.dll
└── main.py
```

在 import `akvc` **之前**，用环境变量告诉 helper client 去哪找 exe：
```python
import os
os.environ["AKVC_HELPER_EXE"] = os.path.join(os.path.dirname(__file__), "bin", "akvc_helper.exe")
```

## 3. 最小集成类

```python
import os
import numpy as np

os.environ.setdefault("AKVC_HELPER_EXE",
                      os.path.join(os.path.dirname(__file__), "bin", "akvc_helper.exe"))

from akvc.core.helper.client import HelperService
from akvc.core.frame import Frame
from akvc.core.frame_pipeline import FramePipeline, ResizeStage, ColorConvertStage
from akvc.core.frame_sink.windows_shm import WindowsShmSink

class VirtualCamera:
    """将 BGR numpy 帧推送到系统级 AK Virtual Camera。"""

    WIDTH, HEIGHT, FPS = 1280, 720, 30

    def __init__(self):
        self.helper = HelperService()
        self.sink = WindowsShmSink()
        self.pipeline = (
            FramePipeline()
            .add(ResizeStage(target_w=self.WIDTH, target_h=self.HEIGHT))
            .add(ColorConvertStage(dst="NV12"))
        )
        self._started = False

    def start(self) -> bool:
        """启动 helper（注册 MF 设备 + 创建 Global\ 共享内存）并打开 sink。
        必须以管理员权限运行——Global\ 共享内存需要 SeCreateGlobalPrivilege。
        成功返回 True。"""
        if not self.helper.start():
            return False
        self.helper.register_mf()
        self.sink.open()
        self._started = True
        return True

    def push_frame(self, bgr: np.ndarray):
        """推送一帧 BGR 图像（HxWx3 uint8，任意尺寸——自动缩放）。
        在渲染定时器/工作线程中调用。同步执行，约 1ms。"""
        if not self._started:
            return
        frame = Frame.from_bgr(bgr)
        frame = self.pipeline.process(frame)   # → 1280×720 NV12
        self.sink.publish(frame)

    def stop(self):
        """停止推流；设备保持注册（helper 继续运行）。"""
        if self._started:
            self.sink.close()
            self._started = False

    def shutdown(self):
        """完全关闭——停止 helper（MF 设备 Stop）。app 退出时调用。"""
        self.stop()
        self.helper.stop()
```

## 4. 在 PySide6 中使用

```python
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import numpy as np, sys

app = QApplication(sys.argv)
vc = VirtualCamera()
if not vc.start():
    sys.exit("启动失败——请以管理员运行")

timer = QTimer()
seq = [0]
def on_tick():
    # 替换成你的真实帧源（QImage、OpenCV、渲染输出…）
    bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
    bgr[:, :] = (seq[0] % 256, 100, 50)
    seq[0] += 4
    vc.push_frame(bgr)

timer.timeout.connect(on_tick)
timer.start(int(1000 / vc.FPS))
rc = app.exec()
vc.shutdown()
```

### 推送真实画面

从 QImage 转换：
```python
def qimage_to_bgr(qimg):
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(qimg.height(), qimg.width(), 4)
    return arr[:, :, :3].copy()   # RGBA → BGR
```

从 OpenCV 转换：
```python
ok, bgr = cap.read()
if ok: vc.push_frame(bgr)
```

## 5. 约束与注意事项

| 约束 | 原因 |
|---|---|
| **必须管理员运行** | helper 创建 `Global\akvc-frames-v1`——需要 `SeCreateGlobalPrivilege`。非管理员运行 `CreateFileMappingW` 返回错误 5。 |
| **帧尺寸灵活** | `ResizeStage` 自动缩放到 1280×720，`ColorConvertStage` 自动转 BGR→NV12。你只需传原始 BGR。 |
| **`push_frame` 是同步的** | 约 1ms（共享内存 memcpy + 事件信号）。可从 QThread 调用；SHM 写入有锁保护。但不可多线程同时调用——需串行化。 |
| **`register_mf` 每个 helper 生命周期只需一次** | helper 内部有标志跟踪；Start→Stop→Start（切换源）时重复调用是安全的。 |
| **app 退出必须调 `shutdown()`** | 否则 helper 成为孤儿，MF 设备节点残留（System 生命周期）。`shutdown()` → `helper.stop()` → helper 读到 stdin EOF → 干净 Stop。 |
| **替换 DLL 后需重启 FrameServer** | `frameserver.exe` 缓存 `akvc-mf.dll`。更新 DLL 后：`Stop-Service FrameServer; Start-Service FrameServer`（管理员）。 |
| **只显示一个 AK Virtual Camera 设备** | MF 设备（KSCATEGORY_VIDEO_CAMERA）+ DShow filter（VideoInputDeviceCategory）用相同 friendly name，Win11 会聚合为一个设备。不要用不同的名字注册 DShow filter。 |
| **PnP 名 "Windows Virtual Camera Device"** | 仅装饰性——设备管理器显示这个名字是因为 AddProperty 无法覆盖 MF VirtualCamera 设备节点名。应用通过 MF friendlyName 看到 "AK Virtual Camera"。忽略它。 |

## 6. 线程模型

SHM sink（`WindowsShmSink.publish`）内部使用 `threading.Lock` + Win32 互斥锁——单线程逐次调用是安全的。GUI 应用建议：

- **简单场景**：从 `QTimer` 调用 `push_frame`（在 GUI 线程运行，30fps 没问题——约 1ms 开销）。
- **重渲染场景**：从 `QThread` 工作线程推送，避免阻塞 GUI；缓存最新帧让定时器拉取。

不要在同一进程启动多个 `VirtualCamera` 实例——helper 是单例（一个 SHM、一个 MF 设备）。

## 7. 分发/安装器

### 7.1 注册时机说明

| 组件 | 注册时机 | 方式 |
|---|---|---|
| DShow filter（`akvc-dshow.dll`） | **安装时** | `regsvr32`（调用 `DllRegisterServer`，写 CLSID + VideoInputDeviceCategory） |
| MF CLSID（`akvc-mf.dll`） | **安装时**（可选） | `regsvr32` 或手动写 `HKLM\SOFTWARE\Classes\CLSID\{...}\InprocServer32` |
| MF VirtualCamera 设备 | **运行时** | helper 调 `MFCreateVirtualCamera`（不在安装器做，与 OBS 28+ 一致） |

DShow filter 必须在安装时注册——否则 OBS/Zoom/GraphStudioNext 看不到设备（这些应用只枚举 `VideoInputDeviceCategory`，不会触发运行时注册）。MF 设备由 helper 在首次启动时创建，安装器不需要管。

### 7.2 NSIS 安装脚本片段

```nsis
; ---- 安装时注册 DShow filter + MF CLSID（需要管理员权限）----
Section "Register Virtual Camera" SecRegister
    SetOutPath "$INSTDIR\bin"
    File "build\bin\Release\akvc_helper.exe"
    File "build\bin\Release\akvc-mf.dll"
    File "build\bin\Release\akvc-dshow.dll"

    ; 注册 DShow filter（写 CLSID + VideoInputDeviceCategory）
    ExecWait '"$SYSDIR\regsvr32" /s "$INSTDIR\bin\akvc-dshow.dll"' $0
    ${If} $0 != 0
        DetailPrint "警告：DShow filter 注册失败 (错误码 $0)"
    ${EndIf}

    ; 注册 MF CLSID（可选——helper 运行时也会注册，预注册避免首次延迟）
    ExecWait '"$SYSDIR\regsvr32" /s "$INSTDIR\bin\akvc-mf.dll"' $0
SectionEnd

; ---- 卸载时注销 ----
Section "Unregister Virtual Camera" SecUnregister
    ExecWait '"$SYSDIR\regsvr32" /u /s "$INSTDIR\bin\akvc-dshow.dll"'
    ExecWait '"$SYSDIR\regsvr32" /u /s "$INSTDIR\bin\akvc-mf.dll"'

    ; 如果 helper 曾运行过，MF 设备节点可能残留——提示用户或用 pnputil 清理
    ; （需要管理员权限；System 生命周期设备不会自动消失）
    Delete "$INSTDIR\bin\akvc_helper.exe"
    Delete "$INSTDIR\bin\akvc-mf.dll"
    Delete "$INSTDIR\bin\akvc-dshow.dll"
SectionEnd
```

### 7.3 纯注册表方式（不用 regsvr32）

如果不想用 `regsvr32`（或做 MSIX/UWP 打包），可以直接写注册表：

```nsis
; DShow filter CLSID {8E14549A-DB61-4309-AFA1-3578E927E933}
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{8E14549A-DB61-4309-AFA1-3578E927E933}" "" "AK Virtual Camera"
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{8E14549A-DB61-4309-AFA1-3578E927E933}\InprocServer32" "" "$INSTDIR\bin\akvc-dshow.dll"
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{8E14549A-DB61-4309-AFA1-3578E927E933}\InprocServer32" "ThreadingModel" "Both"

; MF source CLSID {3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}\InprocServer32" "" "$INSTDIR\bin\akvc-mf.dll"
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{3C2D3A1A-8E5F-4B8F-9C1A-2D7E5F1A3B4C}\InprocServer32" "ThreadingModel" "Both"

; DShow VideoInputDeviceCategory 条目（让 OBS/Zoom 枚举到）
; {860BB310-5D01-11d0-BD3B-00A0C911CE86} = VideoInputDeviceCategory
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{860BB310-5D01-11d0-BD3B-00A0C911CE86}\Instance\{8E14549A-DB61-4309-AFA1-3578E927E933}" "FriendlyName" "AK Virtual Camera"
WriteRegStr HKLM "SOFTWARE\Classes\CLSID\{860BB310-5D01-11d0-BD3B-00A0C911CE86}\Instance\{8E14549A-DB61-4309-AFA1-3578E927E933}\CLSID" "" "{8E14549A-DB61-4309-AFA1-3578E927E933}"
```

> 注意：纯注册表方式缺少 `FilterData` 二进制块（`IFilterMapper2::RegisterFilter` 会生成）。部分 DShow 消费端（如 GraphStudioNext）需要 `FilterData` 才能完整枚举。优先用 `regsvr32`（调 `DllRegisterServer`），它会通过 `IFilterMapper2` 写完整的 `FilterData`。

### 7.4 安装器必须管理员权限

NSIS 脚本开头加：
```nsis
RequestExecutionLevel admin
```

因为 `regsvr32` 写 `HKLM` + DShow filter 注册到 `VideoInputDeviceCategory` 都需要管理员权限。

### 7.5 卸载时清理 MF 设备节点

System 生命周期的 MF 设备节点不会随卸载自动消失。卸载脚本应提示用户，或尝试清理：

```nsis
Section "Uninstall"
    ; 先停 helper（如果在运行）
    nsExec::ExecToLog 'taskkill /f /im akvc_helper.exe'

    ; 注销 DShow + MF CLSID
    ExecWait '"$SYSDIR\regsvr32" /u /s "$INSTDIR\bin\akvc-dshow.dll"'
    ExecWait '"$SYSDIR\regsvr32" /u /s "$INSTDIR\bin\akvc-mf.dll"'

    ; 清理残留 MF 设备节点（需要 Windows 10 2004+ 的 pnputil）
    nsExec::ExecToLog 'pnputil /enum-devices /class SoftwareDevice' ; 用户手动确认后删

    Delete "$INSTDIR\bin\akvc_helper.exe"
    Delete "$INSTDIR\bin\akvc-mf.dll"
    Delete "$INSTDIR\bin\akvc-dshow.dll"
SectionEnd
```

> MF 设备节点清理较复杂（`pnputil /remove-device` 需要精确的 InstanceId）。建议卸载器提示用户"请在设备管理器中手动删除虚拟摄像头设备"，或在 helper 里加一个 `--unregister` 参数调 `IMFVirtualCamera::Remove()`。

## 8. 故障排查

| 症状 | 检查 |
|---|---|
| `start()` 返回 False | `AKVC_HELPER_EXE` 路径对吗？是否管理员运行？ |
| Chrome 看不到设备 | helper 在运行吗？（`vc.helper.ping()`）。重启 FrameServer：`Stop-Service FrameServer; Start-Service FrameServer`。 |
| OBS 看不到设备 | DShow 注册了吗？（`akvc_cli register` 一次，管理员）。 |
| 有设备但黑屏 | `push_frame` 有在调吗？帧是有效的 BGR uint8 吗？helper 日志在 `%LOCALAPPDATA%\AKVC\logs\akvc.worker.log`。 |
| 有设备但画面不动 | `akvc-core` 版本有心跳修复吗？（用 `GetSystemTimeAsFileTime`，不是 `perf_counter`）。 |
| 设备列表出现两个 | DShow 和 MF 的 friendly name 不同？都必须是 "AK Virtual Camera"。MF 必须注册 `KSCATEGORY_VIDEO_CAMERA`。 |
| 崩溃后残留设备 | `Get-PnpDevice \| Where InstanceId -like '*VCAMDEVAPI*'` 然后管理员 `pnputil /remove-device <id>`。 |
| `ImportError: akvc` | 没执行 `pip install -e /path/to/camera-core`？ |

## 9. 不需要的东西

- desktop app（`apps/desktop/`）——它是参考 UI，你的 app 替代它。
- FrameWorker 子进程（`frame_worker.py`）——那是为隔离 GUI 和采集设计的；你直接调 `sink.publish()` 即可。
- CLI（`apps/cli/`）——仅一次性 `register`/`unregister` 时需要。
- 测试图 / USB provider——自带帧源即可。

## 10. 文件布局总结

```
your-project/
├── bin/                          # 从 build/bin/Release/ 复制
│   ├── akvc_helper.exe
│   ├── akvc-mf.dll
│   └── akvc-dshow.dll
├── your_app.py                   # 设置 AKVC_HELPER_EXE，import akvc.core.*
└── (akvc-core 通过 pip install -e 安装)
```
