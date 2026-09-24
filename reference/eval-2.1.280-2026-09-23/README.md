# renderpatch 2.1.280 evaluation — 2026-09-23

Static, read-only evaluation by an Opus 5.5 subagent of whether Arthur's claude-bridge patch set
(full-redraw inline rendering / provider context window / subagent explicit-model routing) is still
needed on stock Claude Code 2.1.280. Decision: NOT upgrading yet. Summary lives in memory note
`reference_renderpatch_2_1_280_eval.md`; this folder is the full evidence.

- `handoff-notes.md` — 416-line handoff for a second reviewer (report verbatim, artifact guide,
  2.1.261→2.1.280 rename table with chunk names on both sides, unverified items as pass/fail checks,
  two claims to challenge with evidence).
- `extract.py` — repo `tools/extract-source-darwin.py` with the SHA pin removed (extracts the Bun ESM graph
  from a stock darwin-arm64 binary into a directory).
- `anchor_check.py` — tests every 2.1.261 exact anchor string against an extracted graph.
- `ctx.py` / `resolve.py` — regex context search over graph chunks; follow chunk-local import aliases
  (minified names are per-chunk, never global).

The ~350 MB scratch (`/tmp/cc-2.1.280/`: stock 2.1.280 npm tarballs, extracted graph, CHANGELOG.md)
was NOT kept; §2 of handoff-notes.md has the exact commands to regenerate it. A copy of this folder
also sits in the renderpatch repo at `reference/eval-2.1.280-2026-09-23/` (branch
feature/internal-sdk-2.1.261-darwin worktree).
