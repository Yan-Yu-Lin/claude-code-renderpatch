# Claude Code 2.1.261 — Darwin arm64 source bridge

Original port verified 2026-09-06; Bash helper repair verified 2026-09-22. This port
builds on the Linux 2.1.246 extraction approach and preserves the Mac 2.1.226 bridge
contract and launcher behavior. It excludes the unfinished subagent-view-history
experiment. The Linux deployment remains independent.

## Provenance and release

| Component | Identity |
|---|---|
| Official Claude package | `@anthropic-ai/claude-code-darwin-arm64@2.1.261` |
| Claude binary SHA-256 | `5efecaff231b798be3c66def9be54183623b328b80eaef17f93c43987024e82a` |
| Official Bun package | `@oven/bun-darwin-aarch64@1.4.1` |
| Bun binary SHA-256 | `4c6a735e82bd9da8403f0ece106730ebe431f50a246826197bf51dc0680eb959` |
| Build | `internal-sdk-2.1.261-darwin-arm64.4` |
| Local release | `2.1.261-internal-sdk-darwin-arm64-2931bbef` |
| Manifest SHA-256 | `e275dcb7a6f59641b92ed339064efaf94ebaaa5cea4bafc0025dc66a61a057f0` |
| Version-named entry SHA-256 | `2931bbefaaa06672078b54917ae78b90663ec5f585d63cd832f707fdb0907d36` |

`latest` and `next` were 2.1.261; `stable` was 2.1.236. The exact official executable's
preload reported Bun 1.4.1. The builder pins both input hashes and reads Mach-O load commands
to locate `__BUN`, then validates Bun's trailer and module table bounds.

The graph contains 1,837 records: 1,650 JS, five N-API modules, 107 loader-5 assets, and
75 loader-13 assets. All are retained. Native modules are image-processor, computer-use-swift,
computer-use-input, audio-capture, and url-handler. Module imports are rewritten to the
final absolute release path, so an installed release must not be moved.

## Reproduce

Download the two exact packages with `npm pack --ignore-scripts` into separate staging
directories and extract them. Read each package README. No global package installation
or replacement of stock Claude is required.

```bash
uv run tools/build-source-release-2.1.261-darwin.py \
  --stock /absolute/path/to/claude-package/claude \
  --bun /absolute/path/to/bun-package/bin/bun \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4"

"$HOME/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4/claude-renderpatch-candidate" --renderpatch-status
"$HOME/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.4/claude-renderpatch-candidate" --renderpatch-diagnose
```

The output must not already exist. Its absolute path affects graph and entry hashes;
the identities above describe the verified local installation. Another user's path will
produce different artifact hashes. `--development` permits rebuilding only a directory
marked as a development build; its convenience launchers intentionally permit test preloads
and are not installed as the daily command.

## Semantic changes

- **Context:** wraps the complete current raw resolver, preserving native early-return
  behavior before applying the provider table. Kimi gets 262144; other non-Claude routes
  get 372000; Claude keeps native handling, including `[1m]`.
- **Routing:** changes only the explicit-override `ojt(r,t)` shortcut in `cH`; retains
  the second frontmatter/default call, `inherit`, the new force-model option, provider
  adaptation, and available-model checks.
- **Frames:** current `L7e` uses `history` rather than the older render-cap props. The
  policy removes both pre-normalization and final frame caps and transcript truncation,
  while disabling virtualization for a full frame.
- **Terminal:** disables fullscreen and DECSTBM mode while the full-frame policy is
  active. `Za` replays from row zero and marks the reset for ED2+ED3 serialization.
- **Toggle:** schedules a redraw after 50ms only if the renderer has not already performed
  an authoritative reset since the toggle. This removes the duplicate collapse redraw.
- **Captures:** retains all six positional domains. Separate React cleanup components
  leave the original components' hook counts/order intact. A small wrapper owns shared
  show-all state; compiler cache dependencies are updated explicitly.

Current module/symbol anchors and exact replacements live in
`tools/source_patches_2_1_261.py`. Every old anchor must occur exactly once. Do not carry
these minified identifiers or hashed chunk names into another version.

## Grep/find repair (2026-09-22)

The Bash tool, not the launcher, assigned `CLAUDE_CODE_EXECPATH=process.execPath`.
In this extracted build that is bare Bun. The shell snapshot re-executes that path
with argv0 `ugrep` or `bfs`; those implementations belong to the native stock binary,
not the extracted JavaScript. `ARGV0=ugrep bun graph/cli -G -I hello` exits 1 with
`error: unknown option '-G'`; it does not enter an embedded grep implementation.

The recipe now makes one exact-anchor replacement in `chunk-3963bmck.js`:

```diff
-D[HJe]=process.execPath
+D[HJe]=jAe(SD(),P()==="windows"?"claude.exe":"claude")
```

`HJe` is the Bash helper environment key. `SD()` is the existing native installation
directory resolver (`~/.local/bin`). The inherited override map still applies after
this assignment, and missing native binaries still take the existing command fallback.
Other `process.execPath` consumers, self-invocation, updates and resume are untouched.
No global executable identity, entrypoint flags, settings, hooks or shell prefixes changed.

Build `.4` was generated at its final immutable path and selected by atomic symlink
rename. `.3` was not edited. All asset names match; every asset matches `.3` after
normalizing release paths/build identity and undoing the single Bash expression above.
The generated launcher differs only in four release identity/hash constants. Its
settings overlay, appended prompt, proxy checks and custom policies are unchanged.

Verification used the real candidate Bash tool and sourced the existing latest
`snapshot-zsh-1790066281489-r5qetv.sh` in zsh with the effective helper environment
observed from that live tool. Results: piped grep prints `hello`; recursive grep
prints only `some-dir/visible.md:1:something visible`; native find lists both
`ignored.md` and `visible.md`. The control `command grep` finds both files, proving
that the shim's ugrep path applies `.gitignore`. Find is not asserted to honor it.
`claude-bridge --version` remains `2.1.261 (Claude Code)`; `claude-bridge -p "say hi"`
returned a greeting with exit 0. The existing `claude-f51[1m]` unknown-model warning
remains. Status reports `verification=ok`; diagnostic policy checks and child Bun pass.

Evidence/build inputs: `~/.local/share/claude-renderpatch/staging/grep-find-repair-20260922/`.
Backups: `~/.local/share/claude-renderpatch/backups/grep-find-20260922/`, including
`claude-renderpatch-candidate.bak-20260922` and the original selector symlink.

This survives rebuilding 2.1.261 from the updated recipe, not arbitrary future
upstream versions or builds from another checkout. Reapply instruction: **port this
Bash-only native-helper assignment into the next version's exact-anchor recipe,
build a new immutable release, test the shims, then select it.** Do not copy hashed
chunks or reuse minified identifiers across versions. Keep native stock Claude
available at `~/.local/bin/claude`; it was read/executed but not modified here.
New sessions use the repair; running `.3` processes must be restarted. Raw extensions
that explicitly pin build `.3` must negotiate `.4`; raw-slot ABI/slot meanings did not change.
Omarchy was not modified; its actual installed graph must be inspected before porting.

## Verification

- Static graph/asset/mode verification, exact input hashes, signed Bun, normal/status/
  diagnostic/safe modes, inherited-preload rejection, safe-mode cleanup, and mode exclusion.
- All five native modules loaded successfully; no recording, input injection, or URL
  registration operations were called. This is library-loading coverage, not full testing
  of those newer product features.
- Six capture domains: d0 bitmap 4194303, d1 3194879, d2 63, d3/d4 65535, d5 511.
  The lifecycle harness observed 25 publications/replacements and 19 clears. Missing,
  non-callable, throwing-function, and throwing-getter facades all exited cleanly.
- A 140-message synthetic transcript at 100×30, resized to 80×30: expand 57,691 bytes,
  collapse 46,345, resize 46,306. Each phase replayed the first and last anchors and emitted
  exactly one ED2+ED3 pair. Repeated toggles passed. Captured ANSI frames were visually
  inspected through terminal emulation; direct Terminal UI automation was unavailable.
- Safe-mode phase metrics matched the stock native binary: no ED2/ED3 and the oldest
  transcript anchor absent after expansion/collapse/resize. This is the behavioral control.
- Exact-version test extension successfully negotiated unsafe capture access. After app
  initialization, alias/window reads confirmed Sonnet→Sol/372000, Haiku→Kimi/262144,
  `claude-f51[1m]`→1000000, and generic non-Claude→372000.
- The actual captured subagent resolver was exercised with a deliberate family collision:
  explicit `sonnet` with parent `claude-sonnet-4-6` returned `gpt-5.6-sol`; frontmatter
  `sonnet` and `inherit` retained the parent. This test makes no network request or agent.
- Real inference through the existing Claude harness/proxy returned `BRIDGE_261_OK`,
  `PACKAGED_BRIDGE_261_OK` (Sol), and `FABLE_BRIDGE_261_OK` (Fable 5.1).

Static function capture may occur before user configuration has initialized. Extensions
that evaluate model routing should wait for app/REPL capture (d2/d4); obtaining a raw
function reference does not imply configuration readiness. Safe read methods contain failures.

## Packaging and rollback

The Mac wrapper preserves trusted listener checks, settings overlay, model-restoration
guard, explicit extension trust, and Herdr's `HERDR_AGENT=claude` hint. Its routing note
now identifies Fable 5.1 and asks for explicit subagent model selection. User settings
retain `DISABLE_AUTOUPDATER=1`.

The launcher pins the manifest and verifier; the manifest covers the complete graph,
native modules, runtime, bootstrap, extensions, helpers, and contract. Directories are
0555; executable entries and Bun are 0555; other assets are 0444. The bootstrap's legacy
`signed-bridge-artifact` status label now means the hash-verified source release whose
Bun runtime is signed; the JavaScript and shell entry do not receive a Mach-O signature.

Switch only `~/.local/bin/claude-bridge` after verification, using an atomic symlink rename.
The retained predecessor is:

```text
~/.local/share/claude-renderpatch/releases/2.1.261-internal-sdk-darwin-arm64.3/claude-renderpatch-candidate
```

Repointing the same link to that predecessor restores the old version. No running session
is migrated. Plain `claude` and the Linux installation are independent.

## Known limitations

ED3 still erases terminal scrollback above Claude, and full mounted frames cost more
memory on large sessions. Compacted-away messages cannot be recovered by rendering.
Raw extensions must negotiate the new exact version/build. This port does not add new
generic key-dispatch or banner APIs; previous API limitations remain.

Claude 2.1.261 emits an unknown-model notice for some proxy routes, including Sol and
the Fable shorthand. Real requests succeed and the provider context table is applied.
No warning suppression or model impersonation was added.
