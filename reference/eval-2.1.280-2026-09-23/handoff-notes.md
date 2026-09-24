# claude-bridge renderpatch: is the patch set still needed on stock Claude Code 2.1.280?

Handoff for a second reviewer who has not seen the original conversation.
Author: evaluation-only subagent, 2026-09-23. All work was static analysis plus `--version` runs.
Nothing under `~/.claude`, `~/.local` or the renderpatch repo was modified. All downloads are under `/tmp/cc-2.1.280/`.

## 0. Background (read first)

Arthur runs a custom Claude Code build called `claude-bridge`.

- Mac: 2.1.261 source-graph release at `~/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4/`. `~/.local/bin/claude-bridge` resolves to `.../claude-renderpatch-candidate` in that directory.
- omarchy Linux: 2.1.246.
- Upstream today: npm `latest` = 2.1.280, `stable` = 2.1.267.

Since 2.1.245, Claude Code ships as a Bun ESM chunk graph inside the native binary. The builder does four things:

1. Extracts the graph.
2. Applies exact-string, fail-closed edits (every anchor must occur exactly once).
3. Runs the result under an external Bun.
4. Adds a trusted preload and extensions that answer policy queries `__rpQ261(id, fallback, ...)`.

The recipe lives in the renderpatch repo worktree `.claude/worktrees/bridge-2.1.261/tools/`:

- `source_patches_2_1_261.py`: all anchors and replacements.
- `build-source-release-2.1.261-darwin.py`: the builder.
- `extract-source-darwin.py`: graph extraction.

Human-readable intent is in `reference/bridge-intent-2.1.261.md`.

The three logical patches:

1. **full-redraw / inline rendering.** Disables the fullscreen, virtual and DECSTBM paths. Removes the message caps so Ctrl+O shows everything. Emits an authoritative ED2+ED3 redraw on expand, collapse and resize.
2. **Provider-aware context window.** The policy in `extensions/_shared.mjs` `providerContextWindow`:
   - `kimi*` → 262144
   - `claude-*` → native handling
   - anything else → 372000
3. **Subagent explicit-model routing fix.** An explicit `model:` is ignored when the parent's concrete id contains another alias family keyword (opus/sonnet/haiku/fable).

There is also a one-line **Bash-helper fix**: the Bash tool's `CLAUDE_CODE_EXECPATH` must point at native stock `claude`, not bare Bun.

Current overlay `~/.claude/claude-mix-settings.json` (read-only check):

| Setting | Value |
|---|---|
| `ANTHROPIC_BASE_URL` | `http://127.0.0.1:8317` (CLIProxyAPI) |
| `ANTHROPIC_DEFAULT_FABLE_MODEL` | `claude-f51[1m]` |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `claude-o55[1m]` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `gpt-5.6-sol` |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `gpt-5.6-luna` |

- At first read there was no `modelOverrides`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS` or `DISABLE_COMPACT`. **Later during this task, `CLAUDE_CODE_MAX_CONTEXT_TOKENS="372000"` was added (see §1 corrections).** Still no `modelOverrides` or `DISABLE_COMPACT`.
- `~/.claude/settings.json` has `model = fable`.
- `claude-f51` and `claude-o55` are proxy aliases for `claude-fable-5-1` and `claude-opus-5-5`. They exist only because 2.1.261's display table lacked those models.

**Important reading tip:** minified identifiers are chunk-local. The same name (e.g. `Tf`, `aC`, `pT`) means different functions in different chunks. Always resolve through that chunk's `import{...}from"./chunk-xxx.js"` (see `resolve.py`).

---

## 1. The report sent to team-lead (verbatim)

> Report: stock 2.1.280 still needs the render patch, but the context-window patch can be replaced by one env var and the subagent-routing patch is optional.
>
> # Is the claude-bridge patch set still needed on 2.1.280?
>
> ## Bottom line
> - **Patch 1 (full-redraw / inline rendering): still needed.** Upstream shipped nothing that replaces it. The code it patches still exists with the same logic, but under new names and in different chunks. None of the 22 exact anchors in the current builder match, so this needs a real re-port.
> - **Patch 2 (provider-aware context window): replaceable by a setting.** This isn't an upstream fix. It works because Kimi was dropped from the slots today, so every non-Claude slot now wants the same 372000. Stock `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000` in the overlay's `env` gives that.
> - **Patch 3 (subagent explicit-model routing): upstream bug NOT fixed**, but the current slot names can't trigger it. It is defense in depth, and porting it is a one-line change.
> - **Recommendation: partial.** Stay on 2.1.261 until someone budgets a re-port. When porting, carry only patch 1 (plus the Bash-helper fix), switch patch 2 to the env var, and make patch 3 optional. Target 2.1.280, not `stable` 2.1.267 (see new-features section).
>
> ## How I checked
> - Downloaded `@anthropic-ai/claude-code-darwin-arm64@2.1.280` with `npm pack --ignore-scripts` into `/tmp/cc-2.1.280/native/`. Binary SHA-256 `387a5c5dcdbb815085edf0baf79591f9d8894efe922bceaf3d75b1b08055229d`, `--version` = `2.1.280 (Claude Code)`.
> - Extracted the graph with a copy of the repo's `extract-source-darwin.py` with the SHA pin removed (`/tmp/cc-2.1.280/extract.py`) → `/tmp/cc-2.1.280/graph/`. It has **2213 records** (2.1.261 had 1837).
> - There is no changelog in the npm tarball or the graph. I got CHANGELOG.md from `anthropics/claude-code` with `gh`: `/tmp/cc-2.1.280/CHANGELOG.md`. I read 2.1.263 through 2.1.280 in full.
> - Anchor check script: `/tmp/cc-2.1.280/anchor_check.py`. Helpers: `ctx.py`, `resolve.py` (the second follows chunk-local import aliases).
> - Nothing was installed, patched or changed, and I made no network requests to Anthropic.
>
> ## Patch 1 — full-redraw / inline rendering
> **Exact anchors:** 0 of 22 match. The one "hit", `function iee(){`, is a false positive: it lands in an unrelated function in chunk-ft3bhzm2.
>
> **The semantic sites all still exist in the same shape, just renamed:**
>
> | 2.1.261 site | 2.1.280 equivalent |
> |---|---|
> | fullscreen selector `Ta(e=KI)` (chunk-w7y6dfep) | `Va(e=CF)` in chunk-2p1kp6xr, same body (`SESSION_KIND==="bg"`, `NO_FLICKER`, tmux -CC …) |
> | inline/fullscreen latch `oO()` | `jH()` / `Se()` in chunk-cdkwzv6s |
> | DECSTBM selector `iee()` | `Rie()` in chunk-qbx8et3j (still behind `tengu_marlin_porch`) |
> | reset `Za(t,s,c,f,m,y){let b=f?0:` | `kr(n,s,u,f,m,p){let S=f?0:` in chunk-qbx8et3j, same `clearTerminal` object |
> | serializer `l.altScreen?JUn():Lat(...)` | `case"clearTerminal":i+=d.altScreen?WMr():hNt(d.viewportRows)` in chunk-7rn4mcxd (now a switch-case) |
> | message list `L7e` flags `ZM` / `$x` / `_he` | `ph()` in chunk-57gge8cv: `Q=v==="uncapped"\|\|me!==void 0`, `Re=Z!=null&&!we`, `Uo=J&&!U&&!Re` |
> | REPL `m5e` with memo `_(596)`, `JZe=$w?"uncapped":M_?"all"` | chunk-ad1vsmtp `let ri=Je?"uncapped":jt?"all":void 0`. **The memo-cache slot indices changed, so the wrapper edits must be re-derived. This is the riskiest part.** |
> | Bash helper `D[HJe]=process.execPath` | `j[w_e]=process.execPath` in chunk-dt8bvbsd |
>
> **Upstream alternatives: none.**
> - `CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN` and `CLAUDE_CODE_NO_FLICKER=0` (see `s()` in chunk-2p1kp6xr) only keep inline mode, which is already the default for Arthur.
> - The transcript Ctrl+E "show all" and `[` "dump to scrollback" already existed in 2.1.261.
> - In 2.1.263–2.1.280, the rendering changelog items are all fullscreen fixes plus generic speedups (2.1.271 "long transcripts render faster"). None fixes inline expand, collapse or resize.
>
> **Re-port effort:** similar to the 2.1.246→2.1.261 port. Extra infrastructure work:
> - New stock SHA, file size (217254576) and module count.
> - **The embedded Bun is v1.4.3 (`f08e57bec`), which is not published.** npm `@oven/bun-darwin-aarch64` latest is 1.4.2, and there's no GitHub 1.4.3 release. The builder pins Bun 1.4.1. `bun-1.4.1 graph/cli --version` on the 2.1.280 graph printed `2.1.280 (Claude Code)`, but nothing beyond `--version` was tested.
>
> ## Patch 2 — provider-aware context window
> **Anchor:** the raw resolver `QL` is now `Mg()` in chunk-m200zvyg, same shape. `Tf()` wraps it and adds a `DISABLE_COMPACT` override (`Pg()`):
> ```
> Mg(e,n){if(au(e))return 1e6; … let r=Qyr(e); … if(jh(e))return 1e6; … let g=a.CLAUDE_CODE_MAX_CONTEXT_TOKENS;if(g!==void 0&&g>0&&xg(e))return g;return L0e /*200000*/}
> ```
> - The new per-model catalog lookup `Bi()` reads the served catalog `Ui()`. That only applies when `ja()` is true, meaning first-party with a real Anthropic base URL, so it is null behind the proxy.
> - Gateway `/v1/models` discovery (`F0e`) only supplies picker id, label and description. It carries no window.
> - The new `autoCompactWindow` setting and `CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `aC()` (chunk-dt8bvbsd) are clamped with `Math.min(g, …)`, so they can only lower the window, never raise it.
>
> **Why the env var now works:** the current slots are fable=`claude-f51[1m]`, opus=`claude-o55[1m]`, sonnet=`gpt-5.6-sol`, haiku=`gpt-5.6-luna`.
> - `xg()` is true for gpt-* ids, so they get the env value (372000).
> - `claude-f51` / `claude-o55` start with `claude-` and aren't in the catalog, so `xg` is false for them. Their `[1m]` suffix hits the `au()` 1M path first anyway.
> - Bonus: the new unknown-model notice `Sc()` returns null when this env var is set and `xg` is true, so the `[claude-code:unrecognized_model]` nag for Sol/Luna goes away.
>
> **Caveats:**
> - The value is global. If Kimi (262144) or any model with a different ceiling comes back, you need the patch again.
> - Don't set `DISABLE_COMPACT`: `Pg()` would then apply the value to every model, including Claude.
> - **Don't use `modelOverrides` to make gpt ids look like Claude ids.** It gains no window, and the canonical id (e.g. `claude-sonnet-5`) would contain a family keyword and re-arm the routing bug.
> - Needs a live `/context` check (sonnet/haiku should show 372k).
>
> ## Patch 3 — subagent explicit-model routing
> **Anchor intact, renamed:** in `tO()` (chunk-wyjryvm7), `if(n==="inherit")return y();if(Egn(n,r))return r;` — same as 2.1.261's `cH`/`ojt`. The helper still does the substring short-circuit:
> ```
> function Egn(e,r){let n=e.toLowerCase();if(!pT(n))return!1;let s=Kt(r);if(Ry(s)&&!pT(s))return!1;let g=ze(r);if(g.includes(n))return!0;return n==="opus"&&Dxt()&&!c_r()&&La(r,g)}
> ```
> - **Not fixed upstream.** The 2.1.274 changelog entry ("subagents with `model: "opus"` on Bedrock/Vertex/Foundry…") added the extra `opus` clause. It only applies when the provider isn't first-party. Arthur's proxy is classified first-party: `Oe()` returns "gateway" only with gateway auth.
> - 2.1.254's `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` doesn't help: it overrides every per-spawn model.
> - **Existing gap in 2.1.261:** there is a second call site in the named-teammate spawn resolver: `re()` / `H(n,e,o="tool")` in chunk-m6y5r0f2 (`if(e!==null&&Egn(n,e))return e`). It was in chunk-xddhe4q4 in 2.1.261, and **it was never patched**. Named teammates with an explicit model are still exposed on the current bridge.
> - **Current exposure: none.** No slot id contains another family's keyword. The bug fires only when a parent runs a raw id containing family X while slot X points elsewhere.
>
> ## Opus 5.5 in the 2.1.280 built-in model table
> - The baked-in catalog in chunk-x29j4pyb has `{id:"claude-opus-5-5",family:"opus",display_name:"Opus 5.5",…context:{window:1e6,native_1m:!0,supports_1m_beta:!0,supports_1m_suffix:!0},default_effort:"medium",fallback_3p:"claude-opus-5"}`. The changelog confirms it: "Added Claude Opus 5.5 … now the default Opus model". `claude-fable-5-1` is also in the table as "Fable 5.1".
> - **So on 2.1.280 both display-name aliases (`claude-o55`, `claude-f51`) become unnecessary.** Using `claude-opus-5-5[1m]` / `claude-fable-5-1[1m]` in their own slots is collision-safe, because each contains only its own family keyword.
> - Keep the `[1m]` suffix. Behind the proxy, `jh()` is false because `ms()` fails with a custom `ANTHROPIC_BASE_URL`, so native 1M isn't detected without it.
> - Using the real ids would also activate model-specific behaviour, such as Opus 5.5's `default_effort:"medium"` and its prompt bundle.
> - `min_claude_code_version`: the only served-catalog entries (chunk-daa108e6) are `claude-fable-5-1` at 2.1.251. opus-5-5 has no entry in the bundled served catalog. The server-side 2.1.280 gate lives in the API and is already handled by the proxy's `claude-cli/2.1.280` user agent.
>
> ## New upstream items (2.1.261→2.1.280) that matter here
> - **2.1.268:** "Fixed every turn failing with HTTP 400 on third-party Anthropic-compatible endpoints (`ANTHROPIC_BASE_URL`) since 2.1.265". **npm `stable` 2.1.267 has this bug, so skip it.**
> - **2.1.276:** "Fixed every request failing with `400 … Input tag 'advisor_20260301'` when `ANTHROPIC_BASE_URL` points at a proxy" (a 2.1.275 regression). **2.1.280** also retries without the advisor tag behind gateways.
> - **2.1.268:** task tools (TaskCreate / TodoWrite) are now offered only on older Claude models. **Fable 5.1, Opus 5/5.5 and all GPT slots lose them unless you set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`.** Worth adding to the overlay if you upgrade.
> - **2.1.271:** "Fixed `--resume` dropping the 1M context window (`[1m]`) when the resumed session's model family differs from the configured default". This is relevant to the mixed slots.
> - **2.1.269 / 2.1.273:** `CLAUDE_CODE_GATEWAY_MODEL_DISCOVERY_TIMEOUT_MS`; opt-in gateway hint headers (`CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`).
> - **2.1.273:** fixed the context meter and auto-compact counting advisor turns at about double their size.
> - **2.1.267:** per-model `modelSettings` with `effortLevel` / `maxEffortLevel` (no context-window field).
> - **2.1.280:** saved effort no longer applies to newly released models such as Opus 5.5.
> - **2.1.277:** subagent results now arrive under a header marking them as subagent output; AGENTS.md fallback.
> - **2.1.278:** auto mode on gateways defaults to the server-side classifier.
> - **2.1.277:** TaskOutput tool removed; `taskOutputMaxChars` no longer has any effect.
> - **`modelPicker` / `modelOverrides`** (from 2.1.247/2.1.261) are only cosmetic or for recognition. They don't affect the context window.
>
> ## Verdict
> | Patch | Still needed? | Re-port effort | Upstream alternative |
> |---|---|---|---|
> | 1 full-redraw / inline | **Yes** | **Drifted**: 0/22 exact anchors, every semantic site present and renamed; REPL memo indices must be re-derived. Bun 1.4.3 is unpublished (1.4.1 passes `--version` only) | None |
> | 2 context window | **No** (for the current Kimi-free slots) | Anchor intact (`Mg` in chunk-m200zvyg), but no port needed | `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000` in the overlay `env`, verified with `/context` |
> | 3 subagent routing | Bug still there; not needed for current slot names | **Intact**, 1 line (`tO`/`Egn`). Consider also patching the teammate site in chunk-m6y5r0f2 | Slot-naming rule, which 2.1.280's real Opus 5.5 / Fable 5.1 ids also satisfy |
> | Bash-helper execPath fix | Yes for any extracted build | Intact (`j[w_e]=process.execPath`, chunk-dt8bvbsd) | None |
>
> **My recommendation:** the upgrade is a medium-effort port of the renderer only, not the full cumulative re-port.
>
> **Can be done on 2.1.261 now:** put `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000` in the overlay. That lets the next port drop the mix-window policy.
>
> **On the port to 2.1.280:**
> - Carry only patch 1 and the Bash-helper line. Optionally add patch 3, covering both call sites.
> - Also set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` and switch the display aliases back to the real ids with `[1m]`.
> - Consider skipping the six-domain capture layer: the installed `default.mjs` extension registers only the q-policies. I'm inferring that from the extension files; I didn't audit every consumer of the capture layer.
>
> **Uncertainty:**
> - I didn't run the 2.1.280 graph beyond `--version`.
> - The Bun version choice and the renderer's behaviour at the new sites still need PTY verification.
> - The env-var replacement for patch 2 is from static reading and needs a live `/context` check.
>
> All files are under `/tmp/cc-2.1.280/` (packages, `graph/`, `CHANGELOG.md`, `anchor_check.py`, `ctx.py`, `resolve.py`).

### Corrections and additions found after the report was sent

- **Overlay state changed during this task.** When I first read `~/.claude/claude-mix-settings.json`, it had no `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. It now contains `"CLAUDE_CODE_MAX_CONTEXT_TOKENS": "372000"`, plus `CLAUDE_CODE_ALWAYS_ENABLE_EFFORT=1`, `CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK=1` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. Someone (presumably the main agent or Arthur) applied the recommendation. It is still running on the **2.1.261** bridge, where the provider patch also sets 372000 for gpt-*, so the two agree. The Background section above describes the earlier state.
  - On 2.1.261 the env var takes effect only if the patched `QL` falls through to it. The patch wraps `QL` and then applies the provider table, and the table returns 372000 for gpt-* regardless. So on 2.1.261 the env var is redundant, not conflicting.
  - 2.1.261's own gate is `XL(e)` in chunk-7s5z3cw5, the same logic as 2.1.280's `xg`.
- **N-API modules shrank from 5 to 3.** 2.1.280 ships `audio-capture.node`, `computer-use-input.node` and `computer-use-swift.node`. 2.1.261 also had `image-processor.node` and `url-handler.node`. This matches the 2.1.265 changelog ("image processing … uses the runtime's built-in image support"). The builder's asset and contract lists need updating.
- The teammate-site claim is now confirmed against the live release file with hashes. See §5b.

---

## 2. How to reproduce / verify

All paths are absolute. Everything is under `/tmp/cc-2.1.280/` unless noted.

| Artifact | What it is |
|---|---|
| `native/anthropic-ai-claude-code-darwin-arm64-2.1.280.tgz`, `native/package/claude` | Stock native binary. SHA-256 `387a5c5dcdbb815085edf0baf79591f9d8894efe922bceaf3d75b1b08055229d`, size 217254576 |
| `main/anthropic-ai-claude-code-2.1.280.tgz`, `main/package/` | npm wrapper package (cli-wrapper.cjs, install.cjs, sdk-tools.d.ts). No CHANGELOG |
| `graph/` | Extracted Bun module graph, 2213 records. `graph/cli` is the entry. `graph/extraction.json` lists each record's name, loader and entry flag. Absolute `/$bunfs/root/...` imports are rewritten to `/private/tmp/cc-2.1.280/graph/...` |
| `CHANGELOG.md` | Upstream changelog (7274 lines). The 2.1.280 section starts at line 3; 2.1.261 at line 919 |
| `extract.py` | Copy of the repo's `tools/extract-source-darwin.py` with the stock-SHA check changed to `if False:`. Parses Mach-O → `__BUN` → Bun module table, writes every record, rewrites import paths |
| `anchor_check.py` | Parses `source_patches_2_1_261.py` with `ast`, pulls every `(chunk, old_anchor)` pair from the `edit(...)` calls, and counts each anchor across all `graph/*.js`. A hit anywhere is reported, not just in the same-named chunk |
| `ctx.py` | `ctx.py GRAPH PATTERN [before] [after] [maxhits]`. Python regex context search over `GRAPH/*.js`. Needed because macOS BSD grep rejects `{0,N}` with N>255 |
| `resolve.py` | `resolve.py GRAPH CHUNK NAME [after]`. Finds `function NAME(` or `NAME=` in CHUNK. If NAME is absent, follows that chunk's `import{... as NAME}from"./chunk-X.js"` to the defining chunk and prints the definition |
| `native.log` | npm pack log |

Reference (read-only) live release graph: `~/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4/graph/`. It is the patched 2.1.261, so its anchors are already replaced by `__rpQ261(...)` calls. Its `release-manifest.json` lists `semanticEdits` and per-asset SHA-256.

Exact commands used:

```bash
# fetch (no install; nothing global touched)
mkdir -p /tmp/cc-2.1.280/native /tmp/cc-2.1.280/main
cd /tmp/cc-2.1.280/native && npm pack --ignore-scripts @anthropic-ai/claude-code-darwin-arm64@2.1.280 && tar xzf *.tgz
cd /tmp/cc-2.1.280/main   && npm pack --ignore-scripts @anthropic-ai/claude-code@2.1.280 && tar xzf *.tgz
npm view @anthropic-ai/claude-code dist-tags          # { stable: '2.1.267', latest: '2.1.280', next: '2.1.280' }
shasum -a 256 /tmp/cc-2.1.280/native/package/claude
/tmp/cc-2.1.280/native/package/claude --version       # 2.1.280 (Claude Code)

# changelog
gh api repos/anthropics/claude-code/contents/CHANGELOG.md -H "Accept: application/vnd.github.raw" > /tmp/cc-2.1.280/CHANGELOG.md

# extract graph (output dir must not exist)
cd /tmp/cc-2.1.280 && uv run extract.py --stock native/package/claude --output /tmp/cc-2.1.280/graph

# anchor survival check: prints one line per 2.1.261 anchor with the number of files containing it
cd /tmp/cc-2.1.280 && uv run anchor_check.py /tmp/cc-2.1.280/graph

# examples of the searches behind the rename table
uv run ctx.py graph '==="inherit"\)return' 700 400 5              # subagent resolver tO()
uv run ctx.py graph 'function Egn\(' 50 700 2                     # family helper
uv run resolve.py graph chunk-dt8bvbsd.js Tf 1800                 # -> Tf/Mg in chunk-m200zvyg
uv run ctx.py graph 'type:"clearTerminal",reason:' 400 200 3      # reset kr()
uv run ctx.py graph '\.altScreen\?' 200 200 3                     # serializer
uv run ctx.py graph '==="uncapped"\|\|' 900 700 2                 # ph() message list
uv run ctx.py graph '\]=process\.execPath' 250 150 3              # Bash helper
uv run ctx.py graph 'if\(a\.CLAUDE_CODE_SESSION_KIND==="bg"\)return!0;' 250 450 2   # Va()
uv run ctx.py graph 'decstbmRendererEnabled!==void 0\)return' 250 450 2           # Rie()
uv run ctx.py graph 'i\("tengu_toggle_transcript"' 150 250 2      # toggle site
# same searches against the live release: replace "graph" with the release graph path

# Bun version embedded in stock binary
strings -n 6 /tmp/cc-2.1.280/native/package/claude | /usr/bin/grep -m5 -E "bun-v1\.4|1\.4\.3"   # v1.4.3 (f08e57bec)
npm view @oven/bun-darwin-aarch64 dist-tags            # latest 1.4.2
gh api repos/oven-sh/bun/releases --jq '.[0:4][] | .tag_name'   # newest bun-v1.4.2

# 2.1.280 graph under the release's Bun 1.4.1 (only test run)
~/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4/runtime/bun /tmp/cc-2.1.280/graph/cli --version
# -> 2.1.280 (Claude Code), exit 0
```

Note: `grep` is a shadowed shell function on this Mac, so use `/usr/bin/grep` in pipes. There is no `timeout` binary.

---

## 3. Rename table, 2.1.261 → 2.1.280 (chunk filenames on both sides)

2.1.261 chunks are in the live release graph. 2.1.280 chunks are in `/tmp/cc-2.1.280/graph/`. The "2.1.261 anchor" column is the exact `old` string from `source_patches_2_1_261.py`.

### Patch 1: full-redraw / inline rendering

| Role | 2.1.261 chunk · symbol · anchor | 2.1.280 chunk · symbol · shape |
|---|---|---|
| Fullscreen decision | `chunk-w7y6dfep.js` · `Ta(e=KI)` · `function Ta(e=KI){` | `chunk-2p1kp6xr.js` · `Va(e=CF)` · `function Va(e=CF){if(id()==="local-agent")return!1;if(a.CLAUDE_CODE_SESSION_KIND==="bg")return!0;…` (same body) |
| Opt-out helper (reference only) | same chunk, `s()` | `chunk-2p1kp6xr.js` · `s(){return a.CLAUDE_CODE_NO_FLICKER===!1\|\|a.CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN}` |
| Inline/fullscreen latch | `chunk-9wy4tdk8.js` · `oO()` · `function oO(){let r=De(de);` | `chunk-cdkwzv6s.js` · `jH()` · `function jH(){let o=Me(re);if(o===null)return Se();…o.latched=Se()…}`, `Se(){return Va()?"fullscreen":"inline"}` |
| DECSTBM decision | `chunk-q5rezcap.js` · `iee()` · `function iee(){` | `chunk-qbx8et3j.js` · `Rie()` · `function Rie(){{let n=fs();if(n.decstbmRendererEnabled!==void 0)…x("tengu_marlin_porch",!1)…}` |
| Full reset (row-zero replay + destructive flag) | `chunk-q5rezcap.js` · `Za` · `function Za(t,s,c,f,m,y){let b=f?0:` and `type:"clearTerminal",reason:s,altScreen:f,viewportRows:t.viewport.height,debug:y` | `chunk-qbx8et3j.js` · `kr` · `function kr(n,s,u,f,m,p){let S=f?0:Math.min(m,…)…return[{type:"clearTerminal",reason:s,altScreen:f,viewportRows:n.viewport.height,debug:p},...C.diff]}` |
| Clear serializer (ED2/ED3) | `chunk-rvxxpz38.js` · `i+=l.altScreen?JUn():Lat(l.viewportRows);` | `chunk-7rn4mcxd.js` · `case"clearTerminal":i+=d.altScreen?WMr():hNt(d.viewportRows);break;`. `WMr(){return PS+Kot+bh}` is the full-clear sequence; `hNt(r)` is the per-row erase |
| Message list caps / virtualization | `chunk-5vxbh0wn.js` · `L7e(ein)`, memo `_(199)` · `ZM=iQt==="uncapped"\|\|Ok!==void 0,` / `$x=hhe!=null&&!ain,` / `_he=om&&!yhe&&!$x,` / `return nYt}function d7(w)` | `chunk-57gge8cv.js` · `ph(o)`, memo `w(229)` · `Q=v==="uncapped"\|\|me!==void 0` / `Re=Z!=null&&!we` (`we=a.CLAUDE_CODE_DISABLE_VIRTUAL_SCROLL`) / `Uo=J&&!U&&!Re`. Return/cleanup-injection site not yet located |
| Toggle (Ctrl+O) + forced redraw | `chunk-5vxbh0wn.js` · `x0` · `X7e()},lA[6]=nZe`; redraw fn `F5t(){ws().get(process.stdout)?.forceRedraw()}` | `chunk-ad1vsmtp.js` · `px(h)` memo `w(22)` · `…i("tengu_toggle_transcript",{…}),D()},Ie[6]=Pe,…`; redraw fn `sot(){_s().get(process.stdout)?.forceRedraw()}` |
| REPL show-all wrapper | `chunk-5vxbh0wn.js` · `m5e(Bwi)` memo `_(596)` · anchors `function m5e(Bwi){let ls=_(596),`, `[rcn,icn]=d(!1),M_=rcn\|\|$w,`, `ls[472]`, `ls[483]/ls[484]`, `let zYe=HVo;if(fm==="transcript")`, `return j4}let DV=`, `return WVo}\nexport{`, dump expr `JZe=$w?"uncapped":M_?"all":void 0` | `chunk-ad1vsmtp.js` · REPL component · `let ri=Je?"uncapped":jt?"all":void 0`. All memo indices and local names changed; not re-derived |
| Key-manager capture (d5; ABI only) | `chunk-3nf3qbb9.js` · `return I}function sl(){` | Not located. `sl` in 2.1.280 is unrelated (e.g. chunk-qbx8et3j `sl(){return iC.of(G().host)}`). Only needed if the capture ABI is kept |
| Static renderer capture (d1; ABI only) | `chunk-9wy4tdk8.js` exports `[S9e, ws().get, Y0, he]`; `chunk-q5rezcap.js` `[Xye,Yd,Za,ng,Kd]`; `chunk-rvxxpz38.js` `[Dtn,JUn,Lat]` | Not mapped. Only needed if the capture ABI is kept |

### Patch 2: context window

| Role | 2.1.261 chunk · symbol · anchor | 2.1.280 chunk · symbol |
|---|---|---|
| Raw window resolver | `chunk-7s5z3cw5.js` · `QL(e,t)` · anchor `function QL(e,t){` (wrapped by `__rpRawWindow261`) | `chunk-m200zvyg.js` · `Mg(e,n)`; outer `Tf(e,n){let r=Pg();if(r!==void 0)return r;if(Zyr(e,n))return YW;return Mg(e,n)}` |
| Env gate "non-Claude id" | `chunk-7s5z3cw5.js` · `XL(e)` | `chunk-m200zvyg.js` · `xg(e)` (same logic) |
| Default window constant | `qme` (200000) | `L0e=200000`, `YW=200000` |
| Auto-compact window | (older logic) | `chunk-dt8bvbsd.js` · `aC(e,n,r=gf())`, sources `env\|settings\|clientdata\|experiment\|model-default\|unknown-model\|auto` |
| Unknown-model notice | — | `chunk-bjmhhyed.js` · `Sc(o,u,p)` (wrapped by `oa`) |
| Served catalog gate | — | `chunk-x29j4pyb.js` · `ja(){return Oe()==="firstParty"&&ms()}`; `ms()` → `hb()` → true only with no or first-party `ANTHROPIC_BASE_URL` |

### Patch 3: subagent routing

| Role | 2.1.261 chunk · symbol · anchor | 2.1.280 chunk · symbol |
|---|---|---|
| Agent-tool subagent resolver (**patched** site) | `chunk-3963bmck.js` · `cH(e,t,r,o,d)` · `if(r==="inherit")return p();if(ojt(r,t))return t;` | `chunk-wyjryvm7.js` · `tO(e,r,n,s,g)` · `if(n==="inherit")return y();if(Egn(n,r))return r;` |
| Frontmatter call (leave unpatched) | same fn · `if(ojt(e,t))return t;` | same fn · `if(Egn(e,r))return r;` |
| Family helper | `chunk-3963bmck.js` · `ojt(e,t)` (switch of `includes`) | `chunk-wyjryvm7.js` · `Egn(e,r)` (`g=ze(r);if(g.includes(n))return!0;` plus a non-first-party opus clause) |
| Named-teammate resolver (**unpatched** in live release) | `chunk-xddhe4q4.js` · `re(t,e)` · `if(e!==null&&ojt(t,e))return e;` (imports `ojt` from chunk-3963bmck) | `chunk-m6y5r0f2.js` · `re(n,e)` · `if(e!==null&&Egn(n,e))return e;` |
| `CLAUDE_CODE_SUBAGENT_MODEL` default | `chunk-3963bmck.js` · `vV()` | `chunk-wyjryvm7.js` · `gee()` |

### Bash helper

| Role | 2.1.261 | 2.1.280 |
|---|---|---|
| Bash tool helper-exec env | `chunk-3963bmck.js` · `D[HJe]=process.execPath` → replaced by `D[HJe]=jAe(SD(),P()==="windows"?"claude.exe":"claude")` | `chunk-dt8bvbsd.js` · inside `getEnvironmentOverrides(w,M,D)`: `j[w_e]=process.execPath`. The path-join and install-dir helpers (`jAe`/`SD` equivalents) still need resolving in that chunk |

### Other build-input changes

- Stock SHA, file size 217254576, and module count 2213.
- N-API modules: 3 instead of 5 (§1 corrections).
- Embedded Bun 1.4.3 vs pinned 1.4.1.

---

## 4. Unverified items, as concrete checks

### 4a. Env-var replacement for patch 2 (on stock or ported 2.1.280)

The overlay already contains `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000`.

- **Run:** for each alias `fable opus sonnet haiku`, run `<2.1.280 build> --settings ~/.claude/claude-mix-settings.json --model $A -p "/context" --max-turns 1`, then grep the output for `Tokens:`.
- **Pass:** fable `…/1m` (or 1000k), opus `…/1m`, sonnet `…/372k`, haiku `…/372k`.
- **Also check:**
  - No `[claude-code:unrecognized_model]` line on stderr for the sonnet/haiku runs. `Sc()` should suppress it.
  - Same check with the real ids `claude-fable-5-1[1m]` and `claude-opus-5-5[1m]`: expect 1m.
- **Fail signals:**
  - Claude slots showing 372k: env leaked (see §5a).
  - GPT slots showing 200k: `xg` false or env not read.
- **How to run it:** stock 2.1.280 can do this directly. Use `/tmp/cc-2.1.280/native/package/claude`, or `runtime/bun graph/cli`, which is not patched. This does make a real model request through the proxy, via Arthur's harness. That is allowed; never call Anthropic directly.

### 4b. Renderer port (PTY)

Harness: renderpatch worktree `verify/source-pty-2.1.261.py BINARY --output DIR [--assert-render] [--extension EXT]`.

What it does:

1. Writes a 140-message synthetic transcript (`RP_USER_000` … `RP_ASSISTANT_069`, plus `RP_EXPANDED_ONLY_DETAIL` in message 35).
2. Resumes it at 100×30.
3. Sends Ctrl+O (expand), Ctrl+O (collapse), resizes to 80×30, then expands and collapses again.
4. Counts per phase: ED2 `\x1b[2J`, ED3 `\x1b[3J`, alt-screen `\x1b[?1049h`, and the first/last anchors.

Pass criteria with `--assert-render`, for every phase after startup:

- ED2 and ED3 present.
- First and last anchors both present.
- No alt-screen.
- `expandedDetail` true only in expand phases.
- Additionally (2.1.261 verification standard): exactly one ED2+ED3 pair per phase, with no double redraw on collapse.

Control run: stock 2.1.280 (unpatched) should show no ED2/ED3 and should be missing the oldest anchor after expand/collapse/resize. This proves the bug still exists upstream. **This control was NOT run.** Running it is the cheapest way to confirm "patch 1 still needed" behaviourally rather than statically.

Note: the harness hard-codes `--settings ~/.claude/claude-mix-settings.json` and fixture `version:"2.1.261"`. Should be harmless for 2.1.280, but not confirmed.

### 4c. Bun 1.4.1 vs embedded 1.4.3

Only `--version` has been run. Checks:

1. **Import/runtime surface:** run `runtime/bun-1.4.1 /tmp/cc-2.1.280/graph/cli -p "say hi" --settings ~/.claude/claude-mix-settings.json`. Expect a normal reply and exit 0. Watch for `SyntaxError`, missing `Bun.*` APIs, or N-API load errors.
2. **Interactive:** start a PTY session and run the §4b control under 1.4.1. Compare its phase metrics with the stock native binary (which uses the embedded 1.4.3). They should match exactly, as they did for 2.1.261. Any difference means Bun behaviour differs.
3. **Native modules:** `bun -e 'require("/tmp/cc-2.1.280/graph/computer-use-swift.node")'` etc. for the 3 `.node` files, under 1.4.1 and under 1.4.2 (npm latest).
4. **Search for 1.4.x-only APIs:** grep the graph for `Bun.` symbols absent in 1.4.1's type defs. This is optional and low value.
5. **Alternative:** Bun 1.4.2 is available on npm (`@oven/bun-darwin-aarch64@1.4.2`). 1.4.3 can't be fetched. A reviewer could check whether the stock binary itself can run as Bun (`BUN_BE_BUN=1 native/package/claude …`). My one attempt printed the Claude version, so the env var was not honoured in this build.

### 4d. Other static-only claims worth a spot check

- **"Arthur's proxy is firstParty":** `Oe()` in chunk-x29j4pyb returns `"gateway"` only when `No()`/`J0t()`/`Q0t()` (gateway credential slots) are set. With only `ANTHROPIC_BASE_URL`, it returns `"firstParty"` unless a `CLAUDE_CODE_USE_*` provider env is set. Check: `/status` in the 2.1.280 build should not show a gateway provider.
- **"`autoCompactWindow` can only lower the window":** `aC()` returns `Math.min(g, n)`.
- **"Default `.mjs` uses only q-policies":** live release `extensions/default.mjs` imports only `*_POLICIES` from `_shared.mjs`. It passes `{ policies }` to `registerExtension` and declares no raw-slot capture use. Audit `bootstrap.mjs` and `candidate/diagnostic.mjs` before dropping the capture layer.

---

## 5. Two claims to challenge

### 5a. Can `CLAUDE_CODE_MAX_CONTEXT_TOKENS=372000` leak onto `claude-f51[1m]` / `claude-o55[1m]`?

**My claim:** no, not on 2.1.280. Argument, with citations in `/tmp/cc-2.1.280/graph/`:

1. **Only two readers of the env var.** Both are in `chunk-m200zvyg.js`, plus a notice-only use in `chunk-bjmhhyed.js` `Sc()`. (List with `uv run ctx.py graph CLAUDE_CODE_MAX_CONTEXT_TOKENS 120 90 10`. Other hits are env registries.)
   - `Pg()`: `if(De(process.env.DISABLE_COMPACT)){let e=a.CLAUDE_CODE_MAX_CONTEXT_TOKENS;…return e}` → applies to every model, but **only if `DISABLE_COMPACT` is set**. The overlay does not set it.
   - `Mg()` tail: `let g=a.CLAUDE_CODE_MAX_CONTEXT_TOKENS;if(g!==void 0&&g>0&&xg(e))return g;`. Only reached after the earlier early-returns.
2. **`[1m]` returns first.** `Mg(e,n){if(au(e))return 1e6;…}`, with `au(e){if(ZO())return!1;return Il(e)}` and `Il(e){return/\[1m\]/i.test(e)}`. `ZO()` = `CLAUDE_CODE_DISABLE_1M_CONTEXT` (not set). So any id string still carrying `[1m]` gets 1e6 before the env var is consulted.
3. **Even without `[1m]`, `xg` is false for these ids.** `xg(e){let n=Ct(e),r=Jn(n),s=ze(r);if(mJ(s)||…)return!1;let g=r.toLowerCase();return!g.startsWith("claude-")||g!==s}`. For `claude-f51`, `Ct` returns it unchanged, since `Ry("claude-f51")` is false (not in the `U$` alias list).
   - `ze()` → `ZS()` → `db()` → `KF()`: no catalog match; none of the `includes("claude-…")` rules match `claude-f51` or `claude-o55`; `QS()` only strips `-YYYYMMDD`. So `s === "claude-f51"`, and `startsWith("claude-")` is true.
   - `xg` = `false || false` = **false**, so no env value. It falls to `L0e` (200000). This is the "no `[1m]` = 200K" behaviour, not leakage.

**Where it could still go wrong (please attack these):**

- **(i) A code path that strips `[1m]` before calling `Tf`/`Mg`.** Callers pass `(model, gf())` or similar; I did not trace every caller's argument back to see whether any pass `Kt(model)` (suffix stripped). Callers are in `chunk-dt8bvbsd.js` (~10), `chunk-ad1vsmtp.js` (2), `chunk-bjmhhyed.js` (2) and `chunk-m200zvyg.js` itself.
  - Known: the subagent resolver keeps or adds `[1m]` (`qn()`, `He()`).
  - Task: find any `Tf(Kt(`, `Tf(Jn(` or `Tf(ze(` pattern, or a caller whose model variable was normalised.
  - If found, that path gets 200K for the Claude aliases, not 372000. It still would not leak, because `xg` is false for them.
  - So the leak scenario needs **both** stripped `[1m]` **and** `xg` true. `xg` true would need a canonicalisation returning a non-`claude-` id or one differing from the input. Try `ze("claude-f51")` with a `modelOverrides` entry present: `ZS` consults `pa()` = `settings.modelOverrides`. If someone later adds `modelOverrides` mapping `claude-f51`, `s` could differ from `g` and `xg` flips to true → 372000. Today there are no `modelOverrides`.
- **(ii) Subagents / teammates:** do they resolve the slot through a path that drops `[1m]`? `tO()` → `T(qn(Ct(n)),n)` keeps the suffix; `Ct` re-appends `[1m]` if present. I believe this is safe, but it is not exercised.
- **(iii) The 2.1.261 bridge (current live):** a different code path. The provider table in `extensions/_shared.mjs` `providerContextWindow` returns `fallback` for `claude-*`. The fallback is `__rpRawWindow261` (= the original `QL`), which has the same `[1m]`-first order and the `XL` gate. So there is no leak there either.

- **(iv) Parsing:** the overlay stores the value as the JSON string `"372000"`. The env registry declares it `CLAUDE_CODE_MAX_CONTEXT_TOKENS:()=>Ai` with `Ai=D.int()` (`chunk-0hm7n25m.js`), so it is parsed as an integer. The `g>0` check then works. Not exercised live.

**Decisive empirical test:** §4a `/context` for fable and opus must show 1m. Also run without the suffix (`--model claude-f51`): it should show 200k, not 372k, which proves `xg` is false for the alias.

### 5b. Is the named-teammate call site really unpatched in the live 2.1.261 release?

**My claim:** yes. Evidence, all read-only:

- Live release: `~/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4/`, release id `2.1.261-internal-sdk-darwin-arm64-2931bbef`. `~/.local/bin/claude-bridge` → `…/2.1.261-internal-sdk-darwin-arm64.4/claude-renderpatch-candidate`.
- **File:** `graph/chunk-xddhe4q4.js`. Manifest SHA-256 `109abaa2c1486c2b03add2d63739fc7660ff34fa33721b96e6a56044c017c7d0` matches `shasum -a 256` of the on-disk file.
  - At char offset 32178 (line 10): `function re(t,e){if(a.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)t=void 0;if(t==="inherit")return F(e);if(t!==void 0){if(!Rr(t))return Z(t,e);if(e!==null&&ojt(t,e))return e;return t}…`
  - `ojt` here is imported from `chunk-3963bmck.js`, the unpatched helper. The patch changed the **call site** in `cH`, not `ojt` itself.
  - `/usr/bin/grep -c __rpQ261 graph/chunk-xddhe4q4.js` → **0**.
- `release-manifest.json` → `semanticEdits` = `{chunk-3963bmck.js:2, chunk-3nf3qbb9.js:1, chunk-5vxbh0wn.js:13, chunk-7s5z3cw5.js:1, chunk-9wy4tdk8.js:1, chunk-q5rezcap.js:3, chunk-rvxxpz38.js:1, chunk-w7y6dfep.js:1}`. **`chunk-xddhe4q4.js` is not listed.** Recipe: `source_patches_2_1_261.py` has no `edit("chunk-xddhe4q4.js", …)`.
- The patched site, for contrast: `graph/chunk-3963bmck.js` contains `if(__rpQ261(4,ojt(r,t),r,t))return t;` (inside `cH`).
- **Reachability:**
  - `chunk-xddhe4q4.js` exports `{ct as spawnTeammate}`.
  - `chunk-3963bmck.js` (the Agent tool) loads it lazily: `let{spawnTeammate:Fi}=import.meta.require(".../chunk-xddhe4q4.js"),ul=await Fi({name:E,…,model:F??wGo(as,Bd(t)),modelSource:F?"tool":"frontmatter",…},t,d)`.
  - Inside xddhe4q4, spawn functions `pe`/`ue`/`z` call `H(t.model,i().mainLoopModel,t.modelSource)` → `re(...)` → the unpatched `ojt` short-circuit. The site is live when the Agent tool is called with a `name` (teammate path) and an explicit `model`.
- Memory `bug_claude_code_subagent_alias_collision.md` and `bridge-intent-2.1.261.md` describe testing only `cH`: "explicit `sonnet` with parent `claude-sonnet-4-6` returned `gpt-5.6-sol`". Neither mentions the teammate resolver.

**Where it could still be wrong (please attack these):**

- **(i) Is this `re()` actually reached for in-process named teammates, or only for tmux/split-pane backends?** The `spawnTeammate` call passes `use_splitpane:!0`, and the chunk has tmux/pane code (`tmux` ×33) plus `in_process_teammate` task creation. All three spawn functions call `H(...)` before branching, as far as I read, but I did not map which spawn function each backend uses.
- **(ii) Does `modelSource:"tool"` change anything?** It only affects telemetry precedence inside `H`. `re(n,e)` does not take it.
- **(iii) Is it exploitable with current slots?** No. Same reasoning as §1: no slot id contains another family keyword. So this is a latent gap, not an active bug.
- **Behavioural test (no network needed, same method as the 2.1.261 verification):** use an unsafe-capture test extension (see `verify/raw-capture-behavior-2.1.261.py`) to obtain `re`/`H` from chunk-xddhe4q4. Call `re("sonnet","claude-sonnet-4-6")`. Unpatched returns `"claude-sonnet-4-6"`; a correct fix would return the sonnet slot (`gpt-5.6-sol`). Note `re` is not exported, so the extension route may not reach it. A plain Bun script that imports the chunk will not expose it either.
- **Real-harness alternative:** in `claude-bridge`, set the parent model to a raw id containing "sonnet" (e.g. `/model claude-sonnet-4-6`), spawn a **named** teammate with `model: "sonnet"`, then read `~/.claude/logs/agent_models.jsonl` (SubagentStop hook). This hits the network through the proxy, which is allowed through the harness.
