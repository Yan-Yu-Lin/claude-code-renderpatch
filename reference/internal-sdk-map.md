# Internal SDK map for Claude Code 2.1.220

This document is the human-readable companion to
[`manifests/internal-sdk-2.1.220.json`](../manifests/internal-sdk-2.1.220.json). It freezes the
internal SDK contract before any bridge bytes are designed or applied.

The contract is pinned to:

- Claude Code: **2.1.220**
- Platform: **macOS arm64**
- Stock SHA-256:
  `8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081`
- Stock size: **256,908,272 bytes**
- `__BUN`: file offset **64,831,488**, size **191,365,120**
- Legacy registry API: **1**
- Runtime API: **2**
- Synchronous policy API: **2**
- Bridge ABI baseline: **1**
- Bridge manifest schema: **1**
- Extension manifest schema: **1**
- Raw slot API: **2.1.220.1**
- Planned bridge build ID: **internal-sdk-2.1.220.1**

The physical layout is **planned**, not verified. Function names and offsets below were
observed in the exact stock binary and are diagnostic landmarks only. A patcher must still
rediscover each site semantically, prove uniqueness/equal length/non-overlap, and validate
exact stock fallback on a disposable candidate. This map does not claim final replacement
bytes.

## Architecture: two independent planes

The SDK has two planes:

1. **Control plane:** five compact synchronous policy queries for current renderer,
   context-window, and subagent-routing behavior.
2. **Raw asset plane:** six positional publication/capture domains used to build read tools,
   validated actions, and explicitly unsafe exact-version experiments outside the binary.

The distinction is fundamental:

> **Raw publication does not itself override lexical control flow.**

Publishing `SZc`, `Xrd`, a Messages array, an app store, or an Ink instance only makes that
asset inspectable or callable by trusted external code. Claude Code's existing private call
sites do not begin consulting an external result. A decision changes only where the binary
contains a separate Tier 4 policy query.

## Runtime rendezvous and query ABI

The canonical registry remains:

```text
Symbol.for("claude-code-renderpatch.runtime")
```

Registry API v1 remains compatible. Runtime API v2 adds a synchronous total query facade and
generation-aware capture replacement.

Bridge ABI 1 freezes the protected compact facade and both method names:

```text
globalThis.__rp.q(policyDomainId, fallback, ...primitivePayload)
globalThis.__rp.c(captureDomainId, generation, presenceBitmap, slotsOrNull)
```

`globalThis.__rp` is non-enumerable, non-writable, and non-configurable. It exposes exactly
`q` and `c`, not the whole registry. If the property already exists with an incompatible
value or ABI, the runtime does not replace it and disables the bridge facade safely. Policy
calls then use their stock fallback and capture calls become no-ops.

`q` is synchronous and total. It returns the **exact fallback argument** when:

- the facade/runtime is absent;
- the runtime, policy API, or capability ABI is incompatible;
- the policy-domain ID is unregistered;
- the handler throws;
- the handler returns a Promise or any thenable;
- the handler returns `undefined`;
- the return type or integer range is invalid; or
- an atomic renderer bundle is incomplete.

Valid `false` and `0` are real results and must never be mistaken for absence.

`c` publishes, replaces, or clears one positional raw capture and its return value is always
ignored:

- static captures use generation `0`;
- `presenceBitmap` is a non-negative integer whose bit N states whether positional slot N is
  present; omitted slots never renumber later indexes;
- a non-null `slotsOrNull` array plus its bitmap publishes or atomically replaces the capture
  at `generation`;
- `presenceBitmap === 0` with `slotsOrNull === null` clears only the matching current
  generation, so stale cleanup cannot delete a newer provider/render capture;
- null slots with a nonzero bitmap are invalid and become an ignored no-op;
- absent, incompatible, disabled, colliding, invalid, or throwing capture machinery is a
  literal no-op and stock behavior continues.

## IDs

### Eight semantic asset domains

| ID | Asset domain |
|---|---|
| `mc` | model and context system |
| `sr` | subagent routing |
| `msg` | Messages/transcript pipeline |
| `repl` | REPL controls and commands |
| `app` | app state and dialogs |
| `ink` | Ink/terminal renderer |
| `key` | keybindings, actions, and dispatch |
| `diag` | diagnostics and telemetry |

### Five policy-query domains

Numeric IDs are frozen for bridge byte size. Readable names stay in external manifests.
Every capability begins at ABI version 1.

| Numeric ID | Compact ID | Readable policy |
|---:|---|---|
| `0` | `o0` | `renderer.messages` |
| `1` | `o1` | `renderer.reset` |
| `2` | `o2` | `renderer.toggleRedraw` |
| `3` | `o3` | `provider.contextWindow` |
| `4` | `o4` | `subagent.explicitModelRouting` |

### Six raw capture domains

| Compact ID | Capture domain | Lifecycle |
|---|---|---|
| `d0` | static model/context/subagent helpers | static |
| `d1` | static Ink/terminal/dialog/diagnostics | static plus live lookup |
| `d2` | live app state | provider |
| `d3` | live Messages pipeline | render-latest |
| `d4` | live REPL controls/commands | render-latest |
| `d5` | live keybinding provider | provider |

Minified symbols such as `lzb`, `CXr`, or `Xrd` are exact-version observations. They never
become public capability IDs.

## The eight asset domains

### `mc`: model and context system

**Lifecycle:** static  
**Sensitivity:** policy/decision state  
**Risk:** medium

Known 2.1.220 assets include catalog/default lookup, alias canonicalization, allowlist checks,
provider/model normalization, effective/raw context windows, 1M capability helpers,
auto-compact decisions, and output-token limits.

Observed landmarks include:

| Symbol | Offset | Meaning |
|---|---:|---|
| `ww` | `225789193` | model catalog lookup |
| `Hl` | `227908447` | available-model check |
| `HH` | `227918015` | default/main-loop model resolver |
| `lo` | `227931600` | provider/model normalization |
| `Ei` | `227933508` | alias canonicalization |
| `JE` | `228834160` | effective context resolver |
| `SZc` | `228834423` | raw context-window resolver |

External features unlocked:

- model catalog and canonicalization inspector;
- provider, 1M, context, compact, and token-limit diagnostics;
- preview of stock/default decisions;
- provider-aware context policy through policy domain 3;
- exact-version raw helper experiments through `unsafe`.

Safe fallback is the entire stock model/provider/1M/environment/context path.

### `sr`: subagent routing

**Lifecycle:** static  
**Sensitivity:** model/provider/cost/privacy decisions  
**Risk:** high

Observed functions:

| Symbol | Offset | Meaning |
|---|---:|---|
| `ite` | `232657409` | core subagent resolver |
| `Qrd` | `232658032` | resolver plus diagnostics/telemetry |
| `Jrd` | `232658874` | explicit alias/1M adjustment |
| `Xrd` | `232658974` | same-family helper |

The exact explicit branch starts at `232657803`. The first shortcut clause
`if(Xrd(r,t))return t;` begins at `232657837`; the second default/frontmatter clause
`if(Xrd(u,t))return t;` at `232657956`.

External features unlocked:

- route previews and family mismatch diagnostics;
- regression tests for env, `inherit`, tool override, frontmatter/default, provider,
  allowlist, fallback, and 1M handling;
- a veto of only the first explicit same-family shortcut through policy domain 4;
- exact-version resolver calls under `unsafe`.

The second shortcut, real alias resolver, remapping, allowlist, fallback, telemetry, and 1M
logic stay stock.

### `msg`: Messages/transcript pipeline

**Lifecycle:** render-latest  
**Sensitivity:** conversation and tool content  
**Risk:** high

The core Messages function `lzb` begins at `241694130`. Its useful live stages are:

1. raw input messages `e`;
2. normalized/filtered messages `Ee`;
3. collapsed base `Ue`;
4. post-tool-stat array `at`;
5. final rendered slice `Ze`;
6. pre-normalization cap start `te`;
7. cap anchor refs `ce` and `se`;
8. truncation flag/count `ze`/`nt`;
9. virtual-scroll state `re` and cap rows `oe`;
10. screen/show-all/disable-cap/render-range values `l`/`u`/`H`/`L`.

Exact cap landmarks:

- `let te=!re&&!H?Xhf(e,ce,oe*2):0` at `241695167`;
- final `let He=!re&&!H?Xhf(at,se,oe):0` at `241696889`.

`He` exists only inside the final memo callback and is intentionally not a raw slot. External
diagnostics derive the final cap from `at`, `Ze`, `se`, and the exact-version helper.

External features unlocked:

- per-stage counts and cap/truncation diagnostics;
- bounded redacted raw-versus-rendered snapshots;
- transcript search/export;
- combined show-all/disable-cap policy through domain 0;
- exact-version arrays/refs under `unsafe`.

Tier 1 must never retain React-owned arrays or a previous render graph.

### `repl`: REPL live controls and commands

**Lifecycle:** render-latest  
**Sensitivity:** prompts, commands, tools, agents, and control state  
**Risk:** critical

The core component `Ahl` begins at `245816318`. Useful landmarks are:

| Offset | Landmark |
|---:|---|
| `245818985` | `[lr,It]` screen state/setter |
| `245819015` | `[fr,Ot]` show-all state/setter |
| `245819039` | `[Cr,yr]` disable-cap state/setter |
| `245834983` | `ug=nnp(...)` current view |
| `245865944` | `let rU=` submit callback |
| `245893878` | `let OGt={screen:` late compact control props |

External features unlocked:

- screen/transcript state inspection;
- command, tool, agent, and current-view catalogs;
- validated redraw, toggle, show-all, and whitelisted dispatch;
- an external controller or custom UI;
- prompt/slash/bash submission only under exact-version `unsafe`.

The smaller `Hui` toggle component does not contain the broad commands/tools/submit catalog
and cannot replace the `Ahl` capture.

### `app`: app state and dialogs

**Lifecycle:** provider  
**Sensitivity:** tasks, transcripts, configuration, dialogs, and permissions  
**Risk:** critical

Observed landmarks:

| Symbol | Offset | Meaning |
|---|---:|---|
| `Gae` | `238804272` | default app state |
| `dR` | `238807399` | `AppStateProvider` |
| `sM` | `242611887` | dialog store |

The provider-local store is `H1`; the REPL accesses the live store as `at` and setter as
`Le`.

External features unlocked:

- frozen metadata for tasks, transcripts, model state, notifications, overlays, MCP/plugins,
  and other selected safe slices;
- validated unregisterable subscriptions;
- diagnostic panels;
- raw store mutation and dialog operations only under `unsafe`.

The normal facade never answers, dismisses, or bypasses a user-facing decision. Test-only
reset methods are not part of the facade.

### `ink`: Ink and terminal renderer

**Lifecycle:** static registry/functions; current instance resolved on demand  
**Sensitivity:** frames, renderer state, and output control  
**Risk:** critical

Observed assets:

| Symbol/site | Offset | Meaning |
|---|---:|---|
| `xd=fa_` | `230930643` | stdout-to-Ink instance map assignment |
| `Oms` | `231132162` | destructive ED2 + ED3 + home sequence |
| `_Xr` | `231132222` | viewport-preserving main-screen erase |
| `Hms` | `231135081` | terminal patch serializer |
| clear switch | `231135291` | stock `altScreen ? Oms() : _Xr(...)` decision |
| `Rhs` | `231165676` | diff/log planner class |
| `CXr` | `231170016` | full-reset planner |
| row declaration | `231170042` | stock start-row calculation |
| `Qsr` | `231221157` | main Ink class |

External features unlocked:

- frame/viewport/reset diagnostics;
- validated redraw/invalidate/repaint actions;
- atomic authoritative reset policy through domain 1;
- live Ink instance, frames, planner, serializer, and terminal state only under `unsafe`.

Publish `xd`, not a startup snapshot of `xd.get(process.stdout)`: the current instance may be
absent, replaced, or unmounted.

### `key`: keybindings, actions, and dispatch

**Lifecycle:** provider  
**Sensitivity:** input ownership and action decisions  
**Risk:** critical

The provider `tQr` begins at `231293190`; its manager object `tp_={` at `231294286`.
Useful raw assets include bindings, handler registry ref, pre-dispatch ref, key-handler
registry, active contexts, pending chord/ref, and setter.

External features unlocked:

- binding/action/context catalogs;
- custom keybinding UI;
- provider-mediated registration;
- invocation of a small whitelisted action set;
- raw handler maps and refs only under `unsafe`.

Tier 2 never invokes raw handlers directly; provider mediation retains context, priority,
dialog, and input-ownership checks.

### `diag`: diagnostics and telemetry

**Lifecycle:** static  
**Sensitivity:** operational paths/state and possibly content-bearing payloads  
**Risk:** medium

Observed landmarks include `M`/`logEvent` at `225512906` and `w`/debug logging at
`225937669`, plus debug-path, flush, debug-mode, async event, analytics-state, and sink helpers.

External features unlocked:

- bridge/API/build/capability health;
- capture generation, lifecycle, and slot-presence diagnostics;
- redacted debug logging;
- raw telemetry only under exact-version `unsafe`.

Status and logs never include handlers, raw capture values, transcripts, stores, terminal
frames, command arguments, credentials, or payload history.

## Candidate integrity and one-shot launch metadata

A normal candidate launch transports exactly three one-shot metadata values:

```text
CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID
CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256
CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION
```

The candidate wrapper rejects normal launch if any of these names is already present in the
ambient environment. After that check, it hardcodes all three values from the selected signed
`RELEASE` metadata and the independently verified target artifact. Bootstrap captures the three
values before extension loading and immediately deletes all three names from `process.env`.
Status, `--renderpatch-safe`, and child-process paths scrub the names instead of forwarding them.

Signed candidate activation requires every one of the following:

- wrapper-supplied bridge build ID exactly equals the signed `RELEASE` bridge build ID;
- wrapper-supplied target version exactly equals the signed `RELEASE` target version and the
  actual executable target version;
- the independently computed SHA-256 of the actual executable target exactly equals the
  wrapper-supplied artifact SHA-256.

`stockSha256` and `artifactSha256` are different facts. `stockSha256` records the verified stock
source provenance. `requirements.target.artifactSha256` identifies the actual signed candidate
being executed and must independently match its computed SHA-256. An `unsafeRaw: true` manifest
must include both fields under `requirements.target`; stock provenance never substitutes for
artifact identity.

Stock-lab path/file-size compatibility exists only to exercise runtime and harness behavior. It
cannot activate a signed candidate or satisfy `unsafeRaw` artifact identity. This contract does
not freeze the temporary five-site artifact SHA-256: raw-capture work changes the final artifact,
so the release wrapper supplies the final verified value.

## Access Tier 0–4

These are interface layers, not a simple privilege ladder. Tier 4 is the narrow control
plane; Tier 3 is the dangerous raw plane.

### Tier 0: external runtime

Required infrastructure:

- trusted preload bootstrap;
- legacy registry API v1;
- synchronous policy/query API v2;
- exact-target bridge manifest;
- exact signed-`RELEASE` build ID, target version, and independently verified artifact SHA-256;
- absolute trusted extension selection;
- immediate `BUN_OPTIONS` and one-shot bridge-metadata cleanup;
- status, safe-mode, and child-environment scrubbing;
- safe launcher for the exact same target.

### Tier 1: read facade

Only cloned, frozen, bounded, and redacted snapshots or metadata:

- model/context/route previews;
- message-stage counts and optional redacted snapshots;
- task/transcript/model/notification metadata;
- Ink dimensions/reset state;
- command/keybinding catalogs;
- bridge versions, capability ABIs, lifecycle, generation, and slot-presence bitmap/count.

No live mutable object is returned.

### Tier 2: validated actions

Narrow actions with schema, allowlist, and liveness/generation checks:

- redraw/invalidate/repaint;
- transcript toggle/show-all;
- safe subscriptions;
- whitelisted command/action dispatch;
- bounded transcript search/export.

Stale actions perform no mutation, dispatch, submission, dialog operation, or terminal write.

### Tier 3: `unsafe`

Raw helpers, stores, setters, arrays, refs, Ink instances, submit callbacks, dialog controls,
and handler maps exist only when an explicit trusted manifest requests:

```text
unsafeRaw: true
```

and exactly matches:

- `requirements.target.version` against the verified target version;
- `requirements.target.stockSha256` against the separate stock provenance SHA or approved
  signature-independent stock `__BUN` hash;
- `requirements.target.artifactSha256` against the independently computed SHA-256 of the actual
  verified executable target;
- `requirements.target.bridgeBuildId` against the signed `RELEASE` bridge build ID;
- bridge ABI and capture-domain ABI;
- raw slot API.

Failure omits `unsafe`; it does not return an empty permissive proxy. Unsafe access is
same-process/local only and never network exposed.

### Tier 4: override hooks

Five synchronous primitive-only queries alter specific lexical decisions. Raw publication is
not a substitute for these hooks.

## Five stable policy contracts

### Domain 0: `renderer.messages`

```text
globalThis.__rp.q(0, 0, screen)
```

- Payload: `screen: string`
- Fallback/result: integer bitmask `0..3`
- Bit 0: force effective show-all true
- Bit 1: force effective disable-render-cap true for both caps
- Initial policy: `2 | (screen === "transcript" ? 1 : 0)`

The result is additive: unset bits preserve stock local values. The planned supplier is early
inside `lzb`, after virtual-scroll state exists but before transcript truncation and both cap
starts. The transcript JSX prop call remains stock.

### Domain 1: `renderer.reset`

```text
globalThis.__rp.q(1, false, reason, altScreen)
```

- Payload: `reason: string | null`, `altScreen: boolean`
- Fallback/result: boolean `destructiveRowZeroReplay`

One validated result must atomically drive both `startY=0` and the emitted clear patch's
destructive intent. The stock `Hms` serializer remains unchanged only if the disposable
prototype proves that `CXr` can carry the intent without partial destructive state.

If this cannot be proven, add one explicit sixth clear-mode query after proof or reject the
five-site prototype. Never enable destructive clear without row-zero replay.

### Domain 2: `renderer.toggleRedraw`

```text
globalThis.__rp.q(2, false, enteringTranscript)
```

- Payload: `enteringTranscript: boolean`
- Fallback/result: boolean authorization
- Binary-owned helper: `oFS`
- Binary-owned delay: **50 ms**

The external policy does not receive callbacks or choose a timer. The binary preserves the
private redraw helper, state setters, scheduling, and telemetry.

The `Hui` component begins at `243071716`; `oFS` at `243071663`; the 153-byte telemetry/state
block starts at `243072602`.

### Domain 3: `provider.contextWindow`

```text
globalThis.__rp.q(3, stockWindow, canonicalModel)
```

- Payload: canonical model string
- Fallback: exact precomputed stock context-window result
- Result: validated positive safe integer
- Initial policy:
  - `kimi*` -> `262144`
  - `claude-*` -> fallback
  - other non-Claude -> `372000`

The final supplier must be a wide-enough `SZc` contextual replacement that computes and
passes the exact stock result. A narrower canonical-model-only call that loses the stock
environment fallback does not satisfy this contract.

### Domain 4: `subagent.explicitModelRouting`

```text
globalThis.__rp.q(4, Xrd(requestedModel, parentModel), requestedModel, parentModel)
```

- Payload: requested model and concrete parent model strings
- Fallback/result: boolean `retainSameFamilyShortcut`
- Initial policy: `false` for the explicit branch

Only the first explicit `Xrd(r,t)` gate is a supplier. The second default/frontmatter call,
environment precedence, `inherit`, `Jrd(Ei(r))`, provider remapping, allowlist, fallback, and
telemetry remain stock.

## Feature activation

Recommended external extension IDs:

- `full-redraw`
- `mix-window`
- `subagent-routing`
- aggregate `default`

`mix-window` and `subagent-routing` negotiate independently.

`full-redraw` is atomic and requires all of:

- `renderer.messages@1`
- `renderer.reset@1`
- `renderer.toggleRedraw@1`

If any capability is absent or incompatible, none of the three renderer handlers becomes
active.

Extension registration is transactional: validate schema/identity, policy API, every bridge
ABI, handler synchrony/return contract, duplicate numeric/readable ownership, and atomic
bundle completeness before publishing any handler.

## Six raw capture domains and slot order

The JSON manifest is authoritative. Slots are positional and never silently renumbered within
a bridge build. Optional omission uses a presence bitmap; it does not shift later indexes.

### `d0`: static model/context/subagent helpers

Lifecycle: static generation 0. Preferred supplier: at/after the `Ydt` initializer following
`Xrd`; one site preferred, two allowed if a single entry-scope payload does not fit safely.

Slot order:

0. `HH` default model resolver
1. `Ei` alias canonicalizer
2. `Hl` allowlist check
3. `lo` provider/model normalizer
4. `n_` provider resolver
5. `ww` model catalog lookup
6. `JE` effective context window
7. `SZc` raw context window
8. `Wb` 1M suffix test
9. `OH` native-1M eligibility
10. `tG` 1M beta support
11. `bZc` disable-compact override
12. `gYi` auto-compact decision
13. `fro` cached auto-compact window
14. `cst` output-token limits
15. `ite` raw subagent resolver
16. `Qrd` resolver/diagnostic wrapper
17. `Jrd` explicit alias/1M adjuster
18. `Xrd` same-family helper
19. `tO_` default requested model
20. `Cur` family classifier
21. `rO_` disallowed-model warning

### `d1`: static Ink/terminal/dialog/diagnostics

Lifecycle: static generation 0, with slot 0 used as a live lookup registry. Preferred Ink
supplier: after `T3u`/`Ju_` initialization. Dialog and diagnostic statics may be folded into
that publication or use a second small static supplier if needed.

Slot order:

0. `xd` stdout-to-Ink instance map
1. `Qsr` Ink class
2. `Rhs` diff planner class
3. `CXr` full-reset planner
4. `vUu` frame-slice renderer
5. `khs` diff/cursor builder
6. `Hms` terminal serializer
7. `Oms` destructive clear sequence
8. `_Xr` viewport-preserving erase
9. `S3u` async Ink constructor
10. `Ju_` instance getter
11. `Kpe` render entry
12. `QHt` lower render entry
13. `sM` dialog store
14. optional `Krl` legacy-dialog focus store
15. `w` debug logger
16. `gqe` debug flush
17. `SMe` debug log path
18. `R7` debug-mode test
19. `N5` debug-to-stderr test
20. `M` telemetry event
21. `lb` async telemetry event
22. `PAl` analytics-state factory
23. `SEi` telemetry sink attachment

The current Ink instance is resolved from `xd` on demand. Tier 1 does not retain it.

### `d2`: provider app state

Lifecycle: provider. Preferred broad supplier: inside `dR` after `H1` creation. For REPL-only
availability, `d4` can supply the same store through `at`/`Le`; add `d2` as a separate physical
site only when early or non-REPL availability matters.

Slot order:

0. live app store (`H1` or REPL `at`)
1. dialog store `sM`
2. `getState`
3. `setState`/REPL setter `Le`
4. `subscribe`
5. default-state factory `Gae`

### `d3`: latest Messages pipeline

Lifecycle: render-latest. Supplier: immediately after `Ze` assignment inside `lzb`.

Slot order:

0. raw messages `e`
1. normalized messages `Ee`
2. collapsed base `Ue`
3. post-tool-stat messages `at`
4. final rendered messages `Ze`
5. pre-normalization cap start `te`
6. first cap anchor ref `ce`
7. final cap anchor ref `se`
8. truncation flag `ze`
9. hidden message count `nt`
10. virtual-scroll-active `re`
11. effective cap rows `oe`
12. screen `l`
13. show-all `u`
14. disable-cap `H`
15. render range `L`

The policy-domain-0 query is earlier and this capture is later. They share `lzb`, but must not
be forced into one mega-replacement if that increases semantic blast radius.

### `d4`: latest REPL controls

Lifecycle: render-latest. Supplier: near `OGt` in core `Ahl`, after all declared values exist.

Slot order:

0. app store `at`
1. app setter `Le`
2. current view `ug`
3. screen `lr`
4. screen setter `It`
5. show-all `fr`
6. show-all setter `Ot`
7. disable-cap state `Cr`
8. disable-cap setter `yr`
9. commands `Dn`
10. submit callback `rU`
11. active tools `_o`
12. agent definitions `ee`
13. scroll ref `Py`
14. jump/search ref `Gr`
15. compact toggle props `OGt`

### `d5`: keybinding provider

Lifecycle: provider. Supplier: inside `tQr` immediately after `tp_` is assembled and before it
is passed to `dgo.Provider`.

Slot order:

0. manager `tp_`
1. bindings `lut`
2. handler registry ref `i9u`
3. pre-dispatch ref `Ggs`
4. key-handler registry `s9u`
5. active contexts `r9u`
6. pending chord ref `Z4u`
7. pending-chord setter `t9u`
8. pending chord `e9u`

Publish live refs, not copied registries; React effects continue populating them after render.

## Planned physical site count

Five policy queries plus six raw domains produce eleven conceptual suppliers before
co-location. The expected production candidate remains approximately **8–10 unique bridge
sites**.

This is a planned maintenance target, not a verified count. Likely reductions are:

- `d2` supplied by the `d4` REPL site when early/non-REPL app access is unnecessary;
- `d0` sharing a model/routing neighborhood only after scope and byte-fit proof;
- `d1` sharing reset/Ink neighborhoods only if raw publication does not expand terminal risk;
- `d3` and policy domain 0 sharing `lzb`, while still permitting distinct early/late edits.

Policy domain 2 in `Hui` cannot replace the broad `d4` capture in `Ahl`.

The planned five policy-query sites are:

1. early `lzb` combined Messages query;
2. `CXr` combined reset query;
3. `Hui` Ctrl+O redraw authorization;
4. wide-enough `SZc` tail;
5. first explicit `Xrd` gate in `ite`.

A sixth policy site is permitted only after proof when either Messages must split into
show-all plus shared-cap queries or terminal clear mode must be separated to preserve atomic
reset pairing. If destructive clear can partially enable without row-zero replay, the
prototype is no-go rather than a reason to ship uncontrolled extra policy patches.

Do not force a theoretical mega-payload merely to lower the site count.

## Lifecycle and staleness

### Static

- generation 0;
- publish once after dependencies initialize;
- identical recapture is a no-op;
- conflicting replacement is rejected.

### Provider

- monotonically increasing generation;
- atomic replacement on mount/recreation;
- cleanup token removes only its own generation;
- stale actions fail closed.

### Render-latest

- strictly increasing generation on every render;
- replace rather than append;
- release the previous arrays, refs, closures, and React graphs immediately;
- unmount cleanup is generation-safe.

### Lookup-live

Publish a stable map/registry and resolve the current instance when needed. Do not retain a
startup instance in Tier 1.

There is at most one current capture per `d0`–`d5`. A stale action returns unavailable and
performs no side effect.

## Security constraints

1. **Primitive policy ABI only.** No callback, React setter, Ink instance, renderer object,
   resolver function, or raw graph crosses `q`.
2. **No eval or arbitrary dispatch.** The short facade exposes only known operations.
3. **Trust absolute paths, not the working directory.** Extension entries are explicit,
   user-owned regular files under the user's home, with parent-symlink and group/world-write
   checks.
4. **Never autoload project code.** Do not scan `$PWD`, `.claude`, package metadata, or
   relative module names.
5. **Clean startup state.** Delete `BUN_OPTIONS` immediately, scrub child preload state, reject
   ambient normal-mode `BUN_OPTIONS`, and keep exact-target `--renderpatch-safe`. The candidate
   wrapper also rejects ambient bridge build/artifact/version metadata, hardcodes verified values
   only for normal launch, and scrubs them from status, safe-mode, and child paths; bootstrap
   captures and immediately deletes those three one-shot names.
6. **Read means copies.** Tier 1 never leaks live arrays, stores, refs, setters, handlers,
   terminal objects, or submit callbacks.
7. **Actions are narrow.** Tier 2 validates arguments, current generation, liveness, and
   command/action allowlists.
8. **Unsafe is exact and explicit.** `unsafeRaw: true` plus exact target/build/ABI/slot match
   is mandatory. `requirements.target` carries separate `stockSha256` provenance and
   `artifactSha256` identity; the latter must match the actual verified executable. Failure omits
   `unsafe`.
9. **Never network-expose raw handles.** Same-process trusted code already has substantial
   authority; a network facade would create remote permission-bypass or code-execution
   primitives.
10. **Protect decisions.** Normal facades never answer dialogs, bypass permissions, skip
    input ownership, or invoke raw handlers directly.
11. **Protect content.** Messages, prompts, commands, tools, tasks, paths, terminal frames,
    and telemetry payloads are sensitive and redacted by default.
12. **Metadata-only status.** Status contains versions, lifecycle, generation, slot presence,
    and health—not raw values, payload history, handlers, credentials, or content-bearing
    paths.
13. **Transactional registration.** Schema/API/ABI mismatch, duplicate ID/alias ownership, or
    incomplete atomic bundles reject the whole extension registration.
14. **Stock-safe failure.** Patched-without-preload, bootstrap-only, partial/incompatible,
    throwing/thenable/invalid policy, and safe mode all retain stock behavior and produce zero
    renderpatch ED3.

The broad raw plane enables experimentation. The five small policy queries remain the only
planned mechanism for changing private lexical decisions.
