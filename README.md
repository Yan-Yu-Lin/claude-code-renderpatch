# claude-code-renderpatch

Version-pinned binary patches for Claude Code's terminal renderer, claude-mix context
windows, and explicit subagent model routing. The current cumulative recipe targets
**2.1.219**; older per-version scripts remain as rediscovery references.

The stock `claude` is a Bun-compiled Mach-O containing readable minified JavaScript in
its `__BUN` segment. The renderer combines bounded React/Ink frames with preserved native
terminal scrollback, making Ctrl+O omit old messages, leaving expanded rows behind after
collapse, and preserving stale wrapping across width changes.

Two recipes are retained:

- **V1** (`install_patch.sh`): expand-only; installs `claude-full-history`.
- **V2 / recommended** (`patches/full-redraw.sh`): complete expand/collapse plus
  destructive row-zero replay on resize; installs `claude-full-redraw`.

All recipes use **same-length byte patches** inside the embedded `__BUN` JavaScript
bundle, followed by an entitlement-preserving ad-hoc re-sign. The original binary is
never modified.

## What the patch changes

Two equal-length replacements in the transcript's `<Messages>` render call (minified):

| Original | Patched | Meaning |
|---|---|---|
| `showAllInTranscript:Gt` | `showAllInTranscript:!0` | force "show all" (drop the 30-message cap) |
| `disableRenderCap:Or}` | `disableRenderCap:!0}` | force the safety render cap off |

Corresponding readable source: `src/screens/REPL.tsx` ~line 4390–4402
(the transcript `Messages` element), `src/components/Messages.tsx`
(`MAX_MESSAGES_TO_SHOW_IN_TRANSCRIPT_MODE = 30`).

## Additional cumulative patches

### Provider-aware claude-mix windows

The mix-window patch keeps Claude models on native handling, assigns `kimi*` a 262144
window, and assigns other non-Claude providers (such as GPT) a 372000 window. This avoids
server-overwritable cache values and global context-window environment overrides.

### Explicit subagent model-override routing

Claude Code's subagent resolver has a same-family shortcut. Before resolving an explicit
alias, it canonicalizes the **parent's concrete model id** and substring-tests it for
`fable`, `opus`, `sonnet`, or `haiku`. If it appears to match, it returns the parent model
without running the real alias resolver.

This was measured from each subagent's own transcript `.message.model` field:

| parent slot | concrete parent at reproduction time | subagent `model:"opus"` |
|---|---|---|
| fable | `claude-fable-5[1m]` | resolved the opus slot correctly |
| sonnet | `kimi-k3` | resolved the opus slot correctly |
| haiku | `claude-opus-5[1m]` | **incorrectly inherited `claude-opus-5`** |

The haiku slot's concrete id contained `opus`, so the shortcut fired before the configured
opus alias could resolve. The patch disables only that shortcut's **explicit-override**
call site. It deliberately retains the second call used for frontmatter/default
same-family inheritance, as well as `inherit`, `CLAUDE_CODE_SUBAGENT_MODEL` precedence,
available-model checks, provider remapping, and 1M handling. It does not affect `/model`,
the main loop, quota routing, classifiers, or `opusplan` main-loop behavior. Local,
background, workflow, and remote-workflow agents with explicit model overrides all use
the corrected path.

A configuration-only belt-and-braces workaround is also active in
`~/.claude/claude-mix-settings.json`: no slot is mapped to a concrete model id containing
a **different** slot's family keyword. Keep that invariant even though the binary is now
fixed.

## Current target binary

- Version: `2.1.219`
- Stock SHA-256: `a8e806faaefac53c7a0f26523d8a45c60dbef3407b14ef990c75765d08febc82`
- Stock path: `~/.local/share/claude/versions/2.1.219`
- Cumulative output: `~/.local/share/claude/patched/claude-2.1.219-full-redraw-mix-window`
- Verified cumulative SHA-256: `a3423442e91548f046b3c7e723a41266935ae6137e4ffdc26e932c3d8cfc25f2`

The byte patterns are **version-specific**. Every update requires semantic rediscovery;
installers SHA-guard their expected input and require every old anchor exactly once.

## Experimental zero-patch preload runtime

Claude Code's embedded Bun runtime honors `BUN_OPTIONS=--preload=<absolute module>`.
The preload executes in Claude Code's own JavaScript process before CLI argument parsing,
shares process-wide globals, and worked unchanged on the patched 2.1.219 binary and stock
2.1.220. This creates an update-following extension seam for runtime-reachable surfaces
without modifying, signing, or pinning the selected executable.

This does **not** make every existing byte patch obsolete. A preload can wrap globals such
as `console`, mutate `process.argv`, and use Bun/Node APIs, but Claude Code's renderer,
resolvers, React state, and other minified lexical bindings remain private. Features that
need those internals still require a version-specific direct patch or a much smaller bridge
patch that invokes the external runtime.

The experiment is deliberately separate from `claude-mix`:

```bash
# Show which newest installed Claude candidate would be used.
./preload/claude-preload-lab --renderpatch-status

# Load the quiet bootstrap and run the selected Claude candidate normally.
./preload/claude-preload-lab --version

# Prove that external code can intercept Claude's own console.log.
CLAUDE_RENDERPATCH_MODULE="$PWD/preload/examples/console-prefix.mjs" \
  ./preload/claude-preload-lab --version

# Run all ordering, shared-global, API, trust, failure, and bypass checks.
uv run verify/preload-harness.py
```

`--renderpatch-safe` invokes the same resolved candidate after removing preload-related
environment variables, even if the bootstrap is missing or broken. Normal mode refuses an
inherited `BUN_OPTIONS`, accepts only a trusted bootstrap path, and the bootstrap requires
an explicitly selected, trusted external-module entry file under the user's home. These
checks do not inspect transitive imports; trusted extensions still have full same-user code
execution. The runtime never discovers or loads code from the current project automatically.

Run `preload/install.sh` only if you want the optional
`~/.local/bin/claude-preload-lab` convenience command. It copies the launcher and
bootstrap into `~/.local/share/claude-renderpatch/preload/`, then links only that durable
copy. The installer does not change `claude`, `claude-mix`, settings, or any installed
Claude binary. Remove the lab files with `preload/install.sh --uninstall`.

See [`reference/preload-runtime.md`](reference/preload-runtime.md) for the empirical record,
security boundary, update matrix, failed alternatives, and the recommended external-runtime
plus minimal-internal-bridge architecture.

## Install

Recommended 2.1.219 cumulative build (seven render edits + mix-window + routing fix,
one final codesign):

```bash
bash patches/full-redraw-mix-window-2.1.219.sh
```

It writes `~/.local/share/claude/patched/claude-2.1.219-full-redraw-mix-window`, preserving
the previous combined artifact as `.pre-routing-fix` when that backup does not already
exist. Normal `claude` is untouched. The version-specific standalone migration script is
`patches/subagent-model-override-2.1.219.sh`; clean rebuilds should prefer the cumulative
script.

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

## Routing-fix rediscovery after updates

Do not reuse `Vrd`, `ote`, `Ei`, or any old offset: minified identifiers regenerate.
Search for the stable `CLAUDE_CODE_SUBAGENT_MODEL` literal, then locate the nearby resolver
with an `"inherit"` explicit-model branch. Confirm its family helper contains adjacent
`fable`/`opus`/`sonnet`/`haiku` cases whose results use `.includes(...)`. The resolver has
two helper calls: patch only the first, explicit-override call immediately before the real
alias resolver; retain the second default/frontmatter call. Require one contextual anchor,
an equal-length replacement, old=0/new=1 afterward, then re-extract entitlements and sign.
See `REPATCHING-PLAYBOOK.md` for the complete procedure.

## Documentation and verification

- [`reference/root-cause.md`](reference/root-cause.md) — architecture and failure modes.
- [`reference/patch-intent.md`](reference/patch-intent.md) — exact bytes and source mapping.
- [`reference/preload-runtime.md`](reference/preload-runtime.md) — tested external preload
  behavior, security boundary, and update/repatch matrix.
- [`REPATCHING-PLAYBOOK.md`](REPATCHING-PLAYBOOK.md) — rediscovery procedure after updates.
- [`verify/pty-harness.py`](verify/pty-harness.py) — repeatable expand/collapse/resize PTY test.
- [`verify/preload-harness.py`](verify/preload-harness.py) — repeatable latest-candidate
  preload, same-global, trust, failure, child-environment, and bypass tests.

## Known tradeoffs / limitations

- V2 deliberately uses ED3 and can erase shell scrollback above Claude.
- Its destructive behavior applies to all full-reset paths, not only Ctrl+O and resize.
- Removing the frame caps raises memory/CPU costs on very large sessions.
- "Full" means every message currently loaded in display state; it cannot resurrect
  messages dropped by compaction/resume pruning (though they may remain in JSONL).
- The V2 Ctrl+O replacement reuses telemetry bytes, so it sacrifices the
  `tengu_toggle_transcript` analytics event.
