---
name: android-ad-removal
description: Remove ads from an installed Android app over adb without root. Use when the user asks to remove/block ads (去广告) from a specific Android app, or mentions AdMob, AppLovin MAX, Unity Ads, Meta Audience Network, Vungle, Yandex, ironSource/LevelPlay, or a mediation-heavy game. Supports quick device-wide Private DNS blocking and permanent per-app APK repackaging (backup, smali patches, re-sign, multi-split install, verification).
---

# Android Ad Removal (no root)

Scripts live in `~/.claude/skills/android-ad-removal/scripts/` (or the directory
containing this SKILL.md). Run them with `python3`; they only need `adb` for
scanning/installing, plus Java + `apktool` for repackaging.

## 1. Preflight

```bash
adb devices -l
adb shell pm list packages | grep -i <keyword>
adb shell dumpsys package <package> | grep -E "versionName|versionCode|installerPackageName"
```

Find the package by name/label/recent task (`dumpsys activity recents`). Never
patch a system app or an app the user does not own.

## 2. Scan and choose a strategy

```bash
python3 ~/.claude/skills/android-ad-removal/scripts/remove_ads.py \
  --device <serial> scan <package>
```

- **One SDK (AdMob only)** → `apk` mode is straightforward; AdMob is handled generically.
- **Mediation / many SDKs (games)** → try `dns on` first, it is fast and reversible.
  If the user wants a per-app permanent fix, use `apk` mode with auto-generated rules.
- **No known SDK** → ads may be first-party; DNS may still help, otherwise inspect the app.

Tell the user which mode you chose and why before modifying the device.

## 3a. Quick mode: Private DNS (device-wide)

```bash
python3 .../remove_ads.py --device <serial> dns on
python3 .../remove_ads.py --device <serial> dns off   # restore default
```

Caveats: affects every app, persists across reboots. Apps routed through a VPN
bypass it — check `dumpsys connectivity` UIDs if needed. Ad SDKs may still wait
for timeouts, leaving blank ad slots.

## 3b. Permanent mode: APK repackaging (per-app)

```bash
# First run without --yes: builds, backs up, prints the install commands.
python3 .../remove_ads.py --device <serial> apk <package>

# After the user confirms the install/uninstall:
python3 .../remove_ads.py --device <serial> apk <package> --yes
```

The script:

1. pulls base + all split APKs;
2. backs them up and the app's external data to `./backups/<package>-<version>/`;
3. decodes with apktool;
4. applies `patch_apk.py` (PairIP bypass + generic AdMob disable);
5. auto-generates and applies rules for AppLovin MAX, Unity Ads, Meta, Vungle,
   Yandex, ironSource/LevelPlay, Chartboost, InMobi, AdColony, Tapjoy, Pangle,
   Mintegral, Smaato, Fyber and Amazon Ads (`gen_rules.py`);
   also replaces AdMob ad unit IDs (`ca-app-pub-.../...`) with zero units —
   the fallback for the new Google Mobile Ads SDK, whose classes are often
   R8-repackaged under `ads_mobile_sdk` and cannot be found by class patches;
6. applies `rules/<package>.json` if present (app-specific extras);
7. rebuilds, re-signs base + splits with `~/.android/adfree.keystore`;
8. uninstalls the original and installs the patched build with `install-multiple`.

Useful flags: `--no-auto-rules`, `--rules <json>`, `--workdir <dir>`,
`--backup-dir <dir>`, `--no-install`, `--in-place` (install over the existing
build when it already uses our signing key; preserves app data).

### Writing app-specific rules

You usually do **not** need a rule file for a new app: `gen_rules.py` scans the
decoded APK and generates SDK rules at build time. Only add a manual file when
the app has its own ad gate that is not an SDK method (splash-ad branch, rating
prompt, server-controlled ad switch).

Add a JSON file to `rules/<package>.json` (see `rules/example.json`):

```json
{
  "rules": [
    { "class": "Lcom/example/app/AdGate;", "method": "canShowAd()Z", "return": false },
    { "class": "Lcom/example/app/AdGate;", "method": "show()V", "return": "void" }
  ]
}
```

`class` is the smali descriptor (`Lpackage/Class;`). Use this for app-level
ad gates (e.g. a splash-ad branch) or an SDK entry point the scanner missed.

## 4. Verify

```bash
adb shell am force-stop <package>
adb shell logcat -c
adb shell am start -n <launch-activity>
adb shell dumpsys window | grep -iE "AdActivity|AppLovinFullscreen|unityads|AudienceNetwork"
adb shell logcat -d | grep -iE "AppLovin|UnityAds|AdMob|AudienceNetwork|Vungle|Yandex"
adb exec-out screencap -p > /tmp/check.png
```

Read the screenshot. Exercise the surfaces that normally show ads: launch,
level start/end, reward buttons, tab switches. Then pull the installed base APK
and confirm a patched method is a no-op:

```bash
apkanalyzer dex code --class com.applovin.mediation.ads.MaxInterstitialAd installed.apk
```

## 5. Report caveats

- Re-signing changes the signature: **app data is wiped**, Play Store updates
  stop working, and Play Games / in-app purchases may fail. Some games
  auto-sign-in to Play Games and will log `DEVELOPER_ERROR` on a re-signed
  build; the game itself can still run. Progress stored on the game's own
  server usually restores after reinstall.
- Users must re-run the toolkit after updating the app from Play (if Play will
  even update it — usually it cannot, due to the signature mismatch).
- Provide the restore command using the backup APKs.
- MIUI/Xiaomi may need "USB debugging (Security settings)" enabled for adb installs.
- Stop and report if the app has anti-tamper beyond PairIP (native integrity
  checks, Play Integrity gating, server-side attestation).

See `references/ad-sdks.md` for the covered SDK entry points and ad domains.
