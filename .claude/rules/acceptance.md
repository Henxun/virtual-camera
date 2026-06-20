# acceptance.md — Definition of Done

> 任务在所有四闸通过前**禁止**标记 `COMPLETE`。
> 通过 ≠ 部分通过；通过 ≠ "我觉得应该可以"。

## 1. 四闸（Four Gates）

| 闸 | 含义 | 出口判据 |
|---|---|---|
| Build | 全部目标产物可被现代工具链一次性构建出来 | `uv run tools\make.py build --python` 退出码 0；关键产物存在；时间戳 = 本次构建 |
| Run   | 所有可独立启动的入口可以启动到健康点 | `python -m akvc_app` 显示主窗口、`akvc status` 返回成功码、`akvc doctor` 全 PASS |
| Tests | 所有自动化测试通过 | `pytest -q` 全绿；新增功能有覆盖；跳过项 ≤ 白名单 |
| Acceptance | 业务级验收（按当前 Phase 与项目级专项） | 见 §2 + `virtual-camera.md` |

每个闸必须有"证据"：命令 + 关键输出 + 时间戳。

## 2. 业务级 Acceptance

### 2.1 当前阶段（默认）

读取**最新一份** `docs/phaseN/verification-plan.md`，把全部"必通过"项映射成清单，逐一执行。

### 2.2 项目级专项

| 涉及范围 | 叠加规则 |
|---|---|
| Windows DShow / MF / Helper | `virtual-camera.md` 全部 6 条 |
| macOS Camera Extension | `virtual-camera.md` macOS 子节（Phase 4 起生效） |
| 跨平台桌面 UI | `apps/desktop` MVVM 边界检查（pre-commit grep） |
| 安装器 / 签名 | EV / Developer ID / 公证状态 |

## 3. 验收闸状态表（每次必输出）

每次任务结束都必须打印这张表：

```
| Gate       | Status     | Evidence                                                  |
|------------|------------|-----------------------------------------------------------|
| Build      | PASS/FAIL  | uv run tools\make.py build --python  → exit 0; akvc-dshow.dll @ ...  |
| Run        | PASS/FAIL  | python -m akvc_app  → main window OK; akvc status → exit 0  |
| Tests      | PASS/FAIL  | pytest -q  → 23 passed, 0 failed                          |
| Acceptance | PASS/FAIL  | virtual-camera.md: 6/6 PASS; verification-plan.md: 14/14 |
```

任一为 FAIL/SKIPPED，**任务收尾必须是 `INCOMPLETE` 或 `BLOCKED`**。

## 4. 测试跳过白名单

允许跳过的测试种类（必须显式 `pytest.skip(reason=...)`）：

- 需要物理摄像头但当前环境无可用 USB 设备：reason 含 `"no usb camera"`。
- 需要管理员权限的注册测试：reason 含 `"requires admin"`。
- 需要外部消费端（OBS/Zoom）启动：reason 含 `"requires consumer client"`。

非白名单原因跳过 = FAIL。

## 5. 收尾报告格式

任务最后必须包含：

```
### Gates
| Gate | Status | Evidence |
|---|---|---|
| ... | ... | ... |

### Project-specific Acceptance
- virtual-camera.md:
  - [x] DShow 注册成功
  - [x] GraphStudioNext 发现设备
  - [x] DirectShow 枚举成功
  - [x] OBS 发现
  - [x] Zoom 发现
  - [x] Chrome getUserMedia 发现

### Final status
COMPLETE / INCOMPLETE / BLOCKED

### Files changed
- ...

### Logs / artefacts
- .akvc/logs/build/20260619T...-attempt-03.log
- .akvc/logs/run/...
- .akvc/logs/test/...

### Next steps
1. ...
2. ...
```

## 6. 反例（不允许出现）

- "代码已经写好了，请您测试一下" → 违反 N-1。
- "编译过了 + 单元测试过了，任务完成" → 漏 Run/Acceptance 两闸。
- "Run 报错但 Tests 全过，所以 COMPLETE" → 违反 §1 任一闸即不通过。
- "我无法在沙箱里跑 OBS，所以这条免验" → 应标 `BLOCKED`，不是免验。

## 7. 例外

- 仅文档变更：四闸退化为 `Build=N/A, Run=N/A, Tests=N/A, Acceptance=docs lint`。
- 仅工作流变更（`.claude/rules/*`）：`Acceptance` 闸 = "rules 自洽 + 与 docs/ai-workflow.md 一致 + 与现有 phase docs 不冲突"。
