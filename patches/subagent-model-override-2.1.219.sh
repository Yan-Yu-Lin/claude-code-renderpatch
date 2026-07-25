#!/usr/bin/env bash
# Add the explicit subagent model-override routing fix to the existing verified
# Claude Code 2.1.219 full-redraw + mix-window artifact.
#
# For clean rebuilds prefer full-redraw-mix-window-2.1.219.sh, which applies all
# cumulative edits directly to stock and performs one final codesign pass.

set -euo pipefail

VERSION="2.1.219"
PATCH_DIR="$HOME/.local/share/claude/patched"
TARGET="$PATCH_DIR/claude-$VERSION-full-redraw-mix-window"
BACKUP="$TARGET.pre-routing-fix"
STOCK="$HOME/.local/share/claude/versions/$VERSION"
EXPECTED_INPUT_SHA="3abedf608d8769713417d6cbeee6f8a8d2c0f653df9fb86976863238fdcbb884"

for command in python3 shasum codesign trash; do
  command -v "$command" >/dev/null || {
    echo "Required command not found: $command" >&2
    exit 1
  }
done

[[ -f "$TARGET" && -f "$STOCK" ]] || {
  echo "Expected combined artifact or stock binary is missing" >&2
  exit 1
}

ACTUAL_INPUT_SHA="$(shasum -a 256 "$TARGET" | awk '{print $1}')"
if [[ "$ACTUAL_INPUT_SHA" != "$EXPECTED_INPUT_SHA" ]]; then
  echo "Refusing to patch: combined input hash differs" >&2
  echo "Expected: $EXPECTED_INPUT_SHA" >&2
  echo "Actual:   $ACTUAL_INPUT_SHA" >&2
  exit 1
fi

TMP_PATCH=""
TMP_ENTITLEMENTS=""
cleanup() {
  local paths=()
  [[ -z "$TMP_PATCH" || ! -e "$TMP_PATCH" ]] || paths+=("$TMP_PATCH")
  [[ -z "$TMP_ENTITLEMENTS" || ! -e "$TMP_ENTITLEMENTS" ]] || paths+=("$TMP_ENTITLEMENTS")
  ((${#paths[@]} == 0)) || trash "${paths[@]}"
}
trap cleanup EXIT
TMP_PATCH="$(mktemp "$PATCH_DIR/.claude-$VERSION-routing-fix.XXXXXX")"
TMP_ENTITLEMENTS="$(mktemp "$PATCH_DIR/.claude-entitlements.XXXXXX")"

cp "$TARGET" "$TMP_PATCH"
chmod +x "$TMP_PATCH"

python3 - "$TMP_PATCH" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()
old = (
    b'if(r){if(r==="inherit")return i();if(Vrd(r,t))return t;'
    b'let p=c(Grd(Ei(r)),r);if(!Hl(p))return s(r,p);return p}'
)
new = (
    b'if(r){if(r==="inherit")return i();if(!1&&r&&t)return t;'
    b'let p=c(Grd(Ei(r)),r);if(!Hl(p))return s(r,p);return p}'
)

if len(old) != len(new):
    raise SystemExit(f"length mismatch: old={len(old)} new={len(new)}")
old_count = data.count(old)
new_count = data.count(new)
if old_count != 1 or new_count != 0:
    raise SystemExit(
        f"subagent-explicit-model-resolution: expected old=1/new=0, "
        f"found old={old_count}/new={new_count}"
    )
offset = data.find(old)
print(f"subagent-explicit-model-resolution: offset={offset} length={len(old)}")
data = data.replace(old, new, 1)
if data.count(old) != 0 or data.count(new) != 1:
    raise SystemExit("subagent-explicit-model-resolution: post-patch verification failed")
path.write_bytes(data)
PY

codesign -d --entitlements :- "$STOCK" >"$TMP_ENTITLEMENTS" 2>/dev/null
[[ -s "$TMP_ENTITLEMENTS" ]] || {
  echo "Failed to extract stock entitlements" >&2
  exit 1
}

codesign --force \
  --sign - \
  --identifier com.anthropic.claude-code \
  --entitlements "$TMP_ENTITLEMENTS" \
  "$TMP_PATCH"
codesign --verify --strict --verbose=2 "$TMP_PATCH"
"$TMP_PATCH" --version

if [[ -e "$BACKUP" ]]; then
  echo "Refusing to overwrite existing backup: $BACKUP" >&2
  exit 1
fi
cp "$TARGET" "$BACKUP"
mv -f "$TMP_PATCH" "$TARGET"

echo "Patched in place: $TARGET"
echo "Backup:           $BACKUP"
echo "SHA-256:          $(shasum -a 256 "$TARGET" | awk '{print $1}')"
