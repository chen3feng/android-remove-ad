# Rules

两类规则，不要混淆：

## 根目录 `<package>.json` — 手写的应用级规则

只用于 **SDK 之外的广告逻辑**，例如：

- 启动器的开屏广告分支（`AdManager.canShowAd()`）
- 应用自己的评分弹窗触发方法
- 自营广告 / 服务端下发的广告开关

`remove_ads.py apk <package>` 会自动查找并应用这个文件；没有也能正常改包。

## `example.json` — 格式示例

`rules/example.json` 展示了规则格式（类描述符 + 方法签名 + 返回值）。SDK 入口规则由
`gen_rules.py` 在改包时按目标 APK 自动生成，不需要手工维护快照。

## 结论

新应用不需要预先准备 rules 文件：

1. `patch_apk.py` 先做通用补丁（PairIP + AdMob 初始化/横幅/各格式 load）；
2. `gen_rules.py` 按目标 APK 实际存在的 SDK 类生成规则；
3. 如果发现应用自己的广告分支，再手写一个根目录 `<package>.json` 补充。
