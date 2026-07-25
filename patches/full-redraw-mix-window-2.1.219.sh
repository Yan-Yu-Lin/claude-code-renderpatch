#!/usr/bin/env bash
# Reproduce the cumulative Claude Code 2.1.219 custom build directly from stock:
#   1. V2 full-redraw terminal fixes
#   2. provider-aware claude-mix context windows
#   3. explicit subagent model-override routing fix
#
# All nine __BUN edits are equal-length and receive one final codesign pass.
# The stock binary and normal Claude launcher are never modified.

set -euo pipefail

VERSION="2.1.219"
STOCK="$HOME/.local/share/claude/versions/$VERSION"
PATCH_DIR="$HOME/.local/share/claude/patched"
OUTPUT="$PATCH_DIR/claude-$VERSION-full-redraw-mix-window"
BACKUP="$OUTPUT.pre-routing-fix"
EXPECTED_STOCK_SHA="a8e806faaefac53c7a0f26523d8a45c60dbef3407b14ef990c75765d08febc82"
EXPECTED_OUTPUT_SHA="a3423442e91548f046b3c7e723a41266935ae6137e4ffdc26e932c3d8cfc25f2"

for command in python3 shasum codesign trash; do
  command -v "$command" >/dev/null || {
    echo "Required command not found: $command" >&2
    exit 1
  }
done

[[ -f "$STOCK" ]] || {
  echo "Stock Claude Code $VERSION binary not found: $STOCK" >&2
  exit 1
}

ACTUAL_STOCK_SHA="$(shasum -a 256 "$STOCK" | awk '{print $1}')"
if [[ "$ACTUAL_STOCK_SHA" != "$EXPECTED_STOCK_SHA" ]]; then
  echo "Refusing to patch: unexpected stock $VERSION binary hash" >&2
  echo "Expected: $EXPECTED_STOCK_SHA" >&2
  echo "Actual:   $ACTUAL_STOCK_SHA" >&2
  exit 1
fi

mkdir -p "$PATCH_DIR"
TMP_PATCH=""
TMP_ENTITLEMENTS=""
cleanup() {
  local paths=()
  [[ -z "$TMP_PATCH" || ! -e "$TMP_PATCH" ]] || paths+=("$TMP_PATCH")
  [[ -z "$TMP_ENTITLEMENTS" || ! -e "$TMP_ENTITLEMENTS" ]] || paths+=("$TMP_ENTITLEMENTS")
  ((${#paths[@]} == 0)) || trash "${paths[@]}"
}
trap cleanup EXIT
TMP_PATCH="$(mktemp "$PATCH_DIR/.claude-$VERSION-cumulative.XXXXXX")"
TMP_ENTITLEMENTS="$(mktemp "$PATCH_DIR/.claude-entitlements.XXXXXX")"

cp "$STOCK" "$TMP_PATCH"
chmod +x "$TMP_PATCH"

python3 - "$TMP_PATCH" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()


def padded(old: bytes, code: bytes) -> bytes:
    if len(code) > len(old):
        raise SystemExit(
            f"replacement is longer: old={len(old)} code={len(code)}\n"
            f"old={old!r}\ncode={code!r}"
        )
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
        padded(
            b'case"clearTerminal":s+=a.altScreen?Ims():gXr(a.viewportRows);break;',
            b'case"clearTerminal":s+=Ims();break;',
        ),
    ),
    (
        "reset-replay-from-row-zero",
        b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new Ahs({x:0,y:s},e.viewport.width);",
        padded(
            b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new Ahs({x:0,y:s},e.viewport.width);",
            b"let s=0,a=new Ahs({x:0,y:s},e.viewport.width);",
        ),
    ),
    (
        "force-authoritative-expand-redraw",
        b'M("tengu_toggle_transcript",{is_entering:Oui!=="transcript",show_all:Yvt,message_count:Xvt,open_dialog_count:iM.getState().open.length}),GOn(Y2S),Jvt(!1)',
        padded(
            b'M("tengu_toggle_transcript",{is_entering:Oui!=="transcript",show_all:Yvt,message_count:Xvt,open_dialog_count:iM.getState().open.length}),GOn(Y2S),Jvt(!1)',
            b'GOn(Y2S),Jvt(!1),Oui!=="transcript"&&setTimeout(Q2S,50)',
        ),
    ),
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
        raise SystemExit(
            f"{name}: length mismatch: old={len(old)} new={len(new)}"
        )
    old_count = data.count(old)
    new_count = data.count(new)
    if old_count != 1 or new_count != 0:
        raise SystemExit(
            f"{name}: expected old=1/new=0, found "
            f"old={old_count}/new={new_count}"
        )
    offset = data.find(old)
    print(f"{name}: offset={offset} length={len(old)}")
    data = data.replace(old, new, 1)
    if data.count(old) != 0 or data.count(new) != 1:
        raise SystemExit(f"{name}: immediate post-patch verification failed")

# Later overlapping patches may refine an earlier replacement, so the durable
# final invariant is that every stock anchor is gone. The two non-overlapping
# provider/routing replacements must each remain unique.
for name, old, _ in patches:
    if data.count(old) != 0:
        raise SystemExit(f"{name}: stock anchor remains after cumulative patch")

for name, _, new in patches[-2:]:
    if data.count(new) != 1:
        raise SystemExit(f"{name}: expected one final replacement, found {data.count(new)}")

path.write_bytes(data)
print("All nine equal-length cumulative patches applied and verified")
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

ACTUAL_OUTPUT_SHA="$(shasum -a 256 "$TMP_PATCH" | awk '{print $1}')"
if [[ "$ACTUAL_OUTPUT_SHA" != "$EXPECTED_OUTPUT_SHA" ]]; then
  echo "Refusing to install: cumulative output hash differs" >&2
  echo "Expected: $EXPECTED_OUTPUT_SHA" >&2
  echo "Actual:   $ACTUAL_OUTPUT_SHA" >&2
  exit 1
fi

# Preserve the pre-routing working build. Never overwrite an existing backup.
if [[ -e "$OUTPUT" && ! -e "$BACKUP" ]]; then
  cp "$OUTPUT" "$BACKUP"
  echo "Backed up previous combined build: $BACKUP"
elif [[ -e "$BACKUP" ]]; then
  echo "Preserving existing backup: $BACKUP"
fi

mv -f "$TMP_PATCH" "$OUTPUT"

echo "Installed cumulative artifact: $OUTPUT"
echo "SHA-256: $ACTUAL_OUTPUT_SHA"
