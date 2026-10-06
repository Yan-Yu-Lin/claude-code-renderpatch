# Claude Code 2.1.291 — Darwin arm64 host bridge

Verified and selected on 2026-10-06. This remains a patched source graph inside an untouched official executable, not a Mod implementation. Official Mods work alongside the renderer and routing patches.

## Selected installation

- Launcher: `~/.local/bin/claude-bridge`
- Release directory: `~/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.1`
- Release ID: `2.1.291-host-darwin-arm64-74d680c6`
- Build ID: `host-2.1.291-darwin-arm64.1`
- Manifest SHA-256: `dbb7ed915b18c14b3e0da8724dc8199b61456d08db4f35b0bd91c335292d35ab`
- Official executable SHA-256: `9a1d2ed6bb4421e8fc80c892c0413f293be3ee50ae3d7dda1a7622197a056690`
- Official executable: 233211568 bytes; strict signature verification passes; team `Q6L2SF6YDW`.
- Graph: 2,493 records: 2,252 JavaScript, 99 text-loader, 139 file-loader and three native modules (`audio-capture`, `computer-use-input`, `computer-use-swift`).
- Worktree: `.claude/worktrees/bridge-2.1.291`; branch `feature/host-2.1.291-darwin`, based on `a71898dd52f1be8ca088254e2ff518b43055d0d4`.
- Recipe commit: `9e983e69f70b79840d095fbfc4a6a5b3c76da1b1`.
- Selection receipt: `~/.local/share/claude-renderpatch/selections/2026-10-06-2.1.291-host.json`.
- Rollback: untouched `2.1.287-host-darwin-arm64.2`, release `2.1.287-host-darwin-arm64-700d43be`.

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.287-host-darwin-arm64.2/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback" && mv -h "$HOME/.local/bin/claude-bridge.rollback" "$HOME/.local/bin/claude-bridge"
```

## Host architecture and fail-closed boundaries

The [2.1.287 host architecture](bridge-intent-2.1.287.md) is retained. `host.mjs` removes `BUN_OPTIONS`, imports `graph/cli`, and intercepts the embedded entry's first `process.env.NoDefaultCurrentDirectoryInExePath="1";` write. Only a caller frame from `/$bunfs/root/cli` triggers its one-shot sentinel; process exit and signal handling remain with the application.

The entry still has six static helper modules. Their complete closure contains declarations/constants and cwd/realpath reads before the trap, with no new startup dispatch. The builder now explicitly requires exactly one trap assignment in `cli`, then rejects executable entry-body text before it. Two other chunks contain the same assignment, but neither belongs to the entry's static closure and neither matches the host's exact caller-frame filter. Normal and safe version checks both print once and exit 0.

Both the standalone extractor and release builder preserve every loader-13 reference at its original embedded path. The extracted copies remain hash-verified assets. The same official executable supplies compiled text-loader string semantics; no Mods-specific source patch or loader shim is added. Leading `plugin test` argv remains verbatim, without injected root options.

All 14 replacements across eight chunks require their old anchor exactly once across the entire graph, and their replacement absent globally. Missing chunks, duplicate anchors and already-patched input were exercised and refused. The startup parser accepted the real declaration-only prologue and rejected an injected executable statement. Construction enforced the existing SHA/size/signature/team checks; no existing release directory was reused or edited.

## Baked-in patches

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

R2 changed structurally: the old combined hook/latch function is now `wx()` plus `N1n()`. Patching only the resolver keeps the context hook and compiler cache slots intact. R3 is now a direct cached probe without the old redundant block. Existing cap/virtualizer dependencies remain in React's compiler memo; no cache indices changed.

**B1 stays omitted.** Bash receives the release's official `runtime/claude` as `CLAUDE_CODE_EXECPATH`; it already contains the native helpers.

### Named-teammate decision

**S2 is still required.** A real stock interactive in-process teammate requested with explicit `model:"sonnet"` under parent `claude-sonnet-4-6` ran as `claude-sonnet-4-6`, confirmed from its own JSONL assistant records. This is not inferred from tool arguments, telemetry, or the model's self-description.

Upstream now tracks source explicitly: the Agent handler uses the post-hook tool model `ge=x.model`, passes `model:ge??Ko(O,qp(e))` and `modelSource:ge?"tool":"frontmatter"`, and all three teammate backends pass that source to `W`. The minimal patch passes `W`'s existing source parameter into `re(e,n,rpSource)` and changes only its same-family guard to require `rpSource!=="tool"`.

The `inherit` branch, the nonstandard-model resolution branch, frontmatter shortcut, environment/default fallbacks and new `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` precedence remain stock. FORCE clears the explicit model before the patched branch. `rpSource` deliberately avoids collision with the resolver's existing local `let r=Fde()`.

## Verification results

Evidence: this worktree's ignored `patched/verification-2.1.291/`. No package installation was needed.

### Renderer and lifecycle

The versioned PTY harness loads 140 synthetic messages and responds to DA1. `--assert-render` passed on the immutable candidate:

| Phase | Candidate bytes | ED2 / ED3 | First / last | Expanded detail | Alternate screen |
|---|---:|---|---|---|---|
| expand | 62080 | 1 / 1 | both | present | no |
| collapse | 48716 | 1 / 1 | both | absent | no |
| resize | 54724 | 1 / 1 | both | absent | no |
| expand_again | 66941 | 1 / 1 | both | present | no |
| collapse_again | 54735 | 1 / 1 | both | absent | no |

Stock and safe controls both have ED2=0, ED3=0, first=false, last=true, no alternate screen and no expanded-only detail in all five post-startup phases. Stock byte counts are `3539,39004,16819,3182,43377`; safe counts are `3511,39004,16819,3182,43377`. They match behavior, not every byte: the first expand capture differs by 28 bytes. All three harness processes exit 0.

| Check | Observed result |
|---|---|
| Status | `verification=ok`; proxy up; trusted current-user `cliproxyapi` listener |
| Normal / safe / stock version | Exactly one `2.1.291 (Claude Code)` line; exit 0 |
| Invalid flag, normal / safe / stock | Exit 1, unknown-option error |
| Ctrl+C twice, same mod UI | Candidate 0.477 s; safe 0.459 s; stock 0.345 s; all exit 0 |
| Changed graph / host, isolated APFS clone | Exit 1: `asset hash mismatch: graph/chunk-03vmca9k.js` / `asset hash mismatch: host.mjs` |
| Extra asset, isolated clone | Exit 1: `unlisted asset: unexpected-asset` |
| Inherited `BUN_OPTIONS` | Normal refuses with exit 1; safe scrubs it, prints version and exits 0 |
| Model restoration | No saved model → live `/model gpt-5.6-sol` saves it → no saved model after exit; exit 0 |

### Provider slots and context capacities

| Slot | Actual model | Real response | Exit | Interactive `/context` |
|---|---|---|---:|---|
| fable | `claude-f51[1m]` | `PORT_fable_291_OK` | 0 | `56.2k/1m tokens (6%)` |
| opus | `claude-o55[1m]` | `PORT_opus_291_OK` | 0 | `56k/1m tokens (6%)` |
| sonnet | `gpt-5.6-sol` | `PORT_sonnet_291_OK` | 0 | `33k/372k tokens (9%)` |
| haiku | `gpt-5.6-luna` | `PORT_haiku_291_OK` | 0 | `33k/372k tokens (9%)` |

API `modelUsage.contextWindow` independently reports `1000000,1000000,372000,372000`. Upstream emits `unrecognized_model` diagnostics for these custom IDs; successful responses and capacities are recorded, not suppressed. The settings overlay's SHA-256 remained `80ec190fefb781e1c4e6253ad214f2f6cf27496886f151dd1a345e7d0942e4ce`.

### Routing and child isolation

Parent `claude-sonnet-4-6`, explicit child alias `sonnet`:

| Mode | Path | Child actual model | Session ID |
|---|---|---|---|
| stock | named-teammate | `claude-sonnet-4-6` | `8f34a679-61ad-4807-97ad-0236a51df903` |
| candidate | named-teammate | `gpt-5.6-sol` | `0325d5b5-67f3-42ae-ab9b-71f94c0a1b3e` |
| safe | named-teammate | `claude-sonnet-4-6` | `865df6ce-bb4a-4242-916f-6177d281912f` |
| stock | plain-agent | `claude-sonnet-4-6` | `5b615e3d-a4dd-451e-bfcc-988aaec4fcdd` |
| candidate | plain-agent | `gpt-5.6-sol` | `859d5764-af6a-4412-acfc-e345aa162bf4` |
| safe | plain-agent | `claude-sonnet-4-6` | `ca1a27d9-db10-4d8b-bee0-de4ea5b4215d` |

All six sessions exit 0. **Both paths use each child's own `subagents/agent-*.jsonl` assistant `message.model` as primary proof.** `routing-summary.json` records exact paths, hashes and line numbers; `routing-verified-child-records.json` independently extracts those records. Named parent transcripts contain `Spawned successfully.` and the actual `arouteprobe-...` identity. Named tests are interactive, with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and `--teammate-mode in-process`; no TeamCreate assumption or headless named substitute was used.

Real Bash and MCP children both report `BUN_OPTIONS`, `RP_HOST_ENTRY`, `CLAUDE_RENDERPATCH_ACTIVE` and `CLAUDE_RENDERPATCH_TARGET` unset. Bash's helper executable is the release's official `runtime/claude`; MCP's `CLAUDE_CODE_EXECPATH` is unset. The actual tool request returned `CHILD_ENV_291_OK`, exit 0, with no permission denials.

### Official Mods

Fixture: `verify/fixtures/mod-2.1.291/`, registering `/renderpatch-hello` through `session.start` and implementing `command.run`. Verification used an ignored copy to keep generated type declarations out of the tracked fixture.

| Check | Stock | Candidate | Safe |
|---|---|---|---|
| `plugin validate` | Pass, exit 0 | Pass, exit 0 | Pass, exit 0 |
| `plugin test` | 1 pass / 0 fail | 1 pass / 0 fail | 1 pass / 0 fail |
| Live `-p /renderpatch-hello` | Fixture marker, exit 0 | Fixture marker, exit 0 | Fixture marker, exit 0 |
| Interactive `/plugin` | 1 mod active | 1 mod active | 1 mod active |
| Interactive command | Fixture marker | Fixture marker | Fixture marker |

Marker: `renderpatch-mod-fixture: RENDERPATCH_MOD_2_1_291`. Live parent-session loading is essential: isolated `plugin test` alone cannot validate extracted-graph text-loader behavior.

### Selected-path smoke

After the recipe commit and atomic symlink replacement, the daily launcher passed status, normal/safe version, the live mod command, official `plugin test` and a real Sonnet request returning `SELECTED_291_OK`. All six checks exit 0 and are recorded in the selection receipt and `selected-*.json` evidence.

## Rebuild and limits

```bash
python3 tools/build-host-release-2.1.291-darwin.py \
  --stock /absolute/path/to/official/2.1.291/claude \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.1"
```

The builder refuses an existing output. Choose a fresh `.2`, `.3`, etc. for another candidate; imports are absolute, so completed releases must not move. Keep the selected rollback until every gate passes.

The [port log](port-2.1.291-notes.md) records rediscovery and probe pitfalls. Existing releases, plain `claude`, CLIProxyAPI configuration, the settings overlay, other worktrees and Omarchy were not modified. Verification covers the fixture Mod and exercised routes, not every third-party Mod or teammate backend. Full redraw erases native scrollback with ED3 and increases work for large loaded transcripts; it cannot recover messages already removed by compaction.
