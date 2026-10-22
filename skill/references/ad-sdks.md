# Ad SDK reference

## Covered entry points (`gen_rules.py`)

| SDK | Class | Neutralised methods |
|-----|-------|---------------------|
| AdMob | `com.google.android.gms.ads.MobileAds` | `initialize`, auto-init provider |
| AdMob | `BaseAdView` / `InterstitialAd` / `RewardedAd` / `AppOpenAd` / `RewardedInterstitialAd` / native | `loadAd` / static `load` |
| AppLovin MAX | `MaxInterstitialAd`, `MaxRewardedAd`, `MaxAppOpenAd`, `MaxAdView`, `MaxNativeAdLoader` | `loadAd`, `showAd` |
| AppLovin MAX | `AppLovinSdk`, `AppLovinInitProvider` | `initialize`, provider `onCreate` |
| Unity Ads | `com.unity3d.ads.UnityAds` | `initialize`, `load`, `show`, `isInitialized` |
| Meta | `AudienceNetworkAds`, `AudienceNetworkContentProvider` | `initialize`, `isInitialized`, provider `onCreate` |
| Meta | `InterstitialAd`, `RewardedVideoAd` | `loadAd`, `show`, `isAdLoaded` |
| Vungle | `VungleAds`, `VungleProvider` | `init`, `isInitialized`, provider `onCreate` |
| Yandex | `MobileAds`, `MobileAdsInitializeProvider` | `initialize`, provider `onCreate` |
| ironSource / LevelPlay | `IronSource`, `LevelPlayInterstitialAd`, `LevelPlayRewardedAd` | `init`, `load*`, `show*` |
| Chartboost | `Chartboost` | `init`, `cache*`, `show*` |
| InMobi | `InMobi` | `initialize` |
| AdColony | `AdColony` | `configure`, `request*`, `show*` |
| Tapjoy | `Tapjoy` | `connect`, `showContent` |
| Pangle | `TTAdSdk` | `init` |
| Mintegral | `MintegralSDK` | `init` |
| Smaato | `SmaatoSdk` | `init` |
| Fyber / Inneractive | `InneractiveAdManager` | `initialize`, `wasInitialized` |
| Amazon Ads | `AdRegistration` | `setAppKey`, `initBidderSDK`, `isInitialized` |

Mediation SDKs call their adapters only after a successful load, so disabling
the mediator (MAX / LevelPlay) also stops every adapter behind it. Direct SDK
calls from the game still need their own rules.

## Ad domains commonly blocked by AdGuard DNS

AdMob/Google: `googleads.g.doubleclick.net`, `pubads.g.doubleclick.net`,
`pagead2.googlesyndication.com`, `securepubads.g.doubleclick.net`,
`adservice.google.com`, `googleadservices.com`, `app-measurement.com`

AppLovin: `ms.applovin.com`, `a.applovin.com`, `sdk-api.applovin.com`,
`d.applovin.com`, `cdn.applovin.com`

Unity Ads: `cdn.unityads.unity3d.com`, `webview.unityads.unity3d.com`,
`auction.unityads.unity3d.com`

Meta: `an.facebook.com`, `graph.facebook.com` (may affect Facebook login)

Pangle: `api.pangle.io`, `*.pangolin-sdk-toutiao.com`

Mintegral: `api.mintegral.com`, `*.mintegral.com`

Vungle: `api.vungle.com`, `ads.vungle.com`

ironSource/LevelPlay: `*.ironsrc.com`, `*.supersonicads.com`

Chartboost: `live.chartboost.com`, `*.chartboost.com`

Fyber: `*.fyber.com`, `*.inner-active.mobi`

Tapjoy: `*.tapjoy.com`, `*.tapjoyads.com`

InMobi: `*.inmobi.com`, `*.inmobicdn.net`

AdColony: `*.adcolony.com`

Yandex: `*.yandex.net` (careful: shared with other Yandex services)

Smaato: `*.smaato.net`

## New Google Mobile Ads SDK (`ads_mobile_sdk`)

Recent apps use `com.google.android.libraries.ads.mobile.sdk.*` and R8 may
repackage the SDK under `Lads_mobile_sdk/...`. In that case:

- `com/google/android/gms/ads/MobileAds`, `MobileAdsInitProvider` and
  `BaseAdView` are absent, so the class-based patches find nothing;
- the SDK still initialises from Google Play services and can serve a banner.

Fallback: `patch_apk.disable_ad_unit_ids()` replaces every
`ca-app-pub-<publisher>/<unit>` with `ca-app-pub-0000000000000000/0000000000`
in smali and string resources. The SDK initialises but every request is
unfillable. Verified on a real Android 13 device: the banner disappeared while
the app kept working.

Caveat: this only covers AdMob unit IDs. If the app also uses Meta Audience
Network through its asset dex (`assets/audience_network/classes*.dex`), patch
the asset dex or disable the network separately.

## PairIP

Some Play apps declare `android:name="com.pairip.application.Application"`.
The wrapper only calls `LicenseClient.checkLicense()` in `attachBaseContext`.
`patch_apk.bypass_pairip()` points the manifest back at the wrapper's superclass
(the real Application) and removes `LicenseActivity`. If a native
`libpairipcore.so` is present, the protection is stronger — test carefully.

## Split APKs

Play-distributed apps often have:

- `base.apk`
- `split_config.<abi>.apk`
- `split_config.<density>.apk`
- `split_config.<locale>.apk`
- Play Asset Delivery packs such as `split_gpdeku.apk`

Back up and re-sign every one, then install with `adb install-multiple`.
Uninstall the original first — signatures cannot be mixed.

## Tested

App names and package names are intentionally anonymised for privacy:

- 系统工具 A：PairIP 加固 + AdMob。
- 系统工具 B：新版 GMA SDK（`ads_mobile_sdk`，R8 混淆）+ Meta；用广告位 ID 置零兜底。
- 游戏 A：Unity + AppLovin MAX / Unity Ads / Meta / Vungle / Yandex / AdMob 聚合。
- 游戏 B：Unity，12 家广告 SDK，无 PairIP。
- 游戏 C：AppLovin MAX 聚合，带 Smaato / Fyber / Amazon adapter；重签后 Play Games
  自动登录会报 `DEVELOPER_ERROR`，但游戏本体正常。
