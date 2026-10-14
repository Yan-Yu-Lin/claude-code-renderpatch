# Claude Code 2.1.291 — background work for in-process teammates (release `.6`)

## Scope and provenance

2026-10-14 (Taiwan time). Branch `feature/host-2.1.291-teammate-bg`, worktree
`.claude/worktrees/bridge-2.1.291-teammate-bg`, based on `5617ea1` (`.5`, teammate transcript view).
Plan and problem statement: [`docs/internals/TEAMMATE-BACKGROUND-HELPERS-TODO.md`](../docs/internals/TEAMMATE-BACKGROUND-HELPERS-TODO.md).
Earlier research: `~/30-39-Research/34-tech-research/2026-10-14-claude-code-teammate-message-delivery.md` §5–6.

Goal (Arthur): a named teammate (`in_process_teammate`) can start a background Agent helper **and** a
background Bash task, keep working, and get the result **itself** at its next tool round, not in the lead.
If it is idle when the work finishes, it is woken and handles the result.

Recipe: [`tools/host_patches_2_1_291_teammate_bg.py`](../tools/host_patches_2_1_291_teammate_bg.py);
builder revision 6. 16 new replacements in 5 chunks; 57 in total with `.5`'s 41.

## What was wrong in `.5` (stock 2.1.291 behavior)

### Background Agent helpers (code, `chunk-s6pn7fn6.js`, Agent tool `call()`)

- Three throws "In-process teammates cannot spawn background agents" (explicit `run_in_background`,
  `background: true` agent definition, plugin `agent.spawn` hook).
- `To()`: `h=g||callerIsHeadlessSubagent` turns off the default-background path for a teammate, and
  `Yt=Vt&&!ke&&!Kt` turns off fork mode's `forceAsync`. With fork mode on (interactive default), the schema
  omits `run_in_background`, so the model's value was silently dropped and the helper ran in the foreground.
- Owner: `et=t3(Ie,j)??ze()`. `t3()` only accepts a `local_agent` parent, so a teammate's child would
  report to the lead.

### Background Bash (measured on `.5`, `/tmp/tbg6/b0`, evidence `b0-timeline.txt`)

- Allowed already. The task's `agentId` is the teammate's own agent id, so its notification is queued for the
  teammate.
- **Busy teammate:** delivered at its next tool round (the `pk()` query loop's per-round fold reads queued
  task-notifications whose `agentId` equals its own). Shell done 23:03:04, delivered 23:03:11.
- **Idle teammate: never delivered.** Shell done 23:03:15; the notification stayed queued. The runner's idle
  poll (`Xe()`) reads only `pendingUserMessages` and the mailbox file; the REPL wake router (`Ext`) only
  wakes `local_agent` owners. The lead got nothing either.
- Worse, code review: the per-turn cleanup at the end of every `pk()` run (`chunk-g2d84gj0.js`,
  keepalive-gated `nonShellMonitors` / `shellTasks` stages) runs whenever the turn was aborted or no
  background shell is running at that moment. `qs()` kills the agent's running shells **and**
  `xht(n=>n.agentId===se)` deletes every queued notification for it. For a teammate, `se` is the teammate
  itself, so: pressing **Esc** on a teammate turn killed its background shells, and an already-queued
  notification was deleted at the next turn end.

## The patch

| Id | Chunk | Before | After |
|---|---|---|---|
| T1a–c | `chunk-s6pn7fn6.js` | three teammate background throws | removed (comment markers) |
| T1d | same, `To()` | `h=g\|\|callerIsHeadlessSubagent` | `h=callerIsHeadlessSubagent` (teammate gets the same default background as the lead) |
| T1e | same | `Yt=Vt&&!ke&&!Kt` | `Yt=Vt&&!Kt` (fork mode forces async for teammates too) |
| T1f | same | `et=t3(Ie,j)??ze()` | `et=t3(Ie,j)??(ke&&Ie!==void 0?Ie:ze())` (owner = the calling teammate) |
| T2 | `chunk-v1gtm86q.js` `Ymt()` | owner kept only if it is a routable `local_agent`, else lead | also kept if it is a **live** (`status:"running"`, busy or idle) in-process teammate; appended helper `__rpLiveTeammate` |
| T3 | `chunk-ebe4qw6e.js` resume engine | caller adopts a resumed agent only if `t3(caller)` | a teammate caller adopts too (SendMessage to its finished helper → result returns to the teammate) |
| T4 | `chunk-zg4dkp5j.js` runner idle poll `Xe()` | mailbox + pendingUserMessages only | first takes queued task-notifications for this teammate (`__rpTakeQueued`), shows them in the transcript, and starts a turn with `origin:{kind:"task-notification"}` |
| T4b | same | keepalive only for running background shells (`bPe`) | also while a background agent it owns is running (`__rpHasLiveChildren`), so an idle-timeout reap (flag `tengu_zinc_harbor`, currently off) cannot strand it |
| T5 | same, turn end | only the mailbox is checked | if the mailbox has nothing, queued notifications for it start the next turn directly |
| T6 | `chunk-g2d84gj0.js` `pk()` cleanup | shells/monitors + queued notifications dropped when the turn is aborted or nothing is running | skipped whenever the run is a teammate turn (`fo!==void 0`); the runner exit policy owns that cleanup |
| Exit | `chunk-zg4dkp5j.js` both terminal exits | nothing for children | `__rpTeammateExit` per `STOPPED_TEAMMATE_POLICY` |
| Imports | runner | — | `uy,xht,Yi,_A,t$,Hu` (v1gtm86q), `ze as rpLeadId` (96kd8z4r), `er` (dv09tnvh). All already exported; the runner already imported those chunks, so no new cycle. |

No mailbox write, no provenance ledger change: delivery uses the existing in-memory message queue and the
existing `queued_command` fold, exactly like a plain `local_agent`.

### Lifecycle switch (`STOPPED_TEAMMATE_POLICY`)

A turn interrupt (Esc) is **not** a stop: after T6 it keeps shells and helpers (verified, G2).
When the teammate's runner really exits (kill / TaskStop, approved shutdown, idle-timeout reap, failure):

- `"stop-children"` (current default, set by the lead pending Arthur's decision): stop its running
  background agents (`_A(...,"parent")`) and shells (`t$`), stop its monitors, and hand any still-queued
  notification for it to the lead (same as stock `Fke()` for local agents). Nothing is orphaned or lost.
- `"revive"`: **not implemented.** The build refuses this value. Doing it means: on a child completion
  whose owner is a stopped teammate, call the teammate resume path (`resumeInProcessTeammate`,
  `chunk-y93p1tmb.js`) with the notification as its prompt. That contradicts `.4`'s rule that automatic
  wake paths respect a user stop, so it needs Arthur's explicit decision.

The switch is a single constant at the top of the recipe; changing it requires a rebuild (new release).

## Verification

Harness: separate `.6` launcher in tmux, `env -i`, `--setting-sources project,local` (no user hooks unless
listed), test-only `.claude/settings.json` in `/tmp/tbg6/<case>`, `--debug-file`, lead `sonnet`, teammates
and helpers `haiku`. Live `~/.claude/settings.json` and `~/.local/bin/claude-bridge` were not touched.
Timelines (from the transcripts' own timestamps, UTC in the files; Taiwan = +8) are in
`patched/verification-2.1.291-teammate-bg/` (ignored).

Reproduce:
1. Make a fresh `/tmp/tbg6/<case>/.claude/settings.json` that allows Bash/Agent/SendMessage/Read/TaskStop.
   For G3 with the hook, add a `PostToolBatch` entry for `teammate_inbox_wake.py`.
2. Launch with [`verify/fixtures/teammate-bg-launch.sh`](../verify/fixtures/teammate-bg-launch.sh)
   `<tmux-session> <dir> <launcher> --model sonnet --permission-mode bypassPermissions`.
3. Accept the folder trust prompt (Down, Enter), then bracketed-paste a prompt with `tmux paste-buffer -p`:
   [`teammate-bg-prompt-bash.txt`](../verify/fixtures/teammate-bg-prompt-bash.txt) (`.5` baseline),
   [`-g1`](../verify/fixtures/teammate-bg-prompt-g1.txt), [`-g2`](../verify/fixtures/teammate-bg-prompt-g2.txt)
   (for the Esc step, open the `esc` teammate from the footer and press Esc; vim mode needs an extra Esc),
   [`-g3`](../verify/fixtures/teammate-bg-prompt-g3.txt).
4. Read the result with [`verify/teammate-bg-timeline-2.1.291.py`](../verify/teammate-bg-timeline-2.1.291.py)
   `~/.claude/projects/-private-tmp-tbg6-<case>`, plus the runner lines in `debug.log`: `taking N queued`
   and `exited: stopping`.

### New gate results

| Case | Result |
|---|---|
| G1 busy teammate + bg Bash | done 23:41:28 → in teammate at next tool round (after own call 3) → teammate reported |
| G1 busy teammate + bg Agent | Agent returned "async launched" in 25 ms; meta `requestShape:"background"`, `parentAgentId`=teammate; done 23:41:47 → teammate after call 4 |
| G1 idle teammate + bg Bash | done 23:41:29.63 → teammate woken 0.33 s later, handled it |
| G1 idle teammate + bg Agent | done 23:41:57.19 → teammate woken 0.38 s later |
| G1 lead isolation | lead conversation contains none of the four notifications |
| G2 Esc during a teammate's foreground Bash | turn interrupted, teammate idle; bg shell and bg helper both survived and were delivered to it afterwards |
| G2 TaskStop of a teammate (`stop-children`) | runner exit logged stopping its shell (output ends `[killed]`, process gone) and helper; helper's stop notice went to the lead; no crash |
| G2 lead's own background helper | still notifies the lead at its next tool round |
| G3 teammate SendMessage-resumes its finished helper | second result returns to the teammate (with and without hook) |
| G3 lead → teammate message, with inbox-wake hook | delivered at next tool round (after own call 2) |
| G3 same, without hook | delivered at turn end (after own call 5): unchanged upstream behavior |

### Existing gates

Release identity: `2.1.291-host-darwin-arm64-74d62da2`, manifest SHA-256
`1948e998a9ea7867cd8a7df1fcd7158ab7dd6223bfefe595bb8c5ae5511965c1`. `runtime/claude` and `host.mjs` are
byte-identical to `.5`. After normalizing the release path inside imports, the graph differs from `.5` only in
the 5 patched chunks.

| Gate | `.6` result |
|---|---|
| status / version / safe version | `verification=ok`; `2.1.291 (Claude Code)`; exit 0 |
| invalid flag, normal / safe | exit 1 / exit 1 |
| four live slots (`-p`) | fable `claude-f51[1m]`, opus `claude-o55[1m]`, sonnet `claude-sonnet-5-5[1m]`, haiku `claude-h55[1m]`; exact markers |
| render host | 6 phases, each ED2=1/ED3=1, first+last present, expanded detail only when expanded, no alt screen |
| render safe | ED2=0/ED3=0, first absent (stock) |
| official Mods | validate 0; test 1 pass/0 fail; live command and `/plugin` UI pass |
| Bash child env | no preload/host variables; `CLAUDE_CODE_EXECPATH` = `.6/runtime/claude` |
| tamper | graph / host / extra asset refused; ambient `BUN_OPTIONS` refused; safe mode scrubs it |
| resume (7 scenarios) | taskstop, interrupt, restart, noauto, orphan, grouped, wakeafter: all pass |
| teammate view (`.5` PTY gate) | pass: 31/31, 40/40, 40/40, 40/40 tool rows; plain 5/5; 0 missing markers |
| routing | **gate verdict false on both `.5` and `.6`, identical results**: see below |
| context | **gate verdict false on both `.5` and `.6`, identical results**: see below |
| model restore | **not run**: it writes the real `~/.claude/settings.json`, which this task must not touch |

**Routing/context are configuration drift, not regressions.** On 2026-10-10 the overlay
`~/.claude/claude-mix-settings.json` was changed (backup `.bak-2026-10-10-pre-h55`). sonnet now maps to
`claude-sonnet-5-5[1m]` and haiku to `claude-h55[1m]`, all four slots 1M. The gate still hard-codes the old
expectations (`gpt-5.6-sol`, 372K). The `.5` control run (`host-control-r5/`) gives exactly the same values. The
routing fix itself still works: candidate children get the slot model `claude-sonnet-5-5`, not the parent's
`claude-sonnet-4-6`, while safe mode gives the stock `claude-sonnet-4-6`. Before the next release, the gate's
expected values should be updated to read the overlay.

**One flaky stall, not reproduced.** The first `.6` routing run used the gate's default cwd `/tmp/rp-host-gates`
(an untrusted workspace that loads the real user hooks). Its named-teammate spawn took 5 minutes to return. The PTY
then hung in `tcsetattr` after the gate's interrupt and had to be killed. A `.5` control in the same cwd and a
`.6` retry in the same cwd (`host-r6-tmpcwd-retry/`) both completed normally in about 1 minute. The routing path
for a lead spawning a teammate is not touched by this patch; recorded as an environment flake.

`~/.claude/settings.json`, the overlay, the `.5` manifest and the `claude-bridge` link were checked before and
after (`initial-provenance.json` / `final-provenance.json`): unchanged.

## Rollback / selection

Selection is Arthur's decision. Select `.6`:

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.6/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.select-2.1.291.6" && mv -h "$HOME/.local/bin/claude-bridge.select-2.1.291.6" "$HOME/.local/bin/claude-bridge"
```

Rollback to `.5`:

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.5/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback-2.1.291.5" && mv -h "$HOME/.local/bin/claude-bridge.rollback-2.1.291.5" "$HOME/.local/bin/claude-bridge"
```

## Rediscovery on the next version

Anchor on: the three "In-process teammates cannot spawn background agents" strings; `callerIsInProcessTeammate`;
`keepaliveReason:\`agent:${e}\`` (owner router); `"turn-end mailbox check failed"` and `poll #${N}: checking
mailbox` (runner); `{name:"shellTasks",keepaliveGated:!0` (pk cleanup); `observer-activity"?void 0:` (resume
adoption). Re-run the `.5` Bash baseline first: if upstream starts reading the queue in the idle runner,
T4/T5 become redundant.
