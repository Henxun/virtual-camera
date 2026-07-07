# macOS 虚拟摄像头性能基准

## 1. 目标

本文件定义 macOS 虚拟摄像头实现的性能验证口径。

核心目标：

1. `1080p60` 稳定输出
2. CPU `<10%`
3. 丢帧率可控
4. 长时运行稳定

## 2. 测试场景

### 基础场景

1. `720p30`
2. `720p60`
3. `1080p30`
4. `1080p60`
5. `4K30`
6. `4K60`

### 应用场景

1. PySide6 窗口直推
2. 屏幕共享转推
3. 视频文件播放转推
4. AI Avatar 输出转推
5. WebRTC 视频流转推

## 3. 指标

需要记录：

1. 平均 CPU
2. 峰值 CPU
3. 平均内存
4. 平均 FPS
5. P95 帧延迟
6. P99 帧延迟
7. 丢帧率
8. 连续运行时长

## 4. 判定标准

### 主验收标准

1. `1080p60` 可稳定持续输出
2. 平均 CPU `<10%`
3. 无明显画面卡顿
4. 无持续性时间漂移

### 增强标准

1. `4K60` 可运行
2. CPU 与丢帧率处于可接受范围

## 5. 对比对象

建议至少比较：

1. Shared Memory Ring 实现
2. IOSurface Ring 实现
3. 不同输入源类型
4. 单消费者与多消费者

## 6. 基准输出格式

每次基准都应记录：

1. macOS 版本
2. 机器型号
3. 芯片架构
4. 输入类型
5. 分辨率
6. 帧率
7. 消费应用
8. 指标结果

## 7. 当前结论

在正式实现前，benchmark 文档先固定“测什么、怎么判定、怎么比较”；实现阶段再逐步填入真实数据。

## 8. 当前仓库入口

当前仓库已补充基准入口：

1. `python3 tools/macos_benchmark.py`
2. `python3 tools/macos_benchmark.py --width 1920 --height 1080 --fps 60 --duration 5 --warmup 1`
3. `python3 tools/macos_benchmark.py --profile 1080p60 --duration 5 --warmup 1`
4. `python3 tools/macos_benchmark.py --matrix --duration 5 --warmup 1 --output build/macos/benchmark-matrix.json`
5. `python3 tools/macos_benchmark.py --output build/macos/benchmark.json`
6. `python3 tools/make.py benchmark`
7. `python3 tools/make.py benchmark --profile 1080p60 --output build/macos/benchmark-1080p60.json`
8. `python3 tools/make.py benchmark --matrix --output build/macos/benchmark-matrix.json`
9. `python3 tools/macos_validation_report.py --benchmark-json build/macos/benchmark.json --output build/macos/validation-report.json`
10. `python3 tools/macos_validation_session.py --output-dir build/macos/session --benchmark-matrix`

当前输出为结构化 JSON，至少包含：

1. 单场景输出：
   - `scenario`
   - `system`
   - `metrics`
   - `acceptance`
2. 矩阵输出：
   - `kind`
   - `profiles`
   - `results`
   - `summary`

当前 `acceptance` / `summary.benchmark_acceptance` 的语义建议固定为：

1. 单场景：
   - `fps_target_met`
   - `cpu_target_applies`
   - `cpu_target_met`
2. 矩阵摘要：
   - `profile_count`
   - `required_profile_count`
   - `required_profiles_present`
   - `missing_required_profiles`
   - `unexpected_profiles`
   - `all_fps_targets_met`
   - `1080p60_cpu_target_met`

这样 benchmark 不再只是“采样一堆指标”，而是可以直接进入更上层验收判断。

## 9. 当前范围说明

当前 benchmark 先覆盖 **Python Producer Path**：

1. `PySide6 / SDK / FramePipeline / FrameSink` 生产者路径
2. 帧发送吞吐、CPU、延迟、预估丢帧
3. 作为 Shared Memory / IOSurface 后续优化的基线

当前 benchmark **还不能替代**：

1. Camera Extension 真机端到端性能验证
2. Zoom / Teams / Google Meet / OBS / QuickTime / FaceTime 的真实消费端测量
3. 系统级 CPU `<10%` 的最终验收

## 10. 与统一验收链路的关系

当前 benchmark 已开始接入：

1. `validation-report.json.summary.benchmark_acceptance`
2. `session-acceptance.json`

其中 `session-acceptance.json` 目前会直接消费以下两项：

1. `benchmark_matrix_complete`
2. `benchmark_fps_targets_met`
3. `benchmark_1080p60_cpu_target_met`

因此建议把 benchmark 看成两层：

1. 指标层
   - `avg_cpu_percent / peak_cpu_percent / avg_fps / p95 / p99 / drop_estimate`
2. 验收层
   - 是否真的覆盖了 `720p30 / 720p60 / 1080p30 / 1080p60 / 4k30 / 4k60` 六档矩阵
   - 是否达到 profile 对应 FPS 目标
   - 是否在 `1080p60` 场景下满足 CPU `<10%`

如果 benchmark 只产出原始指标、不产出 acceptance 摘要，那么上层会话就无法稳定判断“证据不足”和“证据明确失败”。
如果只跑了子集 profile，例如只跑 `1080p60` 或 `720p30 + 1080p60 + 4k30`，最新 acceptance 也会把 `benchmark_matrix_complete` 标成 `fail/unknown`，避免把“部分 profile 通过”误当成“六档矩阵都已验证”。

## 11. 当前状态（2026-06-27）

当前仓库已经完成的部分：

1. 六档 profile 与 matrix 输出入口已固定
2. benchmark JSON 已能进入 `validation-report` 与 `validation-session`
3. `session-acceptance.json` 已开始直接消费 benchmark acceptance 摘要

当前仍缺的强证据：

1. 真实 Camera Extension 消费路径下的 `1080p60` CPU 实测
2. Shared Memory 与未来 IOSurface 主路径的并排对比
3. 各目标应用实际开启虚拟摄像头后的端到端性能记录

## 12. 下一步

后续应继续补充：

1. 真机 `1080p60` 实测结果
2. 单消费者 / 多消费者对比
3. Shared Memory Ring 与未来 IOSurface 路径对比
4. 目标应用矩阵下的端到端性能记录
