# debugging.md — Root Cause Analysis 强制流程

> 任何"修复型"代码改动都必须先经过 RCA 七步法，并产出标准报告。
> 没有 RCA，就没有 Fix。

## 1. 七步法

```
1. Reproduce        ── 在受控环境复现问题
2. Collect Evidence ── 日志 / coredump / 注册表 / 进程列表 / 抓帧
3. Localize         ── 把问题压缩到具体文件:行 或 具体调用
4. Hypothesize      ── 列 ≥ 1 个根因假设（每个都要"可被证伪"）
5. Verify           ── 用最小实验证伪/证实假设（加 print / 改输入 / 二分）
6. Fix              ── 最小化代码改动；附 reasoning
7. Verify Fix       ── 复现实验重跑必须 PASS；并跑回归
```

## 2. 禁止与必须

**禁止**：
- 看到 error 就改：先 Reproduce + Localize。
- 改了多处再统一测：每次只改一处可证伪的内容。
- 删除日志/注释来"绕过"：把信号换成静默 = 把 bug 埋深。
- "再试一次"作为修复手段（除非已证明问题是 transient，且已加重试逻辑）。

**必须**：
- 每个修改都对应一条假设。
- 每条假设都对应一次 Verify 实验。
- Verify 失败时回滚改动，不允许"层层叠加"。

## 3. 证据矩阵

按问题类别准备最低证据集：

| 类别 | 必备证据 |
|---|---|
| 编译错误 | 完整 build log（`.akvc/logs/build/...`）+ 涉及源文件 ± 30 行 |
| 链接错误 | `link.exe /VERBOSE` 输出 + `dumpbin /symbols <lib>` 节选 |
| 运行期 Python 异常 | traceback + 最近一份 `akvc.*.log` |
| Win32 API 失败 | `GetLastError()` 数值 + `FormatMessage` 译文 + Process Monitor 抓栈 |
| DShow Filter 不可见 | `graphedt` 截图 + `regedit` 导出 CLSID 子树 + DLL 签名状态 |
| OBS 看不见设备 | OBS log 文件（`%APPDATA%\obs-studio\logs\`）+ DShow filter 列表 |
| 帧不到达消费端 | `akvc.worker.log` 中 publish_seq 序列 + 共享内存前 64 字节 hex 转储 |
| 性能未达标 | Windows Performance Recorder 跟踪 / `cv2` 时序 print |

## 4. 标准 RCA 报告模板

每次进入 Debug Loop 后，**至少**产出一份以下报告（可在响应内联）：

```
## RCA — <一行问题概述>

### Root Cause
- 根因（一句话）：……
- 触发条件：……
- 影响范围：……

### Evidence
1. 日志路径：`.akvc/logs/build/20260619T101512-attempt-03.log`
   关键节选：
   ```
   error C4596: ...
   ```
2. 代码位置：`third_party/baseclasses/transip.h:214`
3. 复现命令：`uv run tools\make.py build`
4. 其他证据（可选）：……

### Hypothesis Tree（如经历多假设）
- H1：MSVC 新增 conformance check  →  Verified by minimal repro (link)
- H2：streams.h include order  →  Falsified（去掉 include 仍报错）

### Fix
- 文件：`tools/make.py`、`virtualcam/windows/dshow/CMakeLists.txt`
- 改动：…… (一两行说清"做了什么 + 为什么够用")
- 风险：……（是否波及其他 Phase / 平台）

### Verification
- 命令：`uv run tools\make.py build`
- 结果：退出码 0，产物大小 X MB，关键日志行 ……
- 回归：`uv run python tools/make.py test` 全绿
```

## 5. 假设管理

- 每条假设附两个字段：
  - **Predicts**："如果 H 为真，则 ___"
  - **Refuted by**："出现 ___ 即可证伪"
- 一旦实验证伪，立即放弃；不允许"虽然实验证伪了，但我直觉还是这条"。

## 6. 工具与最小实验清单（项目相关）

| 工具/命令 | 用途 |
|---|---|
| `dumpbin /exports build\bin\Release\akvc-dshow.dll` | 验证 DllRegisterServer 导出 |
| `regedit /e clsid.reg "HKCR\CLSID\{8E14549A-...}"` | 导出 CLSID 注册表 |
| `graphedt.exe` | 直接看 DShow 是否能枚举到我们的 filter |
| `ProcessMonitor.exe` (filter: process=frameserver.exe) | 抓 LowBox ACL 拒绝事件 |
| Python `mmap` 单行 | 验证共享内存 region magic |
| `ffmpeg -f dshow -i video="AK Virtual Camera" -t 2 out.mp4` | 端到端拉流 |
| `OutputDebugString` + `DebugView64.exe` | DShow 进程内调试 |

## 7. 多次循环的"知识沉淀"

每完成一个 RCA，必须把"经验"沉淀到合适位置：

- 通用工程经验 → 追加到 `docs/operations/troubleshooting.md`（不存在则创建）。
- 与 BaseClasses/MSVC/CMake 等第三方相关 → 在 `tools/make.py` 顶部注释"已知 patch 列表"。
- 与某个 Phase 强相关 → 写到该 Phase 的 `risk-analysis.md`。

不沉淀 = 同样的 bug 第二次还要花同样的时间。
