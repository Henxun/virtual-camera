# Phase 2 — Windows DirectShow MVP — Implementation Plan

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 2 — Windows DirectShow MVP
**前置文档**：Phase 0 / Phase 1 全部文档

> 本文档把 Phase 1 的设计契约**裁剪并落地**为 Phase 2 的可交付物。
> 范围聚焦 Windows DirectShow 路径，目标是用最短链路验证：USB Camera → Pipeline → Frame Bus → DShow Filter → OBS/Zoom/Chrome 拉流。

---

## 1. 范围裁剪 (In/Out)

### 1.1 Phase 2 In Scope（必须交付）

| 模块 | 交付物 |
|---|---|
| `virtualcam/shared/` | 帧协议头 `akvc_protocol.h`、错误码 `akvc_errors.h`、版本 `akvc_version.h` |
| `virtualcam/windows/framebus/` | 共享内存 Ring Buffer（C++ Reader/Writer），撕裂保护、ACL |
| `virtualcam/windows/dshow/` | DirectShow Source Filter DLL（CSource + CSourceStream + IAMStreamConfig + 注册表自描述） |
| `camera-core/` | Frame、FrameProvider（USB / TestPattern）、FramePipeline、FrameSink（写 SHM）、Errors、Metrics、Logging |
| `apps/desktop/` | PySide6 桌面应用（MVVM 闭环：选源 → 启动 → 实时预览 → 推送到虚拟摄像头） |
| `apps/cli/` | `akvc` 注册/卸载 CLI |
| `tools/make.py` | 跨语言构建编排：CMake → Python build |
| `tests/unit/` | 帧协议、Pipeline、共享内存读写的单元测试 |
| `docs/phase2/` | 实施方案、构建指南、运行调试、验证 |

### 1.2 Phase 2 Out of Scope（**显式不做**）

| 模块 | 推迟到 |
|---|---|
| Helper Service | Phase 3（与 MF 一并引入） |
| Media Foundation Virtual Camera | Phase 3 |
| 多消费端 1:N 帧分发优化（仅基本支持） | Phase 3 |
| Crashpad / OpenTelemetry | Phase 6 |
| AI 美颜/背景替换 | Phase 7+ |
| macOS 任何模块 | Phase 4 |
| NSIS 安装器 | Phase 2 末尾或 Phase 3 初（见 §6） |
| 32 位 DLL | Phase 3（MVP 只做 x64） |
| ARM64 Windows 二进制 | Phase 3 |

### 1.3 与 Phase 1 设计的差异（裁剪说明）

| Phase 1 设计 | Phase 2 MVP | 理由 |
|---|---|---|
| Helper Service 拥有 Frame Bus | Producer 进程（FrameWorker）拥有 Frame Bus | DShow Filter in-proc，不存在 LowBox 沙盒；MVP 阶段不需要 Helper |
| Frame Bus 命名对象带 LowBox ACL | 仍带 LowBox ACL（前向兼容 Phase 3 MF） | 一次到位避免 Phase 3 改 schema |
| 跨进程对象生命周期 = Helper | MVP 期 = FrameWorker；UI 关闭 = 设备无帧（占位帧降级） | I1 不变量在 Phase 3 MF 才完全满足 |
| 双架构 x64+x86 DLL | 仅 x64 | 现代消费端均 x64；x86 留 Phase 3 |

---

## 2. 模块拆解

### 2.1 Native 层（C++17）

```
virtualcam/
├── shared/                          # 跨 OS / 跨 Native 共享头
│   ├── akvc_protocol.h              # 帧 schema、ring 控制块
│   ├── akvc_errors.h                # 错误码
│   └── akvc_version.h               # 版本
└── windows/
    ├── framebus/                    # 共享内存 Ring (Producer/Consumer)
    │   ├── include/akvc/framebus.h
    │   ├── src/framebus.cpp
    │   ├── src/sddl_helper.cpp      # 构造 LowBox 兼容 SDDL
    │   └── CMakeLists.txt
    └── dshow/                       # DShow Source Filter
        ├── include/cvcam_filter.h
        ├── include/cvcam_stream.h
        ├── src/cvcam_filter.cpp     # CSource 子类
        ├── src/cvcam_stream.cpp     # CSourceStream 子类，含 IAMStreamConfig
        ├── src/dll_main.cpp         # DllMain / DllRegisterServer / DllUnregisterServer
        ├── src/registry.cpp         # 注册表项 (CLSID / Filter Categories)
        ├── resources/akvc.def       # 导出函数表
        ├── resources/akvc.rc        # 版本资源
        └── CMakeLists.txt
```

### 2.2 Python 层

```
camera-core/
├── pyproject.toml
└── src/akvc/core/
    ├── __init__.py
    ├── frame.py                     # Frame 数据类
    ├── errors.py                    # AkvcError 家族
    ├── logging.py                   # structlog 装配
    ├── metrics.py                   # 计数器
    ├── frame_provider/
    │   ├── __init__.py
    │   ├── base.py                  # FrameProvider 接口
    │   ├── usb.py                   # OpenCV UsbCameraProvider
    │   └── test_pattern.py          # 内置测试图
    ├── frame_pipeline/
    │   ├── __init__.py
    │   ├── pipeline.py              # FramePipeline / PipelineStage
    │   ├── resize.py
    │   ├── fps_regulator.py
    │   └── color_convert.py         # BGR → NV12
    ├── frame_sink/
    │   ├── __init__.py
    │   ├── base.py
    │   └── windows_shm.py           # 写共享内存 + ACL
    └── config/
        ├── __init__.py
        └── schema.py                # Pydantic 配置模型

apps/desktop/
├── pyproject.toml
└── akvc_app/
    ├── __init__.py
    ├── __main__.py                  # 启动入口
    ├── services/
    │   ├── __init__.py
    │   └── facade.py                # ServiceFacade
    ├── viewmodels/
    │   ├── __init__.py
    │   └── main_vm.py
    ├── views/
    │   ├── __init__.py
    │   └── main_window.py
    └── workers/
        ├── __init__.py
        └── frame_worker.py          # multiprocessing 子进程入口

apps/cli/
├── pyproject.toml
└── akvc_cli/
    ├── __init__.py
    └── __main__.py                  # akvc register / unregister / status
```

### 2.3 工具与测试

```
tools/
└── make.py                          # python tools/make.py {configure|build|register|run|test|clean}

tests/
├── unit/
│   ├── test_frame.py
│   ├── test_pipeline.py
│   └── test_color_convert.py
├── integration/
│   └── test_shm_roundtrip.py
└── perf/
    └── test_publish_latency.py
```

---

## 3. 关键技术决策

### 3.1 Frame Bus

- **位置**：命名共享内存 `Local\akvc-frames-v1`，事件 `Local\akvc-frames-evt`，互斥 `Local\akvc-frames-mtx`。
- **大小**：4 个 1080p NV12 槽位 + 控制块。每槽位 = `1920 * 1080 * 3 / 2` = 3,110,400 字节，4 槽 ≈ 12.4 MB，加控制块 16 MB。
- **协议**：见 `akvc_protocol.h`，每帧头有 magic / version / fourcc / size / pts / seq；尾部再写一次 seq 用于撕裂检测。
- **Producer**：单一（FrameWorker 子进程）。
- **Consumer**：N 个（每个 DShow Filter 实例一个）。
- **同步**：Mutex 保护 ring 写；Event 通知新帧到达；Consumer 用 `WaitForSingleObject(evt, 200ms)`。
- **ACL**：使用 SDDL `D:(A;;GA;;;BA)(A;;GA;;;SY)(A;;GRGW;;;AC)(A;;GRGW;;;S-1-15-2-1)`，前向兼容 Phase 3 MF Frame Server LowBox。

### 3.2 DShow Filter

- **CLSID**：`{8E14549A-DB61-4309-AFA1-3578E927E933}`（虚构，固定）
- **Friendly Name**：`AK Virtual Camera`
- **Vendor**：`AK`
- **Filter Category**：`CLSID_VideoInputDeviceCategory`
- **支持媒体类型**（GetMediaType 顺序）：
  1. NV12 1920×1080@30
  2. NV12 1280×720@30
  3. YUY2 1920×1080@30
  4. YUY2 1280×720@30
  5. RGB24 1280×720@30
- **CSourceStream** 继承 + 实现 `IAMStreamConfig`、`IKsPropertySet`。
- **基类来源**：使用 Windows SDK Samples 的 DirectShow BaseClasses（`baseclasses` 静态库），不引入 GPL 代码；BaseClasses 是 Microsoft 公开授权的样例代码，可商业使用。

### 3.3 桌面应用

- **MVVM 严格分层**（见 Phase 1）。
- **FrameWorker 子进程**：`multiprocessing.spawn`，跨 OS 一致；通过 `multiprocessing.Pipe` 控制，通过共享内存交付帧。
- **预览**：在 UI 主进程从 FrameWorker 得到一份缩略图（16×9 缩到 320×180），不直接读 SHM。
- **打包**：MVP 期不做 PyInstaller 冻结；用 `python -m apps.desktop` 直接跑。
- **Python 版本**：3.12.x。

### 3.4 注册与卸载

MVP 期不内置 Helper，注册/卸载通过：

- `regsvr32 /s akvc-dshow.dll` 注册
- `regsvr32 /u /s akvc-dshow.dll` 卸载
- `akvc register / akvc unregister` 命令包装

`DllRegisterServer` 内部完成：

1. 写入 `HKCR\CLSID\{...}\InprocServer32`（值 = DLL 路径，`ThreadingModel=Both`）
2. 写入 `HKCR\AKVirtualCamera.Filter`（ProgID）
3. 注册到 Filter Category（`IFilterMapper2::RegisterFilter`）
4. 写入 `HKLM\SOFTWARE\AKVC\` 安装路径与版本

`DllUnregisterServer` 严格反向；幂等。

---

## 4. 构建链

### 4.1 工具要求

| 工具 | 版本 | 用途 |
|---|---|---|
| Visual Studio 2022 (Community 即可) | 17.6+ | MSVC v143、Windows SDK 10.0.22621.0+ |
| CMake | 3.25+ | 多目标构建 |
| Python | 3.12.x | 桌面应用与构建脚本 |
| Git | 任意 | 拉取依赖（DShow BaseClasses）|

### 4.2 第三方依赖

| 名称 | 来源 | 用途 |
|---|---|---|
| DirectShow BaseClasses | Windows-classic-samples (Microsoft, MIT-style) | DShow Filter 基类 |
| OpenCV-Python (headless) | PyPI | USB 采集 + 色彩转换 |
| NumPy | PyPI | 帧数据 |
| PySide6 (LGPL) | PyPI | 桌面 UI |
| structlog | PyPI | 日志 |
| pydantic v2 | PyPI | 配置 |
| pytest, pytest-qt | PyPI | 测试 |

DShow BaseClasses 通过 git submodule 或脚本拉取到 `third_party/baseclasses/`。

### 4.3 单一构建入口

`tools/make.py` 提供：

```
python tools/make.py configure   # 生成 build/ 与 venv
python tools/make.py build       # 构建 Native + Python
python tools/make.py register    # regsvr32 注册 DLL
python tools/make.py unregister  # 卸载
python tools/make.py run         # 启动 PySide6 桌面应用
python tools/make.py test        # pytest
python tools/make.py clean       # 清理
```

---

## 5. 路径约束（Phase 1 不变量复核）

| 不变量 | Phase 2 满足度 | 说明 |
|---|---|---|
| I1 — UI 崩溃设备不消失 | 部分 | MVP 期 FrameWorker 与 UI 同生命周期；UI 关闭 → DShow Filter 读不到帧 → 输出占位帧 |
| I2 — 安装/卸载干净 | 满足 | DllRegister/Unregister 严格对偶 |
| I3 — 故障不抖动 | 满足 | DShow Filter 在 SHM 读取失败时输出占位帧 |
| I4 — 跨进程对象由可信进程拥有 | 部分 | MVP 期 FrameWorker（用户态 UI 子进程）；Phase 3 移交 Helper |
| I5 — MVVM 边界 | 满足 | apps/desktop 严格分层 |

---

## 6. NSIS 安装器策略

Phase 2 **不交付 NSIS 安装器**，仅交付：

- 单 DLL `akvc-dshow.dll`
- `akvc register/unregister` CLI
- 开发者使用 `regsvr32` 直接注册（含管理员提权说明）

理由：Phase 2 目标是**通路验证**，工程化打包在 Phase 3 与 MF 一并解决，避免重复修改 NSIS 脚本。

---

## 7. 风险与回滚（本阶段维度）

| 风险 | 触发 | 回滚 |
|---|---|---|
| BaseClasses 编译不通过 | 新 Windows SDK 改了头文件 | 用历史版本快照 + 在我们的 fork 中 patch |
| 共享内存 ACL 错误致 DShow Filter 读不到 | 在游戏/反作弊环境下 | 暂时退化到 admin-only ACL，并在文档标注 |
| OpenCV cv2.VideoCapture 超时 | 部分 USB 摄像头驱动慢 | 切到 MSMF backend `cv2.CAP_MSMF` |
| Python 3.12 与 PySide6 兼容 | 新版 PySide6 bug | 锁版本 PySide6 6.6.x |

---

## 8. 验收节点（Phase 2 出口）

按"先编译可见、再消费端拉流"的顺序：

1. **构建**：`python tools/make.py build` 全成功，产物 `build/Release/akvc-dshow.dll`。
2. **注册**：`python tools/make.py register` 成功；设备管理器/`graphedt.exe` 中可见 `AK Virtual Camera`。
3. **CLI 自检**：`akvc status` 返回设备已注册、CLSID/路径正确。
4. **UI 闭环**：启动 `python -m akvc_app`，选择 USB Camera 0，点击 Start，UI 显示预览帧率与状态正常。
5. **OBS 拉流**：OBS Studio 添加 `Video Capture Device`，源选 `AK Virtual Camera`，画面同步。
6. **Zoom 拉流**：Zoom 设置 → 视频 → 摄像头选 `AK Virtual Camera`，预览正常。
7. **Chrome 拉流**：`https://webrtc.github.io/samples/src/content/devices/input-output/`，选 `AK Virtual Camera`，预览正常。
8. **卸载**：`python tools/make.py unregister`，设备管理器中消失，注册表无残留（用 `akvc-doctor verify-clean`，本阶段简版）。

**Teams 与新版 Skype 不在 Phase 2 验收清单**（已切 MF，DShow 不可见 — Phase 3 覆盖）。

→ 接下来按目录逐文件交付完整代码与脚本。
