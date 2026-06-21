# virtual-camera.md — 虚拟摄像头专项验收

> 凡是涉及虚拟摄像头通路（注册 / 帧路径 / 消费端识别）的任务，
> 都必须叠加本清单。**任意一项失败 = INCOMPLETE + 自动 Debug Loop**。
> Phase 2 (Windows DirectShow MVP) 的 6 条清单为基线；Phase 3 起追加 MF 与平台扩展条目。

## 1. Phase 2 — Windows DirectShow MVP（强制 6 条）

| # | 验收项 | 检查方式 | 通过判据 |
|---|---|---|---|
| VC-1 | 虚拟摄像头注册成功 | 管理员命令行：`uv run tools\make.py register`；然后 `uv run akvc status` | regsvr32 退出码 0；status 显示 `Inproc DLL: <build path>` 非空 |
| VC-2 | GraphStudioNext / graphedt 能发现设备 | 打开 GraphStudioNext / graphedt → Insert Filters → Video Capture Sources | 列表里出现 `AK Virtual Camera` |
| VC-3 | DirectShow 枚举成功 | 跑脚本 `tools/diag/dshow_enum.py`（若不存在则编写）：用 ctypes 调 `ICreateDevEnum::CreateClassEnumerator(VideoInputDeviceCategory)` | 输出包含 `AK Virtual Camera` |
| VC-4 | OBS 能发现设备 | OBS Studio 30+ → Sources → Video Capture Device → Device | 下拉里出现 `AK Virtual Camera`；选中后画面正常 |
| VC-5 | Zoom 能发现设备 | Zoom Desktop → Settings → Video → Camera | 下拉里出现 `AK Virtual Camera`；预览正常 |
| VC-6 | Chrome getUserMedia 能发现设备 | https://webrtc.github.io/samples/src/content/devices/input-output/ → Video source | 下拉里出现 `AK Virtual Camera`；选择后预览正常 |

### 1.1 Phase 2 不强制（但要在收尾报告中显式标注的）

- Microsoft Teams（新版）— 走 Media Foundation，Phase 3 才覆盖；Phase 2 中 OK 状态 = `KNOWN-GAP`。
- Edge MFCapture — 同上。
- 32-bit 主机 — Phase 2 仅出 x64 DLL，标 `OUT-OF-SCOPE`。

## 2. Phase 3 — Windows MF 上线后追加（占位）

- VC-W-MF-1：Helper Service 安装并自启
- VC-W-MF-2：MFCreateVirtualCamera 注册成功（事件查看器无 ACCESS_DENIED）
- VC-W-MF-3：Microsoft Teams 新版能发现并打开
- VC-W-MF-4：Edge / Chrome MFCapture 能发现并打开
- VC-W-MF-5：UI 关闭后设备仍持续 30 秒（不变量 I1 完整满足）

## 3. Phase 4 — macOS Camera Extension 上线后追加

> 详见 `docs/phase4/verification-plan.md` 与 `.claude/rules/macos.md`。

| # | 验收项 | 检查方式 | 通过判据 |
|---|---|---|---|
| VC-M-1 | Camera Extension 安装成功 | host app 触发 `OSSystemExtensionRequest` + 用户授权；`systemextensionsctl list` | 列表含 `com.akvc.camera-extension` 状态 `activated`；`log stream` 见 `akvc.ext.provider.start` |
| VC-M-2 | FaceTime 能发现设备 | FaceTime → Video → Camera | 下拉含 `AK Virtual Camera`；预览正常 |
| VC-M-3 | Zoom（macOS）能发现并打开 | Zoom → Settings → Video → Camera | 下拉含 `AK Virtual Camera`；预览正常 |
| VC-M-4 | Safari getUserMedia 能发现并打开 | https://webrtc.github.io/samples/src/content/devices/input-output/ | Video source 下拉含 `AK Virtual Camera`；预览正常 |
| VC-M-5 | OBS（macOS）能发现并打开 | OBS → Sources → Video Capture Device → Device | 下拉含 `AK Virtual Camera`；画面正常 |

### 3.1 Phase 4 风险前置备注

- **沙盒 IPC 风险**：Camera Extension 沙盒是否放行 `shm_open("/akvc-frames-v1")` 是头号未验证风险；被挡则切 XPC + IOSurface（见 `docs/phase4/implementation-plan.md` §2.3）。
- **签名/公证前置**：System Extension 在非调试 Mac 强制 Developer ID 签名 + 公证；调试期 `systemextensionsctl developer on`。
- **时间基红线**：macOS heartbeat 用 `CLOCK_REALTIME` 100ns ticks（Unix epoch），**不是** Windows FILETIME；禁用 `perf_counter`（详见 `macos.md` §4）。
- VC-M-1 及 IPC 自检属纯 API/CLI 项，有 Mac 时 Agent 必须自跑，不允许标 BLOCKED。


## 4. 失败时的 Debug Loop（必须自动执行）

当任一 VC-N 失败：

1. **不允许**直接报告"任务完成 / 部分完成"；必须标 `INCOMPLETE`。
2. 进入 `debugging.md` RCA 流程。
3. 按下表先尝试常见根因；不命中再扩散。

| 失败项 | 优先排查 |
|---|---|
| VC-1 Register | DLL 路径、bitness、签名警告、regsvr32 错误码 |
| VC-2 graphedt | Filter Mapper 是否注册到 Video Capture Sources、CLSID 类目项 |
| VC-3 枚举 | `IFilterMapper2::RegisterFilter` 失败、注册表 InprocServer32 ThreadingModel |
| VC-4 OBS | OBS log 文件、Source Filter 协商出来的 MediaType、frame bus 是否就绪 |
| VC-5 Zoom | Zoom 的"Original ratio"开关、camera permission |
| VC-6 Chrome | Chrome 当前是 DShow 还是 MF 路径（看 `chrome://media-internals/`） |

4. 每次修复都按 `debugging.md` 出 RCA 报告。
5. 修复后**完整重跑**全部 6 条；不允许"我只重跑失败那条"。

## 5. 验收输出格式

```
## Virtual-Camera Acceptance (Phase 2)

| # | Item                              | Status | Evidence |
|---|-----------------------------------|--------|----------|
| VC-1 | Filter registered                | PASS / FAIL / BLOCKED | regsvr32 exit=0; akvc status output |
| VC-2 | GraphStudioNext discovers device | PASS / FAIL / BLOCKED | screenshot @ artefacts/vc2.png |
| VC-3 | ICreateDevEnum lists device      | PASS / FAIL / BLOCKED | dshow_enum.py output |
| VC-4 | OBS picks up device              | PASS / FAIL / BLOCKED | obs-studio log line ...      |
| VC-5 | Zoom picks up device             | PASS / FAIL / BLOCKED | manual screenshot vc5.png    |
| VC-6 | Chrome getUserMedia              | PASS / FAIL / BLOCKED | screenshot vc6.png           |

Result: 6/6 PASS  (or  4/6 PASS, 2 BLOCKED — task INCOMPLETE)
```

## 6. 当 Agent 没有图形/物理环境时

Agent 在沙箱里**无法**亲自打开 OBS / Zoom / Chrome。这种情况下：

- 必须显式标 `BLOCKED`，并提供"用户验证脚本"——即一段用户可一键执行 / 一目了然的命令或操作步骤。
- VC-1 / VC-3 这类纯 API/CLI 类项 **不允许标 BLOCKED**——Agent 必须自己跑通（或通过用户机器指令跑通）。
- 不允许把"无法图形验证" 等同于 PASS。
