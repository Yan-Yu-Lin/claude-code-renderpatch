#!/usr/bin/env bash
# Reproduce the Claude Code 2.1.203 "full-redraw" patch from the stock binary.
#
# Installs a separate binary and launcher. The stock Claude Code binary and
# ~/.local/bin/claude are never modified.

set -euo pipefail

VERSION="2.1.203"
ORIG="$HOME/.local/share/claude/versions/$VERSION"
PATCH_DIR="$HOME/.local/share/claude/patched"
PATCH="$PATCH_DIR/claude-$VERSION-full-redraw"
LAUNCHER="$HOME/.local/bin/claude-full-redraw"

EXPECTED_STOCK_SHA="57b5aec68a35f42036bd2f82836d91c2d2990c2d589fb3465e3ee87142af9a1e"
EXPECTED_PATCHED_SHA="a6ea3c39f95075a2d7be925f7ca46b9bbae737f727a8d2f524f655d606cf93ed"

for command in python3 shasum codesign; do
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
  rm -f "$TMP_PATCH" "$TMP_ENTITLEMENTS"
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


# The first two entries are the v1 expand-all patch. The remaining five add
# complete prompt-mode frames, destructive resets, row-zero replay, and a
# forced authoritative redraw after entering Ctrl+O transcript mode.
patches = [
    (
        "transcript-show-all",
        b"showAllInTranscript:Gt,onOpenRateLimitOptions:ENt,isLoading:Fe,scrollRef:mt",
        b"showAllInTranscript:!0,onOpenRateLimitOptions:ENt,isLoading:Fe,scrollRef:mt",
    ),
    (
        "transcript-disable-render-cap",
        b"disableRenderCap:Or})",
        b"disableRenderCap:!0})",
    ),
    (
        "remove-pre-normalization-cap",
        b"let ne=!X&&!P?SQd(e,ie,te*2):0",
        padded(b"let ne=!X&&!P?SQd(e,ie,te*2):0", b"let ne=0"),
    ),
    (
        "remove-final-render-cap",
        b"let pe=!X&&!P?SQd(Je,se,te):0",
        padded(b"let pe=!X&&!P?SQd(Je,se,te):0", b"let pe=0"),
    ),
    (
        "destructive-main-screen-reset",
        b'case"clearTerminal":s+=a.altScreen?ywi():_wi(a.viewportRows);break;',
        padded(
            b'case"clearTerminal":s+=a.altScreen?ywi():_wi(a.viewportRows);break;',
            b'case"clearTerminal":s+=ywi();break;',
        ),
    ),
    (
        "reset-replay-from-row-zero",
        b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new kRi({x:0,y:s},e.viewport.width);",
        padded(
            b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new kRi({x:0,y:s},e.viewport.width);",
            b"let s=0,a=new kRi({x:0,y:s},e.viewport.width);",
        ),
    ),
    (
        "force-authoritative-expand-redraw",
        b'N("tengu_toggle_transcript",{is_entering:bNo!=="transcript",show_all:kdt,message_count:Hdt,open_dialog_count:AP.getState().open.length}),lan(C7_),Idt(!1)',
        padded(
            b'N("tengu_toggle_transcript",{is_entering:bNo!=="transcript",show_all:kdt,message_count:Hdt,open_dialog_count:AP.getState().open.length}),lan(C7_),Idt(!1)',
            b'lan(C7_),Idt(!1),bNo!=="transcript"&&setTimeout(R7_,0)',
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

# Extract and preserve the entitlements from the exact stock binary. Editing
# __BUN invalidates Anthropic's Developer ID signature, so install a local
# ad-hoc signature while retaining JIT, unsigned-executable-memory, Apple
# Events, library-validation, and microphone entitlements.
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

# Atomic replacement of only the custom build, then update its separate launcher.
mv -f "$TMP_PATCH" "$PATCH"
ln -sfn "$PATCH" "$LAUNCHER"

# TMP_PATCH has moved successfully; the trap only removes the entitlement temp.
echo "Installed: $PATCH"
echo "Launcher:  $LAUNCHER"
echo "SHA-256:   $ACTUAL_PATCHED_SHA"
echo "--- version check ---"
"$LAUNCHER" --version
