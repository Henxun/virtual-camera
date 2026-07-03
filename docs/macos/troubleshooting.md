# macOS 故障排查

## 1. 常见问题分类

1. 安装失败
2. 扩展未批准
3. 设备不可见
4. 设备可见但无画面
5. 帧率异常
6. CPU 过高

## 2. 安装相关

### 现象

- `pkg` 安装成功，但扩展未启用
- `open -n -a /Applications/<your-container-app>.app --args --activate` 直接被 `killed`
- `build/macos/Build/Products/Release/akvc-macos-install` 或 runtime 中的 `akvc-macos-install` 直接被 `killed`
- `spctl -a -vvv /Applications/<your-container-app>.app` 返回 `rejected`
- `spctl -a -vvv build/macos/Build/Products/Release/akvc-macos-install` 返回 `rejected`
- `syspolicy_check distribution /Applications/<your-container-app>.app` 提示 `Notary Ticket Missing`

### 排查方向

1. 确认 App 位于 `/Applications`
2. 确认用户已批准系统扩展
3. 确认签名与公证有效

### 典型根因：已开发签名，但缺少公证票据

如果宿主应用与嵌入的 `systemextension` 已经不是 `adhoc`，`codesign --verify --deep --strict` 也通过，但应用一启动就被系统杀掉，优先把问题归类为“启动策略/Gatekeeper 阻塞”，而不是“entitlement 缺失”：

1. 先运行 `akvc status --json`
2. 如果输出里出现：
   - `host_gatekeeper_allowed=false`
   - `host_notarization_missing=true`
   - `start_blocker_code=host_notarization_missing`
   说明当前更接近“宿主签名基本完整，但分发证书链或公证票据缺失”
3. 如果输出里出现：
   - `install_command_gatekeeper_allowed=false`
   - `install_command_notarization_missing=true`
   - `start_blocker_code=install_command_notarization_missing`
   说明当前更接近“Python/CLI 控制面使用的 `akvc-macos-install` 已签名，但仍缺少 Developer ID 分发链路或公证票据”
4. 如果输出里出现：
   - `system_extension_registered=false`
   说明当前 `com.sidus.amaran-desktop.cameraextension` 甚至还没有进入 `systemextensionsctl list` 的系统注册表，问题比“设备暂未枚举”更靠前
5. 继续手动确认：
   - `codesign -dvvv /Applications/<your-container-app>.app`
   - `spctl -a -vvv /Applications/<your-container-app>.app`
   - `syspolicy_check distribution /Applications/<your-container-app>.app`
   - `codesign -dvvv build/macos/Build/Products/Release/akvc-macos-install`
   - `spctl -a -vvv build/macos/Build/Products/Release/akvc-macos-install`
   - `syspolicy_check distribution build/macos/Build/Products/Release/akvc-macos-install`
6. 如果 `spctl` 显示 `origin=Apple Development...` 或 `source=Unnotarized Developer ID`，且 `syspolicy_check` 显示 `Notary Ticket Missing`，说明本机当前只能做开发签名验证，还不能满足标准分发启动策略
7. 这时应补齐：
   - `Developer ID Application`
   - `Developer ID Installer`
   - `NOTARY_PROFILE`
   - `notarize + staple`
8. 如果当前只是开发机联调，且你明确接受“先不走正式分发策略”，可以临时改走开发态绕行：
   - `systemextensionsctl developer on`
   - `xattr -dr com.apple.quarantine /Applications/<your-container-app>.app`
   - Finder 里对目标 container app 执行一次“右键 -> 打开”
   - 再重新跑 `python3 tools/make.py smoke --run-install --host-bundle /Applications/<your-container-app>.app --disable-auto-package`
9. 如果 `smoke` 仍然显示：
   - `install.phase=install_command_failed`
   - `install.returncode=-9`
   说明当前不是 Python 逻辑报错，而是 `akvc-macos-install` 或它试图启动的宿主 app 被启动策略直接杀掉；此时不要继续纠结 `send()` / PySide6 / IPC，优先回到 `spctl`、`syspolicy_check` 和公证票据

截至 2026-06-30，本仓库在真实签名后已经再次验证过下面这组现象是正常且可复现的：

1. `codesign --verify --deep --strict build/macos/Build/Products/Release/<your-container-app>.app`
   - 通过
2. `pkgutil --check-signature build/macos/VirtualCamera.pkg`
   - 显示 `signed by a developer certificate issued by Apple for distribution`
3. 但在尚未 `notarize + staple` 前：
   - `spctl -a -vvv /Applications/<your-container-app>.app`
   - `spctl -a -vvv build/macos/Build/Products/Release/akvc-macos-install`
   仍会显示 `source=Unnotarized Developer ID`
4. 这正是目标 container app 或 `akvc-macos-install` 被直接 `killed` 的最常见原因
5. 如果系统日志里同时出现：
   - `amfid: ... No matching profile found`
   - `Code has restricted entitlements, but the validation of its code signature failed`
   - `ASP: Security policy would not allow process`
   当前项目里应优先把它理解成“宿主仍缺 notarize/staple”，而不是先回头怀疑 Developer ID 证书是否没装好
6. 截至 2026-06-30 的真实验证里，上述日志组合与下面这组结果会同时出现：
   - `codesign --verify --deep --strict /Applications/<your-container-app>.app` 通过
   - `spctl -a -vvv /Applications/<your-container-app>.app` 显示 `source=Unnotarized Developer ID`
   - `syspolicy_check distribution /Applications/<your-container-app>.app` 显示 `Notary Ticket Missing`
7. 需要抓取同类日志时，可直接执行：
   - `/usr/bin/log show --last 10m --predicate 'process == "akvc-host" OR eventMessage CONTAINS[c] "akvc-host" OR eventMessage CONTAINS[c] "cameraextension" OR eventMessage CONTAINS[c] "<your-container-app>"'`
8. 如果日志、`spctl` 与 `syspolicy_check` 同时指向公证缺失，就先不要继续纠结：
   - `OSSystemExtensionRequest`
   - `Zoom/Teams/Meet`
   - `PySide6 send()`
   - `IPC / shared memory`
   因为宿主进程在进入这些路径之前就已经被启动策略拦下了

当前代码里已经把这类状态提升为独立 blocker；后续如果再次出现 “install failed / app killed”，优先看 `host_*`、`install_command_*`、`system_extension_*` 与 `start_blocker_code`，不要只看 `last_error`。

截至 2026-06-30，还额外确认了两条实现/验收层细节：

1. `akvc-macos-install` / `akvc-macos-uninstall` 现在已经不是“只能依赖 host 拉起”的单一路径
   - 原生命令会先尝试拉起 host
   - 如果 host 路径没有让状态收敛，会继续在当前进程里直接提交 `OSSystemExtensionRequest`
   - 因此如果命令本身仍被系统立刻 `killed`，问题更接近 Gatekeeper / notarization / launch policy，而不是“fallback 没做”
2. 在仓库里直接跑 `build/macos/Build/Products/Release/akvc-macos-status`
   - 默认更可能绑定到 build tree 下的 legacy `akvc-host.app` 或当前 container app 构建产物
   - 这和 `/Applications/<your-container-app>.app` 的真实安装态不是一回事
   - 如果你要显式检查已安装宿主，请带上：
     `AKVC_HOST_APP_BUNDLE=/Applications/<your-container-app>.app`

### 典型根因：entitlement 组合或旧安装包导致 `invalid entitlements blob`

如果 `/Applications/<your-container-app>.app` 或 build tree 里的新产物仍然出现：

- `AKVC host request ... failed: Missing entitlement com.apple.developer.system-extension.install`
- `codesign -d --entitlements :- /Applications/<your-container-app>.app` 输出
  `warning: binary contains an invalid entitlements blob. The OS will ignore these entitlements.`

优先按下面两类原因排查：

1. 旧安装版本残留
   - 先删除 `/Applications/<your-container-app>.app`
   - 重新从当前工作区产物签名、打包并安装新的 `VirtualCamera.pkg`
2. 当前签名使用了不适合这条分发链的 entitlement 组合
   - 当前 Host 应只保留 `com.apple.developer.system-extension.install`
   - 当前 Extension 应使用最小 entitlement，不再附加 `app-sandbox / application-groups`

然后再执行：
   - `codesign -d --entitlements :- /Applications/<your-container-app>.app`
   - `codesign -dvvv /Applications/<your-container-app>.app`
   - `open -n -a /Applications/<your-container-app>.app --args --activate`
3. 新版状态诊断现在会把这类问题直接收敛为：
   - `host_entitlements_valid=false`
   - `host_entitlements_summary=...invalid entitlements blob...`
   - `start_blocker_code=host_entitlements_invalid`

截至 2026-06-30，本仓库已经在真实 Developer ID 签名实验里确认：

1. Host 只保留 `com.apple.developer.system-extension.install` 时
   - `invalid entitlements blob` warning 会消失
2. Camera Extension 使用空 entitlement 时
   - `invalid entitlements blob` warning 也会消失

所以如果你又看到这条 warning，优先检查当前安装包是否仍混入了旧的
`app-sandbox / application-groups` entitlement 组合。

## 3. 设备不可见

### 现象

- Zoom / OBS / QuickTime 中没有虚拟摄像头
- `VirtualCamera(direct_only=True).start(...)` 直接报：
  `macOS direct sender unavailable: camera device not found ...`
- `python3 tools/macos_direct_sender_object_demo.py --inspect-only ...` 输出：
  - `environment_device_enumeration_empty=true`
  - `camera_access_status=denied` / `not_determined`

### 排查方向

1. 确认扩展已激活
2. 确认 Provider / Device / Stream 初始化完成
3. 确认应用缓存未阻止设备刷新

### Python 直推专项排查

如果当前目标是“Python 直接创建对象并推帧，不走 helper 热路径”，优先使用 pure direct sender 诊断，而不是先跑整条安装状态链：

1. 先做只读探测：
   - `python3 tools/macos_direct_sender_object_demo.py --inspect-only --direct-sender-library build/macos/Build/Products/Release/libakvc-macos-direct-sender.dylib`
2. 如果怀疑当前 Python 进程还没拿到摄像头权限，直接对当前进程发起权限请求并重取 snapshot：
   - `python3 tools/macos_direct_sender_object_demo.py --inspect-only --request-camera-access --direct-sender-library build/macos/Build/Products/Release/libakvc-macos-direct-sender.dylib`
   - 或在应用里先调用 `MacDirectCameraSender.request_camera_access()`
3. 重点看输出里的：
   - `direct_sender_device_snapshot.camera_access_status`
   - `direct_sender_device_snapshot.environment_device_enumeration_empty`
   - `direct_sender_device_snapshot.avfoundation_devices`
   - `direct_sender_device_snapshot.cmio_devices`
4. 如果 `requested_camera_access_snapshot.camera_access_status` 仍然是 `denied`，说明权限请求链已打通，但当前宿主进程的 TCC 状态本身仍然拒绝访问
   - `macos_direct_sender_object_demo.py --report-json ...` 现在即使真实推帧失败，也会自动回退成 inspect 报告并把 `error / direct_sender_last_error` 写进 JSON，适合保留失败现场
5. 如果 pure object 路径 snapshot 已正常，但你还想确认统一 SDK 外观是否也能看到同一组 native 设备，再运行：
   - `python3 tools/macos_direct_push_demo.py --probe-only --request-camera-access --direct-sender-library build/macos/Build/Products/Release/libakvc-macos-direct-sender.dylib`
6. 外部 Python 应用当前也可直接调用：
   - `MacDirectCameraSender(camera_name=..., ...)`
   - `MacDirectCameraSender.available_device_snapshot()`
   - `MacDirectCameraSender.request_camera_access()`
   - `MacDirectCameraSender.direct_sender_readiness(request_camera_access=True)`
   在真正 `send()` 前先拿 native snapshot
7. 如果你更想从统一 SDK 入口验证，也可继续使用：
   - `VirtualCamera(direct_only=True, ...)`
   - `VirtualCamera.direct_sender_device_snapshot()`
   - `VirtualCamera.request_camera_access()`
   - `VirtualCamera.direct_sender_readiness(request_camera_access=True)`
   在真正 `start()` 前先拿 native snapshot
8. 如果 `direct_only=True` 且 snapshot 已显示：
   - `environment_device_enumeration_empty=true`
   - `camera_access_status=denied`
   那么 `start()` 现在会直接快速失败，而不会再继续走 installer / shared-memory fallback 慢路径

## 4. 有设备但无画面

### 排查方向

1. 检查 stream start/stop 生命周期
2. 检查 IPC 控制面是否已联通
3. 检查数据面是否有新帧
4. 检查 sample buffer 构造是否正确

## 5. 性能问题

### 现象

- `1080p60` 下 CPU 高于预期

### 排查方向

1. 检查是否发生多次全帧复制
2. 检查是否在 GUI 线程做了重格式化
3. 检查 Shared Memory 路径是否成为瓶颈
4. 评估是否升级到 IOSurface 主路径

## 6. 兼容性问题

### 排查方向

1. 按应用逐一确认枚举行为
2. 区分“设备不可见”和“打开失败”
3. 记录应用版本与 macOS 版本

## 7. 当前结论

排障文档必须围绕“安装、枚举、出帧、性能、兼容性”五类问题持续更新。

当前开发环境已知限制：

1. 如果本地缺少 `numpy` 或 `cv2`，则 Python 侧视频帧相关单元测试无法完整执行
2. 如果本地缺少 `xcodegen`，则无法直接从 `project.yml` 生成 `.xcodeproj`
3. 即使 Objective-C++ 文件已通过 SDK 语法校验，也不能替代真实 `xcodebuild`、签名、公证和系统安装验证
4. 当前共享内存读帧路径只验证到“协议一致 + 语法可编译”，尚未完成真实 Zoom / Meet / Teams 打开摄像头验证
5. 当前真实帧路径仅支持 `NV12` 数据面；若后续要直通 `YUY2 / MJPG / RGB24`，需要继续扩展 `FrameProvider`
6. 当前 Python 安装服务已支持“可发现 pkg 时先执行 `/usr/sbin/installer`，再继续 `akvc-macos-install`”的自动链路，但仍需在真实管理员权限与系统批准场景下完成端到端验证
7. 在无法直接跑 `xcodebuild` 的环境下，可先运行 `python3 tools/macos_native_verify.py` 做原生树静态验证
   - 当前这条路径不仅会检查 control-bridge / extension / plist / IPC 语法，也会顺带检查 `tools/macos_sdk_contract.py`，用于确认 Python SDK 面没有和当前 Windows 对外接口约定漂移
8. 当前已补充 `python3 tools/make.py verify-native` 统一入口，建议优先用该命令代替直接调用校验脚本
9. 如果打包测试阶段 `build_dmg.sh` 报 `hdiutil: create failed - device not configured`，通常表示当前 runner/沙箱不支持挂载 DMG 设备，不等同于 `pkg / zip` 脚本本身失败
10. 如果 `status` 显示已安装但 `enumerated_devices` 仍为空，应优先检查 Camera Extension 是否真正出现在系统视频设备列表，而不是只看系统扩展批准状态
11. 如果 `install_extension()` 返回 `False`，需要区分是“安装命令本身失败”，还是“状态长时间停留在 not_installed / 设备列表迟迟未出现”；这两类问题的排查路径不同
12. 如果 smoke 输出的安装 `phase` 为 `pending_approval`，说明命令链路基本可用，但仍需用户在系统设置里批准扩展
13. 现在除了桌面端按钮，也可以直接运行 `akvc open-settings`；该命令会优先尝试打开更接近 `隐私与安全性` 的系统设置入口，如果失败再回退到普通 `System Settings.app`
14. 如果安装 `phase` 为 `installed_visible`，说明“安装状态 + 系统设备枚举”两条链路都已收敛
15. 如果安装 `phase` 为 `timeout_waiting_for_device`，应优先排查 Camera Extension 是否已真正向系统注册出可见摄像头设备
16. 当前桌面端、`akvc --json` 与 `macos_smoke.py` 都会输出 `verification_targets`；如果某个应用仍不可见，应优先按对应应用的 `steps` 定位问题，而不是泛化为同一类“设备不可见”
17. 如果需要沉淀一次完整验收结果，建议使用 `macos_validation_report.py` 把状态、benchmark 与手工应用验证记录汇总成单一 JSON，而不是分散保存多份输出
18. 如果需要证明 “PySide6 直接调用” 路径已跑通，建议先运行 `pyside6_virtual_camera_demo.py --report-json ...`，再把该 JSON 作为 `--demo-json` 输入给 `macos_validation_report.py`
19. 当前这条 demo 路径已优先走统一 SDK 入口，而不是默认直接实例化 integration helper：
    - `provider / latest-provider / video-file` 优先通过 `VirtualCamera.create_pyside6_streamer()`
    - `latest-provider` 还会优先通过 `VirtualCamera.create_latest_frame_provider()`
    - `widget / screen` 直接通过 `VirtualCamera.send_widget()` / `send_screen()`
    因此如果 demo 通过，而外部 PySide6 项目仍失败，应优先对比自己的调用方式是否仍绕过了 SDK
19. 如果想确认某次会话到底走了哪条 Python 入口，不必只看 `mode`，现在也可以直接看：
    - `validation-report.json.summary.demo_python_entrypoint_kind`
    - `session-manifest.json.summary.validation_demo_python_entrypoint_kind`
    - `session-summary.md` 里的 `Python entrypoint`
    常见值包括：
    - `create_pyside6_streamer.start_provider_stream`
    - `create_latest_frame_provider+create_pyside6_streamer.start_latest_frame_stream`
    - `send_widget`
    - `send_screen`
    同时还能继续结合 `demo_sdk_streamer_factory_used / demo_sdk_latest_provider_factory_used / demo_sdk_direct_push_used`
    判断这次 demo 是通过 SDK helper 工厂还是直接 `send_*` 路径完成的
20. 如果还没有现成的人工应用验收结果，建议先用 `macos_validation_report.py --write-manual-template ...` 生成模板，再在 Zoom / OBS / QuickTime / FaceTime 等场景下逐项填写
19. `manual-results` 当前只接受固定 app id：`zoom / teams / google_meet / obs / quicktime / facetime`，且 `result` 只能是 `pass / fail / pending / skipped`
20. 当前示例文件 [manual_validation_results.example.json](/Users/admir/workspace/virtual-camera/docs/macos/manual_validation_results.example.json:1) 与自动生成模板已经对齐，除了填写 `validated / result / notes` 外，也建议保留：
    - `name`
    - `ready`
    - `status`
    - `steps`
    这样后续复盘“为什么某次人工验收没过”时，能直接看到当时是安装未完成、设备未可见，还是只是某个应用入口未走对
21. 如果 `session-summary.md` 里 `Manual validation ready` 是 `yes`，但 `Manual app validation ready` 仍是 `no` 或 `unknown`，优先相信后者：
    - 前者来自 `validation-report.json`，更偏向“人工应用结果模板和 review 流程是否已经开始”
    - 后者来自 `session-acceptance.json`，会继续约束签名、公证工具链、自动安装、系统摄像头可见性、runtime 资产和 artifact replay 是否已经具备开始真机验收的前置条件
    - 这类情况通常不表示 Zoom/Teams 本身出错，而是说明现在还不该进入目标应用真机验收阶段
22. 如果 CLI/桌面端里看到“人工验收阻塞项：系统已枚举到虚拟摄像头、公证工具链已就绪”这类中文项，不要误以为字段名已经变化：
    - 这些是 reader-facing 标签
    - `akvc status --json` / `akvc install --json` 仍会保留 `manual_app_validation_failed_criteria_ids / manual_app_validation_unknown_criteria_ids / manual_app_validation_blocker_ids`
    - `session-summary.md` 里的 `Failed prerequisites / Unknown prerequisites / Combined blockers` 现在也会显示同一套中文标签
    - 如果需要和 `session-manifest.json.summary` 或 contract 脚本做逐项对照，优先比对 `*_ids`
23. 如果想把 demo、benchmark、模板和最终报告一次性落到同一目录，优先使用 `macos_validation_session.py` 或 `tools/make.py validation-session`
24. 如果 `macos_validation_session.py --mode video-file` 直接报错，先检查是否同时传入了 `--video-path`
25. 如果要模拟 WebRTC / AI Avatar 这类“生产者异步提交最新帧”的场景，优先使用 `--mode latest-provider`，而不是普通的 `provider`
26. 如果需要一次性沉淀六档性能基线，优先使用 `macos_validation_session.py --benchmark-matrix` 或 `tools/make.py validation-session --benchmark-matrix`
27. 当前 `akvc status`、`akvc install`、桌面端安装页与 `MacVirtualCamera.status()/enumerate_devices()/is_installed()` 已不再要求先安装 `numpy` / `cv2`；如果只是安装链路失败，不要先把问题归因到视频依赖缺失
28. 桌面端 `ServiceFacade` 当前也已做惰性导入处理；如果只是打开安装页、点击 `Install`、`Open Settings` 或 `Recheck`，不应该再因为 `numpy` / `cv2` 缺失而直接启动失败
29. 如果你自己的 `start_provider_stream(...)` provider 不是每个 tick 都有新帧，不必强行构造占位图：
    - 可以抛 `LookupError("no frame yet")`
    - 现在也可以直接返回 `None`
    这两种情况 streamer 都会跳过当前 tick；如果它仍然报 `unsupported frame input type`，说明 provider 真实返回的不是“空帧”，而是某个 SDK 尚未支持的对象类型
30. 如果桌面端已经能正常显示安装状态，但点击 `Start` 后报“请先安装 numpy 和 OpenCV（cv2）”，说明当前阻塞点已经从“安装链路”切换成“推流依赖缺失”，两者不要混为一谈
31. 当前主窗口还会直接用同一份 `stream_start_ready / stream_start_message` 门禁来控制 `Start`；如果按钮一直是灰色，先看 tooltip/状态文案到底是在提示“未批准/设备未可见”，还是在提示 `numpy / cv2` 缺失
32. 如果只是 `find_spec` 级别的 `numpy / cv2` 缺失，当前桌面端空闲轮询会自动重新探测；补装依赖后可先等待按钮状态恢复，再决定是否需要重启应用
33. 如果已经点过一次 `Start` 并触发了 worker 运行时依赖失败，优先在补装依赖后点击 `Recheck`；当前这条路径会主动重置 runtime dependency error，再重新探测依赖
34. 如果外部 PySide6 项目直接调用 `VirtualCamera.start()`，而异常内容提示“未安装 / 待批准 / 设备未出现”，这不是推流链路故障，而是 macOS 安装状态门禁在正常生效；应先排查 `install_extension_result()` / `status()` 返回的阶段
35. 如果外部 PySide6 项目希望直接走 SDK 入口，而不是自己拼 `akvc.integrations.pyside6` helper，当前优先使用：
    - `create_pyside6_bridge()`
    - `send_image() / send_pixmap() / send_widget() / send_screen()`
    - `create_latest_frame_provider() / create_pyside6_streamer()`
    如果这些入口行为异常，先确认本地代码是否已经包含最新 contract，再决定是否继续排查 Qt 抓取或 provider 逻辑
35. 如果怀疑 `QImage / QPixmap / numpy / OpenCV` 输入支持或 PySide6 demo 模式发生漂移，可先运行 `python3 tools/macos_input_contract.py` 做静态契约检查，再决定是否深入排查运行态问题
36. 如果怀疑 `macOS 13+`、`arm64/x86_64` 或 `universal2` 目标在工程声明层发生漂移，可先运行 `python3 tools/macos_build_contract.py` 检查 `project.yml`、`Info.plist` 与 `tools/make.py` 是否仍保持一致
37. 如果怀疑目标应用验收矩阵发生漂移，例如某个入口漏掉了 `Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime` 之一，可先运行 `python3 tools/macos_app_matrix_contract.py` 做静态一致性检查
38. 如果需要快速验证单架构或双架构构建参数是否正确透传，可先查看 `python3 tools/make.py build --help` / `package --help`，当前已支持 `--archs` 和 `--deployment-target`
39. 如果本机已有 Xcode 但 `tools/make.py build` 仍停在工程生成阶段，优先检查 `xcodegen --version`；当前已确认仅有 `xcodebuild` 并不足以完成 `project.yml -> .xcodeproj` 这一步
40. 如果 `python3 tools/make.py framebus-roundtrip` 或 `tools/macos_framebus_roundtrip.py` 输出里出现：
    - `producer_control.producer_seq = 1`
    - 但 `observed.direct_open_errno = 13`
    说明 producer 已成功写入控制块，但独立原生 probe 进程被当前环境拒绝访问 POSIX shm；这更像受管沙箱/运行环境限制，仍需在外部 macOS runner 或普通 shell 复核
41. 当前 `akvc status`、`akvc install`、桌面端安装状态与 `MacVirtualCamera.start()` 现在也会直接透出：
    - `ipc_probe_present`
    - `ipc_ready`
    - `ipc_environment_blocked`
    - `ipc_direct_open_errno`
    如果系统设备已经可见，但这些字段提示 `ipc_environment_blocked=true`，应优先把问题归类为“IPC/执行环境阻塞”，而不是“设备未枚举”或“视频依赖缺失”
39. 当前桌面端主窗口也会直接在安装提示区与状态栏显示 `IPC: ready / pending / blocked/errno=...`；如果用户反馈“设备已可见但 Start 仍灰掉”，先查看主窗口是否已经明确提示 `IPC: blocked/errno=1` 或 `IPC: blocked/errno=13`
40. 当前 `smoke-report.json` 也会保留同一组 IPC 字段；如果需要区分“命令桥接已通”还是“共享内存 IPC 被环境拦住”，优先查看：
    - `status.ipc_probe_present`
    - `status.ipc_ready`
    - `status.ipc_environment_blocked`
    - `status.ipc_direct_open_errno`
41. 当前 `install-session-report.json` 也会保留同一组 `ipc_*` 字段；如果“自动装包 + 自动激活”链路看起来成功，但 Python 直接推流仍无法启动，优先查看 `post_status.ipc_environment_blocked` 与 `install.ipc_direct_open_errno`
42. 如果当前想确认显式 `sync-ipc` 命令到底有没有在一次真实安装会话里跑通，优先查看：
    - `install-session-report.json.sync_ipc.supported`
    - `install-session-report.json.sync_ipc.success`
    - `install-session-report.json.sync_ipc.phase`
43. 如果需要区分“卸载命令失败”还是“卸载命令成功但系统设备仍未回落”，优先运行：
    - `akvc uninstall --json`
    - 或 `VirtualCamera.uninstall_extension_result()`
    当前原生 `akvc-macos-uninstall` 也已补上短轮询真实状态；如果这里已经直接返回 `install_failed` 或保留 `last_error=timed out waiting for extension deactivation`，就不必先怀疑 Python 轮询层
    然后重点看：
    - `phase`
    - `state`
    - `enumerated_devices`
    - `last_error`
44. 如果是从验收工件回看卸载链路，当前 `smoke-report.json` 与 `install-session.json` 里的 `uninstall` 也已经不只是 `returncode`，还会继续保留：
    - `success`
    - `phase`
    - `state`
    - `enumerated_devices`
    - `last_error`
    - `session-manifest.json.summary.install_session_sync_ipc_*`
    如果这里已经是 `supported=true` 但 `success=false`，说明问题已经从“工具是否进入发布态”收敛到“本次运行时同步失败”
43. 如果当前只想先判断“一次 validation session 是否整体被 IPC 卡住”，可先查看 `session-manifest.json.summary`，里面现在会聚合：
    - `smoke_ipc_environment_blocked`
    - `install_session_ipc_environment_blocked`
    - `framebus_roundtrip_environment_blocked`
44. 如果当前环境里没有单独的 `akvc-macos-list-devices`，也不要默认认为“看不到独立枚举工具就无法判断设备是否出现”：
    - 新版 `akvc-macos-status` 已会附带 `devices / all_devices / device_prefix`
    - Python `install_extension_result()` 现在也会优先消费这份状态快照
    - 如果 `all_devices/device_prefix` 已存在但 `devices=[]`，这更接近“系统里确实还没枚举出 AK Virtual Camera”，而不是“状态信息不足”
45. 如果桌面端安装页显示 `timeout_waiting_for_device`，现在也应优先查看：
    - `all_devices`
    - `device_prefix`
    - `install_message`
    新版桌面端会直接把“期望前缀”和“当前系统视频设备列表”拼进安装提示里；如果这里只看到普通物理摄像头，例如 `FaceTime HD Camera`，说明问题更偏向“系统尚未枚举出虚拟摄像头”，而不是 Python 推流逻辑本身
    - `effective_start_blocker_code`
    如果该字段已经明确给出 `ipc_environment_blocked / approval_required / device_not_visible`，就不需要再手动拼接多份子报告才能定位主因
41. 如果当前想确认“会话最终到底暴露了哪档格式与帧率能力”，也优先看 `session-manifest.json.summary`：
    - `validation_supported_formats / validation_supported_frame_rates`
    - `smoke_supported_formats / smoke_supported_frame_rates`
    - `install_session_supported_formats / install_session_supported_frame_rates`
    - `effective_supported_formats / effective_supported_frame_rates`
    其中 `effective_*` 会优先反映自动安装链路结束后的能力，如果这里已经缺少 `3840x2160@30/60 NV12`，就说明能力信息在会话上层已经丢失，不必先回头怀疑 Zoom/Meet
42. 如果当前怀疑 `session-manifest.json` 自身已经损坏、字段缺失，或者引用了并不存在的子工件，直接运行：
    - `python3 tools/make.py validation-session-artifact-check --manifest build/macos/session/session-manifest.json --require-existing-artifacts`
    这比手工逐个点开 `smoke-report.json`、`install-session-report.json`、`validation-report.json` 更快，因为它会一次性告诉你：
    - 顶层 `artifacts / steps / summary` 是否完整
    - manifest 里声称存在的关键子工件是否真的在磁盘上
    - `effective_start_* / effective_supported_*` 是否已经落到了非法值域
    - `install_session_sync_ipc_*` 是否类型自洽，以及 `sync_ipc_control_plane_ready=pass` 时 runtime sync 证据是否真的存在
43. 如果当前已经运行过 `macos_validation_session.py`，优先先看 `session-manifest.json.summary` 里的：
    - `artifact_check_present`
    - `artifact_check_passed`
    如果 `artifact_check_present=true` 但 `artifact_check_passed=false`，说明问题已经不是“会话有没有生成 manifest”，而是“生成出来的 manifest/子工件已经不自洽”，应优先回到 artifact replay 检查结果而不是先怀疑 UI
44. 如果 `artifact_check_passed=true`，但这次会话仍达不到最终发布标准，继续看 `session-manifest.json.summary` 里的：
    - `acceptance_present`
    - `acceptance_ready`
    - `acceptance_failed_criteria`
    - `acceptance_unknown_criteria`
    这组字段用于区分“工件结构自洽”和“最终验收已就绪”这两层问题，避免把签名、公证、目标应用识别或性能缺口误判成 manifest 结构错误
45. 如果当前只想先判断“具体是哪几个目标应用没过或没测”，也可以直接看 `session-manifest.json.summary` 里的：
    - `validation_validated_apps / validation_passed_apps / validation_failed_apps / validation_pending_apps / validation_skipped_apps`
    - `validation_passed_app_ids`
    - `validation_failed_app_ids`
    - `validation_pending_app_ids`
    - `validation_skipped_app_ids`
    - `validation_unreviewed_app_ids`
    这组字段已经从 `validation-report.json` 提升到了主 manifest 层，适合在 CI 工件页或排障时快速定位
46. 如果想继续看每个目标应用更细的人工验收状态，而不是只看 id 列表，也可以继续查看 `session-manifest.json.summary.validation_app_matrix`：
    - 每个 app id 下会保留 `reviewed / validated / result / notes / ready / status`
    这有助于区分“已经明确失败”“只是尚未验证”“入口可见但还未完成真实会议预览”这几类不同问题
47. 如果当前更希望直接看一页人类可读摘要，而不是翻主 manifest JSON，可优先打开：
    - `build/macos/session/session-summary.md`
    这份工件会把安装快照、install-session IPC 诊断、blocker、能力矩阵、artifact check、acceptance，以及目标应用 `passed/failed/pending/unreviewed` 分组收敛到一页 Markdown，并额外展开 `validation_app_matrix` 的逐应用细节，以及 `macos_13_plus_declared / universal2_ready / release_packaging_ready / pyside6_path_exercised / runtime_assets_packaged / auto_install_ready / signing_evidence_ready / notarization_tooling_ready / benchmark_matrix_complete / benchmark_fps_targets_met / benchmark_1080p60_cpu_target_met` 等关键门禁项
    即使主 manifest 暂时缺少 `validation_passed_app_ids` 这类汇总字段，只要 `validation_app_matrix` 还在，这页摘要也会自动回推出目标应用分组和计数，因此排障时应优先相信这页最终收敛结果
    当前这页摘要也会继续显示 `validation_demo_mode / validation_demo_frame_source_kind / width / height / fps / duration / video_path`；如果你在排查 PySide6 直推问题，先确认本次会话到底跑的是 `provider / latest-provider / widget / screen / video-file` 哪一条路径，再根据 `callable_provider / latest_frame_provider / widget_grab / screen_grab / opencv_video_file` 去决定是看 Qt 截屏、最新帧桥接，还是 OpenCV 视频文件输入
    如果 `pyside6_path_exercised=fail`，且 `demo_mode_supported=yes`，优先检查 `validation_demo_frame_source_kind` 是否与 mode 对应关系一致，例如 `video-file -> opencv_video_file`、`screen -> screen_grab`、`latest-provider -> latest_frame_provider`
    如果 mode 已经是 `video-file`，但 `validation_demo_video_path` 仍为空，优先检查 demo 工具是否真的带上了 `--video-path`，以及会话中使用的是不是最新 `tools/pyside6_virtual_camera_demo.py`
    如果你在运行态主动调用过 `sync_ipc_configuration_result("/new-shm")`，但画面仍旧黑帧，先确认 native sync 命令是否真的返回了 `supported=true` 且 `success=true`；当前只有在这两个条件同时满足时，Python producer 才会把已打开的 sink 重绑到新的 shm 名称。
49. 如果需要展开 acceptance 失败原因，直接运行：
    - `python3 tools/make.py validation-session-acceptance --manifest build/macos/session/session-manifest.json --output build/macos/session/session-acceptance.json`
    再查看 `session-acceptance.json` 里的 `criteria`：
    - `status=fail` 代表当前已有反证
    - `status=unknown` 代表当前只是缺少证据，通常需要补跑 benchmark、install-session 或真实应用验收
    但如果当前只是想快速读 gate 状态或失败/未知计数，也可以直接先看 `session-manifest.json.summary`，因为这些关键字段现在已经同步提升到主 manifest 层
    对 `sync_ipc_control_plane_ready` 而言，当前 `status=pass` 的含义也已经收紧为：
    - `akvc-macos-sync-ipc` 产物存在
    - 已签名
    - 满足 `universal2`
    - 且 `install-session` 已产出一次 `sync_ipc.success=true` 的运行时证据
    对 `system_camera_device_visible` 而言，当前 `status=pass` 的含义是：
    - 已运行 `akvc-macos-list-devices` 自检
    - 自检通过
    - `filtered_device_count > 0`
    - 因此它失败时应优先打开 `list-devices-binary-check.json`，确认是扩展未安装、系统尚未枚举完成，还是 `AKVC_DEVICE_PREFIX` 与实际设备名不匹配
49. 当前 `target_apps_all_passed` 的 evidence 已不再只包含计数，还会继续带出：
    - `observed_target_app_ids`
    - `missing_target_app_ids`
    - `unexpected_target_app_ids`
    - `failed_app_ids`
    - `pending_app_ids`
    - `skipped_app_ids`
    - `unreviewed_app_ids`
    - `target_app_missing_evidence_ids`
    因此如果 acceptance 里这项失败，优先直接看这些 id，而不是先手工翻完整 `verification_targets`
    当前 acceptance 也会优先采用 `session-manifest.json.summary` 里的显式 target identity 字段；如果这里已经出现 `missing_target_app_ids` 或 `unexpected_target_app_ids`，最终 gate 会直接失败，不会再被通过计数掩盖
    如果 `target_app_missing_evidence_ids` 非空，说明对应应用虽然可能填写了 `result=pass`，但缺少 `device_listed / device_selected / preview_visible` 三项证据之一；应回到目标应用重新确认设备列表、选择状态与实时预览画面
49. 当前 acceptance 摘要里尤其值得优先关注：
    - `target_apps_all_passed`
    - `system_camera_device_visible`
    - `benchmark_matrix_complete`
    - `benchmark_fps_targets_met`
    - `benchmark_1080p60_cpu_target_met`
    - `auto_install_ready`
    - `signing_evidence_ready`
    - `notarization_tooling_ready`
    这几项最直接对应最终验收标准中的“目标应用识别、六档性能矩阵完整性、FPS 稳定性、1080p60 CPU<10%、自动安装、签名、公证”
50. `auto_install_ready` 当前不再只看 “install-session 成功 + start_ready=true”，还会继续检查：
    - `install_session_start_blocker_code == ready`
    - `install_session_ipc_environment_blocked != true`
    - 如果 `install_session_ipc_probe_present=true`，则还要求 `install_session_ipc_ready=true`
    因此如果安装命令看起来成功，但 acceptance 里这项仍失败，优先查看 `session-manifest.json.summary` 里的这几组 install-session IPC 字段
51. 如果 `tools/macos_native_verify.py` 或 delivery gate contract 里是 `sync_ipc_control_plane_ready` 失败，不要只看发布物里有没有 `akvc-macos-sync-ipc`：
    现在最终门禁还要求 `install_session_sync_ipc_present/supported/success=true`，也就是当前安装会话里确实执行并跑通过一次显式同步
    如果这里只有 `release_sync_ipc_tool_exists=true` 之类的静态字段，而 `install_session_sync_ipc_success` 缺失或为 `false`，最终交付门禁会保持 `unknown` 或直接 `fail`
52. 如果当前更关心的是性能矩阵而不是单次 `1080p60` 结论，优先查看：
    - `session-manifest.json.summary.validation_benchmark_matrix_profiles`
    - `session-summary.md` 里的 `## Benchmark Matrix`
    这里会直接显示每档 `720p30 / 720p60 / 1080p30 / 1080p60 / 4k30 / 4k60` 的 `actual_fps / cpu_percent / avg_latency_ms / fps_target_met / cpu_target_met`，比只看 `benchmark_1080p60_cpu_target_met` 更适合排查是哪一档 profile 先退化
53. 如果 acceptance 里 `benchmark_fps_targets_met=pass` 但最终仍没有通过性能验收，继续检查：
    - `benchmark_matrix_complete`
    - `session-manifest.json.summary.validation_benchmark_matrix_profiles`
    - `benchmark_report.summary.benchmark_acceptance.required_profiles_present`
    - `benchmark_report.summary.benchmark_acceptance.missing_required_profiles`
    现在上层验收不会再把“只跑了部分 profile、且这些 profile FPS 都达标”误判成完整性能验收通过；六档 `720/1080/4K x 30/60` 只要缺一档，`benchmark_matrix_complete` 就不会是 `pass`
44. 如果在完整依赖环境里运行 `framebus-roundtrip` 或直接观察 `MacVirtualCamera.consumer_count`，而该值始终是 `0`，现在可以把它解读为“原生 consumer 尚未真正附着”或“当前环境阻止了 consumer 打开共享内存”；这比之前单纯看到 `0` 更有诊断意义，因为 macOS consumer 侧已开始维护该字段
45. 当前 `tools/macos_framebus_roundtrip.py` 已不再因为缺少 `numpy` 就直接失效；如果现在运行它仍失败，优先看输出 JSON 里的：
    - `observed.status`
    - `observed.direct_open_errno`
    - `environment_blocked`
    - `error`
    特别是当 `status=producer_open_failed` 且 `direct_open_errno=1` 时，说明问题已经前移到“producer 自己都无法创建 POSIX shm”，这同样应归类为执行环境/权限阻塞，而不是 consumer 读帧问题
46. 当前 `akvc status` / `smoke-report.json` / `install-session-report.json` / `validation-report.json` 在读取最新 roundtrip 工件时，也已开始识别这类 producer 侧失败：
    - `ipc_environment_blocked=true`
    - `ipc_direct_open_errno=1`
    - `ipc_last_error` 中会同时保留 `shm_open(create) failed (errno=1)` 与 `producer_open_failed`
    这说明高层状态入口已经把它视为同一类 IPC/环境阻塞，而不是“未知安装失败”
36. 如果需要一次性确认本机/runner 是否具备“生成工程、构建、打包、签名、公证、staple”的前置条件，优先运行 `python3 tools/make.py preflight`
37. 如果 `xcodebuild` 报 `requires a provisioning profile`，优先确认是否走的是最新 `python3 tools/make.py build` 入口；当前默认会追加 `CODE_SIGNING_ALLOWED=NO` 等参数，正常情况下不应在“编译验证”阶段要求 provisioning
38. 如果仍出现 `requires a provisioning profile`，先删除旧的 `virtualcam/macos/akvc-macos.xcodeproj` 后重新执行 `python3 tools/make.py build`，避免旧工程缓存或手工 Xcode 配置覆盖命令行设置
39. 如果怀疑 `akvc-macos-list-devices` 本身输出漂移，例如少了 `all_devices`、`device_prefix`，或者 prefix 过滤语义不再稳定，优先运行：
    - `python3 tools/make.py list-devices-binary-check --list-devices-tool build/macos/Build/Products/Release/akvc-macos-list-devices --output build/macos/session/list-devices-binary-check.json`
    这条检查会分别覆盖默认 prefix 和“强制无匹配 prefix”两种场景，用来区分“系统里确实还没有虚拟摄像头”和“命令工具自己的过滤/输出格式已经回退”
39. 当前这台开发机的已知预检结果是：`xcodebuild`、`xcodegen`、`pkgbuild`、`codesign`、`notarytool/stapler` 可用，但 `SIGN_IDENTITY / PRODUCTSIGN_IDENTITY / NOTARY_PROFILE` 尚未配置
40. 如果 `status`/`smoke`/`validation report` 里看到 `mach_service_name` 与 `extension_identifier` 不同，不一定是错误；前者是 IPC/Mach Service 名称，后者才是当前 System Extension 的 bundle id
41. 如果 `python3 tools/make.py package` 在当前环境因为 `hdiutil: create failed - device not configured` 报错，最新入口会继续保留 `pkg / zip` 产物；这通常说明当前 runner 不支持 DMG 设备挂载，不等同于 `pkg` 或 `.app` 结构失败
42. `macos_validation_session.py` 与 `tools/make.py validation-session` 现在会默认先生成 `preflight.json`，再把它并入最终 `validation-report.json`；如果只想看安装/设备状态，可显式加 `--skip-preflight`
43. 当前 `session-summary.md` 还已新增 `Sync IPC Tool` 小节，会直接展示：
    - `release_sync_ipc_tool_exists`
    - `release_sync_ipc_tool_signed`
    - `release_sync_ipc_tool_universal2_ready`
    同时 acceptance 门禁里也会额外显示 `sync_ipc_control_plane_ready`
44. 这条 `sync_ipc_control_plane_ready` 当前是非关键 criterion：
    - 它不会单独阻断 `acceptance_ready`
    - 但能明确提示“显式 IPC 配置同步工具是否真的进入发布态”
43. 如果 `preflight.json` 里某个工具出现 `present=true` 但 `probe.available=false`，先检查当前运行环境是否限制了该工具调用，再决定是否判定为“工具不可用”
44. 如果 `installer/macos/uninstall.sh` 找不到卸载工具，先确认当前构建产物目录是：
    - `build/macos/Build/Products/Release`
    - `build/macos/bin`
    - `build/bin`
    最新脚本会按这三类路径依次回退，不需要手工改脚本
39. 如果 `python3 tools/make.py notarize` 或 `installer/macos/notarize.sh` 直接报 `pkg must be signed before notarization`，优先检查：
    - 是否已先执行 `python3 tools/make.py sign`
    - 是否已为 `build_pkg.sh` 配置 `PRODUCTSIGN_IDENTITY`
    - `pkgutil --check-signature build/macos/VirtualCamera.pkg` 是否仍显示 `no signature`
40. 如果 `sign_app.sh` 在签名前就报 `missing extension bundle` 或 `missing ... entitlements`，不要绕过它；这通常意味着当前产物还不满足真正发布要求，而不是脚本过于严格
41. 如果 `release-diagnostics.json` 里 `universal2_ready=false`，优先检查：
    - Host App 可执行文件的 `lipo -archs`
    - Camera Extension 可执行文件的 `lipo -archs`
    - 当前构建是否误用了单架构 `--archs arm64` 或 `--archs x86_64`
42. 如果 `release-diagnostics.json` 里 `pkg_signed=false`，不要直接进入公证；先用 `pkgutil --check-signature build/macos/VirtualCamera.pkg` 复核，并确认 `PRODUCTSIGN_IDENTITY` 是否已配置
43. 如果 `release-diagnostics.json` 里 `pkg_install_location_expected=false` 或 `pkg_identifier_expected=false`，优先检查 `installer/macos/build_pkg.sh` 中的：
    - `INSTALL_LOCATION`
    - `PACKAGE_IDENTIFIER`
    - `PACKAGE_VERSION`
44. 如果 `release-diagnostics.json` 里 `pkg_includes_extension_payload=false`，优先排查 Host App bundle 是否真的包含 `Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension`，再重新打包
45. 如果 `release-diagnostics.json` 里 `host_embeds_extension_bundle=false`，先检查目标 container app 的 `Contents/Library/SystemExtensions` 下是否真的包含 `com.sidus.amaran-desktop.cameraextension.systemextension`，不要只看独立的 Release 目录产物
46. 如果 `release-diagnostics.json` 里 `host_bundle_identifier_expected=false`、`extension_bundle_identifier_expected=false` 或 `minimum_system_version_expected=false`，优先检查 Host / Extension `Info.plist` 与 Xcode 产物中的实际展开值，而不是只看源码模板
47. 如果 `open -n -a /Applications/<your-container-app>.app --args --activate` 仍然被系统直接 `killed`，并且 `log show` 里出现：
    - `No matching profile found`
    - `Code has restricted entitlements`
    - `Missing entitlement com.apple.developer.system-extension.install`
    当前真正缺的通常不是 `akvc-macos-install` 的 entitlement，而是 Host / Camera Extension 的 macOS provisioning profile。优先在签名前设置：
    - `HOST_PROVISIONING_PROFILE=/path/to/host.mobileprovision`
    - `EXTENSION_PROVISIONING_PROFILE=/path/to/extension.mobileprovision`
48. `installer/macos/sign_app.sh` 在检测到上述两个环境变量后，会自动把 profile 嵌入到 Host 与嵌入式 system extension 的 `Contents/embedded.provisionprofile`，再继续执行 `codesign`
49. 如果安装 `phase` 为 `package_install_failed`，优先检查：
    - `AKVC_MACOS_PKG` 是否指向真实存在的 `VirtualCamera.pkg`
    - 当前终端 / 应用是否具备运行 `/usr/sbin/installer -pkg ... -target /` 的权限
    - `installer` 原始 stderr 是否提示鉴权、签名、包损坏或安装位置冲突
50. 如果系统里已经安装了目标 container app，但 Python 侧仍试图先装 `pkg`，优先检查：
    - `AKVC_HOST_APP_BUNDLE`
    - `AKVC_HOST_EXECUTABLE`
    - `/Applications/<your-container-app>.app`
    是否真的存在，避免 container app 定位失败后误判为“需要重新装包”
51. 如果 wheel / 外部 PySide6 打包目录里找不到 macOS 安装资产，优先检查是否已执行：
    - `python3 tools/make.py sync-macos-runtime --require-pkg`
    或：
    - `python3 tools/make.py package --sync-runtime`
50. 当前 `akvc.runtime` 对 macOS 安装资产的查找顺序是：
    - 显式参数
    - `AKVC_MACOS_* / AKVC_HOST_*` 环境变量
    - `build/macos/...`
    - 包内 `akvc/_runtime/macos`
51. 如果 `validation-report.json` 里的 `runtime_packaged_assets_present=false` 或 `runtime_packaged_pkg_present=false`，优先检查：
    - 是否已执行 `python3 tools/make.py sync-macos-runtime --require-pkg`
    - `camera-core/src/akvc/_runtime/macos` 下是否真的包含 `VirtualCamera.pkg`
    - 外部打包流程是否遗漏了 `akvc/_runtime/macos` 目录
52. 如果需要判断“安装命令失败”还是“卸载后状态没有回落”，优先查看 `smoke-report.json`：
    - `install`
    - `status_after_install`
    - `uninstall`
    - `status_after_uninstall`
    这比只看最终 `validation-report.json` 更适合定位安装往返过程中的哪一步出了问题
53. 如果需要判断“Python 自动装包链路失败”还是“底层原生命令链路失败”，优先对比：
    - `install-session-report.json`
    - `smoke-report.json`
    前者覆盖 `pkg -> Host App -> DefaultMacInstallerService`，后者覆盖 `status/install/uninstall` 原生命令桥接
54. 如果 `session-summary.md` 显示 `timeout_waiting_for_device`，先看这几组字段，而不是只盯着 phase：
    - `Effective devices / Effective all devices / Effective device prefix`
    - `Installation Snapshot -> Status devices / Status all devices / Device prefix`
    - `Install Session -> Session devices / Session all devices / Session device prefix`
    经验上：
    - 如果 `all_devices` 里只有 `FaceTime HD Camera` 之类真实摄像头，而 `device_prefix=AK Virtual Camera`，说明“扩展状态已收敛，但系统设备枚举还没看到虚拟摄像头”
    - 如果 `devices` 已出现 `AK Virtual Camera`，但某个目标应用仍看不到，优先排查该应用是否需要重启重新枚举设备
