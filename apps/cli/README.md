# AK Virtual Camera — CLI

```
akvc register     # regsvr32 the DShow filter (admin required)
akvc unregister   # remove registration
akvc status       # show device status
akvc status --json
akvc install      # macOS: install / activate Camera Extension
akvc install --json
akvc sync-ipc     # macOS: 显式同步共享内存/IPC 配置
akvc sync-ipc --json
akvc doctor       # basic self-check (placeholder, full version in Phase 6)
```

macOS `install` 当前会输出安装阶段结果，例如：

1. `pending_approval`
2. `installed_visible`
3. `timeout_waiting_for_install`
4. `timeout_waiting_for_device`

macOS `status --json` 与 `install --json` 当前还会输出结构化 `verification_targets`：

1. 覆盖 `Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime`
2. 每项包含 `ready`、`status`、`steps`
3. 便于直接复用于自动化验证、测试报告或上层 UI

同时，macOS `status/install` 当前已经统一基于 SDK 安装快照语义输出：

1. `state / phase / devices`
2. `start_ready / start_blocker_code / start_message / start_steps`
3. 这样 CLI、Desktop 和 Python SDK 现在共享同一套安装与就绪判断口径
4. 同时还会显式输出运行时拓扑摘要：
   - `runtime_topology_kind`
   - `runtime_frame_path`
   - `runtime_host_role`
   - `runtime_host_in_frame_hot_path`
   - `runtime_dedicated_host_daemon_required`
   - `runtime_container_app_configured`
   - `runtime_data_plane`
   - `runtime_control_plane`
5. 这组字段会直接说明当前 macOS container app 只是容器 / 激活器 / 命令桥，不在高频帧热路径中

macOS 显式指定目标应用时，CLI 现在优先使用：

1. `--app-bundle /Applications/YourApp.app`
2. `--app-executable /Applications/YourApp.app/Contents/MacOS/YourApp`
3. `--host-bundle / --host-executable` 仍可继续使用，但仅作为兼容别名映射到 `app_*`

macOS `sync-ipc` 当前用于显式把目标共享内存名称同步到原生配置面：

1. 可选 `--shared-memory-name /akvc-custom`
2. 输出 `supported / success / phase / shared_memory_name / ipc_transport`
3. 便于在 `status()` 已显示 `ipc_not_ready / ipc_environment_blocked` 时做独立排查

macOS `status/install` 的人工验收前置条件摘要当前采用双轨输出：

1. 普通文本输出优先展示中文标签，例如“系统已枚举到虚拟摄像头”“公证工具链已就绪”
2. `--json` 同时保留 reader-facing 数组与原始 `*_ids` 数组
3. 自动化脚本如需和 `session-manifest.json.summary` 对齐，优先读取 `manual_app_validation_failed_criteria_ids / manual_app_validation_unknown_criteria_ids / manual_app_validation_blocker_ids`
