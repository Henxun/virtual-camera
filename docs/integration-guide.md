# 集成 AK Virtual Camera 到你的 PySide6 项目

最小依赖：`akvc-core` 包 + 3 个 native 文件（`akvc_helper.exe`、`akvc-mf.dll`、`akvc-dshow.dll`）。
不需要整个 desktop app，直接用 camera-core 的 API 推流。

---

## 1. 前置准备

### 1.1 构建 native 二进制

在本项目根目录（管理员 VS 开发命令行）：
```bash
uv run tools/make.py configure
uv run tools/make.py build
```

产物在 `build/bin/Release/`：
- `akvc_helper.exe` — 拥有共享内存 + 注册 MF 设备
- `akvc-mf.dll` — MF VirtualCamera MediaSource
- `akvc-dshow.dll` — DShow 兼容 filter

### 1.2 一次性注册 DShow（管理员）
```bash
uv run python -m akvc_cli register
```

### 1.3 安装 camera-core 包

在你的项目里：
```bash
pip install -e /path/to/amaran-virtual-camera/camera-core
```

### 1.4 复制 native 文件到你的项目

把 3 个文件放到你的项目的一个固定目录，例如 `bin/`：
```
你的项目/
├── bin/
│   ├── akvc_helper.exe
│   ├── akvc-mf.dll
│   └── akvc-dshow.dll
└── main.py
```

用环境变量告诉 helper client 去哪找：
```python
import os
os.environ["AKVC_HELPER_EXE"] = "bin/akvc_helper.exe"
```

---

## 2. 最小集成代码

```python
import os
import sys
import time
import numpy as np

# 告诉 helper client 去哪找 exe（必须在 import akvc 之前）
os.environ["AKVC_HELPER_EXE"] = os.path.join(os.path.dirname(__file__), "bin", "akvc_helper.exe")

from akvc.core.helper.client import HelperService
from akvc.core.frame import Frame, FLAG_NONE
from akvc.core.frame_pipeline import FramePipeline, ResizeStage, ColorConvertStage
from akvc.core.frame_sink.windows_shm import WindowsShmSink

WIDTH, HEIGHT, FPS = 1280, 720, 30

class VirtualCamera:
    """在你的 PySide6 项目里：把 numpy BGR 帧推到虚拟摄像头。"""

    def __init__(self):
        self.helper = HelperService()
        self.sink = WindowsShmSink()
        self.pipeline = (
            FramePipeline()
            .add(ResizeStage(target_w=WIDTH, target_h=HEIGHT))
            .add(ColorConvertStage(dst="NV12"))
        )
        self._started = False

    def start(self) -> bool:
        """启动 helper（注册 MF 设备 + 创建共享内存）+ 打开 sink。
        返回 True 表示成功。需要管理员权限（Global\\ SHM）。"""
        if not self.helper.start():
            print("helper 启动失败——请以管理员运行")
            return False
        # 注册 MF 虚拟摄像头（只需一次）
        if not self.helper.is_alive() or not self.helper.ping():
            print("helper 无响应")
            return False
        # 注册 MF 设备（重复调用安全——helper 内部只注册一次）
        self.helper.register_mf()
        # 打开共享内存 sink（连接 helper 创建的 Global\ SHM）
        self.sink.open()
        self._started = True
        return True

    def push_frame(self, bgr: np.ndarray):
        """推送一帧 BGR 图像（HxWx3 uint8）到虚拟摄像头。
        在你的渲染线程 / 定时器回调里调用。"""
        if not self._started:
            return
        frame = Frame.from_bgr(bgr)
        frame = self.pipeline.process(frame)   # resize + BGR→NV12
        self.sink.publish(frame)

    def stop(self):
        """停止推流，关闭 sink。helper 继续运行（设备保持可用）。"""
        if self._started:
            self.sink.close()
            self._started = False

    def shutdown(self):
        """完全关闭——停 helper（MF 设备 Stop）。app 退出时调用。"""
        self.stop()
        self.helper.stop()


# ── 在 PySide6 里使用 ──────────────────────────────────
if __name__ == "__main__":
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication(sys.argv)
    vc = VirtualCamera()
    if not vc.start():
        sys.exit(1)

    label = QLabel("推流中…打开 OBS/Chrome 选 AK Virtual Camera")
    label.show()

    # 模拟一帧动态画面（替换成你的真实渲染输出）
    seq = [0]
    def on_tick():
        bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        bgr[:, :] = (seq[0] % 256, 100, 50)  # 变色
        seq[0] += 4
        vc.push_frame(bgr)

    timer = QTimer()
    timer.timeout.connect(on_tick)
    timer.start(int(1000 / FPS))  # 30fps

    rc = app.exec()
    vc.shutdown()
    sys.exit(rc)
```

---

## 3. 关键约束

| 约束 | 原因 |
|---|---|
| **必须管理员运行** | helper 创建 `Global\` 共享内存需要 `SeCreateGlobalPrivilege` |
| **帧必须是 1280×720 NV12** | pipeline 的 `ResizeStage` + `ColorConvertStage` 会自动转，你只需传入任意尺寸的 BGR |
| **`push_frame` 在调用线程同步执行** | 如果你的渲染线程很忙，建议放到独立 QThread；当前实现非线程安全 |
| **helper 退出后设备消失** | MF 设备是 helper 进程持有的；app 正常关闭会 Stop 设备 |
| **`register_mf` 只需一次** | helper 内部有 `_mf_registered` 标志，重复 Start/Stop 源不会重复注册 |

---

## 4. 推流你的真实画面

把 `on_tick` 里的 `bgr` 替换成你的真实渲染输出：

```python
# 例：从 QImage 转 BGR numpy
def qimage_to_bgr(qimg):
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(qimg.height(), qimg.width(), 4)
    return arr[:, :, :3].copy()  # RGBA→BGR

# 例：从另一个 OpenCV VideoCapture
cap = cv2.VideoCapture(0)
def on_tick():
    ok, bgr = cap.read()
    if ok:
        vc.push_frame(bgr)
```

---

## 5. 不需要 worker 子进程

本项目的 desktop app 用 `multiprocessing.spawn` 起了一个 FrameWorker 子进程来推流，那是为了隔离 GUI 和采集。**你的项目可以直接在主线程或工作线程调 `push_frame`**，不需要子进程——`WindowsShmSink.publish` 是普通函数调用，写共享内存。

---

## 6. 故障排查

| 症状 | 检查 |
|---|---|
| `helper 启动失败` | `AKVC_HELPER_EXE` 路径对不对；是否管理员运行 |
| Chrome 看不到设备 | helper 是否在运行（`vc.helper.ping()`）；FrameServer 重启过没（`Stop-Service FrameServer; Start-Service FrameServer`） |
| OBS 看不到设备 | DShow 是否注册过（`akvc_cli register`，管理员一次） |
| 有设备但黑屏 | `push_frame` 是否在调；帧尺寸是否 720p；helper 日志在 `%LOCALAPPDATA%\AKVC\logs\` |
| 有设备但画面不动 | `WindowsShmSink._write_heartbeat` 是否用 `GetSystemTimeAsFileTime`（本项目已修复）；看你用的 akvc-core 版本 |
| 两个设备 | DShow 和 MF friendly name 必须相同（都是 "AK Virtual Camera"）；MF 注册了 `KSCATEGORY_VIDEO_CAMERA` |
