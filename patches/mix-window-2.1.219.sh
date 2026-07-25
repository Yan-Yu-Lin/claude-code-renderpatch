#!/usr/bin/env bash
# Add the provider-aware context-window patch and explicit subagent model-
# override routing fix to the verified 2.1.219 V2 full-redraw artifact.
# Both edits are applied before one final codesign pass. This never modifies
# the redraw-only artifact. For a direct-from-stock cumulative build, prefer
# full-redraw-mix-window-2.1.219.sh.
set -euo pipefail

VERSION="2.1.219"
PATCH_DIR="$HOME/.local/share/claude/patched"
INPUT="$PATCH_DIR/claude-$VERSION-full-redraw"
OUTPUT="$PATCH_DIR/claude-$VERSION-full-redraw-mix-window"
STOCK="$HOME/.local/share/claude/versions/$VERSION"
EXPECTED_INPUT_SHA="e90607a9b868c0b49424f99a367e9810ebbc1c65bf8d3c0d31a923166760329f"

for command in python3 shasum codesign trash; do
  command -v "$command" >/dev/null || { echo "Required command not found: $command" >&2; exit 1; }
done
[[ -f "$INPUT" && -f "$STOCK" ]] || { echo "Expected redraw-only input or stock binary is missing" >&2; exit 1; }
ACTUAL_INPUT_SHA="$(shasum -a 256 "$INPUT" | awk '{print $1}')"
[[ "$ACTUAL_INPUT_SHA" == "$EXPECTED_INPUT_SHA" ]] || {
  echo "Refusing to patch: redraw-only input hash differs" >&2
  echo "Expected: $EXPECTED_INPUT_SHA" >&2
  echo "Actual:   $ACTUAL_INPUT_SHA" >&2
  exit 1
}

TMP_PATCH="$(mktemp "$PATCH_DIR/.claude-$VERSION-full-redraw-mix-window.XXXXXX")"
TMP_ENTITLEMENTS="$(mktemp "$PATCH_DIR/.claude-entitlements.XXXXXX")"
cleanup() {
  local paths=()
  [[ ! -e "$TMP_PATCH" ]] || paths+=("$TMP_PATCH")
  [[ ! -e "$TMP_ENTITLEMENTS" ]] || paths+=("$TMP_ENTITLEMENTS")
  ((${#paths[@]} == 0)) || trash "${paths[@]}"
}
trap cleanup EXIT

cp "$INPUT" "$TMP_PATCH"
chmod +x "$TMP_PATCH"

python3 - "$TMP_PATCH" <<'PY'
import sys

path = sys.argv[1]
data = open(path, "rb").read()


def padded(old: bytes, code: bytes) -> bytes:
    if len(code) > len(old):
        raise SystemExit(f"replacement is longer: {len(code)} > {len(old)}")
    return code + b" " * (len(old) - len(code))


patches = [
    (
        "mix-window-provider-table",
        b'let n=Z.CLAUDE_CODE_MAX_CONTEXT_TOKENS;if(n!==void 0&&n>0&&!lo(Ei(e)).startsWith("claude-"))return n;return her',
        padded(
            b'let n=Z.CLAUDE_CODE_MAX_CONTEXT_TOKENS;if(n!==void 0&&n>0&&!lo(Ei(e)).startsWith("claude-"))return n;return her',
            b'let n=lo(Ei(e));if(n.startsWith("kimi"))return 262144;if(!n.startsWith("claude-"))return 372e3;return her',
        ),
    ),
    (
        "subagent-explicit-model-resolution",
        b'if(r){if(r==="inherit")return i();if(Vrd(r,t))return t;let p=c(Grd(Ei(r)),r);if(!Hl(p))return s(r,p);return p}',
        b'if(r){if(r==="inherit")return i();if(!1&&r&&t)return t;let p=c(Grd(Ei(r)),r);if(!Hl(p))return s(r,p);return p}',
    ),
]

for name, old, new in patches:
    if len(old) != len(new):
        raise SystemExit(f"{name}: length mismatch")
    old_count = data.count(old)
    new_count = data.count(new)
    if old_count != 1 or new_count != 0:
        raise SystemExit(
            f"{name}: expected old=1/new=0, found "
            f"old={old_count}/new={new_count}"
        )
    print(f"{name}: offset={data.find(old)} length={len(old)}")
    data = data.replace(old, new, 1)
    if data.count(old) != 0 or data.count(new) != 1:
        raise SystemExit(f"{name}: post-patch verification failed")

open(path, "wb").write(data)
print("mix-window and subagent-routing byte patches applied")
PY

codesign -d --entitlements :- "$STOCK" >"$TMP_ENTITLEMENTS" 2>/dev/null
[[ -s "$TMP_ENTITLEMENTS" ]] || { echo "Failed to extract stock entitlements" >&2; exit 1; }
codesign --force --sign - --identifier com.anthropic.claude-code --entitlements "$TMP_ENTITLEMENTS" "$TMP_PATCH"
codesign --verify --strict --verbose=2 "$TMP_PATCH"
mv "$TMP_PATCH" "$OUTPUT"

echo "Installed combined routing-fixed artifact: $OUTPUT"
echo "SHA-256: $(shasum -a 256 "$OUTPUT" | awk '{print $1}')"
"$OUTPUT" --version
