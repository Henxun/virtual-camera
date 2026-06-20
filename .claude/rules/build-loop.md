# build-loop.md — Build / Run / Test 自动修复循环

> 任何代码改动后，Agent 必须**自动**进入本文件定义的三段循环。
> 每段独立计数：Build-Fix ≤ 20、Run-Fix ≤ 20、Test-Fix ≤ 20。
> 总尝试次数 ≤ 60。第 10 次仍无进展时，可向用户求助（见 CLAUDE.md N-4）。

## 0. 通用规则

### 0.1 日志策略

所有命令输出必须重定向到本地日志：

| 阶段 | 路径（项目根相对） |
|---|---|
| Build | `.akvc/logs/build/<UTC-yyyymmddTHHMMSS>-attempt-NN.log` |
| Run   | `.akvc/logs/run/<UTC-yyyymmddTHHMMSS>-attempt-NN.log`   |
| Test  | `.akvc/logs/test/<UTC-yyyymmddTHHMMSS>-attempt-NN.log`  |

`.akvc/` 已在 `.gitignore`；日志保留 ≥ 30 天。

### 0.2 计数器

每次循环维护：
- `attempt`：当前段的尝试次数。
- `last_signature`：上次错误的关键签名（编译器错误码 / 异常类型 + 文件:行）。
- `repeat_count`：相同签名连续出现次数。

### 0.3 进展检测（Anti-Stuck）

- 同一 `last_signature` 连续 3 次未变 → 触发 **Stuck Heuristic**：必须**立即**切换策略，禁止继续重复同一修法。
- 切换策略例：换抽象层（patch 第三方代码而不是改自己的代码）、换工具链（Ninja↔VS）、收集更多日志（开 verbose / debug 选项）、二分缩小问题面。

### 0.4 终止条件

- **PASS**：阶段出口判据满足。
- **GIVE-UP-LOCAL**：达到 20 次。进入下一段循环前**必须**输出 `INCOMPLETE` 报告。
- **ASK-USER**：连续 ≥ 10 次无进展且收集证据完备时允许；详见 CLAUDE.md N-4。

## 1. Build-Fix Loop

### 触发
任何 .cpp/.h/.py/CMakeLists.txt/.toml 变更后自动进入。

### 命令（Phase 2 当前）
```
uv run tools/make.py configure
uv run tools/make.py build --python
```

### 失败处理
1. 读取最近一份 build log。
2. **抽取首条 fatal/error**（不是 warning）。
3. 记录 signature = `<error-code>:<file>:<line>`。
4. 走 RCA（`debugging.md`）。
5. 修改最少代码。
6. 重新执行命令。
7. attempt++。

### 常见类别与首选策略

| 类别 | 首选策略 |
|---|---|
| 第三方代码编译失败（如 BaseClasses） | patch 第三方源码 + 在 CMake 加 `/wd####`，**禁止**禁用整个目标 |
| MSVC 严格性新增报错 | 用 `/permissive` 而非 `/permissive-`；按需补充 `/wd####` |
| CMake 生成器不识别 | 升级 CMake 或改 generator；必要时回退 Ninja Multi-Config + vcvars |
| 链接错误 | 检查 `target_link_libraries` 顺序，确认 .lib 路径存在 |
| Python 模块找不到 | 重跑 `pip install -e <pkg>`；检查 `pyproject.toml` packages |

### 出口判据
- 退出码 0
- 关键产物存在（如 `build/bin/Release/akvc-dshow.dll`）
- 文件大小 > 0 且时间戳 = 本次构建

## 2. Run-Fix Loop

### 触发
Build 成功后。

### 命令（Phase 2）
```
uv run python -m akvc_app                  # 桌面应用
uv run akvc status                         # CLI 自检
uv run akvc doctor                         # 自检诊断
```

### 失败处理
1. 收集 stderr + 应用日志（`%LOCALAPPDATA%\AKVC\logs\*.log`）。
2. 抽取首条 ERROR / Exception。
3. 记录 signature。
4. 走 RCA。
5. 修复 → 重启进程。
6. attempt++。

### 常见类别

| 类别 | 首选策略 |
|---|---|
| `ImportError` / `ModuleNotFoundError` | 重跑 `pip install -e`；检查 `__init__.py` 导出 |
| `OSError: [WinError 5] Access is denied` | 检查共享内存 ACL；提示用户 elevated shell |
| 注册失败（regsvr32 0x8002801c 等） | DLL 路径含空格、bitness 不符；检查 manifest |
| Filter 在 OBS 不可见 | 见 `virtual-camera.md` Debug Loop |

### 出口判据
- 进程稳态 ≥ 30 秒（应用类）
- 期望日志事件出现（如 `akvc.worker.sink_open`）
- 命令类返回 0 + stdout 含期望字段

## 3. Test-Fix Loop

### 触发
Run 成功后。

### 命令
```
uv run python tools/make.py test
uv run python -m pytest -q tests/integration   # 如适用
```

### 失败处理
1. 收集 pytest 详细输出（`-vv --tb=short`）。
2. 区分：
   - 真实代码问题 → 改代码
   - 测试本身错（断言写错） → 改测试，但要在 RCA 中记录
   - 环境依赖（缺摄像头） → 测试需 `pytest.skip()` + 标 `BLOCKED`
3. 修复 → 重跑。
4. attempt++。

### 出口判据
- `passed` ≥ 期望数；`failed` = 0；`error` = 0。
- 跳过项有显式 reason，且不超过白名单。

## 4. 失败/求助报告模板

第 10 次未通过且证据齐备时，使用以下模板：

```
## ASK-USER — Build/Run/Test stuck after N attempts

### Attempts summary
| # | Hypothesis | Action | Result |
|---|---|---|---|
| 1 | ... | ... | ... |
| ... | ... | ... | ... |

### Current root-cause hypothesis
...

### Why I'm asking now
- This is beyond Agent capability because: <env / hardware / signing / ...>
- Required from user: <decision / credential / hardware / approval>

### What I will do once unblocked
1. ...
2. ...
```
