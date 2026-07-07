# Phase 4 — macOS Run & Debug Guide

> 加载 / 调试 Camera Extension 的操作手册。

## 1. 日志

Camera Extension 写 `os_log`，subsystem `com.akvc.camera-extension`：

```bash
# 实时流
log stream --predicate 'subsystem == "com.akvc.camera-extension"' --level debug

# 含 container app / legacy host
log stream --predicate \
  'subsystem == "com.akvc.camera-extension" OR subsystem == "com.sidus.amaran-desktop"'

# 历史
log show --predicate 'subsystem == "com.akvc.camera-extension"' --last 10m
```

或 Console.app：过滤 subsystem。

## 2. 扩展进程定位

```bash
systemextensionsctl list                              # 已装扩展
launchctl list | grep -i akvc                         # 扩展进程
ps aux | grep -i akvc-camera-extension
```

Camera Extension 进程名通常是 `<bundle-id>` 形式的 helper。

## 3. 加载流程

1. 构建签名（见 build-guide / signing runbook）。
2. `systemextensionsctl developer on`（dev 一次性）。
3. 运行 container app（或 legacy host target）→ 触发 `OSSystemExtensionRequest`。
4. 系统设置 → 隐私与安全性 → 允许扩展。
5. `log stream` 应见 `akvc.ext.provider.start`。
6. 启动 Python 生产者：`python -m akvc_app`（macOS 路径）。
7. 见 `akvc.ext.stream.start` + 帧到达日志。

## 4. 验证 IPC（shm_open 沙盒——头号风险）

```bash
# 生产者创建 region 后，检查存在
ls -la /dev/shm/akvc-frames-v1     # macOS: /tmp/shm-* 或 ipcs
ipcs -m

# 扩展日志里若反复 "akvc_fb_open failed st=-1001" → 沙盒挡了 shm_open
```

若确认被挡：切 Plan B（XPC + IOSurface），见 `implementation-plan.md` §2.3。

## 5. 帧路径自检

扩展内 `framebus_posix.c` 已在 torn/timeout 时分别返回：
- `E_AKVC_FRAMEBUS_TIMEOUT` (-1003) → 无新帧（正常，生产者未发）
- `E_AKVC_FRAMEBUS_TORN_FRAME` (-1004) → 撕裂，跳过

日志里若全是 timeout → 检查：
- Python sink `open()` 是否成功（`/akvc-frames-v1` 是否创建）
- 时间基：Python `_now_100ns_clock_realtime` vs C `clock_gettime` 是否同基
- producer_seq 是否在递增（`akvc_fb_producer_seq`）

## 6. 消费端验证

```bash
# FaceTime / Photo Booth / QuickTime → 摄像头选 "AK Virtual Camera"
# Safari: https://webrtc.github.io/samples/src/content/devices/input-output/
# Zoom: Settings → Video → Camera
# OBS: Sources → Video Capture Device → Device
```

见 `verification-plan.md` VC-M-1~5。

## 7. 常见运行失败

| 症状 | 排查 |
|---|---|
| 扩展不加载 | 签名/公证/entitlements；`systemextensionsctl list` 看状态 |
| `provider.start` 但无设备 | Info.plist V-4 / `attach` API V-3 |
| 设备在但黑屏 | 帧不到达 → §5；或 frame delivery V-1 投递失败 |
| 设备在但画面不动 | 时间基不一致 → 心跳误判 producer 死 → 占位帧覆盖 |
| 客户端报 "Timeout starting video source" | `Start()` 未发足够事件 / clock V-2 |
| 卸载后残留 | `systemextensionsctl uninstall <TEAMID> com.akvc.camera-extension` |

## 8. 工具

| 工具 | 用途 |
|---|---|
| `log stream/show` | os_log 日志 |
| `systemextensionsctl` | 装载/卸载/列举扩展 |
| `ipcs -m` / `ls /dev/shm` | POSIX shm 存在性 |
| `codesign -dv` | 签名状态 |
| `spctl -a -vvv` | Gatekeeper 评估 |
| Console.app | 图形化日志 |
