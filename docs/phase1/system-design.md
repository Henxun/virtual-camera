# System Design — Cross-Platform Virtual Camera

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 1 — 系统架构设计
**日期**：2026-06-19
**前置文档**：`../phase0/architecture-research.md`、`../phase0/technology-selection.md`、`../phase0/risk-analysis.md`

> 本文给出系统的**总体架构、模块划分、数据流、扩展点、目录结构**。
> 类图见 `class-diagram.md`，时序图见 `sequence-diagram.md`，组件图见 `component-diagram.md`。
> 本阶段不写代码。

---

## 1. 设计目标与不变量

### 1.1 设计目标

1. 一份桌面应用、两个原生平台层、一套统一抽象——能力对等、命名一致、可独立演进。
2. 用户态、单 Producer / 多 Consumer、零拷贝优先。
3. 帧路径与 UI 路径**进程隔离**，避免 GIL/UI 卡顿互相传染。
4. 平台层可被替换：Windows 在 DShow / MF 间切换、macOS 只做 Camera Extension，但抽象层无需改动。
5. 商业级可观测性：结构化日志、指标、崩溃报告、自检（`akvc-doctor`）。

### 1.2 系统不变量（Invariants）

- **不变量 I1**：UI 进程崩溃，虚拟摄像头不消失；Helper 仍向消费端递交"最近一帧/占位帧"。
- **不变量 I2**：升级/降级安装永远从干净状态开始；卸载后系统不残留任何 CLSID / 注册表 / launchd plist / 系统扩展。
- **不变量 I3**：帧路径任意一点失败不会回滚到上一帧（避免视觉抖动），改为转入"占位帧"模式。
- **不变量 I4**：所有跨进程对象（共享内存、Mutex、IOSurface）的生命周期由 Helper 拥有，Producer/Consumer 仅持有引用。
- **不变量 I5**：MVVM 三层之间只通过 ViewModel 暴露的 Qt Property / Signal 通信，禁止 View 直接调用 Service。

### 1.3 非目标（重申）

- 不做 Linux v4l2loopback；不做内核态驱动；不做 macOS DAL Plug-In；不做 32 位平台。
- 不做云分发；不做帧加密（视频会议端到端加密由消费端负责）。

---

## 2. 总体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Layer 5 — Presentation                          │
│   PySide6 桌面应用：View（Widgets/QML）⇄ ViewModel ⇄ ServiceFacade   │
└──────────────────────────────────────────────────────────────────────┘
                               │  in-proc Python API
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Layer 4 — Application Service                   │
│   ServiceFacade · Orchestrator · Config · Telemetry · CrashHandler   │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Layer 3 — Camera Core (Python)                  │
│   FrameProvider · FramePipeline · FrameSink (IPC writer)             │
│   AI Hooks · Effects · Metrics                                       │
└──────────────────────────────────────────────────────────────────────┘
                               │  Shared Memory Ring / IOSurface ring
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Layer 2 — Platform Abstraction (C ABI)          │
│   IVirtualCamera · IFrameBus · IRegistrar · IHelperClient            │
│   (跨平台 C 头文件，Python 通过 ctypes/cffi 绑定)                    │
└──────────────────────────────────────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
┌──────────────────────────┐      ┌────────────────────────────────────┐
│  Layer 1 — Win Native     │      │  Layer 1 — macOS Native            │
│  · DShow Source Filter    │      │  · CMIO Camera Extension           │
│  · MF Media Source        │      │  · Helper (launchd)                │
│  · Helper Service (svc)   │      │  · IOSurface bridge                │
│  · Frame Bus shm + ring   │      │  · XPC service                     │
└──────────────────────────┘      └────────────────────────────────────┘
              │                                 │
              ▼                                 ▼
┌──────────────────────────┐      ┌────────────────────────────────────┐
│  Layer 0 — OS Capture     │      │  Layer 0 — OS Capture              │
│  DirectShow / MF Frame    │      │  CoreMediaIO / coremediaiod        │
│  Server                   │      │                                    │
└──────────────────────────┘      └────────────────────────────────────┘
```

**分层契约**：

- 上层只通过下层接口调用；下层不感知上层。
- 跨语言边界（Python ↔ Native）只发生在 Layer 2/3 之间，且数据走共享内存，不走函数参数。
- Layer 1 之间彼此不可见（Win Native 不依赖 macOS Native）。

---

## 3. 进程模型

### 3.1 Windows 进程模型

```
┌──────────────────┐            ┌──────────────────────┐
│  UI App (.exe)   │            │ Helper Service (.exe)│
│  PySide6         │            │  akvc-helper.exe     │
│  ├ View          │            │  · 单例              │
│  ├ ViewModel     │  ─named─▶  │  · 持有 Frame Bus   │
│  ├ FrameWorker   │  pipe      │  · 持有 MF 注册     │
│  │  (子进程)     │            │  · 自启动           │
│  └ Service       │            └─────┬────────────────┘
└─────┬────────────┘                  │
      │ shared memory                 │ shared memory
      ▼                               ▼
┌────────────────────────────────────────────────────────┐
│         Frame Bus (Named Shared Memory + Ring × 4)     │
│         Local\akvc-frames-v1                           │
│         Mutex: Local\akvc-frames-mtx                   │
│         Event: Local\akvc-frames-evt                   │
└────────────────────────────────────────────────────────┘
        ▲                                ▲
        │ in-proc COM                    │ frameserver loads DLL
┌──────────────────────────┐  ┌────────────────────────────┐
│ DShow consumer process   │  │ frameserver.exe (system)   │
│ (OBS / Zoom / 微信)      │  │  · MF Media Source DLL     │
│  Source Filter DLL 加载  │  │  · LowBox AppContainer     │
└──────────────────────────┘  └─────────┬──────────────────┘
                                        │
                                        ▼
                              ┌────────────────────────────┐
                              │ MF consumer process        │
                              │ (Teams / Chrome / 新 Skype)│
                              └────────────────────────────┘
```

**关键点**：
- UI App 可关闭；Helper 仍持有 Frame Bus 与 MF 注册，消费端继续看到设备（占位帧）。
- DShow 路径：Source Filter DLL 加载到消费端进程，**直接读 Frame Bus**。
- MF 路径：Media Source DLL 加载到 frameserver，**也读 Frame Bus**——共用同一份共享内存设计是关键。
- FrameWorker 是 UI App 的子进程，专跑视频处理，避免 GIL 阻塞 UI。

### 3.2 macOS 进程模型

```
┌──────────────────┐            ┌──────────────────────┐
│  UI App (.app)   │            │ Helper (launchd)     │
│  PySide6         │            │ akvc-helperd         │
│  ├ FrameWorker   │  ─XPC──▶   │ · 单例               │
│  └ Service       │            │ · 持有 IOSurface 池  │
└─────┬────────────┘            └─────┬────────────────┘
      │ XPC + IOSurface pool          │ XPC
      ▼                               ▼
┌────────────────────────────────────────────────────────┐
│         IOSurface Ring × 4（零拷贝纹理/平面）          │
│         App Group: group.com.akvc.shared               │
└────────────────────────────────────────────────────────┘
                       ▲
                       │ XPC (CMIO 客户端 API)
                       │
┌──────────────────────────────────────────────────┐
│ AKVirtualCamera.systemextension (system process) │
│ · CMIOExtensionProviderSource                    │
│ · CMIOExtensionDeviceSource                      │
│ · CMIOExtensionStreamSource                      │
└──────────────────────────────────────────────────┘
                       ▲
                       │ CoreMediaIO 客户端
                       │
┌──────────────────────────────────────────────────┐
│ Consumer 进程 (FaceTime / Zoom / OBS / Safari)   │
└──────────────────────────────────────────────────┘
```

---

## 4. 模块划分

### 4.1 顶层模块（与目录一一对应）

| 模块 | 责任 | 语言 | Owner 子团队 |
|---|---|---|---|
| `apps/desktop` | 桌面应用 (View + ViewModel + ServiceFacade) | Python (PySide6) | 应用组 |
| `apps/cli` | 命令行：注册/卸载/自检 (`akvc`, `akvc-doctor`) | Python | 应用组 |
| `camera-core` | FrameProvider / FramePipeline / FrameSink / Effects | Python | 媒体组 |
| `platform-abi` | 跨平台 C ABI 头文件 + Python 绑定 | C/C++ + Python (cffi) | 架构组 |
| `virtualcam/windows/dshow` | DShow Source Filter | C++17 | Windows 原生组 |
| `virtualcam/windows/mf` | MF Virtual Camera Media Source | C++17/20 | Windows 原生组 |
| `virtualcam/windows/helper` | Helper Service (akvc-helper.exe) | C++17 | Windows 原生组 |
| `virtualcam/windows/framebus` | 共享内存 Ring 实现（Win） | C++17 | Windows 原生组 |
| `virtualcam/macos/extension` | CMIO Camera Extension | Swift + Obj-C++ | macOS 原生组 |
| `virtualcam/macos/helper` | Helper (akvc-helperd) | Swift | macOS 原生组 |
| `virtualcam/macos/framebus` | IOSurface Ring + XPC | Swift | macOS 原生组 |
| `virtualcam/shared` | 帧协议头、错误码、版本号 | C 头文件 | 架构组 |
| `installer/windows` | NSIS 脚本 + 子组件签名 | NSIS | 发布工程 |
| `installer/macos` | pkgbuild + productbuild + 公证 | shell | 发布工程 |
| `tests` | 单元 / 集成 / E2E / 性能 | Python + 平台脚本 | 质量组 |
| `tools` | `make.py`、签名、矩阵测试、性能基线 | Python | 工具组 |
| `docs` | 设计、运维、用户、合规 | Markdown | 全员 |

### 4.2 `camera-core` 子模块

| 子模块 | 责任 |
|---|---|
| `frame_provider/` | 抽象 + USB / VideoFile / ImageSequence / TestPattern 实现 |
| `frame_pipeline/` | 滤镜链：Resize / FpsRegulator / ColorConvert / Watermark / EffectStage |
| `frame_sink/` | 把 NV12 帧写入 Frame Bus（Windows shm / macOS IOSurface） |
| `effects/` | 美颜、背景替换、滤镜（AI 通过 Hook 注入） |
| `ai/` | ONNX Runtime / MediaPipe wrapper（接口预留，Phase 6+ 落地） |
| `config/` | 用户配置、设备配置、Profile 管理（Pydantic） |
| `telemetry/` | OpenTelemetry exporter，opt-in |
| `metrics/` | FPS / latency / dropped / cpu / gpu 计数器 |
| `errors/` | 统一错误码、异常类、可恢复策略 |

### 4.3 `apps/desktop` 子模块（MVVM）

```
apps/desktop/
├── views/            # QWidget / QML，纯展示
├── viewmodels/       # Qt Property + Signal/Slot，无业务逻辑
├── services/         # ServiceFacade、Orchestrator、IPC 封装
├── workers/          # FrameWorker（multiprocessing 子进程入口）
├── i18n/             # zh_CN / en_US Qt linguist 资源
├── resources/        # 图标、QSS、QML
└── __main__.py       # 应用入口
```

---

## 5. 数据流（Frame Path）

### 5.1 帧的生命周期

```
[Source]
  USB Camera (cv2.VideoCapture / MF / AVFoundation)
        │
        ▼ NumPy ndarray BGR / NV12 (取决于 source backend)
[Provider]
  FrameProvider.read() ─► Frame{ndarray, pts, seq, meta}
        │
        ▼
[Pipeline]
  ResizeStage      ─► 1920×1080 / 1280×720
  FpsRegulator     ─► 严格 30fps，多余帧丢弃
  ColorConvertStage─► BGR → NV12（libyuv / OpenCV）
  EffectStage(s)   ─► 美颜 / 背景替换 / 水印（可选）
        │
        ▼ Frame{NV12 planes, pts, seq, fourcc='NV12'}
[Sink]
  FrameSink.publish(frame)
   ├─ 申请 ring slot（atomic 比较交换 producer index）
   ├─ memcpy 到共享内存（或 IOSurface lock + copy）
   ├─ 写入 FrameHeader（magic, version, w, h, fourcc, stride, pts, seq, flags）
   └─ Set Event / signal semaphore
        │
        ▼
[Frame Bus] —— 共享内存 Ring × 4
        │
        ├──► [DShow Source Filter] ─► CSourceStream::FillBuffer ─► consumer
        ├──► [MF Media Source]      ─► IMFMediaStream::RequestSample ─► frameserver ─► consumer
        └──► [CMIO Extension]       ─► CMIOExtensionStreamSource.send ─► consumer
```

### 5.2 帧时间戳与节流

- 使用 `QueryPerformanceCounter`（Win） / `mach_absolute_time`（mac）→ 100ns 单位 PTS。
- FpsRegulator 使用 token bucket，目标 30fps，window=1s，允许 ±10% 抖动。
- 每帧带递增 `seq`；消费端用 `seq` 检测丢帧/重复。

### 5.3 Frame Bus Ring

```
SharedMemory Region (≈ 16 MB for 4× 1080p NV12)

┌──────────────────────────┐
│ ControlBlock (cacheline) │
│   uint64 producer_idx    │
│   uint64 consumer_count  │
│   uint64 writer_pid      │
│   uint64 schema_version  │
├──────────────────────────┤
│ Slot 0  Header + Planes  │
├──────────────────────────┤
│ Slot 1  Header + Planes  │
├──────────────────────────┤
│ Slot 2  Header + Planes  │
├──────────────────────────┤
│ Slot 3  Header + Planes  │
└──────────────────────────┘
```

- Producer 写法：原子 `++producer_idx` → 写 slot[idx % 4] → SetEvent。
- Consumer 读法：WaitForSingleObject(event) → 读 producer_idx → 读 slot[(idx-1) % 4]。
- 撕裂保护：每个 slot 头尾各放一个 `seq`，消费端读完比较，不一致则丢弃。
- ABA 保护：`producer_idx` 单调递增 64-bit，永不复用。

---

## 6. 控制面（Control Plane）

### 6.1 控制通道

| 平台 | 通道 | 协议 |
|---|---|---|
| Windows | 命名管道 `\\.\pipe\akvc-ctrl-v1` | length-prefixed JSON-RPC 2.0 |
| macOS | XPC service `com.akvc.helper` | NSXPC + Codable Swift struct |

### 6.2 控制命令清单

| 命令 | 由谁发起 | 接收方 | 作用 |
|---|---|---|---|
| `helper.ping` | Any | Helper | 健康检查 |
| `helper.status` | UI / CLI | Helper | 设备启用状态、注册状态、版本 |
| `helper.start_device` | UI / CLI | Helper | 创建/激活虚拟摄像头（MF Activate / Extension Start） |
| `helper.stop_device` | UI / CLI | Helper | 注销 |
| `helper.set_format` | UI | Helper | 切换输出分辨率/帧率/像素格式 |
| `helper.attach_producer` | UI | Helper | 注册 Producer（PID + Frame Bus name） |
| `helper.detach_producer` | UI | Helper | 注销 Producer，切到占位帧 |
| `helper.metrics` | UI / CLI | Helper | 帧率、丢帧、消费端连接数 |
| `helper.log_tail` | CLI | Helper | 取最近 N 行日志（用于 doctor） |
| `helper.upgrade_drain` | Installer | Helper | 升级前停帧、解除 MF 注册、退出 |

### 6.3 控制面错误模型

- 所有响应携带 `code`（统一错误码）+ `message` + `details`。
- 错误码命名空间：`E_AKVC_<DOMAIN>_<NAME>`，例：`E_AKVC_REG_MF_ACTIVATE_FAILED`。
- 错误码与 HRESULT / OSStatus 在 `virtualcam/shared/errors.h` 维护双向映射。

---

## 7. 配置管理

### 7.1 层次

```
Defaults (内置)
   ↓ overridden by
System Config  (Win: %ProgramData%\AKVC\config.toml; mac: /Library/Application Support/AKVC/)
   ↓ overridden by
User Config    (Win: %APPDATA%\AKVC\config.toml; mac: ~/Library/Application Support/AKVC/)
   ↓ overridden by
Runtime Override (CLI 参数 / UI 临时切换)
```

### 7.2 关键字段（节选）

```
[device]
name = "AK Virtual Camera"
vendor = "AK"
default_format = "NV12"
default_resolution = "1920x1080"
default_fps = 30

[pipeline]
fps_regulator = "token_bucket"
fps_jitter_pct = 10
color_space = "bt709_limited"

[helper]
auto_start = true
keepalive = true

[telemetry]
enabled = false  # opt-in
endpoint = ""

[ai]
backend = "onnxruntime"
providers = ["DmlExecutionProvider", "CPUExecutionProvider"]  # mac: ["CoreMLExecutionProvider"]

[logging]
level = "INFO"
sink = ["file", "eventlog"]   # mac: ["file", "oslog"]
```

### 7.3 配置 Schema 校验

- 使用 Pydantic v2 模型，启动期严格校验；非法配置 → 退化到默认 + 警告。
- 提供 `akvc config validate` 命令；CI 中跑配置文件全集校验。

---

## 8. 日志、指标、崩溃

### 8.1 日志

- 库：`structlog` + Qt logging handler。
- 格式：JSON Lines，带 `ts / level / module / pid / tid / msg / kv`。
- Sink：Windows `%ProgramData%\AKVC\logs\` + Windows EventLog（Helper Service）；macOS `~/Library/Logs/AKVC/` + `os_log`。
- 级别策略：Release 默认 INFO，可由 UI 切到 DEBUG（最多 7 天自动回退）。

### 8.2 指标

- 库：`opentelemetry-api/sdk` + Prometheus exporter（可选）。
- 关键指标：`akvc.fps`, `akvc.frame_drop_rate`, `akvc.frame_latency_ms`, `akvc.consumer_count`, `akvc.cpu_pct`, `akvc.gpu_pct`。
- 采样：每秒 1 次；本地保留 24 小时滚动窗口。

### 8.3 崩溃

- 库：Crashpad（Native）+ Python `faulthandler` + `sys.excepthook`。
- 崩溃产物：minidump + 上下文 JSON，保存到日志目录；opt-in 上传。
- Helper 崩溃恢复：服务恢复策略 `restart/restart/restart`（Win SCM）；launchd `KeepAlive=true`。

---

## 9. 安全设计

### 9.1 进程边界与信任

| 域 | 信任级别 | 说明 |
|---|---|---|
| UI App | 低 | 用户态，可被关闭 |
| FrameWorker | 中 | UI 子进程 |
| Helper | 高 | 服务/守护，单例，控制注册 |
| Frame Bus | 中 | 共享内存，ACL 限制 |
| DShow Filter | 低 | 加载到任意消费端 |
| MF Media Source | 中 | 加载到 frameserver LowBox |
| Camera Extension | 高 | 系统扩展，受 SIP 保护 |

### 9.2 ACL / Sandbox 关键约束

- **Frame Bus 命名对象**：SDDL `D:(A;;GA;;;BA)(A;;GRGW;;;AC)(A;;GRGW;;;S-1-15-2-1)`（管理员全权 + AppContainer/ALL_APP_PACKAGES 读写）。
- **macOS App Group**：`group.com.akvc.shared` 用于 IOSurface 注册表共享。
- **Helper**：Windows 用 LocalSystem 账户运行，但操作 Frame Bus 时降权创建对象（带正确 ACL）。

### 9.3 防御性原则

- Frame Bus 内不存放任何用户视频内容之外的数据；不写入 PII；不写入设备唯一标识。
- 控制面 JSON-RPC 只接受本机连接（命名管道默认本机；XPC 默认本机）。
- 命令白名单：Helper 不接受任意 RPC，只接受 §6.2 清单内命令。

---

## 10. 平台抽象层（Layer 2）

### 10.1 抽象接口（C ABI 视角）

```
// virtualcam/shared/akvc_abi.h
typedef struct akvc_frame_header {
  uint32_t magic;       // 'AKVC'
  uint32_t version;
  uint32_t width;
  uint32_t height;
  uint32_t fourcc;
  uint32_t stride[2];
  uint64_t pts_100ns;
  uint64_t seq;
  uint32_t flags;
  uint32_t reserved;
} akvc_frame_header_t;

typedef struct akvc_format {
  uint32_t fourcc;
  uint32_t width;
  uint32_t height;
  uint32_t fps_num;
  uint32_t fps_den;
} akvc_format_t;

// 平台层 API（每个平台一个实现）
akvc_status_t akvc_helper_attach(const char* producer_name);
akvc_status_t akvc_helper_publish(const akvc_frame_header_t* hdr, const uint8_t* planes[2]);
akvc_status_t akvc_helper_set_format(const akvc_format_t* fmt);
akvc_status_t akvc_helper_detach(void);
akvc_status_t akvc_helper_query_consumers(uint32_t* out_count);
```

### 10.2 Python 绑定

- 使用 `cffi`（ABI mode）加载 `akvc_helper_client.dll` / `libakvc_helper_client.dylib`。
- 帧路径热路径**不走 cffi**，直接用 Python 的 `multiprocessing.shared_memory` 操作内存（与 Native 端对齐 schema）。
- cffi 仅用于控制面命令。

---

## 11. 扩展点

### 11.1 扩展点清单

| 扩展点 | 接口 | 注入方式 |
|---|---|---|
| 帧源 | `FrameProvider` | entry_point / 配置开关 |
| 处理阶段 | `PipelineStage` | 列表配置 + 工厂 |
| AI 模型 | `AiTask`（face_detect / segmentation / pose / restyle） | ONNX/MediaPipe 后端切换 |
| 平台层 | `IVirtualCamera`（C ABI） | 编译期选择 |
| UI 主题 | `theme.qss` / `theme.qml` | 用户配置 |
| 国际化 | Qt linguist `.ts/.qm` | 资源加载 |

### 11.2 命名约定

- Python 包：`akvc.*`（root），`akvc.core.*`、`akvc.app.*`、`akvc.platform.*`。
- C 符号：`akvc_*` 前缀，平台后缀 `_win / _mac`。
- 错误码：`E_AKVC_*`。
- 日志事件：`akvc.<domain>.<verb>`。

### 11.3 SDK 化路径（长期）

将 `camera-core` + `platform-abi` 抽离为 `akvc-sdk`，第三方 Python/C++ 应用可嵌入。
**Phase 1 不实现**，但目录与命名为此预留。

---

## 12. 升级与卸载

### 12.1 升级流程

```
新安装器启动
  │
  ▼
Stop UI App（如运行）
  │
  ▼
helper.upgrade_drain → Helper 停止帧、注销 MF VirtualCamera、退出
  │
  ▼
卸载旧 Helper Service / 旧 .systemextension
  │
  ▼
注册表 / launchd plist 清理（残留检测）
  │
  ▼
安装新文件 + 注册
  │
  ▼
启动新 Helper → 注册 MF VirtualCamera / 请求新 SystemExtension 替换
```

### 12.2 卸载流程

- 调 `helper.upgrade_drain` → 卸载 Helper → DllUnregisterServer（DShow） → MF Activate Shutdown → 清注册表。
- macOS：`OSSystemExtensionRequest.deactivate` → 删除 launchd plist → 删除 App Bundle。
- 卸载后跑 `akvc-doctor verify-clean`：返回 0 即"系统已干净"。

---

## 13. 性能预算

| 指标 | 720p30 | 1080p30 |
|---|---|---|
| 端到端延迟（采集→消费端） | ≤ 80ms | ≤ 100ms |
| Producer CPU（含 OpenCV 处理，无 AI） | ≤ 6% | ≤ 12% |
| Consumer 端额外 CPU | ≤ 1% | ≤ 2% |
| 总 CPU 占用（Producer + Helper + Consumer） | < 10% | < 20% |
| 内存（Helper + UI 常驻） | < 200 MB | < 250 MB |
| 帧丢弃率（30 分钟稳态） | < 0.1% | < 0.2% |
| 启动到首帧 | < 1.5s | < 2.0s |

性能预算违反 = 阻断性 bug，CI 必须卡门禁。

---

## 14. 目录结构（最终）

```
virtual-camera/
├── apps/
│   ├── desktop/                       # PySide6 桌面应用
│   │   ├── akvc_app/
│   │   │   ├── views/
│   │   │   ├── viewmodels/
│   │   │   ├── services/
│   │   │   ├── workers/
│   │   │   ├── i18n/
│   │   │   ├── resources/
│   │   │   └── __main__.py
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── cli/                           # akvc / akvc-doctor
│       ├── akvc_cli/
│       └── pyproject.toml
│
├── camera-core/                       # 帧路径核心 (Python)
│   ├── src/akvc/core/
│   │   ├── frame_provider/
│   │   ├── frame_pipeline/
│   │   ├── frame_sink/
│   │   ├── effects/
│   │   ├── ai/
│   │   ├── config/
│   │   ├── telemetry/
│   │   ├── metrics/
│   │   └── errors/
│   ├── tests/
│   └── pyproject.toml
│
├── platform-abi/                      # 跨平台 C ABI + Python 绑定
│   ├── include/akvc/
│   │   ├── akvc_abi.h
│   │   ├── akvc_errors.h
│   │   └── akvc_frame.h
│   ├── python/akvc/platform/
│   └── README.md
│
├── virtualcam/
│   ├── shared/                        # 跨 OS 共享 (C 头文件 / 协议)
│   │   ├── akvc_protocol.h
│   │   └── akvc_version.h
│   ├── windows/
│   │   ├── dshow/                     # DirectShow Source Filter
│   │   │   ├── src/
│   │   │   ├── include/
│   │   │   ├── resources/
│   │   │   └── CMakeLists.txt
│   │   ├── mf/                        # Media Foundation Virtual Camera
│   │   │   ├── src/
│   │   │   ├── include/
│   │   │   └── CMakeLists.txt
│   │   ├── helper/                    # akvc-helper.exe (Windows Service)
│   │   │   ├── src/
│   │   │   └── CMakeLists.txt
│   │   ├── framebus/                  # 共享内存 Ring 实现
│   │   │   ├── src/
│   │   │   └── CMakeLists.txt
│   │   └── CMakeLists.txt
│   └── macos/
│       ├── extension/                 # CMIO Camera Extension (Swift)
│       │   ├── Sources/
│       │   ├── Resources/
│       │   ├── Info.plist
│       │   └── Package.swift
│       ├── helper/                    # akvc-helperd (launchd)
│       │   ├── Sources/
│       │   └── Package.swift
│       ├── framebus/                  # IOSurface Ring + XPC
│       │   ├── Sources/
│       │   └── Package.swift
│       └── AKVirtualCamera.xcworkspace/
│
├── installer/
│   ├── windows/                       # NSIS
│   │   ├── akvc.nsi
│   │   ├── ui/
│   │   ├── scripts/
│   │   └── sign/
│   └── macos/                         # PKG
│       ├── Distribution.xml
│       ├── scripts/
│       │   ├── preinstall
│       │   └── postinstall
│       └── notarize.sh
│
├── tests/
│   ├── unit/                          # pytest 单元测试
│   ├── integration/                   # 跨模块集成
│   ├── e2e/                           # OBS / Zoom / Chrome 自动化
│   ├── perf/                          # 性能基线
│   └── matrix/                        # OS / 架构矩阵
│
├── tools/
│   ├── make.py                        # 统一构建/打包入口
│   ├── sign.py                        # 签名/公证
│   ├── matrix_run.py                  # 跨 OS 矩阵跑测
│   ├── doctor/                        # akvc-doctor 实现
│   └── ci/
│       ├── windows.yml
│       └── macos.yml
│
├── docs/
│   ├── phase0/
│   │   ├── architecture-research.md
│   │   ├── technology-selection.md
│   │   └── risk-analysis.md
│   ├── phase1/
│   │   ├── system-design.md
│   │   ├── class-diagram.md
│   │   ├── sequence-diagram.md
│   │   └── component-diagram.md
│   ├── operations/                    # 运维文档
│   ├── user/                          # 用户手册
│   └── compliance/                    # 合规/许可证/SBOM
│
├── .github/workflows/
│   ├── windows.yml
│   ├── macos.yml
│   └── lint.yml
│
├── pyproject.toml                     # workspace root
├── CMakeLists.txt                     # workspace root for native
├── LICENSE                            # Apache-2.0
├── NOTICE
├── SECURITY.md
├── CONTRIBUTING.md
└── README.md
```

**结构准则**：

- `apps/` = 可执行入口（用户面）。
- `camera-core/` = 纯 Python 库，可被任何 app 复用。
- `platform-abi/` = 跨语言、跨平台契约面。
- `virtualcam/` = OS 原生实现，按 OS 严格分隔。
- `installer/` / `tools/` / `tests/` / `docs/` = 工程支持面。
- 每个子项目独立可构建（`pyproject.toml` 或 `CMakeLists.txt`），workspace 顶层只做编排。

---

## 15. 与 Phase 0 一致性核对

- ✅ Windows 双栈 DShow + MF：`virtualcam/windows/{dshow, mf}` 双子模块体现。
- ✅ macOS 仅 Camera Extension：`virtualcam/macos/extension/`，无 DAL。
- ✅ NV12 主推：`frame_pipeline/color_convert` 默认输出 NV12。
- ✅ Helper 单例 + Frame Bus：`virtualcam/{windows,macos}/helper` + `framebus`。
- ✅ EV / Developer ID 签名链：`installer/*/sign`、`tools/sign.py`。
- ✅ 风险 R-03 ACL：`§9.2` 显式约束。
- ✅ 风险 R-08 性能预算：`§13` 显式约束 + CI 门禁。
- ✅ 风险 R-11 升级残留：`§12` 升级流程明文。

---

## 16. 本阶段不做（Out of Scope）

- 不写任何 .py / .cpp / .swift。
- 不创建空目录骨架（避免 Phase 2 重复）。
- 不固化 CMake / pyproject 文件内容（Phase 2 一并落）。

下一文档：`class-diagram.md` — 类图。
