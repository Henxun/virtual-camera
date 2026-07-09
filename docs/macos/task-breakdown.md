# macOS 任务拆分

**目标**：在不影响 Windows/Linux 的前提下，为项目增加 macOS 原生虚拟摄像头支持。  
**开发流程**：设计 -> 测试 -> 实现 -> 重构 -> 文档

## 1. 总体阶段

### Phase M0：设计冻结

交付物：

1. `docs/research/macos_virtual_camera_research.md`
2. `docs/macos/architecture.md`
3. `docs/macos/demo_app_design.md`
4. 本文档

完成标准：

1. 确认 Camera Extension 为正式路线
2. 确认不使用 Swift
3. 确认 Python 接口优先对齐 Windows `VirtualCamera`

### Phase M1：Python SDK 对齐测试

先写测试：

1. `VirtualCamera` 在 `darwin` 下的生命周期行为测试
2. `push_frame()` 输入类型测试
3. `started` / `consumer_count` 语义测试
4. `install_extension()` / `is_installed()` 抽象测试

再实现：

1. 抽象 macOS 平台类
2. 接入统一 SDK 入口
3. 不改变 Windows 测试结果

### 当前进展补充

15. 已继续把统一 Python 入口的构造语义向 Windows 侧对齐：
    - `MacVirtualCamera.__init__` 当前已正式接受 `helper_exe=None`
    - 当外部传入 `.app` 路径时，会映射为 `DefaultMacInstallerService(host_bundle=...)`
    - 当外部传入原生可执行文件路径时，会映射为 `DefaultMacInstallerService(host_executable=...)`
    - `VirtualCamera` 的 darwin 分支当前也会把 `helper_exe` 原样透传给 `MacVirtualCamera`
    - 已补充 SDK contract 与定向单测，防止后续再次出现“文档写着统一入口，但 macOS 实现并未真正接受同名参数”的漂移
16. 本轮继续把“指定构建产物做真机验收”的工具链参数透传补齐：
    - `tools/macos_smoke.py` 当前已从 `CommandMacInstallerService` 切到 `DefaultMacInstallerService`
    - `tools/macos_validation_report.py` 当前也改为走 `DefaultMacInstallerService`，`run-install` 路径会复用同一套 host/pkg 覆盖逻辑
    - `tools/macos_validation_session.py` 当前已新增并下传：
      - `--uninstall-tool`
      - `--sync-ipc-tool`
      - `--host-bundle`
      - `--host-executable`
      - `--pkg-path`
      - `--installer-executable`
      - `--disable-auto-package`
    - 这样 `smoke -> install-session -> validation-report` 三段链路现在都能绑定到指定 `akvc-host.app`、指定 `pkg` 与指定 runtime command tools 做人工验收
    - 已补充定向单测验证：
      - `smoke` 命令会带上 host env override
      - `validation_report --run-install` 会带上 host env override
      - `validation_session` 会把同一组覆盖项继续转发给 `smoke / install_session / validation_report`
17. 本轮继续把“本次人工验收到底绑定了哪一套 Host / Extension / PKG / runtime tools”收敛成稳定证据：
    - `tools/macos_validation_report.py` 当前会在 `runtime_assets.provenance` 中显式记录：
      - `host_bundle`
      - `host_executable`
      - `extension_bundle`
      - `package_install_command`
      - `auto_install_package`
    - `tools/macos_validation_session.py` 当前也会把这些 provenance 字段提升进 `session-manifest.json.summary`
    - `tools/macos_validation_session_summary.py` 当前会新增 `Runtime Asset Provenance` 小节，直接展开 Host App、Extension、PKG 与 runtime command tools 的实际路径
    - 已补充 validation-report / validation-session / session-summary 三条定向回归，避免后续只保留参数透传，却在最终人工验收摘要里丢失“这次到底验收的是哪一套工件”
18. 本轮继续把 runtime provenance 从“可见”推进到“可判定一致”：
    - `tools/macos_validation_report.py` 当前会继续比较：
      - runtime provenance 的 `host bundle / extension bundle`
      - runtime resolved assets 的 `sync-ipc tool / pkg`
      - `release-diagnostics` 中对应的 `app_bundle / extension_bundle / sync_ipc_tool / pkg`
    - 会输出 `runtime_release_*_identity_consistent`、`runtime_release_*_path_equal` 与聚合后的 `runtime_release_product_identity_consistent / runtime_release_product_path_equal`
    - `tools/macos_validation_session_acceptance.py` 当前也会把这组 identity consistency 纳入现有 `release_packaging_ready` 证据链：
      - 如果 runtime/验收链路与 release diagnostics 明确指向不同产品集，会直接把 `release_packaging_ready` 判为 `fail`
      - 如果当前会话没有足够路径证据，则不会把旧工件误伤成 `unknown`
    - 已补充 validation-report / validation-session / session-summary / acceptance 四条定向回归，并确认 `python3.12 tools/macos_native_verify.py` 仍通过
19. 本轮继续把上述 runtime/release 一致性门禁收紧到 helper contract 层：
    - `tools/macos_validation_session_contract.py` 当前已固定 runtime provenance 与 release paths 向 `session-manifest.json.summary` 的提升行为
    - `tools/macos_validation_session_summary_contract.py` 当前已固定 `Runtime Asset Provenance` 小节必须展示 runtime/release 路径与 identity/path-equal 结论
    - `tools/macos_validation_session_acceptance_contract.py` 当前已固定 “runtime/release product identity mismatch -> release_packaging_ready=fail” 的代表性回放 case
    - 已补齐三条 contract tool 定向单测，确认这条人工验收门禁不只存在于 helper 实现里，也被 contract 与总验证入口共同保护
20. 本轮继续把 `start(name=...)` 从“接口存在”推进到“原生可见配置链”：
    - Python `MacVirtualCamera.start(name=...)` 当前会先把目标摄像头名称持久化到默认 App Group 共享文件
    - `virtualcam/macos/ipc` 当前已新增设备名 override 解析能力，原生侧会按 `AKVC_DEVICE_NAME / AKVC_DEVICE_NAME_FILE` 或共享文件回退解析
    - Camera Extension `AKVCProviderSource` 当前会用该配置作为 Provider / Device 的默认可见名称
    - 原生 `AKVCDevicePrefix()`、`status` 与 `list-devices` 当前也会读取同一份设备名配置，避免 Python 侧请求名、系统枚举前缀和 Camera Extension 默认名继续分叉
    - 已补充 `macos_ipc`、`MacVirtualCamera`、native skeleton 与 topology contract 回归，并继续通过 `python3.12 tools/macos_topology_contract.py` 与 `python3.12 tools/macos_native_verify.py`
21. 本轮继续把“人工验收看到的设备名”收口到同一条配置链：
    - `build_verification_targets(...)` 当前已支持 `device_prefix`
    - Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime 六个目标应用的步骤、检查项与 ready 状态文案，都会优先使用当前运行时 `device_prefix`
    - `evaluate_extension_readiness(...)` 的 ready 步骤当前也会使用同一设备名，避免系统里已经叫 `Demo Camera`，但人工验收模板仍提示去找 `AK Virtual Camera`
    - `tools/macos_validation_report.py --write-manual-template` 当前会把这组动态设备名直接写进生成的 `manual-results.template.json`
    - 已补充 `test_macos_installer.py` 与 `test_macos_validation_report_tool.py` 定向回归
22. 本轮继续把 `validation-session --name` 与 `list-devices` 二进制自检的设备名前缀收口到同一条会话语义：
    - `tools/macos_list_devices_binary_check.py` 当前已支持 `--expected-prefix`
    - 若未显式传入，它会回退读取与 Camera Extension 相同的设备名共享配置，而不是固定写死 `AK Virtual Camera`
    - `tools/macos_validation_session.py` 当前会在自定义 `--name` 时把期望前缀继续下传给 `list-devices-binary-check`
    - 这样会话中的 PySide6 demo、系统枚举校验与最终 manifest 摘要在自定义设备名场景下会继续保持一致
23. 本轮继续把“设备名是否一致”变成摘要页和验收结论里的显式证据：
    - `tools/macos_validation_session_summary.py` 当前已新增 `Device Name Cohesion` 小节
    - 会直接展示 demo camera name、validation/install/list-devices 前缀与 `effective_device_prefix` 是否一致
    - `tools/macos_validation_session_acceptance.py` 当前也会把这组名字一致性证据并入 `system_camera_device_visible`
    - 当设备未枚举到时，失败/未知说明会优先引用当前运行时设备名，而不是一律写死 `AK Virtual Camera`
24. 本轮继续把设备名 override 语义前推到更底层的独立工具入口：
    - `tools/macos_smoke.py`、`tools/macos_install_session.py`、`tools/macos_validation_report.py` 当前都已新增 `--name`
    - 三个工具在真正调用 `status / install / list-devices` 前，会先写入 camera-name override 共享文件
    - 因此即使当前没有先跑 demo，仅运行 `smoke / install-session / validation-report` 也能让运行时 `device_prefix` 与后续验收模板保持一致
    - 已补充 smoke/install-session/validation-report 三条定向单测，直接验证 `--name -> override 文件 -> status/device_prefix` 这条链路
25. 本轮继续把“公开 Python 直推链路”前推到安装后验收工具：
    - `tools/macos_smoke.py` 当前已新增 `--run-direct-push-demo / --direct-push-demo-tool / --direct-push-frames`
    - `tools/macos_install_session.py` 当前也已新增同名参数，并会把 `tools/macos_direct_push_demo.py` 的结果收进 `install-session-report.json.direct_push_demo`
    - `tools/make.py smoke` 与 `tools/make.py install-session` 当前也已同步透传这组参数
    - 因此现在不必只靠 `validation-session` 聚合，单独执行 `smoke` 或 `install-session` 也能直接证明 `VirtualCamera.start() -> push_frame() -> close()` 公开对象路径是否跑通
    - `tools/macos_validation_session.py` 当前也已把 `smoke_direct_push_demo_*` 与 `install_session_direct_push_demo_*` 提升进 `session-manifest.json.summary`
    - 已完成语法校验与最小回放脚本验证：`smoke-direct-push-ok`、`install-session-direct-push-ok`、`make-smoke-wrapper-direct-push-ok`
26. 本轮继续把 Camera Extension demo bridge 的并发安全与回归证据补齐：
    - `AKVCFrameProvider` 当前已把 `selectFormatAtIndex / selectFrameDuration / closeFrameReader / storeClientSampleBuffer / copyLatestClientSampleBufferWithDiscontinuity / copyNextSampleBufferWithStatus / copyFallbackSampleBuffer / copyPlaceholderSampleBuffer` 收敛到同一把 `@synchronized(self)` 锁下
    - `copyLatestClientSampleBufferWithDiscontinuity(...)` 当前会在空缓存路径先清零 `outDiscontinuity`，并在成功返回后保留 `_latestClientSampleBuffer`、重新打当前 host timing；这样 source stream 在 sink 帧间隙重复最新真实帧，避免 OBS 看到真实帧与 placeholder 交替闪烁
    - demo fallback 的活动格式快照当前也会在同步块内读取，避免 live property change 与 fallback source 更新看到不一致的格式状态
    - 已新增 runtime smoke：验证客户端 sample buffer 只会被消费一次；若当前宿主环境不支持该 CoreMedia 路径，会显式 `skip` 而不是制造误报
    - 已新增源码契约测试：固定上述关键同步点与“保留最新 client frame、sink stop 清空缓存”语义，防止后续回归
    - 当前定向验证结果：
      - `tests/unit/test_macos_native_skeleton.py tests/unit/test_macos_ipc.py tests/unit/test_macos_framebus_contract_tool.py` -> `29 passed, 2 skipped`
      - `tests/unit/test_macos_runtime_sync.py tests/unit/test_macos_stream_contract_tool.py tests/unit/test_macos_virtual_camera.py tests/unit/test_macos_direct_sender.py tests/unit/test_macos_shm_sink.py` -> `100 passed`
      - `tools/macos_framebus_contract.py` -> `all_checks_passed=true`
27. 本轮把 demo 验收文档统一收敛到 GUI container app：
    - 以 `docs/macos/demo_app.md` 作为主 runbook
    - 文档当前覆盖：
      - `akvc-demo-app` 的构建方式
      - QuickTime / FaceTime / Zoom 的最小人工验收顺序
      - 与 `tools/make.py smoke` 的联动方式
      - demo bridge 相关常见排查入口
    - 已补充文档契约测试，并确认：
      - `test_macos_demo_app_doc_exists_and_covers_manual_acceptance` -> `pass`
28. 本轮把“独立原生 macOS demo app”的设计文档切回仓库内工作流：
    - 已新增 `docs/macos/demo_app_design.md`
    - 后续不再以 `docs/superpowers/*` 作为实现依据
    - `demo_app_design.md` 当前已经固定：
      - `akvc-demo-app` target 形态
      - `AppDelegate / MainWindowController / DemoControlService` 三层职责
      - 四个核心动作：刷新状态、启用 Demo 并激活、停用 Demo、复制验收步骤
      - 第一版验收标准与测试策略
29. 本轮继续推进 `Phase M3.5` 的第一批骨架实现：
    - 已新增 `akvc-demo-app` target，并接入：
      - `AppKit.framework`
      - `AKVCCommandSupport`
      - `AKVCSystemExtensionSupport`
      - `akvc-macos-ipc`
    - 已新增 `virtualcam/macos/demo_app/` 目录及最小 AppKit 文件集：
      - `main.mm`
      - `AppDelegate`
      - `MainWindowController`
      - `DemoControlService`
      - `Info.plist`
      - `DemoApp.entitlements`
    - `DemoControlService` 当前已直接复用：
      - `AKVCQuerySystemExtensionStatus(...)`
      - `AKVCVideoDeviceSnapshot()`
      - `AKVCSetDemoModeEnabled(...)`
      - `AKVCSubmitSystemExtensionRequest(...)`
    - 已新增 `docs/macos/demo_app.md`，覆盖构建、运行和 QuickTime / FaceTime / Zoom 的人工验收入口
    - 当前验证结果：
      - `tests/unit/test_macos_native_skeleton.py -k demo_app` -> `4 passed`
      - `tests/unit/test_macos_native_skeleton.py tests/unit/test_macos_ipc.py tests/unit/test_macos_framebus_contract_tool.py` -> `34 passed, 2 skipped`
      - `clang++ -fsyntax-only` 已通过 demo app + host support + ipc 组合编译检查
30. 本轮继续把 Demo App 从“字段展示”推进到“验收导向”：
    - `DemoControlService` 当前已新增：
      - `readiness_stage`
      - `next_action`
    - 阶段判断目前覆盖：
      - `not_activated`
      - `waiting_user_approval`
      - `ipc_not_ready`
      - `waiting_device_enumeration`
      - `ready_for_app_validation`
      - `host_or_install_blocked`
    - `MainWindowController` 当前已把 `Readiness stage / Next action` 直接显示到状态区
    - `docs/macos/demo_app.md` 当前也已补齐这两个字段的阅读方式，方便人工验收时快速定位“下一步该去系统设置、QuickTime 还是 IPC 工具链”
    - 当前验证结果：
      - `tests/unit/test_macos_native_skeleton.py -k demo_app` -> `4 passed`
      - `tests/unit/test_macos_native_skeleton.py tests/unit/test_macos_ipc.py tests/unit/test_macos_framebus_contract_tool.py` -> `34 passed, 2 skipped`
      - `xcodebuild -scheme akvc-demo-app -configuration Release CODE_SIGNING_ALLOWED=NO build` -> `BUILD SUCCEEDED`
31. 本轮继续把 Python/macOS 运行态证据从“工具侧零散拼装”推进到“SDK 统一快照”：
    - `MacVirtualCamera` 当前已新增 `runtime_snapshot()`
    - 该快照当前收敛：
      - `started / camera_name / width / height / fps`
      - `backend_name / using_direct_sender / shared_memory_fallback_used`
      - `direct_sender_*`
      - `last_frame_fourcc / last_frame_format_name / consumer_count`
      - `shared_memory_name`
      - `runtime_topology`
      - `ipc_descriptor`
      - `stream_capabilities`
      - `status`
    - `VirtualCamera` 当前也已透传 `runtime_snapshot()`，便于外部 PySide6 demo、验收脚本与上层应用直接复用
    - `tools/macos_direct_push_demo.py` 与 `tools/pyside6_virtual_camera_demo.py` 当前已优先读取该统一快照，而不是各自重复拼接运行态字段
    - 当前验证结果：
      - `tests/unit/test_macos_virtual_camera.py -k runtime_snapshot` -> `2 passed`
      - `tests/unit/test_sdk_virtual_camera.py -k runtime_snapshot_on_darwin` -> `1 passed`
      - `tests/unit/test_macos_virtual_camera.py tests/unit/test_sdk_virtual_camera.py` -> `99 passed`
      - `python3 -m py_compile camera-core/src/akvc/platforms/macos/virtual_camera.py camera-core/src/akvc/sdk/virtual_camera.py tools/macos_direct_push_demo.py tools/pyside6_virtual_camera_demo.py` -> `pass`
32. 本轮继续把 `runtime_snapshot()` 接进 direct-push / PySide6 验收工具：
    - `tests/unit/test_macos_direct_push_demo_tool.py` 当前已固定：
      - 直推报告必须包含 `runtime_snapshot`
      - 报告中的 `runtime_topology` 与关键运行态字段应可从统一快照读取
      - shared-memory fallback case 也必须反映到快照里
    - `tests/unit/test_pyside6_demo_tool.py` 当前已固定：
      - PySide6 demo 报告必须包含 `runtime_snapshot`
      - `numpy-direct` 与 `provider` 路径都要保留快照中的 backend/topology 证据
    - 当前验证结果：
      - `tests/unit/test_macos_direct_push_demo_tool.py tests/unit/test_pyside6_demo_tool.py` -> `31 passed`
      - `tests/unit/test_macos_virtual_camera.py tests/unit/test_sdk_virtual_camera.py tests/unit/test_macos_direct_push_demo_tool.py tests/unit/test_pyside6_demo_tool.py` -> `130 passed`

### Phase M2：IPC 最小闭环

先写测试：

1. RingBuffer 元数据编码/解码
2. slot 覆盖与序列号递增
3. producer / consumer 健康检查

再实现：

1. `platforms/macos/ipc`（仓库内实际映射到 `camera-core/src/akvc/platforms/macos/` 与 `virtualcam/macos/ipc/`）
2. Python 写帧
3. 原生读帧

### Phase M3：Camera Extension 最小设备闭环

先写测试：

1. Provider / Device / Stream 初始化测试
2. 安装状态查询测试
3. 基础 stream start/stop 测试

再实现：

1. `CMIOExtensionProvider`
2. `CMIOExtensionDevice`
3. `CMIOExtensionStream`
4. `FrameProvider`
5. `StreamSource`

### Phase M3.5：独立原生 Demo App

先写测试：

1. `akvc-demo-app` target 工程契约测试
2. `AppDelegate / MainWindowController / DemoControlService` 源码契约测试
3. `docs/macos/demo_app.md` 文档契约测试

再实现：

1. 新增独立原生 `akvc-demo-app` target
2. 建立单窗口 AppKit 验收控制台
3. 复用现有 `AKVCCommandSupport / AKVCSystemExtensionSupport`
4. 打通四个核心动作：
   - 刷新状态
   - 启用 Demo 并激活
   - 停用 Demo
   - 复制验收步骤
5. 形成 QuickTime / FaceTime / Zoom 的图形化人工验收入口

### Phase M4：端到端推帧

先写测试：

1. Python -> IPC -> Extension 闭环测试
2. `720p30` 基础输出验证
3. 占位帧 / 空帧行为测试

再实现：

1. `push_frame()` 真正打通
2. `CVPixelBuffer` / `CMSampleBuffer` 组装
3. 设备可被 QuickTime / OBS 枚举

### Phase M5：安装与分发

先写测试：

1. 安装状态检测测试
2. 卸载脚本幂等测试
3. 打包脚本输出检查

再实现：

1. `pkg`
2. `install`
3. `uninstall`
4. `sign`
5. `notarize`
6. `staple`

### Phase M6：性能与兼容性

先写测试：

1. `1080p60` 基准测试
2. CPU 指标采集
3. 长时稳定性测试

再实现或优化：

1. 内存复制优化
2. Shared Memory -> IOSurface 升级决策
3. Zoom / Teams / Meet / OBS / QuickTime / FaceTime 兼容修复

## 2. 模块级任务

### 2.1 `platforms/macos/ipc`

任务：

1. 定义 frame metadata ABI
2. 定义 slot 状态机
3. 实现 shared memory ring
4. 收敛 Python 侧 typed IPC surface（`MacFrameBusLayout / MacIPCDescriptor / MacStreamCapabilities`）
5. 让 SDK / Desktop / 验证链路共享同一套 `ipc_transport / shared_memory_name / supported_formats / supported_frame_rates` 语义
4. 预留 IOSurface 抽象层
5. 增加指标与调试字段

风险：

1. 多拷贝导致 CPU 超标
2. 跨进程生命周期管理复杂

### 2.2 `platforms/macos/camera_extension`

任务：

1. Provider 建模
2. Device 建模
3. Stream 建模
4. 格式与帧率声明
5. 原生 sample buffer 生成

风险：

1. Stream 时钟和节流实现错误
2. 应用识别但无法稳定出帧

### 2.3 Python SDK

任务：

1. 统一 `VirtualCamera` darwin 分支
2. 保持 Windows 语义不变
3. 增加输入归一化
4. 增加 macOS 安装查询能力

风险：

1. 平台分支过多导致 SDK 漂移
2. 额外接口破坏统一入口

### 2.4 安装与发布

任务：

1. 构建 app bundle
2. 嵌入 system extension
3. 生成 `pkg`
4. 生成 `dmg`
5. 生成 `zip`
6. 接入 notarization

### 2.5 原生 Demo App

任务：

1. 新增 `akvc-demo-app` target
2. 建立 `AppDelegate / MainWindowController / DemoControlService` 三层结构
3. 复用现有 demo mode 与 system extension 激活桥接
4. 输出图形化状态摘要、日志与人工验收提示

风险：

1. 若再次发明新的激活逻辑，会和现有 container app / 控制桥逻辑分叉
2. 若 UI 首版做得过重，会拖慢主链路验收

## 3. 当前建议的首轮实现顺序

1. 统一 SDK 测试和接口契约
2. Shared Memory Ring 最小实现
3. Camera Extension 空设备闭环
4. 独立原生 Demo App 验收控制台
5. Python -> Extension 推帧闭环
6. QuickTime / OBS 先打通
7. 再扩展 Zoom / Teams / Meet
8. 最后压 `1080p60` 性能

## 4. 每阶段状态模板

后续每阶段都应更新：

1. 当前状态
2. 已完成项
3. 风险
4. 下一步
5. 阻塞项

## 5. 当前状态（2026-06-26）

1. 已完成研究、总体架构、安装分发基线、Python/macOS SDK 骨架与 Camera Extension 原生骨架
2. 已完成安装阶段结果在 `SDK -> CLI -> Desktop` 三条链路的透传
3. 已完成桌面端安装向导文案、步骤清单与目标应用验证清单
4. 已补充 `tools/macos_benchmark.py` 与 `tools/make.py benchmark`，开始建立性能验收基线
5. 已补充 `PySide6VirtualCameraStreamer`，开始覆盖窗口/屏幕/自定义 provider 的实时推流辅助层
   - 当前还已把 `latest-provider` 与 `video-file` 升级为一等 streamer 入口：
     - `start_latest_frame_stream(...)`
     - `start_video_file_stream(...)`
   - 同时已把由 streamer 内部创建的 `OpenCVVideoFileProvider` 生命周期收口到 `stop()/切换 provider/耗尽停止`，避免视频文件推流遗留未释放的 `VideoCapture`
6. 已补充 `tools/macos_validation_report.py`，开始统一沉淀安装/枚举/benchmark/应用验证结果
7. 已补充 `tools/pyside6_virtual_camera_demo.py`，开始提供可运行的 PySide6 实时推流示例
8. 已补充 demo report -> validation report 的工件链路，开始为 “PySide6 直接调用” 建立可归档证据
9. 已补充 validation report -> manual template 的工件链路，开始为目标应用人工验收建立可填写模板
10. 已补充 `manual_validation_results.example.json` 与 manual-results 严格校验，开始固定真机验收记录口径
11. 已补充 `macos_validation_session.py`，开始把 demo / benchmark / template / report 串成单次验收会话
12. `macos_validation_session.py` 当前已覆盖 `numpy-direct / provider / latest-provider / image / pixmap / widget / screen / video-file` 八类 Python/PySide6 推流入口，其中 `video-file` 用于本地视频播放转推验收
13. `akvc.integrations.pyside6` 当前已补充 `LatestFrameProvider`，开始为 WebRTC / AI Avatar / 异步推理线程建立“最新帧提交 -> Qt 定时推流”的桥接基线
14. `tools/pyside6_virtual_camera_demo.py` 与 `macos_validation_session.py` 当前已补充 `latest-provider` 模式，开始为“异步提交最新帧”路径提供可运行示例与验证工件
15. 已继续把统一 Python 入口的构造语义向 Windows 侧对齐：
    - `MacVirtualCamera.__init__` 当前已正式接受 `helper_exe=None`
    - 当外部传入 `.app` 路径时，会映射为 `DefaultMacInstallerService(host_bundle=...)`
    - 当外部传入原生可执行文件路径时，会映射为 `DefaultMacInstallerService(host_executable=...)`
    - `VirtualCamera` 的 darwin 分支当前也会把 `helper_exe` 原样透传给 `MacVirtualCamera`
    - 已补充 SDK contract 与定向单测，防止后续再次出现“文档写着统一入口，但 macOS 实现并未真正接受同名参数”的漂移
15. `tools/pyside6_virtual_camera_demo.py -> tools/macos_validation_report.py -> tools/macos_validation_session.py` 当前还已继续打通 `video-file / latest-provider / widget / screen` 的会话级证据回传：
    - `validation_demo_mode`
    - `validation_demo_mode_supported`
    - `validation_demo_consumer_count`
    - `validation_demo_frame_source_kind`
    - `validation_demo_video_path`
    这样主 manifest 和 `session-summary.md` 现在不仅可以直接区分“本地视频文件转推”“最新帧桥接”“窗口抓取”“屏幕抓取”几类 PySide6 直推场景，也开始保留本次 demo 运行时观测到的 consumer 数
16. `macos_validation_session_acceptance.py` 当前已把 `demo_mode <-> frame_source_kind` 对应关系纳入 `pyside6_path_exercised` 验收门禁，避免 demo 跑过但来源语义漂移
17. `tools/macos_benchmark.py` 当前已补充 `profile / matrix` 能力，开始为 `720p / 1080p / 4K` 与 `30 / 60fps` 验收矩阵建立统一 JSON 工件口径
18. `macos_validation_session.py` 与 `tools/make.py validation-session` 当前开始透传 `benchmark-profile / benchmark-matrix`，用于把性能矩阵直接接入统一验收会话
    - 当前 `validation-report.json.summary -> session-manifest.json.summary -> session-summary.md` 也已开始继续提升 `benchmark_matrix_profiles` 明细，支持直接复盘每档 profile 的 `actual_fps / cpu_percent / avg_latency_ms / fps_target_met / cpu_target_met`
19. 已补充 `macos_capability_contract.py`，开始自动校验原生格式声明、状态上报与 benchmark matrix 的能力契约是否一致
    - 当前 contract 还已继续覆盖 `installer.py`、`macos_smoke.py`、`macos_install_session.py` 与 `macos_validation_report.py` 的 `supported_formats / supported_frame_rates` 透传面，避免 `4K60` 等能力只停留在原生状态层却在上层验收工件里丢失
    - 同时还会校验 `docs/benchmark/macos_virtual_camera_benchmark.md` 中的 profile 矩阵与 `tools/macos_benchmark.py` 保持一致，避免文档与工具在 `4K30 / 4K60` 命名或覆盖集合上漂移
20. 已补充 `macos_framebus_contract.py`，开始自动校验共享协议头、POSIX consumer 与 Python producer 的 Frame Bus ABI 契约是否一致
21. 已补充 `macos_stream_contract.py`，开始自动校验 Camera Extension 流语义，包括占位帧回退、超时/断裂丢帧、属性面和定时推流契约
22. 已补充 `macos_sdk_contract.py`，开始自动校验 `VirtualCamera` 与 `MacVirtualCamera` 的公开方法、属性、签名和上下文管理语义是否仍与现有 Windows SDK 形态对齐
23. `VirtualCamera` / `MacVirtualCamera` 当前还已显式上浮：
    - `readiness()`
    - `inspect_installation()`
    开始把 `status + devices + blocker_code + verification_targets` 收敛成 SDK 级统一快照，供 PySide6 / CLI / 自动化在真正 `start()` 前直接消费
    - `ServiceFacade.recheck_install_status()` 当前也会优先复用这份快照，避免桌面端继续重复枚举设备和重算 readiness 语义
24. 已收紧 `akvc.sdk.virtual_camera`、`akvc.platforms.macos.virtual_camera` 与 `akvc.core` 的惰性导入边界，当前 `status / install / enumerate_devices` 等安装侧路径已不再要求先加载 `numpy / cv2 / frame_input / frame_pipeline`
25. 已补充 `macos_input_contract.py`，开始自动校验 `QImage / QPixmap / numpy / OpenCV` 输入矩阵、PySide6 bridge / streamer 入口与 demo 模式面是否仍满足设计要求
    - 当前 contract 还已进一步覆盖 `akvc.sdk.virtual_camera` 与 `akvc.platforms.macos.virtual_camera` 的 `push_frame()/send()` 公共入口，避免后续只保留 helper 层支持却让 SDK 入口退化
26. 已补充 `macos_build_contract.py`，开始自动校验 `macOS 13.0`、`arm64 + x86_64`、`ONLY_ACTIVE_ARCH=NO` 与 `xcodebuild` 双架构传播约束，避免 `universal2` 目标只停留在文档描述
27. 已补充 `macos_app_matrix_contract.py`，开始自动校验 `Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime` 六个目标应用在安装器、`smoke`、报告、`session-manifest`、`session-summary` 与人工验收模板中的覆盖集合是否仍保持一致
28. 已补充 `macos_list_devices_binary_check.py` 与 `tools/make.py list-devices-binary-check`，开始对原生 `akvc-macos-list-devices` 命令的 JSON 结构、prefix 过滤语义与“过滤结果是 `all_devices` 子集”做独立回归
    - GitHub Actions / Jenkins 当前也会产出并归档 `build/macos/session/list-devices-binary-check.json`
    - `tools/macos_validation_session.py` 与 `tools/make.py validation-session` 当前也已支持 `--run-list-devices-binary-check / --list-devices-binary-check-tool`
    - 会话 manifest 的 `artifacts / steps / summary` 当前都会继续登记这份工件，并额外汇总 `present / passed / device_prefix / filtered_device_count / total_device_count / override_no_match_ok`
29. 已补充 `camera-core/src/akvc/platforms/macos/ipc.py`，开始把 macOS IPC 元数据收敛成 typed surface：
    - 当前导出 `MacFrameBusLayout / MacIPCDescriptor / MacStreamCapabilities`
    - `MacVirtualCamera` 与 SDK `VirtualCamera` 当前都已补充 `ipc_descriptor()` 与 `stream_capabilities()`
    - Desktop `ServiceFacade` 当前也会优先消费 `stream_capabilities()`，并把 `supported_formats / supported_frame_rates` 继续透传给 ViewModel 与主窗口状态栏
30. `VirtualCamera` 与 `MacVirtualCamera` 当前还已直接上浮 PySide6 友好入口：
    - `create_pyside6_bridge()`
    - `send_image() / send_pixmap() / send_widget() / send_screen()`
    - `create_latest_frame_provider() / create_pyside6_streamer()`
    这样外部 PySide6 项目可以直接从 SDK 或 macOS backend 走“窗口抓取 / 屏幕抓取 / 最新帧桥接”路径，而不必先手动拼装底层 integration helper
31. `tools/pyside6_virtual_camera_demo.py` 当前也已切换为优先使用这组 SDK 入口：
    - `numpy-direct` 直接通过 `VirtualCamera.push_frame(numpy.ndarray)`
    - `provider / latest-provider / video-file` 通过 `VirtualCamera.create_pyside6_streamer()`
    - `latest-provider` 通过 `VirtualCamera.create_latest_frame_provider()`
    - `image / pixmap` 直接通过 `VirtualCamera.send_image()` / `send_pixmap()`
    - `widget / screen` 直接通过 `VirtualCamera.send_widget()` / `send_screen()`
    这样“PySide6 直接调用”现在不只体现在底层 API 已存在，也开始体现在 demo/contract/validation 证据链里
32. `validation-report / validation-session / session-summary` 当前也已开始把 demo 实际走过的 Python 入口显式收敛成结构化字段：
    - `demo_python_entrypoint_kind`
    - `demo_sdk_streamer_factory_used`
    - `demo_sdk_latest_provider_factory_used`
    - `demo_sdk_direct_push_used`
    后续在 CI 工件页或人工验收时，不必再反推代码路径，就能直接确认本次会话是否真的走了统一 SDK 入口
33. 当前主要风险仍在真实系统验证层面，包括：
   - 已跑通无签名 `xcodebuild` 真机构建链路，但“签名 + 公证 + 系统安装批准”仍未完成
   - Zoom / Teams / Meet / OBS / QuickTime / FaceTime 仍缺少真实应用枚举验证
   - `1080p60` CPU `<10%` 尚未完成真实性能测量
   - `dmg` 生成在当前受限环境下仍会因 `hdiutil` 报 `device not configured`，需在完整 macOS runner 复核
31. 下一步建议：
    - 用 benchmark 工具补充真机 `1080p60` 测量记录
    - 用 `benchmark --matrix` 固化六档 profile 的真机基线
    - 推进签名、公证与真实系统安装批准链路验证
    - 继续把 PySide6 streamer / LatestFrameProvider 接入真实桌面/屏幕/WebRTC/视频播放 场景示例与端到端测试
    - 开始用 validation report 固化 QuickTime / OBS / Zoom 等真机验收记录
31. 本轮新增进展：
    - 已安装并验证 `xcodegen`，成功生成 `virtualcam/macos/akvc-macos.xcodeproj`
    - 已修复无签名构建时的 provisioning 阻塞、命令工具 IPC 漏链、Camera Extension 缺少 `NSExtensionMain`、Host 误编译 `akvc_macos_list_devices.mm`、以及 Host/Extension bundle id 前缀校验失败
    - 已实际跑通 `python3 tools/make.py build`
    - 已确认 Host App、Camera Extension 与状态工具均为 `arm64 + x86_64` 双架构
32. 当前 IPC 配置链路已继续补齐到 Host 激活时序：
    - `akvc-host --activate` 会先读取 `AKVC_MACOS_SHM_NAME` 或 `AKVC_MACOS_SHM_NAME_FILE`
    - 读取到合法 shm 名称后，会先写入 `~/Library/Group Containers/group.com.akvc.shared/akvc-macos-shm-name.txt`
    - 然后才提交 `OSSystemExtensionRequest`
    - 这样 Camera Extension 被系统首次拉起时，就能优先读到与 Python producer 对齐的共享内存名称
33. Camera Extension 侧当前也已补上 shm 名称热切换最小闭环：
    - `AKVCFrameProvider.copyNextSampleBufferWithStatus(...)` 每次读帧前都会重新读取 `akvc_macos_ring_descriptor_default(...)`
    - 如果发现 App Group 共享文件中的 shm 名称发生变化，会先关闭旧 consumer，再在后续轮询中按新 shm 名称重新打开
    - 切换后的首个真实帧会额外携带 `CMIOExtensionStreamDiscontinuityFlagTime`
    - 当前仍属于轮询式重连，不是显式 XPC 控制面；后续仍可继续收敛成可观察、可命令化的重载流程
34. 当前已继续补上一条可命令化的原生 IPC 同步链路：
    - 新增 `akvc-macos-sync-ipc`
    - Python `MacVirtualCamera.start()` 在写入共享文件后，会优先调用 installer service 的 `sync_ipc_configuration_result(...)`
    - 若原生命令存在，则会把 `AKVC_MACOS_SHM_NAME` 显式传给该命令，由原生层完成同一套校验与持久化
    - 这样当前 SDK / CLI / Desktop 后续都可以复用同一条“显式同步 IPC 配置”的控制面入口
    - 已实际生成无签名 `VirtualCamera.pkg` 与 `VirtualCamera.zip`
    - Python/macOS 安装服务已补充 `pkg -> Host App -> akvc-macos-install` 自动链路：当未发现可用 Host App 且可发现 `VirtualCamera.pkg` 时，会先执行 `/usr/sbin/installer -pkg ... -target /`，再继续激活 Camera Extension
32. 当前 Python 分发态已补充 `akvc/_runtime/macos` 运行时资产目录，并通过 `tools/make.py sync-macos-runtime` / `tools/make.py package --sync-runtime` 支持把：
    - `akvc-macos-status`
    - `akvc-macos-install`
    - `akvc-macos-uninstall`
    - `akvc-macos-list-devices`
    - `VirtualCamera.pkg`
    一并同步进 wheel / 外部 PySide6 分发目录可发现的位置
33. `akvc.runtime` 当前已优先支持从包内 `_runtime/macos` 解析 `status / install / uninstall / list-devices / pkg`，开始为“Python 直接自动安装 Camera Extension”建立分发态路径闭环
31. 已补充 `tools/macos_smoke.py --output ...`，当前可独立产出 `smoke-report.json`，沉淀安装/卸载往返的结构化工件
32. 已补充 `tools/macos_install_session.py`，当前可直接验证更高层自动安装链路：
    - `VirtualCamera.pkg`
    - Host App bundle 定位
    - `DefaultMacInstallerService.install_extension_result()`
    并输出 `install-session-report.json`
33. `tools/macos_validation_report.py` 当前已支持汇总：
    - `runtime_assets`
    - `smoke-report.json`
    - `install-session-report.json`
    开始把“安装资产是否可发现”和“自动安装链路是否可回归”统一沉淀到单一报告
34. `tools/macos_validation_session.py` 与 `tools/make.py validation-session` 当前已支持 `--run-install-session`，开始把：
    - preflight
    - release diagnostics
    - smoke
    - install session
    - validation report
    串成一份可归档的安装验证会话
34. GitHub Actions 与 Jenkins 当前也开始归档：
    - `smoke-report.json`
    - `install-session-report.json`
    让 CI 在构建产物之外同步保留安装链路的结构化证据
35. 当前主要风险已进一步聚焦到真机系统层：
    - 运行时资产发现、自动装包与安装状态收敛路径已具备合成测试与工件沉淀
    - 但真实 `installer` 授权、System Extension 用户批准、以及目标应用内实际摄像头可见性仍需真机复核
36. 下一步建议更新为：
    - 在真实 macOS 开发机上运行 `tools/make.py install-session` 与 `validation-session --run-install-session`，沉淀首份非合成安装证据
    - 用 `validation-report.json` 开始回填 QuickTime / OBS / Zoom / Meet / Teams / FaceTime 的人工验收结果
    - 继续推进 `1080p60` 真机 benchmark 与 CPU `<10%` 数据闭环
37. 本轮补充行为收口：
    - `akvc status --json` 当前已显式输出 `phase`，可区分 `pending_approval / installed_visible / timeout_waiting_for_device`
    - 桌面端 `ServiceFacade.start()` 当前会在启动推流 worker 前强制复查 macOS 安装状态；如果扩展已启用但系统摄像头还未枚举完成，会直接阻止启动并返回明确提示
    - 已补充对应 CLI / Desktop 单测，用于固定“设备未可见时禁止误启动”的行为
38. 本轮继续收口导入边界：
    - `ServiceFacade` 当前已移除对 `frame_provider` / `frame_worker` 的模块级强依赖，改为惰性导入
    - 桌面端现在即使缺少 `numpy / cv2`，也仍可完成 `Install / Open Settings / Recheck / 状态展示`
    - 只有真正点击 `Start` 时，才会要求 `numpy / cv2` 与 worker 相关依赖存在
    - 已补充 `test_package_lazy_imports.py` 与桌面端单测，固定“安装状态可用但推流依赖仍可单独报错”的行为
39. 本轮继续把状态门禁接到 UI：
    - `ServiceFacade` 当前已显式产出 `stream_start_ready / stream_start_message`
    - `MainViewModel` 会把这两个字段继续透传到桌面端
    - `MainWindow` 当前会在初始化阶段先禁用 `Start`，等状态轮询到达后再根据 `installed_visible / pending_approval / timeout_waiting_for_device` 自动切换启用状态
    - 已补充 fake-Qt 桌面端测试，固定“安装未完成时禁用 Start、安装完成后重新启用”的交互行为
40. 本轮继续把依赖门禁并入同一条状态链：
    - `ServiceFacade` 当前会用 `find_spec("numpy") / find_spec("cv2")` 预探测推流依赖，而不主动导入这些模块
41. 本轮继续把显式 IPC 同步能力上浮到统一 Python/CLI 入口：
    - `MacVirtualCamera.start()` 当前已改为先检查“安装/批准/设备可见”，再执行 `sync_ipc_configuration_result(...)`，最后才对 `ipc_not_ready` 做最终阻断
    - 这样当问题本身就是“共享内存配置尚未同步”时，不会在真正尝试同步前被过早拒绝
    - `MacVirtualCamera` 与 SDK `VirtualCamera` 当前都已显式补充：
      - `sync_ipc_configuration_result(shared_memory_name=None)`
      - `sync_ipc_configuration(shared_memory_name=None)`
    - CLI 当前也已补充 `akvc sync-ipc --json [--shared-memory-name ...]`
    - 已补充对应契约/单测，固定：
      - sync 成功时可恢复 `ipc_ready=false` 的启动前状态
      - sync 失败时会继续返回明确错误
      - SDK / CLI 公开方法签名保持对齐
42. 本轮继续把 `sync-ipc` 收口进分发与验收资产：
    - `tools/make.py sync-macos-runtime` 当前已把 `akvc-macos-sync-ipc` 视为正式 runtime 资产
    - 根包与 `akvc-core` 的 package-data 当前都已包含 `_runtime/macos/akvc-macos-sync-ipc`
    - GitHub Actions / Jenkins 当前也已开始归档这份产物
    - `tools/macos_validation_report.py` 当前会把 `sync_ipc_tool` 纳入 `runtime_assets.resolved_assets` 与 `packaged_tools_present` 判断
    - 当前仓库内的 `camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc` 已完成一次真实原生构建产物同步
43. 本轮继续把 `sync-ipc` 前推到发布诊断与会话摘要：
    - `tools/macos_release_diagnostics.py` 当前已支持 `--sync-ipc-tool`
    - 发布诊断当前会额外输出：
      - `sync_ipc_tool_exists`
      - `sync_ipc_tool_signed`
      - `sync_ipc_tool_universal2_ready`
    - `tools/macos_validation_report.py` 当前也会把这些字段继续并入 `summary.release_sync_ipc_tool_*`
    - `tools/macos_validation_session.py` 当前会把这组字段继续前推到 `session-manifest.json.summary`
    - `tools/macos_native_verify.py` 当前也已把 `virtualcam/macos/control_bridge/akvc_macos_sync_ipc.mm` 纳入 control bridge tools syntax 覆盖
44. 本轮继续把 `sync-ipc` 做成可读验收证据：
    - `tools/macos_validation_session_acceptance.py` 当前会新增非关键 criterion `sync_ipc_control_plane_ready`
    - `tools/macos_validation_session_summary.py` 当前会新增 `Sync IPC Tool` 小节，直接渲染 exists/signed/universal2 三个字段
    - Acceptance Gates 小节当前也会额外显示 `Sync IPC control plane ready`
45. 本轮继续把分发态闭环提升成独立 contract：
    - 已新增 `tools/macos_distribution_contract.py`
    - 当前会固定：
      - `tools/make.py sync-macos-runtime` 是否仍同步 `status / install / uninstall / list-devices / sync-ipc / pkg`
      - `akvc.runtime` 是否仍能从包内 `_runtime/macos` 解析 `akvc-macos-sync-ipc` 与 `VirtualCamera.pkg`
      - `tools/macos_validation_report.py` 的 runtime snapshot 是否仍保留 `sync_ipc_tool_resolved / packaged_tools_present / packaged_pkg_present`
      - `tools/macos_release_diagnostics.py` 是否仍导出 `sync_ipc_tool_exists / signed / universal2_ready`
    - `tools/macos_native_verify.py` 当前也已接入这条检查，开始把“build 目录里有产物”进一步收紧到“分发态 runtime 与 release 诊断面未漂移”
    - 这样真机安装、公证、CI 归档与人工复盘现在都能直接看到“显式 IPC 控制面工具是否真正进入发布态”
46. 本轮继续把签名/公证链路提升成独立 contract：
    - 已新增 `tools/macos_signing_pipeline_contract.py`
    - 当前会固定：
      - `sign_app.sh` 是否仍先签 Extension 再签 Host，并执行 `codesign --verify / spctl`
      - `build_pkg.sh` 是否仍保留 `productsign` 与 `pkgutil --check-signature`
      - `notarize.sh` 是否仍拒绝未签名 `pkg` 后再提交
      - `staple.sh` 是否仍执行 `stapler staple / validate` 与 `spctl -t install`
      - `tools/macos_release_diagnostics.py` 与 `tools/macos_validation_report.py` 是否仍导出 `app_signed / extension_signed / pkg_signed` 及 `release_*` 汇总字段
    - `tools/macos_native_verify.py` 当前也已接入这条检查，开始把“shell 脚本存在”进一步收紧到“签名语义未漂移”
    - 这样签名、公证、封口与最终 JSON 验收证据之间现在形成了可回归的闭环，不再只依赖人工翻 shell 日志
47. 本轮继续收紧 Python SDK 对齐语义：
    - `tools/macos_sdk_contract.py` 当前已把 `ipc_descriptor()` 与 `stream_capabilities()` 一并纳入共享公开方法集合
    - 同时新增了 `enumerate_devices / status / readiness / inspect_installation / ipc_descriptor / stream_capabilities / is_installed / install_extension_result / install_extension` 的签名级断言
    - `tests/unit/test_macos_install_result_api.py` 当前也补充了非 macOS 路径下这些方法的降级返回值约束，避免后续平台分支重构时把统一 SDK 表面撞歪
    - 这样“对齐当前 Windows SDK，而不是对齐 pyvirtualcam”的要求现在不只体现在文档里，也体现在可执行契约里
48. 本轮继续把入口层真实调用链提升成独立 contract：
    - 已新增 `tools/macos_entrypoints_contract.py`
    - 当前会固定：
      - `tools/pyside6_virtual_camera_demo.py` 仍通过统一 `VirtualCamera` 创建相机，并保持 `start(name) -> streamer -> close()` 调用链
      - CLI `status/install/sync-ipc` 仍通过统一 `VirtualCamera` 暴露 `inspect_installation / install_extension_result / sync_ipc_configuration_result`
      - 桌面端 `ServiceFacade` 仍优先消费 `inspect_installation()` 与 `stream_capabilities()`
      - 上述四条入口链都不回退到 `MacVirtualCamera` 直接耦合，也不重新引入 `pyvirtualcam` 依赖
    - `tools/macos_native_verify.py`、GitHub Actions、Jenkins 与单测白名单当前也已接入这条检查，避免“底层 SDK 没漂移，但入口层各自分叉”
    - `stream_start_ready` 现在由“安装是否完成”与“推流依赖是否齐全”共同决定
    - 如果扩展已安装完成但 `numpy / cv2` 缺失，桌面端仍会保持 `Start` 禁用，并优先提示“推流依赖缺失”
    - 已补充服务层与 fake-Qt UI 测试，固定“依赖缺失优先提示”的行为
41. 本轮继续收口依赖恢复体验：
    - 空闲态 `poll_status()` 当前会重新执行依赖探测
    - 如果之前只是 `find_spec` 级别的 `numpy / cv2` 缺失，补装依赖后无需重启应用，`Start` 可自动恢复
    - 对于已经发生过的 worker 运行时导入失败，当前可通过补装依赖后点击 `Recheck` 主动恢复，而不会强制要求重启应用
42. 本轮继续把同一条门禁下沉到 SDK：
    - `MacVirtualCamera.start()` 当前会在真正打开 sink 前校验扩展是否已安装、是否仍待系统批准、以及系统设备列表里是否已出现虚拟摄像头
    - 统一 `VirtualCamera` 的 darwin 分支也会继承这条行为，外部 PySide6 项目直接调用时不再出现“started=True 但系统实际上没有可用虚拟摄像头”的假启动
    - 已补充 `test_macos_virtual_camera.py` 覆盖未安装、待批准、设备未可见三类禁止启动场景
43. 本轮继续推进 IPC baseline 的可测性：
    - 已新增 `tests/unit/test_macos_shm_sink.py`，覆盖 POSIX shared-memory producer 的 `producer_seq` 递增、`seq_head / seq_tail` finalize、ring slot 回卷覆盖与 heartbeat 更新
    - `MacOsShmSink.publish()` 当前已新增 payload 长度校验；当 `frame.data` 字节数小于 `plane_size[0] + plane_size[1]` 时，会直接拒绝写入且不会推进序列号
    - GitHub Actions 与 Jenkins 的显式 macOS 单测清单当前也已接入这组测试，避免后续只校验 ABI 但遗漏实际写 ring 行为
44. 本轮继续把“跨语言互通”做成可运行验证：
    - 已新增 `virtualcam/macos/ipc/src/framebus_consumer_probe.c`，真实调用 `akvc_fb_open / akvc_fb_poll / akvc_fb_producer_alive`
    - 已新增 `tools/macos_framebus_roundtrip.py`，会先用 Python `MacOsShmSink` 发布一帧，再编译并执行原生 probe，最后校验 `plane_size / checksum / producer_seq / view_seq / producer_alive`
    - GitHub Actions 与 Jenkins 当前也已开始显式运行 `tools/make.py framebus-roundtrip` 并归档 `build/macos/framebus-roundtrip.json`
    - 当前在这台受管开发环境里，roundtrip probe 已进一步暴露出 `direct_open_errno=13 (EACCES)`：producer 侧能创建并写入 shm，但独立原生 probe 进程被环境拦截了 `shm_open(O_RDONLY)`；这更像运行环境/沙箱限制，而不是协议布局错误
45. 本轮继续把 IPC 证据并入统一验收报告：
    - `macos_validation_report.py` 当前已支持 `--framebus-roundtrip-json`
    - `macos_validation_session.py` 当前已支持 `--run-framebus-roundtrip`
    - 报告摘要现在会显式输出 `framebus_roundtrip_present / passed / direct_open_errno / environment_blocked / producer_initialized`
46. 本轮继续把 IPC 探测结果接回运行态状态链路：
    - `akvc.runtime` 当前已支持解析 `AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON` 与默认 `build/macos/.../framebus-roundtrip.json`
    - `ExtensionStatus` 当前已新增 `ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_last_error / ipc_probe_path / ipc_direct_open_errno`
    - `akvc status`、`akvc install`、桌面端 `ServiceFacade` 与 `MacVirtualCamera.start()` 现在都会共同消费这组 IPC 状态
    - 如果系统摄像头已可见，但最新 framebus roundtrip 明确显示当前环境阻塞了共享内存访问，桌面端与 Python SDK 现在会在启动前直接给出一致的阻塞原因，而不是等到后续推流失败
47. 本轮继续把 IPC 结果前推到桌面可见层：
    - `MainViewModel` 当前已开始透传 `ipc_transport / ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_probe_path / ipc_direct_open_errno`
    - 主窗口当前会把安装摘要显示成 `IPC: ready / pending / blocked/errno=...`
    - 如果 `framebus-roundtrip` 明确显示环境阻塞，主窗口当前还会额外显示 `IPC 详情` 与 `IPC 报告` 路径，减少用户需要手动翻 JSON/日志的成本
48. 本轮继续把同一组 IPC 状态并入 smoke 验收链路：
    - `tools/macos_smoke.py` 当前已支持 `--framebus-roundtrip-json`
    - `smoke-report.json` 当前已开始沉淀 `ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno / ipc_probe_path`
    - `tools/make.py smoke` 当前也已支持透传 `--framebus-roundtrip-json`
49. 本轮继续把 IPC 状态并入 install-session 与统一摘要：
    - `tools/macos_install_session.py` 当前已支持 `--framebus-roundtrip-json`
    - `install-session-report.json` 当前已开始沉淀 `phase + ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno / ipc_probe_path`
    - `macos_validation_report.py` 摘要当前也已开始透出 `install_session_ipc_probe_present / install_session_ipc_ready / install_session_ipc_environment_blocked / install_session_ipc_direct_open_errno`
50. 本轮继续把 IPC 状态前推到 validation-session manifest：
    - `tools/macos_validation_session.py` 当前会优先生成 `framebus-roundtrip.json`，再把它透传给 `smoke` 与 `install-session`
    - `session-manifest.json.summary` 当前已开始聚合 `smoke / install-session / framebus-roundtrip / validation-report` 的关键 IPC/成功状态
    - `validation-session` 当前还会默认透传 `--framebus-producer-kind mac-virtual-camera`，优先验证公开 `VirtualCamera.start()+push_frame()` 路径
    - 会话摘要里也会显式保留 `framebus_roundtrip_producer_kind`
    - 当前还已新增 `--run-direct-push-demo / --direct-push-demo-tool / --direct-push-frames`，可把公开 `VirtualCamera` direct push 报告直接纳入会话工件
    - `session-manifest.json.summary` 当前也会开始聚合 `direct_push_demo_present / mode / python_entrypoint_kind / sdk_direct_push_used / requested_frames / frames_sent`
51. 本轮继续把同一组 IPC 证据下沉到原生命令层：
    - `virtualcam/macos/control_bridge/AKVCCommandSupport.mm` 当前会在 `AKVCDefaultStatusPayload()` 阶段主动搜索 `AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON` 与默认 `build/macos/.../framebus-roundtrip.json`
    - `akvc-macos-status` 输出现在可直接包含 `ipc_transport / ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_last_error / ipc_probe_path / ipc_direct_open_errno`
    - 这样 Python 侧即使不额外做状态合并，也能从原生命令拿到完整的安装态 + IPC 态统一快照
    - 已补充 native skeleton/verify 测试，并通过 `python3 tools/macos_native_verify.py` 验证 host tools 语法与相关契约未回退
52. 本轮继续补齐 runtime 场景下的 native IPC 状态可见性：
    - `CommandMacInstallerService` 当前已在执行 `status / install / list-devices` 原生命令时，临时导出 `AKVC_MACOS_FRAMEBUS_ROUNDTRIP_JSON`
    - 这样 `akvc-macos-status` 在 wheel / `_runtime/macos` / Host 包装调用场景下，也能稳定读取与 Python 侧相同的 roundtrip 报告路径，而不是只在 `cwd` 恰好命中 `build/macos/...` 时才拿到 `ipc_*`
    - 当前实现会在命令执行结束后恢复调用前的环境变量，避免污染宿主进程环境
    - 已补充 installer 单测覆盖“透传生效”和“原值恢复”两条行为，并通过定向脚本验证 `macos-installer-env-tests-ok`
53. 本轮继续把 `status` 的 IPC 语义升级成独立 contract：
    - 已新增 `tools/macos_status_contract.py`，会同时检查 `AKVCCommandSupport.mm` 是否仍暴露预期的 `ipc_*` 字段、roundtrip 报告路径搜索与 `errno 1/13 -> environment_blocked` 语义
    - 该工具还会用多组 fixture 驱动 `_merge_framebus_roundtrip_status()`，固定 `no_report / invalid_report / successful_probe / open_failed_errno_13 / top_level_error_errno_1 / consistency_marks_environment_blocked` 六类行为
    - `tools/macos_native_verify.py` 当前已把这条 contract 并入默认检查链，GitHub Actions / Jenkins 的显式单测与语法清单也已同步接入
    - 已通过 `python3 tools/macos_status_contract.py`、定向脚本 `macos-status-contract-tests-ok` 与 `python3 tools/macos_native_verify.py` 三层验证
54. 本轮继续把“源码契约正确”推进到“真实二进制输出正确”：
    - 已新增 `tools/macos_status_binary_check.py`，会创建临时 `framebus-roundtrip.json` fixture，调用真实 `akvc-macos-status` 二进制，并验证 `ipc_*` 字段是否按预期出现在最终 JSON
    - 当前该检查已同时覆盖 `consumer_open_failed_errno_13` 与 `producer_open_failed_errno_1` 两组 fixture，开始固定 status 二进制对 consumer / producer 双侧 IPC 阻塞的合并语义
    - GitHub Actions `native-skeleton` 与 Jenkins 当前都已在 build 后显式运行这条检查，并归档 `build/macos/session/status-binary-check.json`
    - 已补充 `tests/unit/test_macos_status_binary_check_tool.py` 覆盖脚本表面与假命令夹具行为，并同步更新 release skeleton 断言
    - 当前本机已在重建 native 产物后实际跑通：`python3 tools/macos_status_binary_check.py --status-tool build/macos/Build/Products/Release/akvc-macos-status --output build/macos/session/status-binary-check.json`
55. 本轮继续把真实 status 二进制证据并入统一会话报告：
    - `tools/macos_validation_report.py` 当前已支持 `--status-binary-check-json`，并开始把 `status_binary_check_present / passed / ipc_keys_present / ipc_environment_blocked / ipc_direct_open_errno` 汇总进 `summary`
    - `tools/macos_validation_session.py` 当前已支持 `--run-status-binary-check`，会把 `status-binary-check.json` 作为会话工件写入 `artifacts`，并把关键状态聚合进 `session-manifest.json.summary`
    - `tools/make.py validation-report / validation-session` 当前也已同步透传 `--status-binary-check-json / --status-binary-check-tool / --run-status-binary-check`
    - 已通过定向脚本 `macos-validation-status-binary-tests-ok`、`macos-make-wrapper-status-binary-ok`，以及一次真实 `python3 tools/macos_validation_session.py --run-status-binary-check ...` 会话验证
56. 本轮继续把“是否可开始推流”的诊断收敛成共享契约：
    - `camera-core/src/akvc/platforms/macos/installer.py` 当前已新增 `infer_extension_phase()` 与 `evaluate_extension_readiness()`，统一产出 `phase / ready / blocker_code / message / steps / verification_targets`
    - 桌面端 `ServiceFacade` 现在不再手写一套安装态 / IPC 态分支，而是直接消费这份 readiness 结果，并把 `install_blocker_code` 继续透传给 `MainViewModel`
    - `akvc status`、`akvc install` 与 `tools/macos_validation_report.py` 当前也已开始沉淀 `start_ready / start_blocker_code / start_message / start_steps` 或对应的 `readiness` 摘要，避免 CLI、桌面端与验收报告出现不同口径
    - 已补充 installer / CLI / desktop / validation report 侧单测断言，固定 `ready / approval_required / ipc_environment_blocked / device_not_visible` 等关键 blocker 分支
57. 本轮继续把统一 readiness 诊断前推到验收会话链路：
    - `tools/macos_smoke.py` 与 `tools/macos_install_session.py` 当前也已开始输出 `start_ready / start_blocker_code / start_message / start_steps`
    - `tools/macos_validation_session.py` 当前会把 `validation_report / smoke / install_session / framebus / status_binary_check` 中可用的开始推流诊断汇总成 `effective_start_ready / effective_start_blocker_code`
    - `session-manifest.json.summary` 还会额外保留 `smoke_start_blocker_code / install_session_start_blocker_code / validation_status_start_blocker_code`，便于 CI 直接读取而不是手工翻多份子工件
    - 已同步补充 smoke/install-session/validation-session 单测断言与文档说明，收紧“ready / device_not_visible / ipc_environment_blocked / package_install_failed”这几类常见会话级 blocker
58. 本轮继续把能力声明抬升到 validation session 摘要层：
    - `tools/macos_validation_session.py` 当前会从 `validation-report.json`、`smoke-report.json` 与 `install-session-report.json` 中提取 `supported_formats / supported_frame_rates`
    - `session-manifest.json.summary` 会额外保留 `validation_* / smoke_* / install_session_* / effective_*` 四组能力字段
    - `effective_supported_formats / effective_supported_frame_rates` 当前优先采用 `install-session`，再回退到 `smoke`、最后回退到 `validation-report`，用于表达“本次会话最终对外暴露的能力”
59. 本轮继续把 capability contract 与 CI 归档追到 validation session 顶层：
    - `tools/macos_capability_contract.py` 当前已开始检查 `macos_validation_session.py` 是否仍读取并导出 `supported_formats / supported_frame_rates`
    - GitHub Actions 与 Jenkins 当前也会把 `build/macos/session/session-manifest.json` 一并归档，开始把 `effective_supported_formats / effective_supported_frame_rates` 作为流水线可见工件
    - 这样 `4K60` 等能力现在不仅存在于状态层、smoke/install-session 子工件，还能被 contract 和 CI 工件页同时固定住
60. 本轮继续把 validation session 摘要从 surface 检查推进到行为 contract：
    - 已新增 `tools/macos_validation_session_contract.py`
    - 当前 contract 会固定 `validation -> smoke -> install-session` 的 `effective_start_*` 聚合顺序
    - 当前 contract 也会固定 `install-session -> smoke -> validation-report` 的 `effective_supported_*` 能力回退顺序，并单独覆盖 `framebus errno=1` 对 `ipc_environment_blocked` 的提升行为
    - `tools/macos_native_verify.py`、GitHub Actions、Jenkins 与 release skeleton 断言当前也已接入这条检查
61. 本轮继续把 validation session 推到“真实工件回放”层：
    - 已新增 `tools/macos_validation_session_artifact_check.py`
    - `tools/make.py` 当前已新增 `validation-session-artifact-check` 入口
    - GitHub Actions 与 Jenkins 当前会在生成 `build/macos/session/session-manifest.json` 后立刻回放检查，并额外归档 `session-manifest-check.json`
    - 这样 `session-manifest.json` 不再只是被动归档文件，而是会被自动校验结构、自引用工件存在性，以及 `effective_start_* / effective_supported_*` 的值域一致性
62. 本轮继续把真实工件回放并回收到统一 validation session：
    - `tools/macos_validation_session.py` 当前会在 `validation-report.json` 生成后自动执行 artifact check
    - `session-manifest.json` 的 `artifacts` 当前也会额外登记 `artifact_check_report`
    - `session-manifest.json.summary` 当前会继续保留 `artifact_check_present / artifact_check_passed`
    - `tools/macos_validation_session_artifact_check.py` 当前还会继续校验：
      - `release_sync_ipc_tool_exists / release_sync_ipc_tool_signed / release_sync_ipc_tool_universal2_ready`
      - `sync_ipc_control_plane_ready` 以及相关 acceptance gate 的类型面
      这样 release diagnostics -> acceptance -> session manifest 的 `sync-ipc` 控制面证据链也已被纳入真实工件回放
    - 已同步补充 `validation_session` 单测、`make.py` wrapper 单测，以及 `validation_session_contract` 的源码表面断言
63. 本轮继续把 readiness/helper 语义提升成独立 contract：
    - 已新增 `tools/macos_readiness_contract.py`，会直接校验 `infer_extension_phase()` 与 `evaluate_extension_readiness()` 的源码表面和代表性 case 行为
    - 当前 contract 会固定 `approval_required` 优先于陈旧 IPC、`not_installed` 不被旧 roundtrip 误覆盖、`ipc_environment_blocked / ipc_not_ready / device_not_visible / package_install_failed / install_failed / ready` 等关键 blocker 分支
    - `tools/macos_native_verify.py`、GitHub Actions、Jenkins 与 release skeleton 断言当前也已接入这条检查，避免后续只测上层工具输出却放过 helper 级语义回退
64. 本轮继续把六目标应用精确身份集合接入最终 delivery gate contract：
    - `tools/macos_delivery_gate_contract.py` 当前除 `pkg / 签名 / 公证 / install-session` 外，也会继续回放 `target_apps_all_passed`、`system_camera_device_visible` 与 `sync_ipc_control_plane_ready`
    - 已补充三类代表性 case：
      - 六个目标 app id 恰好齐全且全部通过 -> `pass`
      - 只有 `validated_apps/passed_apps` 计数、没有精确 app id 证据 -> `unknown`
      - 缺失或混入意外 app id -> `fail`
      - `akvc-macos-list-devices` 缺证据 -> `system_camera_device_visible=unknown`
      - `akvc-macos-list-devices` 运行但没有看到匹配虚拟摄像头 -> `system_camera_device_visible=fail`
      - sync-ipc 工具虽已进入发布物，但 install-session 未显式同步成功 -> `sync_ipc_control_plane_ready=fail`
    - 这样 `tools/macos_native_verify.py` 当前已不只是在“会话摘要层”约束目标应用矩阵，而是会继续在最终 delivery gate 层固定这条三态语义
65. 本轮继续把 acceptance helper 本身接入独立 contract 与总验证入口：
    - 已新增 `tools/macos_validation_session_acceptance_contract.py`
    - `tools/make.py` 当前也已新增 `validation-session-acceptance-contract` 统一入口
    - `tools/macos_validation_session.py` 当前也会在真实 session 中自动生成 `session-acceptance-contract.json`
    - `session-manifest.json.artifacts` 当前会显式登记 `acceptance_contract_report`
    - `session-manifest.json.steps` 当前会显式登记 `acceptance_contract`
    - `session-manifest.json.summary` 当前会继续保留 `acceptance_contract_present / acceptance_contract_passed`
    - 当前 contract 会直接回放：
      - 完整 acceptance 通过
      - 只有计数时 `target_apps_all_passed=unknown`
      - manifest 显式 `validation_observed/missing/unexpected_target_app_ids` 覆盖 validation report 推导
      - entrypoints contract / benchmark 缺证据时保持 `unknown`
    - `tools/macos_native_verify.py`、GitHub Actions 与 Jenkins 当前也已显式接入这条 contract，避免 acceptance helper 只靠单元测试覆盖
59. 本轮继续把 Camera Extension 顶层设备图谱提升成独立 contract：
    - 已新增 `tools/macos_topology_contract.py`，会直接校验 `AKVCProviderSource -> AKVCDeviceSource -> AKVCStreamSource -> AKVCFrameProvider` 的默认装配拓扑
    - 当前 contract 会固定 `AK Virtual Camera / AKVC / com.akvc.camera.device`、`AKVC Stream`、`CMIOExtensionStreamDirectionSource`、`CMIOExtensionStreamClockTypeHostTime` 与 `startServiceWithProvider` 注册链路
    - 同时会固定 ring descriptor -> `FrameProvider` 的 IPC 接线，以及 Device 默认输入能力与只读属性面，避免后续原生重构把“可被系统识别为摄像头”的基础图谱悄悄改坏
    - `tools/macos_native_verify.py`、GitHub Actions、Jenkins 与 release skeleton 断言当前也已同步接入这条检查
60. 本轮继续把 macOS FrameBus 的 consumer 可观测性往前推进：
    - `framebus_posix.c` 当前已从只读 consumer 升级为可维护 `consumer_count` 的读写附着路径，成功打开时递增、关闭时递减
    - 已新增 `akvc_fb_consumer_count()`，并让 `framebus_consumer_probe.c` / `tools/macos_framebus_roundtrip.py` 开始输出 `consumer_count`
    - `tools/macos_framebus_contract.py` 与相关单测当前也已固定这条语义，避免后续又退回“producer 在写，但 macOS 侧永远观测不到 consumer 附着数量”的状态
61. 本轮继续把 FrameBus roundtrip 的“瘦环境可运行性”往前推进：
    - `akvc.core.frame` 与 `akvc.core.frame_sink.macos_shm` 当前已允许在未安装 `numpy` 时完成 metadata-only/import-only 路径，避免诊断工具被视频依赖提前拦住
    - `tools/macos_framebus_roundtrip.py` 当前已能在无 `numpy` 环境下继续运行到真实共享内存阶段
    - 如果 producer 侧直接卡在 `shm_open(create)`，工具现在会输出 `producer_open_failed + direct_open_errno` 的结构化 JSON，`validation-report` / `validation-session` 也会把 `errno=1 / 13` 统一归类到 `ipc_environment_blocked`
62. 本轮继续把 producer-side IPC blocker 并入高层状态契约：
    - `tools/macos_status_contract.py` 当前已新增 `producer_open_failed_errno_1` fixture，直接固定 `_merge_framebus_roundtrip_status()` 对这类 JSON 的合并行为
    - `CommandMacInstallerService.status()` 当前也已通过单测覆盖这一路径，确认会透出 `ipc_environment_blocked=true`、`ipc_direct_open_errno=1`、`ipc_transport=iosurface_ring`
63. 本轮继续把 validation session 从“结构自洽”推进到“最终验收摘要”层：
    - 已新增 `tools/macos_validation_session_acceptance.py`，会把 `session-manifest / validation-report / preflight / benchmark / release-diagnostics` 收敛成 `session-acceptance.json`
    - `tools/make.py` 当前已新增 `validation-session-acceptance` 入口，GitHub Actions 与 Jenkins 也已把 `session-acceptance.json` 作为显式归档工件
    - `tools/macos_validation_session.py` 当前会在 artifact check 后按 `acceptance -> acceptance-contract -> summary` 的固定顺序执行，并把 `acceptance_present / acceptance_ready / acceptance_failed_criteria / acceptance_unknown_criteria` 继续写回 `session-manifest.json.summary`
    - 当前 release gate 还已继续收紧：
      - `macos_13_plus_declared / universal2_ready / release_packaging_ready / signing_evidence_ready`
      - 会优先读取 `validation-report.json.summary`
      - 如果上游尚未把字段前推到 validation report，则继续回退到 `release-diagnostics.json.summary`
      - 当证据只是“部分存在”时保持 `unknown`，避免把“尚未补齐”误判成 `fail`
      - `notarization_tooling_ready` 当前也已统一到同一套 tri-state 语义，避免 `can_notarize=true` 但 `can_staple` 缺失时被过早判成 `fail`
    - 当前 acceptance 摘要会直接对齐最终验收标准中的 `macOS 13+ / universal2 / pkg+host+extension / 签名 / 公证工具链 / PySide6 路径 / 六个目标应用 / 720p-4K + 30/60fps / benchmark / 自动安装 / runtime assets`
64. 本轮继续把 IPC 身份信息抬升到统一验收摘要层：
    - `tools/macos_validation_report.py` 当前已在 `status / summary` 中继续显式保留 `shared_memory_name / mach_service_name / ipc_transport`
    - `tools/macos_validation_session.py` 当前会继续聚合 `validation_* / smoke_* / install_session_* / effective_*` 四组 IPC 身份字段
    - `session-summary.md` 当前也会把 `effective shared memory / mach service / IPC transport`、`validation status` 与 `install-session` 的对应字段直接展开
    - 已同步补充 artifact-check / session-contract / summary-render / report/session 单测，固定 “install-session -> smoke -> validation install -> validation status” 的 IPC 身份回退顺序
65. 本轮继续把 shm 名称从 typed IPC surface 打通到真实运行时：
    - Python `MacOsShmSink` 当前已支持按构造参数使用自定义 `shared_memory_name`
    - `MacVirtualCamera.start()` 当前会优先把 `ipc_descriptor().framebus.shared_memory_name` 传给 sink，而不是始终退回默认 `/akvc-frames-v1`
    - 当 `MacVirtualCamera` 已经 `start()` 后，再次调用 `sync_ipc_configuration_result("/new-shm")`，当前也会在 sync 成功后把 producer sink 重绑到新的 shm 名称
    - 原生 `framebus_posix.c` 当前已新增 `akvc_fb_open_named(...)`，`AKVCFrameProvider` 也会使用自身 `sharedMemoryName` 打开 shm
    - `framebus_consumer_probe.c` 当前也已支持 `--shm-name`，为后续补齐“非默认 shm 名称 roundtrip 验证”预留了直接入口
66. 本轮继续把 shm 名称配置源前推到原生 descriptor 默认层：
    - `virtualcam/macos/ipc/include/akvc/macos_ipc.h` 当前已新增 `AKVC_MACOS_SHM_NAME_ENV`
    - `virtualcam/macos/ipc/src/macos_ipc.cpp` 当前会在构造默认 ring descriptor 时读取该环境变量，并对“非空、以 `/` 开头、长度不超 descriptor buffer”做最小合法性校验
    - `AKVCProviderSource`、`AKVCDefaultStatusPayload` 与其他依赖 `akvc_macos_ring_descriptor_default()` 的原生路径因此开始共享同一套 shm 名称 override 语义
    - 已同步补充 `macos_framebus_contract` 与 native skeleton 断言，固定这条 override 不会在后续重构中丢失
67. 本轮继续把 shm 名称从“进程环境”推进到“App Group 持久化配置”：
    - `camera-core/src/akvc/platforms/macos/ipc.py` 当前已新增：
      - `default_shared_memory_name_override_path()`
      - `resolve_shared_memory_name_override_path()`
      - `read_shared_memory_name_override()`
      - `write_shared_memory_name_override()`
    - 默认配置文件路径当前为：
      `~/Library/Group Containers/group.com.akvc.shared/akvc-macos-shm-name.txt`
    - `MacVirtualCamera.start()` 当前会在创建 sink 前把最终 `shared_memory_name` 写入这份共享文件
    - `virtualcam/macos/ipc/src/macos_ipc.cpp` 当前会在读取 `AKVC_MACOS_SHM_NAME` 失败后，继续尝试：
      - `AKVC_MACOS_SHM_NAME_FILE`
      - App Group 默认配置文件
    - 当前主要剩余风险是：Extension 一旦已经启动，`AKVCFrameProvider` 还不会因为共享文件变化而热刷新 shm 名称；后续需要补重载/重连控制面
68. 本轮继续把 Python 统一入口 contract 收回到最终 validation session 工件层：
    - `tools/macos_validation_session.py` 当前会在 `validation-report.json` 之后自动执行 `tools/macos_entrypoints_contract.py`
    - 会新增会话工件 `entrypoints-contract.json`
    - `session-manifest.json` 当前会把它登记到 `artifacts.entrypoints_contract_report`
    - `steps` 当前也会登记 `entrypoints_contract`
    - `session-manifest.json.summary` 当前会继续沉淀：
      - `entrypoints_contract_present`
      - `entrypoints_contract_passed`
      - `entrypoints_contract_surface_complete`
      - `entrypoints_contract_demo_case_complete`
      - `entrypoints_contract_cli_case_complete`
      - `entrypoints_contract_desktop_case_complete`
    - `tools/macos_validation_session_summary.py` 当前也会新增 `Python Entrypoints` 小节，直接渲染这六个字段
    - `tools/macos_validation_session_artifact_check.py` 当前还会回放这份工件与字段类型，避免 entrypoint contract 只在 native verify 中通过，却没有真正进入最终验收会话
    - GitHub Actions 与 Jenkins 当前也会把 `build/macos/session/entrypoints-contract.json` 一并归档，保证 CI 工件页与会话 manifest 的工件声明保持一致
    - 已补充 `validation_session / artifact_check / summary / contract` 四组单测，并通过定向脚本回归
69. 本轮继续把统一 Python 入口一致性提升到最终 acceptance gate：
    - `tools/macos_validation_session_acceptance.py` 当前已新增 `python_entrypoints_consistent`
    - 会优先读取 `entrypoints-contract.json`，并结合：
      - `entrypoints_contract_passed`
      - `entrypoints_contract_surface_complete`
      - `entrypoints_contract_demo_case_complete`
      - `entrypoints_contract_cli_case_complete`
      - `entrypoints_contract_desktop_case_complete`
      统一判断 PySide6 demo / direct-push demo / CLI / desktop 四条入口链是否仍共同走统一 `VirtualCamera`
    - `tools/macos_validation_session.py` 当前也会把这条 gate 的状态继续合并回 `session-manifest.json.summary`
    - `tools/macos_validation_session_summary.py` 当前会在 `Acceptance Gates` 小节直接渲染 `Python entrypoints consistent`
    - 已补充 acceptance helper、summary helper、summary contract 与 validation session merge 的定向回归
70. 本轮继续把目标应用验收从“计数通过”收紧到“六个指定应用集合通过”：
    - `tools/macos_validation_session_acceptance.py` 当前会优先读取 `validation_observed_target_app_ids / validation_missing_target_app_ids / validation_unexpected_target_app_ids`
    - 如果主 manifest 里没有显式 target identity 字段，才会回退到 `validation_app_matrix` 与 `validation_*_app_ids`
    - 会显式校验 `facetime / google_meet / obs / quicktime / teams / zoom` 六个目标 app id 是否恰好齐全
    - 只要 `missing_target_app_ids` 或 `unexpected_target_app_ids` 非空，即使通过计数仍显示完整，`target_apps_all_passed` 也会直接失败
    - 当 evidence 里存在缺失/意外 app id，或某些应用处于 `fail / pending / skipped / unreviewed` 时，`target_apps_all_passed` 会直接失败
    - 如果只有 `validated_apps / passed_apps` 这类计数而没有精确 app id 集合，当前会保持 `unknown`
    - `tools/macos_app_matrix_contract.py` 当前也已开始固定 `EXPECTED_APP_IDS` 与 installer / manual template / acceptance helper 的一致性
71. 本轮继续把目标应用证据前推到 report / session / summary：
    - `tools/macos_validation_report.py` 当前已开始导出：
      - `reviewed_app_ids`
      - `observed_target_app_ids`
      - `missing_target_app_ids`
      - `unexpected_target_app_ids`
      - `target_app_ids_complete`
    - `tools/macos_validation_session.py` 当前会继续把这组字段提升到 `session-manifest.json.summary`
    - `tools/macos_validation_session_summary.py` 当前会在 `Target Apps` 小节直接显示 `Reviewed / Observed target ids / Target id set complete / Missing target ids / Unexpected target ids`
72. 本轮继续把 acceptance helper 自检证据前推到 reader-facing summary：
    - `tools/macos_validation_session_summary.py` 当前会显式渲染 `Acceptance Contract` 小节
    - 会直接展开 `acceptance_contract_present / acceptance_contract_passed`
    - `session-summary.md` 的 `Artifacts` 小节当前也会继续列出 `acceptance_contract_report`
    - 已同步补充 summary helper 与 summary contract 的定向回归，避免主 manifest 已有字段但 reader-facing 摘要漏展示
    - 已补充 validation report、validation session 与 summary helper 的定向回归，确保这组字段能从 `validation-report.json` 一直传到最终 reader-facing Markdown
72. 本轮继续把目标应用 identity 证据接回 artifact replay 与 session contract：
    - `tools/macos_validation_session_artifact_check.py` 当前会检查：
      - `validation_reviewed_app_ids`
      - `validation_unreviewed_app_ids`
      - `validation_observed_target_app_ids`
      - `validation_missing_target_app_ids`
      - `validation_unexpected_target_app_ids`
      - `validation_target_app_ids_complete`
      这些字段在主 manifest 摘要层的类型一致性
    - `tools/macos_validation_session_contract.py` 当前也已把这组字段纳入源码 surface 与代表性 summary case
    - 已补充 artifact-check 与 validation-session-contract 的定向回归，保证这组字段不仅“可见”，还会被真实工件回放与 helper contract 一起固定
73. 本轮继续把 `sync-ipc` 从“发布物存在证明”前推到“install-session 运行时证据”：
    - `tools/macos_install_session.py` 当前已支持 `--sync-ipc-tool`
    - install-session 结束后会按 `post_status.shared_memory_name` 主动执行一次 `sync_ipc_configuration_result(...)`
    - `install-session-report.json` 当前已新增 `sync_ipc` 子对象
    - `session-manifest.json.summary` / `session-summary.md` 当前也已继续提升 `install_session_sync_ipc_*`
    - `tools/macos_validation_session_artifact_check.py` 当前也已开始回放 `install_session_sync_ipc_*`，并约束 `sync_ipc_control_plane_ready=pass` 时 runtime sync 证据必须同时成立
    - `validation-session-acceptance` 的 `sync_ipc_control_plane_ready` 当前已收紧为“发布物完整 + install-session 显式同步成功”
    - 已通过定向 install-session 回放、acceptance fail 回放，以及 `validation-session-* contract` / `macos_native_verify` 复核
74. 本轮继续把人工验收模板从“工件存在”推进到“模板可执行”：
    - `tools/macos_validation_session_artifact_check.py` 当前已开始回放 `manual-results.template.json`
    - 会校验六个目标应用 id 是否齐全
    - 会校验每个条目是否仍保留完整字段集合
    - 会校验每个条目的 `checks / steps` 是否都是非空字符串列表
    - 已补充 artifact-check 定向回归，覆盖“完整模板通过”和“退化模板失败”两类场景
75. 本轮继续把 Python Producer 与 native `sync-ipc` 的共享内存命名收敛做实：
    - 当 native `sync_ipc_configuration_result(...)` 返回的 `shared_memory_name` 与请求值不同，`MacVirtualCamera.start()` 当前会改用“最终生效值”打开 producer sink
    - 同时也会把 `AKVC_MACOS_SHM_NAME_FILE` 对应的 override 文件更新为 native 最终返回值，避免后续 host / extension / producer 三侧对同一会话使用不同 shm 名称
    - 已补充 `test_macos_virtual_camera_start_uses_native_synced_shared_memory_name` 与 `test_macos_virtual_camera_sync_ipc_configuration_persists_native_synced_name` 两条定向回归
76. 本轮继续把原生 install tool 从“固定 pending 占位返回”推进到“短轮询真实状态快照”：
    - `akvc-macos-install` 当前在发起 host activation 后，会短轮询 `AKVCQuerySystemExtensionStatus(...)`
    - 若状态已收敛到 `installed / install_pending_approval / install_failed`，会直接返回真实快照
    - 若短时间内仍未收敛，才回退到 `install_pending_approval`
    - 已补充 native skeleton 源码回归，固定这组 surface，避免后续又退回固定占位返回
77. 本轮继续把“扩展已启用”和“系统设备已可见”两条证据彻底拆开：
    - `AKVCQuerySystemExtensionStatus(...)` 当前不再因为 `property.isEnabled` 就伪造 `devices=["AK Virtual Camera"]`
    - 原生 `status` 现在只负责 system extension 安装/批准状态
    - 原生 `list-devices` 继续独占“系统视频设备是否真的枚举到了 AK Virtual Camera”这条证据
    - 这样 install-session / readiness / validation report 后续就能更稳定地区分 `installed_visible` 与 `timeout_waiting_for_device`
78. 本轮继续把“状态快照”和“设备枚举”统一到同一套原生实现上：
    - `virtualcam/macos/control_bridge/AKVCCommandSupport.mm` 当前已新增共享的 `AKVCEnumeratedVideoDevices()` 与 `AKVCVideoDeviceSnapshot()`
    - `akvc-macos-list-devices` 与 `AKVCQuerySystemExtensionStatus(...)` 现在都会复用同一套 `AVCaptureDeviceDiscoverySession` 枚举逻辑
    - 当 system extension 已启用时，原生 `status` 会附带真实 `devices / all_devices / device_prefix` 快照，而不是继续使用各自分叉的枚举实现
    - 已通过 `python3 tools/macos_native_verify.py` 复核 host tools 语法与 contract，确认这次 helper 收敛未引入结构回退
79. 本轮补充了对 `/Users/admir/workspace/cameraextension` 参考项目的结论澄清：
    - 该项目并不是“纯 extension、零宿主”
    - 它只是把宿主职责放进了 `samplecamera.app`，而不是单独做成 daemon/helper
    - 这进一步确认了我们当前“保留 `akvc-host.app` 作为宿主容器，但不把宿主职责误解为必须常驻 daemon”的架构判断
80. 本轮继续把 native `status` 的真实设备快照提升到 Python / CLI / 验证层可直接消费：
    - `ExtensionStatus` 当前已新增 `all_devices / device_prefix`
    - `installer.py` 现在会解析 native `status` 返回的 `devices / all_devices / device_prefix`
    - 当没有单独 `list-devices` 工具时，如果 `status.devices` 已出现虚拟摄像头，会直接判定 `installed_visible`
    - 如果 `status` 已明确给出 `all_devices/device_prefix`，但过滤后的 `devices` 仍为空，则会继续等待并最终收敛为 `timeout_waiting_for_device`，不再一律宽松回退为 `installed_state_only`
    - `akvc status`、`akvc install`、`macos_smoke.py`、`macos_install_session.py` 与 `macos_validation_report.py` 当前也会继续透出 `status_all_devices / all_devices / device_prefix`
    - 已通过新增 installer 定向回归与 `python3 tools/macos_native_verify.py` 复核
81. 本轮继续把“为什么设备仍不可见”这条证据推进到 desktop / VM 层：
    - `ServiceFacade.WorkerStatus` 当前已新增 `install_all_devices / install_device_prefix`
    - `recheck_install_status()` 即使优先走 `inspect_installation()`，现在也会按最新 `evaluate_extension_readiness(...)` 重新生成 readiness，避免旧 snapshot 文案吞掉新的设备可见性细节
    - 当 phase 为 `timeout_waiting_for_device` 且状态里已有 `all_devices / device_prefix` 时，安装提示会直接包含“期望前缀 + 当前系统视频设备列表”
    - `MainViewModel.install_status_changed` 与 `metrics_changed` 当前也会继续透出 `all_devices / device_prefix`
    - 已通过 desktop status 定向回放、`tests/unit/test_desktop_main_vm.py` 脚本回放与 `python3 tools/macos_native_verify.py` 复核
82. 本轮继续把设备可见性证据推进到最终验收摘要与 contract：
    - `tools/macos_validation_session.py` 当前已开始在 `session-manifest.json.summary` 里固定：
      - `validation_devices / validation_all_devices / validation_device_prefix`
      - `validation_install_status_devices / validation_install_status_all_devices / validation_install_device_prefix`
      - `smoke_devices / smoke_all_devices / smoke_device_prefix`
      - `install_session_devices / install_session_all_devices / install_session_device_prefix`
      - `effective_devices / effective_all_devices / effective_device_prefix`
    - `tools/macos_validation_session_summary.py` 当前会把这组字段直接渲染到 `Validation Status / Installation Snapshot / Install Session` 与顶部 `Effective *` 摘要
    - `tools/macos_validation_session_contract.py` 与 `tools/macos_validation_session_summary_contract.py` 当前也已把这组字段纳入 source surface 与代表性回放 case，避免后续 reader-facing 摘要再次漏掉“当前系统里到底看到了哪些摄像头”
    - 已通过 `python3 tests/unit/test_macos_validation_session_tool.py`、两条 summary/contract 脚本回放与 `python3 tools/macos_native_verify.py` 复核
83. 本轮继续把 benchmark 从“部分 profile 指标”收紧为“完整矩阵验收证据”：
    - `tools/macos_benchmark.py` 当前已在 `summary.benchmark_acceptance` 中新增：
      - `required_profile_count`
      - `required_profiles_present`
      - `missing_required_profiles`
      - `unexpected_profiles`
    - `tools/macos_validation_session_acceptance.py` 当前新增 `benchmark_matrix_complete` 门禁，不再只看 `benchmark_fps_targets_met` 与 `benchmark_1080p60_cpu_target_met`
    - 这样即使某次会话只跑了 `1080p60` 或其他 profile 子集，也不会再被误判为“720/1080/4K x 30/60 六档矩阵都已完成验收”
    - 已同步补充 benchmark tool、acceptance helper、acceptance contract 的定向回归，并通过 `python3 tools/macos_native_verify.py` 复核
84. 本轮继续把“进入人工批准入口”的动作收口为统一能力：
    - `camera-core/src/akvc/platforms/macos/installer.py` 当前已新增 `macos_install_settings_commands()` 与 `open_macos_install_settings()`
    - 打开顺序现在会优先尝试更接近 `隐私与安全性` 的 deep link，再回退到普通 `System Settings.app`
    - `apps/desktop/akvc_app/services/facade.py` 当前已改为复用这条统一 helper，而不是各处散落的 `open` 命令
    - `apps/cli` 当前已新增 `akvc open-settings`
    - 已通过 installer / CLI / desktop status 三条脚本回放以及 `python3 tools/macos_native_verify.py` 复核
85. 本轮继续把“卸载/停用”链路收口进统一 Python / CLI surface：
    - `camera-core/src/akvc/platforms/macos/installer.py` 当前已新增 `UninstallExtensionResult`
    - `CommandMacInstallerService / DefaultMacInstallerService` 当前都已补充：
      - `uninstall_extension_result()`
      - `uninstall_extension()`
    - `MacVirtualCamera` 与统一 `VirtualCamera` 当前也都已补充同名接口，并在卸载前自动停止推流
    - `apps/cli` 当前已新增 `akvc uninstall` / `akvc uninstall --json`
    - 已补充 installer / SDK / CLI 契约回归，并通过 `python3 tools/macos_native_verify.py` 复核
86. 本轮继续把卸载结果并入验收工件统一语义：
    - `tools/macos_smoke.py` 与 `tools/macos_install_session.py` 当前已改为复用 `uninstall_extension_result()`，不再只记录裸 `returncode`
    - `smoke-report.json` / `install-session.json` / `validation-report.json` 当前都会继续保留：
      - `success`
      - `phase`
      - `state`
      - `enumerated_devices`
      - `last_error`
    - `tools/macos_validation_report.py` 当前也已把 `smoke_uninstall_* / install_session_uninstall_*` 汇总字段补齐
    - 已补充 smoke / install-session / validation-report 三条脚本回归
87. 本轮继续把目标应用人工验收线索前推到 reader-friendly 摘要：
    - `tools/macos_validation_session.py` 当前已把 `verification_targets` 里的 `steps / checks` 一并带入 `validation_app_matrix`
    - `tools/macos_validation_session_summary.py` 当前会在 `Target App Details` 里继续渲染：
      - `steps / checks` 数量
      - 首条 `first_step / first_check`
    - 这样只看 `session-summary.md` 也能直接知道“该去哪验证、第一条通过现象是什么”，不必再回翻 template 或原始 JSON
    - 已补充 validation-session / session-summary 两条脚本回归
88. 本轮继续把“manual-results 回灌”推进到可复用的真实人工验收闭环：
    - `tools/macos_validation_session.py` 当前已新增 `--reuse-existing-artifacts`
    - 当这项开关与 `--skip-preflight / --skip-release-diagnostics / --skip-demo / --skip-benchmark` 组合使用时，脚本会复用当前 `output-dir` 下已存在的：
      - `preflight.json`
      - `release-diagnostics.json`
      - `demo-report.json`
      - `benchmark*.json`
      - `smoke-report.json`
      - `install-session-report.json`
      - `framebus-roundtrip.json`
      - `status-binary-check.json`
    - 然后只重算：
      - `validation-report.json`
      - `session-manifest-check.json`
      - `session-acceptance.json`
      - `session-acceptance-contract.json`
      - `session-summary.md`
    - `tools/make.py validation-session` 当前也已透传同名参数
    - 这样“先跑一轮 session 生成模板 -> 去六个目标应用手工验证 -> 回来只刷新最终验收结论”已经成为稳定工作流
89. 本轮继续把原生卸载工具从“固定成功回包”推进到“短轮询真实状态快照”：
    - `virtualcam/macos/control_bridge/akvc_macos_uninstall.mm` 当前已新增 `AKVCUninstallStatusConverged(...)`
    - 在提交 `akvc-host --deactivate` 后，会短轮询 `AKVCQuerySystemExtensionStatus(...)`
    - 当状态真正回落到 `not_installed`、或系统已经进入 `needs_reboot` / `enabled=false` 收敛态时，才直接回写 JSON
    - 如果短时间内仍未收敛，也会保留当前状态并显式返回 `last_error=timed out waiting for extension deactivation`
    - 已补充 native skeleton 源码回归，并通过 `python3 tools/macos_native_verify.py` 复核
90. 本轮继续把 `list-devices` 原生命令自检从“独立子工件”前推到 `validation-report.json`：
    - `tools/macos_validation_report.py` 当前已新增 `--list-devices-binary-check-json`
    - `tools/make.py validation-report` 与 `tools/macos_validation_session.py` 当前也都已透传这条输入
    - 总报告 `summary` 会继续提升：
      - `list_devices_binary_check_present`
      - `list_devices_binary_check_passed`
      - `list_devices_binary_check_device_prefix`
      - `list_devices_binary_check_filtered_device_count`
      - `list_devices_binary_check_total_device_count`
      - `list_devices_binary_check_override_no_match_ok`
    - 这样 `validation-report.json` 现在不只汇总扩展状态，还能直接证明“原生设备枚举二进制是否真的看到了 AK Virtual Camera，并且 prefix 过滤语义没有漂移”
    - 已补充 validation-report / make wrapper / validation-session 三条定向回归
91. 本轮继续把 `list-devices` 自检从“可见证据”提升为最终 acceptance gate：
    - `tools/macos_validation_session_acceptance.py` 当前新增 `system_camera_device_visible`
    - 该门禁优先使用 `list_devices_binary_check_*` 字段判断 `akvc-macos-list-devices` 是否真的从系统视频设备枚举中看到 AKVC 虚拟摄像头
    - 如果该自检没有运行，最终验收会保持 `unknown`，不会把“缺少设备枚举证据”误判成可人工验收
    - `tools/macos_validation_session_summary.py` 当前也会在 `Acceptance Gates` 中渲染 `System camera device visible`
    - 这样“什么时候可以人工验收”的判断会明确包含系统摄像头可见性，而不只依赖安装命令返回值或扩展状态旁推
92. 本轮继续把 `system_camera_device_visible` 从 acceptance 子报告提升到主 session manifest：
    - `tools/macos_validation_session.py` 的 `ACCEPTANCE_GATE_NAMES` 当前已包含 `system_camera_device_visible`
    - 因此 `session-manifest.json.summary` 会直接保留该 gate 的 `pass / fail / unknown` 状态，Dashboard / CI / Jenkins 只消费主 manifest 时不会漏掉系统摄像头可见性结论
    - `tools/macos_validation_session_artifact_check.py` 当前也把该字段纳入 acceptance gate 类型回放，防止新字段被 artifact replay 误判或后续回退
    - `tools/macos_validation_session_contract.py` 与 `tools/macos_validation_session_summary_contract.py` 已同步增加回放覆盖，确保 JSON manifest 与 Markdown 摘要两条读取路径都能看到这一项
93. 本轮继续把 `system_camera_device_visible` 接入最终 delivery gate contract：
    - `tools/macos_delivery_gate_contract.py` 当前会固定该 gate 的三态行为：
      - `list_devices_binary_check_present=true && passed=true && filtered_device_count>0` -> `pass`
      - 缺少 `list-devices` 自检证据 -> `unknown`
      - 自检运行但没有枚举到匹配虚拟摄像头 -> `fail`
    - `tests/unit/test_macos_delivery_gate_contract_tool.py` 已同步校验源码 surface 与代表性 case
    - 这样 `tools/macos_native_verify.py` / GitHub Actions / Jenkins 的最终交付门禁不会只验证安装命令成功，而会继续约束系统摄像头设备枚举证据
94. 本轮根据 `/Users/admir/workspace/cameraextension` 参考项目继续校准 Host/Container 边界：
    - 已确认该参考项目没有独立常驻 host daemon，但仍有 `samplecamera.app` 作为 System Extension 容器与 `OSSystemExtensionRequest` 激活入口
    - 当前架构文档已明确 `akvc-host.app` 是容器 / 激活器 / 命令桥，不在 `1080p60 / 4K` 帧热路径中
    - 帧数据面继续固定为 `Python producer -> shared memory / IOSurface -> Camera Extension`
    - `tools/macos_topology_contract.py` 已新增 `extension_hot_path_bypasses_host` 契约，防止后续把 Host App 或 System Extension 激活代码混入 Camera Extension 热路径
95. 本轮继续把 CI/CD 验收产物归档提升为独立契约：
    - 已新增 `tools/macos_ci_artifact_contract.py`，同时检查 `.github/workflows/macos.yml` 与 `jenkins/macos.Jenkinsfile`
    - 契约会固定 `pkg / dmg / zip`、runtime 命令工具、`list-devices-binary-check.json`、`session-summary.md`、`manual-results.template.json` 与 `validation-report.json` 均被归档
    - 契约还会固定两条流水线都运行 `validation-session-artifact-check --require-existing-artifacts`、`validation-session-summary` 与 `validation-session-acceptance-contract`
    - GitHub Actions、Jenkins 与 `tools/macos_native_verify.py` 当前均已接入该契约，避免“构建通过但人工验收材料缺失”
96. 本轮继续把目标应用人工验收从“结果字符串”收紧为“证据驱动”：
    - `manual-results.template.json` 与示例文件当前都会为每个应用生成 `evidence.device_listed / device_selected / preview_visible / screenshot`
    - `tools/macos_validation_report.py` 会校验并合并这些 evidence，并在 summary 中输出 `manual_validation_missing_evidence_app_ids`
    - `tools/macos_validation_session.py` 会把 evidence 保留进 `validation_app_matrix`
    - `tools/macos_validation_session_acceptance.py` 当前要求所有 `result=pass` 的目标应用都具备 `device_listed=true && device_selected=true && preview_visible=true`
    - `tools/macos_validation_session_summary.py` 会在 `Target App Details` 中直接渲染 `listed / selected / preview / screenshot`
    - 这样 `target_apps_all_passed` 不再只相信“六个应用写了 pass”，而是要求每个目标应用都证明“已识别系统摄像头、已选择、且已看到实时画面”
97. 本轮把原生构建从语法契约推进到真实 `xcodebuild` 验证：
    - 已修复 `AKVCCommandSupport.mm` 引入 `AVCaptureDeviceDiscoverySession` 后，`akvc-host / status / install / uninstall / list-devices / sync-ipc` 目标缺少 `AVFoundation.framework` 的链接问题
    - `tools/macos_build_contract.py` 当前新增 `command_support_targets_link_avfoundation`，防止后续命令目标再次漏链 `AVFoundation`
    - 已在当前 macOS/Xcode 16.2 环境实际跑通：
      - `python3.12 tools/make.py configure`
      - `python3.12 tools/make.py build --archs arm64 --deployment-target 13.0`
      - `python3.12 tools/make.py build --archs "arm64 x86_64" --deployment-target 13.0`
    - 当前 universal2 无签名构建已产出 host app、Camera Extension、`akvc-macos-status / install / uninstall / list-devices / sync-ipc`，`release-diagnostics-current.json` 中 `universal2_ready=true`
98. 本轮继续验证无签名打包链路：
    - `python3.12 tools/make.py package --skip-build --archs "arm64 x86_64" --deployment-target 13.0` 当前可生成 `VirtualCamera.pkg` 与 `VirtualCamera.zip`
    - 当前受限环境下 `hdiutil create` 仍返回“设备未配置”，脚本会按预期跳过 dmg 并保留 pkg/zip
    - `installer/macos/build_pkg.sh` 与 `build_zip.sh` 已设置 `COPYFILE_DISABLE=1`；zip staging 会删除 `._*` 元数据文件
    - 当前已进一步修复 pkg payload 清单：`build_pkg.sh` 会在 `pkgbuild` 后用 `pkgutil --expand-full / --expand`、`mkbom -s`、`cpio`、`gzip` 与 `pkgutil --flatten` 重建 Payload/BOM
    - 真实 `pkgutil --payload-files build/macos/VirtualCamera.pkg` 当前 `._*` 条目计数为 `0`，`release-diagnostics-current.json.summary.pkg_payload_appledouble_clean=true`
99. 本轮真实执行了 universal2 命令行产物：
    - `akvc-macos-status` 可运行并输出 JSON；在未签名、未安装、未系统批准状态下返回 `state=install_failed`，这是当前环境的预期结果
    - `akvc-macos-list-devices` 可运行并输出 `devices=[] / all_devices=[] / device_prefix=AK Virtual Camera`；由于扩展尚未签名安装，当前不会枚举到系统摄像头
    - `tools/macos_native_verify.py` 继续全绿，说明本轮构建、发布契约和拓扑契约未回退
100. 本轮继续把发布签名门禁从 Host/Extension/pkg 扩展到完整 runtime 命令工具：
    - `installer/macos/sign_app.sh` 当前会逐一检查、签名并校验 `akvc-macos-status / install / uninstall / list-devices / sync-ipc`
    - `tools/macos_release_diagnostics.py` 当前会输出整组 `command_tools` 元数据，并在 summary 中提升 `command_tools_exist / command_tools_signed / command_tools_universal2_ready`
    - `tools/macos_validation_report.py`、`tools/macos_validation_session.py` 与 `tools/macos_validation_session_acceptance.py` 当前都会把 `release_command_tools_signed` 纳入签名验收证据
    - 已补齐 signing pipeline、release diagnostics、validation session、acceptance contract 的回归覆盖，防止后续只签 App/Extension 而遗漏 Python SDK 实际调用的命令桥
101. 本轮根据 `/Users/admir/workspace/cameraextension` 再次校准 Host 语义：
    - 参考项目确实没有独立常驻 host daemon，但仍有 `samplecamera.app` 作为 `.systemextension` 容器和 `OSSystemExtensionRequest` 激活入口
    - 当前文档已明确 `akvc-host.app` 只承担安装激活容器、状态命令桥和分发锚点，不进入高频帧热路径
    - 参考项目使用 Swift；当前项目继续坚持不使用 Swift，Camera Extension 与控制面保持 Objective-C++ / C++ 实现
102. 本轮继续把这条 Host 语义提升成长期可回放证据：
    - `tools/macos_validation_report.py`、`tools/macos_validation_session.py` 与 `tools/macos_validation_session_summary.py` 当前都会导出 `runtime_topology_kind / runtime_frame_path / runtime_host_role / runtime_host_in_frame_hot_path / runtime_dedicated_host_daemon_required / runtime_data_plane / runtime_control_plane`
    - `session-summary.md` 当前新增 `Runtime Topology` 小节，人工验收时可直接确认“Host 只是容器/激活/命令桥，不在帧热路径”
    - `tools/macos_validation_session_contract.py` 与 `tools/macos_validation_session_summary_contract.py` 当前也会回放这组字段，避免后续 helper 仍输出、但 manifest/summary/contract 任一层静默回退
103. 本轮继续把最终交付门禁与人工摘要同步到 runtime tools 级别：
    - `tools/macos_delivery_gate_contract.py` 当前要求 `signing_evidence_ready` 同时具备 Host App、Camera Extension、runtime command tools 与 pkg 签名证据
    - `tools/macos_validation_session_summary.py` 当前新增 `Runtime Command Tools` 摘要区，直接展示整组命令工具是否存在、是否签名、是否 universal2 ready
    - `tools/macos_native_verify.py` 已复核通过，说明 build/distribution/signing/topology/session/summary/delivery gate 合约均未回退
104. 本轮继续把 pkg payload 清洁度提升为发布门禁：
    - `tools/macos_release_diagnostics.py` 当前会记录 `payload_appledouble_files / payload_appledouble_clean`
    - `tools/macos_validation_report.py`、`tools/macos_validation_session.py` 与 `tools/macos_validation_session_acceptance.py` 当前都会提升 `release_pkg_payload_appledouble_clean`
    - `release_packaging_ready` 当前要求 release artifacts、Extension payload、Host 内嵌 Extension 与 pkg payload AppleDouble 清洁度同时成立
    - `session-summary.md` 的 `Runtime Command Tools` 区域会显示 `PKG payload AppleDouble clean`
    - 已用真实 `python3.12 tools/make.py package --skip-build --archs "arm64 x86_64" --deployment-target 13.0`、`pkgutil --payload-files`、`tools/macos_release_diagnostics.py` 与 `tools/macos_native_verify.py` 复核通过
104. 本轮继续把这条 release pkg 清洁证据前推到人工验收主摘要：
    - `tests/unit/test_macos_validation_session_tool.py` 当前已开始显式断言 `session-manifest.json.summary.release_pkg_payload_appledouble_clean`
    - `docs/macos/install.md`、`docs/macos/build.md` 与 `docs/macos/architecture.md` 当前都已补充：主 manifest 与 `session-summary.md` 会继续透传这条字段
    - 已通过 `python3.12 tools/macos_validation_session_contract.py`、`python3.12 tools/macos_validation_session_summary_contract.py` 与 `python3.12 -m py_compile tests/unit/test_macos_validation_session_tool.py` 复核通过
105. 本轮继续把“六个目标应用识别”证据链接进主验证入口：
    - `tools/macos_app_matrix_contract.py` 当前已扩展为同时固定 `session-manifest.json.summary` 与 `session-summary.md` 的 target identity 字段和详情区，不再只校验 installer / smoke / validation report / manual template
    - `tools/macos_native_verify.py` 当前已新增 `app matrix contract` 步骤，目标应用矩阵漂移会直接进入总门禁
    - `docs/macos/build.md` 当前也已同步说明：`Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime` 六个目标应用的矩阵覆盖现在会贯通到 `session-manifest` 与 `session-summary`
    - 已通过 `python3.12 tools/macos_app_matrix_contract.py`、`python3.12 -m py_compile tools/macos_app_matrix_contract.py tests/unit/test_macos_app_matrix_contract_tool.py tools/macos_native_verify.py` 与 `python3.12 tools/macos_native_verify.py` 复核通过
106. 本轮继续把 benchmark 结构化证据提升为 CI 必归档工件：
    - `tools/macos_ci_artifact_contract.py` 当前已把 `build/macos/benchmark.json` 纳入 GitHub Actions / Jenkins 的必归档 validation 工件
    - `.github/workflows/macos.yml` 与 `jenkins/macos.Jenkinsfile` 当前也已同步归档 `build/macos/benchmark.json`
    - 这样即使 validation-session 本身使用 `--skip-benchmark`，单独 producer benchmark 的结构化 JSON 仍必须随流水线结果一起保留
    - 已通过 `python3.12 tools/macos_ci_artifact_contract.py`、`python3.12 -m py_compile tools/macos_ci_artifact_contract.py tests/unit/test_macos_ci_artifact_contract_tool.py` 与 `python3.12 tools/macos_native_verify.py` 复核通过
107. 本轮继续把 benchmark 证据从“必须归档”收紧到“必须执行”：
    - `tools/macos_ci_artifact_contract.py` 当前已新增 `REQUIRED_BENCHMARK_COMMAND_FRAGMENTS`，要求流水线文本里显式存在 `tools/macos_benchmark.py` 与 `--output build/macos/benchmark.json`
    - 这样 contract 不再接受“只归档 benchmark.json 路径，但实际没有运行 benchmark 命令”的假阳性场景
    - 已补齐 `tests/unit/test_macos_ci_artifact_contract_tool.py` 断言，并继续通过 `python3.12 tools/macos_ci_artifact_contract.py` 与 `python3.12 tools/macos_native_verify.py` 复核
108. 本轮继续把 validation-session 的 benchmark 证据链从“工件存在”收紧到“工件可回放且与摘要一致”：
    - `tools/macos_validation_session_artifact_check.py` 当前已开始解析 `benchmark_report`，并校验 `validation_benchmark_kind / validation_benchmark_matrix_profiles`
    - 对 `benchmark_matrix` 场景，artifact replay 现在会继续校验：
      `benchmark_fps_targets_met`、`benchmark_1080p60_cpu_target_met` 与 benchmark 工件推导结果一致，且 `1080p60` profile 保持 `1920x1080@60` 与 `cpu_target_applies=true`
    - 已补齐 `tests/unit/test_macos_validation_session_artifact_check_tool.py` 的正向与错配回归，防止后续出现 “benchmark.json 正常，但 session-manifest 摘要漂移” 的假阳性
    - 已通过 `python3.12 -m py_compile tools/macos_validation_session_artifact_check.py tests/unit/test_macos_validation_session_artifact_check_tool.py`、定向 artifact replay 场景复核，以及 `python3.12 tools/macos_native_verify.py` 全链路回归
109. 本轮继续把 benchmark 证据前推到 reader-facing `session-summary.md`：
    - `tools/macos_validation_session.py` 当前已把 `benchmark_matrix_complete` 纳入 acceptance gate 合并，开始进入 `session-manifest.summary`
    - `tools/macos_validation_session_summary.py` 当前会在 `## Benchmark Matrix` 中直接展示 `kind / profiles covered / required profile set complete / matrix complete gate / fps targets met / 1080p60 cpu target met`
    - `## Acceptance Gates` 当前也会同步展示 `Benchmark matrix complete` 与 `Benchmark FPS targets met`，避免人工验收只看到 profile 明细却看不到结论
    - 已同步补齐 `validation-session contract`、`validation-session summary contract` 和 reader-facing summary 测试覆盖，并继续通过 `python3.12 tools/macos_validation_session_contract.py`、`python3.12 tools/macos_validation_session_summary_contract.py` 与 `python3.12 tools/macos_native_verify.py`
110. 本轮继续把 `benchmark_matrix_complete` 真正纳入 artifact replay 与人工文档口径：
    - `tools/macos_validation_session_artifact_check.py` 当前已开始把 `benchmark_matrix_complete` 与 benchmark 工件推导结果做一致性校验，而不再只核对 `benchmark_fps_targets_met / benchmark_1080p60_cpu_target_met`
    - `summary_snapshot` 当前也会保留 `benchmark_matrix_complete`，便于回放脚本、CI 工件和外部自动化直接读取
    - `tests/unit/test_macos_validation_session_artifact_check_tool.py` 已新增 gate mismatch 回归，防止后续出现 “benchmark matrix 工件完整，但主 manifest 把 matrix gate 写成 fail/pass 错位” 的假阳性
    - `docs/macos/build.md`、`docs/macos/install.md` 与 `docs/macos/troubleshooting.md` 当前也已统一改成同时强调 `benchmark_matrix_complete / benchmark_fps_targets_met / benchmark_1080p60_cpu_target_met` 三个性能 gate
    - 已继续通过 `python3.12 -m py_compile tools/macos_validation_session_artifact_check.py tests/unit/test_macos_validation_session_artifact_check_tool.py` 与 `python3.12 tools/macos_native_verify.py`
111. 本轮继续把“什么时候可以开始人工验收”从隐含语义提升成显式 reader-facing 字段：
    - `tools/macos_validation_session_acceptance.py` 当前已输出 `manual_app_validation_ready / manual_app_validation_failed_criteria / manual_app_validation_unknown_criteria / manual_app_validation_blockers`
    - 这组字段和 `validation-report.json` 里的 `manual_validation_ready / manual_validation_complete / manual_validation_all_passed` 不是同一层语义：
      - 前者回答的是“系统级前置条件是否已经收敛到可开始真机人工验收”
      - 后者回答的是“目标应用人工 review 结果目前推进到了哪一步”
    - `tools/macos_validation_session_acceptance_contract.py` 与 `tests/unit/test_macos_validation_session_acceptance_contract_tool.py` 当前已补齐这组字段的真实回放，不再把它们误当成 criteria gate 读取
    - `session-summary.md` 的 `Manual App Validation Readiness` 小节现在会直接显示 `Ready / Failed prerequisites / Unknown prerequisites / Combined blockers`
    - 已继续通过 `python3.12 tools/macos_validation_session_acceptance_contract.py`、`python3.12 tools/macos_validation_session_summary_contract.py` 与 `python3.12 tools/macos_native_verify.py`
112. 本轮继续把这组人工验收前置条件摘要落到 CLI 与桌面端 reader-facing 展示层：
    - `camera-core/src/akvc/platforms/macos/installer.py` 当前已新增 `MANUAL_APP_VALIDATION_GATE_LABELS` 与 `describe_manual_app_validation_gates(...)`
    - `akvc status/install` 现在会优先输出中文标签数组，同时保留 `manual_app_validation_*_ids` 供 JSON/自动化继续读取原始 gate id
    - Desktop 安装提示区会优先显示 “人工验收失败前置项 / 待确认项 / 阻塞项” 的中文标签，而不是裸露 `system_camera_device_visible` 这类内部字段名
    - 已通过 `python3.12 -m py_compile`、内联 CLI payload sanity check，以及 `python3.12 tools/macos_native_verify.py` 复核这次 reader-facing 收敛未引入回退
113. 本轮继续把同一套 manual gate 标签前推到 `session-summary.md`：
    - `tools/macos_validation_session_summary.py` 当前会复用同一套 `describe_manual_app_validation_gates(...)` 映射
    - `Manual App Validation Readiness` 小节现在会显示“系统已枚举到虚拟摄像头 / 公证工具链已就绪 / 性能矩阵完整”等中文标签，而不是原始 gate id
    - 已补齐 `tests/unit/test_macos_validation_session_summary_tool.py`、`tools/macos_validation_session_summary_contract.py` 与 `tests/unit/test_macos_validation_session_summary_contract_tool.py` 的回归
    - 已继续通过 `python3.12 tools/macos_validation_session_summary_contract.py` 与 `python3.12 tools/macos_native_verify.py`
114. 本轮继续补强 PySide6 `QImage` 输入矩阵，开始覆盖单通道图像格式：
    - `camera-core/src/akvc/core/frame_input.py` 当前已直接支持 `QImage.Format_Grayscale8 / Format_Indexed8 / Format_Alpha8`
    - 对这类单通道 `QImage` 会在 Python 适配层扩展成三通道 BGR，再继续进入既有 `FramePipeline -> NV12` 路径
    - `convertToFormat(...)` 回退路径当前也已把 `Grayscale8 / Indexed8` 纳入候选，避免“非标准输入格式可转换，但 SDK 仍报不支持”的假失败
    - 已补齐 `tests/unit/test_frame_input.py` 与 `tests/unit/test_macos_virtual_camera.py` 的回归，并继续通过 `python3.12 tools/macos_input_contract.py`
115. 本轮继续补强 PySide6 provider 推流语义，开始显式支持“本 tick 没有新帧”返回空值：
    - `camera-core/src/akvc/integrations/pyside6.py` 当前在 `PySide6VirtualCameraStreamer._push_next_frame()` 里已把 `None` 视为“跳过当前 tick”
    - 这样普通 provider 现在既可以抛 `LookupError("no frame yet")`，也可以直接返回 `None`，避免把空值继续推到 `camera.push_frame(...)`
    - 这个行为更贴近 WebRTC / AI Avatar / 推理线程按需产帧场景，不需要调用方为“无新帧”额外造占位图
    - 已补齐 `tests/unit/test_pyside6_integration.py` 的回归，并通过 `PYTHONPATH=camera-core/src python3.12 tests/unit/test_pyside6_integration.py`
116. 本轮继续把 `QImage/QPixmap` 直推路径真正纳入可执行 demo / 验收链路：
    - `tools/pyside6_virtual_camera_demo.py` 当前已新增 `image / pixmap` 两种模式，分别直接走 `VirtualCamera.send_image()` 与 `send_pixmap()`
    - `tools/make.py validation-session`、`tools/macos_validation_session.py`、`tools/macos_validation_report.py` 与 `tools/macos_validation_session_acceptance.py` 当前也已同步承认这两种模式
    - `tools/macos_input_contract.py` 与 `tests/unit/test_pyside6_demo_tool.py` 当前已开始固定这两条入口，避免后续只保留 SDK API，但 demo / contract / acceptance 链路静默退化
    - 这样现在不仅“接口存在”，而且 `QImage/QPixmap -> Python SDK -> shared memory producer -> Camera Extension` 这条纯 Python 直推路径已经进入正式演示与验收语义
117. 本轮继续补上最贴近 `/Users/admir/workspace/cameraextension/vcam.mm` 语义的直接推帧模式：
    - `tools/pyside6_virtual_camera_demo.py` 当前已新增 `numpy-direct`，直接执行 `VirtualCamera.push_frame(numpy.ndarray)`
    - 该模式不再强依赖 `PySide6` 或 `QApplication`，而是纯 Python 循环推送 BGR `numpy` 帧
    - `tools/make.py validation-session`、`tools/macos_validation_session.py`、`tools/macos_validation_report.py` 与 acceptance gate 当前也已同步承认这条模式
    - 这样现在仓库里已经有一条官方可执行路径，能直接证明“Python 应用创建相机对象并发送帧数据”，而不是只能通过 streamer/provider 或 Qt 抓取间接验证
118. 本轮继续把 framebus roundtrip 从“底层 sink 互通”推进到“公开对象路径互通”：
    - `tools/macos_framebus_roundtrip.py` 当前新增 `--producer-kind mac-virtual-camera`
    - 该模式会通过公开 `VirtualCamera.start()+push_frame()` 路径发布 NV12 帧，再交给同一个 native `framebus_consumer_probe.c` 读取
    - 这样现在除了 `numpy-direct` demo 之外，仓库里还有一条结构化 probe，能直接证明“公开 Python 相机对象已经把帧送进共享内存数据面”
119. 本轮继续补了一个真正面向外部应用的最小直推脚本：
    - `tools/macos_direct_push_demo.py` 当前会直接执行 `VirtualCamera.start() -> push_frame(numpy.ndarray) -> close()`
    - 该脚本不依赖 Qt，也不要求调用方理解 provider/streamer/bridge 层
    - `tools/make.py direct-push-demo` 当前也已接入，便于后续人工试跑、安装后验证和支持文档直接引用
120. 本轮继续把更贴近 `/Users/admir/workspace/cameraextension/vcam.mm` 的 native direct sender 后端接入 Python SDK：
    - `camera-core/src/akvc/platforms/macos/direct_sender.py` 当前已新增可选的 ctypes 包装层，会查找 `libakvc-macos-direct-sender.dylib`
    - `MacVirtualCamera.start()` 当前会优先尝试 direct sender；成功时会跳过 `sync-ipc` 与 shared-memory sink，直接走 native sender
    - 如果 direct sender 缺失或打开 sink stream 失败，当前会自动回退到既有 `shared memory -> Camera Extension` 路径，避免破坏现有实现
    - `MacVirtualCamera` 当前默认也会按 direct/shm 后端切换不同 pipeline：direct sender 默认保留 `RGB24/BGR`，shared-memory 路线仍保持 `NV12`
    - 已补齐定向回放验证：确认 direct sender 成功时不再依赖 IPC probe，失败时会自动回退旧链路
121. 本轮继续把 macOS 运行时证据从“零散字段”收敛成统一快照：
    - `camera-core/src/akvc/platforms/macos/virtual_camera.py` 与 `camera-core/src/akvc/sdk/virtual_camera.py` 当前已新增 `runtime_snapshot()`，统一输出后端类型、direct sender 状态、共享内存名、最后一帧格式、IPC 描述与 runtime topology
    - `tools/macos_direct_push_demo.py` 与 `tools/pyside6_virtual_camera_demo.py` 当前也会优先把这份快照写入结构化报告，避免调用方继续依赖零散私有属性
    - 这样后续 `validation-report / validation-session / session-summary` 可以直接消费同一份 runtime 证据，而不是在不同工具里各自猜测 direct/shm 拓扑
122. 本轮继续把 `validation-session` 的回放一致性修到了“最小夹具也能稳定通过”：
    - `tools/macos_validation_session.py` 当前会在 `validation-report` 产出后自动规范化 `manual-results.template.json`，补齐六个目标应用和必需字段，避免最小模板导致 artifact replay 假失败
    - `tools/macos_validation_session_artifact_check.py` 当前已同步承认 manual template 中的 `evidence` 字段，不再与 `validation-report` 生成的模板形状冲突
    - `runtime_frame_path` 的默认回退现在固定回到 `shared_memory_ringbuffer -> camera_extension`，不再把安装期 `validation_install_transport` 误写成运行时热路径
    - `artifact_check / acceptance / acceptance_contract` 这类后验校验当前会继续写入 manifest 与 summary，但不会像前置构建失败那样中断整场 session，便于保留完整人工验收证据链
    - 已通过 `PYTHONPATH=camera-core/src:apps/cli ./.venv/bin/pytest -q tests/unit/test_macos_validation_report_tool.py tests/unit/test_macos_validation_session_tool.py tests/unit/test_macos_validation_session_summary_tool.py` 全链路回归
