set -e

ORIG="$HOME/.local/share/claude/versions/2.1.203"
PATCH_DIR="$HOME/.local/share/claude/patched"
PATCH="$PATCH_DIR/claude-2.1.203-full-history"
ENTITLEMENTS="$PATCH_DIR/claude-entitlements.plist"

mkdir -p "$PATCH_DIR"

EXPECTED_SHA="57b5aec68a35f42036bd2f82836d91c2d2990c2d589fb3465e3ee87142af9a1e"
ACTUAL_SHA="$(shasum -a 256 "$ORIG" | awk '{print $1}')"

if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
    echo "Refusing to patch: unexpected 2.1.203 binary hash"
    echo "Expected: $EXPECTED_SHA"
    echo "Actual:   $ACTUAL_SHA"
    exit 1
fi

cp "$ORIG" "$PATCH"

python3 - "$PATCH" <<'PY'
import sys

path = sys.argv[1]
data = open(path, "rb").read()

patches = [
    (
        b"showAllInTranscript:Gt,onOpenRateLimitOptions:ENt,isLoading:Fe,scrollRef:mt",
        b"showAllInTranscript:!0,onOpenRateLimitOptions:ENt,isLoading:Fe,scrollRef:mt",
    ),
    (
        b"disableRenderCap:Or})",
        b"disableRenderCap:!0})",
    ),
]

for old, new in patches:
    assert len(old) == len(new)
    count = data.count(old)
    if count != 1:
        raise SystemExit(
            f"Refusing to patch: expected one occurrence, found {count}: {old!r}"
        )
    data = data.replace(old, new)

open(path, "wb").write(data)
print("byte patch applied")
PY

# Preserve the original entitlements while replacing Anthropic's now-invalid
# signature with a local ad-hoc signature.
codesign -d --entitlements :- "$ORIG" > "$ENTITLEMENTS" 2>/dev/null

codesign --force \
    --sign - \
    --identifier com.anthropic.claude-code \
    --entitlements "$ENTITLEMENTS" \
    "$PATCH"

codesign --verify --strict --verbose=2 "$PATCH"

ln -sfn "$PATCH" "$HOME/.local/bin/claude-full-history"

echo "--- version check ---"
"$HOME/.local/bin/claude-full-history" --version
