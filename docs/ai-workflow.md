# AI Workflow — 项目级 AI 开发工作流

> 面向**人类协作者**的总览。规则正本在 `.claude/CLAUDE.md` 与 `.claude/rules/*`。
> 本文档解释"为什么这么定 / 如何正确使用 / 出现冲突时怎么处理"。

## 1. 设计目标

工作流升级的目的：把 AI Agent 从"**写完代码就走**"升级成"**写、编、跑、测、调、验、收**全链路工程师"。

具体解决以下既往问题：

- 写完代码就结束（不验证）。
- 编译失败后停下并把错误丢给用户。
- 测试失败后不自动修复。
- 不会自动调试，每次靠用户分析报错。
- 摄像头无法被 OBS/Zoom 识别就直接收尾。

## 2. 强制流程图

```
┌──────────┐
│ Analysis │
└────┬─────┘
     ▼
┌──────────┐
│  Design  │
└────┬─────┘
     ▼
┌────────────────┐
│ Implementation │
└────┬───────────┘
     ▼
┌──────────┐  fail (≤20)
│  Build   │ ───────────┐
└────┬─────┘            │
     │ pass             ▼
     │              ┌────────┐
     │              │ Debug  │
     │              │  Fix   │
     │              └────┬───┘
     │                   │
     ▼                   │
┌──────────┐  fail (≤20) │
│   Run    │ ────────────┘
└────┬─────┘
     │ pass
     ▼
┌──────────┐  fail (≤20)
│   Test   │ ────────────┐
└────┬─────┘             ▼
     │ pass         (Debug→Fix→Retest)
     ▼
┌────────────┐  any fail
│ Acceptance │ ────────────┐
└────┬───────┘             ▼
     │ all pass        (Debug→Fix→Re-Acceptance)
     ▼
┌────────────┐
│  Complete  │
└────────────┘
```

## 3. 文件清单

| 路径 | 角色 |
|---|---|
| `.claude/CLAUDE.md` | Agent 入口；列出强制行为 / 禁止行为 / 决策权限 |
| `.claude/rules/workflow.md` | 12 步工作流契约 |
| `.claude/rules/build-loop.md` | Build / Run / Test 三段自动修复循环（每段 ≤ 20） |
| `.claude/rules/debugging.md` | Root-Cause-Analysis 七步法 + 标准报告模板 |
| `.claude/rules/acceptance.md` | Definition of Done：四闸 + 状态表 + 反例 |
| `.claude/rules/virtual-camera.md` | 虚拟摄像头专项 6 条（Phase 2）+ 后续阶段占位 |
| `docs/ai-workflow.md` | 本文（人类总览） |

未来扩展：
- `.claude/rules/macos.md`（Phase 4 引入）
- `.claude/rules/release.md`（Phase 6 / 6+ 签名 / 公证流程）

## 4. 四闸（Definition of Done）

| Gate | 通过判据 |
|---|---|
| Build | 全部产物可被 `tools/make.py build` 一次性出来；退出码 0 |
| Run   | 所有可独立启动入口启动到健康点 |
| Tests | `pytest -q` 全绿；跳过项 ≤ 白名单 |
| Acceptance | 当前 Phase 的 `verification-plan.md` + `virtual-camera.md` 全过 |

四闸全过 = `COMPLETE`；任一未过 = `INCOMPLETE` 或 `BLOCKED`。

## 5. 三段自动修复循环

```
Build-Fix Loop:  attempt 1..20  → ASK-USER 在 ≥10 次无进展时
Run-Fix   Loop:  attempt 1..20
Test-Fix  Loop:  attempt 1..20
```

- 每次失败必须按 `debugging.md` 走 RCA。
- 同一错误签名连续 3 次未变 → Stuck Heuristic：必须切换策略。
- 求助前必须有 ≥10 次有差异的尝试 + 完整证据。

## 6. RCA 报告（每次 Debug 必产）

四节模板：

```
### Root Cause       — 一句话根因
### Evidence         — 日志路径 + 关键节选 + 复现命令
### Fix              — 改动清单 + 为什么够用 + 风险
### Verification     — 重跑命令 + 退出码 + 关键日志行 + 回归
```

## 7. 虚拟摄像头专项（Phase 2 强制 6 条）

```
[ ] VC-1 虚拟摄像头注册成功
[ ] VC-2 GraphStudioNext 能发现设备
[ ] VC-3 DirectShow 枚举成功
[ ] VC-4 OBS 能发现设备
[ ] VC-5 Zoom 能发现设备
[ ] VC-6 Chrome getUserMedia 能发现设备
```

任一失败：任务 = `INCOMPLETE`，自动进入 Debug Loop。
Phase 3 起追加 MF 与 Teams/Edge；Phase 4 追加 macOS。

## 8. Agent 在每次任务开始时的"开机自检"

期望 Agent 在每次会话/任务开头打印一行：

```
Rules loaded: workflow / build-loop / debugging / acceptance / virtual-camera
```

未打印 = 未读规则 = 你可以理直气壮地让它重读。

## 9. 与 Phase 文档的关系

- `docs/phase0/`、`docs/phase1/`、`docs/phase2/` 是"业务真值"——目标、设计、风险、验收。
- `.claude/rules/*` 是"流程真值"——执行方法、修复方法、收尾方法。
- 二者**不应**冲突；如有冲突：
  - 业务条款（如 CLSID、像素格式）以 Phase 文档为准。
  - 流程条款（如 attempt 上限、报告格式）以 `.claude/rules/*` 为准。

## 10. 用户如何发挥这套规则

### 10.1 期望 Agent 做的事
- 编译失败时**自己读编译日志、自己修、自己重编译**。
- 摄像头不可见时**自己跑 graphedt / OBS log / RegEdit 等工具收集证据**，按 RCA 修。
- 把每次任务收尾整理成"四闸状态表 + RCA 报告 + 下一步计划"。

### 10.2 用户最少的干预姿势
- 提需求时引用 Phase 文档里的"Acceptance"/"Verification"段。
- 让 Agent 自己跑构建、自己读日志；只在 Agent 卡 ≥ 10 次时介入。
- 当 Agent 想"跳步"或"绕开规则"时，直接说一句"按 `.claude/rules/` 执行"。

### 10.3 当 Agent 违反规则时
- 直接引用规则编号：例如 "你违反了 N-2，请按 build-loop.md 自动循环修复，再来。"
- 让它把违反的 N-x / B-x 复述一遍，然后重做该步。

## 11. 规则演进

- 任何规则修改都属于"工作流变更"，需在响应中显式标注。
- 推荐的演进姿势：
  1. 用一次真实任务暴露当前规则的不足。
  2. 在任务结束的 "下一步计划" 里建议规则更新。
  3. 用户确认后再改 `.claude/rules/*`。

## 12. 不变量

无论规则如何演进，下列不变量一定保留：

- **代码完成 ≠ 任务完成**（四闸全过才完成）。
- **错误信息 ≠ 解决方案**（必须 RCA）。
- **Agent 不允许把构建/调试甩给用户**（除非 ≥10 次无进展）。
- **不允许伪造验收**（无法跑就标 BLOCKED）。
