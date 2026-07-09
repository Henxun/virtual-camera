# macos.md — macOS Camera Extension 专项规则

> 凡是涉及 macOS 摄像头通路的任务，叠加本文件。
> 与 `virtual-camera.md` Phase 4 节、`docs/phase4/*` 配套使用。
> **任意一项失败 = INCOMPLETE + 自动 Debug Loop**（无 Mac 时标 BLOCKED）。

## 1. 阅读顺序（macOS 任务强制）

1. `.claude/CLAUDE.md`
2. `.claude/rules/workflow.md` / `build-loop.md` / `debugging.md` / `acceptance.md`
3. `.claude/rules/virtual-camera.md`（Phase 4 节）
4. 本文件
5. `docs/phase4/implementation-plan.md`

## 2. 技术栈与红线

- **CoreMediaIO Camera Extension**（System Extension）。当前仓库基线为 **Objective-C++ + C/C++**，禁止把旧 Swift 方案继续当作当前实现真值。
- 最低 macOS 12.3。
- System Extension 在非调试 Mac 上**强制** Developer ID 签名 + 公证。调试期用 `systemextensionsctl developer on`。
- IPC 默认走 POSIX shm（`/akvc-frames-v1`）。**头号风险**：扩展沙盒是否放行 `shm_open`。被挡则切 Plan B（XPC + IOSurface），须更新 `docs/phase4/implementation-plan.md` §2.3 与对应 memory。

## 3. 验收叠加（与 virtual-camera.md Phase 4 一致）

VC-M-1~5 为强制项；纯 API/CLI 类（VC-M-1、IPC 自检）在有 Mac 时**必须 Agent 自己跑通**，不允许标 BLOCKED。图形消费端（FaceTime/Zoom/Safari/OBS）无图形环境时标 BLOCKED + 用户验证脚本。

## 4. 时间基红线

macOS heartbeat 用 `clock_gettime(CLOCK_REALTIME)` → 100ns ticks（Unix epoch）。
- Python 生产者：`time.time_ns()//100`
- C / ObjC++ 消费者：`clock_gettime`

**禁止**用 `perf_counter` / `mach_absolute_time`（无绝对时间基会让扩展误判 producer 死亡 → 占位帧覆盖真实帧，复现 Windows 端的同名 bug）。

## 5. 调试 RCA 清单（macOS 专项）

| 失败项 | 优先排查 |
|---|---|
| 扩展不加载 | `systemextensionsctl list` 状态、签名/公证/entitlements、Hardened Runtime |
| `akvc_fb_open` 失败 st=-1001 | shm_open 被沙盒挡（Plan B）；或 region 未创建 |
| 设备在但黑屏 | 帧路径（producer_seq 是否递增、torn/timeout 日志）、frame delivery API |
| 画面不动 | 时间基不一致（§4）、start/stream 事件缺失 |
| 客户端 Timeout | `Start()` 未发足够事件 / clock 推进 |
| 公证失败 | `xcrun notarytool log`；Hardened Runtime / timestamp / 未授权 entitlement |

## 6. 签名/公证必经步骤（不可跳过）

1. Developer ID Application 证书 + Team ID。
2. 工程配置中设置 `CODE_SIGN_IDENTITY="Developer ID Application"`、`DEVELOPMENT_TEAM`、`ENABLE_HARDENED_RUNTIME=YES`。
3. camera-extension 相关 entitlements 必须在 App ID / provisioning 配置中启用。
4. `codesign --deep --options runtime --timestamp`。
5. `xcrun notarytool submit --wait` → Accepted。
6. `xcrun stapler staple`。

详见 `docs/phase4/signing-notarization.md`。

## 7. 当前状态纪律

- 历史上的“Swift skeleton / no Mac available / 全 BLOCKED”只可作为历史背景，不可继续当作当前实现状态。
- 当前仓库若出现与 `docs/macos/architecture.md`、已验收代码路径冲突的 Phase 文档，应当修正文档，而不是按过期文档回退实现方向。
- 若后续引入新的 native data path（例如 XPC + IOSurface），必须同时更新本规则、Phase 4 文档与验收脚本。

## 8. 跨平台一致性

改动 `akvc_protocol.h`、`_protocol.py`、frame schema 时，必须同时更新
Windows（`windows_shm.py` / `framebus.cpp`）与 macOS（对应 shm / framebus 实现）两侧。schema 是双平台 ABI，单边修改 = 破坏另一侧。

## 9. 例外

- 纯文档/规则变更：Build/Run/Test 闸 `N/A (docs only)`，Acceptance = docs 自洽 + 与 `virtual-camera.md` Phase 4 / `docs/phase4/*` 不冲突。
- 无 Mac 环境：四闸可标 BLOCKED，但必须附"用户验证脚本"。
