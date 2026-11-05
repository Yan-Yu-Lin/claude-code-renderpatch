# 2.1.318 Linux x64 port (omarchy) — release .5

Branch `feature/linux-2.1.318`, based on `feature/host-2.1.318-darwin` @ `79a3373`. Built and selected on omarchy on 2026-11-05.

## Approach: official-executable host, same as the Mac

The 2.1.246 Linux method (extract the graph, run it on a pinned public Bun) does not work any more. Since 2.1.271 the renderer needs `Bun.ant.CellSegmenter`, which only exists in the Bun that Anthropic embeds in the official executable. So Linux now uses the Mac design: a verbatim official executable as `runtime/claude`, plus `host.mjs` (byte-identical to `preload/host-2.1.318.mjs`) as the only `--preload`. The preload loads the patched `graph/cli` and stops the embedded entry at its first statement.

- Official package: `@anthropic-ai/claude-code-linux-x64@2.1.318`, npm integrity `sha512-GX+7CUng2R5f…NV2A==`.
- Executable SHA-256: `708c77b204db30086ff6f1ed34577bda03e1be74ced80557cbf7b54249ebf0bd`. Size: 337,814,032 bytes (ELF x86-64).
- Graph: 3,100 records (2,857 JS, 103 text-loader, 138 file-loader, 2 native: `clipboard-napi.node`, `audio-capture.node`). The payload sits in the ELF `.bun` section (`tools/extract-source-linux-2.1.318.py`).
- Entry trap: one `process.env.NoDefaultCurrentDirectoryInExePath="1";` and seven static helper imports. Six helpers match the reviewed Darwin helpers token for token (identifiers normalized). The seventh, `chunk-0993wma0.js`, is the cwd-capture helper. Its macOS NFC/realpath normalizers compile to `return n` on Linux, so it is pinned by content hash. The builder refuses anything else.
- There is no codesign on Linux. Integrity comes from the pinned SHA-256 plus the manifest hash of every asset, as before.

## Translating the Darwin recipes (no hand-copied anchors)

Every chunk name and most minified identifiers differ between the darwin-arm64 and linux-x64 builds of the same version. In a structural comparison, none of the 26 target chunks had a matching name. `tools/build-host-release-2.1.318-linux.py` runs the **unchanged** Darwin recipes (`host_patches_2_1_318*.py`) against the hash-pinned Darwin graph. `tools/translate_anchors_2_1_318_linux.py` mirrors each edit onto the Linux graph as it runs:

- Short identifiers in the Darwin anchor become wildcards. The same identifier must bind the same way every time, and the binding must be injective. The generalized anchor must match exactly once in the Linux graph. If it does not, the translator widens it with Darwin context until it is unique (9 edits needed this).
- Names declared in the replacement are renamed to `rpv_*`. Imported names are resolved by finding the Linux definition of the Darwin export and then the Linux import that binds it. Other names are resolved by unanimous witness windows. Any disagreement is fatal.
- Darwin import-list additions (7) become separate hoisted `import{x}from"…"` declarations on Linux. Each one must bind an unused local name.
- The same strict editor runs on Linux: global old=1/new=0 before each edit and old=0/new=1 after.
- **Independent post-check** (`verify_alpha_equivalence`): each patched Darwin site plus its surrounding context must match exactly once in the patched Linux chunk, with an injective renaming covering the Linux replacement. 95 sites were checked (minimum context 60 chars around a 234-char replacement, median 912). One site was superseded by a later refining layer, as designed.
- Totals: Darwin 103 edits in 26 chunks; Linux 96 in-place edits plus 7 import additions in 26 chunks. The full decision log is `reference/linux-2.1.318-translation-log-r5.json`, also stored in the release as `translation-log.json`.

Spot-checked by reading: R9 `TLt`→`ILt` (both `forceRedraw`), S1 `z8r`→`k8r`, S2 `rpSource`, title gate `z2o()`→`uGo()` replaced by `i.CLAUDE_CODE_DISABLE_TERMINAL_TITLE`, N1 `K3t`→`LYt` imported, `T`→`h` task registry.

## Release

`~/.local/share/claude-renderpatch/releases/2.1.318-host-linux-x64.5/`. Release ID `2.1.318-host-linux-x64-adf93f84`. Manifest SHA-256 `7a078874e140b82b4c831479aee105422e4a7ca8bd034f352ad9d3aed9da190f`. The revision number 5 matches the Mac `.5` patch set: `full-redraw, explicit-subagent-model-routing, resumable-stopped-agents, teammate-transcript-view, teammate-background-work, mcp-owner-background, mcp-background-now, block-server-prompt-injection, essential-traffic-session-title`.

Rebuild (refuses an existing output):

```bash
uv run --script tools/build-host-release-2.1.318-linux.py \
  --stock ~/.cache/claude-bridge-2.1.318/package/claude \
  --darwin-stock ~/.cache/claude-bridge-2.1.318/darwin/package/claude \
  --revision 5 --mcp-background \
  --output ~/.local/share/claude-renderpatch/releases/2.1.318-host-linux-x64.<N>
```

The release launcher is `candidate/host-launcher-2.1.318-linux.in`. It has the same interface as the 2.1.246 launcher (`--renderpatch-status`, `--renderpatch-safe`) and uses only `/usr/bin` tools, because T3's service PATH is `/usr/local/bin:/usr/bin` and has no `uv`. It also adds the `-original_games_guidance` capability in normal mode. Proxy, overlay, MIX_NOTE and the `/model` guard stay in the outer `~/.local/bin/claude-bridge` (copy: `candidate/omarchy-claude-bridge-wrapper.sh`). The outer wrapper now calls `~/.local/bin/claude-renderpatch-active`, a symlink that is repointed atomically.

## Gates (omarchy, 2026-11-05)

- `--renderpatch-status`: verification=ok, reported 2.1.318. Normal and safe `--version` = `2.1.318 (Claude Code)`. A bad flag exits 1.
- Proxy `-p` on all four slots: `LINUX318_{fable,opus,sonnet,haiku}_OK`, is_error=false.
- PTY title (`verify/pty-title-2.1.318-linux.py`): patched shows `◑ Why the sky is blue`; safe (stock) only shows `… Claude Code`.
- PTY render (`verify/pty-render-2.1.318-linux.py`, 100x30, then 80x30): patched sends exactly one ED2+ED3 for each of expand, collapse and resize, the first anchor is replayed, and there is no alt screen. Safe sends 0 ED2/ED3 and the first anchor disappears after collapse.
- Agent(model:"opus") under parent `claude-opus-5-5`: the subagent transcript shows `claude-o55` (the slot) on patched and `claude-opus-5-5` (the parent, the collision bug) on safe. So S1 works.
- T3 Code 0.1.7 `thread start --provider claudeAgent --wait` returned `T3_BRIDGE_318_OK`, and the process was the new release's `runtime/claude`.

Not run on Linux: S2 named-teammate routing, resume, teammate view/background, N1/N2 MCP timing, the server-prompt synthetic test, and Mods. These are the same recipes the Mac verified. On Linux they rest on the translation plus the alpha-equivalence check, not on behavioral tests.

## Selection and rollback

Receipt: `~/.local/share/claude-renderpatch/selections/2026-11-05-2.1.318-linux.json`. The 2.1.246 `.6` release is untouched.

```bash
ln -s ~/.local/share/claude-renderpatch/releases/2.1.246-internal-sdk-linux-x64.6/claude-renderpatch ~/.local/bin/claude-renderpatch-active.rb &&
  mv -T ~/.local/bin/claude-renderpatch-active.rb ~/.local/bin/claude-renderpatch-active
```

The outer wrapper also works with the 2.1.246 launcher. A full wrapper backup is at `~/.local/bin/claude-bridge.bak-2026-11-05-pre-2.1.318`.
