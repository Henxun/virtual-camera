# Technology Selection — Cross-Platform Virtual Camera

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 0 — 技术选型
**日期**：2026-06-19
**前置文档**：`architecture-research.md`

> 本文给出**最终选型建议**与每个决策的**取舍论证**，供 Phase 1 系统架构设计直接落地。
> 决策原则：①工程质量 ②可维护性 ③商业软件标准 ④长期扩展 ⑤性能。

---

## 1. 一句话结论

| 平台 | 选型 |
|---|---|
| Windows MVP（Phase 2） | **DirectShow Source Filter（in-proc COM DLL）+ 共享内存 IPC + Helper Service** |
| Windows 正式版（Phase 3） | **Media Foundation Virtual Camera**（MFCreateVirtualCamera）；DShow 作为兼容层保留 |
| macOS（Phase 4） | **CoreMediaIO Camera Extension（System Extension）**；不实现 DAL Plug-In |
| 桌面端 | **Python 3.12 + PySide6 + MVVM**；视频处理 OpenCV/NumPy；AI 预留 ONNX Runtime + MediaPipe |
| IPC | **匿名/命名共享内存 + 命名事件/互斥 + Ring Buffer**；macOS 用 IOSurface + XPC |
| 帧主格式 | **NV12** 主推；YUY2 / MJPEG / RGB24 作为协商兜底 |
| 安装器 | Windows **NSIS**（带管理员提权 + 子组件签名）；macOS **PKG + Distribution.xml + 公证** |
| 签名分发 | Windows **EV Code Signing + MSI/MSIX 兼容路径**；macOS **Developer ID + Notarization + System Extension entitlement** |
| 测试 | **pytest + pytest-qt + headless OpenGL + GitHub Actions Win/macOS runner** |

---

## 2. 决策矩阵（加权评分）

评分 1–5，权重之和 = 1.0。

### 2.1 Windows 路径

| 维度 | 权重 | DShow Only | MF Only | DShow + MF 双栈 |
|---|---|---|---|---|
| 主流消费端覆盖（OBS/Zoom/Teams/Chrome/微信/QQ/FaceTime） | 0.25 | 3 | 4 | **5** |
| MVP 上手速度 | 0.15 | **5** | 2 | 4 |
| 长期可维护性 | 0.20 | 2 | **5** | 4 |
| 沙盒/反作弊兼容 | 0.10 | 2 | **4** | 4 |
| 调试与可观测性 | 0.10 | **4** | 2 | 3 |
| 安装/签名复杂度（越简单越高分） | 0.10 | **4** | 2 | 3 |
| 性能（共享 1:N 分发） | 0.10 | 2 | **5** | 4 |
| **加权得分** | 1.00 | 3.20 | 3.65 | **3.95** |

→ **采用双栈**。Phase 2 先 DShow 跑通端到端；Phase 3 上 MF，DShow 退为"经典兼容驱动"。

### 2.2 macOS 路径

| 维度 | 权重 | DAL Only | Camera Extension Only | DAL + Extension |
|---|---|---|---|---|
| 13+ 兼容（Hardened Runtime / Sandboxed App） | 0.30 | 1 | **5** | 3 |
| 14/15 长期演进 | 0.20 | 1 | **5** | 3 |
| 安装复杂度（用户授权） | 0.15 | **5** | 2 | 2 |
| 签名/公证可行性 | 0.10 | 4 | 4 | 3 |
| 实施成本 | 0.10 | **5** | 2 | 1 |
| 主流消费端覆盖 | 0.15 | 2 | **5** | 4 |
| **加权得分** | 1.00 | 2.55 | **4.10** | 2.85 |

→ **只做 Camera Extension**。理由：DAL 已被 Apple 弃用，多数 Hardened Runtime 应用拒绝加载；做 DAL 等于增加维护面而少有收益。

### 2.3 桌面端 UI 框架

| 维度 | 权重 | PySide6 | PyQt6 | Electron + Python 后端 | Tauri + Python 后端 |
|---|---|---|---|---|---|
| 原生性能 | 0.20 | **5** | **5** | 2 | 4 |
| 与视频/AI 生态结合 | 0.20 | **5** | **5** | 3 | 3 |
| 跨平台一致性 | 0.15 | **5** | **5** | **5** | 4 |
| 商用授权（LGPL 友好度） | 0.15 | **5** (LGPL) | 3 (GPL/商用费) | 4 | 4 |
| 团队招聘/上手 | 0.10 | 4 | 4 | **5** | 3 |
| 与 OpenCV/MediaPipe 帧零拷贝 | 0.10 | **5** | **5** | 1 | 2 |
| 包体积 | 0.10 | 4 | 4 | 1 | **5** |
| **加权得分** | 1.00 | **4.80** | 4.55 | 2.95 | 3.55 |

→ **PySide6**。LGPL 商业可用，与 OpenCV/Numpy/ONNX 在同进程零拷贝处理帧最直接。

---

## 3. 详细选型说明

### 3.1 Windows: DShow MVP 选型

- 形式：**进程内 COM DLL**（一个 x64、一个 x86），可通过 `regsvr32` 注册。
- Filter 类目：`CLSID_VideoInputDeviceCategory` (`{860BB310-5D01-11D0-BD3B-00A0C911CE86}`)。
- 关键接口：`IBaseFilter`、`IAMStreamConfig`、`IAMVideoControl`、`IKsPropertySet`、`IAMFilterMiscFlags`、`CSourceStream` 子类做 `FillBuffer`。
- 媒体类型枚举顺序（默认协商最优）：NV12 1920×1080@30 → NV12 1280×720@30 → YUY2 同上 → MJPEG → RGB24。
- IPC：`CreateFileMapping` 命名共享内存 + `CreateEvent` 帧到达事件 + 序列号防撕裂。
- 注册表自描述：在 `Filter Categories` 下写明 Pin/MediaType，使 DShow 应用无需打开设备即可知能力。
- 卸载：`DllUnregisterServer` + Helper 在卸载时清理残留。

### 3.2 Windows: MF Virtual Camera 选型

- 形式：**Media Source COM DLL**，由 `frameserver.exe` 加载；激活通过 `MFCreateVirtualCamera`。
- 持久注册策略：**Helper 服务（开机自启）** 调用 `IMFVirtualCamera::Start`，关闭时 `Shutdown`。
- 关键接口：`IMFMediaSource`、`IMFMediaStream`、`IMFAttributes`、`IKsControl`（用于 PnP/属性集）。
- 帧 IPC：与 DShow 共用同一份 Frame Bus（共享内存环），由 Helper 单例供帧。
- ACL：命名对象使用包含 `S-1-15-2-1`(`ALL_APP_PACKAGES`) 与具体 Frame Server LowBox SID 的 SDDL。
- 跨架构产物：x64 + ARM64 双产物；x86 不再单独支持（Win11 已不发 x86）。

### 3.3 macOS: CMIO Camera Extension 选型

- 形式：**`.systemextension`，App Bundle 内嵌**，首次运行通过 `OSSystemExtensionRequest` 安装。
- 实现语言：**Swift**（Extension 部分）+ **Obj-C++ 桥接**（与 Python/PySide6 通信的 XPC 客户端用 PyObjC）。
- 关键类：`CMIOExtensionProvider/Source`、`CMIOExtensionDevice/Source`、`CMIOExtensionStream/Source`。
- 帧 IPC：**IOSurface**（零拷贝）+ **XPC**（控制面）+ **Mach Port** 通知；备用 POSIX 共享内存。
- App Group：`group.com.akvc.shared` 用于跨进程共享 IOSurface 注册表。
- entitlements：
  - Container App：`com.apple.developer.system-extension.install`
  - Extension：`com.apple.developer.driverkit`（如未来转 DriverKit 路径）/ Camera Extension 默认无需，但需 `Hardened Runtime`。
- 安装器：PKG，内含 Helper Service（launchd plist）用于持久启动 Producer 守护。

### 3.4 桌面应用栈

- 语言：Python 3.12（PEP 703 之外仍走 GIL，但帧密集处放 C 扩展/原生层）。
- 框架：PySide6（Qt 6.6+）。
- 模式：**MVVM**：
  - Model：`camera-core`（设备、Pipeline、配置）。
  - ViewModel：`Qt Property` + `Signal/Slot`，承载 UI 状态。
  - View：QML 或 Widgets（首选 Widgets，QML 二期）。
- 视频：OpenCV-headless（避免 Qt 冲突）+ NumPy（避免 PIL 拷贝）。
- AI 预留：ONNX Runtime（DirectML on Win, CoreML EP on Mac）+ MediaPipe Tasks（人脸/分割）。
- 异步：`asyncio` + `qasync`，IO/控制面用协程，帧路径用线程/进程。
- 帧路径运行时：单独的 **Frame Worker 进程**（`multiprocessing` + `SharedMemory`）避免 GIL 阻塞 UI。

### 3.5 IPC 选型

| 平台 | 控制面 | 数据面 | 同步 |
|---|---|---|---|
| Windows | 命名管道 (`\\.\pipe\akvc-ctrl`) | 命名共享内存 (`Local\akvc-frames`) Ring × 4 | `CreateEvent` × 2（producer/consumer） + Mutex |
| macOS | XPC connection | IOSurface（按帧分配，4-deep ring） | `dispatch_semaphore` + `os_unfair_lock` |

帧元数据头（C struct，平台一致）：

```
struct FrameHeader {
  uint32_t magic;        // 'AKVC'
  uint32_t version;
  uint32_t width;
  uint32_t height;
  uint32_t fourcc;       // NV12 / YUY2 / RGB24 / MJPG
  uint32_t stride[2];
  uint64_t pts_100ns;    // 100ns ticks since epoch
  uint64_t seq;
  uint32_t flags;        // keyframe / discontinuity
  uint32_t reserved;
};
```

### 3.6 帧格式与色彩

- **首选 NV12**：硬件友好，与 D3D11 NV12 纹理、IOSurface NV12 同构。
- 色彩空间：**BT.709 limited** 输出（视频会议主流），同时支持 BT.601 兼容。
- 处理管线在内部用 **BGR(A) uint8**（OpenCV 原生）或 **RGBA float16**（AI 段），交付前一次性转 NV12。
- 转换实现：CPU 用 `libyuv` / OpenCV，GPU 路径未来引入 D3D11 Compute / Metal Shader。

### 3.7 安装器选型

**Windows — NSIS**

- 选 NSIS 而非 Inno/MSIX 的理由：脚本灵活（要 `regsvr32` 双架构、要装 Helper 服务、要可视化驱动签名提示），社区成熟。
- 要做：管理员提权（`RequestExecutionLevel admin`）、版本检查、卸载残留检测、`regsvr32 /s` 双架构、Helper Service `sc create`、签名校验失败回滚。
- MSIX 路径未来追加（用于 Microsoft Store 发布），但不替代 NSIS。

**macOS — PKG**

- 使用 `pkgbuild` + `productbuild` + `Distribution.xml`，整体公证。
- 内含 preinstall/postinstall 脚本：检测旧版本 → 触发 `OSSystemExtensionRequest` 卸载旧 Extension → 安装新 App Bundle → 提示用户授权。
- 不用 DMG-only：DMG 缺少安装脚本能力，无法处理 Helper / launchd。

### 3.8 签名分发

| 平台 | 必需 | 可选/未来 |
|---|---|---|
| Windows | EV Code Signing 证书（DigiCert/Sectigo），SHA-256 双重签名 | MSIX + Microsoft Store；WHQL（DShow/MF 不强制，但可加分） |
| macOS | Apple Developer ID Application + Installer 双证书；Notarization；System Extension entitlement | TestFlight 不适用（系统扩展不上架）；MAS 同样不可 |

### 3.9 测试体系

- **单元**：`pytest` 覆盖 `camera-core` 与 ViewModel；`pytest-qt` 覆盖 PySide6 信号槽。
- **集成（host-side）**：通过 OBS / Zoom / Chrome 自动化（PowerShell + AHK / AppleScript）打开摄像头，截屏比对像素一致性。
- **端到端 Headless**：CI 上用合成帧（彩条 + 时间戳），消费端用 `ffmpeg -f dshow -i video="AK Virtual Camera"` / `ffmpeg -f avfoundation` 抓帧并校验时间戳单调与帧率。
- **离屏 UI**：`QT_QPA_PLATFORM=offscreen`（Linux runner 跑非平台相关测试），Win/macOS runner 跑平台层。
- CI：GitHub Actions `windows-2022`、`macos-14`（Apple Silicon）、`macos-13`（Intel）三 runner。

---

## 4. 依赖矩阵（顶层）

| 模块 | 依赖 | 备注 |
|---|---|---|
| `apps/desktop` | PySide6 6.6+, Pillow（仅图标）, qasync | 不直接依赖 OpenCV，避免冲突 |
| `camera-core` | numpy, opencv-python-headless, onnxruntime, mediapipe | 帧处理纯 Python + C 扩展 |
| `virtualcam/windows/dshow` | Windows SDK, ATL, baseclasses（DShow base） | C++17，CMake |
| `virtualcam/windows/mf` | Windows 11 SDK 22621+, mfsensorgroup.h | C++17/20 |
| `virtualcam/macos/extension` | Swift 5.9, CoreMediaIO, IOSurface, Foundation | Xcode 15+ |
| `installer/windows` | NSIS 3.09 + signtool | EV 证书 |
| `installer/macos` | pkgbuild, productbuild, notarytool | Developer ID |
| `tools/` | Python 脚本 + cmake/xcodebuild 包装 | 单一 `make.py` 入口 |

---

## 5. 模块边界（与 Phase 1 对齐）

```
┌────────────────────────────────────────────────────────────┐
│                    apps/desktop  (PySide6)                  │
│  View ── ViewModel ── Service Facade                        │
└────────────────────────────────────────────────────────────┘
              │  in-proc Python API
              ▼
┌────────────────────────────────────────────────────────────┐
│                     camera-core (Python)                    │
│  FrameProvider | FramePipeline | FrameSink (IPC writer)     │
│  Config | Metrics | Logging                                 │
└────────────────────────────────────────────────────────────┘
              │  Shared Memory / IOSurface
              ▼
┌────────────────────────────────────────────────────────────┐
│            virtualcam/  (Native, per-OS)                    │
│  windows/{dshow, mf, helper-svc}                            │
│  macos/{camera-extension, helper-launchd}                   │
│  shared/ (frame protocol header, ring impl)                 │
└────────────────────────────────────────────────────────────┘
              │  OS API
              ▼
┌────────────────────────────────────────────────────────────┐
│  OS Capture Stack                                           │
│  Windows: DirectShow / Media Foundation Frame Server        │
│  macOS:   CoreMediaIO / cmio assistant                      │
└────────────────────────────────────────────────────────────┘
```

---

## 6. 取舍与不做的事

为了控制范围，**Phase 0 选型阶段明确不做**：

- 不做 Linux v4l2loopback 适配（市场 ROI 低，可在 Phase 7+ 评估）。
- 不做 DAL Plug-In（macOS 弃用路径）。
- 不做内核态驱动（DShow / MF / CMIO Extension 全是用户态，符合现代 OS 安全模型）。
- 不做自研编码器；MJPEG 兜底用 `libjpeg-turbo`。
- 不做云端帧分发；仅本机 IPC。
- 不做 32 位 ARM 与 32 位 x86（市占近零）。

---

## 7. 选型回滚条件

如果在 Phase 2/3 中以下任何一条触发，回到 Phase 0 重新评估：

1. MF Virtual Camera 在 Windows 10 22H2 实测无法稳定加载 ≥3 个主流消费端 → 评估 DShow + 用户教育的折中。
2. macOS Camera Extension 申请 entitlement 被 Apple 拒绝超过 30 天 → 评估转 DAL（但只做内部分发版）+ 公开版仅做帧库 SDK。
3. PySide6 在 ARM64 macOS 上的 Qt 多媒体兼容性出现阻塞性 bug → 评估降级到 PyQt6 商业授权或 wxPython。

---

## 8. 决策回执

| 决策项 | 决定 | 决策人 | 触发回滚条件 |
|---|---|---|---|
| Windows 双栈 DShow + MF | 采纳 | 架构组 | §7-1 |
| macOS 仅做 Extension | 采纳 | 架构组 | §7-2 |
| 桌面端 PySide6 + MVVM | 采纳 | 架构组 | §7-3 |
| 主像素格式 NV12 | 采纳 | 架构组 | 无 |
| 安装器 NSIS / PKG | 采纳 | 架构组 | 无 |

→ 风险与缓解见 `risk-analysis.md`。
→ 选型获确认后，进入 Phase 1：系统架构设计。
