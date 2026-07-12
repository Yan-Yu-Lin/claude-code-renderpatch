# claude-code-renderpatch

Binary patch for Claude Code's native binary to fix the transcript (Ctrl+O) renderer.

The stock `claude` (Bun-compiled Mach-O, version-pinned here to **2.1.203**) renders
only the last ~30 messages when you press **Ctrl+O**, because it assumes older rows are
still sitting in the terminal's native scrollback. This patch forces the Ctrl+O
transcript view to render **all currently-loaded messages**.

This is a **same-length byte patch** inside the embedded `__BUN` JavaScript bundle,
followed by an ad-hoc re-sign (macOS requires a valid signature to run). The original
binary is never modified — the patch is applied to a copy installed as a separate
launcher, `claude-full-history`.

## What the patch changes

Two equal-length replacements in the transcript's `<Messages>` render call (minified):

| Original | Patched | Meaning |
|---|---|---|
| `showAllInTranscript:Gt` | `showAllInTranscript:!0` | force "show all" (drop the 30-message cap) |
| `disableRenderCap:Or}` | `disableRenderCap:!0}` | force the safety render cap off |

Corresponding readable source: `src/screens/REPL.tsx` ~line 4390–4402
(the transcript `Messages` element), `src/components/Messages.tsx`
(`MAX_MESSAGES_TO_SHOW_IN_TRANSCRIPT_MODE = 30`).

## Target binary

- Version: `2.1.203`
- SHA-256 (original, unmodified): `57b5aec68a35f42036bd2f82836d91c2d2990c2d589fb3465e3ee87142af9a1e`
- Path: `~/.local/share/claude/versions/2.1.203`

The byte patterns are **version-specific** — they do NOT exist in 2.1.205. Any upgrade
needs a fresh inspection, not a blind re-apply. The install script SHA-guards against
running on the wrong binary.

## Install

```bash
bash install_patch.sh
```

Creates `~/.local/share/claude/patched/claude-2.1.203-full-history` and symlinks
`~/.local/bin/claude-full-history` to it. Normal `claude` is untouched.

## Uninstall

```bash
trash ~/.local/bin/claude-full-history ~/.local/share/claude/patched
```

## Known limitations / open work

- **Collapse doesn't re-render the whole transcript.** Ctrl+O expands all correctly,
  but collapsing only re-folds the currently-viewed section; earlier expanded content
  stays expanded. Desired (pi-style): Ctrl+O toggles expand-all / fold-all with a full
  re-render each way.
- **Resize distortion.** On window/width change it should redraw the entire transcript
  (first visible line → latest message) to avoid mangling. Not yet addressed.
- **Compaction boundary.** The patch renders every message currently loaded in the
  session; it cannot resurrect messages already dropped from display state by
  compaction/resume-pruning (still on disk in the JSONL).
