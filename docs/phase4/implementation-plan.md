# Phase 4 — macOS Camera Extension — Implementation Plan

**项目代号**：AK Virtual Camera
**阶段**：Phase 4 — macOS Camera Extension
**前置**：Phase 2（Windows DShow MVP）、Phase 3（Windows MF）已验收
**当前约束**：无 macOS 机器 → Build/Run/Test/Acceptance 全部 `BLOCKED`

> 本文档把 macOS 端的设计落地为可交付物。本轮交付的是**设计 + 骨架 +
> 构建/签名 runbook**，不声明可编译可运行（缺 Mac）。所有无法离线
> 核对的 API 调用点在代码中以 `// VERIFY` 标注，列入本文档 §6。

---

## 1. 范围

### 1.1 In Scope（本轮 + 后续 Mac 联调）

| 模块 | 交付物 |
|---|---|
| `virtualcam/macos/framebus/` | POSIX shm 消费者（C），复用 `akvc_protocol.h` |
| `virtualcam/macos/CameraExtension/` | CoreMediaIO Camera Extension（Swift）：Provider/Device/Stream/Reader |
| `virtualcam/macos/host/` | 激活扩展的 Host app（Swift） |
| `virtualcam/macos/project.yml` | XcodeGen 工程描述 |
| `camera-core/.../frame_sink/macos_shm.py` | Python POSIX shm 生产者（镜像 `windows_shm.py`） |
| `camera-core/.../frame_sink/_protocol.py` | 跨平台共享协议常量（单一真值） |
| `tools/make.py` | macOS 分支（xcodegen + xcodebuild） |
| `docs/phase4/` | 设计/构建/签名/调试/验证 五份 |
| `.claude/rules/macos.md` | macOS 专项验收叠加规则 |

### 1.2 Out of Scope

| 项 | 推迟到 |
|---|---|
| XPC + IOSurface 实现 | 仅作文档 Plan B，`shm_open` 沙盒被挡时启用 |
| 真正的签名/公证执行 | 有 Mac + Developer ID 后 |
| AI 美颜、Crashpad/OTel | 沿用 Phase 2 推迟 |
| Host app 占位帧发布 | Phase 4 联调期补（`FrameBusReader.publishPlaceholder` 是 stub） |
| Python↔Host 激活桥接 | 联调期补 |

---

## 2. 技术决策

### 2.1 扩展类型：CoreMediaIO Camera Extension

macOS 12.3+ 唯一现代虚拟摄像头路径。旧 DAL（QuickTime）插件已弃用，
无法在 ARM64 / 新 macOS 上加载。Camera Extension 是 **System Extension**，
独立沙盒进程，需 `OSSystemExtensionRequest` 安装授权 + Developer ID 签名 + 公证。

### 2.2 IPC：POSIX 共享内存环形（用户已确认）

- 复用 `virtualcam/shared/akvc_protocol.h` 的 ring 控制块 + 4 槽 NV12 + seq 撕裂保护。
- Python 生产者 `macos_shm.py` 用 `shm_open("/akvc-frames-v1", O_RDWR|O_CREAT, 0o666)` 创建（`0o666` 让沙盒扩展可读）。
- 扩展端 C 消费者 `framebus_posix.c` 用 `shm_open(..., O_RDONLY)` + `mmap(PROT_READ, MAP_SHARED)`。
- **同步**：无跨进程 Event/Mutex。扩展以 30fps 轮询 ring + 依赖 seq_head/seq_tail 撕裂保护。POSIX 命名信号量在沙盒里同样有可用性风险，故不引入。
- **时间基**：`clock_gettime(CLOCK_REALTIME)` → 100ns ticks（Unix epoch）。Python 端 `time.time_ns()//100`，C 端 `clock_gettime`。与 Windows FILETIME（1601 epoch）**不同**，但 `producer_heartbeat` 字段语义是"同侧同源 100ns ticks"，跨平台无需对齐。

### 2.3 Plan B：XPC + IOSurface（沙盒被挡时）

若 `shm_open` 在扩展沙盒内被拒，切到 Apple 官方路径：
- Host app 创建 `IOSurface`（跨进程共享 buffer），通过 XPC 把 `IOSurface` + 帧元数据发给扩展。
- 扩展用 `CVPixelBufferCreateWithIOSurface` 零拷贝包成 `CVPixelBuffer`。
- 代价：Python 生产者需原生桥接创建 IOSurface + XPC（新增不少原生代码）。

本轮不实现，仅记录。

### 2.4 帧交付（VERIFY 重灾区）

`CMIOExtensionStream` 把 `CMSampleBuffer` 投递给消费端的确切 API 是本轮
最大未知（见 §6 VERIFY-1）。骨架中 `Stream.pushFrame` 已隔离该调用点。

### 2.5 region 归属（与 Windows I4 差异）

| 平台 | region 拥有者 | 理由 |
|---|---|---|
| Windows | Helper（admin） | `Global\` 需 `SeCreateGlobalPrivilege` |
| macOS | Python sink（谁先启动谁创建，0666） | 无 helper.exe；信任链靠签名/公证建立 |

Phase 4 的 I4（跨进程对象由可信进程拥有）由 **签名/公证的 host app +
扩展** 承担：只有签名的扩展能读 region，恶意进程虽可 `shm_open` 但写入
会被扩展的 schema/tear 校验拒绝（非安全边界，仅为健壮性）。

---

## 3. 模块拆解

### 3.1 Native（Swift + C）

```
virtualcam/macos/
├── project.yml
├── framebus/                         # C（可移植）
│   ├── include/akvc/framebus_posix.h
│   └── src/framebus_posix.c
├── CameraExtension/                  # Swift System Extension
│   ├── CameraExtension.swift
│   ├── Provider.swift                # CMIOExtensionProvider
│   ├── Device.swift                  # CMIOExtensionDevice
│   ├── Stream.swift                  # CMIOExtensionStream
│   ├── FrameBusReader.swift          # C → CVPixelBuffer
│   ├── CameraExtension-Bridging-Header.h
│   ├── Info.plist
│   └── CameraExtension.entitlements
└── host/                             # Swift app
    ├── main.swift                    # OSSystemExtensionRequest
    ├── Info.plist
    └── HostApp.entitlements
```

### 3.2 Python

```
akvc/core/frame_sink/
├── _protocol.py          # NEW: 跨平台共享协议常量
├── windows_shm.py        # 重构为 import _protocol（行为不变）
├── macos_shm.py          # NEW: POSIX shm 生产者
├── __init__.py           # NEW: create_sink() 平台分发
└── base.py               # 不变
```

### 3.3 跨平台改动

- `apps/desktop/akvc_app/workers/frame_worker.py`：`WindowsShmSink()` → `create_sink()`；平台守卫放行 `darwin`。
- `apps/desktop/akvc_app/services/facade.py`：`HelperService` 仅 Windows 实例化；macOS 路径跳过 `register_mf`，`_mf_registered` → `_device_registered`。
- `virtualcam/shared/akvc_protocol.h`：加 `AKVC_POSIX_SHM_NAME` 宏 + macOS 时间基注释。
- `tools/make.py`：加 `darwin` 分支（`cmd_*_macos`），main() 平台分发。

---

## 4. 与 Phase 1 不变量复核

| 不变量 | Phase 4 满足度 | 说明 |
|---|---|---|
| I1 — UI 崩溃设备不消失 | 满足 | 扩展是 System Extension，独立于 Python 进程；Python 崩溃 → 扩展读不到帧 → 发占位黑帧（`flags=PLACEHOLDER`） |
| I2 — 安装/卸载干净 | 满足 | host app `OSSystemExtensionRequest` 装载；`systemextensionsctl uninstall` 卸载，幂等 |
| I3 — 故障不抖动 | 满足 | 扩展内 `isProducerAlive` 判定 → 占位帧；tear 帧丢弃 |
| I4 — 跨进程对象由可信进程拥有 | 部分 | region 由 Python 创建（0666）；信任链靠签名扩展。安全边界弱于 Windows，标注为已知限制 |
| I5 — MVVM 边界 | 满足 | facade 平台分支不影响 MVVM 分层 |

---

## 5. 与 Windows 端差异表

| 维度 | Windows | macOS |
|---|---|---|
| 技术栈 | DShow Source Filter + MF VirtualCamera | CoreMediaIO Camera Extension |
| 语言 | C++17 | Swift + C |
| 扩展进程模型 | in-proc（DShow）/ frameserver.exe session 0（MF） | 独立 System Extension 沙盒进程 |
| 共享内存 | `Global\` 命名 file mapping | `shm_open` POSIX |
| 同步对象 | named Event + Mutex | 无（轮询 + tear 保护） |
| 时间基 | FILETIME 1601 epoch | CLOCK_REALTIME Unix epoch |
| 设备聚合 | DShow + MF 同名 → Win11 聚合 | 单一 Camera Extension，天然单设备 |
| 签名 | 可选（regsvr32 即可） | **强制** Developer ID + 公证 |
| 安装 | regsvr32 / NSIS | host app OSSystemExtensionRequest（用户授权） |

---

## 6. VERIFY 清单（拿到 Mac 后第一件事）

| # | 位置 | 未知点 | 对照 |
|---|---|---|---|
| V-1 | `Stream.swift` pushFrame | `CMIOExtensionStream` 投递 `CMSampleBuffer` 的 API | Apple CameraExtension sample |
| V-2 | `Stream.swift` clock | `CMIOExtensionClock` resume/pause/advance + `consumeClockValue` | CMIOExtensionStream.h |
| V-3 | `Provider/Device/Stream.swift` | `attach`/`detach` 与各 init 签名 | CMIOExtension*.h |
| V-4 | `Info.plist` | `CMIOExtension` provider key + `NSExtensionPointIdentifier` | sample plist |
| V-5 | `CameraExtension.entitlements` | camera-extension entitlement 键名 | provisioning profile |
| V-6 | `framebus_posix.c` / 扩展运行时 | **`shm_open` 沙盒是否放行**（头号风险） | on-device test → 若挡则 Plan B |
| V-7 | `FrameBusReader.swift` | C 函数 Swift 导入名 / struct tuple 映射 | bridging header build |

---

## 7. 风险与回滚

| 风险 | 触发 | 回滚 |
|---|---|---|
| `shm_open` 沙盒拒绝 | 扩展读不到 region | 切 Plan B（XPC + IOSurface） |
| Frame delivery API 记错 | 编译失败 / 客户端收不到帧 | 对照 sample 修 V-1 |
| 签名/公证失败 | 扩展无法加载 | 按 signing runbook 排查 entitlements/hardened runtime |
| CLOCK_REALTIME 与 Python 不一致 | 扩展误判 producer 死亡 → 一直黑屏 | 两端统一 `time.time_ns//100` ↔ `clock_gettime` |
| Camera Extension 不被 FaceTime 枚举 | Info.plist/entitlements 错 | V-4/V-5 |

---

## 8. 出口（待 Mac 上达成）

1. `uv run tools/make.py build` → `xcodebuild` 退出 0，`.systemextension` 产物存在。
2. 签名 + 公证通过（`xcrun notarytool` 返回 accepted）。
3. host app 启动 → 扩展授权成功 → `log stream` 见 `akvc.ext.provider.start`。
4. VC-M-1~5 全 PASS（FaceTime/Zoom/Safari/OBS 发现 `AK Virtual Camera`）。
5. `pytest -q` 含 macOS sink 单测全绿。

本轮：以上 1~5 全部 `BLOCKED`（缺 Mac）。
