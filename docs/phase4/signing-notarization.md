# Phase 4 — macOS Signing & Notarization Runbook

> System Extension 在非调试 Mac 上**必须**签名 + 公证才能加载。
> 本 runbook 假设你已有 Apple Developer 账号与 Developer ID 证书。

## 1. 证书

| 证书 | 用途 |
|---|---|
| **Developer ID Application** | 签名 `.app`（host）与 `.systemextension` |
| **Developer ID Installer** | （可选）打 `.pkg` 安装器 |

在 Keychain Access 中确认证书存在，记下 Team ID（10 位，如 `ABCD1234EF`）。

## 2. 配置 `project.yml` 签名

把两个 target 的签名设置改为：

```yaml
settings:
  base:
    CODE_SIGN_IDENTITY: "Developer ID Application"
    CODE_SIGN_STYLE: Manual
    DEVELOPMENT_TEAM: ABCD1234EF          # 你的 Team ID
    ENABLE_HARDENED_RUNTIME: YES
    CODE_SIGN_INJECT_BASE_ENTITLEMENTS: NO
```

> Camera Extension 的 entitlements（`com.apple.developer.camera-extension`
> 等）需在 Apple Developer 后台为 App ID 启用后才能签上——**VERIFY V-5**。

## 3. 命令行签名（手动，可选）

若不用 Xcode 自动签名：

```bash
# 扩展
codesign --force --deep --options runtime \
  --entitlements virtualcam/macos/CameraExtension/CameraExtension.entitlements \
  --sign "Developer ID Application: <Your Name> (<TEAMID>)" \
  --timestamp \
  build/macos/Build/Products/Release/akvc-camera-extension.systemextension

# Host app（含 embedded extension）
codesign --force --deep --options runtime \
  --entitlements virtualcam/macos/host/HostApp.entitlements \
  --sign "Developer ID Application: <Your Name> (<TEAMID>)" \
  --timestamp \
  build/macos/Build/Products/Release/akvc-host.app
```

`--options runtime` = Hardened Runtime（公证前置条件）。
`--deep` 递归签名嵌入的扩展。

## 4. 公证

```bash
# 打包成 zip 上传（或用 .app 直接传）
ditto -c -k --keepParent build/macos/Build/Products/Release/akvc-host.app akvc-host.zip

xcrun notarytool submit akvc-host.zip \
  --apple-id you@example.com \
  --team-id ABCD1234EF \
  --password <app-specific-password> \
  --wait
```

`--wait` 阻塞直到出结果。成功：`status: Accepted`。
失败用 `xcrun notarytool log <submission-id> ...` 查原因。

App-specific password 在 appleid.apple.com 生成。

## 5. Staple

```bash
xcrun stapler staple build/macos/Build/Products/Release/akvc-host.app
xcrun stapler validate build/macos/Build/Products/Release/akvc-host.app
```

## 6. 安装 / 授权

```bash
# 运行 host app 触发 OSSystemExtensionRequest
open build/macos/Build/Products/Release/akvc-host.app
```

用户需在 **系统设置 → 隐私与安全性** 中：
1. 允许来自开发者的系统扩展。
2. 在 **相机** 中允许 Camera Extension 访问。

或 dev 侧载：
```bash
systemextensionsctl developer on
systemextensionsctl install <TEAMID> com.akvc.camera-extension
```

## 7. 验证签名

```bash
codesign -dv --verbose=4 akvc-host.app
codesign -dv --verbose=4 akvc-camera-extension.systemextension
spctl -a -vvv -t install akvc-host.app   # Gatekeeper 评估
```

## 8. 常见公证失败

| 原因 | 修复 |
|---|---|
| Hardened Runtime 未开 | `ENABLE_HARDENED_RUNTIME=YES` |
| entitlements 含未授权键 | 后台 App ID 启用对应 capability |
| 未 `--timestamp` | 签名加 `--timestamp` |
| 嵌入扩展未签名 | `--deep` 或在 Xcode 里设扩展 target 签名 |
| Python 依赖未签名 | 打包时对 .app 内所有二进制签名（PyInstaller 需额外处理） |
