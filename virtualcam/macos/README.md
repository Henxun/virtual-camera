# macOS Native Skeleton

此目录承载 macOS 原生层骨架：

- `camera_extension/`：CoreMediaIO Camera Extension（Objective-C++）
- `control_bridge/`：共享命令桥、System Extension 控制辅助代码与原生命令工具；不在高频帧数据面中
- `ipc/`：共享协议和原生 IPC 辅助代码
- `project.yml`：XcodeGen 工程定义

当前阶段目标：

1. 建立稳定目录结构
2. 明确 build target 和 bundle 关系
3. 为 Python 层 `CommandMacInstallerService` 提供未来可对接的原生命令入口
4. 将“系统扩展状态查询”和“系统视频设备枚举”拆成独立命令工具，减少安装验证误判
5. 让 `akvc-macos-status` 原生命令直接合并 FrameBus/IPC 探针结果，输出 `ipc_transport / ipc_probe_present / ipc_ready / ipc_environment_blocked / ipc_last_error / ipc_probe_path / ipc_direct_open_errno`
6. 固定运行时热路径为 `Python producer -> shared memory / IOSurface -> Camera Extension`，避免把容器 App 变成帧转发 daemon

当前阶段不宣称：

1. Camera Extension 已可加载
2. 容器 App 已可完成真实安装
3. 所有目标宿主应用中的识别链路都已完成最终验收
