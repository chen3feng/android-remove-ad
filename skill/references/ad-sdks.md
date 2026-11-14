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

Fallback: `patch_apk.disable_ad_ids()` replaces two kinds of literal in smali
and string resources:

- ad **unit** IDs `ca-app-pub-<publisher>/<unit>` →
  `ca-app-pub-0000000000000000/0000000000`;
- the AdMob **app** ID `ca-app-pub-<publisher>~<app>` →
  `ca-app-pub-0000000000000000~0000000000`.

The SDK may still initialise (and start mediation adapters), but it cannot
fetch app settings and every request fails with
`Ads: Ad failed to load : 3` (`ERROR_CODE_NO_FILL`). Verified on a real
Android 13 device: banners/interstitials never appear while the app keeps
working. (The standalone `disable_ad_unit_ids()` name is kept as an alias.)

### Null the APP id when units come from Remote Config

Some apps keep the app ID in a resource (`ph_admob_app_id`,
`GOOGLE_ADMOB_APPLICATION_ID`, …) but ship the unit IDs as **zero constants**,
fetching the real units from Firebase Remote Config keys such as
`ad_unit_admob_banner` / `ad_unit_admob_interstitial` /
`ad_unit_admob_native` / `ad_unit_admob_rewarded`. When the device has no
cached Remote Config value (or the fetch is blocked), logcat shows
`FirebaseRemoteConfig: No value ... exists for parameter key '...'`.

Replacing only unit literals does nothing in that case — they are already
zero. Nulling the **app ID** is what breaks init: GMA logs
`Not retrying to fetch app settings` and all loads end with no-fill. This is
why `disable_ad_ids()` always replaces both patterns.

### AdMob-mediated other SDKs

A bundled AppLovin SDK does not mean the app calls MAX directly: logcat may
show `Mediation Provider: admob` and classes like
`com.google.ads.mediation.applovin.AppLovinMediationAdapter` (plus a Meta
adapter started by AppLovin). These adapters initialise as a side effect of
GMA init, but with the app/unit IDs nulled their waterfalls never fill and no
ad shows. No per-adapter rules are needed for that topology.

Caveat: this only covers AdMob unit IDs. If the app also uses Meta Audience
Network through its asset dex (`assets/audience_network/classes*.dex`), patch
the asset dex or disable the network separately.

## Rating prompts and monetisation helper SDKs

Apps often bundle a third-party "monetisation/premium helper" library that
owns the rating bar, paywall and Remote Config gates. After R8 the classes
are obfuscated, but the structure is stable enough to follow:

- a config class reads Remote Config keys (`rate_us_mode`,
  `rateus_session_start`, `ads_provider`, `ad_manager_timeout_seconds`, …);
- a manager class (e.g. `Lxx/m;`) mixes the Play Core in-app review flow with
  its own dialog: one static method (`d`/`e`) wraps
  `requestInAppReview` — leave it, Google rate-limits it itself; another
  method (`f(FragmentManager;ILjava/lang/String;I...)V`) contains the
  `"RATE_DIALOG"` tag and a `"Failed to show rate dialog"` log;
- the custom 5-star bar is a `DialogFragment` (an `AppCompatDialogFragment`
  subclass with a short `onCreateDialog`).

Choke point: one `void` rule on the manager method that shows the custom
dialog kills the prompt app-wide; do not patch Play Core review, the fragment
itself, or every click listener. Search for `"RATE_DIALOG"` /
`"Do you like"` strings and `new-instance` of the dialog class to find it.
Keep paywall/IAP code untouched unless the user explicitly asks otherwise.

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
- 系统工具 C：新版 GMA SDK 作聚合，AppLovin / Meta 均为其 mediation adapter；
  广告位 ID 本地全为零、真实值走 Firebase Remote Config；置零 **AdMob App ID**
  后所有请求 `Ad failed to load : 3`。另用一条 void 规则掐掉第三方 helper 的
  自定义五星评分弹窗（Play Core 评审流保留）。
- 游戏 A：Unity + AppLovin MAX / Unity Ads / Meta / Vungle / Yandex / AdMob 聚合。
- 游戏 B：Unity，12 家广告 SDK，无 PairIP。
- 游戏 C：AppLovin MAX 聚合，带 Smaato / Fyber / Amazon adapter；重签后 Play Games
  自动登录会报 `DEVELOPER_ERROR`，但游戏本体正常。
