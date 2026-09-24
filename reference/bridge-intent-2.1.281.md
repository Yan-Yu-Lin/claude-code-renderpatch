# Claude Code 2.1.281 — Darwin arm64 host bridge

Verified and selected 2026-09-24. This release supersedes the 2.1.261 source-graph bridge, which remains installed and intact as the rollback.

## Why the architecture changed

From 2.1.271, Claude Code's interactive renderer constructs `Bun.ant.CellSegmenter`, a native API that exists only in the Anthropic-internal Bun embedded in the official executable (reported as Bun 1.4.3, unpublished).

| Versions | CellSegmenter? | Embedded Bun |
|---|---|---|
| 2.1.267–2.1.270 | no | 2.1.267/268: 1.4.1; 2.1.269/270: 1.4.3 |
| 2.1.271, 2.1.272, 2.1.273, 2.1.280, 2.1.281 | yes | 1.4.3 |

An extracted graph run on published Bun 1.4.1/1.4.2 handles `--version` and `-p`, but the TUI never draws. The captured error is:

```
This build of @anthropic-ai/bun-internal has no Bun.ant.CellSegmenter; src/ink needs bun-internal >= the version pinned in package.json.
```

**So the extract + public-Bun method ends at 2.1.270.**

## Architecture

```
claude-bridge -> releases/2.1.281-host-darwin-arm64.1/claude-renderpatch-candidate
  verify: release manifest SHA, verifier SHA, every asset hash + mode, no unlisted files,
          runtime/claude SHA == official a922981f..., codesign --strict, TeamIdentifier Q6L2SF6YDW
  BUN_OPTIONS=--preload=<release>/host.mjs  runtime/claude --settings <overlay> --append-system-prompt <MIX_NOTE> ...
```

- `runtime/claude` is a byte-identical copy of the official `@anthropic-ai/claude-code-darwin-arm64@2.1.281` executable.
- `graph/` is its module graph, extracted with absolute import paths and carrying baked-in edits.
- `host.mjs` is the only preload. It does four things:
  1. Deletes `BUN_OPTIONS`, so no child process inherits the preload.
  2. Refuses to run outside a standalone executable that has `Bun.ant.CellSegmenter`.
  3. Imports `./graph/cli`, the patched entry. Its `Mt()` main starts asynchronously.
  4. Stops the embedded, unpatched entry at its first statement (next section).

### Stopping the embedded entry without breaking exit

After the preload settles, Bun evaluates the compiled entry `/$bunfs/root/cli`.
- Its static import closure is 6 small modules (33 KB) with no side effects beyond reading `process.cwd()`.
- Its body's first statement is `process.env.NoDefaultCurrentDirectoryInExePath="1"`.

The host replaces `process.env` with a one-shot Proxy that does three things:
- On a write of that key whose caller frame is `/$bunfs/root/cli`, it restores the real env object and throws a private sentinel.
- A prepended one-shot `uncaughtException` listener swallows the sentinel and then removes itself.
- Writes from anywhere else (including the patched graph's own write of the same key) pass through.

Result: the embedded `Mt()` never runs, and the patched app owns the process lifecycle. Natural exit works:
- `--version` prints once, exit 0.
- `-p` exits 0.
- Interactive Ctrl+C Ctrl+C exits 0 in 0.8 s, the same as stock.
- An invalid flag gives rc 1, the same as stock.
- The debug log contains no trace of the sentinel.

### Rejected interception approaches

Each was tested; the evidence is in `port-2.1.281-notes.md`.

| Approach | Problem |
|---|---|
| Never-settling preload | `--version` / `-p` never exit |
| `Bun.plugin` `build.module("/$bunfs/root/cli")` virtual module | Not applied to the compiled entry; both entries ran |
| `Bun.plugin` `onLoad` | Never fires for embedded bunfs modules |
| JSC `Loader.registry` | Absent in Bun |
| `process.getActiveResourcesInfo()` exit detection | Always `[]` in Bun |

## Baked-in edits

The modding ABI is retired: no `__rp` facade, policy domains, capture domains, extensions or `--renderpatch-extension`. Each former policy is replaced by the constant the retired default extension returned. All anchors occur exactly once in the whole graph, and every replacement is checked absent beforehand (fail-closed); see `tools/host_patches_2_1_281.py`.

| Site | Chunk | Before | After |
|---|---|---|---|
| Fullscreen selector | `chunk-5msfmr7e.js` | `function rl(e=N$){` | `function rl(e=N$){return!1;` |
| Inline latch (hook still runs) | `chunk-hkhfvq8c.js` | `function $O(){let o=Ie(re);` | `…let o=Ie(re);return"inline";` |
| DECSTBM renderer | `chunk-vnnj4fsp.js` | `function Qle(){` | `function Qle(){return!1;` |
| Full reset | `chunk-vnnj4fsp.js` | `function Xr(n,d,f,m,y,g){let C=m?0:` | Main-screen reset is destructive (`rp=!m`), replays from row 0, bumps `__rpResetEpoch` |
| Reset op | `chunk-vnnj4fsp.js` | `{type:"clearTerminal",reason:d,altScreen:m,…}` | Adds `destructiveReplay:rp` |
| Serializer | `chunk-35z18qft.js` | `i+=d.altScreen?Z6r():e2t(…)` | `d.altScreen\|\|d.destructiveReplay?Z6r():…` (`Z6r` = CSI 2J + CSI 3J + CSI H) |
| Messages: uncapped | `chunk-rsmxg7f6.js` | `D=v==="uncapped"\|\|de!==void 0,` | `D=!0,` |
| Messages: no virtualization | `chunk-rsmxg7f6.js` | `Ke=ee!=null&&!qe,` | `Ke=!1,` |
| Transcript show-all | `chunk-rsmxg7f6.js` | `Bo=q&&!fe&&!Ke,` | `Bo=!1,` |
| Ctrl+O redraw | `chunk-dkd7nfng.js` | `D()},Me[6]=Pe` | `__rpToggle(D)},…` (one `hrt()` forceRedraw after 50 ms unless a destructive reset already happened) |
| Explicit subagent model | `chunk-5mg9g7ss.js` (`XO`) | `if(Rwn(n,r))return r;` | `if(!1&&Rwn(n,r))return r;` (frontmatter call unchanged) |
| Named-teammate model | `chunk-ehps9anq.js` (`se`/`W`) | `se(n,e)` family shortcut | Shortcut skipped only for `modelSource==="tool"` |

Notes:
- In `Fh` (messages), both cap computations and the virtualizer read only `D`/`Ke`, which are already memo dependencies. No React compiler cache slots change.
- No REPL memo edits are needed. In 2.1.261 they existed only for capture domains.

## Dropped relative to 2.1.261.4

- **Provider context-window policy.** Replaced by the overlay's `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000`, verified below.
- **The Bash helper execPath edit.** `process.execPath` is now the official executable, which carries native ugrep/bfs.
- **The modding ABI:**
  - policy query facade;
  - six capture domains;
  - extension files and `--renderpatch-extension`;
  - `--renderpatch-diagnose`;
  - the preload bootstrap;
  - the pinned public Bun runtime.

## Verification (installed path)

- **Release:** `2.1.281-host-darwin-arm64-0a709331`
- **Manifest SHA-256:** `81a463752ebea8fbfa252c88bf5eb1fb8497a92dc67c1955b4620a979a6fd867`
- **Official executable SHA-256:** `a922981f6f3b55a251ef9f9dbaa0621a5f99cbcb5ca67f8a797476ccfc83f626`

| Check | Result |
|---|---|
| `--renderpatch-status` | `verification=ok`, proxy up, trusted listener |
| Tamper tests | Graph edit / host edit / extra file all refused (`asset hash mismatch`, `unlisted asset`) |
| `--renderpatch-safe --version`, normal `--version` | `2.1.281 (Claude Code)`, printed once, exit 0 |
| PTY (`verify/source-pty-2.1.281.py --assert-render`) | Every phase: exactly one ED2 + one ED3, first and last anchors, no alt screen, expanded detail only on expand |
| Stock + safe PTY controls | No ED2/ED3; oldest anchor missing after toggles |
| Proxied requests | `PORT_fable_OK`, `PORT_opus_OK`, `PORT_sonnet_OK`, `PORT_haiku_OK` |
| `/context` | fable 1m, opus 1m, sonnet 372k, haiku 372k |
| Subagent from parent `claude-sonnet-4-6`, `model:"sonnet"` | Actual `gpt-5.6-sol` (stock control: `claude-sonnet-4-6`) |
| Named teammate, same collision | Actual `gpt-5.6-sol` (stock control: `claude-sonnet-4-6`) |
| Bash tool child | `BUN_OPTIONS`/`RP_HOST_ENTRY` unset; `CLAUDE_CODE_EXECPATH` = release `runtime/claude` |
| MCP child | No `BUN_OPTIONS` |
| `/model` banner | Shows "Opus 5.5" natively for `claude-opus-5-5` |
| Overlay `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` | Task tools present |

The PTY harness now answers the DA1 query. It hard-codes the mix overlay and a synthetic 140-message transcript.

## Rebuilding and upgrading

```bash
npm pack --ignore-scripts @anthropic-ai/claude-code-darwin-arm64@2.1.281   # extract; read README
uv run tools/build-host-release-2.1.281-darwin.py --stock <package>/claude \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.281-host-darwin-arm64.<n>"
```

Things to know:
- The builder pins the official SHA, size, Anthropic team ID and the three native modules. It refuses an existing output directory.
- Graph imports are absolute, so the release must not be moved.

For a new version:
1. Re-discover the 12 anchors semantically. Do not reuse minified names.
2. Re-check the embedded entry's first statement and its static import closure. The host depends on both.
3. Re-run the full gate.
