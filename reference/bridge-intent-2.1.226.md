# Semantic bridge port for Claude Code 2.1.226

This is the exact-version port record for the locally verified 2.1.226 internal-SDK bridge.
The domain contracts and longer architectural rationale remain in the 2.1.220 documentation;
this file records what changed during semantic rediscovery and what was actually released.

## Identity

- Claude Code: **2.1.226**, macOS arm64
- Stock path: `~/.local/share/claude/versions/2.1.226`
- Stock SHA-256: `013a1cf17df5ff1dcc189d5d6fd3fdd5f097ddc3cd41aa9992e99805574febbe`
- Stock size: `279661952` bytes
- `__BUN`: file offset `65306624`, size `213598208`
- Bridge build: `internal-sdk-2.1.226.1`
- Raw slot API: `2.1.226.1`
- Signed artifact SHA-256: `60901a7b9a1259ff1113ef6ce8e8f49fbdc4f5a8fa4cde3cc9249ddcb2d50bb9`
- Immutable release: `2.1.226-internal-sdk-2.1.226.1-60901a7b`

The port intentionally starts from the verified 2.1.220 bridge line. It does not include the
unfinished `feature/subagent-view-history` experiment.

## Architecture and physical layout

The two-part architecture is unchanged:

1. exact-length binary replacements expose synchronous policy queries and raw capture suppliers
   from Claude Code's closure-bound internals;
2. the trusted Bun preload runtime validates exact release identity and implements the external
   runtime, default policies, optional user extension, and safe fallback behavior.

The 2.1.226 port uses eight physical ranges rather than 2.1.220's nine. Capture domain d2 moved
into the late REPL replacement and is co-located with d4; a separate app-provider replacement
blanked the UI in 2.1.226 and was rejected. The exposed logical surface remains policy domains
q0-q4 and capture domains d0-d5.

Exact offsets and lengths are frozen in `tools/semantic_bridge_2_1_226.py`; replacement sources
are under `tools/replacements/2.1.226/`. Build with:

```bash
bash patches/semantic-bridge-2.1.226.sh --force
```

The ignored signed output is `patched/claude-2.1.226-semantic-bridge`. A fresh clone must first
provide the exact stock 2.1.226 binary; the repository does not distribute either native binary.

## Verified behavior

The final artifact passed:

- strict signing and exact `2.1.226 (Claude Code)` version checks;
- eight-range static verification with 41,277 changed `__BUN` byte positions;
- q0-q4 and d0-d5 presence/contract checks;
- no-preload, bootstrap-only, incompatible collision, throwing handler, and throwing getter PTY fallbacks;
- live raw capture publication/replacement and generation-safe cleanup for all six domains;
- stock-equivalent patched-without-preload expand/collapse/resize behavior;
- trusted-runtime authoritative redraw on expand, collapse, and resize;
- immutable installer, status, normal, diagnostic, and safe modes;
- a live request routed automatically through the trusted local CLIProxyAPI/settings overlay.

Run the current bridge checks with:

```bash
uv run verify/bridge-static-2.1.226.py
uv run verify/raw-capture-behavior-2.1.226.py --startup-seconds 8 --shutdown-seconds 4
```

The local stable launcher is `~/.local/bin/claude-bridge`. The previous immutable 2.1.220 release
is retained as the rollback target; switching versions only requires repointing that symlink.
