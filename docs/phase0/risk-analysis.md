# Risk Analysis — Cross-Platform Virtual Camera

**项目代号**：AK Virtual Camera
**文档版本**：v1.0
**阶段**：Phase 0 — 风险分析
**日期**：2026-06-19
**前置文档**：`architecture-research.md`、`technology-selection.md`

> 商业级虚拟摄像头的失败几乎不在功能本身，而在签名、沙盒、版本碎片、消费端兼容、用户授权这五个看不见的角落。
> 本文系统化地识别风险、分级评估、给出可执行缓解方案，并指定每个风险的 owner 与触发指标。

---

## 1. 风险评估方法

- **影响（Impact, I）**：1=轻微、2=可绕过、3=阻塞部分用户、4=阻塞主路径、5=不可发布。
- **概率（Likelihood, L）**：1=极低、2=低、3=中、4=高、5=必然。
- **风险分（R = I × L）**：≥15=红、9–14=黄、≤8=绿。
- 每条风险包含：背景、触发指标、缓解策略、owner、复核节奏。

---

## 2. 风险登记册（Top-Level）

| 编号 | 风险 | 类别 | I | L | R | 等级 |
|---|---|---|---|---|---|---|
| R-01 | Windows EV 代码签名延迟/失败 | 签名分发 | 5 | 3 | 15 | 🔴 |
| R-02 | macOS System Extension entitlement 被拒 | 签名分发 | 5 | 3 | 15 | 🔴 |
| R-03 | MF Frame Server 沙盒 ACL 错误导致黑屏 | 兼容/沙盒 | 4 | 4 | 16 | 🔴 |
| R-04 | DShow 在新版 Teams/Chrome 不可见 | 兼容性 | 3 | 5 | 15 | 🔴 |
| R-05 | macOS 13/14/15 用户授权流程改动 | OS 演进 | 4 | 3 | 12 | 🟡 |
| R-06 | ARM64 Windows 兼容/性能不达标 | 架构覆盖 | 3 | 3 | 9 | 🟡 |
| R-07 | 反作弊（EAC/Vanguard/BattlEye）拦截注入 | 兼容性 | 3 | 4 | 12 | 🟡 |
| R-08 | 1080p30 性能不达标（CPU>20%） | 性能 | 3 | 3 | 9 | 🟡 |
| R-09 | Python GIL 导致 UI 与帧路径互相饿死 | 架构 | 3 | 3 | 9 | 🟡 |
| R-10 | IPC 共享内存撕裂 / 帧错位 | 数据正确性 | 4 | 2 | 8 | 🟢 |
| R-11 | 升级安装时旧 DShow filter 残留 | 安装/卸载 | 3 | 3 | 9 | 🟡 |
| R-12 | 多消费端并发抢占 / 引用计数泄漏 | 稳定性 | 4 | 2 | 8 | 🟢 |
| R-13 | macOS Apple Silicon vs Intel 行为差异 | 兼容性 | 3 | 2 | 6 | 🟢 |
| R-14 | 用户安装后 Camera 系统权限未授予 | 用户体验 | 3 | 3 | 9 | 🟡 |
| R-15 | Helper Service 被杀死或未自启 | 稳定性 | 4 | 2 | 8 | 🟢 |
| R-16 | OBS/Zoom 自动化测试在 CI 不稳定 | 测试体系 | 2 | 4 | 8 | 🟢 |
| R-17 | 商标/命名冲突（"AK Virtual Camera"） | 法务 | 3 | 2 | 6 | 🟢 |
| R-18 | LGPL/GPL 边界——OBS 代码参考导致传染 | 法务 | 5 | 2 | 10 | 🟡 |
| R-19 | Windows 10 22H2 MF VirtualCam 缺失 KB | OS 演进 | 3 | 3 | 9 | 🟡 |
| R-20 | 反病毒（Defender SmartScreen / 360 / Avast）误报 | 用户体验 | 4 | 3 | 12 | 🟡 |

总览：5 红、9 黄、6 绿。下文按红→黄→绿展开。

---

## 3. 红色风险（必须前置缓解）

### R-01 Windows EV 代码签名延迟/失败

**背景**：EV 证书签发需 KYC 审核，HSM/USB Token 模式签名链路复杂；未签名 DLL 在 SmartScreen、AppLocker、企业策略下会被拦截。MF VirtualCamera 加载到 frameserver LowBox 容器，签名缺失会直接拒绝加载。

**触发指标**：

- 安装后 OBS/Zoom 中设备不可见且 `Event Viewer / Applications and Services / Microsoft / Windows / Frameserver-Diagnostic` 出现 ACCESS_DENIED 或 SIGNATURE 相关错误。
- SmartScreen 弹"未识别的发布者"。

**缓解**：

1. 立项 **第 0 周** 即启动 EV 证书采购（DigiCert/Sectigo），通常 5–15 工作日。
2. 双重签名：SHA256（主）+ SHA1（兼容老系统，不再强制）。
3. CI 集成签名步骤，使用 Azure Key Vault 或 SignPath 远程签名，避免本地 USB Token 单点故障。
4. 准备**未签名 dev 版本** + 测试机开 `bcdedit /set testsigning on`，开发期不阻塞。
5. 保留备用 OV 证书一张，用于内部测试与紧急回滚。

**Owner**：发布工程组 / 法务
**复核**：每周

---

### R-02 macOS System Extension entitlement 被拒

**背景**：`com.apple.developer.system-extension.install` 与（如 DriverKit 路径）`com.apple.developer.driverkit.*` 需 Apple 单独审批。CMIO Camera Extension 自身不强制审批，但 Container App 安装它需要前述 entitlement，并经过公证。

**触发指标**：

- `OSSystemExtensionRequest` 报错 `OSSystemExtensionErrorCodeUnknown` 或 `Request rejected`。
- Apple Developer 后台申请超过 30 天无回复。

**缓解**：

1. 项目立项即提交 entitlement 申请，附使用场景描述与 demo 视频。
2. 设计 **降级方案**：在 entitlement 未到位前，发布 Internal Build 仅用于内测；不退化到 DAL（弃用路径）。
3. 维护 Apple DTS（Developer Technical Support）申诉模板。
4. Bundle ID 与 Team ID 在第 1 周确定并不再变更（变更会导致 entitlement 重新审批）。

**Owner**：发布工程组
**复核**：每周

---

### R-03 MF Frame Server 沙盒 ACL 错误导致黑屏

**背景**：MF VirtualCamera 的 Media Source DLL 由系统 `frameserver.exe` 加载，进程运行在 LowBox AppContainer 中，能力受限：默认无法读取我们 UI 进程创建的命名共享内存与互斥。

**触发指标**：

- DShow 路径正常 / MF 路径黑屏。
- `frameserver.exe` 中 `OpenFileMappingW` 返回 ERROR_ACCESS_DENIED（用 ProcMon 抓到）。

**缓解**：

1. 命名内核对象的 SDDL 必须授予 `S-1-15-2-1`(`ALL_APP_PACKAGES`) 与具体 frameserver SID。
2. UI 进程创建对象后，调用 `SetSecurityInfo` 显式追加 ACE。
3. 引入"自检命令" `akvc-doctor.exe`：模拟 LowBox 打开对象，输出诊断。
4. 文档化：用户在企业策略下可能仍受 SRP/AppLocker 影响，提供 ADMX 模板。

**Owner**：Windows 原生组
**复核**：每周（在 Phase 3 期间每日）

---

### R-04 DShow 在新版 Teams/Chrome 不可见

**背景**：Teams 新版与 Chromium-based 浏览器（Chrome/Edge）已切到 MF Capture Engine，DShow 路径在这些客户端不可见。这就是双栈策略存在的本因。

**触发指标**：

- 用户报"在 Teams/Chrome 看不到 AK Virtual Camera"。
- Phase 2 验收时这些客户端无法识别（**符合预期**）。

**缓解**：

1. **Phase 2 仅承诺 OBS/Zoom/微信/QQ/Discord 兼容**，文档明确写出 Teams/Chrome 需 Phase 3 才覆盖。
2. Phase 3 上线 MF VirtualCamera 后立即覆盖，规避用户预期落差。
3. 桌面应用 UI 在状态栏明示当前激活的"摄像头驱动"是 DShow 还是 MF。

**Owner**：产品 + 架构组
**复核**：Phase 2 验收 / Phase 3 验收节点

---

### R-20 反病毒误报（Defender SmartScreen / 360 / Avast）

**背景**：虚拟摄像头的"在 frameserver 加载未知 DLL + 共享内存 + Helper Service"模式，与某些恶意软件特征高度相似，初次发布被误报概率高。

**触发指标**：

- VirusTotal 扫描有 ≥1 引擎报警。
- Defender SmartScreen 拦截。
- 360 / Tencent / Huorong 弹窗。

**缓解**：

1. EV 签名 + 长期使用稳定的发布者名 → 累积 SmartScreen 信誉。
2. 发布前向 **Microsoft Defender、360、火绒、QQ 安全管家、Avast、Kaspersky** 主动提交白名单。
3. Helper Service 命名与服务描述清晰、不混淆。
4. 安装器签名 + 公证日志中无空 timestamp。
5. 发布前 VirusTotal 自检，通过率 < 100% 不发版。

**Owner**：发布工程组
**复核**：每次发布

---

## 4. 黄色风险（计划期内必须缓解）

### R-05 macOS 13/14/15 用户授权流程改动

每个 macOS 主版本对 System Extension 与 Camera Extension 的提示文案、跳转入口、TCC 行为都有微调。**缓解**：维护 OS 矩阵测试机（13.x、14.x、15.x），每个 macOS GM 发布后 7 天内回归。

### R-06 ARM64 Windows 兼容/性能

**缓解**：第一日就交付 ARM64 native 二进制；不靠 x64 模拟。NumPy/OpenCV 选 ARM64 wheel，OpenCV 自编 ARM64 with NEON。

### R-07 反作弊拦截

**缓解**：DShow Source Filter 在游戏进程内可能被反作弊拦截。对策：①官方文档中说明"游戏内不保证可用"，②MF 路径 Frame Server 在系统进程，不进游戏进程，不触发反作弊；③与主流游戏厂商联系白名单流程（长尾）。

### R-08 1080p30 性能（CPU>20%）

**缓解**：

- 帧路径 NumPy/OpenCV 全 NV12 in-place；避免 `cv2.cvtColor` 多次往返。
- 共享内存零拷贝；不通过 socket 传字节流。
- 美颜/AI 段在独立进程，UI 与帧路径解耦。
- 性能基准在 CI 上每提交跑：`pytest tests/perf/ -k 1080p30 --max-cpu-percent=20`。

### R-09 Python GIL 导致饿死

**缓解**：将 Frame Worker 放进 `multiprocessing` 子进程；UI 进程只负责控制面与少量预览。共享内存避免 IPC 拷贝。

### R-11 升级安装残留

**缓解**：安装器先调 `akvc-doctor uninstall --legacy` 清掉旧 CLSID 注册、旧 Helper Service、旧 Frame Server 持久注册；再安装新版。CI 用 Sandbox VM 测试 0.x→1.x→2.x 的升级路径矩阵。

### R-14 用户安装后 Camera 权限未授予（macOS）

**缓解**：首启动检测 `AVCaptureDevice.authorizationStatus(for: .video)`；未授予则在 UI 内引导用户去 System Settings；提供"重新检测"按钮。

### R-18 LGPL/GPL 边界

**背景**：OBS Studio GPLv2，`obs-virtualcam` 同源。"参考"代码若直接复制改写存在 GPL 传染风险。

**缓解**：

1. 我们的代码 **从规范与官方头文件出发**，参考开源实现仅为理解机制，**不复制源码**。
2. 法务 review：自研代码许可证用 Apache-2.0 或 MIT；与第三方代码隔离。
3. 引入 SBOM（CycloneDX）跟踪每个第三方组件的 License。
4. 所有提交需通过 `reuse lint` 检查 SPDX header。

### R-19 Windows 10 22H2 MF VirtualCam 缺失 KB

**缓解**：检测目标 OS build；若 < 19045.最低支持 build，UI 提示用户升级；否则 fallback 到 DShow。

---

## 5. 绿色风险（监控、不阻塞）

- **R-10 共享内存撕裂**：序列号 + 双互斥（producer / consumer），并在头部加 magic + 校验和；CI 跑 24 小时浸泡测试。
- **R-12 多消费端引用计数泄漏**：DShow Filter 用 `CUnknown` 标准实现，单元测试模拟开关 1000 次不泄漏；MF 端依赖 `IMFShutdown`。
- **R-13 Apple Silicon vs Intel 差异**：CI 双 runner 全量回归；性能基线分别建立。
- **R-15 Helper Service 被杀**：服务恢复策略：`failure restart/restart/restart`（Windows）；launchd `KeepAlive=true`（macOS）。
- **R-16 CI 自动化不稳定**：用录制式 UI 自动化（AHK/AppleScript）+ 重试 3 次 + 视频抓屏作为失败证据。
- **R-17 商标**：上线前做 USPTO + WIPO + 中国商标局检索；保留品牌备选。

---

## 6. 风险监控仪表盘（建议落地）

| 指标 | 阈值 | 告警 |
|---|---|---|
| 安装失败率（telemetry，opt-in） | >2% | 红 |
| 设备在 OBS/Zoom 不可见率 | >1% | 红 |
| 1080p30 平均 CPU 占用 | >20% | 黄 |
| Helper Service 异常退出/天/万台 | >1 | 黄 |
| 反病毒误报数（社区反馈） | ≥1 厂商 | 黄 |
| 升级失败回滚率 | >0.5% | 黄 |

实现路径：客户端嵌入 OpenTelemetry exporter（opt-in），上报到自有指标后端；不收集任何视频内容、不收集 PII。

---

## 7. 法务与合规清单

- [ ] EV Code Signing 证书采购（Windows）
- [ ] Apple Developer Program Enterprise/Individual + entitlements
- [ ] System Extension entitlement 申请
- [ ] 商标检索与注册
- [ ] 隐私政策 + 用户协议（首启动展示）
- [ ] 第三方依赖 License 清单（SBOM）
- [ ] 出口管制审查（如使用强加密：本项目不涉及，但保留检查项）
- [ ] 数据收集合规：GDPR/CCPA opt-in 模型

---

## 8. 应急预案

| 场景 | 应急动作 |
|---|---|
| 上线后大规模"找不到设备" | 灰度回滚到上一稳定版；启用 `--force-dshow` 命令行兜底；24h 内热修复 |
| 反病毒大面积误报 | 暂停下载链接；提交白名单；EV 证书 timestamp 校验；24–72h 修复 |
| Apple 推 macOS 大版本破坏兼容 | Beta 期纳入 OS 矩阵；GM 后 7 天内出兼容版；UI 内显眼提示 |
| EV 证书私钥泄露 | 立即吊销 + 重新签发；下架受影响版本；公开披露 |
| 卸载后残留导致用户系统异常 | 提供独立 cleanup tool；配合社区文档 |

---

## 9. 风险持续治理流程

- **每周**：架构组同步红/黄风险状态，更新 R 分。
- **每阶段验收**：复核所有红风险是否仍为红，未解决不允许进入下阶段。
- **每发布前**：跑完整风险检查清单（含签名、误报、矩阵测试），通过率 100% 才发布。
- **每事故后**：根因分析（RCA）→ 新增风险条目或调整等级。

---

## 10. Phase 0 风险结论

- 红色风险共 5 项，**均有可执行缓解路径**，不构成立项阻塞。
- 黄色风险需要在 Phase 1 架构设计中以"模块约束"方式体现（例如 ACL 设计、Helper Service 设计、性能预算）。
- 法务 / 签名 / 公证类风险时间敏感，**必须在 Phase 1 启动同期并行推进**，不可等到 Phase 2 上线前才动手。

→ Phase 0 三份文档全部完成，等待用户确认后进入 **Phase 1：系统架构设计**。
