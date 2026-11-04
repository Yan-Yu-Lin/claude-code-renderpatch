# Claude Code 2.1.318 — Darwin arm64 host bridge

## Architecture and provenance

The bridge runs a patched source graph inside a verbatim Anthropic-signed official executable. It does not byte-patch or re-sign the executable, replace the embedded Bun runtime, or restore the retired extension ABI.

- Branch: `feature/host-2.1.318-darwin`, based on `feature/host-2.1.291-rex-foreground` commit `8644140`.
- Worktree: `.claude/worktrees/bridge-2.1.318`.
- Official npm package: `@anthropic-ai/claude-code-darwin-arm64@2.1.318`.
- Official executable SHA-256: `677a2ea7bf576cedd20e191d973914ed8a41796f53a63b1923381ddc4d5b5e7d`.
- Official executable size: 319,598,464 bytes.
- Strict signature verified; team `Q6L2SF6YDW`.
- Graph: 3,116 records; 2,872 JavaScript, 103 text-loader, 138 file-loader, three native modules.
- Native modules: `audio-capture.node`, `computer-use-input.node`, `computer-use-swift.node`.
- First core candidate: `~/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.1/`.
- Core release ID: `2.1.318-host-darwin-arm64-adf9a7b5`.
- Core manifest SHA-256: `ca8305fc956aa09f68ef22a984fde3f2127debfa16c0a828b5bb98a2dd545dca`.

Selection and the final gate verdict are recorded in [port notes](port-2.1.318-notes.md). The rollback target is the untouched `2.1.291-host-darwin-arm64.7` release, not `.6`.

## Entry interception and loaders

`cli` still contains exactly one `process.env.NoDefaultCurrentDirectoryInExePath="1";` host trap. Before it, the body contains only a function declaration and seven static helper imports. Their complete closure was reviewed: declarations/constants plus cwd/realpath capture only. The new seventh helper is the storage-mode latch. The builder checks the exact static helper set, rejects unexpected transitive graph imports, and refuses executable entry text before the trap.

The helpers are `chunk-sr5zgxjs.js`, `chunk-h58p4vvs.js`, `chunk-kw79qzsb.js`, `chunk-3na38vnk.js`, `chunk-6c7y6v7r.js`, `chunk-34713hc6.js`, and `chunk-bgsak306.js`. Entry parsing now also recognizes the upstream side-effect import form.

The unmodified graph under the new host printed exactly one version line and exited 0; an invalid option exited 1. The real entry prologue was accepted and an injected executable statement rejected. Text-loader references remain embedded in the exact official host; extracted text files remain manifest assets. This preserves compiled string-loader behavior required by live Mods.

The launcher preserves `.7`'s `exec`: Claude replaces the shell process, and a detached model-restoration watcher runs after that PID exits. `MIX_NOTE` describes all four slots as Anthropic. `plugin test` retains verbatim argv. No settings overlay or user settings change is part of this port.

## Core semantic rediscovery

The first core build applies 56 exact replacements across 18 chunks. Every replacement requires global `(old,new)` counts `(1,0)` before and `(0,1)` immediately afterward. Duplicate anchors, missing chunks, and already-patched input are refused. Appended helper text is separately uniqueness-checked.

| Behavior | 2.1.291 site | 2.1.318 site |
|---|---|---|
| R1 fullscreen off | `m6m73xp1` · `Hc` | `3df33mkc` · `Nd` |
| R2 inline resolver | `vc97qmvg` · `wx/N1n` | `v5qk8x3w` · `mM/i1r` |
| R3 DECSTBM off | `047zrb4c` · `D6` | `qfycx4yg` · `fj` |
| R4 destructive reset | `047zrb4c` · `Wl` | `qfycx4yg` · `Ol` |
| R5 ED2+ED3 serialization | `na5bb0t0` · `Iwo/gtn` | `8n1d4f6t` · `JVs/Wwt`, serializer `N0o` |
| R6 uncapped messages | `03vmca9k` · `O` | `2388he8y` · `ee` |
| R7 no virtualization | `03vmca9k` · `lt` | `2388he8y` · `ce` |
| R8 full transcript | `03vmca9k` · `zn` | `2388he8y` · `Jo` |
| R9 Ctrl+O redraw | `scapxbwa` · `M/Pmt` | `p2q3ejfg` · `O/TLt` |
| S1 explicit plain override | `g2d84gj0` · `Tzn` | `0x9x817t` · `aV/z8r` |
| S2 explicit teammate override | `az8vv0m7` · `re/W` | `0h62541d` · `ne/W/z8r` |
| Reply-mode resume | `ebe4qw6e` · `Qt`, mode `ce` | `z45ktpqq` · `Ur`, mode `B`, reply wrapper `Xzr` |
| Stopped target classifier | `dj0tea96` · `X` | `xfg1peqx` · `X` |
| Additional SendMessage stop precheck | absent | `nhbc679q` · `stoppedByPerson` refusal |
| Orphan auto-resume exclusion | `jdcpjj4f` · `os` | `7fv02std` · `Hn`; sidecar `yb`, stop-sibling `DCn` |
| View retention enter/leave | `scapxbwa` · `Du/fZ` | `0x9x817t` · `E1/k1/Wut` |
| Disk hydration | `scapxbwa` · `kMe/ese` | `p2q3ejfg` · `Pqe/ede`, plain merge `xqe` |
| Bounded teammate cache | `9ag6ybmh` · `uJn/GBe/e6o` | `ygm0kzqk` · `dto/Ult/Q_i` |
| Teammate append | `m5sckpqa` · `d2n/pHt` | `me4n0c3r` · `l2r/gGt` |
| Teammate runner/view lifecycle | `zg4dkp5j` · `Qe` | `nyc0s6f6` · `q$o` |
| Off-view kill eviction | `qm1h7fwt` · `Son/Ght` | `nn5f14r9` · `a8n/YO` |
| Background Agent decision/owner | `s6pn7fn6` · `To` | `595kpmgv` · `To/Gr`, `He/wn/lt` |
| Completion owner router | `v1gtm86q` · `Ymt` | `0x9x817t` · `K3t` |
| Resume owner adoption | `ebe4qw6e` · `Qt` | `z45ktpqq` · `ie` adoption |
| Idle/turn-end notification drain | `zg4dkp5j` · `Xe/Qe` | `nyc0s6f6` · `Qe/q$o` |
| Teammate per-turn cleanup protection | `g2d84gj0` · `pk` | `56swczar` · `HO` |

Chunk basenames in the table have the `chunk-` prefix and `.js` suffix omitted for readability. Recipes contain the complete exact before/after anchors.

## Preserved invariants

- R1–R9 preserve React hook/memo dependencies and request only one authoritative redraw per toggle/reset epoch.
- S1 bypasses only explicit tool-model same-family matching. S2 passes existing `modelSource` through `W` into `ne` and bypasses the shortcut only for `"tool"`. FORCE, inherit, frontmatter, environment/default precedence and allowlists remain upstream.
- Stop still kills and marks the agent. Only explicit SendMessage reply mode bypasses stopped-marker refusal. The `userStopCount` snapshot check still rejects a stop landing during a resume. Clearing uses upstream's guarded sidecar and race-safe sibling-marker operations.
- Orphan scanning reads metadata and the current stop-sibling marker once; read errors fail closed for automatic restart.
- Teammate views use `identity.resumableAgentId`, never the TUI task ID. Epoch, selected task, start time, status and source identity guard hydration. A terminal transition invalidates a pending read even if `diskLoaded` was already false.
- Only retained teammate views bypass the 50-row cache. Off-view bounds, explicit model-context compaction, persistence, and task retirement remain unchanged.
- Background results use the existing queue and the owner teammate; busy delivery is the stock per-tool-round fold, with explicit idle/turn-end draining added.
- Esc is a turn interruption, not teammate exit. Terminal policy remains `stop-children`: stop owned Agents/Bash/monitors and forward queued notices to the lead. Automatic stopped-teammate revival is not introduced.
- Upstream `I5e` already covers background Bash/monitors, `XXr` handles 180-second background-subagent shell handoff, `JXr` distinguishes timed/message-arrival handoff, and `wDs` withdraws an inline-delivered Bash notice. These paths remain intact.

## Upstream-covered pieces dropped

The custom sidecar name-directory scan from `.4` is removed. Upstream `chunk-qb6krrm5.js:y9n` reconstructs `agentNameRegistry` from successful Agent/Workflow transcript pairs, and both SDK startup and interactive rehydration call it. The gate still requires fresh-process SendMessage by name.

The old orphan wording/grouping substitutions are removed. Upstream now builds capability-based notices describing stop/failed possibilities and whether SendMessage may continue the agent. The port fixes missing behavior—excluding stopped/unreadable agents from auto-resume—rather than maintaining stale text. Gates assert transcript, stop-marker, task-start and completion transitions, not exact wording.

No full-redraw, S1/S2, teammate-view, teammate-background, or exec-launcher behavior was dropped. The known `auto`-mode SubagentHandback ownership issue is not changed by this default-mode port.

## Rebuild

```bash
python3 tools/build-host-release-2.1.318-darwin.py \
  --stock '/Volumes/111360128 Lin Yan Yu/DevCache/claude-bridge-2.1.318/package/claude' \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.1" \
  --revision 1
```

The builder refuses existing outputs. Choose a fresh revision/path for another build; graph imports contain the final absolute release path, so releases must not move. N1/N2, when enabled, are a separate recipe selected by `--mcp-background`; the final port notes record whether they were included and their gate verdict.

## N1/N2 layer

`tools/host_patches_2_1_318_mcp_bg.py` adds 34 replacements over the core: 90 total across 21 chunks. Build with `--mcp-background`, a fresh release directory, and matching `--revision`. `.2` first included this layer; `.3` corrects the child-interactivity policy described below.

- Both MCP clients (`6jypdf2f`, `r2ksrv9a`) allow background plain agents and in-process teammates, but retain foreground-child blocking and existing policy/threshold decisions. Server-side MCP Tasks eligibility stays main-only.
- Eligible child calls pass the host launch's interactivity to both `getMcpAutoBackgroundMs` and `isMcpCallMovableWithoutTimer`, rather than their always-headless child request flag. The stock `ecyypctx:ye()` reads `!host.launchOptions.isInteractive()`; the first MCP client imports it as `__rpMcpHeadless`, and the second reuses its existing import. Main calls retain their original context flag. Interactive children therefore inherit main's threshold/N2 eligibility without a global environment override; actual headless sessions retain upstream opt-in policy.
- `kdb20esk:De` records the caller's `agentId` on the new MCP task, acquires `mcp:<taskId>`, and routes normal/degraded completion through `0x9x817t:K3t`. A missing/stopped owner falls back to the lead. TaskStop uses the existing ownership check.
- `Gne`, `gar`, and `_Rt` recognize MCP work. Deferred `noticeGate` publication is protected by `__rpMcpNoticePending`; enqueue failure, stopped tasks, and task conversion release the keepalive. Queued owner notices survive until consumption; stopped-owner queue forwarding includes MCP tasks.
- The teammate runner's live-child predicate includes owned running MCP calls. Terminal teammate exit aborts those calls; Esc remains only a turn interruption.
- `kdb20esk:Ie` recognizes only `_meta["claudecode/backgroundNow"] === true`. A module-local WeakMap registers each eligible child AbortSignal with its early-handoff callback and removes the registration in `finally`. The main-only message-arrival registry is not broadened. The server-trigger notice explicitly says the server requested backgrounding.

Each replacement still enforces global old=1/new=0 before and old=0/new=1 immediately afterward. The redundant end-of-composition replay was removed because N1 intentionally refines the core's owner router and runner helpers; their earlier replacement strings no longer exist verbatim after layering.

Arthur explicitly authorized bounded smoke/owner/marker checks rather than completion of the earlier full gate campaign. See the port notes for observed results and manual verification limits; this is not a claim that every lifecycle scenario passed.
