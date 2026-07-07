---
name: macos-camera-extension-repair
description: 诊断并修复 macOS CMIO 相机 System Extension 的激活失败问题。适用于任意 macOS 应用内嵌 `.systemextension` 相机扩展但激活失败、系统设置里“通用 > 登录项与扩展 > 相机扩展”的开关无法启用、宿主应用错误地提示 `/Applications` 路径问题，或者需要排查 bundle ID、App Group、mach service、签名、provisioning、sysext 状态及授权规则相关问题的场景。
---

# macOS 相机扩展修复

## 概览

使用这个 skill 可以端到端排查 macOS 相机扩展问题，包括应用侧发起激活请求、内嵌 system extension 的打包、签名与 provisioning、系统设置中的审批流程，以及最终 `sysextd` 的状态变化。

建议按工作流顺序排查。大多数失败都落在五类原因里：应用错误提示误导、标识符不一致、签名或 provisioning 问题、旧的 system extension 残留状态、或者本机授权规则损坏。

## 快速排查

优先执行下面几个检查：

```bash
systemextensionsctl list
```

```bash
log show --style compact --last 10m --predicate '(process == "sysextd" OR process == "System Settings" OR subsystem == "com.apple.systemextensions")'
```

```bash
security authorizationdb read com.apple.system-extensions.admin
```

常见状态可以这样理解：

- `activated waiting for user`：打包和签名基本通过了，但用户授权流程或本地权限规则挡住了启用。
- `activated enabled`：扩展已经运行，激活成功。
- `terminated waiting to uninstall on reboot`：旧扩展残留，通常要重启后才能完全清掉。

## 排查流程

### 1. 先修正应用侧的报错展示

不要直接相信类似 “run this app from inside /Applications” 这种泛化提示。

在应用的 `OSSystemExtensionRequestDelegate.request(_:didFailWithError:)` 回调里：
- 展示真实的 `NSError` domain、code 和 localized description。
- 只有当 `Bundle.main.bundleURL.path` 确实不在 `/Applications` 下时，才显示 `/Applications` 的提示。

这样可以避免把无关问题误判成启动路径错误。

### 2. 核对标识符是否一致

确认下面这些值属于同一套命名体系：
- app bundle ID
- extension bundle ID
- 内嵌 system extension 的产物路径和名称
- Xcode target / scheme / 产物名称
- app 侧 entitlements 里的 app group
- extension 侧 entitlements 里的 app group
- `CMIOExtensionMachServiceName`

可以用下面这些方式检查：

```bash
rg -n "PRODUCT_BUNDLE_IDENTIFIER|application-groups|CMIOExtensionMachServiceName" /path/to/project
plutil -p path/to/Info.plist
plutil -p path/to/*.entitlements
```

关键规则：
- `CMIOExtensionMachServiceName` 必须以前述 extension 的某个 app group 为前缀。
- 实测可行的模式是 `group.<app-group-suffix>.cameraextension`。

如果日志提示 mach service 无效，或者没有以 app group 为前缀，先修这个，再继续做别的排查。

### 3. 必要时使用新的 DerivedData 路径重新构建

如果命令行构建因为现有 `DerivedData` 不可写而失败，改用一个临时路径：

```bash
xcodebuild -project /path/to/YourProject.xcodeproj \
  -scheme YourHostAppScheme \
  -configuration Debug \
  -derivedDataPath /private/tmp/cameraextension-deriveddata \
  -allowProvisioningUpdates \
  build
```

如果自动签名需要为新的 bundle ID 创建或更新 provisioning profile，就加上 `-allowProvisioningUpdates`。

### 4. 验证构建产物，不要只看源码

构建完成后，直接检查生成出来的 app 和其中内嵌的 extension：

```bash
plutil -p /path/to/YourHostApp.app/Contents/Info.plist
plutil -p /path/to/YourHostApp.app/Contents/Library/SystemExtensions/*.systemextension/Contents/Info.plist
codesign -d --entitlements :- /path/to/YourHostApp.app
codesign -d --entitlements :- /path/to/YourHostApp.app/Contents/Library/SystemExtensions/*.systemextension
```

不要默认源码改动一定已经进到最终 app 里，必须直接验证构建产物。

### 5. 放到 `/Applications` 里安装并测试

本地测试时，把签好名的宿主 app 复制到 `/Applications`，再从那里启动：

```bash
ditto /path/to/built/YourHostApp.app /Applications/YourHostApp.app
open -na /Applications/YourHostApp.app
```

然后点击应用里的 `activate` 按钮，并打开：
- `System Settings > General > Login Items & Extensions > Camera Extensions`

如果 UI 自动化或系统缓存还在使用旧的 bundle/path 元数据，调试时可以试着换一个新名字的测试副本，帮助隔离缓存问题。

### 6. 结合 `systemextensionsctl` 和日志给故障分类

最有价值的检查通常是：

```bash
systemextensionsctl list
```

```bash
/usr/bin/log show --style compact --last 5m --predicate 'subsystem == "com.apple.systemextensions" OR process == "sysextd" OR eventMessage CONTAINS[c] "system extension"'
```

常见判断方式：
- `activated waiting for user` 且没有校验错误：下一步重点怀疑授权或审批链路。
- `activated enabled`：说明已经成功。
- 如果校验错误提到 mach service、entitlements 或 bundle ID：先修打包和配置问题。

### 7. 如果相机扩展开关点了立刻失败，检查管理员授权规则

这是非常关键、也很容易被忽略的一类故障。

先读取当前生效的规则：

```bash
security authorizationdb read com.apple.system-extensions.admin
```

再读取系统内置默认值：

```bash
plutil -p /System/Library/Security/authorization.plist | sed -n '460,490p'
```

期望的默认值：
- `authenticate-admin-nonshared`

异常的当前值：
- `is-root`

如果当前规则是 `is-root`，系统设置在启用时可能会出现下面这些特征：
- `authd` 在 `com.apple.system-extensions.admin` 上失败
- 报错 `-60005`（`errAuthorizationDenied`）
- 不会弹出正常的管理员密码确认框

这种情况下，即使代码、签名和 entitlement 全都正确，扩展仍然无法启用。

### 8. 修复损坏的授权规则前，必须先得到用户明确确认

这一步会持久修改本机 macOS 的授权策略，不能静默执行。

在用户明确同意后，可以把默认规则写回去，例如：

```bash
security authorizationdb write com.apple.system-extensions.admin < fixed-rule.plist
```

一个最小可用的恢复规则示例如下：

```xml
<dict>
  <key>class</key>
  <string>rule</string>
  <key>comment</key>
  <string>Authorize a 3rd party application which wants to manipulate system extensions.</string>
  <key>rule</key>
  <string>authenticate-admin-nonshared</string>
  <key>shared</key>
  <false/>
</dict>
```

恢复后，再次尝试启用 Camera Extensions 开关。之前卡住的扩展通常会从下面这个状态链路继续往前走：
- `activated_waiting_for_user`
- 到 `activated_enabling`
- 再到 `activated_enabled`

### 9. 测试完成后清理旧扩展残留

可以使用：

```bash
systemextensionsctl uninstall <TEAM_ID> <BUNDLE_ID>
```

如果系统显示 `terminated waiting to uninstall on reboot`，通常需要重启后才能彻底移除旧扩展。

## 完成标准

只有同时满足下面两点，才能认为修复完成：
- `systemextensionsctl list` 显示目标扩展为 `activated enabled`
- 宿主应用能够发现对应的 CMIO sink/source stream，或者用其他方式确认扩展已经正常工作
