#!/usr/bin/env python3
"""Neutralise AdMob + PairIP in an apktool-decoded app.

Usage:
    python3 patch_apk.py <decoded-apktool-dir> [--rules rules/<pkg>.json]

What it does (all patches are no-ops, the rest of the app is untouched):
  1. PairIP: point AndroidManifest's application back at the real app class,
     so com.pairip.licensecheck.LicenseClient is never invoked.
  2. AdMob: no-op MobileAds.initialize() and the auto-init provider.
  3. Banners: no-op BaseAdView.loadAd(AdRequest).
  4. All full-screen formats: no-op the static load(Context, unitId, AdRequest, cb)
     entry points shared by interstitial / app-open / rewarded / native ads.
  5. App-specific rules (e.g. "never take the splash-ad branch").
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def method_decls(smali: Path):
    """Yield (line, signature) for every .method declaration in a file."""
    try:
        text = smali.read_text(errors="ignore")
    except OSError:
        return
    for line in text.splitlines():
        if line.startswith(".method "):
            yield line, line.split()[-1]


def replace_body(path: Path, signature: str, body: str) -> bool:
    text = path.read_text()
    pattern = re.compile(
        r"(?m)^(\.method [^\n]*" + re.escape(signature) + r"\n)(.*?)(^\.end method\n)",
        re.S,
    )
    new, n = pattern.subn(lambda m: m.group(1) + body + m.group(3), text)
    if n:
        path.write_text(new)
    return bool(n)


def noop_void(path: Path, signature: str) -> bool:
    return replace_body(path, signature, "    .locals 0\n    return-void\n")


def noop_bool(path: Path, signature: str, value: bool) -> bool:
    v = "0x1" if value else "0x0"
    body = f"    .locals 1\n    const/4 v0, {v}\n    return v0\n"
    return replace_body(path, signature, body)


def smali_dirs(dec: Path):
    return sorted(p for p in dec.glob("smali*") if p.is_dir())


def find_class(dec: Path, descriptor: str) -> Path | None:
    """Find a smali file by class descriptor, e.g. 'Lcom/example/app/AdGate;'."""
    needle = re.compile(r"^\.class\b.*\s" + re.escape(descriptor) + r"$")
    for d in smali_dirs(dec):
        for f in d.rglob("*.smali"):
            try:
                first = f.read_text(errors="ignore").splitlines()[0]
            except (OSError, IndexError):
                continue
            if needle.match(first):
                return f
    return None


def bypass_pairip(dec: Path) -> None:
    manifest = dec / "AndroidManifest.xml"
    text = manifest.read_text()
    if 'android:name="com.pairip.application.Application"' not in text:
        print("[=] PairIP wrapper not present")
        return
    wrapper = find_class(dec, "Lcom/pairip/application/Application;")
    if wrapper is None:
        sys.exit("[!] PairIP wrapper class not found")
    m = re.search(r"^\.super L([^;]+);$", wrapper.read_text(), re.M)
    if not m:
        sys.exit("[!] cannot read PairIP wrapper superclass")
    real = m.group(1).replace("/", ".")
    text = text.replace(
        'android:name="com.pairip.application.Application"',
        f'android:name="{real}"',
    )
    # Drop the PairIP license activity if declared.
    text = re.sub(
        r"\s*<activity[^>]*com\.pairip\.licensecheck\.LicenseActivity[^>]*/>", "", text
    )
    manifest.write_text(text)
    print(f"[+] PairIP bypassed -> {real}")


def disable_mobileads(dec: Path) -> None:
    mobile_ads = find_class(dec, "Lcom/google/android/gms/ads/MobileAds;")
    if mobile_ads is None:
        print("[=] MobileAds not bundled, skipping init patch")
        return
    # initialize(Context, InitializationStatusCallback)
    for line, sig in method_decls(mobile_ads):
        if "public static" in line and re.fullmatch(
            r"[a-zA-Z0-9_$]+\(Landroid/content/Context;L[^;]+;\)V", sig
        ):
            if noop_void(mobile_ads, sig):
                print(f"[+] MobileAds init disabled: {sig}")

    # Auto-init ContentProvider -> patch the config object's attachInfo().
    provider = find_class(dec, "Lcom/google/android/gms/ads/MobileAdsInitProvider;")
    if provider is not None:
        m = re.search(r"\.field private final \w+:L([^;]+);", provider.read_text())
        if m:
            target = find_class(dec, f"L{m.group(1)};")
            if target and noop_void(
                target, "attachInfo(Landroid/content/Context;Landroid/content/pm/ProviderInfo;)V"
            ):
                print(f"[+] MobileAds auto-init disabled: {target.name}")


# AdRequest is renamed to `c` in some R8-processed bundles.
AD_REQUEST = r"(?:Lcom/google/android/gms/ads/AdRequest;|Lcom/google/android/gms/ads/c;)"


def disable_banners(dec: Path) -> None:
    base = find_class(dec, "Lcom/google/android/gms/ads/BaseAdView;")
    if base is None:
        print("[=] BaseAdView not bundled, skipping banner patch")
        return
    for line, sig in method_decls(base):
        if "public" in line and re.fullmatch(
            r"[a-zA-Z0-9_$]+\(" + AD_REQUEST + r"\)V", sig
        ):
            if noop_void(base, sig):
                print(f"[+] banner load disabled: {sig}")


def disable_ad_unit_ids(dec: Path) -> None:
    """Null out AdMob ad unit IDs.

    The new Google Mobile Ads SDK is often R8-repackaged (e.g. under
    ``ads_mobile_sdk``), so the class-based patches above cannot find it.
    Replacing every ``ca-app-pub-<id>/<unit>`` with a zero unit makes all
    requests unfillable while leaving the app otherwise untouched.
    """
    replacement = "ca-app-pub-0000000000000000/0000000000"
    pattern = re.compile(r"ca-app-pub-\d{16}/\d+")
    count = 0
    for d in smali_dirs(dec):
        for f in d.rglob("*.smali"):
            text = f.read_text(errors="ignore")
            new, n = pattern.subn(replacement, text)
            if n:
                f.write_text(new)
                count += n
    # IDs sometimes live in string resources instead of code.
    for f in (dec / "res").rglob("*.xml"):
        text = f.read_text(errors="ignore")
        new, n = pattern.subn(replacement, text)
        if n:
            f.write_text(new)
            count += n
    if count:
        print(f"[+] ad unit ids nulled: {count}")


def disable_ad_loads(dec: Path) -> None:
    pat = re.compile(
        r"^\.method public static [a-zA-Z0-9_$]+\("
        r"Landroid/content/Context;Ljava/lang/String;" + AD_REQUEST + r"[^\n]*\)V$"
    )
    count = 0
    for d in smali_dirs(dec):
        for f in d.rglob("*.smali"):
            try:
                head = f.read_text(errors="ignore")
            except OSError:
                continue
            if (
                "play-services-ads-api" not in head[:400]
                and "com/google/android/gms/ads" not in str(f)
            ):
                continue
            for line in head.splitlines():
                if pat.match(line):
                    sig = line[len(".method public static "):]
                    if noop_void(f, sig):
                        count += 1
                        print(f"[+] ad load disabled: {f.name} :: {sig}")
    if not count:
        print("[=] no static ad load entry points found")


def apply_rules(dec: Path, rules_file: Path) -> None:
    data = json.loads(rules_file.read_text())
    for rule in data.get("rules", []):
        target = find_class(dec, rule["class"])
        if target is None:
            print(f"[!] rule class not found: {rule['class']}")
            continue
        method = rule["method"]
        ret = rule.get("return", "void")
        if ret == "void":
            ok = noop_void(target, method)
        elif isinstance(ret, bool):
            ok = noop_bool(target, method, ret)
        else:
            print(f"[!] unsupported return type in rule: {ret}")
            continue
        print(f"[{'✅' if ok else '!'}] rule {rule['class']} -> {method} = {ret}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("decoded", type=Path)
    ap.add_argument("--rules", type=Path)
    args = ap.parse_args()

    dec = args.decoded.resolve()
    if not (dec / "AndroidManifest.xml").exists():
        sys.exit(f"[!] {dec} does not look like apktool output")

    bypass_pairip(dec)
    disable_mobileads(dec)
    disable_banners(dec)
    disable_ad_loads(dec)
    if args.rules:
        apply_rules(dec, args.rules)
    print("[done]")


if __name__ == "__main__":
    main()
