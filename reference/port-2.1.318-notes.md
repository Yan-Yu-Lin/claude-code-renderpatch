# 2.1.318 port — accelerated release

Branch: `feature/host-2.1.318-darwin`; resumed from Arthur's pushed WIP checkpoint `9ba9959`. Arthur explicitly replaced the full-gate prerequisite with bounded smoke/N1 verification and manual follow-up. The previous run's unfinished teammate gates are not represented as passing.

## Contents

Core: full-redraw R1–R9; explicit S1/S2 model routing; explicit revival of stopped agents with stop-race protection; disk-backed teammate transcript views; teammate background Agent/Bash ownership and notification delivery; exec launcher and model-restoration watcher. Upstream now handles restart-name registry reconstruction and capability-based orphan notices, so the old custom name scan and wording patches were dropped. Rediscovery details: [bridge intent](bridge-intent-2.1.318.md).

N1/N2 are a separate `tools/host_patches_2_1_318_mcp_bg.py` layer. Background plain agents and teammates may background eligible MCP calls; foreground subagents retain blocking behavior. Tasks carry owner identity and an `mcp:` keepalive. Completion routes to the owner or falls back to the lead; wake/sweep classification, queued-notice cleanup, delayed publication, TaskStop ownership and teammate exit are covered in the implementation. Server-side MCP Tasks eligibility remains unchanged.

A progress notification with `_meta["claudecode/backgroundNow"] === true` requests immediate handoff through a signal-keyed callback. The notice identifies a server request, not an arriving user message. Existing threshold, policy and elicitation checks remain in force. `remote-shell-mcp` was not changed.

## Candidate and verification

Candidate: `~/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.2/`.

- Official executable unchanged: SHA-256 `677a2ea7bf576cedd20e191d973914ed8a41796f53a63b1923381ddc4d5b5e7d`; 319598464 bytes; strict signature/team verified by builder.
- Manifest SHA-256: `180a0aae316a3e1ef8664b8865b4552a86c7e9bc1f29a738114be4225ab42b51`.
- All 85 replacements across 21 chunks passed global pre/postconditions. Checks occur immediately around each replacement, allowing later layers to refine earlier replacements.
- N1 quick check PASS: child background handoff 5.001s; main handoff 5.008s; both 20s calls completed; child task-notification reached the child and not the lead; main received its own task-notification. Actual background Agent input and transcript records were checked. Evidence: `patched/verification-2.1.318/fast-mcp-owner-quick/summary.json`.
- N2 quick check PASS on unchanged `.2`: marker at 2.009s, server-requested background tool result at 2.015s with the timer set to 60000ms. Evidence: `patched/verification-2.1.318/fast-marker-enabled/summary.json`. The first probe omitted `CLAUDE_AUTO_BACKGROUND_TASKS=1`, so headless backgrounding was disabled; correcting that prerequisite required no runtime/schema change. Headless consumers must retain this upstream opt-in.
- Status, normal/safe version, and a real proxy request passed on the candidate and again through the selected `~/.local/bin/claude-bridge` symlink. Final evidence: `patched/verification-2.1.318/fast-selected-smoke/summary.json`.

Prior `.1` evidence remains under `patched/verification-2.1.318/`: renderer controls, S1, genuine interactive S2, seven resume scenarios, slots/context windows, Mods, exec, isolated restore, child environment and tamper controls passed. ToolSearch and nested SDK foreground behavior passed. Idle compaction verification combined real proxy 1h cache creation with a simulated-clock upstream controller; no full wall-clock idle compaction was demonstrated. The invalid earlier headless S2 evidence is explicitly labeled `INVALID-BACKEND.json`.

## Manual verification limits

No full teammate-view/background gates were rerun. Their earlier incomplete runs had transcript-discovery, assertion and process-cleanup problems; no complete green verdict exists. Arthur should check long teammate transcript opening/growth/finished reopen, busy/idle teammate MCP delivery, Esc versus terminal stop, foreground-child blocking, own-task cancellation, stopped-owner fallback and eventual keepalive release. These are implemented but not all exercised in the accelerated run. The known auto-mode SubagentHandback ownership issue remains outside this default-mode port.

Quick harnesses use isolated configuration, explicit default permission mode, bounded subprocess waits, process-group kill on timeout and a summary written before cleanup. No user settings or remote-shell-mcp changes are intended.

## Selection and rollback

Atomically selected `.2` and passed the post-selection smoke. Receipt: `~/.local/share/claude-renderpatch/selections/2026-11-05-2.1.318-mcp-background.json`. `.7` remains installed as rollback; `.1` remains available as a core-only candidate. No existing Claude sessions were replaced. The branch is not merged.

```bash
rollback="$HOME/.local/bin/claude-bridge.rollback.$$"
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.7/claude-renderpatch-candidate" "$rollback" &&
  mv -f "$rollback" "$HOME/.local/bin/claude-bridge"
```

Rollback affects new launches only; it does not replace an already-running session's graph.

## `.3` — interactive children inherit host MCP policy (2026-11-05)

Arthur's C10/C11 manual test exposed a real `.2` defect: eligible children still passed their always-true `requestNonInteractive` flag to the upstream threshold check. The earlier quick gate's `CLAUDE_AUTO_BACKGROUND_TASKS=1` masked it. Both MCP clients now use `agentId ? ye() : options.isNonInteractiveSession` for **both** timer and movable-without-timer/N2 eligibility; `ye()` is the host launch predicate, not the child's request mode. Main calls, actual headless-session opt-in, explicit background-disable policy, foreground-child exclusion and server-side Tasks eligibility stay unchanged. No global environment variable or user configuration was changed.

Built and selected `~/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.3/`. All 90 global replacement checks passed. Status, normal/safe version and a real proxy `-p` smoke passed (`patched/verification-2.1.318/fix3-smoke/summary.json`). Exact built caller expressions and the host predicate are recorded in `fix3-policy-source.json`.

**Verification limit:** the interactive no-opt-in probe did not execute reliably. The first attempt matched prompt echo; the corrected attempt waited for an actual assistant record, timed out at 150s, and produced no transcripts. Summary preceded bounded cleanup, which completed in 0.134s. Evidence: `interactive-mcp-owner-quick-rerun1/`. No further harness debugging or full gates were run. Selection uses Arthur's explicitly permitted built-graph-proof fallback; interactive child/teammate result delivery and N2 timing on `.3` still need manual verification. Start a new Claude process: existing `.2` sessions retain their old graph.

Receipt: `~/.local/share/claude-renderpatch/selections/2026-11-05-2.1.318-mcp-parent-interactivity.json`. Immediate rollback is `.2`; the older `.7` rollback above remains installed:

```bash
rollback="$HOME/.local/bin/claude-bridge.rollback.$$"
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.2/claude-renderpatch-candidate" "$rollback" &&
  mv -f "$rollback" "$HOME/.local/bin/claude-bridge"
```

### Manual-test oddities — investigated, not patched

- **`run_in_background:false` still launches asynchronously:** stock `chunk-595kpmgv.js:yr` omits `run_in_background` from the effective Agent schema when `Wft() || DAt()` is true. The manual-session API schema indeed omitted it; the model emitted false, but it was already absent from the input handed to `subagent_guard.sh`. `To` then sees undefined and `Gr` chooses its background default; `chunk-56swczar.js:HO` derives the background request shape. The exact internal predicate enabling omission is inferred, but the schema/input omission is observed. The teammate patch's `Gr` change has no effect for this main caller (`s=false`); it is not N1 or the guard hook overriding false. Foreground blocking remains a contract for actual foreground children, not a guarantee that this interactive schema accepts that flag.
- **`team-lead` versus `main`:** stock `chunk-xfg1peqx.js:imn` resolves the former to a mailbox and the latter to the direct main queue. `chunk-nhbc679q.js:Ut` writes through `Uv`; lead mailbox consumption is `chunk-4z4cnx58.js:RS.poll`, wired to the loop's `afterRelease`. The `main` branch instead immediately enqueues `DC({mode:"prompt",agentId:ot(),priority:"next",...})`, allowing mid-turn absorption. The relevant `.2` routing blocks match stock; our teammate queue drain does not change the lead mailbox. The observed delivery immediately after `stop_hook_summary`, versus `absorbed_mid_turn` for `main`, matches these paths. Using `main` is the existing mid-turn route.
- **TaskStop described as rejection:** stock `chunk-363wfywp.js:ki.createSyntheticErrorMessage` maps this interruption to generic user rejection unless the abort reason selects its neutral interruption/remote-cancel branch. Our resume patch does not alter that mapping; no wording change was made.

## `.4` — block server prompt injection (2026-11-05)

Built `~/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.4/` with the complete `.3` graph plus `block-server-prompt-injection`. The builder applied 99 fail-closed replacements across 25 chunks. Release ID: `2.1.318-host-darwin-arm64-adf9cc07`. Manifest SHA-256: `997d7feabacc34e6f91bc432049704595091afbed6bd9fbd9c8aae01a0837818`.

The patch drops server-controlled free text from `tengu_heron_brook`, `tengu_brook_heron`, `tengu_toasty_thimble`, `tengu_gentle_parasol`, `tengu_kairos_brief_stop_hook_text`, `tengu_projects_thread_recap_prompt`, `tengu_cinder_plover`, and `tengu_cinder_wren`. Built-in fallback text remains where stock has one. Each distinct blocked channel/text pair is appended once per process/session to `~/.local/state/claude-bridge/blocked-injections.jsonl` with timestamp, model, full text and PID. `CLAUDE_BRIDGE_ALLOW_SERVER_PROMPTS=1` restores stock behavior.

Normal patched launches also append `-original_games_guidance` to `CLAUDE_CODE_MODEL_CAPABILITIES`. The parser strips `[1m]` before matching, and an unscoped capability entry applies to every model, including proxy IDs such as `claude-o55[1m]`. Safe mode does not set the override. The escape hatch does not set it either.

Verification passed: immutable status, normal version, safe version, real proxy `-p`, and `verify/server-prompt-block-2.1.318.py`. The synthetic test forced distinct text through every patched channel, confirmed null/block behavior, full JSONL records, same-process deduplication, and stock return values under the escape hatch. No full interactive UI, subagent, or teammate prompt capture was run. Those paths use the same patched prompt builders and shared reminder source, but Arthur should inspect a fresh main/subagent/teammate session if visual confirmation is wanted.

Rollback is `.3`:

```bash
rollback="$HOME/.local/bin/claude-bridge.rollback.$$"
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.3/claude-renderpatch-candidate" "$rollback" &&
  mv -f "$rollback" "$HOME/.local/bin/claude-bridge"
```

Rollback affects new launches only.
