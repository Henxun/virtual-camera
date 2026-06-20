# Sequence Diagram — Cross-Platform Virtual Camera

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 1 — 系统架构设计
**前置文档**：`system-design.md`、`class-diagram.md`

> 本文给出系统在关键路径上的时序图，覆盖：开机/首启、注册、推帧、消费端打开（DShow/MF/CMIO）、错误恢复、升级、卸载、跨平台对照。
> 所有时序均为目标实现，作为 Phase 2/3/4 的契约。

---

## 1. 首次安装 → 启动 → 设备就绪（Windows）

```mermaid
sequenceDiagram
    actor User
    participant Inst as Installer (NSIS)
    participant SCM as Windows SCM
    participant Helper as akvc-helper.exe
    participant FB as Frame Bus (shm)
    participant Reg as Registrar
    participant DShow as DShow .dll (registered)
    participant FS as frameserver.exe
    participant MFDLL as MF Media Source .dll

    User->>Inst: 双击 akvc-setup.exe
    Inst->>Inst: 校验 EV 签名 / 提权
    Inst->>SCM: sc create akvc-helper start=auto
    Inst->>Reg: regsvr32 /s akvc-dshow.dll (x64+x86)
    Inst->>Inst: 复制 MF DLL 到 ProgramFiles
    Inst-->>User: 安装完成 / 启动 Helper
    SCM->>Helper: ServiceMain
    Helper->>FB: CreateFileMapping + ACL(ALL_APP_PACKAGES)
    Helper->>FB: CreateEvent / CreateMutex (with ACL)
    Helper->>Reg: MFCreateVirtualCamera + Start
    Reg->>FS: 系统通知 frameserver 加载 MF DLL
    FS->>MFDLL: LoadLibrary + 实例化 MediaSource
    MFDLL->>FB: OpenFileMapping (LowBox 兼容 ACL)
    Helper-->>SCM: SERVICE_RUNNING
    Helper->>Helper: NamedPipe listen (\\.\pipe\akvc-ctrl-v1)
    Note over Helper,FB: 设备已注册<br/>消费端枚举即可看到 AK Virtual Camera
```

---

## 2. 首次安装 → 启动 → 设备就绪（macOS）

```mermaid
sequenceDiagram
    actor User
    participant Inst as Installer (PKG)
    participant App as AKVC.app
    participant SE as systemextensionsd
    participant Helper as akvc-helperd (launchd)
    participant Ext as AKVC.systemextension
    participant CMIO as coremediaiod

    User->>Inst: 双击 AKVC.pkg
    Inst->>Inst: 公证校验 / 提权
    Inst->>App: 复制到 /Applications
    Inst->>Helper: 安装 launchd plist 并 launchctl bootstrap
    Inst-->>User: 安装完成 / 引导首启
    User->>App: 启动 AKVC.app
    App->>SE: OSSystemExtensionRequest.activate(AKVC.systemextension)
    SE-->>User: "系统扩展被阻止"提示
    User->>User: 前往 设置 → 隐私与安全性 → 启用
    SE->>Ext: 加载 .systemextension 进程
    Ext->>CMIO: 注册 CMIOExtensionProvider/Device/Stream
    Helper->>Helper: 启动 XPC listener (com.akvc.helper)
    Ext->>Helper: NSXPCConnection 建立
    Helper-->>Ext: 共享 IOSurface 池
    Note over Helper,Ext: 设备已注册<br/>FaceTime/Zoom/Safari 即可看到 AK Virtual Camera
```

---

## 3. UI 启动 → 选择源 → 开始推流（跨平台共通）

```mermaid
sequenceDiagram
    actor User
    participant View as PySide6 View
    participant VM as MainViewModel
    participant SF as ServiceFacade
    participant DC as DeviceController
    participant FW as FrameWorker (子进程)
    participant FP as FrameProvider (USB)
    participant PIPE as FramePipeline
    participant SINK as FrameSink
    participant FB as Frame Bus
    participant HC as HelperClient
    participant H as Helper

    User->>View: 启动 AKVC.app
    View->>VM: bind()
    VM->>SF: bootstrap()
    SF->>HC: connect()
    HC->>H: helper.ping
    H-->>HC: ok / version
    SF->>SF: load_config()
    SF-->>VM: ready
    User->>View: 选择 "USB Camera 0"
    View->>VM: select_source(id)
    VM->>SF: select_source(id)
    SF->>DC: select(id)
    DC->>FW: spawn() / send(SELECT, id)
    FW->>FP: open()
    FP-->>FW: ProviderInfo
    User->>View: 点击 Start
    View->>VM: start()
    VM->>SF: start()
    SF->>HC: helper.start_device
    HC->>H: helper.start_device
    H->>H: 创建/验证 MF Activate / Extension start
    H-->>HC: ok
    SF->>DC: start()
    DC->>FW: send(START)
    FW->>SINK: open(name=fb-v1, fmt=NV12 1080p30)
    SINK->>FB: attach
    FW->>FW: 进入帧循环
```

---

## 4. 帧循环（稳态推帧）

```mermaid
sequenceDiagram
    participant FP as FrameProvider
    participant PIPE as FramePipeline
    participant SINK as FrameSink
    participant FB as Frame Bus (Ring x4)
    participant CONS as Native Consumer<br/>(DShow Filter / MF Stream / CMIO Stream)
    participant APP as 消费端进程<br/>(OBS/Zoom/...)

    loop 每 33ms (30fps)
        FP->>FP: read() (USB)
        FP-->>PIPE: Frame(BGR/NV12, pts, seq)
        PIPE->>PIPE: Resize → FPS regulate → ColorConvert → Effects
        PIPE-->>SINK: Frame(NV12, pts, seq)
        SINK->>FB: lock(mtx)
        SINK->>FB: write slot[idx % 4] (header + planes)
        SINK->>FB: ++producer_idx
        SINK->>FB: SetEvent
        SINK->>FB: unlock(mtx)
        CONS->>FB: WaitForSingleObject(evt)
        CONS->>FB: read slot[(idx-1) % 4]
        CONS->>FB: 比较头尾 seq → 撕裂检测
        CONS-->>APP: 投递 IMediaSample / IMFSample / CMSampleBuffer
    end
```

---

## 5. 消费端打开 — Windows DirectShow

```mermaid
sequenceDiagram
    participant App as 消费端 (OBS/Zoom)
    participant DS as DirectShow Runtime
    participant Filter as AKVC DShow Filter
    participant FB as Frame Bus

    App->>DS: ICreateDevEnum::CreateClassEnumerator(VideoInputDevice)
    DS-->>App: Moniker list (含 AKVC)
    App->>DS: BindToObject(IBaseFilter)
    DS->>Filter: CoCreateInstance (in-proc)
    Filter->>FB: open(read)
    Filter-->>DS: IBaseFilter*
    App->>DS: AddFilter(filter) → ConnectFilter(...)
    DS->>Filter: GetMediaType(0, &mt) [NV12 1920x1080@30]
    DS->>Filter: CheckMediaType(&mt) → S_OK
    DS->>Filter: SetMediaType(&mt)
    App->>DS: Run()
    DS->>Filter: Run(t0)
    Filter->>Filter: streaming thread → FillBuffer 循环
    loop 每帧
        Filter->>FB: WaitForSingleObject(evt, 100ms)
        Filter->>FB: read slot
        Filter-->>DS: IMediaSample (NV12)
        DS-->>App: 渲染/编码
    end
```

---

## 6. 消费端打开 — Windows Media Foundation

```mermaid
sequenceDiagram
    participant App as 消费端 (Teams/Chrome)
    participant MF as MF Capture Engine
    participant FS as frameserver.exe
    participant Src as AKVC MF MediaSource
    participant FB as Frame Bus

    App->>MF: MFEnumDeviceSources(VIDEO_CAPTURE)
    MF->>FS: 系统级枚举（含 AKVC virtual camera）
    MF-->>App: IMFActivate list
    App->>MF: ActivateObject(IID_IMFMediaSource)
    MF->>FS: 在 frameserver 中实例化 Source
    FS->>Src: CoCreateInstance（LowBox 容器）
    Src->>FB: OpenFileMapping (匹配 ACL)
    Src-->>FS: IMFMediaSource*
    FS-->>App: IMFMediaSource* (跨进程代理)
    App->>MF: CreateSourceReader → Start
    MF->>Src: Start(pd, format, t0)
    Src->>Src: 启动 worker，开始 RequestSample
    loop 每帧
        MF->>Src: RequestSample(token)
        Src->>FB: WaitForSingleObject(evt)
        Src->>FB: read slot → 构造 IMFSample (NV12)
        Src-->>MF: QueueEvent(MEMediaSample, sample)
        MF-->>App: 投递帧
    end
```

---

## 7. 消费端打开 — macOS CoreMediaIO

```mermaid
sequenceDiagram
    participant App as 消费端 (FaceTime/Zoom/Safari)
    participant CMIO as coremediaiod
    participant Ext as AKVC.systemextension
    participant Helper as akvc-helperd
    participant Pool as IOSurface Pool

    App->>CMIO: AVCaptureDevice.devices(for: .video)
    CMIO->>Ext: 枚举 (CMIOExtensionProvider)
    CMIO-->>App: 设备列表（含 AKVC）
    App->>CMIO: open device
    CMIO->>Ext: connect / startStream
    Ext->>Helper: NSXPCConnection.consume
    Helper->>Pool: vend IOSurface (零拷贝引用)
    loop 每帧
        Helper->>Helper: 等待新帧信号
        Helper->>Pool: 获取最新 IOSurface
        Helper-->>Ext: send(IOSurfaceID, pts, seq)
        Ext->>Ext: 构造 CMSampleBuffer (NV12, IOSurface-backed)
        Ext-->>CMIO: stream.send(sampleBuffer)
        CMIO-->>App: 投递帧
    end
```

---

## 8. UI 关闭 / 崩溃 → 占位帧 兜底

```mermaid
sequenceDiagram
    participant UI as PySide6 App
    participant FW as FrameWorker
    participant H as Helper
    participant FB as Frame Bus
    participant CONS as 消费端 Consumer

    UI--xUI: 用户关闭 / 崩溃
    FW--xFW: 子进程退出 (随父退出 / job object)
    Note over H: Helper 检测到 attach 心跳超时 (3s)
    H->>FB: 切换到内置 Placeholder Source
    loop
        H->>FB: 写入"未连接"占位帧 (黑底 + AKVC 文字 + 时间戳)
        CONS->>FB: 正常读取 (不感知切换)
    end
    UI->>UI: 用户重启 App
    UI->>H: helper.attach_producer
    H->>FB: 切回真实 Producer
```

**不变量 I1 体现**：消费端**不会感知设备消失**。

---

## 9. 升级安装

```mermaid
sequenceDiagram
    actor User
    participant New as 新安装器
    participant OldH as 旧 Helper
    participant FB as Frame Bus
    participant Reg as Registrar

    User->>New: 双击 akvc-setup-2.0.0.exe
    New->>New: 检测 1.x 已安装
    New->>OldH: helper.upgrade_drain(timeout=10s)
    OldH->>FB: 切到占位帧
    OldH->>Reg: MF Shutdown / 注销 DShow filter
    OldH-->>New: drained
    New->>New: 停止 / 删除旧 Helper Service
    New->>New: 删除旧 DLL / 注册表残留
    New->>New: 安装新文件
    New->>New: 注册新 Helper / 新 DLL / 新 MF
    New-->>User: 升级完成
    Note over FB: 期间消费端持续看到设备<br/>仅可能掉 1-2 帧
```

---

## 10. 卸载

```mermaid
sequenceDiagram
    actor User
    participant Un as Uninstaller
    participant H as Helper
    participant Reg as Registrar
    participant Doc as akvc-doctor

    User->>Un: 控制面板/Uninstall.exe
    Un->>H: helper.upgrade_drain
    H-->>Un: drained
    Un->>Un: sc stop akvc-helper / sc delete
    Un->>Reg: regsvr32 /u akvc-dshow.dll (x64+x86)
    Un->>Reg: 删除 MF Activate 注册
    Un->>Un: 删除 ProgramFiles / ProgramData / 注册表
    Un->>Doc: akvc-doctor verify-clean
    Doc-->>Un: rc=0 (clean)
    Un-->>User: 卸载完成
```

macOS 等价流程：`OSSystemExtensionRequest.deactivate` → 卸载 launchd → 删 App。

---

## 11. 错误恢复 — Helper 崩溃

```mermaid
sequenceDiagram
    participant H as akvc-helper.exe
    participant SCM as Windows SCM
    participant FB as Frame Bus
    participant FS as frameserver.exe
    participant Crash as Crashpad

    H--xH: 崩溃 (segfault)
    H->>Crash: minidump 写盘
    SCM->>SCM: failure restart=10s
    SCM->>H: 重启 ServiceMain
    H->>FB: 重新创建 / 复用命名内核对象
    Note over FS: frameserver 持有 MF MediaSource 仍存活<br/>但 OpenFileMapping 已失效
    FS->>FB: 重新 OpenFileMapping (Helper 已重建)
    H->>H: 恢复 attach_producer 状态
    H->>FB: 重新进入帧循环 / 占位帧
```

---

## 12. 错误恢复 — 帧路径异常

```mermaid
sequenceDiagram
    participant FP as FrameProvider
    participant PIPE as FramePipeline
    participant SINK as FrameSink
    participant Log as Logger
    participant Met as Metrics

    FP-->>PIPE: read() raises (USB unplug)
    PIPE->>Log: warn "provider failed, fallback"
    PIPE->>Met: metrics.provider_error++
    PIPE->>PIPE: 切到 TestPattern("device disconnected")
    PIPE-->>SINK: 持续投递占位帧
    Note over FP: 后台每 1s 重试 open()
    FP-->>PIPE: open() ok (USB 重新插入)
    PIPE->>PIPE: 切回真实源
    PIPE->>Log: info "provider recovered"
```

---

## 13. 配置变更 — 切换分辨率

```mermaid
sequenceDiagram
    participant View
    participant VM
    participant SF as ServiceFacade
    participant DC as DeviceController
    participant PC as PipelineController
    participant HC as HelperClient
    participant H as Helper
    participant FB as Frame Bus

    View->>VM: set_format(1280x720@30)
    VM->>SF: set_format(fmt)
    par 控制面更新
        SF->>HC: helper.set_format(fmt)
        HC->>H: helper.set_format
        H->>FB: 标记 schema 切换 (writer-side)
    and 数据面切换
        SF->>PC: configure(resize=720p)
        PC->>PC: ResizeStage 重新配置
    end
    Note over FB: 当前帧周期内可能 1 帧丢弃<br/>消费端通过 MF/DShow 重新协商或 dynamic format change
    H-->>HC: ok
    HC-->>SF: ok
    SF-->>VM: ok
    VM-->>View: 已切换
```

**注**：DShow 不支持运行期改变 MediaType；该路径会触发 Filter 重新连接（消费端 1–2 帧黑屏）。MF / CMIO 支持热切换。

---

## 14. AI 模型加载 (Phase 6 预演)

```mermaid
sequenceDiagram
    participant View
    participant VM
    participant PC as PipelineController
    participant Eff as BackgroundReplaceEffect
    participant AI as AiTask (ONNX)
    participant FW as FrameWorker

    View->>VM: enable("background_replace", model="mediapipe-selfie")
    VM->>PC: set_effect(name, params)
    PC->>Eff: lazy import + load
    Eff->>AI: load(model_path)
    AI->>AI: ORT InferenceSession (DML / CoreML)
    AI-->>Eff: ready
    Eff-->>PC: ready
    Note over FW: 帧循环开始调用 effect.process(frame)
```

---

## 15. 自检流程 — `akvc-doctor`

```mermaid
sequenceDiagram
    actor User
    participant Doc as akvc-doctor
    participant H as Helper
    participant FB as Frame Bus
    participant Reg as Registrar
    participant CONS as Test Consumer

    User->>Doc: akvc-doctor diag
    Doc->>H: helper.ping → version, status
    Doc->>FB: 自模拟 LowBox open → 验证 ACL
    Doc->>Reg: 检查 DShow CLSID / MF 注册 / 系统扩展状态
    Doc->>CONS: 内嵌 ffmpeg 模拟拉流 1s
    CONS-->>Doc: 帧数 / fourcc / pts 单调
    Doc-->>User: 报告 (pass/fail 项 + 修复建议)
```

---

## 16. 跨平台路径对比一图

```mermaid
flowchart LR
    subgraph Windows
      A1[UI App] --> A2[FrameWorker]
      A2 -->|shm Ring| A3[Helper Service]
      A3 -->|in-proc| A4[DShow .dll]
      A3 -->|frameserver| A5[MF MediaSource]
      A4 --> A6[OBS/Zoom/微信]
      A5 --> A7[Teams/Chrome/新Skype]
    end
    subgraph macOS
      B1[UI App] --> B2[FrameWorker]
      B2 -->|XPC + IOSurface| B3[Helper launchd]
      B3 -->|XPC| B4[CMIO Extension]
      B4 --> B5[FaceTime/Zoom/Safari/OBS]
    end
```

---

## 17. 跨流程 invariants 校验

| 不变量 | 体现于时序图 |
|---|---|
| I1 — UI 崩溃设备不消失 | §8 占位帧 |
| I2 — 安装/卸载干净 | §9 升级 / §10 卸载 / §15 doctor |
| I3 — 故障不抖动旧帧 | §12 错误恢复（切到占位） |
| I4 — Helper 拥有跨进程对象 | §1 §2 Helper 创建 ACL 对象 |
| I5 — MVVM 边界 | §3 View→VM→SF 链路 |

下一文档：`component-diagram.md` — 组件/部署图。
