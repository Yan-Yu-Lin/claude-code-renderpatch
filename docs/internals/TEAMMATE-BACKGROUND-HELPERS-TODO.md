# TODO: background helpers for in-process teammates (binary patch)

Status: **not started.** Problem and plan written down 2026-10-14 (Taiwan time) by the lead of the DRG modding session.
Arthur will run the patch work in a separate session. Target: claude-bridge 2.1.291 release `.5` → new release `.6`.

Full research (read §5 and §6 first):
`~/30-39-Research/34-tech-research/2026-10-14-claude-code-teammate-message-delivery.md`
Test transcripts it cites: `~/.claude/projects/-private-tmp-tbg-t0`, `-tbg-d1`, `-tbg-d2` (and `-tiw-hook`, `-tiw-hook3`,
`-tiw-ctrl` for §5).

## 1. The problem (observed in a real session)

- The lead spawns named agents. With `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` a named agent becomes an
  **in-process teammate** (`taskKind: in_process_teammate`).
- Teammate `god-chat-design` spawned a Sonnet helper with `run_in_background: true`. The helper's meta.json says
  `requestShape: "foreground"`. The teammate sat inside that one Agent tool call for about **1.5 hours**: it did no work
  of its own, and messages from the lead couldn't reach it, because the inbox-wake hook (below) only fires when a tool
  call ends.
- Arthur's position: a helper that blocks its parent is pointless. A teammate must be able to start a helper in the
  background, keep working, and get the helper's result back **at its own next tool round**, not in the lead's session.

## 2. What is already solved (don't redo)

- **Messages to a busy teammate** used to arrive only at turn end: the per-tool-round `teammate_mailbox` collector `lEr()`
  is an empty stub in every build 2.1.220–2.1.299. Fixed without a binary patch by the PostToolBatch hook
  `~/.claude/hooks/teammate_inbox_wake.py`. When the teammate's inbox holds an unread non-protocol message, it returns
  `{"continue": false}`; the turn ends normally, the runner's turn-end mailbox check delivers the message, and the next
  turn starts. Wired in `~/.claude/settings.json` (claude-config commit `67f2aab`), tested live (research §5).
- `~/.claude/hooks/subagent_guard.sh` allows one helper layer (haiku/sonnet only). It identifies helpers by
  `parentAgentId` in meta.json (claude-config `3ca4a0f`). `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2` is the backstop.

## 3. Why teammates can't have background helpers today [verified in 2.1.291 `.5`, research §6.1]

All in `graph/chunk-s6pn7fn6.js`, the Agent tool's `call()`:
1. `ke = !!e.teammateContext`. `ke && run_in_background === true` throws "In-process teammates cannot spawn background
   agents". The same applies to an agent definition with `background: true` and to a mod's `agent.spawn` forcing background.
2. `To()` picks foreground/background. `callerIsInProcessTeammate` disables both the default-background path and fork
   mode's `forceAsync` (`Yt = Vt && !ke && …`).
3. With fork mode on (the interactive default, `PIo()` → "default", `Coe()` true), the Agent input schema omits
   `run_in_background` (`xkr()`). The model's value is dropped at parse time, so there is no error: the helper silently
   runs in the foreground.

What it protects (**the real blocker**):
- Background completion goes through `Kmt()` / `Ymt()`. The notification owner is `t3(parentAgentId) ?? ze()`, and `t3()`
  only accepts a parent that is a `local_agent` (`Pn()`). For a teammate parent it returns undefined, so the result would go
  to the **lead**, not the teammate.
- The teammate runner (`chunk-zg4dkp5j.js`) reads only its mailbox and `pendingUserMessages`, at turn end and in the idle
  poll `Xe()`. It never drains the message queue where task-notifications land.
- So there is no path in 2.1.291 for a teammate to receive a background child's result.

Contrast [verified, test D2]: a plain unnamed background subagent (`local_agent`) can start a background helper (returned
in 11 ms), keep working, and receive the helper's task-notification at its next tool round. The lead does not get it.

## 4. The patch to make (research §6.4 c)

Arthur's requirement in his words: when the background helper finishes, its result must go **back to the sub-agent that
spawned it, not the main agent**, re-invoke that sub-agent if needed, and push the result in.

1. **Allow it:** remove the `ke && run_in_background === true` throw and the `callerIsInProcessTeammate` suppression of
   default-background / `forceAsync` in `To()`. Decide whether the schema should expose `run_in_background` to teammates
   when fork mode is on.
2. **Route the result to the teammate:** in `Kmt()` / `Ymt()`, when the parent is an `in_process_teammate`, write the
   task-notification into **the teammate's inbox** with the existing mailbox writer `sb()` (`from` = the helper's
   description) instead of the lead's queue.
   - While the teammate is running, the inbox-wake hook then delivers it after the next tool call. Without the hook it
     arrives at turn end.
   - While the teammate is idle, the `Xe()` poll picks it up and wakes the teammate, which covers the "re-invoke it" part.
   - Don't use the message queue: an idle teammate never reads it.
   - Keep provenance consistent with the ledger (`ame()` / `I().wrote`) so the message isn't flagged `forged`.
3. **Lifecycle:** when a teammate is killed or reaped by idle timeout, stop its background children; or don't reap a
   teammate that still has live children (keepalive). Make sure nothing is orphaned or reports to a dead teammate.

Optional, related: fill in the empty `lEr()` collector, so teammates read their inbox every tool round natively; then the
inbox-wake hook can be removed. Research §4 c has a draft.

### 4b. Same gap for background **Bash** commands (observed 2026-10-14)

- Teammate `selfstatus-a7` ran its astra review (`omp-sub`) with the Bash tool's `run_in_background: true`, ended its
  turn ("the completion notification will wake me") and went idle at 20:27. The command finished at 20:30 (task output
  `b5o9f1rkw.output`, exit 0, verdict HOLD). The teammate was never woken; the lead didn't see a notification either. It
  sat idle about 2.5 hours until the lead read the output file and sent it a message.
- [inferred, not traced] Same root cause as §3: background task notifications go to the message queue, which a
  teammate never reads. Check `Kmt()`/`Ymt()`, or whatever notifies on shell-task completion, for the owner computation.
- Fix in the same patch: when a teammate's own background shell command ends, write the completion notice into the
  teammate's inbox (as in §4 step 2). The idle poll `Xe()` then wakes it; while running, the inbox-wake hook delivers it.
- Possible hook-only workaround (untested): a PreToolUse hook on Bash, inside teammates only, that rewrites a
  `run_in_background` command to also write an inbox message to that teammate when it exits. Risks: writing the inbox from
  outside Claude Code (the `.lock` directory protocol; ledger provenance `unverifiable`/`forged` may get the message
  filtered or flagged). Verify how `ke()` treats an unverifiable message before relying on it.
- Test: a teammate starts `sleep 30` in the background and ends its turn; it must wake and act on the result within a
  second or two of the command finishing.

## 5. Tests the new release must pass

Reuse the research §6.3 harness: a separate claude-bridge in tmux, `env -i`, a test-only `--settings` copy, a /tmp
working dir, cheap models. Never this live session or the real settings until repointed.
- Teammate starts a background helper (`sleep 60`) and keeps running its own short calls. The Agent call returns at once;
  the teammate's calls continue; the helper result reaches **the teammate** at its next tool round; the lead gets nothing.
- The helper finishes while the teammate is idle: the teammate wakes and receives it.
- A shutdown_request or kill of the teammate while the helper is still running: the helper is stopped or handled, with
  no orphan and no crash.
- The lead's own background agents still notify the lead as before.
- Messages to the teammate still arrive (with and without the inbox-wake hook).
- All existing renderpatch gates, plus these as a new gate. Repoint claude-bridge only after everything passes;
  rollback = point back to `.5`.

## 6. Notes

- Function names are minified and change per version. Anchor on strings: "In-process teammates cannot spawn background
  agents", "callerIsInProcessTeammate", `Al("teammate_mailbox"`, "turn-end mailbox check failed".
- Upstream: anthropics/claude-code #30492, #35072, #71723, #80604. Nothing in 2.1.292–2.1.299 relaxes this.
- Until the patch ships, interim rule in Arthur's sessions: teammates shouldn't start long helpers; plain unnamed
  background subagents can.
