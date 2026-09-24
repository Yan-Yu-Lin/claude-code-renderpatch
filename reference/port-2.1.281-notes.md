# Port notes: Mac claude-bridge 2.1.261.4 → 2.1.281 (running log)

These notes are append-only, so the work survives a context loss or a handoff. The final record will be `bridge-intent-2.1.281.md`.

## Inputs

| Input | Value |
|---|---|
| Target | Claude Code **2.1.281** (npm latest, 2026-09-24; stable = 2.1.273) |
| Changelog check | 2.1.281 has no proxy regression. It has several proxy *fixes* (clean stream close, dropped events, trailing usage-only frame) |
| Stock package | `@anthropic-ai/claude-code-darwin-arm64@2.1.281` |
| Stock binary SHA-256 | `a922981f6f3b55a251ef9f9dbaa0621a5f99cbcb5ca67f8a797476ccfc83f626` |
| Stock binary size | 220931760 |
| Embedded Bun | bun-v1.4.3 (unpublished) |
| Candidate Bun | `@oven/bun-darwin-aarch64@1.4.2`, bun SHA-256 `35d20dd0263e5c950194434b925454fdfa9ba6e4467da960410fa05b08a7a5b5` |
| Staging | `/tmp/cc-2.1.281/{native,bun142,graph}` |
| Graph | 2266 records; 3 N-API modules (audio-capture, computer-use-input, computer-use-swift) |
| Smoke test | `--version` works under Bun 1.4.1 (release runtime) and 1.4.2 |
| Branch | `feature/internal-sdk-2.1.281-darwin` from 78449bd |
| First commit | 8c307e6, carrying the uncommitted 2.1.261.4 recipe (Bash helper) and the 2.1.280 evaluation |

## Scope (team-lead, 2026-09-24)

- **Include:** the renderer (patch 1), the Bash helper, and the asset list with 5→3 native modules.
- **Drop:** the provider window policy (patch 2). Overlay `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000` replaces it.
- **Optional:** patch 3, at both sites.
- **Overlay:** add `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`.

## Site table

(filled below as found)

## Site table (all anchors verified count==1 across the whole graph, 2026-09-24)

| # | Role | 2.1.261 (chunk · anchor) | 2.1.281 (chunk · anchor) |
|---|---|---|---|
| R1 | fullscreen selector | w7y6dfep `function Ta(e=KI){` | chunk-5msfmr7e.js `function rl(e=N$){` |
| R2 | inline latch | 9wy4tdk8 `function oO(){let r=De(de);` | chunk-hkhfvq8c.js `function $O(){let o=Ie(re);` |
| R3 | DECSTBM selector | q5rezcap `function iee(){` | chunk-vnnj4fsp.js `function Qle(){` |
| R4 | full reset (row-zero replay + flag) | q5rezcap `function Za(t,s,c,f,m,y){let b=f?0:` + clearTerminal obj | chunk-vnnj4fsp.js `function Xr(n,d,f,m,y,g){let C=m?0:` + `type:"clearTerminal",reason:d,altScreen:m,viewportRows:n.viewport.height,debug:g` |
| R5 | serializer ED2+ED3 | rvxxpz38 `i+=l.altScreen?JUn():Lat(l.viewportRows);` | chunk-35z18qft.js `case"clearTerminal":i+=d.altScreen?Z6r():e2t(d.viewportRows);`. Z6r = CSI 2J + CSI 3J + CSI H (rb=ma(2…),_ct=ma(3…),Kh=ma("H") in chunk-hn35vsf8) |
| R6 | messages: uncapped | 5vxbh0wn L7e `ZM=iQt==="uncapped"\|\|Ok!==void 0,` | chunk-rsmxg7f6.js Fh (memo w(240)) `fe=v!==void 0,D=v==="uncapped"\|\|de!==void 0,` |
| R7 | messages: no virtualization | `$x=hhe!=null&&!ain,` | `Ke=ee!=null&&!qe,` |
| R8 | messages: transcript tail truncation | `_he=om&&!yhe&&!$x,` | `Bo=q&&!fe&&!Ke,` (slices to last Ln) |
| R9 | Ctrl+O toggle + forced redraw | 5vxbh0wn x0 `X7e()},lA[6]=nZe`, redraw F5t | chunk-dkd7nfng.js vT `D()},Me[6]=Pe`, redraw `hrt(){ks().get(process.stdout)?.forceRedraw()}` |
| B1 | Bash helper execPath | 3963bmck `D[HJe]=process.execPath` | chunk-h3bc7dkc.js `G[l_e]=process.execPath` (l_e="CLAUDE_CODE_EXECPATH"); bin dir = `Y2()` exported from chunk-8bc0vvxx.js; platform `H()` already imported |
| S1 | subagent explicit site | 3963bmck cH `if(r==="inherit")return p();if(ojt(r,t))return t;` | chunk-5mg9g7ss.js XO `if(n==="inherit")return _();if(Rwn(n,r))return r;` |
| S2 | named-teammate site (never patched in 261) | xddhe4q4 re `if(e!==null&&ojt(t,e))return e;` | chunk-ehps9anq.js se `if(e!==null&&Rwn(n,e))return e;`, sole caller `W(n,e,o="tool")` → `let s=se(n,e),` |

Inside Fh, both cap computations (`ce=!Ke&&!D?Ni(l,te.preCap,yt*2):0` and the final-frame `Hu=!Ke&&!D?Ni(ut,te.slice,yt):0`) read only D/Ke. Forcing those two flags covers both caps, and the memo dependencies already include D/Ke/Bo. No memo slot changes are needed in Fh.

## Design decisions

1. **No REPL memo edits and no capture layer (d0–d5).** Every 2.1.261 edit in the REPL (`m5e` wrapper, `_(596)`→`_(597)`, `ls[596]`, `__rpShowAll` prop, `zYe` capture block, cleanup returns) served only one purpose: to publish raw capture domains d1/d2/d4 (and lift the show-all state for the `repl.showAll` capture action). None of it changes rendering. Show-all in the transcript is forced by policy bit 1 through R8.
   - **Consumers checked:** the installed `default.mjs` registers policies only. The only unsafe-capture consumers are `candidate/subagent-view-history.mjs` and `subagent-view-measure.mjs`, which are explicitly excluded from the bridge (unfinished experiment), plus docs examples. The fish `claude-subagent-test` targets the old 2.1.220 candidate.
   - **Effect:** this removes the riskiest part of the port (the memo indices). The bootstrap is unchanged: missing captures report `available:false`, and actions return `stale`/`unavailable`, so nothing fails hard.
   - The launcher status now prints `capture_domains=none`.
2. **Patch 2 dropped.** Provider window policy domain 3 is not queried by any 2.1.281 site.
   - `default.mjs` no longer registers mix-window.
   - `mix-window.mjs` / `internal-sdk.mjs` stay in the tree. If loaded, they register a handler that is never called, which is harmless.
   - Bootstrap domain 3 stays in its table (fail-closed).
   - The overlay's `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000` provides the 372k window.
3. **Patch 3 included at both sites.** S2 is gated to explicit tool-supplied models only. `W` passes `o==="tool"` into `se` as a third argument, so frontmatter/default teammate models keep stock semantics. This mirrors S1, where the frontmatter call is left alone.
4. **Bun:** primary candidate is 1.4.2 (npm latest, Oven-signed 7FRXF46ZSN, closest to the embedded unpublished 1.4.3). If it fails, fall back to 1.4.1. The decision is made from the verification results (below).

## BLOCKER found 2026-09-24: interactive UI needs Anthropic-internal Bun (Bun.ant.CellSegmenter)

**Symptom.** The extracted 2.1.281 graph works for `--version` and `-p` (real request "say hi" OK under Bun 1.4.2). The interactive TUI, however, never draws a frame: 100 bytes of mode setup, then nothing.
- This happens with the UNPATCHED graph too, on both Bun 1.4.1 and 1.4.2. My patches are not the cause.
- Stock binary in the same PTY draws normally.

**Root cause** (captured with a preload uncaughtException hook, `/tmp/cc-2.1.281/hangprobe.mjs`):
```
Error: This build of @anthropic-ai/bun-internal has no Bun.ant.CellSegmenter; src/ink needs bun-internal >= the version pinned in package.json.
  at Rs (chunk-vnnj4fsp.js) <- new tf <- new f1e <- onRender
```
The renderer's cell segmenter is a native API only in Anthropic's internal Bun (`bun-v1.4.3` embedded; unpublished). Published Bun 1.4.1/1.4.2 have `Bun.ant` without `CellSegmenter`.

**First affected version.** Found by scanning official binaries for `Bun.ant?.CellSegmenter`:

| Version | CellSegmenter? | Embedded Bun |
|---|---|---|
| 2.1.267 | no | 1.4.1 |
| 2.1.268 | no | 1.4.1 |
| 2.1.269 | no | 1.4.3 |
| 2.1.270 | no | 1.4.3 |
| 2.1.271 | **yes** | 1.4.3 |
| 2.1.272 / 273 / 280 / 281 | yes | 1.4.3 |

So the "extract graph + run under external published Bun" architecture ends at **2.1.270**.

**Side finding.** The builtin agents-md hooks module also fails in the extracted graph (`graph/hooks/register.ts: no such file`). It takes the non-compiled path because `Bun.isStandaloneExecutable` is false. This is non-fatal (AGENTS.md simply isn't loaded), but it is another divergence from stock.

## Candidate architecture: host the patched graph inside a verbatim stock executable

Experiment (`/tmp/cc-2.1.281/host-runner.mjs`):

```
BUN_OPTIONS=--preload=host.mjs RP_HOST_ENTRY=<release>/graph/cli <stock claude> ...
```

The host preload `await import(entry)` of the patched graph, then never settles, so the embedded entry never starts.

Result: the stock executable's internal Bun runs our patched chunks. The TUI renders fully (banner, prompt, footer), `Bun.ant.CellSegmenter` is present, and `isStandaloneExecutable=true`, so agents-md / embedded rg / self-exec behave as stock.

Open risks to verify:
- (a) process exit / "--version" completion when the patched app returns without `process.exit` (first `--version` try under `| head` did not return within 60s);
- (b) embedded entry must never start after the patched app ends;
- (c) BUN_OPTIONS/RP_HOST_ENTRY inheritance by children (subagents, Bash helper, hooks);
- (d) bootstrap + host preload ordering in one BUN_OPTIONS;
- (e) codesign/verification changes (runtime/claude instead of runtime/bun).

### Host-architecture experiments (2026-09-24, all in /tmp/cc-2.1.281)

| Experiment | Result |
|---|---|
| `host-runner.mjs`: `await import(patched cli)` then `await new Promise(()=>{})` | TUI renders fully under the stock executable. **But** `--version` / `-p` never exit, because the preload is pending forever and a pending top-level await blocks exit even after `beforeExit`. A PTY probe showed `--version` printed, then hung until SIGTERM. |
| `host2.mjs`: `Bun.plugin build.module("/$bunfs/root/cli")` to replace the embedded entry with an empty module, no pending await | The plugin is **not** applied to the compiled entry (`overridden=false`). The embedded **unpatched** entry runs after the patched one: `--version` printed twice. **Unusable as is.** |
| `plugin-probe.mjs` (`onLoad` filter on chunk-*.js) | Never fires for embedded bunfs chunks (`seen=0`). Runtime plugins cannot intercept the compiled graph. |
| `process.getActiveResourcesInfo()` | Returns `[]` in Bun even with timers, children and stdin active, so it can't be used to detect "app finished". |
| 2.1.270 extracted graph under published Bun 1.4.2 | Interactive TUI renders (banner/prompt). This confirms 2.1.270 is the newest version where the current architecture works. |

Also recorded: module records in the stock 2.1.281 `__BUN` carry **bytecode** (2040/2266). Byte-patching `__BUN` in place, the pre-2.1.245 method, would also need bytecode invalidation or stripping. That is not attempted.

### Status at stop

- **Done:**
  - Worktree and branch.
  - `tools/source_patches_2_1_281.py`: all renderer sites, the Bash helper, and patch 3 at both sites. Anchors are unique, and the build succeeds.
  - `tools/build-source-release-2.1.281-darwin.py` with Bun choice and the 3-native-module check.
  - `tools/extract-source-darwin-2.1.281.py`.
  - `candidate/source-launcher-2.1.281.in`.
  - `candidate/diagnostic-2.1.281.mjs`.
  - `preload/extensions-2.1.281/` (provider window retired).
  - `verify/source-pty-2.1.281.py` (answers DA1).
- **Dev build:** `~/.local/share/claude-renderpatch/staging/2.1.281-bridge-dev` (Bun 1.4.2) and `…-bun141`. The diagnostic under preload is all OK: bridgeActive, signed-bridge-artifact, policies 0/1/2/4 answered, provider window retired.
- **Blocked:** interactive TUI on any published Bun (no `Bun.ant.CellSegmenter`). None of the verification gate can pass, so **no release was built and `claude-bridge` was NOT repointed**. `~/.claude/claude-mix-settings.json` was NOT modified. 2.1.261.4 is still live and untouched.
- **Options for whoever continues:**
  1. **Host inside stock executable.** Needs a reliable way to (a) stop the embedded entry and (b) still exit normally. Ideas:
     - The preload awaits the patched app's own completion signal: wrap `process.exit` so it exits for real, and treat the `cli` `Mt()` promise settling as done. That requires exporting that promise from a patched `cli`, e.g. `export const __rpMain = Mt()`, then `await __rpMain; await flush; process.exit(process.exitCode ?? 0)`.
     - `-p` and `--version` paths that just return normally need the same handling.
     - Also check that children don't inherit `BUN_OPTIONS`. The bootstrap already deletes it; the host preload must too.
     - Codesign/verification must pin the stock executable SHA instead of Bun.
  2. **Pin 2.1.270** (last version without CellSegmenter). The current recipe works as is; the renderer sites need re-anchoring.
     - This does NOT meet the "same version as T3 Code" goal unless T3 is also pinned.
     - 2.1.270 lacks Opus 5.5 in the display table (that arrived in 2.1.280). The Opus 5.5 server gate needs UA 2.1.280, which the proxy already overrides, so requests would still work.
  3. **Implement a JS CellSegmenter shim.** Replace `Rs()` with a JS implementation. The native API surface covers graphemes/sgrKeys/uris/setCell/…, so this is large, and a correctness risk for the exact renderer Arthur cares about. Not recommended.

## Option A (host architecture), resumed 2026-09-24

### Entry-interception attempts

| # | Attempt | Result |
|---|---|---|
| 1 | Preload awaits `import(patched cli)`, then a never-settling promise | Renders, but `--version` / `-p` never exit (pending TLA blocks exit). Rejected. |
| 2 | `Bun.plugin build.module("/$bunfs/root/cli")` virtual override | Not applied to the compiled entry; the embedded entry ran too. Rejected. |
| 3 | `Bun.plugin onLoad` on chunks | Never fires for bunfs modules. Rejected. |
| 4 | JSC `Loader.registry` from the preload | `globalThis.Loader` undefined in Bun. Rejected. |
| 5 | **process.env write trap** (`/tmp/cc-2.1.281/host3.mjs`) | **Works.** Details below. |

How the env write trap (#5) works:
- The embedded entry's static import closure is only 6 tiny modules (cli + 5 helpers, 33 KB, no side effects beyond reading cwd).
- Its body's first statement is `process.env.NoDefaultCurrentDirectoryInExePath="1"`.
- The preload imports the patched cli (whose `Mt()` then runs asynchronously), installs a Proxy over `process.env` that throws a sentinel error on that key's write, restores the real env, and swallows the sentinel in `uncaughtException`.
- host4 stack capture confirms the first writer is exactly `/$bunfs/root/cli:11:629`. The real host checks for that stack frame, so the patched graph's own writes to the key (patched cli and chunk-qp0rn9dk) can never trip it.

Results:
- `--version` prints once, exit 0.
- `-p` returns `HOST3_OK`, exit 0 in 8 s.
- Interactive TUI renders.

### Consequences
- `process.execPath` is now the official binary, so the Bash helper (ugrep/bfs argv0) works natively. **Patch B1 is dropped.**
- `Bun.isStandaloneExecutable` is true, so agents-md, embedded rg and self-spawn behave like stock.
- The host deletes `BUN_OPTIONS` and `RP_HOST_ENTRY` first thing, so children spawned via execPath run stock 2.1.281 with no preload.
- The modding ABI is retired. Renderer and patch 3 are baked in as constants, equal to what the old default policy returned:
  - messages bits 2|(transcript?1:0)
  - reset destructive iff !altScreen
  - toggle redraw always
  - explicit routing shortcut never
