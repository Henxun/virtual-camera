# macOS 构建说明

## 1. 目标

本文件定义 macOS 原生支持的构建目标、产物结构和自动化构建约束。

## 2. 构建目标

需要输出：

1. `arm64` 构建产物
2. `x86_64` 构建产物
3. `universal2` 最终分发产物

最终分发目标：

1. `.pkg`
2. `.dmg`
3. `.zip`

## 3. 构建产物组成

建议包含：

1. Container App
2. System Extension
3. Native helper / launcher
4. Python runtime
5. Qt 运行时
6. 项目 Python 包
7. `virtualcam/macos/project.yml`
8. `akvc-macos-all` 聚合 scheme
9. `akvc-macos-status` / `akvc-macos-install` / `akvc-macos-uninstall` / `akvc-macos-list-devices` 命令工具
10. `tools/macos_list_devices_binary_check.py` 与 `tools/make.py list-devices-binary-check`

## 4. 构建阶段

### 4.1 Python 层

1. 安装依赖
2. 运行单元测试
3. 生成 wheel 或打包目录

### 4.2 原生层

1. 编译 Objective-C++ / C++ 代码
2. 生成 system extension
3. 生成 helper / container app 组件
4. 生成命令桥接工具

### 4.3 Bundle 组装

1. 合并 Python 与原生产物
2. 嵌入 `Contents/Library/SystemExtensions`
3. 校验 bundle 结构

## 5. 构建策略

建议：

1. 开发阶段优先单架构快速构建
2. 发布阶段生成完整 `universal2`
3. CI 中分别保留架构单产物与合并后产物
4. 默认构建入口使用聚合 scheme `akvc-macos-all`

## 6. 自动化构建建议

### GitHub Actions

用于：

1. 代码检查
2. 单元测试
3. 构建验证
4. 基础打包

### Jenkins

用于：

1. 签名
2. 公证
3. 长时集成测试
4. 应用矩阵验证

## 7. 构建前置

1. Xcode 命令行工具
2. `xcodegen`
3. 有效的 Apple 签名证书
4. notarization 凭据
5. Python 与 Qt 运行环境

## 8. 当前结论

在正式编码前，构建系统要优先保证：

1. 能分层构建 Python 与原生组件
2. 能组合为统一 app bundle
3. 能继续生成后续 `pkg / dmg / zip` 产物
4. 能同时产出 Python 层依赖的状态/安装命令工具

当前仓库已验证到的最低构建基线：

1. `AKVCProviderSource / DeviceSource / StreamSource / FrameProvider` 已通过本机 `clang++ -fsyntax-only` + macOS 15.2 SDK 语法校验
2. `framebus_posix.c` 已通过本机 `clang -fsyntax-only` 语法校验，并与共享协议头对齐
3. `AKVCCommandSupport` 与 `akvc_macos_status` 已通过同级语法校验
4. 当前 `python3 tools/make.py build` 默认以“无签名编译”方式调用 `xcodebuild`，避免在本机开发和 CI 编译阶段被 `Provisioning Profile` 卡住
5. Python 侧尚未执行完整 `pytest`，因为当前环境缺少 `numpy / cv2 / pytest`
6. 已新增 `tools/macos_smoke.py`，可在构建产物就绪后校验 `status / install / uninstall` 命令链路
7. CI/Jenkins 已补上 `pkg / dmg / zip` 产物脚本入口与归档出口
8. `tools/make.py` 已补充统一入口：
   - `python3 tools/make.py preflight`
   - `python3 tools/make.py build`
   - `python3 tools/make.py build --archs arm64`
   - `python3 tools/make.py build --archs "arm64 x86_64" --deployment-target 13.0`
   - `python3 tools/make.py package`
   - `python3 tools/make.py package --sync-runtime`
   - `python3 tools/make.py package --archs "arm64 x86_64" --deployment-target 13.0`
   - `python3 tools/make.py sync-macos-runtime --require-pkg`
   - `python3 tools/make.py smoke`
   - `python3 tools/make.py direct-push-demo --frames 90 --output build/macos/direct-push-report.json`
   - `python3 tools/make.py verify-native`
   - `python3 tools/make.py benchmark`
   - `python3 tools/make.py benchmark --profile 1080p60 --output build/macos/benchmark-1080p60.json`
   - `python3 tools/make.py benchmark --matrix --output build/macos/benchmark-matrix.json`
   - `python3 tools/make.py validation-report`
   - `python3 tools/make.py release-diagnostics`
   - `python3 tools/make.py install-session --output build/macos/install-session.json`
   - `python3 tools/make.py validation-session --output-dir build/macos/session`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --run-install-session --run-uninstall --skip-demo --skip-benchmark`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --benchmark-profile 1080p60`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --benchmark-matrix`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --mode numpy-direct`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --mode latest-provider`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --mode image`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --mode pixmap`
   - `python3 tools/make.py validation-session --output-dir build/macos/session --mode video-file --video-path demo.mp4`
     该命令当前会在单次会话内自动生成 `session-acceptance.json`、`session-acceptance-contract.json` 与 `session-summary.md`
   - `python3 tools/make.py validation-session-acceptance --manifest build/macos/session/session-manifest.json --output build/macos/session/session-acceptance.json`
   - `python3 tools/make.py validation-session-acceptance-contract --output build/macos/session/session-acceptance-contract.json`
   - `python3 tools/make.py validation-session-summary --manifest build/macos/session/session-manifest.json --output build/macos/session/session-summary.md`
9. 已新增 `tools/macos_native_verify.py`，可在无完整 `xcodebuild` 的前提下执行原生语法、plist 与 `build / capability / topology / status / framebus / stream / sdk` 等 contract 校验
10. 已新增真实打包脚本集成测试，会在 macOS runner 上对最小 `.app` bundle 实际执行 `pkg / dmg / zip` 产物生成链路
11. 当前本机已实际验证最小 bundle 的 `pkg / zip` 生成成功；`dmg` 在当前受限运行环境下可能因 `hdiutil create failed - device not configured` 无法稳定通过，需以完整 macOS CI runner 或开发机复核
12. 已新增 `tools/macos_benchmark.py`，用于输出 Python Producer Path 的结构化基准结果，作为后续 `1080p60` 优化与 Shared Memory / IOSurface 取舍依据
13. 已新增 `tools/macos_capability_contract.py`，用于自动比对 `AKVCFrameProvider`、`AKVCCommandSupport` 与 benchmark profiles 的分辨率/帧率契约一致性
14. 当前这条 capability contract 还会继续校验：
   - `installer.py` 是否仍解析 `supported_formats / supported_frame_rates`
   - `macos_smoke.py`、`macos_install_session.py`、`macos_validation_report.py` 是否仍把这组能力声明向上层工件透传
   - `docs/benchmark/macos_virtual_camera_benchmark.md` 是否仍覆盖 `720p30 / 720p60 / 1080p30 / 1080p60 / 4K30 / 4K60` 与 `1080p60 CPU <10%` 基线
15. 已新增 `tools/macos_framebus_contract.py`，用于自动校验 `akvc_protocol.h`、`framebus_posix.c`、Python `_protocol.py` 与 `macos_shm.py` 的跨语言 Frame Bus 契约一致性
16. 已新增 `tools/macos_framebus_roundtrip.py`，用于在 macOS 上真实执行：
   - Python `MacOsShmSink` 写入 NV12 帧
   - `framebus_posix.c` 原生 consumer 通过 `framebus_consumer_probe.c` 读取
   - JSON 校验 `producer_seq / width / height / plane_size / checksum / producer_alive`
   这条链路开始把验证从“文本协议一致”推进到“跨语言真实互通”
   - 当前还支持 `--producer-kind mac-virtual-camera`，可改为通过公开 `VirtualCamera.start()+push_frame()` 对象路径写入共享内存，再复用同一份 native probe 校验
17. 已新增 `tools/macos_stream_contract.py`，用于自动校验 `AKVCFrameProvider` 与 `AKVCStreamSource` 的占位帧、超时/断裂处理、流属性面与定时推流语义是否一致
18. 已新增 `tools/macos_sdk_contract.py`，用于自动校验 `VirtualCamera` 兼容层的 Python 公共接口、生命周期方法、属性和上下文管理语义是否保持稳定
19. 已新增 `tools/macos_validation_report.py`，用于把安装状态、设备可见性、benchmark 与人工应用验证结果汇总成单一 JSON 验证工件
20. `validation-report.json` 当前还会输出 `runtime_assets`，用于记录：
    - Python 侧当前解析到的 `status / install / uninstall / list-devices / sync-ipc / pkg` 路径
    - 包内 `akvc/_runtime/macos` 是否真的包含这些分发资产
    这样可以区分“原生构建产物存在”和“Python 分发态安装链路真正可发现”这两类状态
21. 当前还会继续把 `runtime provenance` 与 `release-diagnostics` 的产品集身份对齐结果一路透传到：
    - `validation-report.json.summary`
    - `session-manifest.json.summary`
    - `session-summary.md`
    其中会显式比较 `host bundle / extension bundle / sync-ipc tool / pkg` 的 identity consistency，帮助区分“只是路径位置不同的同名交付物”与“验收链路实际绑定到了另一套工件”
22. 已新增 `tools/macos_release_diagnostics.py`，用于对当前 `.app / .systemextension / .pkg / .dmg / .zip` 做结构化发布诊断，包括：
    - bundle id
   - Host App 是否内嵌 Camera Extension bundle
   - Host / Extension 最低系统版本是否仍为 `13.0`
   - 可执行文件架构
   - `codesign --verify`
   - `pkgutil --check-signature`
   - `spctl` 评估结果
   - `PackageInfo` 中的 `identifier / version / install-location`
   - `pkgutil --payload-files` 中是否包含 Camera Extension payload
   - `akvc-macos-sync-ipc` 是否存在、是否已签名、是否为 `arm64 + x86_64`
22. 当前 `akvc.sdk.virtual_camera` 与 `akvc.core` 已进一步收紧惰性导入边界：`status / install / enumerate_devices` 等安装侧路径在未推帧前不再强制加载 `frame_input / frame_pipeline / numpy / cv2`
23. 已新增 `tools/macos_input_contract.py`，用于自动校验 `Frame/QImage/QPixmap/numpy/OpenCV` 输入矩阵、PySide6 bridge / streamer 入口，以及 demo `numpy-direct / provider / latest-provider / image / pixmap / widget / screen / video-file` 模式面是否仍保持完整
    当前这条 contract 也已继续覆盖 `akvc.sdk.virtual_camera` 与 `akvc.platforms.macos.virtual_camera` 的公共入口，固定：
   - `push_frame()/send()` 输入入口不会绕开 PySide6/QImage/QPixmap 支持
   - `create_pyside6_bridge()` 与 `send_image()/send_pixmap()/send_widget()/send_screen()` 这组直接 PySide6 入口持续存在
   - `create_latest_frame_provider()/create_pyside6_streamer()` 这组高层 helper 构造入口持续存在
24. `tools/pyside6_virtual_camera_demo.py` 当前也已优先走 Python 兼容层入口，而不是默认直接实例化 integration helper：
    - `numpy-direct` 直接走 `VirtualCamera.push_frame(numpy.ndarray)`，且不依赖 Qt
   - `provider / latest-provider / video-file` 优先通过 `VirtualCamera.create_pyside6_streamer()`
   - `latest-provider` 还会优先通过 `VirtualCamera.create_latest_frame_provider()`
   - `image / pixmap` 直接走 `VirtualCamera.send_image()` / `send_pixmap()`
   - `widget / screen` 则直接走 `VirtualCamera.send_widget()` / `send_screen()`
   这样 demo、验收会话与外部 PySide6 项目现在共享的是同一层 Python 对外能力，而不是旁路 helper
25. `validation-report.json -> session-manifest.json.summary -> session-summary.md` 当前也会继续显式透传这条 PySide6/SDK 路径证据：
   - `demo_python_entrypoint_kind`
   - `demo_sdk_streamer_factory_used`
   - `demo_sdk_latest_provider_factory_used`
   - `demo_sdk_direct_push_used`
   这样 CI 和人工验收现在可以直接区分本次会话到底走的是：
   - `push_frame`
   - `create_pyside6_streamer.start_provider_stream`
   - `create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream`
   - `send_image`
   - `send_pixmap`
   - `send_widget`
   - `send_screen`
   当前 `release-diagnostics.json.summary.pkg_payload_appledouble_clean` 也会继续前推到 `session-manifest.json.summary.release_pkg_payload_appledouble_clean`
   - 这样在 CI 工件页或人工验收时，只打开主 manifest 就能先判断当前 release pkg payload 是否已经清除 `._*` AppleDouble 元数据
   - `session-summary.md` 的 `Runtime Command Tools` 区域会继续显示同一条结论
24. 已新增 `tools/macos_build_contract.py`，用于自动校验 `project.yml`、Host/Extension `Info.plist` 与 `tools/make.py` 是否仍共同声明 `macOS 13.0`、`arm64 + x86_64`、`ONLY_ACTIVE_ARCH=NO` 与 `xcodebuild` 构建入口的双架构传播约束
25. 已新增 `tools/macos_app_matrix_contract.py`，用于自动校验 `Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime` 六个目标应用在安装器、`validation_report`、`smoke`、`session-manifest` 与 `session-summary` 中的矩阵覆盖是否保持一致
   - 当前还会固定人工验收模板里的 `evidence.device_listed / device_selected / preview_visible / screenshot` 结构，确保目标应用通过结论具备可复盘证据槽位
26. `tools/macos_ci_artifact_contract.py` 当前也已把 `build/macos/benchmark.json` 纳入 GitHub Actions / Jenkins 的必归档工件
   - 这样 `720p/1080p/4K x 30/60` 的结构化 benchmark 证据不会只存在于临时 runner 工作目录
   - 即使当前 validation-session 选择 `--skip-benchmark`，单独运行的 producer benchmark 结果也必须作为正式工件保留下来
   - 当前 contract 还会固定流水线文本里确实存在 `tools/macos_benchmark.py --output build/macos/benchmark.json`，避免只归档占位路径却不真正执行 benchmark
27. `tools/make.py build/package` 当前已显式支持 `--archs` 与 `--deployment-target`，便于本机单架构调试、CI 双架构构建和 `universal2` 分发前的一致性控制
27. macOS CI/Jenkins 的显式单测清单当前已新增 `tests/unit/test_macos_shm_sink.py`，用于固定 POSIX shared-memory producer 的：
   - `producer_seq` 递增
   - `seq_head / seq_tail` finalize
   - ring slot 回卷覆盖
   - heartbeat / writer_pid 更新
   - 短 payload 拒绝写入
28. macOS CI/Jenkins 当前还会显式运行 `python3 tools/make.py framebus-roundtrip --output build/macos/framebus-roundtrip.json`，并归档该 JSON，开始为“Python producer 与原生 consumer 真实互通”沉淀结构化证据
29. 当前这台受管开发环境上的本地 roundtrip 诊断结果显示：
   - producer 控制块已成功写入 `producer_seq=1`
   - 但独立原生 probe 进程对 `/akvc-frames-v1` 的 `shm_open(O_RDONLY)` 返回了 `EACCES (13)`
   这说明当前仍存在“环境是否允许跨进程打开该 POSIX shm”的运行时风险；外部 macOS runner / 真机 shell 仍需继续复核
29. `macos_validation_report.py` 当前也已支持 `--framebus-roundtrip-json`，会把：
   - `framebus_roundtrip_present`
   - `framebus_roundtrip_passed`
   - `framebus_roundtrip_direct_open_errno`
   - `framebus_roundtrip_environment_blocked`
   这些摘要字段并入统一验收报告
30. `macos_validation_session.py` 当前也已支持 `--run-framebus-roundtrip`，可把 `framebus-roundtrip.json` 作为会话工件的一部分自动生成并并入最终 `validation-report.json`
   - 当前 `validation-session` 默认还会透传 `--framebus-producer-kind mac-virtual-camera`
   - 这意味着会话工件默认验证的是公开 `VirtualCamera.start()+push_frame()` 对象路径，而不是只验证底层 `shm-sink`
   - 当前还可额外启用 `--run-direct-push-demo`，把 `tools/macos_direct_push_demo.py` 的结构化结果一并收进会话工件
31. `tools/macos_smoke.py` 当前也已支持 `--framebus-roundtrip-json`，并会把 `ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno / ipc_probe_path` 一并写入 `smoke-report.json`
32. `tools/macos_install_session.py` 当前也已支持 `--framebus-roundtrip-json`，并会把同一组 `ipc_*` 字段一并写入 `install-session-report.json`
33. `tools/macos_smoke.py` 与 `tools/macos_install_session.py` 当前也已支持直接纳入公开 `VirtualCamera` 对象直推证据：
   - 两者都新增 `--run-direct-push-demo / --direct-push-demo-tool / --direct-push-frames`
   - 会调用 `tools/macos_direct_push_demo.py`，并把结构化结果写入各自工件的 `direct_push_demo`
   - 因此单独跑 `smoke` 或 `install-session` 时，也能直接证明 `VirtualCamera.start() -> push_frame() -> close()` 这条公开 Python 路径是否实际跑过
34. `tools/make.py` 对 `smoke / validation-report / install-session / validation-session` 的 macOS 包装入口当前也已同步透传 `--name`：
   - 可直接从顶层命令把运行时摄像头名称写入共享 override，而不必降到脚本级入口
   - 这样 CI、本地构建机和人工验收脚本现在都能用同一条设备名参数路径
35. `tools/make.py smoke` 当前也已同步透传底层 `macos_smoke.py` 的 `status/install/list-devices/uninstall/host/pkg/sync-ipc/direct-push` 覆盖参数：
   - 这样顶层 smoke wrapper 现在不仅能跑默认路径，也能直接绑定某次构建产物、某个 container app（含 legacy host 兼容目标）或某套打包结果做安装链路验收
36. `tools/macos_install_session.py` 当前还会在 `post_status.shared_memory_name` 可用时主动执行一次显式 `sync-ipc`，并把结果写入 `install-session-report.json.sync_ipc`：
   - `supported / success / phase / shared_memory_name / ipc_transport / returncode`
   这样 install-session 不再只证明“自动安装链路成功”，也开始直接证明“显式 IPC 控制面命令在这次真实安装会话里跑通过”
37. `tools/macos_validation_session.py` 当前还会把 `smoke / install-session / framebus-roundtrip / validation-report` 的关键摘要聚合进 `session-manifest.json.summary`，便于在 CI 工件页或人工验收时先快速判断当前会话是否卡在 IPC 环节
   - 当前也会继续提升 `install_session_sync_ipc_present / supported / success / phase / shared_memory_name / ipc_transport / returncode`
   - `session-manifest.json.summary` 当前也会显式写出 `framebus_roundtrip_producer_kind`
   - 如果启用了 `--run-direct-push-demo`，摘要里还会继续带出 `direct_push_demo_*` 字段，直接说明公开 `VirtualCamera` 对象路径是否实际跑过
   - 当前还会继续提升 `smoke_direct_push_demo_*` 与 `install_session_direct_push_demo_*`，便于区分“主会话直推成功”与“安装后 smoke/install-session 子链路也各自实际跑过直推”
   这样主 manifest 和 `session-summary.md` 已能直接区分“sync-ipc 工具已进入发布态”和“本次 install-session 里显式同步命令真的执行成功”
31. 当前本机已确认 `xcodebuild`、`xcodegen`、`pkgbuild`、`codesign`、`notarytool` 和 `stapler` 均可探测；签名、公证所需的 `SIGN_IDENTITY / PRODUCTSIGN_IDENTITY / NOTARY_PROFILE` 仍需单独配置
32. 已新增 `tools/macos_toolchain_preflight.py` 与 `python3 tools/make.py preflight`，用于在真实构建前统一检查 `xcodebuild / xcodegen / pkgbuild / codesign / notarytool / stapler` 与签名、公证相关环境变量
33. 当前 `python3 tools/make.py package` 在检测到 `SIGN_IDENTITY` 时，会先调用 `python3 tools/make.py sign` 对 Host App 与 Camera Extension 执行显式签名，再继续生成 `pkg / dmg / zip`
34. 当前本机已实际跑通一次真实 `python3 tools/make.py build`，成功产出 container app 构建产物、`com.sidus.amaran-desktop.cameraextension.systemextension`、`akvc-macos-status`、`akvc-macos-install`、`akvc-macos-uninstall` 与 `akvc-macos-list-devices`
29. 当前本机已用 `lipo -archs` 确认 Host App、Camera Extension 与状态工具均为 `arm64 + x86_64` 双架构产物
30. 当前本机已实际运行 `akvc-macos-status` 与 `akvc-macos-list-devices`，命令工具可启动并返回结构化 JSON
31. 当前还已补充 `list-devices-binary-check`，用于独立验证 `akvc-macos-list-devices` 的 JSON 结构、`AKVC_DEVICE_PREFIX` 过滤语义，以及 `devices` 结果是否始终保持为 `all_devices` 子集
31. 当前本机已实际跑通无签名 `pkg` 与 `zip` 生成；`dmg` 仍受当前运行环境的 `hdiutil` 限制，需在完整 macOS 开发机或 CI runner 继续验证
32. 当前 `akvc-macos-status`、`macos_smoke.py` 与 `macos_validation_report.py` 输出中已显式包含 `extension_identifier`，用于区分真实 System Extension bundle id 与 `mach_service_name`
33. 当前 `python3 tools/make.py package --skip-build` 在 headless/受限环境下会保留 `pkg / zip` 产物，并对 `dmg` 失败输出降级说明，而不是直接中断整条打包链路
34. 当前 GitHub Actions 与 Jenkins 的 macOS 流水线已统一优先调用 `python3 tools/make.py package --skip-build`，不再在发布阶段直接绕开入口去串行调用原始 `build_pkg.sh / build_dmg.sh / build_zip.sh`
35. 当前 GitHub Actions 与 Jenkins 还会在 native build 后补跑一次 `python3 tools/make.py validation-session --skip-demo --skip-benchmark`，并归档：
   - `preflight.json`
   - `release-diagnostics.json`
   - `status-binary-check.json`
   - `list-devices-binary-check.json`（当 session 启用 `--run-list-devices-binary-check` 时）
   - `install-session-report.json`（当 session 启用 `--run-install-session` 时）
   - `smoke-report.json`（当 session 启用 `--run-install` 或 `--run-uninstall` 时）
   - `manual-results.template.json`
   - `validation-report.json`
   - `session-acceptance-contract.json`
   这样 CI 工件里不仅有 `pkg / dmg / zip`，也会同时保留一份工具链与安装状态快照。
   其中 `session-acceptance.json` 记录某次真实会话的最终验收结果，`session-acceptance-contract.json` 则记录 acceptance helper 自身的代表性行为回放，便于区分“本次工件失败”与“验收逻辑本身回退”。
   当前 `tools/macos_validation_session.py` 也已直接把这两份 acceptance 工件登记进 `session-manifest.json.artifacts`，并固定执行顺序为 `artifact-check -> acceptance -> acceptance-contract -> summary`，避免 CI 侧额外生成“主流程未知”的旁路工件。
   当前归档的 runtime 资产里也已显式包含 `akvc-macos-sync-ipc`，避免分发态只带安装命令而丢失显式 IPC 控制面
   当前 `validation-session -> validation-report` 也会把 `list-devices-binary-check.json` 继续注入总报告，因此归档后的 `validation-report.json` 已能直接体现“系统设备枚举链路是否自洽”
   如果后续人工把 `manual-results.template.json` 填成了真实 `manual-results.actual.json`，也可以在同一个输出目录上追加执行：
   - `python3 tools/make.py validation-session --output-dir build/macos/session --manual-results build/macos/session/manual-results.actual.json --reuse-existing-artifacts --skip-preflight --skip-release-diagnostics --skip-demo --skip-benchmark`
   这样无需重跑整套 demo / benchmark / preflight，就能刷新 `validation-report.json`、`session-acceptance.json` 与 `session-summary.md`
36. 当前还已新增 `tools/macos_status_binary_check.py`，用于在 build 后直接执行真实 `akvc-macos-status` 二进制，并通过临时 `framebus-roundtrip.json` fixture 验证它是否真的把 `ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno / ipc_probe_path / ipc_last_error` 合并进输出 JSON
37. 该检查当前会同时覆盖两类 IPC 阻塞夹具：
   - consumer 侧 `open_failed + direct_open_errno=13`
   - producer 侧 `producer_open_failed + direct_open_errno=1`
   这样可以同时固定“独立 probe 无法读 shm”和“producer 自己无法创建 shm”两条真实故障路径
38. `tools/macos_validation_report.py` 当前也已支持 `--status-binary-check-json`，会把 `status_binary_check_present / passed / ipc_keys_present / ipc_environment_blocked / ipc_direct_open_errno` 这些摘要字段并入统一验收报告
39. `tools/macos_validation_session.py` 当前也已支持 `--run-status-binary-check` 与 `--status-binary-check-tool`，可在会话阶段自动生成 `status-binary-check.json`，并把它透传进 `validation-report.json` 与 `session-manifest.json.summary`
40. `tools/macos_validation_session.py` 当前也已支持 `--run-list-devices-binary-check` 与 `--list-devices-binary-check-tool`，可在会话阶段自动生成 `list-devices-binary-check.json`，并把它写入 `session-manifest.json`：
   - `artifacts` 会登记 `list_devices_binary_check_report`
   - `steps` 会登记 `list_devices_binary_check`
   - `summary` 会继续聚合 `list_devices_binary_check_present / passed / device_prefix / filtered_device_count / total_device_count / override_no_match_ok`
   - `session-summary.md` 当前也会新增 `List-Devices Binary Check` 小节，便于直接人工复盘 prefix 过滤与枚举结果
41. 当前 `camera-core/src/akvc/platforms/macos/installer.py` 还已新增共享 readiness 诊断层：
   - `infer_extension_phase()` 统一推断 `installed_visible / pending_approval / timeout_waiting_for_device`
   - `evaluate_extension_readiness()` 统一推断 `ready / approval_required / ipc_environment_blocked / ipc_not_ready / device_not_visible / install_failed`
   - `akvc status`、`akvc install` 与 `validation-report.json` 现在会显式输出 `start_ready / start_blocker_code` 或 `readiness.blocker_code`
   - 另外已新增 `tools/macos_readiness_contract.py`，并接入 `tools/macos_native_verify.py` / GitHub Actions / Jenkins，专门固定这套 blocker 优先级与阶段推断语义
42. `tools/macos_smoke.py`、`tools/macos_install_session.py` 与 `tools/macos_validation_session.py` 当前也已接入同一套 readiness 口径：
   - `smoke-report.json` / `install-session-report.json` 会显式输出 `start_ready / start_blocker_code / start_message / start_steps`
   - `session-manifest.json.summary` 会继续汇总 `smoke_start_blocker_code / install_session_start_blocker_code / effective_start_blocker_code`
43. `tools/macos_validation_session.py` 当前还会把能力声明继续提升到 `session-manifest.json.summary`：
   - `validation_supported_formats / validation_supported_frame_rates`
   - `smoke_supported_formats / smoke_supported_frame_rates`
   - `install_session_supported_formats / install_session_supported_frame_rates`
   - `effective_supported_formats / effective_supported_frame_rates`
   这样 CI 在不展开子工件时，也能直接确认本次会话最终暴露的是 `720p / 1080p / 4K` 与 `30 / 60fps` 哪一档能力
44. 同一层摘要当前也已继续保留 IPC 身份信息：
   - `validation_shared_memory_name / validation_mach_service_name / validation_ipc_transport`
   - `smoke_shared_memory_name / smoke_mach_service_name / smoke_ipc_transport`
   - `install_session_shared_memory_name / install_session_mach_service_name / install_session_ipc_transport`
   - `effective_shared_memory_name / effective_mach_service_name / effective_ipc_transport`
   这样 CI 或人工验收在只看主 manifest 时，也能直接判断本次会话最终实际落到哪条共享内存命名、Mach Service 与 IPC transport，而不必再翻子工件 JSON
   当前 `VirtualCamera` 运行中如果再次执行 `sync_ipc_configuration_result("/new-shm")`，在原生命令返回 supported+success 后也会把 producer sink 一并重绑到新 shm 名称，避免 Camera Extension 已切换 descriptor，但 Python 侧仍继续向旧共享内存写帧。
45. `session-summary.md` 当前还会继续输出 `Runtime Topology` 小节：
   - 会直接显示 `runtime_topology_kind=camera_extension_direct_framebus`
   - 会显示 `runtime_host_role=container_activation_command_bridge`
   - 会明确标注 `runtime_host_in_frame_hot_path=no`
   - 会同步展示 `runtime_data_plane / runtime_control_plane`
   这样 CI 工件页和人工验收摘要现在都能直接证明：当前 macOS 方案不是“零宿主容器”，而是“有宿主容器，但没有独立 frame-relay daemon，且 Host 不在高频帧热路径”。
46. `tools/macos_capability_contract.py` 当前也已把 `macos_validation_session.py` 纳入 capability surface 检查：
   - 会确认会话层确实读取 `validation-report / smoke / install-session` 的 `supported_formats / supported_frame_rates`
   - 会确认 `session-manifest.json.summary` 继续导出 `validation_* / smoke_* / install_session_* / effective_*` 四组能力字段
   这样能力链路现在不只校验到 `validation-report.json`，而是继续收紧到了最终 CI 验收摘要层
47. 当前还已新增 `tools/macos_validation_session_contract.py`，用于固定 `session-manifest.json.summary` 的行为契约：
   - 会直接校验 `effective_start_ready / effective_start_blocker_code`
   - 会固定 `validation -> smoke -> install-session` 的开始推流摘要优先级
   - 会固定 `install-session -> smoke -> validation-report` 的能力摘要回退顺序
47. `tools/macos_validation_session_summary.py` 当前也已进一步收紧 reader-facing 摘要的回退逻辑：
   - 即使 `session-manifest.json.summary` 暂时还没有显式写出 `validation_passed_app_ids / validation_failed_app_ids / validation_pending_app_ids / validation_skipped_app_ids / validation_unreviewed_app_ids`
   - 只要 `validation_app_matrix` 仍在，`session-summary.md` 也会自动回推出 `passed/failed/pending/skipped/unreviewed` 分组和对应计数
   这样 CI / Jenkins 在只消费主 manifest 的场景下，也不会因为上游统计字段缺失而丢失目标应用验收摘要
   这样 validation session 顶层摘要不再只是“字段存在”，而是会被代表性 case 自动验证
48. 当前还已把 Python 兼容入口 contract 接回最终 validation session 会话：
   - `tools/macos_validation_session.py` 会在生成 `validation-report.json` 后自动执行 `tools/macos_entrypoints_contract.py`
   - 会默认产出 `entrypoints-contract.json`
   - `session-manifest.json` 的 `artifacts` 当前会登记 `entrypoints_contract_report`
   - `steps` 当前会登记 `entrypoints_contract`
   - `session-manifest.json.summary` 当前会继续聚合：
     - `entrypoints_contract_present`
     - `entrypoints_contract_passed`
     - `entrypoints_contract_surface_complete`
     - `entrypoints_contract_demo_case_complete`
     - `entrypoints_contract_cli_case_complete`
     - `entrypoints_contract_desktop_case_complete`
   - `session-summary.md` 当前也会新增 `Python Entrypoints` 小节，直接面向人工验收展示 PySide6 demo / direct-push demo / CLI / desktop 四条入口链是否仍共同走 `VirtualCamera` 兼容层
   这样“SDK 契约正确”和“最终验收会话里真的保留了统一入口证据”现在已经收敛为同一条可回放工件链
   - GitHub Actions 与 Jenkins 当前也会把 `build/macos/session/entrypoints-contract.json` 一并归档，避免会话 manifest 中声明了这份工件，但 CI 工件页里却找不到对应证据
49. `tools/pyside6_virtual_camera_demo.py -> tools/macos_validation_report.py -> tools/macos_validation_session.py -> tools/macos_validation_session_summary.py` 当前还已继续把 `consumer_count` 提升到最终会话摘要层：
   - `demo-report.json` 继续记录 `consumer_count`
   - `validation-report.json.summary` 当前开始导出 `demo_consumer_count`
   - `session-manifest.json.summary` 当前开始导出 `validation_demo_consumer_count`
   - `session-summary.md` 当前也会直接渲染 `Consumer count`
   这样 PySide6 直推链路现在不只证明“demo 跑过了哪种 mode”，还开始证明“本次 demo 运行时是否真的看到了 consumer”
50. 当前目标应用验收证据还已继续前推到主摘要层：
   - `validation-report.json.summary` 当前会新增：
     - `reviewed_app_ids`
     - `observed_target_app_ids`
     - `missing_target_app_ids`
     - `unexpected_target_app_ids`
     - `target_app_ids_complete`
   - `session-manifest.json.summary` 当前也会继续保留对应的 `validation_*` 字段
   - `session-summary.md` 的 `Target Apps` 小节当前会直接渲染：
     - `Reviewed`
     - `Observed target ids`
     - `Target id set complete`
     - `Missing target ids`
     - `Unexpected target ids`
     - 逐应用的 `steps / checks` 数量，以及首条 `first_step / first_check`
   这样 CI / Jenkins 在只看主工件时，不必再手工展开 `verification_targets` 明细，也能直接知道本次人工验收到底缺了哪些目标应用、是否混入了意外 app id
   同时也能直接看到“下一步该进哪个应用设置页、先观察哪条通过现象”
51. 当前还已新增 `tools/macos_validation_session_artifact_check.py` 与 `python tools/make.py validation-session-artifact-check`：
   - 会直接回放真实 `session-manifest.json`
   - 会校验 `artifacts / steps / summary` 结构是否完整
   - 会额外回放 `manual-results.template.json` 是否仍覆盖六个目标应用，且每个条目都保留非空 `checks / steps`
   - 也会确认每个条目都保留 evidence 槽位，供后续 `target_apps_all_passed` 门禁判断设备是否被目标应用识别、选择并成功预览
   - 会在启用 `--require-existing-artifacts` 时确认本次会话声明为已生成的工件文件确实存在
   - 会进一步检查 `effective_start_*` 与 `effective_supported_*` 的值域是否仍与当前能力/阻塞口径一致
   - 当前也会继续校验 `validation_reviewed_app_ids / validation_missing_target_app_ids / validation_unexpected_target_app_ids / validation_target_app_ids_complete` 这组目标应用 identity 字段在主 manifest 中的类型面
   - 当前也会继续检查 `entrypoints_contract_report` 是否存在，以及 `entrypoints_contract_*` 六个摘要字段在存在时是否仍保持正确类型
   - 当前还会继续检查 `install_session_sync_ipc_*` 的类型面，以及 `sync_ipc_control_plane_ready=pass` 时是否真的伴随 `install_session_sync_ipc_present/supported/success=true`
   - 当前还会继续检查：
     - `release_sync_ipc_tool_exists / release_sync_ipc_tool_signed / release_sync_ipc_tool_universal2_ready`
     - `target_apps_all_passed / system_camera_device_visible / auto_install_ready / signing_evidence_ready / notarization_tooling_ready / runtime_assets_packaged / sync_ipc_control_plane_ready`
     这样 release diagnostics、acceptance 与 session manifest 三段关于 `sync-ipc` 的证据链现在也会被统一回放校验
   这样 CI 不再只验证“代码会生成 manifest”，而是会继续验证“生成出来的 manifest 作为真实工件是否自洽”
52. `tools/macos_validation_session.py` 当前也已开始原生集成这一步：
   - 会在生成 `validation-report.json` 与 `session-manifest.json.summary` 后自动调用 artifact check
   - 会默认产出 `session-manifest-check.json`
   - 会把 `artifact_check_present / artifact_check_passed` 继续写回 `session-manifest.json.summary`
   这样“统一验收会话”现在已经自带一轮真实 manifest 回放，而 GitHub Actions / Jenkins 里的额外调用更像是对归档工件的二次复核
53. 当前还已新增 `tools/macos_validation_session_acceptance.py`：
   - 会把 `session-manifest`、`validation-report`、`preflight`、`benchmark` 等会话工件收敛成一份 acceptance 摘要
   - 会按最终验收标准输出 `pass / fail / unknown`
   - 当前还已新增 `tools/macos_validation_session_acceptance_contract.py`：
     - 会直接回放 acceptance helper 的代表性 case，而不只是检查源码表面
     - 当前已覆盖完整通过、只有计数时保持 unknown、manifest 显式 target identity 覆盖 report 推导、entrypoints/benchmark 缺证据保持 unknown 这几类关键行为
     - `tools/macos_native_verify.py`、GitHub Actions 与 Jenkins 当前也已接入这条 contract
   - `tools/macos_delivery_gate_contract.py` 当前也已把 `target_apps_all_passed`、`system_camera_device_visible` 与 `sync_ipc_control_plane_ready` 一并纳入最终 delivery gate contract：
     - 六个目标 app id 恰好齐全且全部 `pass` 时为 `pass`
     - 只有通过数量、缺少精确 app id 证据时保持 `unknown`
     - 存在缺失/意外 app id 时直接 `fail`
     - `akvc-macos-list-devices` 自检缺失时，`system_camera_device_visible` 保持 `unknown`
     - `akvc-macos-list-devices` 自检运行但没有枚举到匹配虚拟摄像头时，`system_camera_device_visible=fail`
     - 只有 `akvc-macos-sync-ipc` 发布证据、但缺少 install-session runtime sync 成功证据时，`sync_ipc_control_plane_ready` 不会误报为 `pass`
     这样 `tools/macos_native_verify.py` 和 CI/Jenkins 不再只校验交付结构本身，也会继续校验最终门禁是否真的按六个指定宿主应用收口
   - `macos_validation_session.py` 当前也会自动生成 `session-acceptance.json` 与 `session-acceptance-contract.json`
   - `session-manifest.json.summary` 当前会继续保留 `acceptance_present / acceptance_ready / acceptance_failed_criteria / acceptance_unknown_criteria`
   - 同一份 summary 当前也会保留 `acceptance_contract_present / acceptance_contract_passed`
   - 当前 acceptance gate 里也已新增 `python_entrypoints_consistent`：
     - 会优先复用 `entrypoints-contract.json`
     - 并结合 `entrypoints_contract_passed / surface_complete / demo_case_complete / cli_case_complete / desktop_case_complete`
     - 用于判断 PySide6 demo / direct-push demo / CLI / desktop 四条入口链是否仍共同走统一 `VirtualCamera`
   - `target_apps_all_passed` 当前也已从“通过数量”收紧到“六个指定应用集合本身完整且全部通过”：
     - 会优先读取 `validation_observed_target_app_ids / validation_missing_target_app_ids / validation_unexpected_target_app_ids`
     - 如果主 manifest 没有显式 target identity 字段，才回退到 `validation_app_matrix` 与 `validation_*_app_ids`
     - 会显式检查 `zoom / teams / google_meet / obs / quicktime / facetime` 六个 app id 是否恰好齐全
     - 只要 `missing_target_app_ids` 或 `unexpected_target_app_ids` 非空，即使通过计数看起来完整，也会直接 `fail`
     - 如果当前只有 `validated_apps=6 / passed_apps=6` 这类计数证据，而缺少精确 app id 集合，则保持 `unknown`，不再误判为 `pass`
   这样 CI 现在不仅能看“工件是否自洽”，还能直接看“离最终验收标准还差哪些证据”
54. 当前还已新增 `tools/macos_validation_session_summary.py`：
   - 会从 `session-manifest.json` 与 `session-acceptance.json` 生成一份 reader-friendly 的 `session-summary.md`
   - 当前也会继续显式渲染 `Acceptance Contract` 小节，帮助区分“本次验收失败”和“acceptance helper 自身 contract 回退”
   - 会直接汇总：
     - `artifact_check_passed / acceptance_ready / acceptance_contract_passed`
     - `validation_install_present / validation_install_phase / validation_install_start_blocker_code`
     - `validation_install_supported_formats / validation_install_supported_frame_rates`
     - `validation_install_ipc_probe_present / validation_install_ipc_ready / validation_install_ipc_environment_blocked`
     - `install_session_present / install_session_success / install_session_start_blocker_code`
     - `install_session_ipc_probe_present / install_session_ipc_ready / install_session_ipc_environment_blocked`
     - `validation_demo_present / validation_demo_mode / validation_demo_mode_supported`
     - `validation_demo_frame_source_kind`
     - `validation_benchmark_kind / validation_benchmark_matrix_profiles`
     - `validation_demo_width / validation_demo_height / validation_demo_fps / validation_demo_duration`
     - `validation_demo_camera_name / validation_demo_video_path`
     其中 `validation-session-acceptance` 还会继续校验 `demo_mode` 与 `validation_demo_frame_source_kind` 的对应关系，确保会话工件不只是“跑过 demo”，而是能稳定证明具体走了哪条 PySide6 输入路径
     当前 `validation-session-acceptance` 还会额外输出一个非关键 criterion：
     - `sync_ipc_control_plane_ready`
     该 gate 现在不仅要求 `akvc-macos-sync-ipc` 已存在、已签名、且满足 `universal2`
     还要求 `install-session` 已产出一次 `sync_ipc.supported=true && success=true` 的运行时证据
     当前 release 相关 gate 还会优先复用 `validation-report.json.summary`，并在缺失时继续回退到 `release-diagnostics.json.summary`
     同时对“部分证据缺失”的场景保持 `unknown`，而不是因为 `None` 被错误折叠成 `fail`
     这条三态语义当前也已覆盖 `notarization_tooling_ready`，因此 `can_notarize=true` 但 `can_staple` 尚未验证的会话不再被误判成 `fail`
     同时 benchmark matrix 的六档 profile 也会继续提升到主 manifest 摘要层，便于 CI 或人工复盘直接读取每档 `actual_fps / cpu_percent / avg_latency_ms / fps_target_met / cpu_target_met`
     - `effective_start_blocker_code`
     - `effective_supported_formats / effective_supported_frame_rates`
     - `validation_passed_app_ids / validation_failed_app_ids / validation_pending_app_ids / validation_unreviewed_app_ids`
     - `validation_validated_apps / validation_passed_apps / validation_failed_apps / validation_pending_apps / validation_skipped_apps`
     - `validation_app_matrix` 的逐应用明细（`result / reviewed / validated / notes / ready / status`）
     - `macos_13_plus_declared / universal2_ready / release_packaging_ready / pyside6_path_exercised / runtime_assets_packaged`
     - `python_entrypoints_consistent`
     - `sync_ipc_control_plane_ready`
     - `target_apps_all_passed / system_camera_device_visible / auto_install_ready / signing_evidence_ready / notarization_tooling_ready / benchmark_matrix_complete / benchmark_fps_targets_met / benchmark_1080p60_cpu_target_met`
   - GitHub Actions 与 Jenkins 当前也会把这份 Markdown 一并归档，便于在工件页直接读取，而不是手工展开多份 JSON
   - 这样现在只看一页摘要，也能知道本次 Python/PySide6 直推到底跑的是 `numpy-direct / provider / latest-provider / image / pixmap / widget / screen / video-file` 哪条路径、底层来源语义是什么，以及运行时请求的尺寸/帧率/视频文件输入
25. 已新增 `tools/macos_direct_push_demo.py`，用于提供最小的“公开对象直推”脚本：
   - 直接执行 `VirtualCamera.start() -> push_frame(numpy.ndarray) -> close()`
   - 不依赖 Qt / PySide6
   - `tools/make.py direct-push-demo` 当前也已接到这条入口，便于本机或 CI 手动复现
   - 同时 `tools/macos_validation_session.py` 当前也会把这些 acceptance gate 的状态与 `acceptance_passed_count / acceptance_failed_count / acceptance_unknown_count` 一起合并回 `session-manifest.json.summary`
   - `tools/pyside6_virtual_camera_demo.py` 当前生成的 `demo-report.json` 也会在 `video-file` 模式下保留 `video_path`，因此 `validation_demo_video_path` 不再只是测试夹具字段，而是会由真实 demo 运行产出
48. 当前发布脚本已进一步收紧：
   - `sign_app.sh` 会拒绝缺失 Extension bundle / entitlements 的签名请求
   - `notarize.sh` 会拒绝对 `no signature / not signed` 的 `pkg` 发起公证
   - `staple.sh` 会在 `stapler` 之后补充 `spctl -a -vvv -t install` 评估
   这样可以更早暴露“构建成功但发布不可交付”的问题
42. 当前 `tools/make.py` 已新增 `sync-macos-runtime` 入口，可把：
   - `akvc-macos-status`
   - `akvc-macos-install`
   - `akvc-macos-uninstall`
   - `akvc-macos-list-devices`
   - `akvc-macos-sync-ipc`
   - `VirtualCamera.pkg`
   同步到 `camera-core/src/akvc/_runtime/macos`
43. 当前 `python3 tools/make.py package --sync-runtime` 会在成功生成 `pkg / zip` 后自动执行这一步，开始为 wheel / 外部 PySide6 打包目录提供可发现的 macOS runtime 资源
44. 当前还已新增 `tools/macos_distribution_contract.py`，用于把分发态闭环提升成独立契约检查：
   - 会固定 `tools/make.py sync-macos-runtime` 是否仍同步 `status / install / uninstall / list-devices / sync-ipc / pkg`
   - 会固定 `akvc.runtime` 是否仍能从包内 `_runtime/macos` 发现 `akvc-macos-sync-ipc` 与 `VirtualCamera.pkg`
   - 会固定 `tools/macos_validation_report.py` 的 runtime snapshot 是否仍导出：
     - `sync_ipc_tool_resolved`
     - `packaged_tools_present`
     - `packaged_pkg_present`
   - 会固定 `tools/macos_release_diagnostics.py` 是否仍导出：
     - `sync_ipc_tool_exists`
     - `sync_ipc_tool_signed`
     - `sync_ipc_tool_universal2_ready`
   - `tools/macos_native_verify.py` 当前也已接入这条检查，开始把“构建目录已存在产物”进一步收紧到“分发态 runtime 与 release 诊断面未漂移”
45. 当前还已新增 `tools/macos_signing_pipeline_contract.py`，用于把签名/公证/封口脚本提升成独立契约检查：
   - 会固定 `sign_app.sh` 是否仍先签 Extension 再签 Host，并执行 `codesign --verify` 与 `spctl`
   - 会固定 `build_pkg.sh` 是否仍保留 `productsign` 与 `pkgutil --check-signature`
   - 会固定 `notarize.sh` 是否仍拒绝未签名 `pkg`
   - 会固定 `staple.sh` 是否仍执行 `stapler staple / validate` 与 `spctl -t install`
   - 会固定 `tools/macos_release_diagnostics.py` 与 `tools/macos_validation_report.py` 是否仍导出 `app_signed / extension_signed / pkg_signed` 及对应 `release_*` 摘要
   - `tools/macos_native_verify.py` 当前也已接入这条检查，开始把“有发布脚本”进一步收紧到“签名链路语义未漂移”
45. 已新增 `tools/macos_topology_contract.py`，用于自动校验 `AKVCProviderSource`、`AKVCDeviceSource` 与 `bootstrapProviderGraph()` 的 Camera Extension 拓扑契约，包括：
   - `AK Virtual Camera / AKVC / com.akvc.camera.device` 等默认标识是否仍保持一致
   - `AKVC Stream`、`CMIOExtensionStreamDirectionSource`、`CMIOExtensionStreamClockTypeHostTime` 是否仍按系统摄像头 Source 语义注册
   - `startServiceWithProvider`、`addStream`、`addDevice` 与 ring descriptor -> `FrameProvider` 的接线是否仍完整
46. `tools/macos_native_verify.py`、GitHub Actions、Jenkins 与 release skeleton 单测当前也已接入这条 topology contract，开始把“能编译”进一步收紧到“Provider/Device/Stream 系统图谱未漂移”
47. 当前 macOS POSIX FrameBus consumer 已开始维护共享控制块中的 `consumer_count`：
   - `akvc_fb_open()` 成功后会递增
   - `akvc_fb_close()` 关闭时会递减
   - `framebus_consumer_probe.c` 与 `macos_framebus_roundtrip.py` 当前也已开始透出该字段
48. 这意味着在完整依赖环境里，macOS 侧 `VirtualCamera.consumer_count` 与 roundtrip/probe 诊断现在开始具备与 Windows 更接近的“原生 consumer 是否真正附着”可观测性，而不再长期固定为 `0`
49. 当前 `tools/macos_framebus_roundtrip.py` 已进一步收紧到“诊断优先”模式：
   - 导入路径不再强依赖 `numpy`
   - 即使 producer 侧 `shm_open(create)` 就失败，也会输出结构化 JSON，而不再直接抛 traceback
   - 当失败里出现 `errno=1 / 13` 时，`validation-report` 与 `validation-session` 当前也会统一把它归类为 `ipc_environment_blocked`
50. 当前已新增 `tools/macos_ci_artifact_contract.py`，用于固定 GitHub Actions 与 Jenkins 的 macOS 验收产物发布契约：
   - 两条流水线都必须归档 `VirtualCamera.pkg / .dmg / .zip`
   - 两条流水线都必须归档 `_runtime/macos` 下的 `status / install / uninstall / list-devices / sync-ipc / pkg`
   - 两条流水线都必须归档 `list-devices-binary-check.json`、`validation-report.json`、`session-manifest.json`、`session-summary.md` 与 `manual-results.template.json`
   - 两条流水线都必须运行 `validation-session-artifact-check --require-existing-artifacts`、`validation-session-summary` 与 `validation-session-acceptance-contract`
   - `tools/macos_native_verify.py` 当前也已接入这条检查，防止 CI 看似通过但人工验收所需工件缺失
51. 当前已在本机 Xcode 16.2 跑通无签名 `xcodebuild`：
   - `python3.12 tools/make.py configure`
   - `python3.12 tools/make.py build --archs arm64 --deployment-target 13.0`
   - `python3.12 tools/make.py build --archs "arm64 x86_64" --deployment-target 13.0`
   - `tools/macos_build_contract.py` 会固定所有编入 `AKVCCommandSupport.mm` 的控制桥 / 命令工具目标都链接 `AVFoundation.framework`
52. 当前 universal2 产物诊断结果：
   - Host App 和 Camera Extension 均为 `arm64 + x86_64`
   - `release-diagnostics-current.json.summary.universal2_ready=true`
   - `pkg_exists=true / zip_exists=true / host_embeds_extension_bundle=true`
   - `app_signed=false / extension_signed=false / pkg_signed=false`，因为当前环境没有 `SIGN_IDENTITY / PRODUCTSIGN_IDENTITY / NOTARY_PROFILE`
53. 当前打包链路状态：
   - `python3.12 tools/make.py package --skip-build --archs "arm64 x86_64" --deployment-target 13.0` 可生成 `VirtualCamera.pkg` 与 `VirtualCamera.zip`
   - 当前受限环境下 `hdiutil create` 会报“设备未配置”，因此本机不会稳定生成 dmg；完整 macOS CI runner 或开发机仍需复核 dmg
   - zip 与 pkg 当前都已清理 AppleDouble 元数据；`pkgutil --payload-files build/macos/VirtualCamera.pkg` 中 `._*` 条目计数已验证为 `0`
   - `build_pkg.sh` 会在 `pkgbuild` 后重建 Payload cpio 与 BOM，避免 `pkgbuild` 对 bundle component 推断时生成 0 字节 AppleDouble 清单项
   - `release-diagnostics-current.json.summary.pkg_payload_appledouble_clean=true`，该字段已进入 `release_packaging_ready` 门禁
54. 当前可人工验收到的阶段：
   - 可以验收“无签名 universal2 原生构建是否成功”
   - 可以验收“pkg/zip 是否生成、Extension 是否嵌入 Host App”
   - 可以验收 `akvc-macos-status` 与 `akvc-macos-list-devices` 二进制是否可运行并输出 JSON
   - 还不能验收“Zoom/Teams/Meet 可识别摄像头”，因为那一步必须先完成 Developer ID 签名、公证、pkg 安装、System Extension 批准与系统摄像头枚举
   - 当前判断“现在能不能开始真机人工验收”，优先看 `session-manifest.json.summary.manual_app_validation_ready`
   - 如果它是 `false` 或 `unknown`，继续看 `manual_app_validation_failed_criteria / manual_app_validation_unknown_criteria / manual_app_validation_blockers`
   - `akvc status --json` / `akvc install --json` 也会额外保留 `manual_app_validation_*_ids`，用于机器读取原始 gate id；非 JSON 的 CLI 与桌面端安装提示则优先显示中文标签
   - `session-summary.md` 当前也会把这三组前置条件渲染成中文 reader-facing 标签，便于 CI 工件页直接阅读；需要逐项对照 contract 时再回看 manifest 里的原始 gate id
   - 如果只是 `validation_manual_validation_ready=true`，不能单独说明已经适合开始 Zoom / Teams / Meet 真机验收；它更偏向“应用结果模板已经准备好”
55. 当前 release 诊断已把 runtime 命令工具纳入一等发布资产：
   - `akvc-macos-status / install / uninstall / list-devices / sync-ipc` 必须全部存在
   - 签名流水线必须对这些工具执行 `codesign --options runtime --timestamp`
   - `release-diagnostics.json.summary` 会输出 `command_tools_exist / command_tools_signed / command_tools_universal2_ready`
   - `release-diagnostics.json.summary` 也会输出 `pkg_payload_appledouble_clean`，用于证明 pkg payload 清单不含 `._*` 元数据项
   - `session-acceptance.json` 的 `signing_evidence_ready` 当前要求 Host App、Camera Extension、runtime tools 与 pkg 全部具备签名证据
56. 关于 `/Users/admir/workspace/cameraextension` 参考项目的结论：
   - 它没有独立常驻 host daemon，因此可以作为“帧热路径绕过 host”的佐证
   - 它仍有 `samplecamera.app` 负责嵌入 `.systemextension` 并提交系统扩展激活请求，因此不能解读为“Camera Extension 完全不需要容器 App”
   - 当前项目保留 legacy `akvc-host.app` 主要是为了兼容已有安装、CLI、Python 兼容层和 CI 验证流程；正式跨平台集成时更推荐把 GUI App 自身改造成 container app，但不能让控制面容器参与每帧转发
