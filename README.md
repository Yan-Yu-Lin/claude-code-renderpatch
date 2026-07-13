# claude-code-renderpatch

Version-pinned binary patches for Claude Code's native Ctrl+O and terminal renderer.

The stock `claude` (Bun-compiled Mach-O, pinned here to **2.1.203**) combines bounded
React/Ink frames with preserved native terminal scrollback. That makes Ctrl+O omit old
messages, leaves older expanded rows behind on collapse, and can preserve stale wrapping
across width changes.

Two recipes are retained:

- **V1** (`install_patch.sh`): expand-only; installs `claude-full-history`.
- **V2 / recommended** (`patches/full-redraw.sh`): complete expand/collapse plus
  destructive row-zero replay on resize; installs `claude-full-redraw`.

Both use **same-length byte patches** inside the embedded `__BUN` JavaScript bundle,
followed by an ad-hoc re-sign. The original binary is never modified.

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

Recommended full-redraw build:

```bash
bash patches/full-redraw.sh
```

Creates `~/.local/share/claude/patched/claude-2.1.203-full-redraw` and symlinks
`~/.local/bin/claude-full-redraw` to it. Normal `claude` is untouched.

The original expand-only build remains reproducible with:

```bash
bash install_patch.sh
```

## Uninstall

```bash
trash ~/.local/bin/claude-full-history ~/.local/share/claude/patched
```

## Other platforms (Linux / Windows)

The prebuilt scripts here target **macOS / Apple Silicon (arm64)**. But the fix is not
macOS-specific: Claude Code ships a separate native binary per platform, and the *same*
minified JavaScript app is bundled inside all of them — only the outer runtime wrapper
(Mach-O vs ELF vs PE) differs. So the patch sites, and very likely the exact byte
patterns, are the same for a given version on Linux and Windows; only the packaging
around them changes.

The per-OS differences are small, and an AI agent following [`REPATCHING-PLAYBOOK.md`](REPATCHING-PLAYBOOK.md)
should be able to fill them in without much trouble:

- **Linux** — *easier* than macOS. ELF binaries have no code signature, so you skip the
  re-signing step entirely: patch the bytes in place and run.
- **Windows** — doable. Windows will run a modified binary, so it's mostly a matter of
  adapting the signing step (invalidated Authenticode is not a hard block the way macOS
  Gatekeeper is).
- **Verification** — [`verify/pty-harness.py`](verify/pty-harness.py) uses a Unix
  pseudo-terminal (works on macOS/Linux as-is). On Windows an agent would adapt it to
  ConPTY, or just verify interactively.

These platforms are **untested by me** — but the hard part (locating the sites, deriving
same-length replacements, confirming the render behavior) is identical everywhere and is
exactly what the playbook + `reference/` docs cover. Point your agent at them and the
platform gap should be straightforward to close.

## Documentation and verification

- [`reference/root-cause.md`](reference/root-cause.md) — architecture and failure modes.
- [`reference/patch-intent.md`](reference/patch-intent.md) — exact bytes and source mapping.
- [`REPATCHING-PLAYBOOK.md`](REPATCHING-PLAYBOOK.md) — rediscovery procedure after updates.
- [`verify/pty-harness.py`](verify/pty-harness.py) — repeatable expand/collapse/resize PTY test.

## Known tradeoffs / limitations

- V2 deliberately uses ED3 and can erase shell scrollback above Claude.
- Its destructive behavior applies to all full-reset paths, not only Ctrl+O and resize.
- Removing the frame caps raises memory/CPU costs on very large sessions.
- "Full" means every message currently loaded in display state; it cannot resurrect
  messages dropped by compaction/resume pruning (though they may remain in JSONL).
- The V2 Ctrl+O replacement reuses telemetry bytes, so it sacrifices the
  `tengu_toggle_transcript` analytics event.
