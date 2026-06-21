# Phase 4 — Verification Plan

> 把 `.claude/rules/virtual-camera.md` Phase 4 占位的 VC-M-1~5 落地为
> 可执行清单。本轮无 Mac → 全部 `BLOCKED`，本文为用户验证脚本。

## 1. 验收清单

| # | 验收项 | 检查方式 | 通过判据 |
|---|---|---|---|
| VC-M-1 | Camera Extension 安装成功 | 运行 host app → 系统设置授权 → `systemextensionsctl list` | 列表含 `com.akvc.camera-extension` 状态 `[activated waiting]` 或 `[activated enabled]`；`log stream` 见 `akvc.ext.provider.start` |
| VC-M-2 | FaceTime 能发现设备 | FaceTime → Video → Camera | 下拉含 `AK Virtual Camera`；选中后预览正常 |
| VC-M-3 | Zoom（macOS）能发现并打开 | Zoom → Settings → Video → Camera | 下拉含 `AK Virtual Camera`；预览正常 |
| VC-M-4 | Safari getUserMedia 能发现并打开 | https://webrtc.github.io/samples/src/content/devices/input-output/ | Video source 下拉含 `AK Virtual Camera`；选择后预览正常 |
| VC-M-5 | OBS（macOS）能发现并打开 | OBS → Sources → Video Capture Device → Device | 下拉含 `AK Virtual Camera`；画面正常 |

## 2. 辅助验收（非强制，但建议）

| 项 | 方式 |
|---|---|
| Photo Booth 发现 | Photo Booth → Camera → `AK Virtual Camera` |
| QuickTime 录制 | File → New Movie Recording → `AK Virtual Camera` |
| 占位帧（I3） | 不启动 Python 生产者，只加载扩展 → 消费端应显示稳定黑帧（不闪烁） |
| UI 崩溃不消失（I1） | 启动生产者后 kill Python → 设备仍在，画面切到占位黑帧 |
| 卸载干净（I2） | `systemextensionsctl uninstall` → `systemextensionsctl list` 不再含；`/akvc-frames-v1` shm 清理 |

## 3. 验收输出格式

```
## Virtual-Camera Acceptance (Phase 4 / macOS)

| # | Item                              | Status  | Evidence |
|---|-----------------------------------|---------|----------|
| VC-M-1 | Extension installed             | PASS/FAIL/BLOCKED | systemextensionsctl list output; log line |
| VC-M-2 | FaceTime discovers device       | PASS/FAIL/BLOCKED | screenshot vc-m2.png |
| VC-M-3 | Zoom discovers device           | PASS/FAIL/BLOCKED | screenshot vc-m3.png |
| VC-M-4 | Safari getUserMedia             | PASS/FAIL/BLOCKED | screenshot vc-m4.png |
| VC-M-5 | OBS discovers device            | PASS/FAIL/BLOCKED | obs log line / screenshot |

Result: 5/5 PASS  (or  N/5 PASS, M BLOCKED — task INCOMPLETE/BLOCKED)
```

## 4. 本轮状态

| # | Status | Reason |
|---|---|---|
| VC-M-1 | BLOCKED | 无 macOS 机器 |
| VC-M-2 | BLOCKED | 无 macOS 机器 |
| VC-M-3 | BLOCKED | 无 macOS 机器 |
| VC-M-4 | BLOCKED | 无 macOS 机器 |
| VC-M-5 | BLOCKED | 无 macOS 机器 |

按 `acceptance.md` §6，无图形/物理环境时必须标 `BLOCKED` 并提供用户验证
脚本（即本文 §1）。VC-M-1 / IPC 自检这类纯 API/CLI 项，Agent 在有 Mac 后
必须自己跑通，不允许标 BLOCKED。

## 5. 离线自检（本轮已在 Windows 环境完成）

| 项 | 方式 | 结果 |
|---|---|---|
| `macos_shm.py` 语法 | `python -m pyflakes` / AST parse | PASS |
| `macos_shm.py` 在 win32 可惰性导入 | `from ...macos_shm import MacOsShmSink` | PASS |
| `_protocol.py` schema 尺寸 | `struct.calcsize` 对比 C 头 | PASS（header=80, ctrl=128） |
| `windows_shm.py` 重构无回归 | `pytest -q tests/unit` | PASS（6/6） |
| `framebus_posix.c` 语法 | 无 C 编译器，人工 review | PASS（POSIX 标准用法） |
| Swift 骨架 | 人工 review + `// VERIFY` 标记完整 | PASS（scaffold） |
