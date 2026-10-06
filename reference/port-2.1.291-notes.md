# Port notes: 2.1.287 → 2.1.291 Darwin official-binary host

Completed on 2026-10-06 in `.claude/worktrees/bridge-2.1.291`, branch `feature/host-2.1.291-darwin`, based on `a71898dd52f1be8ca088254e2ff518b43055d0d4`. The [intent and verification table](bridge-intent-2.1.291.md) is authoritative.

## Required reading and scope

Read the repository README and the base worktree's current README completely; previous port notes, intent table, extractor, host patcher, builder, preload, launcher and PTY harness; canonical `project_claude_bridge.md`, `reference_claude_code_mods.md` and the alias-collision history. Work stayed in the new worktree. The prior worktree and rollback release remained unchanged.

Input `/tmp/cc291/package/claude` was already downloaded. The committed builder enforced SHA-256 `9a1d2ed6bb4421e8fc80c892c0413f293be3ee50ae3d7dda1a7622197a056690`, size 233211568, strict code signature and team `Q6L2SF6YDW`. Fresh extraction using the new recipe produced 2,493 records: 2,252 JavaScript, 99 text-loader, 139 file-loader and the same three native `.node` modules. Build metadata says `2026-10-06T02:24:19Z`.

## Entry interception and loader semantics

The trapped assignment remains `process.env.NoDefaultCurrentDirectoryInExePath="1";`, occurring once in `cli`. Its static closure is:

- `chunk-9td80jgd.js`: cwd/realpath capture and storage selector;
- `chunk-w8fnredk.js`: string-brand declarations;
- `chunk-462x54n1.js`: deep-link argument guard;
- `chunk-yvjhrpzg.js`: argument helper declarations;
- `chunk-090nhp1n.js`: gh stand-in dispatcher declarations/constants;
- `chunk-25y6gjjn.js`: AI_AGENT helper declarations.

None imports further graph modules. Only cwd/realpath reads execute at module scope. The entry itself has one function declaration before the assignment. The builder now explicitly requires exactly one trap in the entry and retains the existing executable-prologue refusal. A throwaway check confirmed the real declaration-only prologue is accepted and an appended executable statement is rejected.

`chunk-tacyqejf.js` and `chunk-z89fk9rg.js` contain two additional assignments. They do not invalidate the precondition: neither is an entry static import, and the host only intercepts a write whose caller frame is `/$bunfs/root/cli`. Version output once, natural successful exits, and invalid-flag exit 1 verify that the embedded CLI does not run twice.

Preserved the previous port's loader-13 fix in the builder and applied the same rule to the new standalone extractor. Every text-loader reference stays embedded; extracted files remain in the manifest. A comparison confirmed preservation across 18 JavaScript records. This avoids the known string-versus-module-namespace failure without patching the Mods compiler.

Preserved the leading `plugin test` argv fast path. No root options are inserted before or after that runner's arguments. The test is supplemented by live `--plugin-dir` command and `/plugin` checks in stock, host and safe sessions.

## Semantic rediscovery

| Site | 2.1.287 | 2.1.291 | Behavior |
|---|---|---|---|
| R1 fullscreen | chunk-qravq5t1.js · Sc | chunk-m6m73xp1.js · Hc | Return false before fullscreen selection. |
| R2 inline mode | chunk-jkt292h5.js · IO | chunk-vc97qmvg.js · wx / N1n | Keep the context hook and compiler memo; force the split resolver to inline. |
| R3 DECSTBM | chunk-p50qybax.js · WW | chunk-047zrb4c.js · D6 | Return false before cached probing. |
| R4 full reset | chunk-p50qybax.js · Ir | chunk-047zrb4c.js · Wl | Replay from row zero; advance reset epoch; mark destructiveReplay. |
| R5 serialization | chunk-nzck9a32.js · Lco / cYt | chunk-na5bb0t0.js · Iwo / gtn | Serialize destructive main-screen replay as ED2 + ED3 + home. |
| R6 message caps | chunk-1ypw9bby.js · W | chunk-03vmca9k.js · O | Force uncapped messages; retain compiler dependencies. |
| R7 virtualization | chunk-1ypw9bby.js · st | chunk-03vmca9k.js · lt | Disable virtualized message lists. |
| R8 transcript tail | chunk-1ypw9bby.js · Cs | chunk-03vmca9k.js · zn | Keep all loaded messages. |
| R9 Ctrl+O | chunk-f2cpzzp9.js · D / ddt | chunk-scapxbwa.js · M / Pmt | Redraw after 50 ms only if no full reset already advanced the epoch. |
| S1 plain override | chunk-5ne43w2c.js · LLn | chunk-g2d84gj0.js · Tzn | Bypass only the explicit-override same-family shortcut. |
| S2 teammate override | chunk-fkttf1dq.js · se / j | chunk-az8vv0m7.js · re / W | Pass existing source into re as rpSource; bypass shortcut only for tool source. |

The final recipe has 14 exact replacements across eight chunks. Uniqueness and replacement absence are checked globally, not merely inside the expected chunk. Duplicate-anchor, missing-chunk and already-patched input probes all refused.

R2 and R3 needed structural rediscovery rather than symbol substitution. The latch is split into React hook/memo `wx()` and resolver `N1n()`, so only the latter is forced inline. DECSTBM's old redundant outer block disappeared; `D6()` is now the direct cached probe. All renderer memo dependencies stay intact. B1 remains unnecessary because `process.execPath` is the official host.

### S2 stock reproduction and minimal fix

The 2.1.291 teammate resolver has new source tracking and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, but it still short-circuits aliases against the parent's family.

Stock interactive parent `claude-sonnet-4-6`, Agent `name:"routeprobe", model:"sonnet"`, returned `Spawned successfully.` with `arouteprobe-2b14d53d7effd8e2`. Its own transcript assistant records at lines 8,14,16,17,20 all say `claude-sonnet-4-6`. Thus S2 is still needed, independently of the plain Agent collision.

The tool handler assigns the post-hook explicit model to `ge`, then constructs `model:ge??Ko(O,qp(e))` and `modelSource:ge?"tool":"frontmatter"`. All three teammate backends already pass the source to `W(e,n,r="tool")`. The minimal patch passes that source into `re(e,n,rpSource)` and guards only the same-family shortcut with `rpSource!=="tool"`.

No blanket alias change: nonstandard-model resolution, explicit inherit, frontmatter inheritance, environment/default paths and FORCE stay stock. FORCE clears the explicit model before the modified branch. The added parameter must not be named `r`: `re` already has `let r=Fde()`. That collision was caught during integration before any candidate build; the committed parameter is `rpSource`.

S1 similarly disables only the plain explicit override shortcut, leaving its later frontmatter check unchanged. Both fixed routes were confirmed using actual child JSONLs, not model self-reports or requested tool parameters.

## Probe environment pitfall

The harness inherited `CLAUDE_CODE_CHILD_SESSION`. The first stock interactive routing attempt displayed that transcript saving was disabled; it was not counted as transcript evidence. The successful routing sessions explicitly enabled `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1` and emptied the inherited child/nesting markers. This is probe setup only, not a launcher or user-settings change.

Named probes were interactive with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and `--teammate-mode in-process`. Text and Enter were separate PTY writes. No headless named substitute or TeamCreate assumption was used. Plain headless probes also enabled persistence and supplied each anonymous child's own `subagents/agent-*.jsonl` as evidence.

## Candidate .1 and complete gate

The first immutable build passed; no rejected release or `.2` rebuild was needed:

- Release directory: `~/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.1`;
- release ID: `2.1.291-host-darwin-arm64-74d680c6`;
- manifest SHA-256: `dbb7ed915b18c14b3e0da8724dc8199b61456d08db4f35b0bd91c335292d35ab`.

Observed results:

- Status verified all assets and official signature; proxy listener trusted.
- Normal, safe and stock version each print once and exit 0; invalid flag exits 1 in all modes.
- Five renderer phases each emit exactly one ED2 and ED3, retain first and last messages, never enter alternate screen, and show expanded-only detail only when expanded. Stock/safe emit no ED2/ED3 and omit the first message. Safe and stock differ by 28 bytes in the first expansion, not by the measured behavior.
- All four real slots return their exact marker; interactive context limits and API metadata agree on 1M/1M/372K/372K.
- Plain and named child-own transcript records show candidate `gpt-5.6-sol`, stock/safe `claude-sonnet-4-6`; all six routing sessions exit 0.
- Official Mods validate and test pass in all three modes. Live command marker and `/plugin` one-active-mod display also pass in all three.
- Real Bash and MCP children have no preload/host variables. Bash uses the release's official executable as helper; tool request returns `CHILD_ENV_291_OK` without permission denials.
- An isolated APFS clone refuses graph tamper, host tamper and an extra asset with exit 1. The immutable candidate itself was never edited.
- Inherited `BUN_OPTIONS` is refused normally and scrubbed in safe mode.
- Ctrl+C twice exits 0 in candidate 0.477 s, safe 0.459 s, stock 0.345 s, measured in the same Mod UI scenario.
- Model restore: no saved model before; `/model gpt-5.6-sol` saves that model during the session; after wrapper exit the saved model is absent again.
- Custom IDs still trigger upstream `unrecognized_model` diagnostics; successful inference/context results are retained without suppressing the diagnostics.

## Selection and delivery

Only after every gate passed, committed the recipe as `9e983e69f70b79840d095fbfc4a6a5b3c76da1b1`. Created a sibling `claude-bridge.select-2.1.291` symlink and atomically replaced the live link with `os.replace`. The selection receipt records previous/new targets, release/manifest, recipe commit, evidence and rollback:

`~/.local/share/claude-renderpatch/selections/2026-10-06-2.1.291-host.json`

Selected-path smoke passed status, normal/safe version, live Mod command, `plugin test` (1 pass / 0 fail), and real Sonnet `SELECTED_291_OK`; all exit 0. The receipt includes those results.

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.287-host-darwin-arm64.2/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback" && mv -h "$HOME/.local/bin/claude-bridge.rollback" "$HOME/.local/bin/claude-bridge"
```

The rollback is the untouched 2.1.287 `.2` release, not its rejected `.1`. Plain `claude`, proxy configuration, overlay, other worktrees and Omarchy were unchanged. Overlay hash equality was checked after the gates. No package install or Desktop staging copy was used. The branch is delivered separately, without merging.

Disposable extraction, APFS tamper clone and throwaway drivers were removed with `trash` after their checks; the generated Mod copy and routing inspector are likewise disposable. JSON/ANSI evidence remains under the worktree's ignored `patched/verification-2.1.291/`. The committed versioned PTY harness and Mod fixture remain reproducible inputs.

## Evidence index

- `provenance.json`, `baseline.json`, `loader13-preservation.json`, `fail-closed-patches.json`;
- `render-host/summary.json`, `render-safe/summary.json`, `render-stock/summary.json`, with raw per-phase ANSI;
- `slots-summary.json`, `context-summary.json`, real `print-*.json` and context ANSI;
- `routing-summary.json`, `routing-verified-child-records.json`, `routing-patch-anchors.json`, `routing-probe-plan.json`;
- `mods-summary.json`, stock/host/safe Mod command/test/validation records and UI ANSI;
- `model-restore/summary.json`, `bash-child-env.json`, `mcp-child-env.json`, `child-isolation.json`;
- `tamper-graph.json`, `tamper-host.json`, `tamper-extra.json`, `reject-ambient-preload.json`, `safe-scrub-ambient.json`;
- `selected-*.json` and the external selection receipt.
