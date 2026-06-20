# Architecture Research — Cross-Platform Virtual Camera

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 0 — 技术调研
**日期**：2026-06-19
**作者**：架构组（Windows Driver / macOS Multimedia / MF / DirectShow / CMIO / PySide6 联席）

> 本文不写代码、不做选型结论，只对底层框架与业界开源实现做事实性、可对比的深度分析。
> 选型结论见同目录 `technology-selection.md`，风险见 `risk-analysis.md`。

---

## 1. 研究范围与方法

研究覆盖以下五条技术路径：

1. Microsoft DirectShow — Source Filter 形式的虚拟摄像头
2. Microsoft Media Foundation — Virtual Camera (MFCreateVirtualCamera, Win11 21H2+)
3. Apple CoreMediaIO — DAL Plug-In（旧）与 Camera Extension（新）
4. OBS Studio — `obs-virtualcam`（Win/Mac）实现剖析
5. AKVirtualCamera — 跨平台开源虚拟摄像头实现剖析

研究方法：阅读官方 SDK 头文件、Microsoft Learn、Apple Developer 文档、相关项目源码、Windows Driver Samples、Apple `CoreMediaIO/CMIOExtension` 头文件、社区在 22H2 与 macOS 14/15 上的踩坑记录。

研究目标：

- 数据流路径（采集 → 帧分发 → 消费端）
- 进程/沙盒模型
- 注册与卸载机制
- 安全与签名要求
- 兼容主流消费端（OBS / Zoom / Teams / Meet / Chrome / FaceTime）的能力
- 长期演进风险

---

## 2. Windows: DirectShow Source Filter

### 2.1 核心模型

DirectShow 是基于 COM 的有向图（Filter Graph）模型。一个虚拟摄像头本质是一个实现了
`IBaseFilter + IAMStreamConfig + IKsPropertySet + IAMFilterMiscFlags` 的 **Source Filter**，
通过 `CLSID_VideoInputDeviceCategory` 注册到系统设备枚举类下，DirectShow 应用通过
`ICreateDevEnum::CreateClassEnumerator` 即可看到。

```
DirectShow Application (OBS / Zoom legacy / Skype legacy)
        │
        ▼
  Filter Graph Manager (quartz.dll)
        │
        ▼
  ┌─────────────────────────────┐
  │   Source Filter (我们)      │  ← 进程内 in-proc COM (DLL)
  │   IBaseFilter               │
  │   IAMStreamConfig           │
  │   Output Pin (CSourceStream)│
  └─────────────────────────────┘
        │ Sample (IMediaSample)
        ▼
   Color Space Convert / Renderer / Encoder
```

### 2.2 关键事实

| 维度 | 描述 |
|---|---|
| 部署形式 | 进程内 COM DLL（`.ax` 或 `.dll`），通过 `regsvr32` 注册到 HKCR/HKLM |
| 帧来源 | 由 Filter 自身的 worker 线程在 `FillBuffer()` 中提供 |
| 跨进程 | 需自行实现 IPC（命名管道 / 共享内存 / 全局事件）让 UI 进程喂帧 |
| 像素格式 | 在 `GetMediaType` 中声明 NV12 / YUY2 / RGB24 等，消费端按需协商 |
| 注册方式 | `DllRegisterServer` 写注册表 `CLSID\{...}\InprocServer32` 与 `Filter Categories\{860BB310-...}` |
| 签名要求 | 不强制驱动签名（不是内核驱动），但建议 Authenticode EV 提升可信度 |
| 系统支持 | Windows 7 至 Windows 11 全覆盖 |

### 2.3 兼容性矩阵（实测/官方资料）

| 消费端 | 是否识别 DirectShow Source Filter | 备注 |
|---|---|---|
| OBS Studio | ✅ | 经典 `Video Capture Device (DirectShow)` |
| Zoom Desktop | ✅ | 仍走 DShow 枚举 |
| Microsoft Teams (经典/新版) | ⚠ | 新版 Teams 走 Media Foundation Frame Server，DShow 不可见 |
| Google Meet (Chrome) | ⚠ | Chrome 在 Win10/11 走 MediaFoundation Capture Engine（约 M90 之后），DShow 路径已在 desktop_capture/MF 下逐步淘汰 |
| 微信 / QQ 桌面 | ✅ | 多数仍 DShow |
| Skype 新版 | ❌ | 已切到 MF |
| Discord | ✅ | DShow 可见 |

**结论事实**：DirectShow 路径仍能覆盖 60–70% 主流消费端，但 **Chrome/Edge/Teams** 三大重要客户端已逐步只走 Media Foundation。这是为什么需要 Phase 3 升级到 MF 的核心原因。

### 2.4 已知陷阱

- 64 位 / 32 位双注册问题：必须同时提供 x64 与 x86 DLL，否则 32 位老应用看不到设备。
- `IPin::QueryAccept` 协商失败导致部分消费端默认黑屏，需要谨慎实现媒体类型枚举顺序。
- Filter 在被多个消费端同时打开时，必须保证帧总线（IPC 共享内存）支持 1:N 广播。
- 部分主板/反作弊（如 EAC、Vanguard）会在内核态阻断未签名 in-proc 模块加载到游戏进程。

---

## 3. Windows: Media Foundation Virtual Camera

### 3.1 核心模型

Windows 11 21H2 引入 `MFCreateVirtualCamera` API，Windows 10 22H2 通过 KB 累积更新部分回填。
Virtual Camera 由 **Media Source DLL（COM）+ Activate（注册）** 组成，运行在 **Frame Server**
（`frameserver.exe`，`Windows Camera Frame Server` 服务）中，所有消费端共享同一帧源。

```
Consumer Process (Teams / Chrome / Zoom modern / Camera.exe)
        │  IMFActivate / IMFMediaSource 引用
        ▼
┌────────────────────────────────────────┐
│   Windows Camera Frame Server          │  ← 系统进程
│   (frameserver.exe, LowBox container)  │
│   ┌──────────────────────────────┐     │
│   │ Our Media Source (COM, DLL)  │     │  ← 我们的 DLL 被加载到 frameserver
│   │ IMFMediaSource               │     │
│   │ IMFMediaStream               │     │
│   │ IKsControl (PnP/属性)        │     │
│   └──────────────────────────────┘     │
└────────────────────────────────────────┘
        │ 帧来自 IPC（共享内存 / D3D 纹理）
        ▼
  UI App (PySide6) — Frame Producer
```

### 3.2 关键事实

| 维度 | 描述 |
|---|---|
| API | `MFCreateVirtualCamera()`（mfsensorgroup.h） |
| 部署形式 | 进程内 COM DLL，但**实际运行在 frameserver.exe 沙盒** |
| 注册 | 通过 `IMFVirtualCamera::AddDeviceSourceInfo` + `Start` 注册，不再依赖 regsvr32 类别注册 |
| 生命周期 | App 调用 Start → 设备出现在系统；调用 Shutdown → 消失。也可“持久注册”常驻 |
| 帧 IPC | 推荐 Shared Handle / D3D11 共享纹理，CPU 路径用 Named Pipe + Shared Memory |
| 签名 | 强烈建议 EV 代码签名，否则 LowBox 容器可能拒绝加载；分发要走 MSIX/MSI 流程 |
| 系统支持 | Windows 11（首选）、Windows 10 22H2（部分回填，需测试） |
| 兼容性 | 系统级出现，**所有走 MF Capture 的消费端**都能看到 |

### 3.3 与 DShow 的关键差异

| 维度 | DirectShow | Media Foundation VirtualCamera |
|---|---|---|
| 进程模型 | 加载到消费端进程 | 加载到 Windows Frame Server |
| 一次注册 | regsvr32 永久 | API 创建（可瞬时也可持久） |
| 多消费端 | 各自加载一份 DLL | 系统统一帧源，Frame Server 1:N 分发 |
| 沙盒 | 无 | LowBox AppContainer，文件/网络受限 |
| 兼容 Teams/Chrome/新 Skype | ❌ | ✅ |
| 兼容老应用 | ✅ | 视应用 capture path 而定，多数 Win11 已迁移 |
| 调试难度 | 中 | 高（跨进程 + 沙盒 + 系统服务） |

### 3.4 已知陷阱

- frameserver 沙盒下读取我们 UI 进程写入的共享内存：必须使用具有正确 ACL（包含 `ALL_APP_PACKAGES` 或具体 capability SID）的命名对象。
- 持久注册需要在每次开机后由 Helper 重新激活，否则设备消失。
- 跨架构：必须发 ARM64 / x64 两套（ARM64 PC 数量上升中）。
- 一个 Media Source 不能被多个 `IMFVirtualCamera` 同时托管，多 UI 实例需要 Helper 单例化。

---

## 4. macOS: CoreMediaIO

### 4.1 两条路径并存的现实

| 路径 | 状态 | 适用版本 | 备注 |
|---|---|---|---|
| **DAL Plug-In** (`/Library/CoreMediaIO/Plug-Ins/DAL/*.plugin`) | **Deprecated** | macOS ≤ 12 仍工作；macOS 13+ 仍可加载但 Apple 已宣布弃用 | 加载到每个消费端进程内，Sandbox/Hardened Runtime 应用经常拒绝加载 |
| **CMIO Camera Extension** (System Extension, DriverKit-like 用户态) | **官方推荐** | macOS 12.3+ 引入，13+ 稳定 | 系统级，所有消费端可见，FaceTime/Safari/Chrome/Zoom 全兼容 |

### 4.2 Camera Extension 模型

```
Consumer (FaceTime / Zoom / OBS / Safari getUserMedia)
        │  CoreMediaIO 客户端 API
        ▼
┌──────────────────────────────────────────────┐
│  cmio assistant / coremediaiod (system)      │
│        │                                      │
│        ▼                                      │
│  ┌────────────────────────────────────────┐  │
│  │ Our Camera Extension (.systemextension)│  │  ← 用户态系统扩展
│  │ Bundle: AppKit/CMIOExtension           │  │
│  │ - CMIOExtensionProviderSource          │  │
│  │ - CMIOExtensionDeviceSource            │  │
│  │ - CMIOExtensionStreamSource            │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
        │  XPC / Mach Port / IOSurface
        ▼
  Container App (PySide6 桌面端) — Frame Producer
```

### 4.3 关键事实

| 维度 | 描述 |
|---|---|
| 框架 | `CoreMediaIO/CMIOExtension*.h`（Swift / Obj-C++ 均可） |
| 打包 | App Bundle 内嵌 `Contents/Library/SystemExtensions/*.systemextension` |
| 安装 | 通过 `OSSystemExtensionRequest` API，弹用户授权 + 重启系统服务 |
| 进程 | 系统加载为独立用户态进程（沙盒、受 SIP 保护） |
| 帧传输 | IOSurface（零拷贝）+ XPC 控制通道，由 CMIOExtensionStreamSource 投递 CMSampleBuffer |
| 像素格式 | `kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange`（NV12）、`yuvs`（YUY2）、`BGRA` |
| 签名 | **必须** Developer ID + Notarization + System Extension entitlement |
| 架构 | Universal 2（x86_64 + arm64）必备 |

### 4.4 已知陷阱

- 用户授权流程：首次安装弹"系统扩展被阻止"，需用户去 **System Settings → Privacy & Security** 手动启用 → 重启可能必需。
- Container App 与 Extension 必须同 Team ID + App Group，否则 IOSurface/XPC 不通。
- `com.apple.developer.system-extension.install` entitlement 需要 Apple 审批（Developer Program 内可申请，但不是默认开启）。
- macOS 14+ 引入更严格的 TCC，Camera Extension 自身访问系统摄像头需要单独的 Camera 权限。
- Apple Silicon 下 Reduced Security 与 Full Security 启动模式都允许，但 DriverKit 类扩展在 Permissive Security 下调试更顺。

---

## 5. 业界开源实现剖析

### 5.1 OBS Studio — `obs-virtualcam` / `win-dshow` / `mac-virtualcam`

**Windows 现状（OBS 28+）**

- 旧版（≤27）：基于 DirectShow Source Filter，注册 `obs-virtualcam.dll`。
- 新版（28+）：**已切换到 Media Foundation VirtualCamera API**，通过 `obs-virtualcam-module.dll` 在 OBS 主进程中调用 `MFCreateVirtualCamera`，Media Source DLL 单独打包，由 frameserver 加载。
- 帧 IPC：命名共享内存 `OBSVirtualCamVideo`，配合互斥锁与帧序列号。

**macOS 现状（OBS 28+）**

- 旧版：DAL Plug-In `obs-mac-virtualcam.plugin`。
- 新版：CMIO Camera Extension（位于 OBS.app 内，首次启动调 `OSSystemExtensionRequest` 安装）。
- 帧 IPC：CVPixelBuffer + Mach Port + 命名共享内存（仍兼容旧 DAL）。

**对我们的启示**

- 双栈策略（DShow + MF / DAL + Extension）是过渡期常态，非过度设计。
- IPC 用"共享内存 + 序列号 + 互斥/事件"的模式经过实战检验。
- OBS 选择**单一 Producer（OBS 主进程）→ N Consumer**，没尝试做多 Producer，我们也应如此。

### 5.2 AKVirtualCamera (webcamoid 项目周边)

由 Gonzalo Exequiel Pedone 维护，BSD/GPL 双授权，跨 Windows/macOS。其架构具有非常高的参考价值：

```
┌────────────────────────────────────────────────────┐
│  Manager / CLI (AkVCamManager.exe / akvcam-utils)  │  ← 注册/卸载/枚举
└────────────────────────────────────────────────────┘
                    │
┌────────────────────────────────────────────────────┐
│  AssistantService (Windows Service / launchd)      │  ← Helper, 单例
└────────────────────────────────────────────────────┘
        │              │
        ▼              ▼
┌─────────────┐   ┌─────────────────────────────┐
│ DShow .dll  │   │ MF Media Source .dll        │   (Windows)
│ Source      │   │                             │
│ Filter      │   └─────────────────────────────┘
└─────────────┘
┌─────────────────────────────┐
│ CMIO Extension .systemext   │   (macOS)
└─────────────────────────────┘
        ▲
        │  Local IPC (Named Pipe / Unix Socket / Shared Memory)
┌────────────────────────────────────────────────────┐
│  Producer App (任意第三方 + 我们的 PySide6)        │
└────────────────────────────────────────────────────┘
```

**对我们的启示**

- AssistantService 模式（系统服务/launchd 守护）是处理"持久注册 + 多 Producer 共存"的最干净方案。
- 把 DShow 与 MF 同时塞到一个 manager 命令行下统一注册/卸载，对运维友好。
- 帧通道走匿名共享内存 + 命名互斥/事件，而非 RPC，性能可保 1080p30 < 5% CPU 开销。
- Camera Extension 安装走 `OSSystemExtensionRequest`，没有自造轮子。

### 5.3 其他参考

- **UnityCapture / Spout / Syphon**：图形对图形的虚拟摄像/视频共享，源自游戏/创作工具领域。不直接用，但 D3D11 NT Handle / IOSurface 共享思路可借鉴。
- **NVIDIA Broadcast**：闭源，使用了 MF VirtualCamera + 自有 AI 管线（TensorRT），是我们 Phase 5+ AI 能力的标杆。
- **Snap Camera**（已停服）：过去走 DShow Source Filter，证明 DShow + 美颜/滤镜的工程组合可行。

---

## 6. 跨平台对比矩阵

| 能力 | DirectShow | MF VirtualCam | DAL Plug-In | CMIO Camera Extension |
|---|---|---|---|---|
| 是否官方推荐 | 仍支持但定位为 Legacy | ✅ Win11 唯一推荐 | ❌ 已弃用 | ✅ macOS 13+ 唯一推荐 |
| 沙盒/Hardened Runtime 兼容 | 部分 | ✅ | ❌ 频繁被拒 | ✅ |
| 系统级单实例 | ❌（每进程一份） | ✅（frameserver） | ❌ | ✅（cmio assistant） |
| 跨进程 IPC 复杂度 | 中 | 高 | 中 | 高 |
| 主流消费端覆盖 | 60–70% | ≥95% | 60% | ≥95% |
| 签名/分发难度 | 低 | 中（需 EV/MSIX） | 低 | 高（需 SystemExt entitlement + 公证） |
| 实施速度（MVP） | **最快** | 中 | 快但价值低 | 慢 |
| 长期维护 | 风险中 | 长期 | 不可投入 | 长期 |

---

## 7. 数据流参考实现

### 7.1 Windows 双栈数据流

```
PySide6 App (Producer)
   │  OpenCV / NumPy 帧 (RGB)
   ▼
Frame Pipeline (Resize / FPS / Color)
   │  NV12 帧 + 时间戳 + 序列号
   ▼
Shared Memory Ring (1080p × 4 缓冲, ~12MB)  ←── Mutex/Event 协调
   │
   ├──→ DShow Source Filter (CSourceStream::FillBuffer)  ──→ 进程内消费端
   │
   └──→ MF Media Source (IMFMediaStream::RequestSample) ──→ frameserver  ──→ 消费端
```

### 7.2 macOS 数据流

```
PySide6 App (Producer)
   │  CVPixelBuffer (NV12, IOSurface-backed)
   ▼
XPC connection → Camera Extension
   │
   ▼
CMIOExtensionStreamSource.send(sampleBuffer)
   │
   ▼
coremediaiod → 所有消费端 (FaceTime/Zoom/OBS/Safari)
```

---

## 8. 像素格式与协商

| 格式 | FourCC | 用途 | 备注 |
|---|---|---|---|
| NV12 | `NV12` | 首选交付格式，硬件友好 | 4:2:0，bi-planar，与 D3D/IOSurface 原生匹配 |
| YUY2 | `YUY2` | 兼容老 DShow 消费端 | 4:2:2，packed |
| MJPEG | `MJPG` | 高分辨率低带宽兜底 | 不建议作为主输出，CPU 编码成本高 |
| RGB24 | `RGB ` | 调试与个别老应用 | 仅作为可选枚举项 |

协商策略：媒体类型枚举顺序 = **NV12 → YUY2 → MJPEG → RGB24**。先呈最优、再退化兼容。

---

## 9. 关键参考资料（供后续阶段精读）

- Microsoft Learn — *Media Foundation Virtual Camera*（`mfsensorgroup.h`、示例 `VirtualCamera/SimpleMediaSource`）
- Microsoft Windows-classic-samples — `Samples/VirtualCamera`
- Apple Developer — *Creating a camera extension with Core Media IO*（WWDC22 Session 10022）
- Apple `CMIOExtension*.h` 头文件
- OBS Studio 源码 — `plugins/win-dshow/`, `plugins/mac-virtualcam/`, `plugins/win-capture/virtual-cam/`
- AKVirtualCamera 仓库 — Manager/Service/DShow/MF/CMIO 完整实现
- Chromium 源码 — `media/capture/video/win/video_capture_device_mf_win.cc`（理解 Chrome 走 MF 的细节）

---

## 10. 结论摘要（事实层）

1. Windows 上要"被所有主流消费端识别"，**MF VirtualCamera 是唯一长期方案**，DShow 是过渡兼容层。
2. macOS 13+ 上 **CMIO Camera Extension 是唯一长期方案**，DAL 不再投入。
3. OBS 与 AKVirtualCamera 已用工程实践证明：**双栈过渡 + 共享内存 IPC + Helper 单例**是经过验证的范式。
4. 所有路径都需要严格的代码签名/公证；macOS 还需 System Extension entitlement。
5. Frame Server / Camera Extension 的沙盒模型决定了 IPC 必须可被低权限进程访问，ACL 与 App Group 设计要前置进入架构阶段。

→ 选型与权衡见 `technology-selection.md`。
→ 风险与缓解见 `risk-analysis.md`。
