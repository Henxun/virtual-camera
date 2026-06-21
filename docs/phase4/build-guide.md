# Phase 4 — macOS Build Guide

> 需 macOS 12.3+ / Xcode 14+。当前环境无 Mac，本文为 runbook。

## 1. 工具要求

| 工具 | 版本 | 用途 |
|---|---|---|
| macOS | 12.3+ | Camera Extension 最低版本 |
| Xcode | 14+ | Swift 5.9、System Extension target |
| XcodeGen | latest | `project.yml` → `.xcodeproj` |
| Python | 3.12.x | 桌面应用 / 生产者 |
| Apple Developer ID | Application + Installer | 签名/公证（调试期可免） |

```bash
brew install xcodegen
```

## 2. 生成工程

```bash
cd virtualcam/macos
xcodegen generate          # 生成 akvc-macos.xcodeproj
```

或从仓库根：

```bash
uv run tools/make.py configure
```

`project.yml` 定义两个 target：
- `akvc-camera-extension`（system-extension）—— Camera Extension 本体
- `akvc-host`（application）—— 激活扩展的 host app

`HEADER_SEARCH_PATHS` 含 `framebus/include` 与 `virtualcam/shared`，使
Swift bridging header 能找到 `akvc/framebus_posix.h`、`akvc_protocol.h`、
`akvc_errors.h`。

## 3. 构建

```bash
# 仅扩展（dev，未签名）
xcodebuild -project akvc-macos.xcodeproj \
  -scheme akvc-camera-extension \
  -configuration Release \
  -derivedDataPath ../../build/macos \
  build

# 或
uv run tools/make.py build
```

产物：`build/macos/Build/Products/Release/akvc-camera-extension.systemextension`

调试期免签名：`project.yml` 设 `CODE_SIGN_IDENTITY="-"`，并：
```bash
systemextensionsctl developer on   # 一次性，允许未签名 dev 构建
```

## 4. 常见构建错误

| 错误 | 原因 | 修复 |
|---|---|---|
| `Cannot find 'akvc_fb_open' in scope` | bridging header 未生效 | 确认 `SWIFT_OBJC_BRIDGING_HEADER` 指向 `CameraExtension/CameraExtension-Bridging-Header.h`，且 `HEADER_SEARCH_PATHS` 含 `framebus/include` |
| `Unknown extension point com.apple.coremediaio.extension` | Info.plist V-4 未核对 | 对照 Apple sample 修 `NSExtensionPointIdentifier` |
| `System Extension target not supported` | Xcode 太旧 | 升级 Xcode ≥ 14 |
| `framebus_posix.c: sys/mman.h not found` | 在非 Mac 上编译 | 必须在 macOS 上构建 |

## 5. 下一步

构建通过后，按 `signing-notarization.md` 签名公证，再按
`run-debug-guide.md` 加载调试。
