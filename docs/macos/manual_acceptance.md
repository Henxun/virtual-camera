# macOS 直连路径人工验收

本文只覆盖当前最关键的目标：

- Python 应用可以直接创建对象
- 直接向 macOS 虚拟摄像头发送视频帧
- 不走 helper 热路径

如果你要先处理安装、签名、公证或系统扩展批准，请先看：

- [build.md](/Users/admir/workspace/virtual-camera/docs/macos/build.md)
- [install.md](/Users/admir/workspace/virtual-camera/docs/macos/install.md)
- [signing.md](/Users/admir/workspace/virtual-camera/docs/macos/signing.md)

## 前置条件

1. 已安装最新 [VirtualCamera.pkg](/Users/admir/workspace/virtual-camera/build/macos/VirtualCamera.pkg)
2. 已在系统里批准 Camera Extension
3. 当前宿主进程已拿到 Camera 权限
4. 已构建出 `libakvc-macos-direct-sender.dylib`

建议先确认这些文件存在：

- `build/macos/Build/Products/Release/<your-container-app>.app`
- [build/macos/Build/Products/Release/com.sidus.amaran-desktop.cameraextension.systemextension](/Users/admir/workspace/virtual-camera/build/macos/Build/Products/Release/com.sidus.amaran-desktop.cameraextension.systemextension)
- [build/macos/Build/Products/Release/libakvc-macos-direct-sender.dylib](/Users/admir/workspace/virtual-camera/build/macos/Build/Products/Release/libakvc-macos-direct-sender.dylib)

## 验收 1：纯对象只读探测

先验证最接近 `vcam.mm` 的对象路径：

```bash
python3 tools/make.py direct-sender-object-demo \
  --inspect-only \
  --request-camera-access \
  --output build/macos/direct-sender-object-inspect.json
```

重点看输出 JSON：

- `mode == "direct-sender-object"`
- `python_entrypoint_kind == "MacDirectCameraSender.send(auto-open)"`
- `using_direct_sender == true`
- `helper_hot_path_used == false`
- `shared_memory_fallback_used == false`
- `direct_sender_ready`
- `direct_sender_blocker_code`

理想状态还应满足：

- `direct_sender_ready == true`
- `direct_sender_blocker_code == "ready"`
- `device_snapshot.camera_access_status == "authorized"`
- `device_snapshot.environment_device_enumeration_empty == false`

新版对象 demo 还会额外输出一组聚合后的 SDK 诊断字段：

- `sdk_direct_sender_ready`
- `sdk_direct_sender_blocker_code`
- `sdk_direct_sender_readiness_message`
- `sdk_direct_sender_readiness`

它们不会改变“当前这条命令走的是低层对象直推路径”这个事实，只是把统一 SDK 层已经掌握的安装态 / Gatekeeper / system extension blocker 一并带进同一份 JSON。

如果命令成功但仍显示：

- `camera_access_status == "denied"`
- `environment_device_enumeration_empty == true`

说明当前主要卡在 TCC 权限或系统设备尚未枚举出来，还不适合进入真实推帧验收。

如果 `direct_sender_blocker_code == "camera_access_denied"`，先执行下面的最短修复动作：

1. 打开“系统设置 -> 隐私与安全性 -> 摄像头”
2. 给当前验收宿主进程授权
3. 如果你是直接在终端里跑 `python3 tools/make.py ...`
   - 勾选 `Terminal` / `iTerm`
4. 如果你是从自己的 PySide6 App 内发起验收
   - 勾选你的 `.app`
5. 重新执行“验收 1”的 inspect 命令

只有当 inspect 重新变成：

- `camera_access_status == "authorized"`
- `direct_sender_ready == true`

才值得继续做真实推帧和 QuickTime / Zoom / Meet 可见性验证。

当前这台开发机上，2026-06-30 的真实 inspect 输出已经更新为：

- `camera_access_status == "authorized"`
- `using_direct_sender == true`
- `helper_hot_path_used == false`
- `shared_memory_fallback_used == false`
- 但 `direct_sender_ready == false`
- `direct_sender_blocker_code == "target_device_not_visible"`

这说明当前对象直推路径本身已经不是“权限没拿到”或“退回 helper/shared memory”，而是目标虚拟摄像头仍未真正出现在系统设备列表里。

如果同一份 JSON 里还出现：

- `sdk_direct_sender_blocker_code == "host_notarization_missing"`
- 或 `sdk_direct_sender_blocker_code == "system_extension_not_registered"`

那就说明“目标设备没出现”只是低层现象，真正更靠前的阻塞其实已经被统一 SDK 识别出来了。

## 验收 2：纯对象单帧推送

在只读探测通过后，验证对象路径真实推帧：

```bash
python3 tools/make.py direct-sender-object-demo \
  --frames 1 \
  --output build/macos/direct-sender-object-send.json
```

通过标准：

- 命令退出码为 `0`
- `frames_sent == 1`
- `direct_sender_state == "active"`
- `using_direct_sender == true`
- `helper_hot_path_used == false`
- `shared_memory_fallback_used == false`

如果命令退出码不是 `0`，当前脚本仍会把失败现场写进 `--output`：

- `error`
- `direct_sender_last_error`
- `device_snapshot`
- `failure_report_generated_via_probe`

因此失败时不要只看返回码，也要看生成的 JSON。

如果看到：

- `probe_only == false`
- `failure_report_generated_via_probe == true`

表示这次原本确实尝试了真实推帧，只是为了补齐失败现场，脚本又额外做了一次只读 probe 快照，不代表这次验收只执行了探测。

## 验收 3：统一 SDK 直连路径

确认 `VirtualCamera` 封装层也没有退回 shared memory：

```bash
python3 tools/make.py direct-push-demo \
  --frames 30 \
  --require-direct-runtime \
  --output build/macos/direct-push-report.json
```

通过标准：

- `mode == "direct-push"`
- `using_direct_sender == true`
- `helper_hot_path_used == false`
- `shared_memory_fallback_used == false`
- `runtime_host_in_frame_hot_path == false`

如果这一步失败，但“验收 2”成功，说明问题更可能在统一 SDK 包装层，而不是 native direct sender 本身。

## 验收 4：外部应用最小代码

低层对象路径：

```python
from akvc import MacDirectCameraSender

sender = MacDirectCameraSender(
    width=1280,
    height=720,
    fps=30.0,
    camera_name="AK Virtual Camera",
)
sender.send(frame)
```

统一 SDK 路径：

```python
from akvc.sdk import VirtualCamera

vc = VirtualCamera(width=1280, height=720, fps=30, direct_only=True)
vc.start(name="AK Virtual Camera")
vc.push_frame(frame)
```

建议先在应用里调用：

- `sender.request_camera_access()`
- `sender.available_device_snapshot()`
- `sender.direct_sender_readiness(request_camera_access=True)`

或：

- `vc.request_camera_access()`
- `vc.direct_sender_device_snapshot()`
- `vc.direct_sender_readiness(request_camera_access=True)`

确认当前宿主进程已经能看到 native 设备，再真正开始推帧。

## 验收 5：系统应用可见性

在对象路径或 SDK 直连路径推帧成功后，再做系统侧人工确认：

1. 打开 QuickTime
2. 打开“新建影片录制”
3. 在摄像头列表里确认能看到目标虚拟摄像头

如果 QuickTime 都看不到设备，就先不要跳到 Zoom/Teams/Meet 排查，优先回看：

- `device_snapshot`
- `camera_access_status`
- `environment_device_enumeration_empty`
- Camera Extension 是否真的已批准并完成注册

对于统一 SDK 路径，还建议额外运行一遍：

```python
from akvc.platforms.macos.virtual_camera import MacVirtualCamera
import json

cam = MacVirtualCamera(
    direct_only=True,
    direct_sender_library="build/macos/Build/Products/Release/libakvc-macos-direct-sender.dylib",
    host_bundle="/Applications/<your-container-app>.app",
)
print(json.dumps(cam.direct_sender_readiness(name="AKVC Demo", request_camera_access=True), ensure_ascii=False, indent=2))
```

这样做的原因是：

1. 低层 `MacDirectCameraSender` / `direct-sender-object-demo` 只能直接看到 native 设备快照
2. 如果它只返回：
   - `target_device_not_visible`
   并不能单独说明“Python 直推对象实现有问题”
3. 截至 2026-06-30，统一 SDK 层已经会把这类结果与安装态合并判断
   - 当 direct sender 快照可见系统视频设备、但目标虚拟摄像头缺席
   - 且安装态已经能证明目标 container app 仍被 Gatekeeper 拒绝
   - `direct_sender_readiness()` 会进一步把 blocker 提升为：
     - `host_notarization_missing`
     - 或 `system_extension_not_registered`
4. 在当前这台开发机上，真实高层 readiness 输出已经收敛到：
   - `blocker_code == "host_notarization_missing"`
   - `installer_blocker_code == "host_notarization_missing"`
   - `direct_sender_blocker_code == "target_device_not_visible"`
   - `system_extension_registered == false`

这比单纯看到“目标设备还没出现”更贴近真实系统前置门槛。

## 当前已知外部阻塞

当前这台开发机上，2026-06-30 的最新真实外部阻塞已经收敛为：

1. `camera_access_status == "authorized"`
2. 但 `/Applications/<your-container-app>.app` 仍是 `Unnotarized Developer ID`
3. `syspolicy_check distribution /Applications/<your-container-app>.app` 仍会报 `Notary Ticket Missing`
4. 因此统一 SDK 层 readiness 会把对象直推 blocker 提升为：
   - `host_notarization_missing`
   而不是继续停留在：
   - `camera_access_denied`
   - 或泛化的 `target_device_not_visible`

另外，截至 2026-06-30 的最新现场里，还确认了两条容易混淆人工验收结论的事实：

1. 在仓库根目录里直接运行 `build/macos/Build/Products/Release/akvc-macos-status`
   - 默认更容易绑定到 build tree 里的 legacy `akvc-host.app` 或当前构建产物
   - 这不等于 `/Applications/<your-container-app>.app` 的真实安装态
   - 如果你想明确查看已安装宿主，请显式带上：
     `AKVC_HOST_APP_BUNDLE=/Applications/<your-container-app>.app`
2. 当前 `akvc-macos-install` / `akvc-macos-uninstall` 原生入口已经补上：
   - 先尝试拉起已解析出的 container app
   - 如果该路径没有让状态收敛，再继续在当前进程里直接提交 `OSSystemExtensionRequest`
   所以如果后续仍看到安装命令被直接 `killed`，优先把问题归因到 Gatekeeper / notarization / 系统策略，而不是“install tool 还强依赖 helper 热路径”

这两类问题都会导致：

- 对象 demo 返回非零退出码
- 但 JSON 里仍会保留 `direct_sender_last_error` 和最新 snapshot

这属于系统权限/运行环境问题，不等同于“Python 对象路径仍在走 helper”。
