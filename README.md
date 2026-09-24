# claude-code-renderpatch
Version-pinned renderer, provider-context, and explicit subagent-routing patches for Claude Code.
Verified source-graph bridges: **Claude Code 2.1.261 on macOS arm64** and
**2.1.246 on Linux x64**. The recipes and platform launchers are version-specific.

The Mac port preserves the five policy domains, six capture domains, inline full-history
redraw, provider context windows, explicit model routing, trusted extensions, proxy overlay,
and Herdr detection. It bundles Bun 1.4.1 and all 1,837 official graph records, including five
Mac native modules. See [the 2.1.261 build and verification record](reference/bridge-intent-2.1.261.md).

```bash
uv run tools/build-source-release-2.1.261-darwin.py \
  --stock /absolute/path/to/official/claude \
  --bun /absolute/path/to/official/bun-1.4.1 \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4"
```

The builder refuses to overwrite an existing release. Build and verify the versioned
candidate before selecting it as the daily launcher. The native binaries and extracted
application code are local build artifacts, not included in Git.

The `.4` Mac recipe also fixes Bash `grep`/`find`: only their shell helper target
uses the stock native `~/.local/bin/claude`, which supplies embedded ugrep/bfs.
The custom app and its policies still run through the bundled Bun/graph.
See the [repair and upgrade notes](reference/bridge-intent-2.1.261.md#grepfind-repair-2026-09-22).

Claude Code 2.1.245+ stores the application as a Bun ESM chunk graph rather than one readable
monolithic bundle. The Linux build therefore extracts all 1,576 embedded records, rewrites graph
paths, patches eight semantic sites in seven source modules, and runs the result with an immutable
bundled Bun 1.4.0 runtime. The official stock ELF remains unchanged.

Historical recipes remain for rediscovery:

- **V1** (`install_patch.sh`): 2.1.219 expand-only macOS patch.
- **V2** (`patches/full-redraw.sh`): 2.1.219 cumulative macOS byte patch.
- **Current Linux source release** (`tools/build-source-release-2.1.246-linux.py`): complete
  expand/collapse/resize replay, provider-aware context windows, capture domains d0-d5, and
  explicit subagent model routing.

## Developer and extension documentation（繁體中文）

本 repo 現在提供已在本機驗證的 **2.1.246 Linux x64 source-graph internal-SDK release**。
既有 2.1.220/2.1.226 文件仍保留為 runtime API 與 raw-slot 設計歷史；目前 release 狀態以
[`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md) 為準。

- **從這裡開始：** [`docs/README.md`](docs/README.md)
- **目前已驗證與未完成狀態：** [`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md)
- **Capability map：** [`docs/CAPABILITY-MAP.md`](docs/CAPABILITY-MAP.md)
- **撰寫 user extension：** [`docs/extensions/getting-started.md`](docs/extensions/getting-started.md)
- **Banner/Clawd internals：** [`docs/internals/BANNER-RENDERER-2.1.220.md`](docs/internals/BANNER-RENDERER-2.1.220.md)

2.1.246 Linux release 不修改 stock executable；它從 exact stock SHA-256 建置 immutable
source graph，並由 release launcher 驗證全部 asset hashes。它是本機 verified release，
不是公開 GitHub binary distribution。

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

## Historical 2.1.219 target binary

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

## Immutable 2.1.246 Linux x64 release

Build directly into a versioned immutable directory:

```bash
python3 tools/build-source-release-2.1.246-linux.py \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.246-internal-sdk-linux-x64.6"

python3 tools/build-source-release-2.1.246-linux.py --verify \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.246-internal-sdk-linux-x64.6"
```

The verified local release is:

```text
release_id=2.1.246-internal-sdk-linux-x64-7ebd85a5
bridge_build_id=internal-sdk-2.1.246-linux-x64.6
identity_sha256=a4daf31c711a640ef9e9693f494fc74e048a472e951d4546fcfd5e1f268b647e
```

`~/.local/bin/claude-renderpatch-2.1.246` points to that immutable launcher, and
`~/.local/bin/claude-bridge` uses it by default while retaining the explicit stock fallback:

```bash
claude-bridge --renderpatch-status
claude-bridge --renderpatch-safe --version
CLAUDE_BRIDGE_BIN="$HOME/.local/bin/claude" claude-bridge --version
```

The release contains the extracted graph, three native N-API modules, Bun 1.4.0, bootstrap,
default extensions, an asset hash list, and a release identity file. Files are read-only and
directories are non-writable. Normal launch rejects inherited preload/bridge metadata, verifies
all release hashes, then activates policies 0-4. Safe mode runs the same patched graph without
the preload; every source bridge falls back to stock behavior.

Verified behavior on Linux 2.1.246:

- Ctrl+O expansion, collapse, and resize replay all loaded transcript anchors;
- authoritative phases emit ED2 and ED3 from row zero;
- policy domains 0-4 and capture domains d0-d5 are live;
- collision/non-callable/throwing bridge fallbacks remain non-fatal;
- parent `gpt-5.6-luna` explicit `opus` subagent resolves to `claude-opus-5` through the real proxy.

## Historical 2.1.219 install

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

## Historical 2.1.219 uninstall

```bash
trash ~/.local/bin/claude-full-history ~/.local/share/claude/patched
```

## Other platforms

- **Linux x64:** implemented and locally verified for 2.1.246. The supported path is source-graph
  extraction plus a bundled Bun runtime, not in-place ELF byte mutation.
- **macOS arm64:** the historical 2.1.219 byte recipes and 2.1.226 internal-SDK candidate remain
  reference implementations.
- **Windows:** not packaged or verified. The same semantic sites should exist, but PE extraction,
  runtime packaging, and ConPTY verification still need a dedicated port.

[`verify/pty-harness.py`](verify/pty-harness.py) runs unchanged on macOS/Linux. A Windows port
needs equivalent ConPTY phase capture and ED2/ED3 assertions.

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
  historical bridge record for the original immutable candidate.
- [`reference/bridge-intent-2.1.226.md`](reference/bridge-intent-2.1.226.md) — current eight-range
  port identity, architectural delta, installation target, and verification record.
- [`REPATCHING-PLAYBOOK.md`](REPATCHING-PLAYBOOK.md) — rediscovery procedure after updates.

Verification:

- [`verify/docs.py`](verify/docs.py) — local Markdown file/link/anchor validation.
- [`verify/pty-harness.py`](verify/pty-harness.py) — repeatable expand/collapse/resize PTY test.
- [`verify/preload-harness.py`](verify/preload-harness.py) — repeatable latest-candidate
  preload, same-global, trust, failure, child-environment, and bypass tests.
- [`verify/candidate-launcher-harness.py`](verify/candidate-launcher-harness.py) — immutable
  2.1.220-era single-command install, hash/mode, status, policy, safe-mode, conflict, and uninstall tests.
- [`tools/build-source-release-2.1.246-linux.py`](tools/build-source-release-2.1.246-linux.py) —
  current Linux graph extraction, semantic patching, immutable packaging, and static verification.
- [`verify/raw-capture-behavior-2.1.246-linux.py`](verify/raw-capture-behavior-2.1.246-linux.py) —
  current Linux PTY fallback, collision, publication, replacement, and generation-safe clear verification.

## Known tradeoffs / limitations

- V2 deliberately uses ED3 and can erase shell scrollback above Claude.
- Its destructive behavior applies to all full-reset paths, not only Ctrl+O and resize.
- Removing the frame caps raises memory/CPU costs on very large sessions.
- "Full" means every message currently loaded in display state; it cannot resurrect
  messages dropped by compaction/resume pruning (though they may remain in JSONL).
- The V2 Ctrl+O replacement reuses telemetry bytes, so it sacrifices the
  `tengu_toggle_transcript` analytics event.
