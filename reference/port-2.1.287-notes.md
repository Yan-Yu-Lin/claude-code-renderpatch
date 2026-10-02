# Port notes: 2.1.281 → 2.1.287 Darwin official-binary host

Completed on 2026-10-02 in `.claude/worktrees/bridge-2.1.287`, branch `feature/host-2.1.287-darwin`, starting at `42f303e`. The [final behavior and evidence table](bridge-intent-2.1.287.md) is authoritative. This log records the changes and the unsuccessful attempts so the next port does not repeat them.

## Input and prior-release checks

- Read README, both 2.1.281 intent/history records, extractor, source-policy patcher, baked host patcher, builder, host preload, launcher and PTY harness in full.
- Read the canonical `project_claude_bridge.md` memory for the previous selection and verification method.
- Input already downloaded: `/tmp/cc287/package/claude` from `@anthropic-ai/claude-code-darwin-arm64@2.1.287`.
- SHA-256 `6eab8333fe2121553100d8f40bfada384a3e989b94f947e18ba6677a6fcb41ea`; size `227827120`; `codesign --verify --strict` passes; `TeamIdentifier=Q6L2SF6YDW`.
- Signature timestamp reported Oct 2, 2026 at 00:11:41 local; executable build metadata says `2026-10-01T16:02:06Z`.
- Fresh extractor parsing confirms 2,404 records and the same three `.node` assets. The previous **2.1.281** host had 2,266 records; 1,837 was the earlier **2.1.261** graph.
- The daily launcher initially resolved to `2.1.281-host-darwin-arm64.1/claude-renderpatch-candidate`.
- Direct inspection of that installed graph found `G[l_e]=process.execPath` once. B1 was not shipped in the old host release and is not needed in this port either.

## Entry interception

The trap statement remains `process.env.NoDefaultCurrentDirectoryInExePath="1";`. The previously reported empty `top_level_non_declarations` result was accepted; the actual build also executes the normal fail-closed precondition.

Read the complete static closure: `cli` imports these six helpers, none importing further graph modules:

- `chunk-ky674g9x.js`: cwd/realpath capture and storage selector;
- `chunk-n4qghq20.js`: string-brand helpers;
- `chunk-p0nydzyj.js`: deep-link argument guard;
- `chunk-ykfrgrjh.js`: gh stand-in dispatcher declaration;
- `chunk-z91ttcdt.js`: argument helpers;
- `chunk-q6t47sex.js`: AI_AGENT environment helper declarations.

Only cwd/realpath reads run at module scope. The CLI body has one function declaration before the trapped assignment. No new interception design was needed. The new host preload differs only in version/comment wording, retaining natural exit and child preload isolation.

## Semantic rediscovery

All old exact anchors had moved. New site map:

| Domain | New chunk | Main symbols |
|---|---|---|
| Fullscreen selector | `chunk-qravq5t1.js` | `Sc` |
| Inline context latch | `chunk-jkt292h5.js` | `IO`, hook `ke(oe)` |
| DECSTBM / full reset | `chunk-p50qybax.js` | `WW`, `Ir` |
| Clear serialization | `chunk-nzck9a32.js` | `Lco` full clear, `cYt` viewport clear |
| Messages / memoized cap flags | `chunk-1ypw9bby.js` | `W`, `st`, `Cs` |
| Ctrl+O / redraw | `chunk-f2cpzzp9.js` | `D` toggle, `ddt` redraw |
| Plain explicit model | `chunk-5ne43w2c.js` | `LLn` same-family check |
| Named teammate model | `chunk-fkttf1dq.js` | `se`, caller `j` with source `o` |

There are 14 replacements across eight chunks. Each old anchor occurred globally once and every replacement was absent. Flags remain existing memo dependencies; no React compiler cache indices changed. S1 retains its later frontmatter shortcut; S2 passes `o==="tool"` into `se` and retains non-tool shortcuts.

The retired `source_patches_2_1_281.py` was read for history, not cloned into another unsupported public-Bun/policy ABI recipe. The new build uses only `host_patches_2_1_287.py`.

## Plugin-test argument ordering

While reading the official Mods documentation and CLI, found the early dispatch:

```js
const t = process.argv.slice(2)
if (t[0] === "plugin" && t[1] === "test") {
  // ... pluginTestMain(t.slice(2))
}
```

The existing launcher always prepended `--settings` and `--append-system-prompt`, so it would miss this dispatch. Putting those options after `plugin test` is also invalid: that runner accepts a directory/help/private child arguments, not root session flags.

Decision: only leading `plugin test` passes through verbatim, retaining the host preload in normal mode and all existing launcher integrity/proxy/sensitive-file checks. Other invocations are unchanged. The new official fixture passed `plugin validate` and `plugin test` under both stock and the host.

## Candidate .1: renderer and models passed, actual Mods failed

Built immutable `2.1.287-host-darwin-arm64.1`, release ID `2.1.287-host-darwin-arm64-700d90fd`, manifest `991b7b4b641355157b740c47726bcfa713694fbbe9fee3fa007f01d026f892e3`.

- Status, versions, bad-flag exit, all four real model responses/context windows and full redraw passed.
- `plugin validate`: passed.
- `plugin test`: 1 pass / 0 fail.
- **Actual mod in a host session: failed.** Stock `/plugin` showed `1 mod active`; host did not. The host printed:

```text
renderpatch-mod-fixture: hooks module did not load: The "sourceText" argument must be of type string. Received Module { default: "// atom-brand/atom-brand.js..." }
Unknown command: /renderpatch-hello
```

This was a host-only difference, not a stock feature gate or plugin fixture error. The daily launcher remained on 2.1.281.

### Root cause and correction

The Mods compiler in `chunk-sthe7p0e.js` initializes source using the shared `Ie=import.meta.require` helper:

```js
var et = Ie("/$bunfs/root/state-library.js-wy8y4843.txt")
```

The old graph builder rewrote **every** embedded path to an extracted filesystem path. The module table marks this asset loader 13. A throwaway preload in the official binary compared the two forms directly:

```json
{"embedded":"string","extracted":"object","extractedDefault":"string","equal":true}
```

Decision: preserve original embedded references for **all loader-13 records**, not special-case the one state-library filename, wrap globals, or patch the Mods compiler. The byte-identical pinned host already supplies the correct loader behavior. Continue extracting/hash-listing every record, but rewrite other record paths as before.

Why the test command was misleading: the test runner spawns an isolated official child after `BUN_OPTIONS` is removed. That child has the correct compiled text semantics even when the parent extracted graph does not. A live `--plugin-dir` command and `/plugin` check must remain part of this upgrade gate.

## Candidate .2: full gate passed

Rebuilt into a new immutable directory instead of modifying `.1`:

- Directory `2.1.287-host-darwin-arm64.2`;
- release `2.1.287-host-darwin-arm64-700d43be`;
- manifest `dd18602004edce16eeedd31d860a2c791b1eefef7f6bc26c92f6472fd0d2104d`.

The live command now returns `renderpatch-mod-fixture: RENDERPATCH_MOD_2_1_287`, exactly like stock. `/plugin` shows `1 mod active · renderpatch-mod-fixture`. Official validate/test remain green. Renderer metrics are unchanged. The four final model responses and `/context` checks were repeated on `.2`; Opus included `<final_answer>` tags around its marker, recorded rather than hidden or retried.

## Routing verification traps encountered

1. **`-p` with Agent `name` is not sufficient to test S2.** A first headless invocation supplied `name:"routeprobe"` and returned Sol, but its result was an ordinary anonymous `agentId`. Inspection showed startup creates session team context only in interactive mode (`Oo() && !Ce() && !o.agentId`). The headless result was discarded as S2 evidence.
2. **TeamCreate/TeamDelete are not available here.** A probe that requested them received only Task/SendMessage in the tool list; no team was created. It was not counted as a routing pass.
3. **Long PTY input plus Enter in one write was treated as pasted input.** The first interactive probe displayed the text without submitting it. Corrected the throwaway driver to send text, wait, then send Enter separately.
4. **Actual named-teammate test:** launch interactive with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `--teammate-mode in-process`, parent `claude-sonnet-4-6`, then request Agent `name:"routeprobe", model:"sonnet"`. Both patched and safe sessions returned `Spawned successfully` with a `routeprobe@session-...` identity. Their own teammate JSONL assistant records reported respectively `gpt-5.6-sol` and `claude-sonnet-4-6`.

Plain Agent was independently verified using forwarded child assistant messages, again Sol versus parent in safe mode. Both routing changes are therefore exercised at their actual call sites, not inferred from requested tool parameters or a model's self-identification.

## Launcher, lifecycle and environment

- Status verifies manifest/verifier/asset hashes, file modes, official SHA, strict codesign and Anthropic team. Proxy is up and the current-user listener is trusted.
- Copied the new release with APFS clone-on-write for tamper tests; the immutable original was never edited. Graph change, host change and extra asset each refused with exit 1 and the expected integrity error.
- Normal inherited `BUN_OPTIONS` refused; safe mode scrubbed it and exited 0 on version.
- Normal and safe version each print once, exit 0. Invalid flag exits 1, like stock.
- Same interactive mod scenario: Ctrl+C twice exits 0 in host 0.172 s versus stock 0.153 s.
- Model restore was checked live: no prior `settings.json.model`; `/model gpt-5.6-sol` saved that value during the session; wrapper restored no saved model after exit.
- A real Bash tool child and MCP child reported no preload/host variables. Bash helper execPath was the official release runtime. Response `CHILD_ENV_OK`, no permission denials.

## Selection and delivery

The recipe was committed as `49fd143` before selection. After all gates passed, created `claude-bridge.select-2.1.287` beside the live symlink and atomically replaced the link with `os.replace`. A new receipt records old/new paths, release/manifest identity, verification status, recipe commit, evidence location and the one-line rollback.

Through the selected daily path: status passed; normal/safe version printed 2.1.287; the mod command returned its marker; `plugin test` reported 1 pass / 0 fail; a real Sonnet request returned `SELECTED_287_OK`, all exit 0.

No edits were made to the 2.1.281 rollback, older releases, plain `claude`, proxy configuration, other worktrees or Omarchy. No npm/uv install was necessary. Generated output stays in the release directories and this worktree's ignored `patched/` directory, never Desktop.

After the selected-path smoke test, the rejected `.1` candidate, isolated tamper clone,
throwaway Python/preload probes and generated mod copy were moved with `trash`.
Only the two rejected read-only directory roots needed write permission for macOS Trash;
neither the selected `.2` release nor any rollback directory was changed. JSON/ANSI
evidence and the committed PTY harness/mod fixture remain available.

## Sources and local evidence

- [Official Mods overview](https://code.claude.com/docs/en/plugins/mods/overview.md)
- [Create Mods](https://code.claude.com/docs/en/plugins/mods/create.md)
- [Mods reference](https://code.claude.com/docs/en/plugins/mods/reference.md)
- [Troubleshooting](https://code.claude.com/docs/en/plugins/mods/troubleshoot.md)

These pages were read with `fcrawl scrape`. Local evidence: `patched/verification-2.1.287/`, notably `provenance.json`, `text-loader-reproduction.json`, `render-host2/summary.json`, `render-safe/summary.json`, `render-stock/summary.json`, `routing-summary.json`, `slots-summary.json`, `context-summary.json`, `host2-mod-ui/`, `model-restore-host2/summary.json`, `bash-child-env.json`, `mcp-child-env.json`, and `selected-*.json`.
