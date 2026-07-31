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

## Developer and extension documentation（繁體中文）

本 repo 現在提供獨立 **2.1.220 internal-SDK candidate/prototype** 的 developer-facing map，
涵蓋 runtime API、safe reads/actions、exact-version unsafe access、目前缺口、bridge 維護，
以及 version-pinned Banner renderer 研究：

- **從這裡開始：** [`docs/README.md`](docs/README.md)
- **目前已驗證與未完成狀態：** [`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md)
- **Capability map：** [`docs/CAPABILITY-MAP.md`](docs/CAPABILITY-MAP.md)
- **撰寫 user extension：** [`docs/extensions/getting-started.md`](docs/extensions/getting-started.md)
- **Banner/Clawd internals：** [`docs/internals/BANNER-RENDERER-2.1.220.md`](docs/internals/BANNER-RENDERER-2.1.220.md)

2.1.219 cumulative direct-patch recipe 與 2.1.220 internal-SDK candidate 是兩條不同路徑。
後者已在本機 macOS arm64 驗證，但尚未 merge 到 `main`、沒有公開 GitHub release/PR，
fresh clone 也不包含 `candidate/install.sh` 所需、被 gitignore 的 signed candidate artifact。

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

## Immutable 2.1.220 internal-SDK candidate

The frozen 2.1.220 SDK bridge is available through one separate user-facing command:
`claude-renderpatch-candidate`. It mirrors the existing multi-provider proxy, settings overlay,
provider note, and model-restoration behavior without calling or changing `claude-mix`.
Normal `claude`, `claude-mix`, and `claude-preload-lab` remain independent.

```bash
# Install the exact signed candidate and its runtime assets.
./candidate/install.sh

# Verify release/build/hash/capability metadata without enabling the preload.
claude-renderpatch-candidate --renderpatch-status

# Run through the multi-provider overlay with the default SDK policies.
claude-renderpatch-candidate --version

# Keep defaults active, then load one explicit trusted user extension.
claude-renderpatch-candidate \
  --renderpatch-extension "$HOME/path/to/my-extension.mjs" --version

# Prove the signed bridge gate, default policies, and child environment cleanup.
claude-renderpatch-candidate --renderpatch-diagnose

# Use the same exact patched target and multi-provider arguments without any preload.
claude-renderpatch-candidate --renderpatch-safe --version

# Exercise installation integrity, conflicts, status, normal/safe modes, and cleanup.
uv run verify/candidate-launcher-harness.py
```

2.1.220 的 `in_process_teammate` view 另有一個 stock 資料供應 bug：running transcript
只保留 bounded live window，completed/failed 時更會被縮成最後一筆，而 `Ahl` 的磁碟回填 effect
只處理 `local_agent`。因此 renderer 實際只收到最後一筆；上方看似「第一句 prompt」的是 task
header，不是完整 transcript。可用 exact-artifact extension 從該 teammate 的 sidechain JSONL 回填最近
80 筆，不需新增 binary bridge：

```bash
claude-renderpatch-candidate \
  --renderpatch-extension "$PWD/candidate/subagent-view-history.mjs"
```

這個 extension 只在目前 viewing task 是 `in_process_teammate` 時作用，透過既有 d4 unsafe
store capture 合併磁碟上的最新 parent chain 與 live messages。它不改主 session、`local_agent`、
policy ownership 或 JSONL，並把 display state 限制在最多 100 筆。

The immutable release lives at
`~/.local/share/claude-renderpatch/releases/2.1.220-internal-sdk-2.1.220.1-97dfb182/`
and is linked only as `~/.local/bin/claude-renderpatch-candidate`. The exact-length REPL
replacement stores its five Unicode UI glyphs as ASCII `\\u` escape bytes; equivalent
`!!` coercion, iterable spread, and a compact unsigned-shift bitmap expression recover the
required 16-byte budget without changing the bridge sites or runtime contracts. Normal mode verifies
ownership, restrictive modes, the release manifest, code signature, and exact SHA-256 for the
candidate/bootstrap/extensions/helpers/manifests before setting one-shot preload and bridge
metadata. The proxy key and settings overlay must be user-owned, symlink-free `0600` files;
the TCP 8317 listener must be the current user's Homebrew `cliproxyapi`, and its bearer header
is supplied to curl over standard input rather than argv. Preload metadata is set only after
release/file checks, proxy startup, and the previous-model snapshot, then scrubbed immediately
when the target returns.
`--renderpatch-extension` is consumed by the wrapper, never forwarded to Claude, and accepts
only an explicit absolute user-owned regular module under the user's home with no symlink or
writable path component. Immutable defaults activate first; a user-module throw/rejection is
reported and skipped without disabling them. The first `--` ends wrapper-option parsing, so
all later tokens are forwarded verbatim and can never activate renderpatch options. No
current-directory or project code is discovered. Safe mode ignores the extension option,
verifies the same patched target, and scrubs all
preload/renderpatch state. Remove only this managed release with
`candidate/install.sh --uninstall`.

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

Developer-facing documentation（繁體中文）:

- [`docs/README.md`](docs/README.md) — developer/AI entry point and source-of-truth order.
- [`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md) — locally verified, intentionally denied,
  incomplete, packaging-gap, and future/unbridged status.
- [`docs/CAPABILITY-MAP.md`](docs/CAPABILITY-MAP.md) — runtime/read/action/policy/capture map.
- [`docs/BRIDGE-DEVELOPMENT.md`](docs/BRIDGE-DEVELOPMENT.md) — bridge design and maintenance rules.
- [`docs/internals/BANNER-RENDERER-2.1.220.md`](docs/internals/BANNER-RENDERER-2.1.220.md) —
  version-pinned Banner/Clawd/WelcomeV2 internals and proposed, unimplemented bridge boundary.

Engineering records:

- [`reference/root-cause.md`](reference/root-cause.md) — architecture and failure modes.
- [`reference/patch-intent.md`](reference/patch-intent.md) — exact bytes and source mapping.
- [`reference/preload-runtime.md`](reference/preload-runtime.md) — tested external preload
  behavior, security boundary, and update/repatch matrix; early implementation references predate runtime API 2.
- [`reference/internal-sdk-map.md`](reference/internal-sdk-map.md) — frozen pre-build domain,
  policy, lifecycle, and raw-slot contract; its `planned` status is historical.
- [`reference/bridge-intent-2.1.220.md`](reference/bridge-intent-2.1.220.md) — verified nine-site
  bridge record for the artifact later used by the local immutable candidate.
- [`REPATCHING-PLAYBOOK.md`](REPATCHING-PLAYBOOK.md) — rediscovery procedure after updates.

Verification:

- [`verify/docs.py`](verify/docs.py) — local Markdown file/link/anchor validation.
- [`verify/pty-harness.py`](verify/pty-harness.py) — repeatable expand/collapse/resize PTY test.
- [`verify/preload-harness.py`](verify/preload-harness.py) — repeatable latest-candidate
  preload, same-global, trust, failure, child-environment, and bypass tests.
- [`verify/candidate-launcher-harness.py`](verify/candidate-launcher-harness.py) — immutable
  single-command install, hash/mode, status, policy, safe-mode, conflict, and uninstall tests.

## Known tradeoffs / limitations

- V2 deliberately uses ED3 and can erase shell scrollback above Claude.
- Its destructive behavior applies to all full-reset paths, not only Ctrl+O and resize.
- Removing the frame caps raises memory/CPU costs on very large sessions.
- "Full" means every message currently loaded in display state; it cannot resurrect
  messages dropped by compaction/resume pruning (though they may remain in JSONL).
- The V2 Ctrl+O replacement reuses telemetry bytes, so it sacrifices the
  `tengu_toggle_transcript` analytics event.
