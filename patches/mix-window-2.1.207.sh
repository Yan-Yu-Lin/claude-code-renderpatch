#!/usr/bin/env bash
# Add the "mix-window" patch on top of the existing 2.1.207 full-redraw binary.
#
# Hardcodes per-provider context windows into the model-window resolver so
# claude-mix sessions are ALWAYS right, with no dependence on env vars or the
# server-overwritable ~/.claude.json autoCompactWindowsCache:
#   kimi*     -> 262144  (real upstream limit of K3 / K2.7 on Arthur's tier)
#   other non-claude (gpt-5.6-sol etc.) -> 372000
#   claude-*  -> unchanged (native resolution; fable [1m] path untouched)
#
# The CLAUDE_CODE_MAX_CONTEXT_TOKENS env override is REMOVED by this patch —
# the table above is authoritative. Kimi cache injection in claude-mix/mix-sub
# becomes redundant (harmless if left).
#
# Patches the full-redraw binary IN PLACE (with a .pre-mix-window backup).
# Stock binary and ~/.local/bin/claude are never modified.

set -euo pipefail

VERSION="2.1.207"
PATCH_DIR="$HOME/.local/share/claude/patched"
TARGET="$PATCH_DIR/claude-$VERSION-full-redraw"
BACKUP="$TARGET.pre-mix-window"
STOCK="$HOME/.local/share/claude/versions/$VERSION"

# full-redraw build produced by full-redraw-2.1.207.sh
EXPECTED_INPUT_SHA="cce71f3eb4378e35c3067b75c63a93b858faf346928feb433d0f01f152766b66"

for command in python3 shasum codesign trash; do
  command -v "$command" >/dev/null || {
    echo "Required command not found: $command" >&2
    exit 1
  }
done

[[ -f "$TARGET" ]] || { echo "full-redraw binary not found: $TARGET" >&2; exit 1; }
[[ -f "$STOCK" ]] || { echo "Stock binary (entitlements source) not found: $STOCK" >&2; exit 1; }

ACTUAL_INPUT_SHA="$(shasum -a 256 "$TARGET" | awk '{print $1}')"
if [[ "$ACTUAL_INPUT_SHA" != "$EXPECTED_INPUT_SHA" ]]; then
  echo "Refusing to patch: unexpected full-redraw binary hash (already mix-window patched, or a different build?)" >&2
  echo "Expected: $EXPECTED_INPUT_SHA" >&2
  echo "Actual:   $ACTUAL_INPUT_SHA" >&2
  exit 1
fi

TMP_PATCH="$(mktemp "$PATCH_DIR/.claude-$VERSION-mix-window.XXXXXX")"
TMP_ENTITLEMENTS="$(mktemp "$PATCH_DIR/.claude-entitlements.XXXXXX")"
cleanup() {
  local paths=()
  [[ ! -e "$TMP_PATCH" ]] || paths+=("$TMP_PATCH")
  [[ ! -e "$TMP_ENTITLEMENTS" ]] || paths+=("$TMP_ENTITLEMENTS")
  ((${#paths[@]} == 0)) || trash "${paths[@]}"
}
trap cleanup EXIT

cp "$TARGET" "$TMP_PATCH"
chmod +x "$TMP_PATCH"

python3 - "$TMP_PATCH" <<'PY'
import sys

path = sys.argv[1]
data = open(path, "rb").read()


def padded(old: bytes, code: bytes) -> bytes:
    """Pad executable replacement code with spaces to preserve byte length."""
    if len(code) > len(old):
        raise SystemExit(
            f"Replacement is longer than original: {len(code)} > {len(old)}\n"
            f"old={old!r}\ncode={code!r}"
        )
    return code + b" " * (len(old) - len(code))


# Inside uyc(e,t) — the per-model max-window resolver (2.1.207). The original
# tail reads the CLAUDE_CODE_MAX_CONTEXT_TOKENS env for non-claude models and
# falls back to EPr (200000). Replace with a hardcoded provider table. The
# earlier branches of uyc (fable [1m]/1M handling, sonnet-4-6 experiment) are
# left untouched, so claude-* models keep native behavior.
patches = [
    (
        "mix-window-provider-table",
        b'let n=be.CLAUDE_CODE_MAX_CONTEXT_TOKENS;if(n!==void 0&&n>0&&!ao(Zo(e)).startsWith("claude-"))return n;return EPr',
        padded(
            b'let n=be.CLAUDE_CODE_MAX_CONTEXT_TOKENS;if(n!==void 0&&n>0&&!ao(Zo(e)).startsWith("claude-"))return n;return EPr',
            b'let o=ao(Zo(e));if(o.startsWith("kimi"))return 262144;if(!o.startsWith("claude-"))return 372e3;return EPr',
        ),
    ),
]

for name, old, new in patches:
    if len(old) != len(new):
        raise SystemExit(f"{name}: length mismatch: old={len(old)}, new={len(new)}")
    count = data.count(old)
    if count != 1:
        raise SystemExit(
            f"{name}: expected exactly one old-pattern match, found {count}: {old!r}"
        )
    offset = data.find(old)
    print(f"{name}: offset={offset} length={len(old)}")
    data = data.replace(old, new)

open(path, "wb").write(data)
print("mix-window byte patch applied")
PY

codesign -d --entitlements :- "$STOCK" >"$TMP_ENTITLEMENTS" 2>/dev/null
if [[ ! -s "$TMP_ENTITLEMENTS" ]]; then
  echo "Failed to extract stock entitlements" >&2
  exit 1
fi

codesign --force \
  --sign - \
  --identifier com.anthropic.claude-code \
  --entitlements "$TMP_ENTITLEMENTS" \
  "$TMP_PATCH"

codesign --verify --strict --verbose=2 "$TMP_PATCH"

cp "$TARGET" "$BACKUP"
mv -f "$TMP_PATCH" "$TARGET"

echo "Patched in place: $TARGET"
echo "Backup:           $BACKUP"
echo "SHA-256:          $(shasum -a 256 "$TARGET" | awk '{print $1}')"
echo "--- version check ---"
"$TARGET" --version
