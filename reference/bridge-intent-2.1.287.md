# Claude Code 2.1.287 — Darwin arm64 host bridge

Verified and selected on 2026-10-02. The bridge remains a patched source graph hosted by an untouched official executable; it is **not implemented as a Claude Code Mod**. Official Mods now work alongside the existing renderer and routing patches.

## Selected installation

- Launcher: `~/.local/bin/claude-bridge`
- Release directory: `~/.local/share/claude-renderpatch/releases/2.1.287-host-darwin-arm64.2`
- Release ID: `2.1.287-host-darwin-arm64-700d43be`
- Build ID: `host-2.1.287-darwin-arm64.2`
- Manifest SHA-256: `dd18602004edce16eeedd31d860a2c791b1eefef7f6bc26c92f6472fd0d2104d`
- Official executable SHA-256: `6eab8333fe2121553100d8f40bfada384a3e989b94f947e18ba6677a6fcb41ea`
- Official executable size: `227827120` bytes; strict signature verification passes, Anthropic team `Q6L2SF6YDW`.
- Graph: 2,404 records, including 2,174 JavaScript, 90 text-loader records, 137 file-loader records, and three native modules (`audio-capture`, `computer-use-input`, `computer-use-swift`).
- Branch: `feature/host-2.1.287-darwin`; recipe commit `49fd143`.
- Selection receipt: `~/.local/share/claude-renderpatch/selections/2026-10-02-2.1.287-host.json`.
- Rollback: the untouched `2.1.281-host-darwin-arm64.1` release.

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.281-host-darwin-arm64.1/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback" && mv -h "$HOME/.local/bin/claude-bridge.rollback" "$HOME/.local/bin/claude-bridge"
```

## Host architecture and changes from 2.1.281

The [2.1.281 host architecture](bridge-intent-2.1.281.md) is retained: `host.mjs` removes `BUN_OPTIONS`, imports the patched `graph/cli`, and intercepts the embedded entry's first `process.env.NoDefaultCurrentDirectoryInExePath="1"` write. Only a caller frame from `/$bunfs/root/cli` can trigger the one-shot sentinel. Natural exit remains under the application's control.

The 2.1.287 entry has six static helper modules plus the entry itself. Inspection found only declarations and cwd/realpath reads before the trap; the builder also rejects executable entry-body statements before that write. No public Bun, compatibility shim, or legacy renderpatch extension ABI is added.

Two compatibility changes were necessary beyond rediscovering minified anchors:

1. **Preserve Bun's compiled text loader.** The old blanket path rewrite turns `require(embedded-text)` from a string into an external module namespace `{default: string}`. Official Mods compile the embedded `state-library.js-*.txt` and fail on the namespace object. The host builder now leaves every loader-13 reference at its original `/$bunfs/root/...` path. The exact, signature/hash-pinned host supplies those strings; their extracted copies remain in the verified asset set. This is an asset-loading correction, not a patch to the Mods API.
2. **Keep `plugin test` arguments at the front.** The official CLI dispatches this command before parsing root options. For leading `plugin test`, the launcher passes argv unchanged instead of injecting `--settings` and `--append-system-prompt`. Release, proxy and sensitive-file checks remain intact; other invocations retain the provider overlay and routing note.

The first candidate, `.1`, failed the live mod command and was never selected. Build `.2` is the verified release. Details and rejected verification attempts are in [the port log](port-2.1.287-notes.md).

## Baked-in patches

`tools/host_patches_2_1_287.py` carries 14 exact replacements across eight chunks, corresponding to the existing renderer sites and two routing paths. Original anchors were checked globally unique during rediscovery; the patcher requires each expected old anchor once and rejects an already-present replacement.

| Site | 2.1.287 chunk / anchor | Behavior after patch |
|---|---|---|
| R1 fullscreen selector | `chunk-qravq5t1.js`, `function Sc(e=x2){` | Always false: no alternate-screen renderer |
| R2 inline latch | `chunk-jkt292h5.js`, `function IO(){let o=ke(oe);` | Context hook still executes; mode is always `inline` |
| R3 DECSTBM | `chunk-p50qybax.js`, `function WW(){{let n=ko();` | Always false before cached probing |
| R4 reset and operation | `chunk-p50qybax.js`, `function Ir(n,u,f,m,y,g){let C=m?0:` | Main-screen reset replays from row zero, increments reset epoch, adds `destructiveReplay` |
| R5 serialization | `chunk-nzck9a32.js`, `case"clearTerminal":d+=c.altScreen?Lco():cYt(c.viewportRows);` | Main-screen destructive replay uses ED2 + ED3 + home |
| R6 uncapped messages | `chunk-1ypw9bby.js`, `Ce=_!==void 0,W=_==="uncapped"\|\|be!==void 0,` | `W=!0` disables both message caps |
| R7 virtualization | `chunk-1ypw9bby.js`, `st=se!=null&&!gt,` | `st=!1` disables virtualized message lists |
| R8 transcript tail | `chunk-1ypw9bby.js`, `Cs=ne&&!Ce&&!st,` | `Cs=!1` keeps all loaded messages |
| R9 Ctrl+O | `chunk-f2cpzzp9.js`, `D()},Oe[6]=Ie` | Toggle, then `ddt()` after 50 ms only if no full reset already advanced the epoch |
| S1 plain Agent override | `chunk-5ne43w2c.js`, `if(n==="inherit")return h();if(LLn(n,s))return s;` | Only explicit override skips the same-family shortcut; frontmatter/default/inherit retain stock semantics |
| S2 named teammate override | `chunk-fkttf1dq.js`, `se(n,e)` called from `j(n,e,o="tool")` | Bypass same-family shortcut only when `o==="tool"`; non-tool sources remain stock |

All cap/virtualizer flags were already React memo dependencies. No compiler cache slots or REPL capture plumbing changed.

**B1 remains omitted.** The installed 2.1.281 graph was checked directly: `G[l_e]=process.execPath` appears once, unmodified. The 2.1.287 Bash child likewise receives the release's official `runtime/claude` as `CLAUDE_CODE_EXECPATH`; that executable contains the native helpers.

## Verification results

Local evidence is under this worktree's ignored `patched/verification-2.1.287/`. It includes JSON results, raw PTY ANSI captures, routing summaries and provenance. No third-party package installation was needed.

### Rendering and process lifecycle

`verify/source-pty-2.1.287.py` retains the 140-message transcript and DA1 response. `--assert-render` now requires **exactly** one ED2 and one ED3, rather than merely nonzero counts. `--safe` replaces the retired extension option.

| Phase | Patched bytes | ED2 / ED3 | First / last | Expanded thinking | Alternate screen |
|---|---:|---|---|---|---|
| expand | 57600 | 1 / 1 | both | present | no |
| collapse | 46565 | 1 / 1 | both | absent | no |
| resize | 46480 | 1 / 1 | both | absent | no |
| expand again | 55851 | 1 / 1 | both | present | no |
| collapse again | 46490 | 1 / 1 | both | absent | no |

Stock and safe controls match exactly: post-startup bytes `3327, 37040, 14323, 2743, 36922`; every phase has ED2=0, ED3=0, first=false, last=true, no alternate screen. All three harness processes exit 0. The corrected `.2` patched render metrics match the initial candidate.

| Check | Observed result |
|---|---|
| Normal / safe / stock `--version` | One `2.1.287 (Claude Code)` line, exit 0 |
| Invalid Claude flag | Host and stock exit 1 with `error: unknown option '--definitely-invalid-renderpatch-flag'` |
| Ctrl+C twice, same mod UI scenario | Host `.2`: 0.172 s, exit 0; stock: 0.153 s, exit 0 |
| Real print request after selection | `SELECTED_287_OK`, exit 0 |
| Status | `verification=ok`, `proxy_status=up`, `proxy_listener=trusted-current-user-cliproxyapi` |
| Tampered graph / host (isolated cloned release) | Exit 1: `asset hash mismatch: graph/chunk-1ypw9bby.js` / `asset hash mismatch: host.mjs` |
| Unlisted asset (isolated clone) | Exit 1: `unlisted asset: unexpected-asset` |
| Inherited `BUN_OPTIONS` | Normal mode refuses, exit 1; safe mode scrubs it and prints version, exit 0 |
| Model restoration | Before: no saved model; live `/model gpt-5.6-sol`: saved `gpt-5.6-sol`; after exit: no saved model, exit 0 |

### Provider slots and context windows

These results were repeated on the final `.2` artifact after the text-loader correction.

| Slot | Actual model | Print result | Exit | `/context` |
|---|---|---|---:|---|
| fable | `claude-f51[1m]` | `PORT_fable_OK` | 0 | `53k/1m tokens (5%)` |
| opus | `claude-o55[1m]` | `<final_answer>PORT_opus_OK</final_answer>` | 0 | `52.8k/1m tokens (5%)` |
| sonnet | `gpt-5.6-sol` | `PORT_sonnet_OK` | 0 | `30.9k/372k tokens (8%)` |
| haiku | `gpt-5.6-luna` | `PORT_haiku_OK` | 0 | `31.6k/372k tokens (8%)` |

The Opus response included literal tags; it was a successful provider response, not an exact-string-format pass. API `modelUsage.contextWindow` independently reported `1000000, 1000000, 372000, 372000`.

### Routing and child isolation

Parent `claude-sonnet-4-6`, explicit requested alias `sonnet`:

| Path | Patched actual model | Safe/stock actual model |
|---|---|---|
| Plain Agent | `gpt-5.6-sol` | `claude-sonnet-4-6` |
| Named in-process teammate `routeprobe` | `gpt-5.6-sol` | `claude-sonnet-4-6` |

Plain results came from forwarded child assistant messages. Named results came from the actual teammate transcripts, after confirming the parent tool result was `Spawned successfully` with `routeprobe@session-...`, not an ordinary anonymous subagent. Interactive session IDs: patched `3866ef1a-9996-41c9-927e-54546ec7eb7c`; safe `58a9f7b8-d024-4f62-8660-f3fc1cc2bcd9`.

A real Bash tool call and a real MCP child each reported `BUN_OPTIONS`, `RP_HOST_ENTRY`, `CLAUDE_RENDERPATCH_ACTIVE`, and `CLAUDE_RENDERPATCH_TARGET` unset. Bash reported `CLAUDE_CODE_EXECPATH=.../2.1.287-host-darwin-arm64.2/runtime/claude`; MCP had it unset. The request returned `CHILD_ENV_OK`, exit 0, with no permission denials.

### Official Mods

The committed fixture is `verify/fixtures/mod-2.1.287/`. It registers `/renderpatch-hello` through `session.start` and implements `command.run`, with a dependency-free test using `claude-code/testing`. Verification loaded an ignored copy because Claude generates local type declarations in plugin directories.

| Check | Stock 2.1.287 | Host `.2` |
|---|---|---|
| `plugin validate <fixture>` | `Validation passed`, exit 0 | Same hook/call report, exit 0 |
| `plugin test <fixture>` | `1 pass`, `0 fail`, exit 0 | `1 pass`, `0 fail`, exit 0 |
| `--plugin-dir <fixture> -p /renderpatch-hello` | `renderpatch-mod-fixture: RENDERPATCH_MOD_2_1_287`, exit 0 | Identical output, exit 0 |
| Interactive `/plugin` | `1 mod active · renderpatch-mod-fixture` | Same |
| Interactive `/renderpatch-hello` | Fixture marker | Same |

**Do not use `plugin test` alone as the host compatibility gate.** Its isolated child uses the unmodified official executable after preload environment scrubbing. The initial broken `.1` candidate passed it but failed the actual host session; the direct command and interactive checks are essential.

After atomic selection, the daily path was checked again for status, normal/safe version, the mod command, `plugin test` (1 pass / 0 fail), and the real `SELECTED_287_OK` response. All exited 0.

## Rebuild and future upgrades

```bash
python3 tools/build-host-release-2.1.287-darwin.py \
  --stock /absolute/path/to/official/2.1.287/claude \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.287-host-darwin-arm64.2"
```

The builder refuses an existing output. Imports are absolute; never move a completed release. For another build, choose a fresh output path. Preserve the prior selected release until all gates pass.

Read the four [official Mods documentation pages](https://code.claude.com/docs/en/plugins/mods/overview.md) via `fcrawl scrape`; see [create](https://code.claude.com/docs/en/plugins/mods/create.md), [reference](https://code.claude.com/docs/en/plugins/mods/reference.md), and [troubleshoot](https://code.claude.com/docs/en/plugins/mods/troubleshoot.md). Recheck the entry/static closure and record loader semantics on every upgrade, not only the renderer anchors.

## Scope and limits

All requested upgrade gates passed. Plain `claude`, proxy configuration, other worktrees, older releases and Omarchy were left untouched. No big npm/uv install was performed. Verification covers a small in-process command mod and its official test API, not every Mods hook or arbitrary third-party mod. Full redraw still erases shell scrollback with ED3 and increases rendering work on very large loaded transcripts; it cannot restore messages already removed by compaction.
