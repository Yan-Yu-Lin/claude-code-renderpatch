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
