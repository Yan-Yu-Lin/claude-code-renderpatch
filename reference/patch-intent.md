# Patch intent and exact byte replacements

This document maps the version-specific minified bytes in Claude Code 2.1.203 back to the readable source dump at:

```text
/Users/linyanyu/20-29-Development/24-reference-repos/claude-code-leaked-src/src
```

The dump and the installed binary are not identical revisions. Source locations are therefore semantic landmarks, not claims that the minified identifiers are identical.

## Invariants

Every replacement is exactly the same length as its original. Bun's `__BUN` section contains an offset-based archive/bundle; changing its length risks shifting embedded data and corrupting the executable. Shorter executable expressions are followed by ASCII spaces (`0x20`).

The full-redraw build is cumulative: it contains the two v1 patches plus five v2 patches.

## V1: expand all in Ctrl+O

### 1. Force `showAllInTranscript`

**Old bytes (75):**

```python
b"showAllInTranscript:Gt,onOpenRateLimitOptions:ENt,isLoading:Fe,scrollRef:mt"
```

**New bytes (75):**

```python
b"showAllInTranscript:!0,onOpenRateLimitOptions:ENt,isLoading:Fe,scrollRef:mt"
```

**Why equal:** the two-byte minified state variable `Gt` is replaced by the two-byte boolean expression `!0` (`true`).

**Semantic target:** the transcript branch's `<Messages>` invocation. It changes the prop from the mutable `showAllInTranscript` state to literal `true`, bypassing the initial 30-message transcript filter.

**Readable-source landmark:**

- `src/screens/REPL.tsx`, approximately lines 4390–4402: `transcriptMessagesElement` and `<Messages ... showAllInTranscript={showAllInTranscript} ...>`.
- `src/components/Messages.tsx`, approximately lines 276 and 467–522: `MAX_MESSAGES_TO_SHOW_IN_TRANSCRIPT_MODE`, `shouldTruncate`, and `messagesToShow`.

### 2. Force `disableRenderCap`

**Old bytes (21):**

```python
b"disableRenderCap:Or})"
```

**New bytes (21):**

```python
b"disableRenderCap:!0})"
```

**Why equal:** `Or` and `!0` are both two bytes.

**Semantic target:** the same transcript `<Messages>` invocation. In 2.1.203, `Or` is the minified `dumpMode` state. Forcing the prop true bypasses the safety slice even when the user has not entered dump mode with `[`.

**Readable-source landmark:**

- `src/screens/REPL.tsx`, approximately lines 4268–4286: `dumpMode`, `setDumpMode(true)`, and `setShowAllInTranscript(true)`.
- `src/screens/REPL.tsx`, approximately line 4402: `disableRenderCap={dumpMode}`.
- `src/components/Messages.tsx`, approximately lines 259, 278–338, and 535–543: `disableRenderCap`, `MAX_MESSAGES_WITHOUT_VIRTUALIZATION`, `computeSliceStart`, and the final `renderableMessages` slice.

## V2 additions: complete collapse and resize replay

### 3. Remove the pre-normalization message cap

**Old bytes (30):**

```python
b"let ne=!X&&!P?SQd(e,ie,te*2):0"
```

**New bytes (30):**

```python
b"let ne=0" + b" " * 22
```

Rendered with visible padding:

```text
let ne=0······················
```

**Why equal:** 8 bytes of executable code plus 22 spaces equals 30 bytes.

**Semantic target:** the first cap in the installed 2.1.203 `Messages` pipeline. Before normalization/grouping, a slicing helper (`SQd`) advances a UUID/index anchor when virtual scrolling and `disableRenderCap` are inactive. Setting its start index to zero keeps the entire loaded input message array available.

**Readable-source landmark:**

- `src/components/Messages.tsx`, approximately lines 471–543: `sliceAnchorRef`, the expensive normalization/grouping pipeline, `computeSliceStart`, and cap application.
- The installed binary is newer than the dump and has two cap stages; this pre-normalization stage is not textually identical in the dump.

### 4. Remove the final renderable-message cap

**Old bytes (29):**

```python
b"let pe=!X&&!P?SQd(Je,se,te):0"
```

**New bytes (29):**

```python
b"let pe=0" + b" " * 21
```

**Why equal:** 8 bytes of executable code plus 21 spaces equals 29 bytes.

**Semantic target:** the second cap after filtering/grouping. It sets the final render slice start to zero, so prompt/collapsed mode retains every loaded renderable message. This is essential: a destructive replay cannot reconstruct rows that the React tree has already sliced away.

**Readable-source landmark:**

- `src/components/Messages.tsx`, approximately lines 535–543: `renderableMessages`, `capApplies`, `computeSliceStart`, and `collapsed_0.slice(sliceStart)`.
- `src/components/Messages.tsx`, approximately lines 315–338: `computeSliceStart` and `SliceAnchor`.

### 5. Make all `clearTerminal` patches destructive

**Old bytes (67):**

```python
b'case"clearTerminal":s+=a.altScreen?ywi():_wi(a.viewportRows);break;'
```

**New bytes (67):**

```python
b'case"clearTerminal":s+=ywi();break;' + b" " * 32
```

**Why equal:** 35 bytes of executable code plus 32 spaces equals 67 bytes.

**Semantic target:** ANSI patch serialization. Stock 2.1.203 distinguishes:

- alternate screen: `getClearTerminalSequence()` (`ED2 + ED3 + home`), and
- classic main screen: `eraseViewportInPlace(viewportRows)` to preserve native scrollback.

The patch always chooses the destructive full-clear sequence. This deliberately wipes native scrollback before replaying the authoritative frame.

**Readable-source landmark:**

- `src/ink/terminal.ts`, approximately lines 190–242: `writeDiffToTerminal` and the `case 'clearTerminal'` serializer.
- `src/ink/clearTerminal.ts`, approximately lines 59–74: `getClearTerminalSequence`, `ERASE_SCREEN`, `ERASE_SCROLLBACK`, and `CURSOR_HOME`.
- The installed 2.1.203 revision additionally exports/contains `eraseViewportInPlace`, which the dump predates.

### 6. Replay full resets from frame row zero

**Old bytes (108):**

```python
b"let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1)),a=new kRi({x:0,y:s},e.viewport.width);"
```

**New bytes (108):**

```python
b"let s=0,a=new kRi({x:0,y:s},e.viewport.width);" + b" " * 62
```

**Why equal:** 46 bytes of executable code plus 62 spaces equals 108 bytes.

**Semantic target:** the installed binary's full-reset planner (minified function `CDr`). Stock 2.1.203 starts at row zero only in alternate-screen mode; on the classic main screen it starts at the physically visible slice:

```text
min(previously reachable row, max(0, frame height - viewport height + 1))
```

The patch always sets `startY = 0`, then renders through `frame.screen.height`. Combined with ED3, this rebuilds native scrollback from the beginning of the loaded frame.

**Readable-source landmark:**

- `src/ink/log-update.ts`, approximately lines 503–555: `fullResetSequence_CAUSES_FLICKER`, `VirtualScreen`, `renderFrame`, and `renderFrameSlice`.
- In the older dump, `renderFrame()` already starts at row zero. The visible-slice optimization exists in the installed 2.1.203 binary and is found near the emitted `{type:"clearTerminal", reason, altScreen, viewportRows}` patch.

### 7. Force one authoritative redraw after entering Ctrl+O

**Old bytes (153):**

```python
b'N("tengu_toggle_transcript",{is_entering:bNo!=="transcript",show_all:kdt,message_count:Hdt,open_dialog_count:AP.getState().open.length}),lan(C7_),Idt(!1)'
```

**New bytes (153):**

```python
b'lan(C7_),Idt(!1),bNo!=="transcript"&&setTimeout(R7_,0)' + b" " * 99
```

**Why equal:** 54 bytes of executable code plus 99 spaces equals 153 bytes.

**Semantic target:** `handleToggleTranscript`. It still toggles `screen` and resets `showAllInTranscript`, but when entering transcript mode it schedules the existing redraw helper (`R7_`, which calls the active Ink instance's `forceRedraw`) for the next event-loop turn. Waiting one turn lets React commit transcript state first; the forced reset then replays the expanded frame authoritatively.

Collapse does not schedule a second redraw because the large expanded-to-collapsed shrink already enters the full-reset path. This avoids two ED3 replays on collapse.

**Sacrifice:** the replacement reuses the telemetry call's byte budget, so this custom build no longer emits the `tengu_toggle_transcript` analytics event.

**Readable-source landmark:**

- `src/hooks/useGlobalKeybindings.tsx`, approximately lines 90–132: `handleToggleTranscript`, `logEvent('tengu_toggle_transcript', ...)`, `setScreen`, and `setShowAllInTranscript(false)`.
- `src/ink/ink.tsx`, approximately lines 815–838 in the dump: `forceRedraw()`/frame invalidation. Installed 2.1.203's implementation routes through `log.forceFullReset()`.

## Verified 2.1.203 offsets

Offsets in the stock 2.1.203 file used during development:

| Patch | Decimal file offset | Match count |
|---|---:|---:|
| transcript show-all | 227341345 | 1 |
| transcript disable cap | 227341491 | 1 |
| pre-normalization cap | 222729718 | 1 |
| final render cap | 222731469 | 1 |
| clear serializer | 212960195 | 1 |
| reset start row | 213192740 | 1 |
| Ctrl+O toggle/redraw | 224914628 | 1 |

Offsets are diagnostic only. Future versions must be rediscovered from stable anchors; never patch a new build by old offsets.
