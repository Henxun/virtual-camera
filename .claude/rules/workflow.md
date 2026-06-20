# workflow.md — 强制开发工作流

> Phase 任务（Phase 2 起的实施类任务）必须严格按此 12 步推进。
> 任何步骤不通过，**不允许**前进到下一步；必须回到 Debug/Fix。

## 1. 总体流程图

```
┌────────────┐
│  Analysis  │  收集需求、读规则、读历史、列出未知项
└─────┬──────┘
      ▼
┌────────────┐
│   Design   │  方案选型、契约、目录、风险（轻量化设计文档）
└─────┬──────┘
      ▼
┌────────────────┐
│ Implementation │  编码（含测试同步编写）
└─────┬──────────┘
      ▼
┌────────────┐
│   Build    │  ── 失败 ──▶ Debug → Fix → Build (≤20)
└─────┬──────┘
      ▼
┌────────────┐
│    Run     │  ── 失败 ──▶ Debug → Fix → Run   (≤20)
└─────┬──────┘
      ▼
┌────────────┐
│    Test    │  ── 失败 ──▶ Debug → Fix → Test  (≤20)
└─────┬──────┘
      ▼
┌────────────┐
│ Acceptance │  ── 任一未过 ──▶ Debug → Fix → Acceptance
└─────┬──────┘
      ▼
┌────────────┐
│  Complete  │
└────────────┘
```

## 2. 步骤定义与出口判据

### 2.1 Analysis
- 输入：用户原话、最新阶段文档、`.claude/rules/*`、git 状态、上次任务遗留 TodoList。
- 行动：
  - 读取并复述任务目标（一句话）。
  - 列出已知 / 未知 / 假设。
  - 找出与现有 Phase 文档冲突点（如有）。
- 出口判据：能用 ≤ 5 行写出 **目标 + 范围 + 风险**。

### 2.2 Design
- 输入：Analysis 输出。
- 行动：
  - 选型与权衡（即使是小改动，也要说一句"为什么这么改"）。
  - 列出会触动的文件清单（precise file list）。
  - 列出可量化的成功条件。
- 出口判据：用户或 Agent 都能据此独立验证。
- 复杂度阈值：若改动跨 ≥ 3 个模块或新增公开 API，必须落到 `docs/` 一份"轻量设计页"。

### 2.3 Implementation
- 输入：Design。
- 行动：
  - **同时**写实现代码与测试代码（红/绿/重构）。
  - 每写完一个功能即提交进度（更新 TodoList）。
  - 严禁"先全写完再调试"。
- 出口判据：所有计划文件已落盘；本地 `pyflakes/ruff/cmake -P` 等静态检查通过。

### 2.4 Build
- 详见 `build-loop.md` §1。
- 出口判据：所有目标产物存在 + `cmake --build` / `pip install` 退出码为 0。

### 2.5 Run
- 详见 `build-loop.md` §2。
- 出口判据：进程能完整启动到指定健康点（如 UI 显示 "Streaming"、CLI 返回成功码）。

### 2.6 Test
- 详见 `build-loop.md` §3。
- 出口判据：`pytest -q` 全绿；新增功能有对应单元/集成测试。

### 2.7 Debug → Fix → Rebuild → Retest
- 触发条件：Build / Run / Test / Acceptance 任一不过。
- 详见 `debugging.md` 与 `build-loop.md`。

### 2.8 Acceptance
- 详见 `acceptance.md`。
- 涉及虚拟摄像头通路时，叠加 `virtual-camera.md`。

### 2.9 Complete
- 详见 `acceptance.md` §收尾报告。

## 3. 步骤间约束

- **不允许跳步**：例如 "我直接 commit 了" 不算 Build。
- **不允许并行**：除非用户明确许可，单一会话内串行推进，避免上下文丢失。
- **不允许"我看起来好了"**：每一步出口必须有可验证证据（命令输出、日志、文件 hash）。

## 4. 步骤的最小输出

每一步必须产出可粘贴的文本块，至少包含：
- 步骤名
- 命令（如有）
- 关键输出摘要（≤ 20 行）
- 出口判据是否满足（PASS / FAIL）

## 5. 与 TodoList 的对应

- 每个 Phase 任务在 TodoList 中至少有：
  - "Analysis & Design"（一项）
  - 各模块 Implementation 子项
  - "Build & Fix Loop"
  - "Run & Fix Loop"
  - "Test & Fix Loop"
  - "Acceptance"
  - "交付总结"

## 6. 例外处理

- 仅文档变更：Implementation→Build/Run/Test 等步骤可"无操作过闸"，但仍要在响应中显式标注 `N/A (docs only)`。
- 仅工作流变更（如本次任务）：同上，禁止开发业务功能。
