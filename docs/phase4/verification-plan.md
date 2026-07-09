# Phase 4 — Verification Plan

> 把 `.claude/rules/virtual-camera.md` Phase 4 的 VC-M-1~5 落地为当前回归验收清单。
> 本文档不再把 macOS 路径描述为“无 Mac → 全 BLOCKED”的前置状态，而是作为后续改动的回归基线。

## 1. 验收清单

| # | 验收项 | 检查方式 | 通过判据 |
|---|---|---|---|
| VC-M-1 | Camera Extension 安装成功 | 运行 host/container app → 系统设置授权 → `systemextensionsctl list` | 列表含目标 extension，状态可用；`log stream` 可见 provider/start 相关日志 |
| VC-M-2 | FaceTime 能发现设备 | FaceTime → Video → Camera | 下拉含 `AK Virtual Camera`；选中后预览正常 |
| VC-M-3 | Zoom（macOS）能发现并打开 | Zoom → Settings → Video → Camera | 下拉含 `AK Virtual Camera`；预览正常 |
| VC-M-4 | Safari / getUserMedia 能发现并打开 | WebRTC device sample 或等价页面 | Video source 下拉含 `AK Virtual Camera`；选择后预览正常 |
| VC-M-5 | OBS（macOS）能发现并打开 | OBS → Sources → Video Capture Device → Device | 下拉含 `AK Virtual Camera`；画面正常 |

## 2. 当前回归定位

这些检查现在的意义是：

- 用于后续 macOS 改动后的 regression verification
- 用于确认打包、签名、扩展激活与推帧路径没有回退
- 用于对齐文档/规则与当前已验收实现

而不是再把它们当作“尚未拿到 Mac 时的阻塞占位项”。

## 3. 建议的回归证据

| 项 | 建议证据 |
|---|---|
| VC-M-1 | `systemextensionsctl list` 输出、`log stream` 关键行 |
| VC-M-2 | FaceTime 截图 / 操作记录 |
| VC-M-3 | Zoom 截图 / 操作记录 |
| VC-M-4 | 浏览器页面截图 / 设备列表证据 |
| VC-M-5 | OBS 截图 / 日志 |

## 4. 验收输出格式

```text
## Virtual-Camera Acceptance (Phase 4 / macOS)

| # | Item                        | Status | Evidence |
|---|-----------------------------|--------|----------|
| VC-M-1 | Extension installed     | PASS / FAIL / BLOCKED | ... |
| VC-M-2 | FaceTime discovers device | PASS / FAIL / BLOCKED | ... |
| VC-M-3 | Zoom discovers device     | PASS / FAIL / BLOCKED | ... |
| VC-M-4 | Safari / getUserMedia     | PASS / FAIL / BLOCKED | ... |
| VC-M-5 | OBS discovers device      | PASS / FAIL / BLOCKED | ... |

Result: 5/5 PASS
```

## 5. 何时允许 BLOCKED

只有在客观环境缺失时才允许标 `BLOCKED`，例如：

- 当前会话无可用 macOS 图形环境
- 无法访问目标消费端
- 缺签名/权限/外部依赖导致无法继续

但这类 BLOCKED 应视为“本次环境限制”，不是当前 Phase 4 的默认项目状态。

## 6. 与打包回归的关系

如果改动涉及 macOS 打包或 host app 验证链路，建议同时回归：

- [tools/package_nuitka.py](../../tools/package_nuitka.py)
- [docs/phase4/run-debug-guide.md](run-debug-guide.md)

重点确认：

1. `.app` bundle 可生成
2. `Info.plist` patch 仍正确
3. `.systemextension` 仍被正确嵌入
4. codesign / runtime 验证链路未回退

## 7. 当前语义说明

- 历史上的“全 BLOCKED”说明已过时。
- 当前应该把本文档当作 **已验收基线的回归清单**。
- 若未来实现再次变化，应更新本文档，而不是继续复用旧的阻塞模板。
