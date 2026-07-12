#!/usr/bin/env bash
# Reproduce the Claude Code 2.1.207 "full-redraw" patch from the stock binary.
#
# Installs a separate binary and version-specific test launcher. The stock
# Claude Code binary, ~/.local/bin/claude, and existing custom launchers are
# never modified.

set -euo pipefail

VERSION="2.1.207"
ORIG="$HOME/.local/share/claude/versions/$VERSION"
PATCH_DIR="$HOME/.local/share/claude/patched"
PATCH="$PATCH_DIR/claude-$VERSION-full-redraw"
LAUNCHER="$HOME/.local/bin/claude-full-redraw-207"

EXPECTED_STOCK_SHA="1397a062c6889675055e3314dd956376ac51262a7734ad9e819c26975d71547a"
EXPECTED_PATCHED_SHA="cce71f3eb4378e35c3067b75c63a93b858faf346928feb433d0f01f152766b66"

for command in python3 shasum codesign trash; do
  command -v "$command" >/dev/null || {
    echo "Required command not found: $command" >&2
    exit 1
  }
done

if [[ ! -f "$ORIG" ]]; then
  echo "Stock Claude Code $VERSION binary not found: $ORIG" >&2
  exit 1
fi

ACTUAL_STOCK_SHA="$(shasum -a 256 "$ORIG" | awk '{print $1}')"
if [[ "$ACTUAL_STOCK_SHA" != "$EXPECTED_STOCK_SHA" ]]; then
  echo "Refusing to patch: unexpected stock $VERSION binary hash" >&2
  echo "Expected: $EXPECTED_STOCK_SHA" >&2
  echo "Actual:   $ACTUAL_STOCK_SHA" >&2
  exit 1
fi

mkdir -p "$PATCH_DIR" "$(dirname "$LAUNCHER")"
TMP_PATCH="$(mktemp "$PATCH_DIR/.claude-$VERSION-full-redraw.XXXXXX")"
TMP_ENTITLEMENTS="$(mktemp "$PATCH_DIR/.claude-entitlements.XXXXXX.plist")"
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
    """Pad executable replacement code with spaces to preserve byte length."""
    if len(code) > len(old):
        raise SystemExit(
            f"Replacement is longer than original: {len(code)} > {len(old)}\n"
            f"old={old!r}\ncode={code!r}"
        )
    return code + b" " * (len(old) - len(code))


# The first two entries force an uncapped detailed transcript. The next four
# keep complete prompt-mode frames and make resets destructive row-zero
# replays. The final patch schedules one authoritative redraw after React has
# had enough time to commit transcript state on 2.1.207; a zero-delay timer
# produced two ED2/ED3 replays in PTY testing, while 50 ms produced exactly one.
patches = [
    (
        "transcript-show-all",
        b"showAllInTranscript:jt,onOpenRateLimitOptions:XH,isLoading:Rt,scrollRef:pt",
        b"showAllInTranscript:!0,onOpenRateLimitOptions:XH,isLoading:Rt,scrollRef:pt",
    ),
    (
        "transcript-disable-render-cap",
        b"disableRenderCap:_r})",
        b"disableRenderCap:!0})",
    ),
    (
        "remove-pre-normalization-cap",
        b"let oe=!X&&!P?xap(e,ie,re*2):0",
        padded(b"let oe=!X&&!P?xap(e,ie,re*2):0", b"let oe=0"),
    ),
    (
        "remove-final-render-cap",
        b"let Ae=!X&&!P?xap(Ke,ae,re):0",
        padded(b"let Ae=!X&&!P?xap(Ke,ae,re):0", b"let Ae=0"),
    ),
    (
        "destructive-main-screen-reset",
        b'case"clearTerminal":s+=a.altScreen?pIi():fIi(a.viewportRows);break;',
        padded(
            b'case"clearTerminal":s+=a.altScreen?pIi():fIi(a.viewportRows);break;',
            b'case"clearTerminal":s+=pIi();break;',
        ),
    ),
    (
        "reset-replay-from-row-zero",
        b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new wDi({x:0,y:s},e.viewport.width);",
        padded(
            b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new wDi({x:0,y:s},e.viewport.width);",
            b"let s=0,a=new wDi({x:0,y:s},e.viewport.width);",
        ),
    ),
    (
        "force-authoritative-expand-redraw",
        b'N("tengu_toggle_transcript",{is_entering:$Bo!=="transcript",show_all:bft,message_count:Sft,open_dialog_count:OP.getState().open.length}),Vun(Vsb),Tft(!1)',
        padded(
            b'N("tengu_toggle_transcript",{is_entering:$Bo!=="transcript",show_all:bft,message_count:Sft,open_dialog_count:OP.getState().open.length}),Vun(Vsb),Tft(!1)',
            b'Vun(Vsb),Tft(!1),$Bo!=="transcript"&&setTimeout(Ysb,50)',
        ),
    ),
]

for name, old, new in patches:
    if len(old) != len(new):
        raise SystemExit(
            f"{name}: length mismatch: old={len(old)}, new={len(new)}"
        )
    count = data.count(old)
    if count != 1:
        raise SystemExit(
            f"{name}: expected exactly one old-pattern match, found {count}: {old!r}"
        )
    offset = data.find(old)
    print(f"{name}: offset={offset} length={len(old)}")
    data = data.replace(old, new)

open(path, "wb").write(data)
print("All seven equal-length byte patches applied")
PY

# Extract entitlements from this exact stock binary before replacing its
# invalidated Developer ID signature with a local ad-hoc signature.
codesign -d --entitlements :- "$ORIG" >"$TMP_ENTITLEMENTS" 2>/dev/null
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

ACTUAL_PATCHED_SHA="$(shasum -a 256 "$TMP_PATCH" | awk '{print $1}')"
if [[ "$ACTUAL_PATCHED_SHA" != "$EXPECTED_PATCHED_SHA" ]]; then
  echo "Refusing to install: patched binary hash differs from verified build" >&2
  echo "Expected: $EXPECTED_PATCHED_SHA" >&2
  echo "Actual:   $ACTUAL_PATCHED_SHA" >&2
  exit 1
fi

# Replace only this version-specific custom artifact and launcher.
mv -f "$TMP_PATCH" "$PATCH"
ln -sfn "$PATCH" "$LAUNCHER"

echo "Installed: $PATCH"
echo "Launcher:  $LAUNCHER"
echo "SHA-256:   $ACTUAL_PATCHED_SHA"
echo "--- version check ---"
"$LAUNCHER" --version
