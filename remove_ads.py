#!/usr/bin/env python3
"""Ad removal for installed Android apps (no root required).

Modes:

  scan <package>        Report which ad SDKs an app uses and recommend a strategy.
  dns on|off            Quick, device-wide: block ad domains via Private DNS.
  apk <package> --yes   Repackage the app with ad SDKs neutralised. Backs up the
                        original APKs/external data, then uninstalls and installs.

Examples:
  ./remove_ads.py scan com.example.game
  ./remove_ads.py dns on
  ./remove_ads.py apk com.example.app --yes
  ./remove_ads.py apk com.example.game --yes --rules rules/com.example.game.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADGUARD_DNS = "dns.adguard-dns.com"
KEYSTORE = Path.home() / ".android" / "adfree.keystore"

SDK_MARKERS = {
    "AdMob": [b"com/google/android/gms/ads/MobileAds", b"ca-app-pub-"],
    "AppLovin MAX": [b"com/applovin/mediation/ads/MaxInterstitialAd", b"com/applovin/sdk/AppLovinSdk"],
    "Unity Ads": [b"com/unity3d/ads/UnityAds"],
    "Meta Audience Network": [b"com/facebook/ads/AudienceNetworkAds"],
    "Vungle": [b"com/vungle/ads/VungleAds"],
    "Yandex Mobile Ads": [b"com/yandex/mobile/ads/common/MobileAds"],
    "ironSource / LevelPlay": [b"com/ironsource/mediationsdk/IronSource"],
    "Chartboost": [b"com/chartboost/sdk/Chartboost"],
    "InMobi": [b"com/inmobi/ads/InMobi"],
    "AdColony": [b"com/adcolony/sdk/AdColony"],
    "Tapjoy": [b"com/tapjoy/Tapjoy"],
    "Pangle": [b"com/bytedance/sdk/openadsdk"],
    "Mintegral": [b"com/mintegral/msdk"],
}

MEDIATION = {"AppLovin MAX", "ironSource / LevelPlay"}
DIRECT = {"Unity Ads", "Vungle", "Yandex Mobile Ads", "Chartboost", "InMobi",
          "AdColony", "Tapjoy", "Pangle", "Mintegral", "Meta Audience Network"}


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def adb_cmd(serial):
    adb = shutil.which("adb")
    if not adb:
        sys.exit("[!] adb not found in PATH")
    return [adb] + (["-s", serial] if serial else [])


def find_apksigner():
    if os.environ.get("APKSIGNER"):
        return os.environ["APKSIGNER"]
    found = shutil.which("apksigner")
    if found:
        return found
    roots = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
             str(Path.home() / "Library/Android/sdk")]
    cands = []
    for r in filter(None, roots):
        cands += list(Path(r).glob("build-tools/*/apksigner"))
    if not cands:
        sys.exit("[!] apksigner not found; set APKSIGNER=/path/to/apksigner")
    return str(sorted(cands, key=lambda p: p.parent.name)[-1])


def apktool_cmd():
    jar = os.environ.get("APKTOOL_JAR")
    if not jar:
        local = ROOT / "tools" / "apktool.jar"
        if local.exists():
            jar = str(local)
    if jar:
        return [shutil.which("java") or "java", "-jar", jar]
    exe = shutil.which("apktool")
    if exe:
        return [exe]
    sys.exit("[!] apktool not found. Install it (brew install apktool) "
             "or set APKTOOL_JAR=/path/to/apktool.jar")


def ensure_keystore():
    if KEYSTORE.exists():
        return
    KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    run(["keytool", "-genkeypair", "-keystore", KEYSTORE, "-alias", "ads",
         "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
         "-storepass", "android", "-keypass", "android",
         "-dname", "CN=AdFree"])


def dns_mode(serial, enabled):
    adb = adb_cmd(serial)
    if enabled:
        run(adb + ["shell", "settings", "put", "global", "private_dns_mode", "hostname"])
        run(adb + ["shell", "settings", "put", "global",
                   "private_dns_specifier", ADGUARD_DNS])
        print(f"[+] ad domains now resolve to 127.0.0.1 via {ADGUARD_DNS}")
        print("    (device-wide; revert with: ./remove_ads.py dns off)")
    else:
        run(adb + ["shell", "settings", "delete", "global", "private_dns_mode"])
        run(adb + ["shell", "settings", "delete", "global", "private_dns_specifier"])
        print("[+] Private DNS restored to the system default")


def package_version(serial, package):
    adb = adb_cmd(serial)
    out = subprocess.run(adb + ["shell", "dumpsys", "package", package],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            return line.split("=", 1)[1]
    return "unknown"


def pull_apks(serial, package, workdir):
    adb = adb_cmd(serial)
    out = subprocess.run(
        adb + ["shell", "pm", "path", package], check=True,
        capture_output=True, text=True,
    ).stdout
    paths = [ln.split("package:", 1)[1].strip()
             for ln in out.splitlines() if ln.startswith("package:")]
    if not paths:
        sys.exit(f"[!] {package} is not installed")
    originals = workdir / "original"
    originals.mkdir()
    local = []
    base = originals / "base.apk"
    run(adb + ["pull", paths[0], str(base)])
    local.append(base)
    for i, remote in enumerate(paths[1:], 1):
        dst = originals / f"split_{i}_{Path(remote).name}"
        run(adb + ["pull", remote, str(dst)])
        local.append(dst)
    print(f"[+] pulled {len(local)} apk(s) from {package}")
    return local


def scan_package(serial, package):
    """Inspect an installed app without modifying it."""
    adb = adb_cmd(serial)
    out = subprocess.run(adb + ["shell", "pm", "path", package],
                         capture_output=True, text=True).stdout
    paths = [ln.split("package:", 1)[1].strip()
             for ln in out.splitlines() if ln.startswith("package:")]
    if not paths:
        sys.exit(f"[!] {package} is not installed")

    tmp = Path(tempfile.mkdtemp(prefix=f"adfree-scan-{package}-"))
    try:
        base = tmp / "base.apk"
        run(adb + ["pull", paths[0], str(base)])
        blobs = []
        with zipfile.ZipFile(base) as zf:
            for name in zf.namelist():
                if name.startswith("classes") and name.endswith(".dex"):
                    blobs.append(zf.read(name))
        found = []
        for sdk, markers in SDK_MARKERS.items():
            if any(any(m in blob for blob in blobs) for m in markers):
                found.append(sdk)
        pairip = any(b"com/pairip/application/Application" in b for b in blobs)

        print(f"\npackage : {package}")
        print(f"version : {package_version(serial, package)}")
        print(f"apks    : {len(paths)} (base + {len(paths) - 1} split)")
        print(f"pairip  : {'yes (signature-check wrapper)' if pairip else 'no'}")
        print(f"ad SDKs : {', '.join(found) if found else 'none detected'}")
        print()
        if not found:
            print("[i] No known ad SDK markers found; ads may be first-party.")
        elif MEDIATION & set(found) or len(found) > 2:
            print("[i] Recommendation: mediation-heavy app.")
            print("    1) try `dns on` first (fast, reversible, covers all networks);")
            print("    2) if you need a per-app permanent fix, use `apk` with auto rules.")
        elif found == ["AdMob"]:
            print("[i] Recommendation: `apk` mode works well; AdMob is handled generically.")
        else:
            print("[i] Recommendation: try `apk` mode with auto-generated rules;")
            print("    fall back to `dns on` if an SDK is missed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def backup_artifacts(serial, package, originals, backup_root):
    adb = adb_cmd(serial)
    version = package_version(serial, package)
    dest = backup_root / f"{package}-{version}"
    if dest.exists():
        dest = dest.with_name(dest.name + "-" + str(len(list(backup_root.glob(dest.name + "*")))))
    dest.mkdir(parents=True, exist_ok=True)

    for apk in originals:
        shutil.copy2(apk, dest / apk.name)
    info = subprocess.run(adb + ["shell", "dumpsys", "package", package],
                          capture_output=True, text=True).stdout
    (dest / "package-info.txt").write_text(
        "\n".join(ln for ln in info.splitlines()
                  if any(k in ln for k in ("versionName", "versionCode", "firstInstallTime")))
    )
    ext = subprocess.run(
        adb + ["pull", f"/sdcard/Android/data/{package}/.", str(dest / "external-data")],
        capture_output=True, text=True,
    )
    print(f"[+] backup -> {dest}"
          + ("" if ext.returncode == 0 else " (external data not accessible)"))
    return dest


def build_patched(package, base_apk, workdir, rules, auto_rules):
    import gen_rules
    import patch_apk  # same directory as this script

    dec = workdir / "decoded"
    run(apktool_cmd() + ["d", "-f", str(base_apk), "-o", str(dec)])

    patch_apk.bypass_pairip(dec)
    patch_apk.disable_mobileads(dec)
    patch_apk.disable_banners(dec)
    patch_apk.disable_ad_loads(dec)
    patch_apk.disable_ad_unit_ids(dec)

    if auto_rules:
        data = gen_rules.build_rules(dec, package)
        auto_path = workdir / "rules_auto.json"
        auto_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"[+] auto rules: {len(data['rules'])} entries -> {auto_path}")
        patch_apk.apply_rules(dec, auto_path)

    if rules and rules.exists():
        patch_apk.apply_rules(dec, rules)
    elif auto_rules:
        print(f"[=] no manual overrides for {package} (auto-generated SDK rules used)")
    else:
        print(f"[=] no rules applied for {package}")

    unsigned = workdir / "patched_unsigned.apk"
    run(apktool_cmd() + ["b", str(dec), "-o", str(unsigned)])
    return unsigned


def sign_all(apks, workdir):
    ensure_keystore()
    signer = find_apksigner()
    signed_dir = workdir / "signed"
    signed_dir.mkdir(exist_ok=True)
    signed = []
    for apk in apks:
        dst = signed_dir / apk.name
        run([signer, "sign", "--ks", KEYSTORE, "--ks-pass", "pass:android",
             "--key-pass", "pass:android", "--out", dst, apk])
        signed.append(dst)
    print(f"[+] signed {len(signed)} apk(s)")
    return signed


def apk_mode(serial, package, yes, rules, auto_rules, workdir, backup_root,
             no_install, in_place):
    adb = adb_cmd(serial)
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix=f"adfree-{package}-"))
    else:
        workdir.mkdir(parents=True, exist_ok=True)
    print(f"[i] workdir: {workdir}")

    originals = pull_apks(serial, package, workdir)
    backup_artifacts(serial, package, originals, backup_root)

    patched_base = build_patched(package, originals[0], workdir, rules, auto_rules)
    to_install = [patched_base] + originals[1:]
    signed = sign_all(to_install, workdir)

    install_cmd = adb + ["install-multiple", "-r"] + [str(p) for p in signed]
    if no_install:
        print("\n[i] Built only. Install with:")
        print("    adb uninstall", package)
        print("    " + " ".join(str(c) for c in install_cmd))
        return
    if not yes:
        print("\n[i] Dry run. To finish, run:")
        print("    adb uninstall", package)
        print("    " + " ".join(str(c) for c in install_cmd))
        return

    if in_place:
        print(f"[i] installing over {package} (data preserved; same signing key required)")
        run(install_cmd)
    else:
        print(f"[!] uninstalling {package} (app data will be lost; progress may sync from server)")
        run(adb + ["uninstall", package])
        run(install_cmd)
    print(f"[+] {package} now runs the ad-free build")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", help="adb serial (default: only connected device)")
    sub = ap.add_subparsers(dest="mode", required=True)

    scan = sub.add_parser("scan", help="report ad SDKs and recommend a strategy")
    scan.add_argument("package")

    dns = sub.add_parser("dns", help="device-wide ad blocking via Private DNS")
    dns.add_argument("state", choices=["on", "off"])

    apk = sub.add_parser("apk", help="repackage one app without ads")
    apk.add_argument("package")
    apk.add_argument("--yes", action="store_true", help="actually uninstall/install")
    apk.add_argument("--rules", type=Path,
                     help="app-specific rules JSON (default: rules/<package>.json)")
    apk.add_argument("--no-auto-rules", action="store_true",
                     help="skip scanning the decoded APK for common ad SDKs")
    apk.add_argument("--workdir", type=Path, help="keep build artifacts here")
    apk.add_argument("--backup-dir", type=Path, default=Path.cwd() / "backups",
                     help="where to put APK/external-data backups (default: ./backups)")
    apk.add_argument("--no-install", action="store_true", help="build and sign only")
    apk.add_argument("--in-place", action="store_true",
                     help="install over the existing app (same signing key), preserving data")

    args = ap.parse_args()
    if args.mode == "scan":
        scan_package(args.device, args.package)
    elif args.mode == "dns":
        dns_mode(args.device, args.state == "on")
    else:
        rules = args.rules or ROOT / "rules" / f"{args.package}.json"
        apk_mode(args.device, args.package, args.yes, rules,
                 not args.no_auto_rules, args.workdir, args.backup_dir,
                 args.no_install, args.in_place)


if __name__ == "__main__":
    main()
