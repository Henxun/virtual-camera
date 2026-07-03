# macOS 签名与公证说明

## 1. 目标

本文件定义 macOS Camera Extension 路径下的签名、公证与交付要求。

## 2. 需要签名的对象

1. 原生动态库与可执行文件
2. Helper / launcher
3. System Extension
4. Container App
5. 最终 Installer 包

## 3. 核心要求

1. 使用有效的 Apple Developer ID 证书
2. 使用正确的 entitlements
3. 完成 notarization
4. 完成 `staple`

当前代码树里的最小 entitlement 策略是：

1. container app（当前 legacy target 仍可能显示为 `akvc-host.app`）
   - 只保留 `com.apple.developer.system-extension.install`
2. `com.sidus.amaran-desktop.cameraextension.systemextension`
   - 当前默认使用空 entitlement
3. `akvc-macos-install` / `akvc-macos-uninstall`
   - 不再直接提交 `OSSystemExtensionRequest`
   - 只负责拉起 Host 并轮询状态，因此按普通 Developer ID CLI 签名，不再复用 Host 的受限 entitlement

这样做的原因是：在 2026-06-30 的真实 Developer ID 签名实验里，旧的
`app-sandbox + application-groups` 组合会让 `codesign -d --entitlements :- ...`
输出 `invalid entitlements blob`，而最小集合不会。

补充说明：container app 一旦携带 `com.apple.developer.system-extension.install`，在标准分发态下通常还需要匹配的 macOS provisioning profile。否则即使 `codesign --verify` 通过，AMFI 仍可能因为 restricted entitlement 缺少 profile 而直接拒绝启动。legacy target 如果仍叫 `akvc-host.app`，也适用同一条规则。

## 4. 建议签名顺序

1. 签底层原生组件
2. 签 System Extension
3. 签 Container App
4. 构建 Installer
5. 签 Installer
6. notarize
7. staple

## 5. 常见失败点

1. entitlement 不匹配
2. Bundle 层级错误
3. 签名顺序错误
4. Team ID 不一致
5. 未启用 Hardened Runtime
6. 为当前分发模型附加了并不需要的 `app-sandbox / application-groups`

## 6. 自动化要求

CI/CD 中需要：

1. 安全管理证书
2. 安全管理 notarization 凭据
3. 在签名后执行结构校验
4. 在公证后执行 smoke test

当前仓库已补齐发布脚本骨架：

1. `installer/macos/sign_app.sh`
2. `installer/macos/build_pkg.sh`
3. `installer/macos/build_dmg.sh`
4. `installer/macos/build_zip.sh`
5. `installer/macos/notarize.sh`
6. `installer/macos/staple.sh`

当前建议在签名/公证前先执行：

1. `python3 tools/make.py preflight`
2. 先执行 `python3 tools/make.py build` 完成无签名编译
3. 确认 `SIGN_IDENTITY` 已配置
4. 执行 `python3 tools/make.py sign`
5. 确认 `PRODUCTSIGN_IDENTITY` 已配置
6. 执行 `python3 tools/make.py package`
7. 确认 `NOTARY_PROFILE` 已配置
8. 执行 `python3 tools/make.py notarize`
9. 执行 `python3 tools/make.py staple`

如果不想先导出 shell 环境变量，当前也可以直接在命令里传：

1. `python3 tools/make.py notarize --notary-profile <你的 profile 名>`

当前 `notarize` / `staple` 的默认语义已从“只处理 pkg”提升为“优先处理宿主 app，再处理 pkg”：

1. `notarize.sh`
   - 默认 `NOTARIZE_TARGETS=app,pkg`
   - 会先把 container app 临时打成 zip 提交 `notarytool`
   - 再继续提交 `VirtualCamera.pkg`
2. `staple.sh`
   - 默认 `STAPLE_TARGETS=app,pkg`
   - 会先对 container app 执行 `stapler staple/validate`
   - 再继续对 `VirtualCamera.pkg` 执行 `stapler staple/validate`

这样做的原因是：仅对 `pkg` 公证并不足以解释“安装后 `/Applications/<your-container-app>.app` 启动仍被 Gatekeeper 直接 `killed`”这类问题；container app 本身也需要进入公证/贴票据闭环。

另外，当前 Python SDK / CLI 的自动安装控制面默认还会直接调用 runtime 内的 `akvc-macos-install`。如果这个命令行工具本身仍是 `Unnotarized Developer ID`，那么即使 container app 已经在 `/Applications`，安装请求也可能在真正触发前就被 Gatekeeper 杀掉。因此排查签名/公证问题时，不能只看 container app，也要一起检查 `akvc-macos-install`、`akvc-macos-uninstall`、`akvc-macos-status` 等 runtime 工具。

当前环境变量约定：

1. `SIGN_IDENTITY`
   - Host App 与 Camera Extension 的 Developer ID Application 签名身份
2. `PRODUCTSIGN_IDENTITY`
   - `VirtualCamera.pkg` 的 Developer ID Installer 签名身份
3. `NOTARY_PROFILE`
   - `xcrun notarytool` 使用的 keychain profile 名称
4. `HOST_PROVISIONING_PROFILE`
   - container app 对应的 macOS provisioning profile 路径
5. `EXTENSION_PROVISIONING_PROFILE`
   - `com.sidus.amaran-desktop.cameraextension.systemextension` 对应的 macOS provisioning profile 路径

如果 `SIGN_IDENTITY` / `PRODUCTSIGN_IDENTITY` 没有显式设置，当前脚本还会尝试直接从当前钥匙串自动发现：

1. `sign_app.sh`
   - 优先查找首个可用 `Developer ID Application: ...`
2. `build_pkg.sh`
   - 优先查找首个可用 `Developer ID Installer: ...`

因此在“证书已导入登录钥匙串，但还没导出环境变量”的机器上，`python3 tools/make.py sign` / `package` 现在通常也能直接工作；`NOTARY_PROFILE` 仍需显式配置。
但如果系统日志已经出现 `No matching profile found` 或 `Code has restricted entitlements`，则还需要显式提供：

1. `HOST_PROVISIONING_PROFILE`
2. `EXTENSION_PROVISIONING_PROFILE`

`installer/macos/sign_app.sh` 会在真正签名前把这些 profile 嵌入到：

1. `container-app.app/Contents/embedded.provisionprofile`
2. `com.sidus.amaran-desktop.cameraextension.systemextension/Contents/embedded.provisionprofile`
3. `container-app.app/Contents/Library/SystemExtensions/com.sidus.amaran-desktop.cameraextension.systemextension/Contents/embedded.provisionprofile`

补充说明：

1. 如果你是在受限执行环境里运行 `python3 tools/make.py preflight`
   - 可能会看到 `sign_identity_effective=false`
   - `productsign_identity_effective=false`
   - 这不一定代表证书真的没装
2. 截至 2026-06-30 的真实验证里，受限环境中的：
   - `security find-identity -v -p codesigning`
   - `security find-identity -v -p basic`
   都可能返回 `0 valid identities found`
3. 但在本机正常终端或非受限环境里重新执行同样命令，可正常看到：
   - `Developer ID Application: Sidus Link Ltd. (XP3H66JF79)`
   - `Developer ID Installer: Sidus Link Ltd. (XP3H66JF79)`
4. 因此如果 `preflight` 与钥匙串里的实际证书状态不一致，优先在本机正常终端复核 `security find-identity`，不要直接把它理解成“证书安装失败”

截至 2026-06-30，本项目在真实 macOS 环境里已再次验证：

1. `python3 tools/make.py sign`
   - 可自动发现 `Developer ID Application: Sidus Link Ltd. (XP3H66JF79)`
   - 可成功签名 container app、`com.sidus.amaran-desktop.cameraextension.systemextension`、`akvc-macos-install/status/uninstall/list-devices/sync-ipc` 与 `libakvc-macos-direct-sender.dylib`
2. `python3 tools/make.py package --skip-build --sync-runtime`
   - 可自动发现 `Developer ID Installer: Sidus Link Ltd. (XP3H66JF79)`
   - 可成功生成并签名 `build/macos/VirtualCamera.pkg`
   - 可继续生成 `build/macos/VirtualCamera.dmg` 与 `build/macos/VirtualCamera.zip`
3. 在尚未配置 `NOTARY_PROFILE` 的前提下，`release-diagnostics` 的预期结果是：
   - `app_signed=true`
   - `command_tools_signed=true`
   - `pkg_signed=true`
   - 但 `app_gatekeeper_accepted=false`
   - `pkg_gatekeeper_accepted=false`
   - `app_stapled=false`
   - `pkg_stapled=false`
   - 并出现 `source=Unnotarized Developer ID` / `Notary Ticket Missing`

4. 对同一份 Host / Extension 产物做过临时 A/B 重签验证：
   - 旧的 `app-sandbox + application-groups` entitlement 组合会触发
     `invalid entitlements blob`
   - Host 只保留 `com.apple.developer.system-extension.install`
   - Extension 使用空 entitlement
   - 上述 warning 会消失
5. 对安装到 `/Applications` 的 Host 做过真实启动策略验证：
   - `codesign --verify --deep --strict /Applications/<your-container-app>.app`
     通过
   - `spctl -a -vvv /Applications/<your-container-app>.app`
     会显示 `source=Unnotarized Developer ID`
   - `syspolicy_check distribution /Applications/<your-container-app>.app`
     会直接报 `Notary Ticket Missing`
   - 此时 `open -n -a /Applications/<your-container-app>.app --args --activate`
     仍可能被系统直接 `killed`
   - 这说明“Developer ID 签名已完成”并不等价于“可以直接开始标准分发态人工验收”

这意味着“签名链已打通”与“可直接人工验收分发态行为”是两件事：前者现在已具备，后者仍需要 `notarize + staple`，或者走下面的开发态绕行方式。

如果当前只是想先做开发机人工验收，而不是正式分发验收，可临时走下面这条开发态路径：

1. 只在开发机执行 `systemextensionsctl developer on`
2. 对本地待验证产物移除隔离属性
   - `xattr -dr com.apple.quarantine /Applications/<your-container-app>.app`
   - 如果你验证的是 build tree 产物，也一起执行：
     `xattr -dr com.apple.quarantine build/macos/Build/Products/Release/<your-container-app>.app build/macos/Build/Products/Release/akvc-macos-install`
3. 在 Finder 中对目标 container app 执行一次“右键 -> 打开”
4. 再运行：
   - `python3 tools/make.py smoke --name "AKVC Demo" --run-install --host-bundle /Applications/<your-container-app>.app --disable-auto-package`
5. 如果这一步仍失败，再回到标准分发路径补齐：
   - `python3 tools/make.py notarize --notary-profile <你的 profile 名>`
   - `python3 tools/make.py staple --targets app,pkg`

补充说明：

1. 如果你是直接验证 build tree 产物，而不是 `/Applications` 里的安装版本，当前更推荐使用 `Apple Development` 身份对 build tree 重新签名，再配合：
   - `systemextensionsctl developer on`
   - `xattr -dr com.apple.quarantine build/macos/Build/Products/Release/<your-container-app>.app build/macos/Build/Products/Release/akvc-macos-install`
2. 当前 Python 安装态诊断在识别到：
   - `bundle_path` 位于 `build/.../<your-container-app>.app` 或 legacy `akvc-host.app`
   - 签名链呈现 `Apple Development`
   - 启动错误接近 `Launch failed`
   时，会优先提示“开发机需要开启 system extension developer mode”，而不是继续把问题归类成正式分发公证缺失。

推荐先用以下命令逐项确认：

1. `python3 tools/make.py preflight`
2. `codesign -dv --verbose=4 build/macos/Build/Products/Release/<your-container-app>.app`
3. `codesign -dv --verbose=4 build/macos/Build/Products/Release/com.sidus.amaran-desktop.cameraextension.systemextension`
4. `pkgutil --check-signature build/macos/VirtualCamera.pkg`
5. `spctl -a -vvv -t install build/macos/VirtualCamera.pkg`
6. `spctl -a -vvv build/macos/Build/Products/Release/<your-container-app>.app`
7. `xcrun stapler validate build/macos/Build/Products/Release/<your-container-app>.app`
8. `spctl -a -vvv build/macos/Build/Products/Release/akvc-macos-install`
9. `syspolicy_check distribution build/macos/Build/Products/Release/akvc-macos-install`

如果需要显式控制要处理的发布物，也可以直接用：

1. `python3 tools/make.py notarize --targets app,pkg`
2. `python3 tools/make.py staple --targets app,pkg`
3. `python3 tools/make.py notarize --app-bundle /path/to/<your-container-app>.app --pkg-path /path/to/VirtualCamera.pkg`
4. `python3 tools/make.py staple --app-bundle /path/to/<your-container-app>.app --pkg-path /path/to/VirtualCamera.pkg`

`preflight` 当前会直接输出工具链与凭据就绪度 JSON，重点包含：

1. `build_tools`
2. `packaging_tools`
3. `signing_tools`
4. `environment`
5. `readiness`

其中 `readiness` 可直接用于判断当前机器是否满足：

1. `can_generate_project`
2. `can_build_native`
3. `can_package`
4. `can_sign`
5. `can_notarize`
6. `can_staple`

当前仓库的签名链路约束：

1. `tools/make.py build` 默认关闭 `xcodebuild` 构建阶段的代码签名，优先保障本机开发和 CI 的“可编译”
2. `installer/macos/sign_app.sh` 负责对 `com.sidus.amaran-desktop.cameraextension.systemextension` 和 container app 做显式签名
3. `sign_app.sh` 当前会在真正签名之前显式检查：
   - Host App bundle 是否存在
   - Camera Extension bundle 是否存在
   - Host / Extension entitlements 是否存在
4. `sign_app.sh` 当前会在签名后执行：
   - Extension `codesign --verify --strict`
   - Host App `codesign --verify --deep --strict`
   - 可用时补充 `spctl -a -vvv` 评估
   - 额外签名并校验 `libakvc-macos-direct-sender.dylib`
   - 如果 `codesign --timestamp` 明确返回时间戳服务不可用，会自动回退到无时间戳签名，优先保障本机安装验证与 Python 直连联调
5. `tools/make.py package` 在检测到 `SIGN_IDENTITY` 时会自动先执行 `sign`，再继续生成 `pkg / dmg / zip`
6. `installer/macos/build_pkg.sh` 在检测到 `PRODUCTSIGN_IDENTITY` 时会继续对最终 `pkg` 做 `productsign`
   - 如果历史 `pkg-staging` 目录因 root-owned / read-only 内容无法复用，脚本会自动切换到新的临时 staging 目录继续打包，而不会直接中断
7. `installer/macos/notarize.sh` 当前会在提交前先检查：
   - `notarytool` 是否可从 `xcrun` 找到
   - `pkgutil --check-signature` 是否显示最终 `pkg` 已签名
   如果仍是 `no signature / not signed`，会直接拒绝提交公证
8. `installer/macos/staple.sh` 当前会在 `stapler staple/validate` 前后补充：
   - `pkgutil --check-signature`
   - 可用时执行 `spctl -a -vvv -t install`
   用于输出最终安装包的 Gatekeeper 评估结果

当前签名/公证结果在统一验收链路中的对应关系：

1. `preflight.json.readiness`
   - 关注 `can_sign / can_notarize / can_staple`
2. `release-diagnostics.json.summary`
   - 关注 `app_signed / extension_signed / command_tools_signed / pkg_signed`
   - 关注 `host_bundle_identifier_expected / extension_bundle_identifier_expected / minimum_system_version_expected`
3. `validation-report.json.summary`
   - 继续汇总 `release_app_signed / release_extension_signed / release_command_tools_signed / release_pkg_signed`
   - 继续汇总 `release_universal2_ready / release_artifacts_present / release_host_embeds_extension_bundle / release_pkg_includes_extension_payload`
4. `session-acceptance.json`
   - `signing_evidence_ready`
   - `notarization_tooling_ready`
   - `release_packaging_ready`
   这三项开始直接对应最终验收标准中的“可签名、公证、自动分发”

当前还已新增独立签名流水线契约 `tools/macos_signing_pipeline_contract.py`，用于把“脚本存在”继续收紧到“签名/公证语义未漂移”：

1. 固定 `sign_app.sh` 仍会先签 Camera Extension，再签 Host App，并执行 `codesign --verify` 与 `spctl` 评估
   - 当前还会逐一签名并校验 `akvc-macos-status / install / uninstall / list-devices / sync-ipc`
   - 这些命令是 Python SDK、CLI、安装会话和人工验收会直接调用的 runtime 资产，不能只让 Host App 与 Extension 具备签名
2. 固定 `build_pkg.sh` 仍会在配置 `PRODUCTSIGN_IDENTITY` 时执行 `productsign`，并补充 `pkgutil --check-signature`
   - 当前还会在 `pkgbuild` 后重建 Payload cpio 与 BOM，确保 `pkgutil --payload-files` 不再出现 `._*` AppleDouble 条目
   - `release_packaging_ready` 现在要求 `pkg_payload_appledouble_clean=true`，不能只证明 pkg/extension payload 存在
3. 固定 `notarize.sh` 仍会在提交前拒绝未签名 `pkg`
4. 固定 `staple.sh` 仍会执行 `pkgutil`、`stapler staple`、`stapler validate` 与 `spctl -t install`
5. 固定 `macos_release_diagnostics.py` 与 `macos_validation_report.py` 仍会持续导出：
   - `app_signed / extension_signed / command_tools_signed / pkg_signed`
   - `release_app_signed / release_extension_signed / release_command_tools_signed / release_pkg_signed`
   - `pkg_payload_appledouble_clean / release_pkg_payload_appledouble_clean`
6. `tools/macos_native_verify.py` 当前也已接入这条 contract，因此本地原生校验、GitHub Actions 和 Jenkins 都能更早发现“签名链路回退但编译仍成功”的问题

当前 CI/CD 分工建议：

1. GitHub Actions
   - 负责语法、单测、无签名 build、基础 package、validation session 工件归档
2. Jenkins
   - 负责持有签名证书、Installer 证书、notary profile 的受控发布流水线
3. 两条流水线都应归档：
   - `preflight.json`
   - `release-diagnostics.json`
   - `session-manifest.json`
   - `session-manifest-check.json`
   - `session-acceptance.json`
   这样签名/公证问题不会只停留在 shell 日志里，而会变成可回归的结构化证据

## 7. 当前结论

签名与公证不是发布阶段的附加步骤，而是 Camera Extension 架构本身的一部分。
