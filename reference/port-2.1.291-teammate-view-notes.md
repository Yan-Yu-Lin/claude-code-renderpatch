# Claude Code 2.1.291 teammate transcript view

## Scope and provenance

2026-10-08 investigation and patch in branch `feature/host-2.1.291-teammate-view`, fresh worktree `.claude/worktrees/bridge-2.1.291-teammate-view`, based on `41a9cb25fdfc59d1b53381bb698e7fd09bbde7cf` (`feature/host-2.1.291-darwin-resume`). Read [resume intent](bridge-intent-2.1.291-resume.md) and [port notes](port-2.1.291-notes.md) first.

Source under investigation is the immutable `.4` graph at `~/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.4/graph`. Its manifest SHA-256 is `8c4cb4c1920f84cb9f585640e2c116430377cd9ddcf3eaf32009aaa3e840c4a8`. `.4` and `~/.local/bin/claude-bridge` must remain untouched. Candidate target is `.5`; selection is Arthur's decision, not part of this change.

Arthur observed a truncated finished `mod-survey` view despite a complete JSONL and complete `$.session.messages({ agentId })` result. These are accepted observations, not a reason to inspect or rerun his private session. The source investigation independently establishes the affected paths. [Upstream issue #98550](https://github.com/anthropics/claude-code/issues/98550) describes the same three causes in 2.1.280; current 2.1.291 source, not the older issue's symbol names, determines the recipe.

## Confirmed source sites

### Bounded teammate cache

`chunk-9ag6ybmh.js`, `uJn` / `GBe` / `e6o`:

```js
var uJn=50;function GBe(e,n){if(e===void 0||e.length===0)return[n];if(e.length>=uJn){let r=e.slice(-(uJn-1));return r.push(n),r}return[...e,n]}function e6o(e,n){let r=e===void 0||e.every((s)=>s.uuid!==n.uuid)?e:e.filter((s)=>s.uuid!==n.uuid);return GBe(r,n)}
```

The cache holds messages, not tool calls: one tool use plus its result consumes at least two slots. `e6o` replaces an existing UUID before appending through the same cap. Raising this cap alone cannot recover already-discarded history.

### Append, resume seed, and completion

`chunk-m5sckpqa.js`: live appends and user messages use the same bounded helper. The status checks are separate from display retention:

```js
function d2n(e,r,s){if(s.get(e)?.status!=="running")return;s.updateTranscript(e,(a)=>({...a,messages:GBe(a.messages,r)}))}
function pHt(e,r,s,a){let n=s.get(e);if(!n||js(n.status)){t(`Dropping message for teammate task ${e}: task status is "${n?.status}"`);return}s.update(e,(m)=>({...m,pendingUserMessages:[...m.pendingUserMessages,{text:r,origin:a}]})),s.updateTranscript(e,(m)=>({...m,messages:GBe(m.messages,Re({content:r,origin:a}))}))}
```

`chunk-zg4dkp5j.js`, in-process runner `Qe`: these are exact excerpts (separate statements/sites):

```js
l.updateTranscript(s,(I)=>{let Q=I.messages;if(u)for(let be of u.slice(-uJn))Q=GBe(Q,be);return{...I,messages:GBe(Q,Re({content:Ee}))}});
return{...k,messages:e6o(k.messages,r),inProgressToolUseIDs:U}
l.updateTranscript(s,(w)=>({...w,messages:GBe(w.messages,r)}))
```

The first seeds a resumed teammate from only the last 50 rows; the second is streamed messages (UUID replacement), the third an interruption notice. Success and failure respectively do this after setting task status to `completed` / `failed`:

```js
l.updateTranscript(s,(I)=>({...I,messages:I.messages.length?[I.messages.at(-1)]:[],inProgressToolUseIDs:new Set}));
l.updateTranscript(s,(x)=>({...x,messages:x.messages.length?[x.messages.at(-1)]:[],inProgressToolUseIDs:new Set}));
```

Both then call `wp(s),l.evictTerminal(s)`. This explains why the finished view can have much less than 50 rows. A normal turn first becomes `isIdle:true`; actual terminal completion/failure is a distinct transition. The idle task update sets `evictAfter:ie?void 0:Date.now()+Yx` even while viewed, so retention must cover that deadline too.

The remaining intentional replacement of the runner's display list is explicit compaction, also in `Qe`:

```js
q.length=0,q.push(...ue),Ne.clear(),l.updateTranscript(s,(k)=>({...k,messages:[...ue,Q]}))
```

This context-compaction transition is not the 50-row view cache. Its semantics remain upstream's, like the plain-agent reader's active-lineage handling; the patch does not reconstruct unrelated historical branches or undo compaction.

### Plain-only hydration and selected rows

`chunk-scapxbwa.js`, `kMe`: exact `.4` loader:

```js
function kMe({store:h,setAppState:C,storageV5:M}){return $H([h],()=>{let{viewingAgentTaskId:N,tasks:Q}=h.getState(),he=N?Q[N]:void 0,be=Pn(he)&&he.retain&&!he.diskLoaded;return[N,be]},(N,Q)=>{if(!N||!Q)return;let he=N;ese(yo(he),M).then((be)=>{C((Pe)=>{let Oe=Pe.tasks[he];if(!Pn(Oe)||Oe.diskLoaded||!Oe.retain)return Pe;let Ne=Pe.transcripts[he],He=Ne?.messages??[],Ge=new Set(He.map((Ye)=>Ye.uuid)),je=be?be.messages.filter((Ye)=>!Ge.has(Ye.uuid)):[];return oPe(je),{...Pe,tasks:{...Pe.tasks,[he]:{...Oe,diskLoaded:!0}},transcripts:{...Pe.transcripts,[he]:{inProgressToolUseIDs:new Set,...Ne,messages:[...je,...He]}}}})}).catch(c)})}
```

`Pn` accepts only `local_agent`. `Du` (enter) uses `if(Pe)Ne[h]=uZ(N)?{...N,retain:!0,evictAfter:void 0}:{...N,evictAfter:void 0}`: only plain agents get `retain`. `fZ` (leave) returns early for teammates with `if(h.type==="in_process_teammate")return{...h,evictAfter:h.isIdle?Date.now()+$Me:void 0};`, so they never get plain agents' `diskLoaded:false` reset either.

The existing `ese` reader is in `chunk-v1gtm86q.js`: `async function ese(e,n,r){let s=await MRn(e,n);if(s.transcript)return s.transcript;...}`. `MRn` uses `Ug(e)` to locate the agent JSONL, `zPe` to read storage, and selects that agent's sidechain/active lineage. It also handles the existing storage backend and on-demand remote hydration. `oPe(e)` is exactly `H2().degradeRestored(e)`; reused for restored disk-only rows. No new file parser or path convention is introduced.

**Three identities, not one:** `chunk-qrbwjj3h.js`, `uRr`, creates `r=RN(s,g),f=fE("in_process_teammate"),c=e.resumableAgentId??nh(s)`, stores `S={agentId:r,...,resumableAgentId:c}`, and registers `{...Rm(f,"in_process_teammate",...),identity:S,...}`. `f` is the TUI task key; `c` is the persisted agent ID. `Qe` passes `...e.resumableAgentId&&{agentId:e.resumableAgentId}` to the engine. Therefore the teammate loader must read **`task.identity.resumableAgentId`**, never its TUI task ID or display/team identity. The plain loader still reads its task ID. A type-check-only patch would read the wrong file and silently mark a null load complete.

The selected-view chain is `fp` → `o7` → `f6o`; the latter returns `messages:n.messages` directly (`chunk-9ag6ybmh.js`). No second 50-row slice exists there. Renderer folding can still group Read calls; an expanded PTY capture is needed to count individual rendered tool rows.

## Patch and rediscovery

Recipe: [`tools/host_patches_2_1_291_teammate_view.py`](../tools/host_patches_2_1_291_teammate_view.py). Its `HYDRATE_BEFORE` / `HYDRATE_AFTER` and replacement tuples are the complete exact before/after patch. All replacements pass the existing global old-count=1/new-count=0 checker.

| Semantic anchor | Before | After |
|---|---|---|
| View enter/leave | Only local agents set/reset retention | Both supported task types set `retain:true` on enter, clear `retain` and `diskLoaded` on leave |
| Retained-view disk loader | `Pn` plain-only eligibility | `pZ` accepts both; same `ese` and storage backend; teammate source is `identity.resumableAgentId`; generation, selected-id, source-id and start-time guards reject stale results |
| Teammate disk/live merge | No disk merge | Disk order and live versions win; shared UUIDs anchor cache-only rows; native timestamps interleave a persisted suffix with later live-only notices |
| Plain disk/live merge | Disk-only prefix + current live rows | Unchanged |
| `GBe` / `e6o` | Always cap at 50 | Optional retained-view argument bypasses cap; all teammate append callers pass the current task's `retain` |
| Resume seed | Last 50 rows | Full UUID-deduplicated seed while retained; bounded seed otherwise |
| Idle deadline | Set even while viewed | No idle eviction deadline while retained |
| Terminal cleanup | Collapse to last row | Preserve retained rows; invalidate `diskLoaded` on success/failure to refresh final disk rows |
| Stop/eviction | `Son` clears `evictAfter`; teammate exit only considers idle | Off-view kills get the existing `Ght` deadline; view exit also sets a deadline for terminal status |

Reopening a view resets the load lifecycle, so any off-view cache trimming is repaired from disk. No model context or JSONL persistence is enlarged. Off-view caches retain their 50-row limit. Existing terminal status/message-delivery guards remain: this patch does not revive a finished task or reinterpret new mailbox deliveries. Upstream task retirement and active-lineage/compaction semantics remain; this is a transcript-view fix, not permanent retention of every historical branch or deleted task.

**Accounting correction:** `.4`'s actual manifest and a fresh replay of its recipe both contain **25** replacements, not the 23 stated in the earlier notes. Normalizing only the graph directory, that replay exactly matches every `.4` JavaScript module. The new logical patch adds 16 replacements across five chunks (41 total). The edit counter now accumulates multiple edit batches for a shared chunk, so the existing Ctrl+O replacement in `chunk-scapxbwa.js` is not overwritten in the count.

Pre-build checks: exact recipe application; duplicate-anchor, missing-chunk and already-patched refusal; parse of five changed chunks; throwaway retained-history exercise covering the off-view cap, 100 retained rows, UUID replacement, concurrent append during hydration, stale reopen reads, task-vs-agent identity, cache-only prompt placement, and interruption/terminal suffix ordering. These checks do not substitute for the real PTY gate.

Read-only source review caught the wrong identity, terminal eviction leak, and cache-only prompt ordering before `.5` was sealed. The latter is real: the display seed `Re({content:Ee})` and persisted `Re({content:X})` have different UUIDs. Content-based deduplication would risk dropping intentional repeated prompts, so the merge preserves both identities and their order. The stop leak arose because `chunk-9ag6ybmh.js` `dn`/`cn` protect any task with a `retain` property and `(evictAfter??Infinity)>now`, even `retain:false`; `chunk-qm1h7fwt.js` `Son` formerly wrote `paneTeardown:void 0,evictAfter:void 0`. The replacement uses `evictAfter:e.retain?void 0:Date.now()+Ght`, and `fZ` expires idle **or terminal** teammates.

## Evidence location

Generated gate evidence belongs under this worktree's ignored `patched/verification-2.1.291-teammate-view/`, not Desktop. `initial-provenance.json` records the `.4` manifest, live launcher target and settings-overlay digest before any work. Final source sites, patch rationale and exercised results are recorded below as they are established.

## Release and verification

- Release: `~/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.5`.
- Release ID: `2.1.291-host-darwin-arm64-74d6f960`; build ID `host-2.1.291-darwin-arm64.5`.
- Manifest SHA-256: `f5f2a45510b7319727ffce363298f3e36e70e9537651daae711e04189b5e3595`.
- Official executable unchanged: SHA-256 `9a1d2ed6bb4421e8fc80c892c0413f293be3ee50ae3d7dda1a7622197a056690`, signature team `Q6L2SF6YDW`.
- Build command: `python3 tools/build-host-release-2.1.291-darwin.py --stock <official 2.1.291> --output <fresh release directory> --revision 5`.

Completed `.5` receipts under the evidence directory:

| Existing gate | Observed result | Receipt |
|---|---|---|
| Status/version/safe version | `verification=ok`; exactly one version line; exit 0 | `basic/summary.json` |
| Invalid flag, normal/safe | Both exit 1 | `basic/summary.json` |
| Four live model slots | Exact markers; Fable/Opus 1M, Sonnet/Haiku 372K | `basic/summary.json` |
| `/context` four slots | 1m / 1m / 372k / 372k | `host/context-summary.json` |
| Renderer | Five toggle/resize phases: ED2=1, ED3=1, first+last rows present; expanded-only detail toggles correctly; no alternate screen | `render-host/summary.json` |
| Safe renderer | ED2=0, ED3=0; first row absent after expansion; no alternate screen | `render-safe/summary.json` |
| Plain + named explicit model override | Candidate child JSONLs: `gpt-5.6-sol`; safe: `claude-sonnet-4-6`; all exit 0 | `host/routing-summary.json` |
| Official Mods | validate 0; 1 pass/0 fail; live command and `/plugin` UI pass | `host/mods-summary.json` |
| Bash child environment | No preload/host-variable leak; helper executable is `.5/runtime/claude` | `host/bash-child-env.json` |
| Tamper and ambient preload | Graph/host/extra assets refused; ambient preload refused; safe mode scrubs it | `host/tamper-summary.json` |
| Four requested resume gates | `taskstop`, `interrupt`, `restart` by id/name, `noauto`: all pass | `resume/summary.json` |
| Remaining existing resume gates | `orphan`, `grouped`, `wakeafter`: all pass | `resume/summary.json` |
| Model restoration | `opus` before → `gpt-5.6-sol` during → `opus` after; exit 0 | `host/model-restore-summary.json` |

The gate runners use `caffeinate -i` only for their lifetime. A preview control wait auto-backgrounded after a long gap; that run was not counted as completed verification. Earlier preview/harness failures are kept in separate directories, not mixed with the final release receipts.

### New real-PTY teammate gate

[`verify/teammate-view-2.1.291.py`](../verify/teammate-view-2.1.291.py) spawns a named `general-purpose` teammate, first with 30 sequential real Read calls and a held Bash call. It opens the **actual `/tasks` picker**, selects the row and presses **`f`**, then **Ctrl+O**. Enter on these running rows opens the detail panel, not the retained transcript. Later it selects the leader through `/tasks` to leave the view; Escape would interrupt the teammate and is not used for navigation.

Final `.5` receipt: `teammate-final/summary.json` (**pass**, gate process exit 0). Each row count below comes from the last full repaint, not accumulated ANSI redraws. Exact required Read/Bash markers must occur in real tool rows; actual Agent prompts are checked to exclude echoed Read markers.

| Checkpoint | Child tool calls | Rendered tool headers | Rendered transcript rows | Missing required markers |
|---|---:|---:|---:|---:|
| First open after 64 persisted user/assistant rows | 31 | 31 | 66 | 0 |
| Eight more Reads + second Bash while continuously viewed | 40 | 40 | 85 | 0 |
| Return from the plain-agent view | 40 | 40 | 84 | 0 |
| Finish **off-view**, observe `: idle`, reopen | 40 | 40 | 82 | 0 |
| Plain background agent, no `name`/`team_name` | 5 | 5 | 14 | 0 |

The finished reopened view also contains the completed final Bash result and the final assistant reply. The gate permits additional genuine tool calls, such as a teammate sending its completion to the lead, rather than assuming the requested 40 calls are an exact total. The probe's owned launcher was terminated by its cleanup fallback after all captures (`launcherExit=-15`); this is not a claimed normal-exit check. Normal CLI/TUI exits are separately covered by the existing gates.

Reproduce from this worktree (fresh output directory):

```bash
caffeinate -i python3 verify/teammate-view-2.1.291.py --launcher "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.5/claude-renderpatch-candidate" --output patched/verification-teammate-view-rerun --cwd "$HOME" --system-prompt "Follow the user's tool-call protocol exactly. This is an isolated rendering gate. Use only the requested Agent invocations; do not inspect the machine or ask for confirmations."
```

Consolidated receipt: `release-verification.json`. All seven existing resume scenarios passed, including the four explicitly requested. Existing gate implementations are unchanged; their JSON `pass` fields were checked, not merely their process exit codes.

### Cleanup and unchanged selection

Disposable preview releases, generated Mod copy, Python caches, throwaway smoke drivers, compile-input copies, and abandoned owned probe fixtures were removed after verification. JSON/ANSI receipts remain under the ignored evidence directory. `final-provenance.json` confirms the `.4` manifest SHA-256, settings-overlay digest and live `claude-bridge` target exactly match their initial values. No active installation path was moved, and no Desktop artifact was created.

## Selection remains manual

After acceptance, select `.5` atomically (not executed by this task):

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.5/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.select-2.1.291.5" && mv -h "$HOME/.local/bin/claude-bridge.select-2.1.291.5" "$HOME/.local/bin/claude-bridge"
```

Rollback to untouched `.4`:

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.4/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback-2.1.291.4" && mv -h "$HOME/.local/bin/claude-bridge.rollback-2.1.291.4" "$HOME/.local/bin/claude-bridge"
```

Both affect newly launched processes only; an already-running `.4` session continues using its existing graph.
