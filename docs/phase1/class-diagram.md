# Class Diagram — Cross-Platform Virtual Camera

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 1 — 系统架构设计
**前置文档**：`system-design.md`

> 本文用 Mermaid 绘制系统全部关键类图，覆盖：camera-core、ServiceFacade、ViewModel、平台抽象、Windows 原生、macOS 原生、Helper 协议。
> 类图聚焦**契约**（字段、方法、依赖、错误模型），不写实现细节。

---

## 1. Camera Core — Frame Provider

```mermaid
classDiagram
    class Frame {
      +int width
      +int height
      +str fourcc
      +bytes planes
      +int[] stride
      +int pts_100ns
      +int seq
      +int flags
      +dict meta
      +nv12_view() tuple
      +copy() Frame
    }

    class FrameProvider {
      <<interface>>
      +open() None
      +read() Frame
      +close() None
      +describe() ProviderInfo
    }

    class ProviderInfo {
      +str id
      +str name
      +list~Format~ supported_formats
    }

    class Format {
      +str fourcc
      +int width
      +int height
      +Fraction fps
    }

    class UsbCameraProvider {
      -VideoCapture cap
      -int device_index
      -Format current
      +open() None
      +read() Frame
      +close() None
      +list_devices() list~ProviderInfo~
    }

    class VideoFileProvider {
      -str path
      -bool loop
      -VideoCapture cap
      +open() None
      +read() Frame
      +close() None
    }

    class ImageSequenceProvider {
      -list~str~ paths
      -float fps
      +open() None
      +read() Frame
      +close() None
    }

    class TestPatternProvider {
      -str pattern
      +open() None
      +read() Frame
      +close() None
    }

    FrameProvider <|.. UsbCameraProvider
    FrameProvider <|.. VideoFileProvider
    FrameProvider <|.. ImageSequenceProvider
    FrameProvider <|.. TestPatternProvider
    FrameProvider ..> Frame
    FrameProvider ..> ProviderInfo
    ProviderInfo --> Format
```

**契约**：
- `read()` 阻塞最长 1 帧周期；超时返回最近一帧的副本，并设 `flags |= STALE`。
- `read()` 永不抛异常向上；底层失败转为 `flags |= ERROR` 的占位帧（黑色 + 时间戳 OSD）。
- `close()` 幂等。

---

## 2. Camera Core — Frame Pipeline

```mermaid
classDiagram
    class PipelineStage {
      <<interface>>
      +name() str
      +process(frame: Frame) Frame
      +on_config_change(cfg: dict) None
    }

    class FramePipeline {
      -list~PipelineStage~ stages
      -Metrics metrics
      +add(stage: PipelineStage) FramePipeline
      +process(frame: Frame) Frame
      +reconfigure(cfg: dict) None
    }

    class ResizeStage {
      -int target_w
      -int target_h
      -str interpolation
      +process(f) Frame
    }

    class FpsRegulator {
      -Fraction target_fps
      -float jitter_pct
      -TokenBucket bucket
      +process(f) Frame
    }

    class ColorConvertStage {
      -str src
      -str dst
      +process(f) Frame
    }

    class WatermarkStage {
      -str text
      -tuple position
      +process(f) Frame
    }

    class EffectStage {
      <<abstract>>
      +process(f) Frame
    }

    class BeautyEffect {
      -float smooth
      -float whiten
      +process(f) Frame
    }

    class BackgroundReplaceEffect {
      -AiTask segmenter
      -Image bg
      +process(f) Frame
    }

    PipelineStage <|.. ResizeStage
    PipelineStage <|.. FpsRegulator
    PipelineStage <|.. ColorConvertStage
    PipelineStage <|.. WatermarkStage
    PipelineStage <|.. EffectStage
    EffectStage <|-- BeautyEffect
    EffectStage <|-- BackgroundReplaceEffect
    FramePipeline o-- PipelineStage
```

**契约**：
- 每个 Stage 必须**就地或新分配**返回 `Frame`，不得修改输入 Frame 的元数据指针。
- Stage 内部异常转为日志 + 透传上一帧（保证不中断帧流）。
- `reconfigure` 必须线程安全且不阻塞当前帧。

---

## 3. Camera Core — Frame Sink (IPC Writer)

```mermaid
classDiagram
    class FrameSink {
      <<interface>>
      +open(name: str, fmt: Format) None
      +publish(frame: Frame) None
      +close() None
      +consumer_count() int
    }

    class WindowsShmSink {
      -str shm_name
      -SharedMemory shm
      -RingControl ctrl
      -Win32Event evt
      -Win32Mutex mtx
      +open(name, fmt) None
      +publish(frame) None
      +close() None
    }

    class MacOSIOSurfaceSink {
      -XPCConnection xpc
      -list~IOSurface~ pool
      -DispatchSemaphore sem
      +open(name, fmt) None
      +publish(frame) None
      +close() None
    }

    class RingControl {
      +int producer_idx
      +int consumer_count
      +int writer_pid
      +int schema_version
      +next_slot() int
    }

    FrameSink <|.. WindowsShmSink
    FrameSink <|.. MacOSIOSurfaceSink
    WindowsShmSink --> RingControl
```

**契约**：
- `publish` 必须 O(1) 复杂度且不阻塞超过 1ms（1080p 拷贝预算）。
- ring 满时丢最旧（覆盖），并 `metrics.frame_drop++`。
- schema_version 不匹配 → 拒绝 open 并返回 `E_AKVC_FRAMEBUS_SCHEMA_MISMATCH`。

---

## 4. Camera Core — AI Hooks 与 Effects

```mermaid
classDiagram
    class AiTask {
      <<interface>>
      +name() str
      +load(model_path: str) None
      +run(frame: Frame) AiResult
      +unload() None
    }

    class AiResult {
      +str task
      +bytes payload
      +float latency_ms
    }

    class FaceDetect {
      -Session ort_session
      +load(p) None
      +run(f) AiResult
    }

    class Segmentation {
      -Session ort_session
      +load(p) None
      +run(f) AiResult
    }

    class PoseEstimation {
      -Session ort_session
      +load(p) None
      +run(f) AiResult
    }

    class AiBackend {
      <<interface>>
      +new_session(model_path: str) Session
    }

    class OnnxRuntimeBackend {
      -list providers
      +new_session(p) Session
    }

    class MediaPipeBackend {
      +new_session(p) Session
    }

    AiTask <|.. FaceDetect
    AiTask <|.. Segmentation
    AiTask <|.. PoseEstimation
    AiTask ..> AiBackend
    AiBackend <|.. OnnxRuntimeBackend
    AiBackend <|.. MediaPipeBackend
```

**Phase 1 仅落接口**；模型加载、推理实现 Phase 6+。

---

## 5. Application Service Layer

```mermaid
classDiagram
    class ServiceFacade {
      -ConfigStore cfg
      -DeviceController dev
      -PipelineController pipe
      -HelperClient helper
      -Telemetry telemetry
      -CrashReporter crash
      +bootstrap() None
      +shutdown() None
      +list_sources() list~ProviderInfo~
      +select_source(id: str) None
      +start() None
      +stop() None
      +set_format(fmt: Format) None
      +set_effect(name: str, params: dict) None
      +metrics_snapshot() Metrics
    }

    class DeviceController {
      -FrameProvider source
      -FrameWorkerProcess worker
      +select(id: str) None
      +start() None
      +stop() None
    }

    class PipelineController {
      -FramePipeline pipeline
      -dict effects
      +configure(cfg: dict) None
      +set_effect(name, params) None
      +remove_effect(name) None
    }

    class HelperClient {
      -Channel rpc
      +ping() bool
      +status() HelperStatus
      +start_device() None
      +stop_device() None
      +set_format(fmt) None
      +metrics() dict
    }

    class FrameWorkerProcess {
      -Process proc
      -Pipe ctrl
      +start() None
      +stop() None
      +restart() None
      +alive() bool
    }

    class ConfigStore {
      -Path system_path
      -Path user_path
      +load() Config
      +save(c: Config) None
      +watch(cb) None
    }

    class CrashReporter {
      +install() None
      +submit(dump_path) None
    }

    class Telemetry {
      +record_counter(name, val) None
      +record_gauge(name, val) None
      +flush() None
    }

    ServiceFacade --> DeviceController
    ServiceFacade --> PipelineController
    ServiceFacade --> HelperClient
    ServiceFacade --> ConfigStore
    ServiceFacade --> Telemetry
    ServiceFacade --> CrashReporter
    DeviceController --> FrameWorkerProcess
    PipelineController --> FramePipeline
    DeviceController ..> FrameProvider
```

**契约**：
- `ServiceFacade` 是 ViewModel 唯一允许调用的入口（**MVVM 边界**）。
- 所有方法支持取消（接受 `Cancellation` token）；耗时操作返回 `Future`。
- `bootstrap` 幂等，可被 UI、CLI、测试夹具复用。

---

## 6. Presentation Layer — MVVM

```mermaid
classDiagram
    class MainView {
      -MainViewModel vm
      +on_start_clicked() None
      +on_stop_clicked() None
      +on_source_changed(idx) None
    }

    class MainViewModel {
      -ServiceFacade svc
      +Property~bool~ is_running
      +Property~str~ current_source
      +Property~Format~ current_format
      +Property~float~ fps
      +Property~float~ cpu_pct
      +Signal status_changed
      +start() None
      +stop() None
      +select_source(id: str) None
      +set_format(fmt: Format) None
    }

    class SettingsView {
      -SettingsViewModel vm
    }

    class SettingsViewModel {
      -ServiceFacade svc
      +Property~Config~ config
      +save() None
      +reset() None
    }

    class EffectsView {
      -EffectsViewModel vm
    }

    class EffectsViewModel {
      -ServiceFacade svc
      +list_effects() list
      +toggle(name) None
      +set_param(name, k, v) None
    }

    MainView --> MainViewModel
    SettingsView --> SettingsViewModel
    EffectsView --> EffectsViewModel
    MainViewModel --> ServiceFacade
    SettingsViewModel --> ServiceFacade
    EffectsViewModel --> ServiceFacade
```

**契约**：
- View 不持有任何业务对象；只持有 ViewModel。
- ViewModel 不持有 Qt Widget；只发 Signal、暴露 Property。
- 测试时可以替换 `ServiceFacade` 为 `FakeServiceFacade`。

---

## 7. Platform Abstraction (Layer 2)

```mermaid
classDiagram
    class IVirtualCamera {
      <<interface, C ABI>>
      +start() akvc_status
      +stop() akvc_status
      +set_format(fmt) akvc_status
      +query_consumers() int
    }

    class IFrameBus {
      <<interface, C ABI>>
      +open(name) akvc_status
      +publish(hdr, planes) akvc_status
      +close() akvc_status
    }

    class IRegistrar {
      <<interface, C ABI>>
      +register() akvc_status
      +unregister() akvc_status
      +verify_clean() akvc_status
    }

    class IHelperClient {
      <<interface, C ABI>>
      +connect() akvc_status
      +call(method, payload) Response
      +disconnect() void
    }

    class WinVirtualCamera
    class MacVirtualCamera
    class WinFrameBus
    class MacFrameBus
    class WinRegistrar
    class MacRegistrar
    class WinPipeClient
    class MacXPCClient

    IVirtualCamera <|.. WinVirtualCamera
    IVirtualCamera <|.. MacVirtualCamera
    IFrameBus      <|.. WinFrameBus
    IFrameBus      <|.. MacFrameBus
    IRegistrar     <|.. WinRegistrar
    IRegistrar     <|.. MacRegistrar
    IHelperClient  <|.. WinPipeClient
    IHelperClient  <|.. MacXPCClient
```

---

## 8. Windows Native — DirectShow 子系统

```mermaid
classDiagram
    class CVCamFilter {
      -CVCamStream* stream
      +NonDelegatingQueryInterface(iid, ppv) HRESULT
      +GetClassID(clsid) HRESULT
    }
    note for CVCamFilter "继承 CSource (DShow baseclasses)"

    class CVCamStream {
      -CSourceStream parent
      -FrameBusReader reader
      -CMediaType mt
      +FillBuffer(IMediaSample*) HRESULT
      +DecideBufferSize(IMemAllocator*, ALLOCATOR_PROPERTIES*) HRESULT
      +CheckMediaType(CMediaType*) HRESULT
      +GetMediaType(int, CMediaType*) HRESULT
      +SetMediaType(CMediaType*) HRESULT
      +Notify(IBaseFilter*, Quality) HRESULT
    }
    note for CVCamStream "继承 CSourceStream + IAMStreamConfig + IKsPropertySet"

    class CVCamControl {
      +GetState(...) HRESULT
      +Run(REFERENCE_TIME) HRESULT
      +Pause() HRESULT
      +Stop() HRESULT
    }

    class CVCamRegistration {
      +DllRegisterServer() HRESULT
      +DllUnregisterServer() HRESULT
      -RegisterFilterInCategory() HRESULT
    }

    class FrameBusReader {
      -HANDLE hMap
      -void* base
      -HANDLE hEvent
      -HANDLE hMutex
      +open(name) bool
      +read(IMediaSample*) HRESULT
      +close() void
    }

    CVCamFilter --> CVCamStream
    CVCamStream --> FrameBusReader
    CVCamFilter --> CVCamControl
    CVCamRegistration ..> CVCamFilter : registers
```

**关键点**：
- `FillBuffer` 阻塞等待 Event，最多 100ms；超时输出占位帧。
- `GetMediaType` 第 0 项必须为 NV12 1920x1080@30；后续按 §architecture-research.md 顺序枚举。

---

## 9. Windows Native — Media Foundation 子系统

```mermaid
classDiagram
    class AkvcMediaSource {
      -ComPtr~IMFMediaEventQueue~ eventQueue
      -ComPtr~IMFPresentationDescriptor~ pd
      -vector~AkvcMediaStream*~ streams
      +Start(pd, fmt, t) HRESULT
      +Stop() HRESULT
      +Pause() HRESULT
      +Shutdown() HRESULT
      +GetCharacteristics(*) HRESULT
      +CreatePresentationDescriptor(**) HRESULT
    }
    note for AkvcMediaSource "实现 IMFMediaSource + IMFMediaSourceEx + IKsControl"

    class AkvcMediaStream {
      -ComPtr~IMFMediaEventQueue~ eventQueue
      -ComPtr~IMFStreamDescriptor~ sd
      -FrameBusReader reader
      -atomic~bool~ active
      +RequestSample(token) HRESULT
      +OnSampleRead() void
    }
    note for AkvcMediaStream "实现 IMFMediaStream + IMFMediaStream2"

    class AkvcVirtualCameraActivator {
      +CreateInstance(IID, **ppv) HRESULT
      +ActivateObject(IID, **ppv) HRESULT
    }

    class AkvcRegistrar {
      +AddDeviceSourceInfo(name, friendly) HRESULT
      +Start() HRESULT
      +Shutdown() HRESULT
    }

    class FrameBusReader

    AkvcMediaSource --> AkvcMediaStream
    AkvcMediaStream --> FrameBusReader
    AkvcVirtualCameraActivator ..> AkvcMediaSource
    AkvcRegistrar ..> AkvcVirtualCameraActivator
```

**关键点**：
- Activator 在 frameserver LowBox 中被实例化；不能假设有完整文件系统访问权。
- `RequestSample` 内部异步：投递 work item，从 ring 取帧后 `QueueEvent(MEMediaSample)`。

---

## 10. Windows Native — Helper Service

```mermaid
classDiagram
    class HelperServiceMain {
      +ServiceMain() void
      +ServiceCtrlHandler(ctrl) void
    }

    class HelperOrchestrator {
      -FrameBusOwner bus
      -MFRegistration mf
      -DshowRegistration dshow
      -RpcServer rpc
      +start() void
      +stop() void
      +on_command(req) Response
    }

    class FrameBusOwner {
      -HANDLE hMap
      -HANDLE hEvent
      -HANDLE hMutex
      -SECURITY_ATTRIBUTES sa
      +create() void
      +destroy() void
    }

    class MFRegistration {
      -ComPtr~IMFVirtualCamera~ vcam
      +activate() HRESULT
      +deactivate() HRESULT
    }

    class DshowRegistration {
      +register_dll() HRESULT
      +unregister_dll() HRESULT
    }

    class RpcServer {
      -HANDLE hPipe
      -ThreadPool pool
      +listen() void
      +stop() void
    }

    HelperServiceMain --> HelperOrchestrator
    HelperOrchestrator --> FrameBusOwner
    HelperOrchestrator --> MFRegistration
    HelperOrchestrator --> DshowRegistration
    HelperOrchestrator --> RpcServer
```

---

## 11. macOS Native — Camera Extension

```mermaid
classDiagram
    class AkvcProviderSource {
      -CMIOExtensionProvider provider
      -AkvcDeviceSource device
      +connect(client) Bool
      +disconnect(client) Void
      +availableProperties() Set
      +providerProperties(set) Properties
    }
    note for AkvcProviderSource "符合 CMIOExtensionProviderSource"

    class AkvcDeviceSource {
      -CMIOExtensionDevice device
      -AkvcStreamSource stream
      +availableProperties() Set
      +deviceProperties(set) Properties
      +setDeviceProperties(props) Void
    }

    class AkvcStreamSource {
      -CMIOExtensionStream stream
      -CMSimpleQueue queue
      -IOSurfaceBridge bridge
      +startStream() Void
      +stopStream() Void
      +send(sampleBuffer) Void
    }

    class IOSurfaceBridge {
      -[IOSurface] pool
      -DispatchSource source
      +receive() IOSurface?
      +release(surface) Void
    }

    class XPCService {
      -NSXPCListener listener
      +listener(_:shouldAcceptNewConnection:) Bool
    }

    AkvcProviderSource --> AkvcDeviceSource
    AkvcDeviceSource --> AkvcStreamSource
    AkvcStreamSource --> IOSurfaceBridge
    AkvcProviderSource ..> XPCService
```

---

## 12. macOS Native — Helper (launchd)

```mermaid
classDiagram
    class HelperDaemonMain {
      +main() Int32
    }

    class HelperOrchestrator {
      -FrameBusOwner bus
      -ExtensionRegistrar reg
      -XPCServer xpc
      +start() Void
      +stop() Void
    }

    class FrameBusOwner {
      -[IOSurface] pool
      -CFMessagePort port
      +create() Void
      +destroy() Void
    }

    class ExtensionRegistrar {
      +activate() OSSystemExtensionRequest
      +deactivate() OSSystemExtensionRequest
    }

    class XPCServer {
      -NSXPCListener listener
      +start() Void
      +stop() Void
    }

    HelperDaemonMain --> HelperOrchestrator
    HelperOrchestrator --> FrameBusOwner
    HelperOrchestrator --> ExtensionRegistrar
    HelperOrchestrator --> XPCServer
```

---

## 13. 控制面协议（IDL 视角）

```mermaid
classDiagram
    class HelperRequest {
      +str method
      +int id
      +dict params
    }

    class HelperResponse {
      +int id
      +int code
      +str message
      +dict result
    }

    class HelperStatus {
      +str helper_version
      +bool device_active
      +str backend
      +int consumer_count
      +Format current_format
      +int uptime_s
    }

    class Format {
      +str fourcc
      +int width
      +int height
      +int fps_num
      +int fps_den
    }

    HelperRequest <.. HelperResponse : reply_to
    HelperResponse --> HelperStatus
    HelperStatus --> Format
```

---

## 14. 错误模型

```mermaid
classDiagram
    class AkvcError {
      <<exception>>
      +str code
      +str message
      +dict details
      +Optional~AkvcError~ cause
      +to_status() akvc_status
      +from_hresult(hr) AkvcError
      +from_osstatus(s) AkvcError
    }

    class FrameBusError
    class HelperUnavailableError
    class DeviceBusyError
    class FormatNotSupportedError
    class RegistrationFailedError
    class ConfigInvalidError

    AkvcError <|-- FrameBusError
    AkvcError <|-- HelperUnavailableError
    AkvcError <|-- DeviceBusyError
    AkvcError <|-- FormatNotSupportedError
    AkvcError <|-- RegistrationFailedError
    AkvcError <|-- ConfigInvalidError
```

**错误码命名空间（节选）**：
- `E_AKVC_FRAMEBUS_OPEN_FAILED`
- `E_AKVC_FRAMEBUS_SCHEMA_MISMATCH`
- `E_AKVC_HELPER_NOT_RUNNING`
- `E_AKVC_HELPER_TIMEOUT`
- `E_AKVC_REG_DSHOW_REGSVR_FAILED`
- `E_AKVC_REG_MF_ACTIVATE_FAILED`
- `E_AKVC_REG_MAC_EXT_REJECTED`
- `E_AKVC_FORMAT_NOT_SUPPORTED`
- `E_AKVC_DEVICE_BUSY`
- `E_AKVC_CONFIG_INVALID`

每个错误码在 `virtualcam/shared/errors.h` 维护一对一映射，并在 `docs/operations/errors.md` 留有"用户级人话解释"。

---

## 15. 类图整体依赖（顶层一图）

```mermaid
flowchart TB
    UI[View] --> VM[ViewModel]
    VM --> SF[ServiceFacade]
    SF --> DC[DeviceController]
    SF --> PC[PipelineController]
    SF --> HC[HelperClient]
    DC --> FW[FrameWorkerProcess]
    FW --> FP[FrameProvider]
    FW --> PIPE[FramePipeline]
    FW --> SINK[FrameSink]
    PC --> PIPE
    SINK -->|shm/iosurface| HELPER[Helper]
    HC -->|pipe/xpc| HELPER
    HELPER --> VCAM[Virtual Camera Native]
    VCAM --> OS[(OS Capture Stack)]
```

---

## 16. 验证清单（架构层）

- [ ] 所有 Provider/Stage/Sink 实现都通过 `IVirtualCamera/IFrameBus` 接口可被替换。
- [ ] ViewModel 不出现 `import cv2 / numpy / ctypes`（MVVM 边界检查，pre-commit lint）。
- [ ] 所有跨进程对象生命周期在 Helper；UI 进程崩溃后 Helper 仍工作（不变量 I1）。
- [ ] 所有错误路径都对应一个 `E_AKVC_*` 码；CI grep 检查无 `raise Exception("...")` 裸抛。
- [ ] `FrameSink.publish` 在 1080p 单帧 ≤ 1ms（性能测试）。
- [ ] 所有平台层只在 `virtualcam/<os>/` 目录内 import OS 头文件；camera-core 严禁。

下一文档：`sequence-diagram.md` — 时序图。
