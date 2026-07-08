# Plan — 纯 C++/OC 控制层重构

## 目标（一句话）
把"控制虚拟摄像头"这层从 Python(`akvc/sdk`) + pybind11 核心重写为**纯 C++/OC 库**（C++ 类 API = 第三方主接口），额外提供薄 pybind11 绑定给 `apps/desktop`；`virtualcam/` 驱动层不变；控制层**不含安装内容**；Windows + macOS 都做。

## 用户已拍板的 4 个决策
1. **Python 去留**：删 `akvc/` 包 + `apps/cli`；**保留** `apps/desktop`(PySide6)，通过新 pybind11 绑定消费 C++ 库。
2. **安装边界**：Windows `start()` 拉起 helper 守护进程（运行时）但**不**注册 MF；macOS `start()` 调 `OSSystemExtensionRequest activationRequestForExtension`。
3. **对外接口**：C++ 类 API（第三方主接口）+ 额外 pybind11 Python 绑定。
4. **节奏**：Windows + macOS 一次性都做（macOS 验收本环境 BLOCKED + 用户脚本）。
5. **补充**：macOS 控制参考 `E:\source\cameraextension\cameraextension\vcam.mm`（CMIO sink-stream 队列注入）。

## Exploration 结论（现状事实）

### 可直接复用（已纯 C/C++/ObjC，无 Python）
- `virtualcam/windows/framebus/` — `akvc::FrameBusProducer/Consumer`（纯 Win32 C++，`publish(header, plane_data[2])` 本就吃 `uint8_t*`）
- `virtualcam/shared/akvc_protocol.h`、`akvc_errors.h` — 纯 C ABI 线协议
- `virtualcam/macos/direct_sender/AKVCDirectCameraSender.mm` — `DirectSender` 类**已是 vcam.mm 的 CMIO sink-queue 注入实现**（纯 ObjC++，C ABI `akvc_macos_direct_sender_*`，吃 `uint8_t*`，BGR24/BGRA32，含队列容量管理/丢旧帧）
- `virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm` — `AKVCSubmitSystemExtensionRequest(activate, timeout, &err)`（纯 ObjC）
- DShow/MF/helper 三个原生目标

### 需重写（pybind11/numpy 耦合）
- `camera-core/native/include/.../frame_types.h` 的 `Frame`（持 `py::array`）→ 裸 `uint8_t*` 视图
- `pipeline_ops.cpp`（`resize_rgb24_frame`/`rgb24_to_nv12_frame`，用 `py::array.unchecked`）→ 裸 buffer
- `sinks/windows_framebus.cpp` `NativeWindowsFrameBusProducer`（`py::array`/`py::value_error`）→ `uint8_t*`，底层 `FrameBusProducer::publish` 不变
- `helper/windows_helper_client.cpp` `NativeWindowsHelperClient`（`py::str`/`py::dict`）→ 去 py 类型；**拆分**：保留运行时 `ping/status/launch/start_service/ensure_running/is_process_elevated`，**移除** `register_mf/unregister_mf/install_autostart/uninstall_autostart/scheduled_task_status/status_summary`（安装，排除）
- `virtual_camera_session.cpp` `NativeVirtualCameraSession`（`py::object` 编排 + `start()` 调 `register_mf`）→ 直接编排 C++ 对象；`start()` 不再注册

### 删除
- `akvc/`（整个 Python 包：sdk/distribution/runtime/windows_runtime/helper_service/_runtime/_core_native.pyd）
- `apps/cli/`
- `camera-core/build/`（旧拷贝）、根 `akvc_core.egg-info`、`amaranth_virtual_camera.egg-info`
- 根 `pyproject.toml` 的 `akvc*` 打包配置 / `setup.py`（Python 包发布）
- `akvc/__init__.py:20` 死引用（随包删除）

## 目标架构
```
virtualcam/                     原生驱动层（不变）
  windows/{dshow,mf,framebus,helper}/   C++
  macos/{camera_extension,direct_sender,control_bridge,ipc,...}/  ObjC/C++
  shared/akvc_protocol.h, akvc_errors.h

camera-core/                    控制层 = 给第三方的 C++ 库
  include/akvc/                 公开 C++ API（第三方 include + link）
    virtual_camera.h            VirtualCamera 类
    frame_input.h               FrameInput {data,w,h,stride,format,pts}
    pixel_format.h              enum PixelFormat
    status.h                    enum Status + last_error
  src/
    virtual_camera.cpp          门面，平台派发
    pipeline_ops.cpp            裸 buffer resize / BGR→NV12 / BGR→BGRA
    platform/windows/
      windows_session.cpp       start=ensure helper+open shm; push=resize→NV12→publish
      helper_client_runtime.cpp 仅运行时控制（ping/status/launch/ensure_running）
      framebus_producer.cpp     包装 akvc::FrameBusProducer，吃 uint8_t*
    platform/macos/
      macos_session.mm          start=OSSystemExtensionRequest activate + DirectSender.start
      direct_sender_bridge.mm   复用 DirectSender（C ABI）
      system_extension_bridge.mm 复用 AKVCSubmitSystemExtensionRequest
  bindings/python/              薄 pybind11 绑定（仅 apps/desktop）
    module.cpp                  暴露 VirtualCamera（push_frame 吃 numpy）
  tests/                        GoogleTest + CTest
  CMakeLists.txt                akvc_camera 库 + akvc_camera_python 绑定 + tests

apps/desktop/  保留             PySide6，改用 akvc_camera 绑定
apps/cli/      删除
akvc/          删除
```

## 公开 C++ API（草案）
```cpp
namespace akvc {
enum class PixelFormat : uint32_t { BGR24, BGRA32, RGB24, NV12 };
struct FrameInput {
  const uint8_t* data; int width, height, stride;
  PixelFormat format; uint64_t pts_100ns;  // 0=host clock
};
enum class Status { Ok, NotStarted, DeviceNotFound, HelperUnavailable,
                    ShmUnavailable, InvalidFrame, ExtensionActivationFailed,
                    StreamStartFailed, Unknown };
class VirtualCamera {
public:
  VirtualCamera(int width, int height, double fps,
                std::string camera_name = "AK Virtual Camera");
  ~VirtualCamera();
  Status start();                 // Win: helper+shm; macOS: ext activate+CMIO sink
  Status push_frame(const FrameInput&);
  void stop();
  bool started() const;
  int  consumer_count() const;
  const char* last_error() const;
};
}  // namespace akvc
```
第三方：`#include <akvc/virtual_camera.h>` + link `akvc_camera`。
apps/desktop：`import akvc_camera`（pybind11）。

## start() 语义（按决策 2 + vcam.mm 参考）
- **Windows**：`start()` = `helper_client_runtime.ensure_running(helper_exe)`（拉起守护进程，运行时）→ `framebus_producer.open_existing()`（失败按 `AKVC_ALLOW_FRAMEBUS_CREATE_FALLBACK` env 回退 create）→ started。**不**调 register_mf。MF 注册由独立安装步骤承担（本层不负责）。
- **macOS**：`start()` = 先 `AKVCQuerySystemExtensionStatus`（已 enabled 则跳过，避免反复弹框）→ 否则 `AKVCSubmitSystemExtensionRequest(activate=YES, timeout)` → `DirectSender.start(camera_name)`（CMIO sink 注入，vcam.mm 路径）。

## 实施里程碑（每个走 Build→Run→Test 闸，≤20 循环）
- **M1** C++ 核心类型与算法（裸 buffer）：`frame_input.h`、`pipeline_ops`（resize/bgr→nv12/bgr→bgra）+ GoogleTest
- **M2** Windows 控制层：`helper_client_runtime`（拆运行时）、`framebus_producer`（uint8_t*）、`windows_session`；CMake `akvc_camera`(Win)
- **M3** macOS 控制层：`macos_session.mm`（复用 DirectSender + AKVCSubmitSystemExtensionRequest）；CMake `akvc_camera`(macOS ObjC++)
- **M4** `VirtualCamera` 门面 + 跨平台编译：Win+macOS 都编出 `akvc_camera`
- **M5** pybind11 薄绑定：`bindings/python/module.cpp`；CMake `akvc_camera_python`
- **M6** apps/desktop 迁移：`facade/frame_worker/helper_service` 改用 `akvc_camera` 绑定；删 `akvc.sdk` 依赖
- **M7** 删 Python 残留：`akvc/`、`apps/cli`、`camera-core/build`、egg-info、死引用；更新 `pyproject`/`make.py`
- **M8** 验收：Windows VC-1..6；macOS BLOCKED + 用户脚本

## 构建系统
- 根 `CMakeLists.txt`：`add_subdirectory(camera-core)`（替代 `camera-core/native` 的 pybind 模块）
- `camera-core/CMakeLists.txt`：
  - `akvc_camera` 静态/动态库（`src/*.cpp/*.mm`），公开 `include/akvc`
  - `akvc_camera_python` pybind11 模块（`bindings/python`）
  - `akvc_camera_tests` GoogleTest + CTest
  - 链接：Win `akvc_framebus`/advapi32/shell32/mf*；macOS CoreMedia/CoreMediaIO/CoreVideo/AVFoundation/SystemExtensions
- `tools/make.py`：`build` 编 `akvc_camera`+绑定；`test` 加 CTest；移除 Python 包打包；`register` 保留（安装，独立于控制层）

## 测试策略
- C++ 单测：GoogleTest（frame/pipeline_ops、helper client mock、producer 协议、status 矩阵）
- 集成：C++ demo exe（推 test pattern → `dshow_enum.py` 验证帧到达）= Run 闸
- 桌面 pytest：保留 `test_desktop_main_vm/main_window`（改用绑定后调整）
- 删除针对 `akvc.sdk`/`akvc_cli` 的 pytest（`test_cli_*`/`test_distribution`/`test_frame_input` 等随包删）

## 验收映射（acceptance.md 四闸 + virtual-camera.md）
| Gate | Windows | macOS |
|---|---|---|
| Build | `make.py build` → `akvc_camera.lib`+`akvc_camera_python.pyd`+DShow/MF/helper dll | 同（.dylib + 绑定） |
| Run | C++ demo exe 推图→dshow_enum 见帧；desktop 主窗口 | BLOCKED(无 Mac) |
| Tests | GoogleTest 全绿 + desktop pytest 全绿 | C++ 单测 BLOCKED |
| Acceptance | VC-1/VC-3 Agent 自跑；VC-2/4/5/6 BLOCKED+用户脚本 | VC-M-1..5 BLOCKED+用户脚本 |

## 风险
- **R1（头号）Windows Global shm ACL**：非 elevated 第三方 app 可能无写权限（SDDL 仅 BA/SY/AC/ALL_APP_PACKAGES）。缓解：M2 验证 ACL；必要时控制层走"helper 持有 shm，app 经 helper pipe 推帧"或要求 app elevated。
- **R2 macOS OSSystemExtensionRequest 频繁弹框**：缓解：start() 先查 status，已 enabled 跳过激活。
- **R3 pybind11 ABI**：apps/desktop 需与 akvc_camera 同 Python/MSVC 运行库；同 CMake 一次构建。
- **R4 macOS 无 Mac**：macOS 闸全 BLOCKED + 用户验证脚本。
- **R5 删除 akvc/ 影响面**：apps/desktop 大量 `import akvc.*`；M6 全量迁移 + 跑 desktop pytest。

## RULE-OVERRIDE 标注
- 决策 2 macOS `start()` 调 `OSSystemExtensionRequest`：CLAUDE.md §4 将其列为"必须人工授权"动作。用户已在本设计决策中**显式授权该设计**；运行期真机执行仍走系统授权弹窗。特此标注（非偏离，为已授权设计）。

## 不做（out of scope，另立任务）
- 安装/注册工具（regsvr32、MFRegisterVirtualCamera、schtasks autostart、macOS .pkg 安装器）
- iOS、32-bit、DShow 之外 Windows 旧通路
- C ABI 对外接口（首版只做 C++ 类 API + pybind11；C ABI 后续按需加）
