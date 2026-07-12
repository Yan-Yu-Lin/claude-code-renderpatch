# Root cause: bounded frames versus native terminal scrollback

## Desired behavior

The target is stock Pi's simple model:

1. Ctrl+O constructs a complete detailed transcript.
2. Ctrl+O again constructs a complete collapsed transcript.
3. Width changes reconstruct the complete transcript at the new width.
4. Each transition clears the previous terminal presentation and writes one authoritative replacement from the beginning.

Claude Code 2.1.203 instead optimizes for bounded memory, fewer writes, and preservation of native terminal scrollback.

## The classic renderer

Claude Code's classic renderer is a custom Ink/React renderer on the terminal's **normal screen**.

The broad pipeline is:

1. React components and Yoga layout produce a complete logical `Screen`/`Frame` for the currently mounted tree.
2. The Ink instance keeps front and back frames.
3. `LogUpdate.render()` compares those frames and emits relative cursor/write/clear patches.
4. `writeDiffToTerminal()` serializes patches into ANSI.
5. Rows pushed above the physical viewport become terminal-emulator scrollback.

Relevant readable-source landmarks:

- `src/ink/ink.tsx`: frame construction and render dispatch.
- `src/ink/log-update.ts`: screen diff and full-reset planning.
- `src/ink/terminal.ts`: patch-to-ANSI serialization.
- `src/ink/clearTerminal.ts`: ED2/ED3/home sequences.
- `src/components/Messages.tsx`: transcript filtering, grouping, and render caps.

A normal terminal offers no portable way to address and rewrite arbitrary rows already in scrollback. Relative cursor movement can only manipulate the visible grid. Once rows scroll above that grid, Claude Code must either:

- preserve them and update only the viewport; or
- erase scrollback and replay an authoritative complete frame.

Stock 2.1.203 chooses preservation.

## The two preservation optimizations

### 1. Bounded message frames

The non-virtualized renderer does not keep every message mounted forever. It applies anchor-based safety slices before and after expensive filtering/grouping work. Ctrl+O also has an initial 30-message detailed-view cap.

The justification in the readable source is explicit: old content has already been printed into native scrollback, so remounting everything would increase React fiber/Yoga/screen-buffer memory and full-frame write costs.

This means the logical React frame and the terminal's complete visible history are different things:

```text
terminal history = old immutable native scrollback + currently mounted bounded frame
```

### 2. Viewport-preserving full reset

The installed 2.1.203 binary contains a newer reset strategy than the source dump:

- `eraseViewportInPlace(viewportRows)` clears only the current main-screen viewport.
- The full-reset planner starts rendering at the first physically addressable/visible frame row rather than row zero.
- ED3 (`CSI 3 J`, erase scrollback) is reserved for alternate-screen/full destructive clearing.

Conceptually:

```text
startY = min(previous reachable row,
             max(0, frameHeight - viewportHeight + 1))
clear visible viewport only
render frame[startY .. frameHeight]
leave older native scrollback untouched
```

This is intentional. It avoids deleting shell history and avoids rewriting thousands of transcript rows after ordinary offscreen changes.

## Failure A: partial Ctrl+O expansion

Stock Ctrl+O changes `screen` from prompt to transcript and asks `Messages` for verbose/detailed rendering.

However:

1. `showAllInTranscript` initially resets false, invoking the latest-30-message detailed filter.
2. Even after "show all", non-virtual safety caps can still slice the mounted frame.
3. Older collapsed rows are assumed to remain valid in native scrollback.
4. The renderer cannot rewrite those old rows in place.

The result is a detailed current tail while earlier native-scrollback rows remain absent or collapsed. V1 fixes this part by forcing both `showAllInTranscript` and `disableRenderCap` for the transcript `<Messages>` call.

## Failure B: partial collapse

V1 makes expansion large enough to print detailed rows far into native scrollback. On Ctrl+O again, React switches back to prompt/collapsed mode.

But stock collapse still has both preservation policies:

1. Prompt mode's ordinary render caps omit much of the old conversation from the new frame.
2. The main-screen reset clears/repaints only the viewport slice.
3. Expanded rows already above the viewport are deliberately preserved.

Therefore only the section currently being viewed folds. Earlier expanded rows remain frozen in native scrollback, producing the observed half-collapsed transcript.

A clean collapse requires both:

- a complete collapsed logical frame; and
- destructive scrollback clearing followed by row-zero replay.

## Failure C: resize distortion

A width change invalidates wrapping and causes `LogUpdate` to request a full reset. Stock 2.1.203 still treats this as a viewport-preserving main-screen reset:

1. old scrollback remains wrapped for the previous width;
2. only the current viewport slice is laid out and repainted at the new width;
3. terminal-native reflow and Claude Code's newly wrapped viewport can disagree;
4. stale fragments above the viewport cannot be corrected.

Repeated width changes can therefore leave mixed-width wrapping, stale expanded blocks, or visually distorted boundaries.

The full-redraw patch turns the existing resize reset into:

```text
ED2 + ED3 + cursor home
render from frame row 0 through frame end at the new width
```

## What the cumulative full-redraw patch changes

1. Force all detailed transcript messages for Ctrl+O (v1).
2. Disable both ordinary message-frame caps so collapsed/prompt mode also has a complete loaded frame.
3. Serialize every `clearTerminal` reset as destructive ED2+ED3+home.
4. Start every full-reset replay at row zero.
5. Schedule `forceRedraw()` after entering transcript mode so expansion also ends with a clean authoritative replay.

Collapse naturally causes a shrink/offscreen full reset, so it does not need a second scheduled redraw. Width changes already route to a full reset; changing reset semantics fixes resize without adding another resize handler.

## Scope and unavoidable limits

"Full transcript" here means **all messages currently loaded into the REPL display state**. The patch cannot resurrect entries already removed by compaction or resume-time pruning. Those records may still exist in JSONL, but presenting them requires a separate display-history store or lazy disk loading.

## Tradeoffs

The patch deliberately pays the costs Claude Code was avoiding:

- ED3 deletes Claude's native scrollback and may also remove shell output above Claude.
- Every full-reset path—not only Ctrl+O and resize—is now destructive.
- Complete message trees consume more memory and make renders more expensive.
- Extremely large sessions may become slow or consume hundreds of megabytes or more.
- Expansion performs an initial state render followed by one authoritative destructive replay.
- The `tengu_toggle_transcript` telemetry call was replaced to obtain same-length byte budget for the scheduled redraw.

A production-quality narrowly scoped fix would introduce explicit reset intents such as `transcriptExpand`, `transcriptCollapse`, and `resize`, applying destructive row-zero replay only to those intents. That requires source-level state/plumbing and a buildable project; it is not a clean same-length patch in 2.1.203.
