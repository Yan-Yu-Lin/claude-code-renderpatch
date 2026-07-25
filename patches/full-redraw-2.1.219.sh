#!/usr/bin/env bash
# Build a versioned Claude Code 2.1.219 V2 full-redraw test artifact.
set -euo pipefail

VERSION="2.1.219"
ORIG="$HOME/.local/share/claude/versions/$VERSION"
PATCH_DIR="$HOME/.local/share/claude/patched"
PATCH="$PATCH_DIR/claude-$VERSION-full-redraw"
LAUNCHER="$HOME/.local/bin/claude-full-redraw-$VERSION"
EXPECTED_STOCK_SHA="a8e806faaefac53c7a0f26523d8a45c60dbef3407b14ef990c75765d08febc82"

for command in python3 shasum codesign trash; do
  command -v "$command" >/dev/null || { echo "Required command not found: $command" >&2; exit 1; }
done
[[ -f "$ORIG" ]] || { echo "Stock Claude Code $VERSION binary not found: $ORIG" >&2; exit 1; }

ACTUAL_STOCK_SHA="$(shasum -a 256 "$ORIG" | awk '{print $1}')"
[[ "$ACTUAL_STOCK_SHA" == "$EXPECTED_STOCK_SHA" ]] || {
  echo "Refusing to patch: unexpected stock binary hash" >&2
  echo "Expected: $EXPECTED_STOCK_SHA" >&2
  echo "Actual:   $ACTUAL_STOCK_SHA" >&2
  exit 1
}

mkdir -p "$PATCH_DIR" "$(dirname "$LAUNCHER")"
TMP_PATCH="$(mktemp "$PATCH_DIR/.claude-$VERSION-full-redraw.XXXXXX")"
TMP_ENTITLEMENTS="$(mktemp "$PATCH_DIR/.claude-entitlements.XXXXXX")"
cleanup() {
  local paths=()
  [[ ! -e "$TMP_PATCH" ]] || paths+=("$TMP_PATCH")
  [[ ! -e "$TMP_ENTITLEMENTS" ]] || paths+=("$TMP_ENTITLEMENTS")
  ((${#paths[@]} == 0)) || trash "${paths[@]}"
}
trap cleanup EXIT

cp "$ORIG" "$TMP_PATCH"
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
        "transcript-show-all",
        b"showAllInTranscript:fr,onOpenRateLimitOptions:CCt,isLoading:bs,scrollRef:yt,jumpRef:Gr,onSearchMatchesChange:Tm,scanElement:rp,setPositions:Wh,disableRenderCap:Cr,hideWelcomeChrome:I}",
        b"showAllInTranscript:!0,onOpenRateLimitOptions:CCt,isLoading:bs,scrollRef:yt,jumpRef:Gr,onSearchMatchesChange:Tm,scanElement:rp,setPositions:Wh,disableRenderCap:Cr,hideWelcomeChrome:I}",
    ),
    (
        "transcript-disable-render-cap",
        b"disableRenderCap:Cr,hideWelcomeChrome:I})",
        b"disableRenderCap:!0,hideWelcomeChrome:I})",
    ),
    (
        "remove-pre-normalization-cap",
        b"let te=!re&&!H?Vhf(e,ce,oe*2):0",
        padded(b"let te=!re&&!H?Vhf(e,ce,oe*2):0", b"let te=0"),
    ),
    (
        "remove-final-render-cap",
        b"let He=!re&&!H?Vhf(at,se,oe):0",
        padded(b"let He=!re&&!H?Vhf(at,se,oe):0", b"let He=0"),
    ),
    (
        "destructive-main-screen-reset",
        b'case"clearTerminal":s+=a.altScreen?Ims():gXr(a.viewportRows);break;',
        padded(b'case"clearTerminal":s+=a.altScreen?Ims():gXr(a.viewportRows);break;', b'case"clearTerminal":s+=Ims();break;'),
    ),
    (
        "reset-replay-from-row-zero",
        b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new Ahs({x:0,y:s},e.viewport.width);",
        padded(b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new Ahs({x:0,y:s},e.viewport.width);", b"let s=0,a=new Ahs({x:0,y:s},e.viewport.width);"),
    ),
    (
        "force-authoritative-expand-redraw",
        b'M("tengu_toggle_transcript",{is_entering:Oui!=="transcript",show_all:Yvt,message_count:Xvt,open_dialog_count:iM.getState().open.length}),GOn(Y2S),Jvt(!1)',
        padded(b'M("tengu_toggle_transcript",{is_entering:Oui!=="transcript",show_all:Yvt,message_count:Xvt,open_dialog_count:iM.getState().open.length}),GOn(Y2S),Jvt(!1)', b'GOn(Y2S),Jvt(!1),Oui!=="transcript"&&setTimeout(Q2S,50)'),
    ),
]

for name, old, new in patches:
    if len(old) != len(new):
        raise SystemExit(f"{name}: length mismatch")
    count = data.count(old)
    if count != 1:
        raise SystemExit(f"{name}: expected exactly one old-pattern match, found {count}")
    print(f"{name}: offset={data.find(old)} length={len(old)}")
    data = data.replace(old, new)

open(path, "wb").write(data)
print("All seven equal-length V2 patches applied")
PY

codesign -d --entitlements :- "$ORIG" >"$TMP_ENTITLEMENTS" 2>/dev/null
[[ -s "$TMP_ENTITLEMENTS" ]] || { echo "Failed to extract stock entitlements" >&2; exit 1; }
codesign --force --sign - --identifier com.anthropic.claude-code --entitlements "$TMP_ENTITLEMENTS" "$TMP_PATCH"
codesign --verify --strict --verbose=2 "$TMP_PATCH"
mv "$TMP_PATCH" "$PATCH"
ln -sfn "$PATCH" "$LAUNCHER"

echo "Installed test artifact: $PATCH"
echo "Test launcher: $LAUNCHER"
echo "SHA-256: $(shasum -a 256 "$PATCH" | awk '{print $1}')"
"$LAUNCHER" --version
