# Why a "stopped" background subagent refuses SendMessage resume (2.1.291)

Research only, 2026-10-07. No release, symlink, or running process was changed. Graph is the selected
release `~/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.1/graph/`. Chunk names are
2.1.291-specific; the anchors in the last section are meant to survive renaming.

Labels: **[verified in code]** = read in the graph; **[verified in logs]** = seen in the on-disk transcript,
sidecar, or T3 provider log; **[inferred]** = reasoning from both; **[needs runtime test]** = not executed.

## Short answer

- The agent `identity-watch` (`ae2f1aca5722ed636`) was not stopped by a person. The **SDK interrupt sweep**
  marked it as stopped. On an SDK `interrupt` control request, if the client did **not** declare
  `perTaskStopAffordance`, Claude Code kills every running background agent and **labels each one
  `stoppedByUser:true`**. It also writes that label into the agent's `.meta.json` sidecar.
  The resume code then refuses any agent with that label. **[verified in code + logs]**
- The "resume it with SendMessage" notice comes from the orphan scan of the **next** process. That scan never
  reads the sidecar's `stoppedByUser`, so its advice contradicts the refusal. **[verified in code]**
- The `name:` is **not** the cause. Naming only explains the second error ("No agent named ... is
  reachable"): the name map exists only in memory and is empty after a restart. **[verified in code]**
- A fix is feasible and small. Remove one call in the sweep, so system sweeps stop labelling tasks as
  user-stopped, and keep explicit user stops as they are. The real risk is semantic, not technical.

## Coordinator's data point: why this subagent resumed but identity-watch did not

| | identity-watch `ae2f1aca5722ed636` | this research agent `a0befcf0019102b20` |
|---|---|---|
| Spawned with `name` | yes (`identity-watch`) | no |
| How it stopped | T3 sent `query.interrupt` then `query.close` (13:35:24.556 UTC) | T3 sent only `query.close` (13:43:36.706 UTC), with no interrupt |
| Sidecar `.meta.json` | `"stoppedByUser":true` (written 21:35:24 local, same second) | no `stoppedByUser` key |
| SendMessage result | `was stopped by the user and won't be resumed` | **resumed OK** (coordinator message arrived 13:45:52 UTC; work continued) |

So the difference is **(a) how it got stopped**: an interrupt followed by a sweep, versus a plain process exit.
It is not (b) the name. **[verified in logs + code]** This resume of the research agent is itself the
positive control: a background agent orphaned by process exit, without the sidecar marker, resumes fine
through SendMessage by agentId. **[verified at runtime]**

## Timeline of the incident (UTC) [verified in logs]

Sources: `~/.t3/userdata/logs/provider/events.9c7deb5c-….log`, parent transcript
`~/.claude/projects/-Users-linyanyu/fb26bff9-….jsonl`, and subagent `subagents/agent-ae2f1aca5722ed636.jsonl`.

1. 13:31:57: identity-watch starts a foreground Bash `omp-sub --model gpt-6-astra …` (a long review call).
2. 13:35:21.882: T3 sends `/compact`. The CLI reports `status: compacting`.
3. 13:35:24.552: the task record for identity-watch becomes `killed` (`end_time 1791380124552`). Then
   `background_tasks_changed: []` and `task_notification status:"stopped"` follow.
4. 13:35:24.556 / .557: T3 logs outgoing `query.interrupt`, then `query.close`. The CLI prints
   `Compaction canceled.` (the abort-signal branch in `chunk-970cashr.js`).
5. 13:35:24.583: the subagent transcript gets `tool_result is_error: "The user doesn't want to proceed with
   this tool use…"` plus `[Request interrupted by user for tool use]`. Its sidecar is rewritten with
   `stoppedByUser:true` at 21:35:24 local.
6. 13:35:35: T3 sends `query.open` with `resume: fb26bff9…`, which starts a new CLI process. The logged options
   contain no `perTaskStopAffordance`.
7. 13:35:38: the new process enqueues the orphan notice ("didn't finish before the previous session ended …
   Resume it by sending it a message with SendMessage").

Step 4 is logged about 4 ms after step 3. T3 probably logs the interrupt after writing it. The only code that
both cancels compaction and kills plus marks background agents in the same instant is the interrupt path
below. **[inferred]** The logs do not show what made T3 send the interrupt: a Stop click, or T3's own logic
on `/compact`. **[needs runtime test]**

## Q1: where the refusal is produced and where the flag comes from

### The refusal [verified in code]

`chunk-ebe4qw6e.js` contains the resume engine. `Ce(e, mode)` is exported as `Ezn` (mode `"reply"`, used by
SendMessage) and calls `Qt(...)`. `Qt` reads the transcript and the sidecar in parallel:

```js
[Tt, n] = await Promise.all([ ese(yo(e), …), Kx(yo(e), s.storageV5) ])   // transcript, .meta.json
…
if (n?.stoppedByUser && g?.kind !== "observer-activity") {
  if (!M) throw (k(), new OU(`Agent ${e} was stopped by the user and won't be resumed. …`))
}
```

`M` is `userInitiated`. `OU` is `AgentStoppedByUserError`. A second, in-memory guard appears later in `Qt`,
just before the new run is registered:

```js
W = u.get(e);
if (Pn(W) && W.stoppedByUser && (!M || (W.userStopCount ?? 0) !== ee)) throw (k(), new OU(`…won't be resumed…`))
```

This second guard catches a stop that races with an in-flight resume (`ee` holds the stop count at the time
the resume began). It is worth keeping.

There is also a third, different wording in the SendMessage resolver. `chunk-dj0tea96.js` `X()` returns
`{kind:"agent-stopped-by-user"}` when the **in-memory** task has `stoppedByUser`. `chunk-y93p1tmb.js` then
replies `Agent "…" was stopped by the user and was **not** resumed.` The user saw "**won't be** resumed", so
the refusal came from `Qt`'s **sidecar** check. That fits a post-restart lookup: the task was not in memory,
so the resolver returned `agent-evicted` and called `Ezn` and then `Qt`. **[verified in code; inferred for
which branch fired]**

### The flag setter [verified in code]

`chunk-t73sf08e.js`:

```js
function ure(e, r, n) {                        // "mark user stop"
  r.update(e, (p) => Pn(p) ? { ...p, stoppedByUser: !0, userStopCount: (p.userStopCount ?? 0) + 1 } : …);
  if (r.get(e)?.type === "local_agent") fn(e, agentType, n);   // fn → UPe(yo(e), {...meta, stoppedByUser:!0})
}
```

`fn` persists the marker into `subagents/agent-<id>.meta.json`. Nothing ever clears it. The worktree-cleanup
rewrite in `chunk-g2d84gj0.js` `WOr` even carries it forward. `FFe` (a user `TaskStop` on an evicted id) uses
`Yoe(...,{stoppedByUser:!0})` and writes the same marker.

### Who calls the setter

| Caller | Trigger | Really a user stop? |
|---|---|---|
| `__e` (StopTask core), `if (r.source==="user") ure(...)` | user TaskStop / task UI | yes |
| `chunk-scapxbwa.js` (several `ure(...)` sites) | TUI task panel stop, stop-all, kill from agent view | yes |
| **`dre()` sweep, `chunk-t73sf08e.js`** | see below | **no, it marks unconditionally** |

`dre` is the "stop all running background agents" sweep:

```js
function dre(e){ let {taskRegistry:r,setAppState:n,shouldStop:s,storageV5:p}=e; JOt(e);
  for (let g of Object.values(r.all())) { …filter running background agents/workflows…
    if (ure(g.id,r,p), g.type==="local_agent") zx(g.id,r), Qgn(g.id);      // ← labels as user-stopped
    y4e(g.type)?.kill(g.id,r,n,"system",p); …Bi(g.id,"stopped",…) } }
```

It passes the kill source `"system"`, yet it still calls the user-stop marker. Callers of `dre`
(`chunk-rysf7q6m.js`, `chunk-9jn7d7yq.js`):

- **SDK interrupt control request.** `$e` handles `subtype:"interrupt"` and calls `Bt()`:
  `if (s7t()) { spared: JOt(M) } else { dre(M) }`. `s7t()` is `sdkPerTaskStopAffordance()===true`.
  **This is what happened here.**
- SDK rewind with `interrupt_if_running` (`Bt()` again, and `mb()` → `dre({shouldStop})` for agents after the cut).
- `--max-budget-usd` halt (`zl`), held-result release while aborted (`Sy`), the engine loop when the queue is
  non-empty after an abort, and `$b`.

So the answer per trigger:

| Trigger | Sets `stoppedByUser`? |
|---|---|
| explicit user stop (TaskStop, task UI) | yes (by design) |
| SDK/T3 interrupt without `perTaskStopAffordance` | **yes, by the sweep** |
| SDK interrupt with `perTaskStopAffordance:true` | no (agents are spared, `JOt` kills only observers) |
| budget halt, rewind cut, aborted held results | yes (sweep) |
| `/compact` itself, or compaction cancel | no direct path; the cancel is a *symptom* of the same interrupt |
| plain process exit / `query.close` / restart | no; this is the orphan path, and those agents resume (this agent proved it) |

The `perTaskStopAffordance` description in `chunk-0p8skvm3.js` makes this explicit: "ABSENCE also fails
closed: the interrupt kills background tasks". The kill is intended. The *user-stopped* label is the
over-reach.

## Q2: the contradictory notification [verified in code]

`chunk-jdcpjj4f.js` `os({asyncAgents, notifiedTaskIds}, …)` runs when a session is resumed. It collects
async agents from the transcript that have no recorded completion notification, logs
`resume: N background agent(s) orphaned by previous process exit`, and stats each transcript's mtime:

- If the transcript is non-empty, the status is `"stopped"` with the note "…may have been stopped, or it may
  have been running when the previous Claude Code process exited — either way its transcript is saved …
  Resume it by sending it a message with SendMessage …".
- A 48-hour auto-resume branch (`es=172800000`) also exists. It needs a callback `s`; it did not fire here.

`os` reads the sidecar (`Kx`) only as `hasMeta`, for the auto-resume branch. It **never checks
`stoppedByUser`**. The old process did emit `task_notification stopped` at 13:35:24.555 (it is in the T3 log).
But that process was closed about 2 ms later, before the parent transcript recorded the notification as
delivered. So the new process treated the agent as an orphan and gave the generic "resume it" advice, while
`Qt` refuses because of the sidecar.

## Q3: how a normal resume works, and is it safe without the guard

Path [verified in code]: SendMessage (`chunk-y93p1tmb.js`) → resolver `Z0t` (`chunk-dj0tea96.js`). Agent ids
resolve through `iA(id)`; names resolve through the in-memory `agentNameRegistry`. Then `X()` returns one of:

- `agent-live`: the message is queued for its next tool round.
- `agent-stopped`: in memory but not running. Calls `Ezn`.
- `agent-evicted`: not in memory, for example after a restart. Teammate-mailbox and in-process-teammate
  checks run first, then `Ezn`.

`Ezn` → `Ce` takes a per-agent `resumesInFlight` lock. Then `Qt`:

1. refuses if the agent or caller is still stopping (`hL`, `xb`, `js(status)`);
2. sets `resuming:true` on the task record, or throws `already running or being resumed`;
3. reads the transcript and sidecar;
4. applies the `stoppedByUser` guard and the forked-skill scoping guards;
5. rebuilds the agent with the transcript messages plus the new prompt, re-registers its name, and registers
   a new task (`DQ`) under the same agentId;
6. re-checks the in-memory stop guard and runs.

With the sidecar guard removed, a swept agent takes exactly the path this agent took after its plain process
exit. **[inferred, consistent with the positive control]** Danger assessment:

- **Duplicate running agent: low.** The `resumesInFlight` lock, the `resuming` flag, the "still stopping"
  check and the running check all stay. **[verified in code]**
- **Corrupt transcript: low.** The sweep ends the in-flight tool call with a proper `tool_result is_error`
  plus an interrupt marker, as identity-watch's last lines show. Resume therefore starts from a well-formed
  turn boundary. **[verified in logs]**
- **Lost tool results mid-call: real but benign.** The killed tool (here `omp-sub`) did not finish, and the
  agent only sees "user doesn't want to proceed". After a resume it must re-run that step, and the new
  prompt should say so. Side effects the killed child already caused remain. **[inferred]**
- **Semantic risk, the main one.** After the patch, an agent stopped by a T3/SDK *interrupt* becomes
  resumable by the model. If Arthur pressed Stop to kill a runaway agent, the parent model could revive it.
  Explicit stops (TaskStop, task panel) keep their marker, so a deliberate per-agent stop is still final.

## Q4: named versus unnamed [verified in code]

- `agentNameRegistry` is created as `new Map` in AppState at startup and filled by `registerName` at spawn
  (`chunk-s6pn7fn6.js`) and at resume (`Qt`: `if (q!==void 0 && registry.get(q)===void 0) registerName(q, …)`).
  It is **not rebuilt from disk** after a restart, and `bdn` prunes it on `/clear`. After the restart, the name
  `identity-watch` was therefore unknown, which explains "No agent named 'identity-watch' is reachable". The
  resolver does not fall back to sidecar `name` fields. Once an agent is resumed by id, its name is
  registered again.
- The stop marker, the sweep and the resume guard never look at `name`.
- identity-watch's sidecar has no `teamName` and it ran as a `local_agent` background agent. The memory note
  about `in_process_teammate` (the 50-message cap, dropping messages when not running) concerns *agent-team
  teammates* and does not apply here.

## Q5: existing switches

- **`perTaskStopAffordance: true` (SDK `query()` option / initialize field) is the supported fix.** With it,
  an interrupt spares background agents: the agent keeps running and nothing is marked. T3's bundled SDK
  0.3.276 forwards the option (`app.asar`: `perTaskStopAffordance: this.initConfig?.perTaskStopAffordance`).
  T3's logged `query.open` options do not include it. **[inferred: T3 does not set it]** Enabling it is a T3
  change, and T3 would need a per-task Stop control so runaway agents can still be stopped.
- There is **no env var or setting** that bypasses the `stoppedByUser` guard. The only bypass is
  `userInitiated:true`, which TUI code (`chunk-scapxbwa.js`) sets when a human types into the agent's own
  view. That path is not reachable through SendMessage or T3. No `CLAUDE_CODE_*` variable appears in the
  resume chunk.
- **Zero-patch manual workaround:** delete `"stoppedByUser":true` from
  `~/.claude/projects/<proj>/<session>/subagents/agent-<id>.meta.json` while that agent is **not** in the
  current process's memory (that is, after a restart, as now), then SendMessage by **agentId**, not name.
  `Qt` would then pass both guards. **[needs runtime test]**

## Q6: patch proposal

### P1: stop the sweep from labelling tasks as user-stopped (recommended)

File (2.1.291): `chunk-t73sf08e.js`, function `dre`. The anchor occurs exactly once in the whole graph:

```text
before: if(ure(g.id,r,p),g.type==="local_agent")zx(g.id,r),Qgn(g.id);
after:  if(g.type==="local_agent")zx(g.id,r),Qgn(g.id);
```

Effect: system sweeps still kill background agents (fail-closed is preserved) and still emit
`Bi(...,"stopped")`. They no longer write `stoppedByUser` / `userStopCount` in memory or in the sidecar.
Explicit user stops are unchanged.

Side checks [verified in code]:

- `zht` (the queued-message gate) rejects non-running/non-completed tasks anyway, because swept tasks become
  `killed`.
- `hR` (budget) only examines running tasks.
- The `Qt` in-memory race guard compares `userStopCount`, which explicit stops still bump.

Semantic anchor for future ports:

1. Find the marker function: the unique `stoppedByUser:!0,userStopCount:(` update; it is followed by a sidecar
   persist call.
2. Find the sweep: the function that destructures `{taskRegistry,setAppState,shouldStop,storageV5}`, first
   kills observers, then loops over `Object.values(<registry>.all())`, calls `.kill(<id>,…,"system",…)` and
   emits `"stopped"`.
3. Inside that loop, remove only the marker call, which is comma-joined in front of
   `<g>.type==="local_agent"`.
4. Require old=1 / new=0 globally before patching and old=0 / new=1 afterwards, as the builder already does.

### P2: make the orphan notice honest (optional, cosmetic)

In `chunk-jdcpjj4f.js` `os`, when the sidecar has `stoppedByUser`, do not say "Resume it by sending it a
message". This removes the contradiction even without P1, but it gets no work back. P1 makes P2 unnecessary
for the interrupt case.

### Not recommended

Deleting the `Qt` sidecar guard. That would let the model override deliberate user stops too.

### What to test

1. **Stock reproduction:** run an SDK stream-json session without `perTaskStopAffordance`. Spawn a background
   agent running `sleep 600`. Send an `interrupt` control request. Expect the sidecar to show
   `stoppedByUser:true`; restart with `--resume`, SendMessage by id, and expect the refusal.
2. **Patched, same steps:** expect no marker, a successful resume, a single running task, and a transcript that
   continues after the interrupt marker.
3. **Explicit stop still final:** TaskStop (source user) and the TUI task-panel stop must still write the
   marker and still be refused.
4. **Race guard:** stop an agent explicitly while a resume is in flight; expect `OU` from the second guard.
5. **Budget halt:** `-p --max-budget-usd` still stops background agents.
6. **SDK rewind with `interrupt_if_running`:** agents after the cut are killed, not marked.
7. **T3 end to end:** `/compact`, cancel, then SendMessage by id. Also confirm name lookup works again once
   the agent has been resumed by id.
8. The usual bridge gates (renderer PTY, routing, Mods), because this adds a 15th replacement.

## Evidence files

- Graph: `chunk-ebe4qw6e.js` (Qt/Ce/Ezn, error classes), `chunk-t73sf08e.js` (ure/fn/dre/__e/FFe),
  `chunk-rysf7q6m.js` ($e interrupt handler, Bt, zl, mb, Sy), `chunk-96kd8z4r.js` (s7t),
  `chunk-0p8skvm3.js` (perTaskStopAffordance schema text), `chunk-jdcpjj4f.js` (os orphan notice),
  `chunk-dj0tea96.js` (resolver X/Z0t), `chunk-y93p1tmb.js` (SendMessage cases), `chunk-970cashr.js`
  ("Compaction canceled.").
- Sidecars: `~/.claude/projects/-Users-linyanyu/fb26bff9-5f17-4847-b1d7-e86dc4d93d8d/subagents/agent-ae2f1aca5722ed636.meta.json`
  (has the marker) and `agent-a0befcf0019102b20.meta.json` (no marker).
- T3: `~/.t3/userdata/logs/provider/events.9c7deb5c-e09c-49a3-8960-682c9d4fd5a3.log`, lines 2689–2698 and 3688.
