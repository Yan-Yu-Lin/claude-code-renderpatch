# Claude Code 2.1.291: resumable stopped background agents (host release .4)

Built and verified on 2026-10-08. This release adds one feature to the [2.1.291 host bridge](bridge-intent-2.1.291.md): **stop means pause**. Every stop path still kills a background agent, and the upstream `stoppedByUser` marker is still written. But an explicit SendMessage can always bring the agent back later, whatever stopped it. Background and root cause: [2026-10-07 research](2026-10-07-stopped-subagent-resume.md) (branch `research/stopped-subagent-resume`).

## Release

- Release directory: `~/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.4`
- Release ID: `2.1.291-host-darwin-arm64-74d61a9b`; build ID `host-2.1.291-darwin-arm64.4`
- Manifest SHA-256: `8c4cb4c1920f84cb9f585640e2c116430377cd9ddcf3eaf32009aaa3e840c4a8`
- Official executable: unchanged (`9a1d2ed6…6a056690`, team `Q6L2SF6YDW`).
- `baked_in=full-redraw,explicit-subagent-model-routing,resumable-stopped-agents`
- Build: `python3 tools/build-host-release-2.1.291-darwin.py --stock <official 2.1.291> --output <fresh dir> --revision 4`. Revision 1 still reproduces the `.1` recipe.
- Rollback: the untouched `2.1.291-host-darwin-arm64.1`.

`.2` was the first candidate. It passed every gate, but the second-model review found real issues, so it was never selected. `.3` was superseded before testing. Both stay on disk unchanged, as the workflow requires (immutable releases, never reused).

## Selection

After every gate passed and the review was clean, the live launcher was switched atomically on 2026-10-08 (sibling temp link + `os.replace`). The selected-path smoke passed status, version, safe version, the live Mod command, `plugin test` (1/0), and a real Sonnet `SELECTED_291R4_OK`; all exit 0. No running Claude or T3 process was touched; already-running sessions keep the old graph until they restart. Receipt: `~/.local/share/claude-renderpatch/selections/2026-10-08-2.1.291-host-resume.json`.

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.1/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback" && mv -h "$HOME/.local/bin/claude-bridge.rollback" "$HOME/.local/bin/claude-bridge"
```

## Behavior

| Stop path | Before (`.1`, stock) | After (`.4`) |
|---|---|---|
| SDK `stop_task` / TaskStop / TUI task panel | SendMessage refused: "stopped by the user and was not resumed" | resumes |
| SDK `interrupt` without `perTaskStopAffordance` (T3) | refused | resumes |
| Process exit after a stop, then `--resume` | by id refused ("won't be resumed"); by name "No agent named … is reachable" | by id and by name resume |
| Restart with no SendMessage | agent stays stopped | agent stays stopped (unchanged) |
| Orphan notice after restart | "may have been stopped … Resume it with SendMessage" (then refused) | "It was stopped … so it is paused … send it a message with SendMessage" (and it works) |

Nothing restarts a stopped agent on its own. The automatic wake paths still respect the marker: task-notification wakes, stranded retries, the 48 h orphan auto-resume, and observer deliveries. Upstream's own exceptions stay unchanged: a human typing into the agent's transcript view (`userInitiated`), and observer activity.

## Baked-in edits (on top of the 14 `.1` replacements)

| Site | 2.1.291 chunk · symbol | Edit |
|---|---|---|
| T1a sidecar refusal | `chunk-ebe4qw6e.js` · `Qt` | add `&&ce!=="reply"` to the sidecar `stoppedByUser` refusal |
| T1b in-memory refusal | `chunk-ebe4qw6e.js` · `Qt` | `(!M\|\|count changed)` → `(!M&&ce!=="reply"\|\|count changed)`: a stop that lands during the resume still wins |
| T1c marker clear | `chunk-ebe4qw6e.js` · `Qt` | run upstream's userInitiated clear block also for reply resumes of a stopped agent (same counter re-check and corrective re-write) |
| T2 resolver | `chunk-dj0tea96.js` · `X` | remove the `agent-stopped-by-user` early refusal; the agent resolves as `agent-stopped`, which goes to `Ezn` → `Qt` |
| T4 name after restart | `chunk-dj0tea96.js` · `Z0t` end | only when the whole resolver returns `not-found` for a bare name: `__rpSidecarName` scans this session's `subagents/*.meta.json` and resolves only if exactly one readable, non-observer sidecar has that name; any read error or duplicate keeps not-found |
| T4 import | `chunk-dj0tea96.js` | `import{F4n,R1r,M7n}` → `import{F4n,R1r,M7n,Kx}`; `YWe` is loaded with a dynamic import of `chunk-vvnkdfw1.js` (absolute graph path taken from the existing import) |
| T3a orphan probe | `chunk-jdcpjj4f.js` · `os` | one sidecar read per orphan; stopped **or unreadable** sidecars are excluded from the auto-resume list (fail closed) |
| T3b list exclusion | `chunk-jdcpjj4f.js` · `os` | `&&V&&H!==null&&R-H<es` → `…&&!rpS&&R-H<es` |
| T3c wording | `chunk-jdcpjj4f.js` · `os` | a known stop gets the paused/resumable note |
| T3d grouping | `chunk-jdcpjj4f.js` · `os` | a known-stopped orphan always gets its own notice (`N.redispatched\|\|rpK`), never the grouped generic text |

`ce` is `Qt`'s mode parameter. SendMessage enters through the export `resumeAgentForReply` = `Ce(e,"reply")`. The automatic paths use `"notification"` (`resumeAgentBackground`) or `"inline"` (observer). This makes "reply" the semantic gate. T1c is required: without it, a revived agent's own later task-notification wakes would be refused by the stale marker. The `wakeafter` gate proves the completion notification arrives.

All 23 replacements are exact, fail-closed and globally unique (old count 1, new count 0) through the existing `edit()` checker. Compared with `.1`, only these three chunks differ, after normalizing the release path.

## Rediscovery anchors for future ports

Do not reuse symbol names. Find each site by its meaning:

1. **Resume engine:** the function that throws a class named `AgentStoppedByUserError` with the text `was stopped by the user and won't be resumed`. It has two throw sites: one guarded by `<meta>?.stoppedByUser&&<origin>?.kind!=="observer-activity"`, the other by `<task>.stoppedByUser&&(!<userInitiated>||(<task>.userStopCount??0)!==<snapshot>)`. The mode is the function's second positional parameter, compared with `"inline"` and `"reply"` in the `let K=<mode>==="inline"||<mode>==="reply"&&…` background-rule line. The clear block starts with `if(<it>)try{if(<count>(<registry>.get(<id>))===<snapshot>){if(await <update>(…,{stoppedByUser:!1},…)`.
2. **Reply entry:** the module's export list maps `<x> as resumeAgentForReply` in its barrel chunk; that wrapper must pass `"reply"`.
3. **Resolver:** the function returning `{kind:"agent-stopped-by-user",agentName:…}` next to `agent-live` / `agent-stopped` / `agent-evicted`. The name fallback goes at the single `return <De>(…)??{...<U>(…),...}` tail of the async target resolver, the one that also handles `sendMessagePins`, cloud and bridge rows.
4. **Orphan scan:** the function that logs `background agent(s) orphaned by previous process exit` and builds `No completion record was found for it in the previous session`. Its per-agent probe returns `{mtimeMs,hasMeta,fetchable}`, and the 48 h constant is `172800000`.
5. **Sidecar helpers:** the reader is `async function <Kx>(e,n){return <read>(<metaPath>(e),n)}` beside `updateAgentMetadata`. The subagent lister reads `agent-*.jsonl` names from `<session>/subagents` (`.slice(6,-6)`).

## Verification (evidence: worktree `patched/verification-2.1.291-resume/`, ignored)

### Resume gates (`verify/resume-stopped-agents-2.1.291.py`)

These are real stream-json SDK sessions with no `perTaskStopAffordance`, which is T3 Code's shape. The parent spawns a background agent that is inside `sleep 900`. Proof comes from the child's own transcript (it contains the requested token), the sidecar, and the SendMessage tool result.

| Scenario | `.1` baseline | `.4` |
|---|---|---|
| taskstop: `stop_task` → SendMessage by id | refused (`agent-stopped-by-user`) | **pass**, child line 11, marker cleared |
| interrupt: `interrupt` → SendMessage by id | refused | **pass**, child line 12, marker cleared |
| restart: stop, exit, `--resume` → by id; stop, exit, `--resume` → by name | by id "won't be resumed"; by name "not reachable" | **pass**: "Resuming agent restartgate" by name |
| noauto: stop, exit, `--resume`, wait with no SendMessage | stays stopped | **pass**: child transcript 9→9 lines, no `task_started` |
| orphan: interrupt + immediate close (identity-watch timing) → restart | n/a | **pass**: idle 13→13, paused notice, resume works |
| wakeafter: revive, then let it finish | n/a | **pass**: completion task-notification reaches the parent |
| grouped: two agents stopped and closed together | n/a | **pass**: each got a truthful notice, no generic grouped text |

The grouped run delivered both in-session stop notices before exit, so the batched-orphan branch (`rs()` with 2+ known-stopped orphans) was covered by review, not at runtime.

### Existing gates (`verify/source-pty-2.1.291.py`, `verify/host-gates-2.1.291.py`)

| Gate | `.4` result |
|---|---|
| status / version / safe version | `verification=ok`; one version line; exit 0 |
| invalid flag, normal / safe | exit 1 / exit 1 |
| render, host | 5 phases, each ED2=1, ED3=1, first+last present, expanded-only detail only when expanded, no alt screen |
| render, safe | ED2=0, ED3=0, first absent (stock behavior) |
| 4 slots (`-p`) | fable `claude-f51[1m]` 1M, opus `claude-o55[1m]` 1M, sonnet `gpt-5.6-sol` 372K, haiku `gpt-5.6-luna` 372K; all exact markers, exit 0 |
| `/context` | 1m / 1m / 372k / 372k |
| routing (parent `claude-sonnet-4-6`, child alias `sonnet`) | candidate plain + named → `gpt-5.6-sol`; safe plain + named → `claude-sonnet-4-6` (child-own JSONL `message.model`) |
| official Mods | validate 0; test 1 pass / 0 fail; live `-p /renderpatch-hello` marker; interactive `/plugin` + command marker |
| model restore | saved `fable` → `/model gpt-5.6-sol` during session → `fable` after exit |
| Bash child env | no `BUN_OPTIONS`/`RP_HOST_ENTRY`/`CLAUDE_RENDERPATCH_*`; `CLAUDE_CODE_EXECPATH` = release `runtime/claude` |
| tamper (APFS clone, exact modes) | graph → `asset hash mismatch: graph/chunk-ebe4qw6e.js`; host → `asset hash mismatch: host.mjs`; extra → `unlisted asset`; ambient `BUN_OPTIONS` refused; safe scrubs it |

### Second-model review

The review was read-only, with `omp-sub --model gpt-6-astra` (session `01a11755-adbd-7333-adfa-c6c279d63795`).

**First pass, on `.2`:**

| Finding | Action |
|---|---|
| T4 could shadow a live or pinned session name, and treated duplicate matches as no match | moved T4 to a not-found-only fallback |
| T3 read the sidecar twice and failed open | changed to one read that fails closed |
| grouped orphan notices kept the generic wording | each known-stopped orphan gets its own notice |
| upstream `userInitiated` / observer exceptions | kept on purpose; both need a human action or an observer agent |
| marker clear happens before launch is fully committed | kept on purpose; this is upstream behavior and T1c needs it |

**Second pass, on `.4`:** no concrete defect in T3/T4. The reviewer noted that it could not prove from the supplied files alone that no action-free trigger reaches the retained upstream exceptions.

## Limits

- The marker clear is upstream's: it happens before the run is fully committed. A setup failure after the clear leaves the agent unmarked (no rollback), but it is still stopped.
- A model can now revive an agent that the user stopped on purpose. The orphan and stop notices say it may be resumed. This is the requested behavior.
- T4 reads every sidecar in the session's `subagents/` directory, but only when a bare name has already resolved to not-found.
