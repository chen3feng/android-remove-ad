#!/usr/bin/env python3
"""Generate no-op rules for common ad-SDK entry points in a decoded APK.

Usage:
    python3 gen_rules.py <decoded-apktool-dir> --package com.example.app \
        [--out rules/com.example.app.json]

The rules only contain public methods that start ad loading/showing or SDK
initialisation. They are applied by patch_apk.py.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# class descriptor -> method regexes (void or boolean methods)
TARGETS = {
    # AppLovin MAX
    "Lcom/applovin/mediation/ads/MaxInterstitialAd;": [r"loadAd\(\)V", r"showAd\(.*\)V"],
    "Lcom/applovin/mediation/ads/MaxRewardedAd;": [r"loadAd\(\)V", r"showAd\(.*\)V"],
    "Lcom/applovin/mediation/ads/MaxAppOpenAd;": [r"loadAd\(\)V", r"showAd\(.*\)V"],
    "Lcom/applovin/mediation/ads/MaxAdView;": [r"loadAd\(\)V"],
    "Lcom/applovin/mediation/nativeAds/MaxNativeAdLoader;": [r"loadAd\(.*\)V"],
    "Lcom/applovin/sdk/AppLovinSdk;": [r"initialize\(.*\)V"],
    "Lcom/applovin/sdk/AppLovinInitProvider;": [r"onCreate\(\)Z"],
    # Unity Ads / LevelPlay bridge
    "Lcom/unity3d/ads/UnityAds;": [
        r"initialize\(.*\)V", r"load\(.*\)V", r"show\(.*\)V", r"isInitialized\(\)Z",
    ],
    # Meta Audience Network
    "Lcom/facebook/ads/AudienceNetworkAds;": [r"initialize\(.*\)V", r"isInitialized\(.*\)Z"],
    "Lcom/facebook/ads/AudienceNetworkContentProvider;": [r"onCreate\(\)Z"],
    "Lcom/facebook/ads/InterstitialAd;": [r"loadAd\(.*\)V", r"show\(.*\)Z", r"isAdLoaded\(\)Z"],
    "Lcom/facebook/ads/RewardedVideoAd;": [
        r"loadAd\(.*\)V", r"show\(.*\)Z", r"isAdLoaded\(\)Z",
    ],
    # Vungle / Liftoff
    "Lcom/vungle/ads/VungleProvider;": [r"onCreate\(\)Z"],
    "Lcom/vungle/ads/VungleAds;": [r"init\(.*\)V", r"isInitialized\(\)Z"],
    # Yandex Mobile Ads
    "Lcom/yandex/mobile/ads/core/initializer/MobileAdsInitializeProvider;": [r"onCreate\(\)Z"],
    "Lcom/yandex/mobile/ads/common/MobileAds;": [r"initialize\(.*\)V"],
    # ironSource / LevelPlay
    "Lcom/ironsource/mediationsdk/IronSource;": [
        r"init\(.*\)V", r"showInterstitial\(.*\)V", r"showRewardedVideo\(.*\)V",
        r"loadInterstitial\(.*\)V", r"loadRewardedVideo\(.*\)V",
    ],
    "Lcom/ironsource/mediationsdk/ads/interstitial/LevelPlayInterstitialAd;": [
        r"loadAd\(\)V", r"showAd\(.*\)V",
    ],
    "Lcom/ironsource/mediationsdk/ads/rewarded/LevelPlayRewardedAd;": [
        r"loadAd\(\)V", r"showAd\(.*\)V",
    ],
    # Chartboost
    "Lcom/chartboost/sdk/Chartboost;": [
        r"init\(.*\)V", r"cacheInterstitial\(.*\)V", r"showInterstitial\(.*\)V",
        r"cacheRewardedVideo\(.*\)V", r"showRewardedVideo\(.*\)V",
    ],
    # InMobi
    "Lcom/inmobi/ads/InMobi;": [r"initialize\(.*\)V"],
    # AdColony
    "Lcom/adcolony/sdk/AdColony;": [
        r"configure\(.*\)V", r"requestInterstitial\(.*\)V", r"showInterstitial\(.*\)V",
        r"requestAd\(.*\)V",
    ],
    # Tapjoy
    "Lcom/tapjoy/Tapjoy;": [r"connect\(.*\)V", r"showContent\(.*\)V"],
    # Pangle / ByteDance
    "Lcom/bytedance/sdk/openadsdk/TTAdSdk;": [r"init\(.*\)V"],
    # Mintegral
    "Lcom/mintegral/msdk/MintegralSDK;": [r"init\(.*\)V"],
    # Smaato
    "Lcom/smaato/sdk/core/SmaatoSdk;": [r"init\(.*\)V"],
    # Fyber / Inneractive
    "Lcom/fyber/inneractive/sdk/external/InneractiveAdManager;": [
        r"initialize\(.*\)V", r"wasInitialized\(\)Z",
    ],
    # Amazon Ads
    "Lcom/amazon/device/ads/AdRegistration;": [
        r"setAppKey\(.*\)V", r"initBidderSDK\(\)V", r"isInitialized\(\)Z",
    ],
}


class SmaliIndex:
    """Lazily index every class descriptor in a decoded apk."""

    def __init__(self, dec: Path):
        self.dec = dec
        self._index = None

    def _build(self):
        index = {}
        for d in self.dec.glob("smali*"):
            if not d.is_dir():
                continue
            for f in d.rglob("*.smali"):
                try:
                    first = f.read_text(errors="ignore").splitlines()[0]
                except (OSError, IndexError):
                    continue
                if first.startswith(".class"):
                    index[first.split()[-1]] = f
        self._index = index

    def get(self, descriptor: str):
        if self._index is None:
            self._build()
        return self._index.get(descriptor)


def method_rules(smali: Path, patterns):
    text = smali.read_text(errors="ignore")
    out = []
    for line in text.splitlines():
        if not line.startswith(".method public"):
            continue
        sig = line.split()[-1]
        if not any(re.fullmatch(p, sig) for p in patterns):
            continue
        ret = False if sig.endswith(")Z") else "void"
        out.append({"method": sig, "return": ret})
    return out


def build_rules(dec: Path, package: str, app: str = "") -> dict:
    index = SmaliIndex(dec)
    rules = []
    for descriptor, patterns in TARGETS.items():
        smali = index.get(descriptor)
        if smali is None:
            continue
        for entry in method_rules(smali, patterns):
            rules.append({"class": descriptor, **entry})
    return {
        "package": package,
        "app": app,
        "notes": "Auto-generated no-op rules for ad SDK entry points.",
        "rules": rules,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("decoded", type=Path)
    ap.add_argument("--package", required=True)
    ap.add_argument("--app", default="")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    if not (args.decoded / "AndroidManifest.xml").exists():
        sys.exit(f"[!] {args.decoded} is not apktool output")

    data = build_rules(args.decoded, args.package, args.app)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"[+] {len(data['rules'])} rules -> {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
