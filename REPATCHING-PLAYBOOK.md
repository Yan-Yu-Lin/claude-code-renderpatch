# Repatching playbook for a new Claude Code version

This playbook is for a future agent after Claude Code updates and the 2.1.203 byte patterns no longer match. Do not copy old offsets or minified variable names. Rediscover the same semantic sites using stable strings and property names.

The objective is a cumulative custom build that:

1. renders every currently loaded message in Ctrl+O;
2. keeps a complete collapsed/prompt frame;
3. uses destructive ED2+ED3 resets on the classic main screen;
4. replays full resets from row zero;
5. forces one authoritative redraw after entering Ctrl+O;
6. applies provider-aware claude-mix context windows;
7. resolves explicit subagent model aliases instead of false-inheriting a parent whose
   concrete model id merely contains that alias's family keyword;
8. passes byte-anchor, signature, version, PTY, and model-routing verification.

## 0. Preserve the known-good build

Never patch in place. Keep the current custom binary and launcher until the replacement passes verification.

```bash
readlink ~/.local/bin/claude
readlink ~/.local/bin/claude-full-redraw
shasum -a 256 ~/.local/share/claude/patched/*full-redraw 2>/dev/null
```

Create the new build under a versioned filename and initially expose it through a different test launcher if desired.

## 1. Locate and fingerprint the new stock binary

```bash
CLAUDE="$(python3 - <<'PY'
import os
print(os.path.realpath(os.path.expanduser('~/.local/bin/claude')))
PY
)"

echo "$CLAUDE"
"$CLAUDE" --version
file "$CLAUDE"
shasum -a 256 "$CLAUDE"
codesign -dv --verbose=4 "$CLAUDE" 2>&1 | head -30
otool -l "$CLAUDE" | grep -A12 -B2 '__BUN'
```

Expected format on 2.1.203:

- thin arm64 Mach-O executable;
- Developer ID identifier `com.anthropic.claude-code`;
- a large `__BUN` segment with a `__bun` section;
- readable minified JavaScript embedded as literal bytes.

If there is no `__BUN` section or the relevant JavaScript is compressed/encrypted, stop. This equal-length technique may no longer apply.

Record the new stock SHA in the new version's installer before doing anything else.

## 2. Make searchable bundle slices

Use Python byte search rather than `strings` alone; Python preserves exact offsets and punctuation.

```bash
python3 - "$CLAUDE" <<'PY'
import re, sys
b = open(sys.argv[1], 'rb').read()
anchors = [
    b'showAllInTranscript:',
    b'disableRenderCap:',
    b'transcript:toggleShowAll',
    b'Showing detailed transcript',
    b'clearTerminal',
    b'eraseViewportInPlace',
    b'getClearTerminalSequence',
    b'viewportRows',
    b'tengu_toggle_transcript',
    b'app:toggleTranscript',
    b'forceRedraw',
]
for anchor in anchors:
    offsets = [m.start() for m in re.finditer(re.escape(anchor), b)]
    print(anchor.decode(errors='replace'), len(offsets), offsets[-20:])
    for i in offsets[-3:]:
        print('  ', i, repr(b[max(0, i-200):i+500]))
PY
```

The Bun executable contains runtime string tables, source-map material, and executable bundle text. Prefer the long printable minified region where multiple related code constructs appear together. In 2.1.203 the live application bundle was around offsets 210–228 MB; do not assume this range remains stable.

For easier reading, extract 50–100 KB around a candidate and optionally format a copy. Never patch a reformatted file.

```bash
python3 - "$CLAUDE" 227341000 /tmp/claude-candidate.js <<'PY'
import sys
p, off, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
b = open(p, 'rb').read()
open(out, 'wb').write(b[max(0, off-50000):off+50000])
PY
```

## 3. Rediscover the two transcript-call patches

### Stable anchors

Search for a JSX-prop object containing these durable property names close together:

```text
screen:
showAllInTranscript:
onOpenRateLimitOptions:
isLoading:
scrollRef:
disableRenderCap:
```

There may be several `showAllInTranscript` occurrences: export, session preview, normal prompt, and transcript. The correct call is inside the branch associated with:

- `screen === "transcript"`;
- nearby `Showing detailed transcript` footer construction;
- nearby transcript virtual-scroll/alternate-screen selection;
- a `disableRenderCap` value derived from dump mode.

### Derive replacements

Replace only the minified value tokens:

```text
showAllInTranscript:<two-byte state variable>
    -> showAllInTranscript:!0

disableRenderCap:<two-byte state variable>
    -> disableRenderCap:!0
```

If the new minified variable is not exactly two bytes, choose an equal-length true expression and pad only where JavaScript permits whitespace. It is safer to replace a longer unique context and preserve its total length than to patch a one-character variable globally.

Confirm each full contextual old pattern occurs exactly once.

Readable source map: `src/screens/REPL.tsx` transcript branch and `src/components/Messages.tsx` transcript truncation.

## 4. Rediscover both ordinary render caps

### Stable anchors

Within the module containing `disableRenderCap`, find:

- the default prop `disableRenderCap:<var>=!1`;
- the virtual-scroll runtime gate (`scrollRef != null` plus the virtual-scroll disable setting);
- an anchor/slicing helper called before expensive normalization/grouping;
- a second anchor/slicing helper applied to the final grouped/renderable array;
- nearby constants equivalent to transcript cap 30 and safety cap 200;
- logic equivalent to `computeSliceStart` using message UUID plus index fallback.

In 2.1.203 both sites looked structurally like:

```js
let start = !virtual && !disableCap ? sliceHelper(array, anchorRef, cap) : 0
```

One cap operated on the input messages (with roughly twice the final cap); the second operated on final renderables.

### Derive replacements

Replace each complete `let <start>=...` expression with:

```js
let <start>=0
```

Pad the remainder with spaces to the exact original length. Do not replace the slicing helper itself; it is used elsewhere.

Why both are required: disabling only the final slice may leave older messages discarded before normalization. Disabling only the early slice still lets the final renderable list be truncated.

Readable source map: `src/components/Messages.tsx`, `SliceAnchor`, `computeSliceStart`, and `renderableMessages`.

## 5. Rediscover destructive reset serialization

### Stable anchors

Search for these exported/durable strings:

```text
eraseViewportInPlace
getClearTerminalSequence
clearTerminal
viewportRows
altScreen
```

Find the patch serializer's switch case. Its semantics should be:

```js
case "clearTerminal":
  output += patch.altScreen
    ? getClearTerminalSequence()
    : eraseViewportInPlace(patch.viewportRows)
```

The correct site is executable code, not merely the export table for the named functions.

### Derive replacement

Replace the complete switch-case body with the unconditional full-clear helper:

```js
case "clearTerminal": output += getClearTerminalSequence(); break;
```

Use the current minified helper name, and pad with spaces. The full helper must produce ED2 + ED3 + cursor home. Confirm by inspecting its body near the `getClearTerminalSequence` export and later by counting `ESC[2J` and `ESC[3J` in PTY captures.

Readable source map: `src/ink/terminal.ts` patch serializer and `src/ink/clearTerminal.ts`.

## 6. Rediscover the reset start-row planner

### Stable anchors

Search near construction of a clear patch object containing:

```text
{type:"clearTerminal", reason:, altScreen:, viewportRows:}
```

Immediately before it, find logic that:

1. computes a start row;
2. uses zero for alternate screen;
3. otherwise computes something like:

```text
min(previous reachable row,
    max(0, screen.height - viewport.height + 1))
```

4. creates a virtual screen/cursor at `{x:0, y:start}`;
5. renders a slice from `start` through `screen.height`.

This is the full-reset planner corresponding to `fullResetSequence_CAUSES_FLICKER` / `renderFrameSlice` in readable source.

### Derive replacement

Replace the complete start-row declaration with:

```js
let <start>=0,<rest of virtual-screen construction>
```

Pad with spaces. Preserve the existing render-to-frame-end call and clear patch object.

Do not simply delete ED3 or change cursor arithmetic elsewhere. The combination must be:

- destructive clear;
- cursor at row zero;
- replay from frame row zero.

## 7. Rediscover Ctrl+O's post-state redraw

### Stable anchors

Search for:

```text
tengu_toggle_transcript
app:toggleTranscript
show_all
message_count
open_dialog_count
```

The target is `handleToggleTranscript`, which should:

- test whether the current screen is transcript;
- toggle prompt/transcript screen state;
- reset show-all state;
- log `tengu_toggle_transcript`.

Also find the nearby redraw handler registered as `app:redraw`; in 2.1.203 its helper called the active Ink instance's `forceRedraw()`.

### Derive replacement

Reuse the telemetry call's long byte range to fit:

```js
setScreen(toggleScreen)
setShowAll(false)
currentScreen !== "transcript" && setTimeout(forceRedrawHelper, 0)
```

Why asynchronous: calling `forceRedraw` before React commits transcript state redraws the old collapsed frame, after which expansion can append again. `setTimeout(..., 0)` allows the transcript state render to commit first, then invalidates and authoritatively replays it.

Why enter-only: collapse already causes a full reset from the large frame shrink. Scheduling another redraw on collapse produced two ED3 replays in testing.

This replacement sacrifices `tengu_toggle_transcript` telemetry. Preserve that caveat unless a new version leaves enough equal-length dead space to retain telemetry and add the callback.

Readable source map: `src/hooks/useGlobalKeybindings.tsx` `handleToggleTranscript`; `src/ink/ink.tsx` `forceRedraw`.

## 8. Rediscover the explicit subagent model-routing fix

### Reproduced failure and mechanism

With the original claude-mix layout, explicit subagent `model:"opus"` correctly resolved
the configured opus slot from fable (`claude-fable-5[1m]`) and sonnet (`kimi-k3`)
parents. From the haiku slot, which then resolved to `claude-opus-5[1m]`, the subagent
silently inherited `claude-opus-5`. This was read from each subagent transcript's API
response `.message.model`, not model self-reporting.

The subagent resolver checks `CLAUDE_CODE_SUBAGENT_MODEL`, then handles an explicit model
argument. Before invoking the real alias resolver it calls a family helper that
canonicalizes the parent's concrete id and substring-tests it for `fable`, `opus`,
`sonnet`, or `haiku`. A match returns the parent immediately. The haiku slot's concrete id
contained `opus`, so explicit `opus` was mistaken for a no-op.

### Stable rediscovery anchors

Do not reuse names such as 2.1.207's `lod`/`ble`/`Zo` or 2.1.219's
`Vrd`/`ote`/`Ei`. Search the new stock bytes for:

```text
CLAUDE_CODE_SUBAGENT_MODEL
```

Near the live executable occurrence, locate a resolver with:

- an environment-override branch comparing against `"inherit"`;
- an explicit argument branch beginning with another `"inherit"` check;
- a real alias resolver call after a same-family early return;
- a default/frontmatter branch with a second same-family early return.

Find the nearby family helper using stable literal adjacency equivalent to:

```js
case "fable": return canonicalParent.includes("fable")
case "opus":  return canonicalParent.includes("opus")
case "sonnet":return canonicalParent.includes("sonnet")
case "haiku": return canonicalParent.includes("haiku")
```

Confirm the helper has exactly two calls inside the subagent resolver. Patch only the
**first** call, in the explicit-override branch, to a same-length constant-false condition
so execution falls through to the existing real alias resolver. For example, 2.1.219
changes the 21-byte clause:

```js
if(Vrd(r,t))return t;
```

to:

```js
if(!1&&r&&t)return t;
```

Use a longer contextual anchor containing the following real resolver call, not the
21-byte clause globally. Require contextual old=1/new=0 before patching and old=0/new=1
immediately afterward.

### Why this is narrow

Do not patch the family helper itself and do not patch its second call. The narrow edit
affects explicit model overrides for ordinary local/background agents, workflow agents,
and remote workflow agents. It leaves unchanged:

- agent-definition/frontmatter defaults and normal same-family inheritance;
- explicit `inherit`;
- higher-precedence `CLAUDE_CODE_SUBAGENT_MODEL`;
- allowlist checks, provider remapping, and 1M handling after alias resolution;
- `/model`, the main loop, quota routing, classifiers, and `opusplan` main-loop behavior;
- built-in, resume, observer, and background launches with no explicit model argument.

The behavior intentionally changed is a pinned same-family parent plus explicit family
alias: the explicit alias now follows its configured slot rather than preserving the
parent's concrete id.

### Configuration-level belt and braces

The user's `~/.claude/claude-mix-settings.json` already avoids assigning any slot a
concrete model id containing a **different** slot's family keyword. Preserve that
configuration invariant as a fallback, but do not treat it as a substitute for
rediscovering and verifying the binary fix.

## 9. Build a same-length patcher safely

Start from the stock binary every time and apply render, mix-window, and routing edits
in one in-memory patch list:

```bash
cp "$CLAUDE" /tmp/claude-new-full-redraw-mix-window
```

Perform one codesign pass only after every byte replacement and post-patch invariant has
succeeded. `patches/full-redraw-mix-window-2.1.219.sh` is the current cumulative reference;
the per-feature scripts are migration and rediscovery references.

Represent every patch as `(name, old_bytes, new_bytes)`. Enforce:

```python
if len(old) != len(new): fail
if data.count(old) != 1: fail
```

For shorter executable replacements:

```python
def padded(old: bytes, code: bytes) -> bytes:
    if len(code) > len(old):
        raise ValueError("replacement grew")
    return code + b" " * (len(old) - len(code))
```

Never:

- insert/delete bytes;
- patch by old file offset alone;
- replace a short minified variable globally;
- continue after a zero/multiple match;
- patch the already patched previous-version binary.

Use `patches/full-redraw-mix-window-2.1.219.sh` as the current cumulative reference and
`patches/full-redraw.sh` as the historical 2.1.203 renderer reference.

## 10. Preserve entitlements and re-sign

Editing `__BUN` invalidates Anthropic's signature. Extract entitlements from the **new stock binary**, then ad-hoc sign the copy:

```bash
codesign -d --entitlements :- "$CLAUDE" >/tmp/claude-entitlements.plist 2>/dev/null

codesign --force \
  --sign - \
  --identifier com.anthropic.claude-code \
  --entitlements /tmp/claude-entitlements.plist \
  /tmp/claude-new-full-redraw-mix-window

codesign --verify --strict --verbose=2 /tmp/claude-new-full-redraw-mix-window
/tmp/claude-new-full-redraw-mix-window --version
```

Compare extracted entitlements with `claude-entitlements.plist`. The stock binary may acquire new entitlements; always prefer extraction over blindly copying the old plist.

Install under a new versioned name only after verification:

```bash
mkdir -p ~/.local/share/claude/patched ~/.local/bin
cp /tmp/claude-new-full-redraw-mix-window \
  ~/.local/share/claude/patched/claude-NEWVERSION-full-redraw-mix-window
ln -sfn ~/.local/share/claude/patched/claude-NEWVERSION-full-redraw-mix-window \
  ~/.local/bin/claude-full-redraw-new
```

## 11. Verify with the PTY harness

Select a backed-up large session containing memorable old strings:

```bash
uv run verify/pty-harness.py \
  ~/.local/bin/claude-full-redraw-new \
  --session SESSION_UUID \
  --anchor "old phrase near the beginning" \
  --anchor "another old phrase"
```

Compare stock, previous custom build, and candidate if uncertain. Inspect:

- `startup.ansi`
- `expand.ansi`
- `collapse.ansi`
- `resize.ansi`
- `summary.json`

A good candidate should show:

- large output for expand, collapse, and resize;
- exactly one ED2/ED3 pair in each authoritative phase;
- old anchors in collapse and resize;
- verbose-only raw tool details in expand but absent in collapse;
- no crash after SIGWINCH.

Then perform the decisive real-terminal test in Ghostty:

1. expand with Ctrl+O;
2. scroll far up;
3. collapse with Ctrl+O;
4. verify all earlier tool blocks folded;
5. repeatedly resize narrow/wide;
6. inspect for stale wrapping, duplicates, or mangled borders.

## 12. Diagnose failures

### Stock SHA mismatch

The installer targets the wrong build, even if the version string is the same. Stop and rediscover patterns. Do not weaken the guard.

### Pattern match count is zero

Expected after an update. Search stable anchors and derive the new minified context. Do not reuse old offsets.

### Pattern match count is greater than one

The pattern is not specific enough or also appears in source-map/string-table copies. Expand it with neighboring durable props/literals until the executable site is unique.

### Replacement length mismatch

Do not write it. Shorten the executable expression, reuse a larger surrounding range, remove nonessential telemetry, or pad a shorter expression with spaces. Never shift the archive.

### `codesign --verify` fails / process is killed immediately

The original signature was invalidated and the copy was not re-signed correctly. Re-extract entitlements, use `--identifier com.anthropic.claude-code`, and sign after all byte edits.

### `--version` works but interactive mode crashes

Likely patched the wrong duplicate, produced syntactically valid but semantically wrong JS, omitted JIT-related entitlements, or changed archive length. Return to stock, verify exact lengths/counts, and test patches incrementally.

### Expansion is full but collapse is tiny

The v1 props worked, but one or more v2 pieces are missing: ordinary caps remain, main reset still preserves viewport, or replay still starts at visible `startY`.

### Collapse is full but expansion has no ED3

The post-state scheduled `forceRedraw` patch is missing or ran before state commit. Verify `setTimeout(forceRedrawHelper, 0)` and that it is gated to entering transcript.

### Collapse emits two ED3 sequences

The forced redraw runs on exit as well as entry. Gate it on the pre-toggle screen not being transcript.

### Resize emits ED3 but only a small viewport

Destructive clear was patched, but reset still starts at the visible slice or message caps remain.

### Signature passes but resulting SHA differs

For the pinned 2.1.203 installer, stop: the recipe drifted. On a new version, record the new verified stock and result SHAs after PTY/Ghostty validation. Ad-hoc signing output can theoretically change with macOS tooling, so distinguish a code-patch mismatch from signature-blob variation by comparing bytes before the `__LINKEDIT` signature region.

## 13. Preserve the tradeoffs in every future version

Communicate these every time:

- ED3 destructively wipes native scrollback, including possible shell output above Claude.
- The serializer patch currently affects **all** full-reset paths, not only Ctrl+O and resize.
- Removing both caps increases React/Yoga/screen-buffer memory and CPU cost on huge sessions.
- "Full" means currently loaded REPL display state, not records discarded by compaction/resume pruning.
- The 2.1.203 same-length toggle patch sacrifices `tengu_toggle_transcript` telemetry.
- A narrowly scoped production design needs explicit reset intents and a buildable source tree; it cannot be cleanly expressed by these broad byte substitutions.

## 2.1.203 reference hashes

```text
stock:
57b5aec68a35f42036bd2f82836d91c2d2990c2d589fb3465e3ee87142af9a1e

verified cumulative full-redraw:
a6ea3c39f95075a2d7be925f7ca46b9bbae737f727a8d2f524f655d606cf93ed
```

The direct-from-stock recipe in `patches/full-redraw.sh` was verified to reproduce the installed 2.1.203 full-redraw binary byte-for-byte.
