# Android Ad-Free Toolkit

从已安装的 Android 应用中去除广告的可复用工具（无需 root）。覆盖 AdMob、AppLovin MAX、Unity Ads、Meta Audience Network、Vungle、Yandex、ironSource/LevelPlay、Chartboost、InMobi、AdColony、Tapjoy、Pangle、Mintegral、Smaato、Fyber、Amazon Ads 等。

> 隐私说明：仓库中不包含任何处理过的应用名称、包名或备份数据；下文中用「系统工具 A/B」「游戏 A/B/C」代指。

已在 **Android 13 真机** 上验证多类应用（单 AdMob、聚合型游戏、新版 GMA SDK 等）。

## 三个命令

### 0. `scan` — 先识别广告 SDK（不改设备）

```bash
./remove_ads.py --device <serial> scan <package>
```

输出版本、split 数量、PairIP 加固、检测到的广告 SDK，并给出建议（单 AdMob → 改包；多 SDK/聚合 → 先试 DNS）。

### 1. `dns` — 快速、全局、可逆（推荐先试）

```bash
./remove_ads.py dns on     # 把 Private DNS 设为 dns.adguard-dns.com
./remove_ads.py dns off    # 恢复系统默认 DNS
```

- 原理：广告域名（`googleads.g.doubleclick.net` 等）被解析到 `127.0.0.1`。
- 优点：不改 APK、不丢数据、对所有接入这些域名的应用生效。
- 缺点：全局生效；ad SDK 会等待超时，部分应用可能仍显示空白广告位。
- 注意：如果手机同时开着代理/VPN，走 VPN 的应用可能绕过该 DNS。

**多广告 SDK 的应用（尤其游戏）可以先 `dns` 快速验证**，确认有效后再决定是否改包。聚合型应用逐个 adapter 打补丁不现实，但把**聚合层和各 SDK 的初始化/加载入口**掐掉就够了：

- AppLovin MAX：`AppLovinSdk.initialize`、各 `Max*Ad.loadAd/showAd`、`MaxAdView`、`MaxNativeAdLoader`
- Unity Ads：`UnityAds.initialize/load/show`
- Meta：`AudienceNetworkAds.initialize`、插屏/激励 `loadAd/show`
- Vungle / Yandex：Provider 自动初始化 + `VungleAds.init` / `MobileAds.initialize`
- AdMob：通用补丁（初始化、横幅、插屏/开屏/激励/原生 load）

### 2. `apk` — 改包，彻底去除（无广告请求）

```bash
./remove_ads.py apk com.example.app --yes
```

流程全部自动完成：

1. `adb` 拉取 base + split APK；
2. 把原始 APK、`package-info.txt` 和外部数据备份到 `./backups/<package>-<version>/`；
3. `apktool` 反编译；
4. 打通用补丁（PairIP + AdMob + 广告位 ID 置空），并按 `gen_rules.py` **自动生成**各广告 SDK 入口的空实现规则；
5. 应用 `rules/<package>.json`（如有，用于应用级广告分支）；
6. `apktool` 回编译、`apksigner` 重签全部 APK；
7. 卸载原版 → `install-multiple` 安装改版。

常用参数：

```bash
--no-auto-rules        # 不自动生成 SDK 规则
--rules <file.json>    # 指定应用级规则
--workdir <dir>        # 保留反编译/构建产物
--backup-dir <dir>     # 指定备份目录
--no-install           # 只构建和签名，不卸载/安装
--in-place             # 覆盖安装（同签名），保留应用数据
```

不带 `--yes` 时只构建、备份，不卸载，打印出需要手动执行的命令。

## 补丁内容

`patch_apk.py` 对反编译目录做以下修改（全部是空实现，不改业务逻辑）：

| # | 目标 | 作用 |
|---|------|------|
| 1 | PairIP `Application` 包装类 | 把 manifest 指回真实的 Application 类，跳过 Play 授权/签名校验 |
| 2 | `MobileAds.initialize()` + `MobileAdsInitProvider.attachInfo()` | 禁止 AdMob SDK 初始化 |
| 3 | `BaseAdView.loadAd(AdRequest)` | 禁止横幅请求 |
| 4 | 所有 `load(Context, unitId, AdRequest, callback)` 静态入口 | 禁止插屏 / 开屏 / 激励 / 原生广告 |
| 5 | `ca-app-pub-.../...` 广告位 ID | 替换为零 ID；新版 GMA SDK（`ads_mobile_sdk`）被 R8 混淆、类补丁找不到入口时的兜底 |
| 6 | `rules/<package>.json` | 应用级规则：跳过开屏广告分支、去掉评分弹窗等 |

应用级规则格式见 `rules/example.json`：

```json
{
  "rules": [
    { "class": "Lcom/example/app/AdGate;", "method": "canShowAd()Z", "return": false }
  ]
}
```

`class` 用 smali 描述符（`L包名/类名;`），脚本会在所有 `smali*` 目录里查找，不依赖 apktool 的目录名。SDK 入口规则由 `gen_rules.py` 在改包时自动生成，不需要手工维护。

## 前置条件

- `adb` 已连接设备并授权；
- Java + [apktool](https://apktool.org/)：`brew install apktool`，或设置 `APKTOOL_JAR=/path/to/apktool.jar`；
- `apksigner`：Android SDK build-tools 自带，脚本会自动查找（也可用 `APKSIGNER=` 指定）；
- 部分厂商设备需在开发者选项中允许「USB 安装 / USB 调试（安全设置）」。

## 注意事项

- **重签会改变签名**：必须先卸载原版（或用 `--in-place` 覆盖安装），应用数据可能丢失；Play 商店无法再更新该应用（签名不匹配），升级时需重新跑脚本。
- 通用补丁覆盖 AdMob；自动规则覆盖常见 SDK。若某个 SDK 未被识别、或广告是应用自营/服务端下发，优先用 `dns`，或在 `rules/<package>.json` 里补入口。
- 如果有 PairIP 之外的加固（native 完整性校验、Play Integrity 门控、服务端证明），改包可能失败或功能受限，先停下评估。
- 仅供在自己拥有/控制的设备上处理自己安装的应用。

## 作为 Claude Code skill

```bash
./sync-skill.sh
# -> ~/.claude/skills/android-ad-removal/
```

安装后新开一个 Claude Code 会话即可使用 `/android-ad-removal`，skill 会按「scan → 选方案 → 备份 → 补丁 → 验证」的流程执行。

## 恢复原版

```bash
adb uninstall <package>
# 从 Play 商店重新安装；或用改包时备份的原始 APK：
adb install-multiple backups/<package>-<version>/base.apk \
  backups/<package>-<version>/split_*.apk
```

## 文件

```
remove_ads.py                  # 命令行入口（scan / dns / apk）
patch_apk.py                   # 通用 smali 补丁（PairIP + AdMob + 广告位 ID 置零）
gen_rules.py                   # 扫描反编译产物，生成各广告 SDK 的空实现规则
rules/example.json             # 应用级规则格式示例
rules/README.md                # 规则说明
skill/SKILL.md                 # Claude Code skill 说明
skill/references/ad-sdks.md    # SDK 入口与广告域名参考
sync-skill.sh                  # 安装/更新 ~/.claude/skills/android-ad-removal
```

> 备份目录 `backups/` 和改包产物默认被 `.gitignore` 忽略，不上传仓库。
