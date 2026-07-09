# macOS 安装说明

## 1. 安装目标

macOS 安装流程需要完成：

1. 部署 Container App
2. 安装并激活 Camera Extension
3. 提供卸载与升级路径

## 2. 推荐安装形式

主安装形式：

1. `VirtualCamera.pkg`

补充分发形式：

1. `VirtualCamera.dmg`
2. `VirtualCamera.zip`

原因：

1. 更适合安装脚本
2. 更适合系统扩展部署
3. 更适合升级和卸载管理

## 3. 安装流程

推荐流程：

1. 安装 `VirtualCamera.pkg`
2. 将 App 放置到 `/Applications`
3. 首次启动时提交 `OSSystemExtensionRequest`
4. 用户在系统设置中批准扩展
5. 安装完成后刷新设备状态

当前代码骨架中，Python 层通过以下命令桥接安装状态：

1. `akvc-macos-status`
2. `akvc-macos-install`
3. `akvc-macos-uninstall`
4. `akvc-macos-list-devices`

当前仓库中的开发期验证入口：

1. `python3 tools/macos_smoke.py`
2. `python3 tools/macos_smoke.py --run-install`
3. `python3 tools/macos_smoke.py --run-uninstall`
4. `python3 tools/make.py smoke`
5. `python3 tools/make.py verify-native`

补充说明：

1. `akvc-macos-status` 侧重系统扩展状态
2. `akvc-macos-list-devices` 侧重系统视频设备枚举
3. 如果想独立验证 `akvc-macos-list-devices` 的 JSON 结构和 `AKVC_DEVICE_PREFIX` 过滤语义，可运行：
   `python3 tools/make.py list-devices-binary-check --list-devices-tool build/macos/Build/Products/Release/akvc-macos-list-devices --output build/macos/session/list-devices-binary-check.json`
   - 如果这次验收使用了自定义设备名，可继续追加 `--expected-prefix "你的设备名"`
   - 如果不传，工具会优先读取与 Camera Extension 共享的设备名配置，而不是固定假设 `AK Virtual Camera`
4. `tools/macos_smoke.py` 现已同时输出 `status.devices` 与 `enumerated_devices`
5. Python 侧 `install_extension()` 现会在安装命令返回后继续轮询状态收敛，而不是只看退出码
6. 如果状态已进入 `installed`，且设备枚举工具可用，会继续等待系统视频设备列表里出现虚拟摄像头候选
7. `tools/macos_smoke.py --run-install` 现会输出安装阶段 `phase`，当前已覆盖：
   - `pending_approval`
   - `installed_visible`
   - `timeout_waiting_for_install`
   - `timeout_waiting_for_device`
   - `package_install_failed`
   - `install_command_failed`
   - `install_failed`
7. `VirtualCamera` 现可直接读取 `install_extension_result()`，用于保留阶段信息；原有 `install_extension()` 仍保持布尔返回
8. `akvc` 兼容命令面现已提供 macOS `install` / `install --json`，可直接查看安装阶段结果，无需手工拼接 smoke 输出
9. `akvc` 兼容命令面现也已提供 macOS `uninstall` / `uninstall --json`，可直接查看停用与卸载状态回落结果
10. `VirtualCamera` 现在已补充：
   - `uninstall_extension_result()`
   - `uninstall_extension()`
   用于把“停止推流 -> 停用扩展 -> 轮询状态回落”收口为统一 Python 能力
11. `apps/desktop` 现已把安装阶段结果接入 `ServiceFacade / MainViewModel / MainWindow`，可直接在 PySide6 界面中看到安装状态、阶段和设备可见性
12. 桌面端当前还会根据安装阶段生成引导文案，例如提示用户前往“系统设置 > 隐私与安全性”批准扩展，或提示设备列表尚未收敛
13. 桌面端当前还会为关键阶段生成步骤清单，例如：
   - `pending_approval`：打开系统设置、批准扩展、返回应用重查
   - `installed_visible`：打开 Zoom/Meet/OBS、选择 AK Virtual Camera、必要时重启目标应用
14. 桌面端当前还提供：
   - `Install`
   - `Open Settings`
   - `Recheck`
   三个安装辅助动作，帮助用户完成从发起安装到批准后重新检测的闭环
15. `Open Settings` 现在已经收口为统一能力：
   - 桌面端按钮会优先尝试打开更接近 `隐私与安全性` 的系统设置入口
   - CLI 现在也支持 `akvc open-settings`
   - 如果当前 macOS 版本不接受深链，会自动回退到直接打开 `System Settings.app`
16. 桌面端当前还会生成结构化“目标应用验证清单”，覆盖：
   - `Zoom`
   - `Teams`
   - `Google Meet`
   - `OBS`
   - `QuickTime`
   - `FaceTime`
17. 验证清单会根据当前安装阶段自动切换：
   - 未安装 / 待批准：提示先完成安装或系统批准
   - `installed_visible`：给出每个目标应用中的具体验证入口，例如 Zoom 视频设置、OBS `Video Capture Device`、QuickTime 影片录制等
18. 这套验证清单当前已接入 `ServiceFacade -> MainViewModel -> MainWindow`，后续也可以直接复用于 CLI / 集成测试报告输出
19. `akvc status --json`、`akvc install --json` 与 `akvc uninstall --json` 当前都可以直接作为安装/卸载诊断入口
20. `akvc status --json` 当前还会显式输出 `phase`，用于区分：
   - `pending_approval`
   - `installed_visible`
   - `timeout_waiting_for_device`
   便于 CLI、报告与桌面端统一判断“扩展已启用但系统摄像头还未枚举完成”的状态
18. `VirtualCamera` 当前已调整为惰性加载视频依赖；在还未进入 `push_frame()` 推帧路径前，`status / install / enumerate_devices` 等安装侧能力不再强制依赖 `numpy` / `cv2`
19. 当前六个目标应用 `Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime` 的检查矩阵，已通过 `tools/macos_app_matrix_contract.py` 固定为统一集合，避免安装页、`smoke`、报告模板之间出现覆盖漂移
20. `python3 tools/macos_smoke.py` 与 `python3 tools/macos_smoke.py --run-install` 当前也会输出同一份 `verification_targets`
21. 这样桌面端、CLI 与 smoke 验证工具现在已经共享同一套目标应用验证清单，不需要分别维护多份指引
22. `tools/macos_smoke.py` 当前还会透传与 CLI/桌面端一致的 IPC 状态字段：
   - `ipc_probe_present`
   - `ipc_ready`
   - `ipc_environment_blocked`
   - `ipc_direct_open_errno`
   - `ipc_probe_path`
23. 如果要让 smoke 明确绑定某一份原生 probe 结果，而不是只依赖默认查找路径或环境变量，可显式传入：
   - `python3 tools/macos_smoke.py --framebus-roundtrip-json build/macos/framebus-roundtrip.json`
22. 桌面端当前还会在 `start()` 前先执行一次 macOS 安装状态复查；如果扩展已启用但系统设备仍未出现，会阻止启动推流 worker，并直接提示用户先完成系统枚举收敛
23. 主窗口当前也会直接使用这份状态门禁：
   - `pending_approval` / `timeout_waiting_for_device`：禁用 `Start`
   - `installed_visible`：重新启用 `Start`
   这样用户不需要先点一次失败的 `Start` 才知道当前还不能推流
24. 如果当前机器缺少 `numpy` / `cv2`，即使已经进入 `installed_visible`，桌面端也会继续保持 `Start` 禁用，并把禁用原因切换为“推流依赖缺失”
25. 当前这条依赖门禁在桌面端空闲轮询期间还会自动重新探测；如果用户补装了 `numpy / cv2`，且扩展状态已满足 `installed_visible`，`Start` 会自动恢复可用
26. 如果用户已经点过一次 `Start` 并触发了 worker 级依赖失败，当前也可以在补装依赖后点击 `Recheck` 主动恢复这条状态，不必强制重启应用
27. 直接使用 Python 兼容层的 macOS 调用方现在也会走同一条启动门禁：`VirtualCamera.start()` 会在真正打开 sink 前校验“已安装、已批准、设备已可见”，如果不满足会直接抛出明确异常，而不会进入“看起来 started=True、但系统其实没有可用摄像头”的假启动状态
28. 兼容层调用方当前还可直接读取：
   - `VirtualCamera.readiness()`
   - `VirtualCamera.inspect_installation()`
   这样 PySide6、CLI 或外部自动化可以在真正 `start()` 之前，直接拿到统一的 `status + devices + blocker_code + verification_targets` 快照
29. 当前 `tools/macos_smoke.py`、`tools/macos_install_session.py`、`tools/macos_validation_report.py` 与 `tools/macos_validation_session.py` 已支持同一组运行时覆盖参数：
   - `--host-bundle`
   - `--host-executable`
   - `--pkg-path`
   - `--installer-executable`
   - `--disable-auto-package`
   这意味着真机人工验收时可以把整条 install/session/report 流程绑定到指定 container app、指定 `pkg` 或指定原生命令产物，而不必依赖默认运行时发现逻辑
30. 这四个工具当前也都支持 `--name`，并会在真正执行 `status / install / list-devices / report` 前先写入 camera-name override 共享文件：
   - `python3 tools/macos_smoke.py --name "AKVC Demo" --run-install`
   - `python3 tools/macos_install_session.py --name "AKVC Demo" --output build/macos/install-session.json`
   - `python3 tools/macos_validation_report.py --name "AKVC Demo" --run-install --output build/macos/validation-report.json`
   - `python3 tools/macos_validation_session.py --name "AKVC Demo" --output-dir build/macos/session`
   这样即使当前没有先跑 demo，`device_prefix`、manual template 与最终 session summary 也会优先围绕同一运行时设备名收口
31. 常用的 `tools/make.py` 包装入口现在也已同步支持这条参数：
   - `python3 tools/make.py smoke --name "AKVC Demo" --run-install`
   - `python3 tools/make.py validation-report --name "AKVC Demo" --run-install --output build/macos/validation-report.json`
   - `python3 tools/make.py install-session --name "AKVC Demo" --output build/macos/install-session.json`
   - `python3 tools/make.py validation-session --name "AKVC Demo" --output-dir build/macos/session`
   因此从最外层 wrapper 进入时，也不会再丢掉运行时设备名
32. `tools/make.py smoke` 当前也已同步透传底层 `macos_smoke.py` 的运行时覆盖参数：
   - `--status-tool / --install-tool / --list-devices-tool / --uninstall-tool`
   - `--sync-ipc-tool`
   - `--host-bundle / --host-executable`
   - `--pkg-path / --installer-executable / --disable-auto-package`
   这样从顶层 smoke 入口也可以直接绑定指定 container app、指定 pkg 和指定原生命令产物；如果还在过渡期，也兼容显式指定 legacy host，不必再退回脚本级入口
33. 当前 `framebus-roundtrip` 诊断路径也已收紧惰性依赖边界：即使本机还没有 `numpy`，也可以先运行 `python3 tools/macos_framebus_roundtrip.py` 来判断是“共享内存阶段被环境拦住”还是“后续 consumer 读帧失败”
34. 如果当前要把安装状态与 IPC 状态放到同一份验收报告里，`python3 tools/macos_validation_report.py` 现在还支持额外读入 `--framebus-roundtrip-json`，用于显示 Python producer 与原生 consumer 的跨语言互通摘要
35. 已新增 `python3 tools/macos_validation_report.py`，可把：
   - 当前 `status`
   - 可选 `install` 收敛结果
   - 可选 `list-devices-binary-check` 设备枚举自检结果
   - 可选 benchmark JSON
   - 可选 PySide6 demo JSON
   - 可选人工应用验证结果
   汇总为单一 JSON 报告工件
   - benchmark JSON 当前既可以是单场景结果，也可以是 `--matrix` 输出
   - 如果同时传入 `--list-devices-binary-check-json`，总报告 `summary` 还会继续提升：
     - `list_devices_binary_check_present`
     - `list_devices_binary_check_passed`
     - `list_devices_binary_check_device_prefix`
     - `list_devices_binary_check_filtered_device_count`
     - `list_devices_binary_check_total_device_count`
     - `list_devices_binary_check_override_no_match_ok`
     这样同一份 `validation-report.json` 就能同时证明：
     - system extension 当前状态如何
     - 原生 `list-devices` 二进制是否真的返回了结构化 JSON
     - prefix 过滤后的虚拟摄像头结果是否仍是 `all_devices` 子集
33. 同一个脚本当前还支持 `--write-manual-template PATH`，可先按当前状态生成一份六个目标应用的人工验收模板，再填充后作为 `--manual-results` 回灌
34. 仓库当前还提供示例文件 [manual_validation_results.example.json](/Users/admir/workspace/virtual-camera/docs/macos/manual_validation_results.example.json:1)，可直接复制后按机器实际情况填写
35. 该示例文件当前已经与 `validation_report` 实际生成模板对齐，除 `validated / result / notes` 外，还会保留：
   - `checks`
   - `name`
   - `ready`
   - `status`
   - `steps`
   这样在回看真机验收记录时，可以同时知道：
   - 当时处于哪个安装阶段
   - 应该从应用里的哪个入口验证
   - 看到哪些现象才算这一步真的通过
36. `validation-report.json.summary` 当前也会继续输出更细粒度的目标应用摘要：
   - `passed_app_ids`
   - `failed_app_ids`
   - `pending_app_ids`
   - `skipped_app_ids`
   - `unreviewed_app_ids`
   - `manual_validation_ready`
   - `manual_validation_complete`
   - `manual_validation_all_passed`
   这样一份报告里就能直接看出“哪些应用已通过、哪些失败、哪些还没测”，不必再手工遍历整份 `verification_targets`
   其中：
   - `manual_validation_ready` 表示 `validation-report.json` 这一层观察到的“安装后启动状态、设备枚举、IPC 阻塞和 sync-ipc 状态”是否允许开始填写目标应用人工 review 结果
   - `manual_validation_complete` 表示六个目标应用是否都已经被人工 review 覆盖
   - `manual_validation_all_passed` 表示六个目标应用是否都已经人工验收通过
32. `session-manifest.json.summary` 当前也已开始继续提升这组结果：
   - `validation_validated_apps / validation_passed_apps / validation_failed_apps / validation_pending_apps / validation_skipped_apps`
   - `validation_passed_app_ids / validation_failed_app_ids / validation_pending_app_ids / validation_skipped_app_ids / validation_unreviewed_app_ids`
   - `validation_manual_validation_ready / validation_manual_validation_complete / validation_manual_validation_all_passed`
   - `manual_app_validation_ready / manual_app_validation_failed_criteria / manual_app_validation_unknown_criteria / manual_app_validation_blockers`
   - `validation_app_matrix`
   其中 `validation_app_matrix` 会按 app id 保留 `name / reviewed / validated / result / notes / ready / status`，便于主 manifest 直接驱动 Dashboard、CI 注释或人工复盘
   这里要特别区分两层语义：
   - `validation_manual_validation_*` 是 `validation-report.json` 汇总出来的“目标应用人工 review 结果”
   - `manual_app_validation_*` 是 `session-acceptance.json` 汇总出来的“现在是否已经具备开始人工验收的系统前置条件”
   也就是说：
   - `validation_manual_validation_ready=true` 更偏向“模板/流程层面可以开始填人工结果”
   - `manual_app_validation_ready=true` 才表示 release、签名、公证工具链、自动安装、系统摄像头可见性、runtime 资产与 artifact replay 这些系统级前提已经收敛到可开始真机验收
   当前 CLI/桌面端也会直接消费这组 `manual_app_validation_*` 字段：
   - reader-facing 文案优先展示中文标签，例如“系统已枚举到虚拟摄像头”“公证工具链已就绪”
   - CLI `--json` 仍保留原始 gate id，字段名为 `manual_app_validation_failed_criteria_ids / manual_app_validation_unknown_criteria_ids / manual_app_validation_blocker_ids`
   - 因此如果要做自动化对比或 contract 回放，优先读取 `*_ids`；如果只是人工查看安装状态，优先看中文标签数组
   - `session-summary.md` 现在也会沿用同一套中文标签，因此 CI 工件页、CLI、桌面端与安装复盘文档的说法已经统一
33. 当 `python3 tools/macos_validation_report.py --run-install ...` 触发自动安装时，`validation-report.json.install` 当前也会继续保留统一安装快照语义，包括：
   - `status_devices / status_all_devices / device_prefix`
   - `enumerated_devices`
   - `supported_formats / supported_frame_rates`
   - `start_ready / start_blocker_code / start_message / start_steps`
   - `ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno`
   这样后续 `validation-session`、CI 归档和人工复盘都不再只能看到“安装命令是否成功”，而是能继续判断“安装后是否已真正达到可开始推流的状态”
34. 桌面端安装状态当前也会继续保留同一组设备可见性细节：
   - `devices`
   - `all_devices`
   - `device_prefix`
   - `message`
   因此如果 UI 停在 `timeout_waiting_for_device`，不需要先打开 CLI；可直接从桌面端提示判断是“系统尚未枚举出 AK Virtual Camera”，还是状态链路本身缺少观测信息
34. 已新增 `python3 tools/macos_validation_session.py --output-dir ...`，可一次性生成：
   - `preflight.json`
   - `release-diagnostics.json`
   - `demo-report.json`
   - `benchmark.json` 或 `benchmark-matrix.json`
   - `manual-results.template.json`
   - `validation-report.json`
35. `validation-session` 当前会默认先运行 `preflight`，再把 `preflight.json` 通过 `--preflight-json` 注入最终 `validation-report.json`，这样一份报告里可以同时看到：
    - 当前工具链是否可生成工程/编译/打包
    - 当前机器是否已配置签名与公证凭据
    - 当前发布产物的架构、签名与 Gatekeeper 评估状态
    - 当前 `pkg` 是否满足 `/Applications` 安装位置、预期包标识与扩展 payload 覆盖
    - Host App 是否真的内嵌了 `Camera Extension`，以及 Host/Extension 的 bundle id / 最低系统版本是否符合正式分发预期
    - 当前系统扩展状态与设备可见性
    - benchmark / PySide6 demo / 人工应用验证结果
36. 如果只想收集安装状态与工具链，而不跑 demo / benchmark，可直接运行：
   - `python3 tools/make.py validation-session --output-dir build/macos/session --skip-demo --skip-benchmark`
   - 如果还想把 `akvc-macos-list-devices` 的 prefix 过滤语义一起并入会话工件，可继续追加 `--run-list-devices-binary-check --list-devices-tool build/macos/Build/Products/Release/akvc-macos-list-devices`
37. 如果当前场景不需要工具链快照，也可以显式跳过：
   - `python3 tools/make.py validation-session --output-dir build/macos/session --skip-preflight`
38. 如果已经生成过一轮 `build/macos/session` 工件，并且现在只是把六个目标应用的人工验收结果回灌进总报告，可直接复用已有工件而不重跑 demo / benchmark / preflight：
   - `python3 tools/make.py validation-session --output-dir build/macos/session --manual-results build/macos/session/manual-results.actual.json --reuse-existing-artifacts --skip-preflight --skip-release-diagnostics --skip-demo --skip-benchmark`
   - 这条命令会继续重算 `validation-report.json`、`session-acceptance.json`、`session-acceptance-contract.json` 与 `session-summary.md`
   - 适合“先跑一次会话生成模板 -> 去 Zoom / Teams / Meet / OBS / QuickTime / FaceTime 逐项人工验证 -> 回来只刷新验收结论”的真实流程
39. 填写 `manual-results.actual.json` 时，如果某个应用要标记为 `result=pass`，必须同时给出：
   - `evidence.device_listed=true`：该应用自己的摄像头列表里能看到 `AK Virtual Camera`
   - `evidence.device_selected=true`：该应用已切换到 `AK Virtual Camera`
   - `evidence.preview_visible=true`：该应用预览区或录制窗口已出现实时画面
   - `evidence.screenshot`：建议填写截图相对路径，便于复盘
   缺少这些 evidence 时，`target_apps_all_passed` 会失败，即使六个应用的 `result` 都写成 `pass`
37. `installer/macos/uninstall.sh` 当前会优先尝试以下卸载工具路径，再执行 `.app` 删除：
   - `build/macos/Build/Products/Release/akvc-macos-uninstall`
   - `build/macos/bin/akvc-macos-uninstall`
   - `build/bin/akvc-macos-uninstall`
   这样本机构建目录、旧开发目录和 CI 产物目录都能兼容
31. 如果要验证“本地视频文件 -> PySide6 -> Virtual Camera”链路，可直接运行：
    - `python3 tools/macos_validation_session.py --output-dir build/macos/session --mode video-file --video-path demo.mp4`
32. 如果要验证“异步最新帧提交 -> PySide6 -> Virtual Camera”链路，可直接运行：
    - `python3 tools/macos_validation_session.py --output-dir build/macos/session --mode latest-provider`
33. 当前 `DefaultMacInstallerService` 已增加“先装包、再激活扩展”的自动链路：
   - 当 `akvc-macos-status` 仍显示 `not_installed`
   - 且当前未发现可用 Host App bundle / executable
   - 且可发现 `VirtualCamera.pkg`
   会先调用 `/usr/sbin/installer -pkg ... -target /`，成功后再继续 `akvc-macos-install`
34. 如需显式指定分发包路径，可设置环境变量 `AKVC_MACOS_PKG=/path/to/VirtualCamera.pkg`
35. 如需显式指定已安装 container app，可设置：
   - `AKVC_HOST_APP_BUNDLE=/Applications/<your-container-app>.app`
   - `AKVC_HOST_EXECUTABLE=/Applications/<your-container-app>.app/Contents/MacOS/<your-executable>`
36. 当前这条自动安装链路仍遵循 macOS 系统权限模型；如果 `installer` 返回鉴权或授权失败，Python 层会以 `package_install_failed` 暴露原始错误，便于 CLI / Desktop 继续引导用户完成安装
37. 如果要把这些 macOS 安装资产一并带入 Python 包或外部 PySide6 分发目录，可执行：
   - `python3 tools/make.py sync-macos-runtime --require-pkg`
   或在打包时直接：
   - `python3 tools/make.py package --sync-runtime`
38. 该同步步骤会把 `akvc-macos-status / install / uninstall / list-devices` 与 `VirtualCamera.pkg` 复制到 `camera-core/src/akvc/_runtime/macos`，供 `akvc.runtime` 在 wheel / 打包目录中继续发现这些资产
    当前也已把 `akvc-macos-sync-ipc` 纳入这份 runtime 资产集合，因此分发态不再只有“安装/状态”工具，而是也具备显式 IPC 配置同步命令
39. `validation-report.json` 当前也会输出一份 `runtime_assets` 快照，说明：
   - Python 侧当前解析到的是 build 目录资产、显式环境变量还是包内 `_runtime/macos`
   - 包内 `_runtime/macos` 是否真的具备完整的 `tool + pkg` 分发资产
   这有助于排查“pkg 已生成但 Python 分发目录仍无法自动安装”的问题
    其中当前也会单独记录 `sync_ipc_tool_resolved`，便于判断 CLI / SDK 的显式 `sync-ipc` 路径究竟来自开发构建还是包内 runtime
40. 这份 `runtime_assets` 快照当前还会继续保留本次验收显式绑定的 provenance：
   - `host_bundle`
   - `host_executable`
   - `extension_bundle`
   - `package_install_command`
   - `auto_install_package`
   这些字段会先进入 `validation-report.json.runtime_assets.provenance`，再提升到 `session-manifest.json.summary`，最后出现在 `session-summary.md` 的 `Runtime Asset Provenance` 小节里，便于人工验收时直接确认本次会话到底绑定的是哪一套 Host App / Extension / PKG / runtime command tools
41. 同一份摘要当前还会继续导出 `Runtime Topology` 小节：
   - `runtime_topology_kind`
   - `runtime_frame_path`
   - `runtime_host_role`
   - `runtime_host_in_frame_hot_path`
   - `runtime_dedicated_host_daemon_required`
   - `runtime_data_plane / runtime_control_plane`
   这样人工验收时不必再反推架构细节，就能直接确认当前方案是“Host App 仅做容器/激活/命令桥，不参与帧热路径”，并能看见最终使用的是哪条数据面与控制面。
42. 当前 `validation-report.json.summary` 还会继续对比 `runtime provenance` 与 `release-diagnostics` 的产品集身份：
   - 会分别比较 `host bundle / extension bundle / sync-ipc tool / pkg`
   - 会输出 `runtime_release_*_identity_consistent` 与聚合后的 `runtime_release_product_identity_consistent`
   - `session-summary.md` 也会直接显示这组结果，避免出现“安装/验收实际使用的是一套工件，但 release diagnostics 检查的是另一套产物”却没有被及时发现的情况
43. `tools/macos_smoke.py` 当前还支持 `--output PATH`，可写出结构化 `smoke-report.json`，其中包含：
   - 初始 `status`
   - 可选 `install`
   - `status_after_install`
   - 可选 `uninstall`
   - `status_after_uninstall`
   适合把一次安装/卸载往返验证作为独立工件归档
44. `macos_validation_session.py` 当前在启用 `--run-install` 或 `--run-uninstall` 时，也会自动生成 `smoke-report.json`，并把它继续注入最终 `validation-report.json`
45. 另外还新增了 `tools/macos_install_session.py`，用于验证更高层的自动安装链路：
   - `VirtualCamera.pkg`
   - Host App bundle 定位
   - `DefaultMacInstallerService.install_extension_result()`
   这条链路更接近“Python 直接调用自动安装”的真实行为
43. 当前 `tools/macos_release_diagnostics.py` 也已开始把 `akvc-macos-sync-ipc` 纳入结构化发布诊断，而 `validation-session` 会继续把：
    - `release_sync_ipc_tool_exists`
    - `release_sync_ipc_tool_signed`
    - `release_sync_ipc_tool_universal2_ready`
    这些字段写入 `session-manifest.json.summary`，便于在安装会话复盘里继续判断“显式 IPC 控制面产物是否完整可分发”
43. `tools/macos_install_session.py` 当前也已支持 `--framebus-roundtrip-json`，并会把与 CLI / smoke 一致的 `ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno / ipc_probe_path` 一并写入 `install-session-report.json`
   同一份报告现在还会继续保留 `start_ready / start_blocker_code / start_message / start_steps`，可直接判断“自动安装链路成功后，为什么仍不能开始推流”
44. `tools/macos_install_session.py` 当前还会在 `post_status.shared_memory_name` 可用时，主动执行一次显式 `sync-ipc`：
   - 结果会写入 `install-session-report.json.sync_ipc`
   - 关键字段包括 `supported / success / phase / shared_memory_name / ipc_transport / returncode`
   这样安装会话现在能同时回答两件事：
   - Camera Extension 是否装好、设备是否出现
   - 显式 IPC 配置同步命令是否在这次真实安装会话里成功执行
45. `smoke-report.json` 与 `install-session-report.json` 当前也都会继续保留 `supported_formats / supported_frame_rates`，因此 `720p / 1080p / 4K` 与 `30 / 60fps` 的能力声明不再只停留在原生状态命令，而是会直接进入上层验收工件
46. `macos_validation_session.py` 当前也支持 `--run-install-session`，会生成 `install-session-report.json`，适合沉淀：
   - 自动装包是否成功
   - 自动激活扩展是否成功
   - 可选卸载后状态是否回落
47. `macos_validation_session.py` 当前还会在 `session-manifest.json.summary` 中汇总：
   - `smoke_ipc_environment_blocked`
   - `install_session_ipc_environment_blocked`
   - `framebus_roundtrip_environment_blocked`
   - `release_pkg_payload_appledouble_clean`
   - `smoke_start_blocker_code / install_session_start_blocker_code / effective_start_blocker_code`
   这样不必先打开所有子工件，就能快速判断一次会话是否已经暴露出共享内存 IPC 阻塞
   也能直接确认当前这次会话对应的 release pkg payload 是否已经清除 `._*` AppleDouble 元数据
   当前也会继续提升 `install_session_sync_ipc_*`，用于区分“自动安装链路成功”与“显式 sync-ipc 已真实跑通”
   现在 `session-summary.md` 里也会额外显示 `Control-plane prerequisites satisfied`：
   只有发布态 `sync-ipc` 工具存在、已签名、满足 universal2，且本次 install-session 里的 `install_session_sync_ipc_present/supported/success=true` 同时成立时，这项才会显示 `yes`
47. 同一份 `session-manifest.json.summary` 现在也会继续保留能力摘要：
   - `validation_supported_formats / validation_supported_frame_rates`
   - `smoke_supported_formats / smoke_supported_frame_rates`
   - `install_session_supported_formats / install_session_supported_frame_rates`
   - `effective_supported_formats / effective_supported_frame_rates`
   这样在安装验收阶段就能直接看到当前会话最终收敛到的是 `720p / 1080p / 4K` 与 `30 / 60fps` 哪组能力，而不必手工翻三份子报告
48. GitHub Actions 与 Jenkins 现在也会把 `build/macos/session/session-manifest.json` 作为工件归档，因此 CI 页面上可以直接读取这份能力摘要与 blocker 摘要，而不必先下载并拼接多份子报告
49. `macos_validation_session.py` 现在还会在会话末尾自动生成 `session-manifest-check.json`，并把：
    - `artifact_check_present`
    - `artifact_check_passed`
    继续写回 `session-manifest.json.summary`
    这样哪怕只打开主 manifest，也能先判断“这次会话自己的真实工件回放检查是否通过”
50. 如果当前想确认“CI 归档出来的 session manifest 是否真的是一份自洽工件”，可直接运行：
    - `python3 tools/make.py validation-session-artifact-check --manifest build/macos/session/session-manifest.json --require-existing-artifacts`
    这一步会继续校验：
    - `artifacts / steps / summary` 结构
    - `manual-results.template.json` 是否仍完整覆盖六个目标应用，并且每个应用都保留可执行的 `checks / steps`
    - `effective_start_*` 与 `effective_supported_*` 的值域
    - 本次会话声明已生成的子工件文件是否真实存在
51. 当前还已新增 `python3 tools/make.py validation-session-acceptance --manifest build/macos/session/session-manifest.json --output build/macos/session/session-acceptance.json`，用于把：
    - `session-manifest.json`
    - `validation-report.json`
    - `preflight.json`
    - `benchmark.json`
    - `release-diagnostics.json`
    收敛成一份面向最终验收标准的 acceptance 摘要
52. `macos_validation_session.py` 当前也会在 artifact check 之后自动生成 `session-acceptance.json`，并把以下字段继续写回 `session-manifest.json.summary`：
    - `acceptance_present`
    - `acceptance_ready`
    - `acceptance_failed_criteria`
    - `acceptance_unknown_criteria`
    这样安装验收阶段可以先直接看主 manifest，快速判断当前是卡在签名、公证、能力矩阵、自动安装还是目标应用识别
53. `session-manifest.json.summary` 当前也会继续透传 `validation-report.json` 的目标应用细粒度摘要：
    - `validation_passed_app_ids`
    - `validation_failed_app_ids`
    - `validation_pending_app_ids`
    - `validation_skipped_app_ids`
    - `validation_unreviewed_app_ids`
    这样在 CI 工件页只打开主 manifest，也能先看出具体是 `zoom`、`teams` 还是 `google_meet` 没通过或尚未验证
54. 当前 CI/Jenkins 还会额外生成 `build/macos/session/session-summary.md`，用于把：
    - `artifact_check_passed / acceptance_ready`
    - `validation_install_present / validation_install_phase / validation_install_start_blocker_code`
    - `validation_install_supported_formats / validation_install_supported_frame_rates`
    - `validation_install_ipc_probe_present / validation_install_ipc_ready / validation_install_ipc_environment_blocked`
    - `install_session_present / install_session_success / install_session_start_blocker_code`
    - `install_session_ipc_probe_present / install_session_ipc_ready / install_session_ipc_environment_blocked`
    - `validation_demo_present / validation_demo_mode / validation_demo_mode_supported`
    - `validation_demo_frame_source_kind`
    - `validation_demo_width / validation_demo_height / validation_demo_fps / validation_demo_duration`
    - `validation_demo_camera_name / validation_demo_video_path`
    - `effective_start_blocker_code`
    - `effective_supported_formats / effective_supported_frame_rates`
    - `validation_*_app_ids`
    - `validation_app_matrix` 的逐应用细粒度状态
    - `macos_13_plus_declared / universal2_ready / release_packaging_ready / pyside6_path_exercised / runtime_assets_packaged`
    - `target_apps_all_passed / system_camera_device_visible / auto_install_ready / signing_evidence_ready / notarization_tooling_ready / benchmark_matrix_complete / benchmark_fps_targets_met / benchmark_1080p60_cpu_target_met`
    汇总成一页可直接阅读的 Markdown 摘要
    同时 `session-manifest.json.summary` 当前也会直接保留：
    - `acceptance_passed_count / acceptance_failed_count / acceptance_unknown_count`
    - 上述关键 acceptance gate 的逐项 `pass / fail / unknown` 状态
    这样外部自动化或自定义 Dashboard 如只消费主 manifest，也不必再额外展开 `session-acceptance.json`
    另外这份 `session-summary.md` 当前对目标应用分组已支持“矩阵优先”的自动回退：
    - 如果主 manifest 已显式给出 `validation_*_app_ids` 与 `validation_*_apps`，就直接展示
    - 如果这些汇总字段暂时缺失，但 `validation_app_matrix` 仍存在，则会自动从 `result / reviewed` 推导出 `passed / failed / pending / skipped / unreviewed` 与对应计数
    这样安装验收页、CI 工件页和人工复盘时可以稳定看到同一套目标应用结论
    现在 `session-summary.md` 的逐应用明细里也会继续带出：
    - `steps / checks` 数量
    - 首条 `first_step / first_check`
    因此即使只看摘要页，也能直接知道该去哪个应用入口验证、以及第一条应该观察的通过现象
    同时 PySide6 直推链路现在也会在这份摘要里保留具体 demo mode、`frame_source_kind` 和请求的尺寸/帧率，因此复盘时可以直接区分“这次跑的是 latest-provider(WebRTC/AI Avatar)”还是“video-file(本地视频转推)”，以及 `widget_grab / screen_grab / callable_provider` 等来源语义。
    `validation-session-acceptance` 当前还会进一步校验 `demo_mode <-> frame_source_kind` 是否匹配，避免出现“demo 的确跑过，但来源语义已经漂移”的误验收。
    现在摘要页还会额外提供 `Device Name Cohesion` 小节，直接对照：
    - `effective_device_prefix`
    - `validation_demo_camera_name`
    - validation/install/list-devices 三条设备名前缀
    这样如果人工验收看到的是 `Demo Camera`，而某条链路还停留在默认名，可以第一时间从摘要页判断出是“设备未枚举”还是“名字链路漂移”。
    此外如果这次跑的是 `benchmark --matrix`，主 manifest 摘要层还会继续保留 `validation_benchmark_matrix_profiles`，方便直接读取每档 `720p/1080p/4K` 与 `30/60fps` 场景的 `actual_fps / cpu_percent / avg_latency_ms`。
55. 如果只想单独验证自动安装链路，可直接运行：
    - `python3 tools/make.py install-session --output build/macos/install-session.json`
    - `python3 tools/make.py install-session --run-uninstall --output build/macos/install-session.json`
    这条路径会优先覆盖：
    - `VirtualCamera.pkg`
    - Host App bundle 定位
    - `DefaultMacInstallerService.install_extension_result()`
    - `post_status.ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_direct_open_errno`
    当前 `validation-session-acceptance` 里的 `auto_install_ready` 也会显式使用这组字段，避免把“安装命令成功但 IPC 仍被环境阻塞”的会话误判成自动安装已就绪

## 4. 升级流程

升级要求：

1. 幂等
2. 支持覆盖安装
3. 支持旧版本扩展替换
4. 保留必要的用户配置

## 5. 卸载流程

卸载要求：

1. 停止 Camera Extension
2. 卸载系统扩展
3. 删除安装文件
4. 删除无效缓存
5. 保留或清理用户数据需明确策略

当前建议入口：

1. Python / SDK：
   - `VirtualCamera.uninstall_extension_result()`
   - `VirtualCamera.uninstall_extension()`
2. CLI：
   - `akvc uninstall`
   - `akvc uninstall --json`
3. Shell：
   - `installer/macos/uninstall.sh`

当前实现语义：

1. 会先停止 Python 侧推流
2. 调用 `akvc-macos-uninstall` 触发 host deactivation
3. `akvc-macos-uninstall` 原生命令当前也会像安装命令一样，短轮询真实 system extension 状态，而不是只返回固定 `not_installed`
4. Python / SDK 再继续轮询 `status + list-devices`
5. 只有当状态回落为 `not_installed` 且系统设备列表不再可见时，才判定为 `uninstalled`

当前 `smoke-report.json`、`install-session.json`、`validation-report.json` 里的 `uninstall` 节点也已经升级为结构化结果，建议重点关注：

1. `success`
2. `phase`
3. `state`
4. `enumerated_devices`
5. `last_error`
6. `returncode`

## 6. 安装状态判断

至少需要区分：

1. 未安装
2. 已安装但未批准
3. 已安装并已启用
4. 升级待重启
5. 卸载中

## 7. 用户体验要求

安装文案应明确：

1. 为什么需要系统扩展
2. 如何批准扩展
3. 批准失败时如何排查

## 8. 当前结论

安装能力必须作为 SDK / Host 层正式能力设计，而不能仅依赖 README 手工操作。

补充说明：

- 最新 `build/macos/session/session-summary.md` 已会直接显示：
  - `Effective devices / Effective all devices / Effective device prefix`
  - `Validation Status` 里的 `Devices / All devices / Device prefix`
  - `Installation Snapshot` 里的 `Status devices / Status all devices / Device prefix`
  - `Install Session` 里的 `Session devices / Session all devices / Session device prefix`
- 这意味着人工验收时即使不展开原始 JSON，也能直接从摘要页判断：
  - 扩展是否已启用
  - 当前系统视频设备列表里是否真的出现了虚拟摄像头
  - 当 `devices` 为空时，系统里到底只看到了哪些真实摄像头
  - `Manual App Validation Readiness` 小节里的 `Ready / Failed prerequisites / Unknown prerequisites / Combined blockers` 到底卡在什么前置条件
