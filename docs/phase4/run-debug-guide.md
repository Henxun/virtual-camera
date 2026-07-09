# Phase 4 — macOS Run & Debug Guide

> 加载 / 调试 Camera Extension 的操作手册。
> 本文档服务于当前已验收过的 macOS 路径回归，不再把该路径视为“仅骨架 / 全 BLOCKED”状态。

## 1. 日志

Camera Extension 写 `os_log`，subsystem `com.akvc.camera-extension`：

```bash
log stream --predicate 'subsystem == "com.akvc.camera-extension"' --level debug

log stream --predicate \
  'subsystem == "com.akvc.camera-extension" OR subsystem == "com.sidus.amaran-desktop"'

log show --predicate 'subsystem == "com.akvc.camera-extension"' --last 10m
```

或 Console.app：过滤 subsystem。

## 2. 扩展进程定位

```bash
systemextensionsctl list
launchctl list | grep -i akvc
ps aux | grep -i akvc-camera-extension
```

## 3. 加载流程

1. 构建 / 打包 / 签名（见 [signing-notarization.md](signing-notarization.md)）。
2. 调试环境下执行 `systemextensionsctl developer on`。
3. 运行 host/container app，触发 `OSSystemExtensionRequest`。
4. 在系统设置中允许扩展。
5. `log stream` 中确认 provider/start 相关日志。
6. 启动 producer 或桌面 app，确认设备开始进入可消费状态。

如果当前走的是仓库内验证过的打包路径，优先参考：
- [tools/package_nuitka.py](../../tools/package_nuitka.py)
- [verification-plan.md](verification-plan.md)

## 4. 验证 IPC / 数据路径

当前实现仍需重点排查共享内存/数据路径是否正常：

```bash
ipcs -m
```

若日志中反复出现 `akvc_fb_open` / timeout / torn frame 相关信号，优先检查：

- producer 是否已成功启动
- 当前 shm 名称 / descriptor 是否一致
- 时间基是否仍遵守 `CLOCK_REALTIME` 100ns ticks
- 扩展端是否确实收到了数据路径初始化结果

如果当前环境明确证明 `shm_open` 路径受阻，再进入 Plan B 讨论；不要在没有证据时回退架构方向。

## 5. 帧路径自检

优先观察：

- producer 是否持续发帧
- consumer 是否持续读到新帧
- 是否存在 timeout / torn frame / stream start failure
- 设备可见但黑屏时，问题是在“枚举链路”还是“帧链路”

## 6. 消费端验证

常见消费端：

- FaceTime
- Safari / getUserMedia 页面
- Zoom
- OBS

具体验收项见 [verification-plan.md](verification-plan.md) 中的 VC-M-1~5。

## 7. 常见运行失败

| 症状 | 优先排查 |
|---|---|
| 扩展不加载 | 签名 / 公证 / entitlements / `systemextensionsctl list` |
| 设备可见但黑屏 | 数据路径、producer_seq、timeout/torn frame、stream start |
| 设备可见但画面不动 | 时间基不一致、start/clock 事件不足 |
| 客户端启动超时 | 扩展未稳定进入流状态 |
| 打包后无授权 / 无设备 | `.app` bundle、`Info.plist`、embedded extension、codesign |

## 8. 工具

| 工具 | 用途 |
|---|---|
| `log stream/show` | os_log 日志 |
| `systemextensionsctl` | 装载/卸载/列举扩展 |
| `ipcs -m` | 共享内存存在性检查 |
| `codesign -dv` | 签名状态 |
| `spctl -a -vvv` | Gatekeeper 评估 |
| Console.app | 图形化日志 |
