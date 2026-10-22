#!/usr/bin/env bash
# Install/update the user-level Claude Code skill from this project.
#   ./sync-skill.sh                 -> ~/.claude/skills/android-ad-removal
#   ./sync-skill.sh /path/to/skill  -> custom destination
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$HOME/.claude/skills/android-ad-removal}"

rm -rf "$DEST/scripts/rules"
mkdir -p "$DEST/scripts/rules" "$DEST/references"
install -m 755 "$SRC/remove_ads.py" "$SRC/patch_apk.py" "$SRC/gen_rules.py" "$DEST/scripts/"
find "$SRC/rules" -maxdepth 1 -name '*.json' -exec cp {} "$DEST/scripts/rules/" \;
cp "$SRC/rules/README.md" "$DEST/scripts/rules/README.md"
cp "$SRC/skill/SKILL.md" "$DEST/SKILL.md"
cp "$SRC"/skill/references/*.md "$DEST/references/"

echo "[+] skill installed -> $DEST"
echo "    restart Claude Code (or start a new session) to pick it up"
