# AK Virtual Camera — Desktop App

PySide6 desktop application; MVVM.

```
python -m akvc_app
```

The app spawns a `FrameWorker` subprocess that owns the Frame Bus producer
(`akvc.core.frame_sink.windows_shm.WindowsShmSink`) and streams the configured
source through the pipeline.

The DirectShow filter (loaded into OBS / Zoom / Chrome / WeChat / etc.) is the
consumer end; it discovers the frame bus by name and reads NV12 frames.

macOS 当前已补充安装状态展示基线：

1. 桌面端 `ServiceFacade` 会轮询 Camera Extension 安装状态
2. `MainViewModel` 会透传 `install_state` / `install_phase` / `install_devices`
3. 主窗口当前提供 `Install` 按钮，并在状态区显示安装阶段与设备可见性
4. 对 `pending_approval` / `installed_visible` / `timeout_waiting_for_device` 等阶段会补充用户引导文案
5. 对关键阶段还会展示结构化步骤列表，帮助用户按顺序完成批准、重试和目标应用验证
6. 当前还提供 `Open Settings` 与 `Recheck` 动作，方便用户在批准扩展后主动刷新安装状态
7. 当前还会输出结构化目标应用验证清单，覆盖 `Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime`
8. 每个目标应用都会附带 `ready` / `status` / `steps`，供主窗口、后续 CLI 或测试报告复用
9. 当前桌面端的安装/状态链路已做惰性导入处理：仅查看安装状态、批准提示和设备可见性时，不再强制依赖 `numpy` / `cv2`
10. 只有真正点击 `Start` 启动推流 worker 时，才会加载 `frame_worker`、`numpy` 和 `cv2`
11. 如果当前机器只想完成 Camera Extension 安装验证而没有视频依赖，桌面端现在仍可打开并完成 `Install / Open Settings / Recheck`
12. 如果在 `Start` 时缺少 `numpy` 或 `cv2`，当前会直接给出明确错误，而不是在导入阶段就让整个桌面端启动失败
13. 主窗口当前还会根据 `stream_start_ready` 自动禁用或启用 `Start` 按钮：
   - 扩展未批准 / 设备未可见：禁用 `Start`
   - 设备已在系统摄像头列表中可见：启用 `Start`
14. 如果 `numpy` / `cv2` 缺失，即使扩展已安装并可见，`Start` 也会继续保持禁用，并优先提示“推流依赖缺失”
15. 如果桌面端处于空闲状态且后续补装了 `numpy` / `cv2`，当前轮询会重新探测依赖并自动恢复 `Start` 按钮，无需重启应用
16. 如果用户之前已经点过一次 `Start`，并触发了 worker 级运行时依赖失败，当前也可以在补装依赖后点击 `Recheck` 主动恢复，不必重启桌面端
17. 当前安装状态区还会显式展示 Camera Extension IPC 探测摘要：
   - `IPC: ready`
   - `IPC: pending`
   - `IPC: blocked/errno=1`
   - `IPC: blocked/errno=13`
18. 如果最新 `framebus-roundtrip` 报告显示当前环境阻止了共享内存访问，主窗口状态提示里会额外显示：
   - `IPC 详情`
   - `IPC 报告`
   便于直接定位 `framebus-roundtrip.json` 与具体错误，而不必先翻 CLI/日志
19. 当前安装提示区如果同时拿到了 `manual_app_validation_*` 摘要，会优先显示中文 reader-facing 标签：
   - `人工验收失败前置项`
   - `人工验收待确认项`
   - `人工验收阻塞项`
   例如“系统已枚举到虚拟摄像头”“公证工具链已就绪”，避免直接把内部 gate id 暴露给验收人员
20. 当前 Desktop 安装状态链路也已开始透传能力矩阵：
   - `supported_formats`
   - `supported_frame_rates`
21. `ServiceFacade` 会优先复用 macOS backend 的 `stream_capabilities()` typed surface，再回退到原始状态 payload
22. `MainViewModel` 与主窗口状态栏当前也会继续带出这两项能力摘要，便于直接确认 `720p / 1080p / 4K` 与 `30 / 60fps` 是否符合当前实现声明
23. 当前安装提示区还会额外显示运行时拓扑摘要：
   - `runtime_topology_kind`
   - `runtime_data_plane`
   - `runtime_control_plane`
   - `runtime_host_role`
24. 这组提示会明确告诉验收人员：`host` 是容器 / 激活器 / 命令桥，不在 Camera Extension 的帧热路径里，也不要求独立常驻 daemon

仓库当前还补充了更通用的 PySide6 集成基线：

1. `akvc.integrations.pyside6.push_qimage(...)`
2. `akvc.integrations.pyside6.push_qpixmap(...)`
3. `akvc.integrations.pyside6.push_widget(...)`
4. `akvc.integrations.pyside6.push_screen(...)`
5. `akvc.integrations.pyside6.LatestFrameProvider`
6. `akvc.integrations.pyside6.PySide6VirtualCameraStreamer`
7. `LatestFrameProvider` 适合：
   - WebRTC 解码线程把最新帧提交给 Qt 主线程
   - AI Avatar / 推理线程把最新渲染结果提交给定时推流器
8. `PySide6VirtualCameraStreamer` 当前支持：
   - `start_widget_stream(...)`
   - `start_screen_stream(...)`
   - `start_provider_stream(...)`
   - `stop()`
17. 当前仓库还提供 `python3 tools/pyside6_virtual_camera_demo.py`
18. demo 支持：
   - `--mode provider`
   - `--mode latest-provider`
   - `--mode widget`
   - `--mode screen`
   - `--mode video-file --video-path demo.mp4`
19. demo 当前还支持 `--report-json`，可把一次 PySide6 推流示例运行结果输出为 JSON 工件
20. 其中：
   - `provider` 适合 AI Avatar / WebRTC / 自定义帧源
   - `latest-provider` 适合用 `LatestFrameProvider.submit(frame)` 模拟 WebRTC / AI Avatar / 推理线程异步产帧
   - `video-file` 适合本地视频播放转推
21. 如果要把 demo + benchmark + manual template + validation report 一次性串起来，可使用：
   - `python3 tools/macos_validation_session.py --output-dir build/macos/session --mode provider`
   - `python3 tools/macos_validation_session.py --output-dir build/macos/session --mode latest-provider`
   - `python3 tools/macos_validation_session.py --output-dir build/macos/session --mode video-file --video-path demo.mp4`
