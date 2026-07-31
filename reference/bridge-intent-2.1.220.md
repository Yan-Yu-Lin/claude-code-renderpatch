# Semantic bridge intent for Claude Code 2.1.220

> **Promotion note（2026-07）：** 本文最初記錄 disposable prototype，因此內文仍保留
> `prototype`／`not installed candidate` 的歷史措辭。後續 exact signed artifact
> `97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157` 被納入本機
> immutable release `2.1.220-internal-sdk-2.1.220.1-97dfb182`。本文件仍是九個 physical
> bridge ranges 與 fallback/verification 的 authoritative engineering record；公開 shipping、
> fresh-clone packaging 與 current API 狀態請見 [`docs/PROJECT-STATUS.md`](../docs/PROJECT-STATUS.md)。

This document records the disposable nine-site internal SDK bridge built by
[`tools/build-semantic-bridge-2.1.220.py`](../tools/build-semantic-bridge-2.1.220.py).
It implements the five frozen `globalThis.__rp.q` policy domains and all six frozen
`globalThis.__rp.c` raw capture domains from bridge ABI 1.

## Exact target and artifact

- Claude Code: **2.1.220**, macOS arm64
- Stock path: `~/.local/share/claude/versions/2.1.220`
- Stock SHA-256:
  `8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081`
- Stock/pre-sign size: **256,908,272 bytes**
- Live `__BUN`: offset **64,831,488**, size **191,365,120**
- Ignored prototype:
  `patched/claude-2.1.220-semantic-bridge-prototype`
- Signed prototype SHA-256:
  `97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157`
- Signed prototype size: **256,908,032 bytes**. The 240-byte difference is the final
  ad-hoc code-signature layout; the pre-sign patched binary remains exactly stock length and
  the complete `__BUN` range changes only inside the nine declared ranges.

The builder extracts entitlements from the exact stock binary, applies and immediately
post-verifies every edit, performs one final ad-hoc signing pass, runs strict `codesign`
verification, and requires `2.1.220 (Claude Code)` from `--version`.

The REPL range remains exactly 18,599 bytes. Its five Unicode UI literals are encoded as
ASCII Unicode escapes so Bun's embedded-source reader cannot reinterpret their UTF-8 bytes.
The 16-byte expansion is offset by three equivalent minifications in the same range:
`Boolean(Lv)` to `!!Lv`, `Array.from(bi.values())` to `[...bi.values()]`, and the d1 bitmap
literal `16777215` to the equal numeric expression `~0>>>8`. No bridge call, slot, bitmap
value, lifecycle edge, or stock fallback changes.

## Physical site table

Every old contextual range occurs once in stock and every complete replacement occurs zero
times. Immediately after each replacement, old is zero and new is one. The nine ranges are
inside live `__BUN`, equal-length, and non-overlapping.

| Physical range | Offset | Length | Executable replacement | Padding | Plane/domain |
|---|---:|---:|---:|---:|---|
| `provider-context-window` | 228,834,423 | 4,695 | 4,532 | 163 | q3 plus collision-safe q/c helpers and capture state |
| `renderer-reset` | 231,170,016 | 855 | 832 | 23 | q1 |
| `key-provider-d5-payload` | 231,293,190 | 1,646 | 1,304 | 342 | d5 provider payload/generation |
| `subagent-routing-static-d0` | 232,657,409 | 1,872 | 1,760 | 112 | q4 plus d0 |
| `key-provider-d5-lifecycle` | 238,774,101 | 5,306 | 4,288 | 1,018 | d5 publish/cleanup |
| `app-provider-d2` | 238,807,399 | 1,797 | 1,419 | 378 | d2 |
| `renderer-messages-d3` | 241,694,130 | 6,254 | 5,978 | 276 | q0 plus d3 |
| `renderer-toggle-redraw` | 243,071,716 | 2,879 | 2,819 | 60 | q2 |
| `repl-render-d4-static-d1` | 245,891,784 | 18,599 | 18,599 | 0 | d4 plus guarded static d1 |

There is no sixth serializer query. The disposable proof showed that the existing `CXr`
`altScreen` field can safely carry one authorized destructive intent to the unchanged `Hms`
serializer while the same effective boolean selects row zero.

## Raw capture plane

One top-level lexical counter and one internal helper are declared in the widened context-window
range:

```js
var rpG = 0, rpS = 0
function rpQ(...args) {
  try {
    return globalThis.__rp?.q?.(...args) ?? args[1]
  } catch {
    return args[1]
  }
}
function rpC(...args) {
  try {
    globalThis.__rp?.c?.(...args)
  } catch {}
}
```

All five policy sites call `rpQ`; all six capture domains call `rpC`. An absent facade, absent
method, non-callable method, throwing property getter, or throwing call therefore preserves the exact policy fallback
or becomes an ignored capture no-op. Valid `false` and `0` survive the nullish fallback check.
Static domains publish at generation 0 after their module dependencies initialize:

- d0 bitmap `4194303`, 22 slots, in the `Ydt` model/routing initializer;
- d1 bitmap `16777215`, 24 slots, guarded by `rpS` in the late `Ahl` render scope after
  `OGt` exists. The live metadata smoke requires all 24 static values, including `sM` and
  optional `Krl`, to be initialized before accepting the publication.

Dynamic domains use `++rpG`, never time, randomness, same-millisecond heuristics, facade state,
or new facade methods:

- d2 publishes the six app-store slots from the existing first provider effect and clears from
  that effect's existing cleanup;
- d3 publishes all 16 Messages slots after `Ze` exists on every render; its existing progress
  effect captures the same generation for cleanup;
- d4 moves the existing `OGt` construction earlier within the same late REPL declaration,
  publishes all 16 slots on every render, and extends the existing width effect cleanup;
- d5 caches `[generation, manager, bindings, refs...]` in the existing React compiler cache when
  `tp_` is rebuilt, clones only the existing interactive `cZs` child with that private payload,
  and extends its existing `useLayoutEffect` for publication and cleanup. No hook is added and
  hook order is unchanged. The offline transcript-export `tQr` instance does not become the
  live keybinding capture owner.

Every cleanup calls `rpC(domain, capturedGeneration, 0, null)`. Live metadata-only PTY tests
observed newer d3/d4 generations replacing older captures before older effect cleanups ran; the
stub rejected those stale clears without deleting the newer generation.

## Domain 0: combined Messages bitmask

The query is early in `lzb`, after the screen and virtual-scroll inputs exist and before
transcript truncation and either render cap:

```js
K = rpQ(0, 0, l) | 0
u ||= !!(K & 1)
H ||= !!(K & 2)
```

- `u` remains the effective boolean `showAllInTranscript` value.
- `H` remains the effective boolean `disableRenderCap` value.
- Bit 0 therefore reaches the existing `Me=ge&&!u&&!re` transcript truncation decision.
- Bit 1 reaches both unchanged cap gates:
  `let te=!re&&!H?Xhf(e,ce,oe*2):0` and
  `let He=!re&&!H?Xhf(at,se,oe):0`.
- With no facade or a fallback-only facade, the result is zero and both booleans retain stock
  behavior and type. This was important: an earlier disposable attempt used bitwise assignment
  directly on the booleans, which converted `false` to numeric `0`; Ink then tried to render a
  text node `"0"`. The final prototype uses boolean logical assignment and passes live PTY tests.

The wide contextual range preserves React hook count and ordering. Several behavior-neutral
minified expressions are shortened only to create byte budget: single-argument arrow
parentheses are removed, null/undefined refs remain equivalent at the cap helper, the always
unused memo result uses the existing no-op `nFS`, duplicate transcript comparison is shared,
and WeakMap initialization is expressed as one nullish-assignment initializer.

## Domain 1: atomic reset authorization

The `CXr` row decision becomes:

```js
let s = (n ||= !!rpQ(1, !1, t, n))
  ? 0
  : Math.min(o, Math.max(0, e.screen.height - e.viewport.height + 1))
```

`n` is the existing `altScreen` boolean. On the stock main screen it is false; an authorized
query changes it to true. That single effective value then does both jobs atomically:

1. the ternary selects replay start row zero; and
2. the existing clear patch remains `altScreen:n`, so unchanged `Hms` selects `Oms()`
   (ED2 + ED3 + home).

When preload/runtime/policy is absent or returns the boolean fallback, `n` stays stock and the
stock visible-row planner plus `_Xr(viewportRows)` serializer path remains active. Existing
alternate-screen resets already have `n === true`, retain row zero and `Oms()`, and do not need
to query external policy.

The contextual range includes `CXr` plus the adjacent `vUu` frame-slice helper to obtain byte
budget without changing output. Equivalent compactions include `undefined` declaration
elision, `++` loop increments, constructing the same `[Ysr, ...kho]` sequence with `push`,
inlining the hyperlink local, and combining identical style-ID assignments. The semantic
harness invokes the actual patched `CXr` bytes with stubs and proves:

- no facade: start row 20, `altScreen:false`;
- fallback facade: start row 20, `altScreen:false`;
- authorized facade: start row 0 and `altScreen:true` from the same query result;
- stock alternate screen: start row 0 and `altScreen:true`.

## Domain 2: binary-owned transcript redraw

Only entry into transcript mode can authorize the extra redraw:

```js
Pui !== "transcript" &&
  rpQ(2, !1, !0) &&
  setTimeout(oFS, 50)
```

The binary retains the private `oFS` helper and the fixed 50 ms delay. External policy receives
only a primitive boolean authorization decision. The existing screen setter,
show-all reset, React compiler cache behavior, and `tengu_toggle_transcript` telemetry event
remain present. No facade/fallback false short-circuits before `setTimeout`; exit from
transcript short-circuits before the query and never schedules a second redraw.

Equivalent cache/object and callback expressions elsewhere in the same `Hui` contextual range
provide the necessary byte budget while preserving the same values and cache slots.

## Domain 3: exact context-window fallback

The replacement computes the complete stock `SZc` result first into `r`:

1. `[1m]` suffix through `Wb(e)`;
2. native 1M beta header through `t?.includes(Cye.header)&&tG(e)`;
3. native 1M eligibility through `OH(e)`;
4. cached `fro(e)` override;
5. positive non-Claude `CLAUDE_CODE_MAX_CONTEXT_TOKENS` override; or
6. stock `_er` default.

Only then does it query:

```js
return rpQ(3, r, lo(Ei(e)))
```

The semantic harness verifies every stock branch, verifies that the exact computed fallback is
passed to `q`, and verifies an external provider override without losing environment/native
branches.

## Domain 4: only the first explicit routing gate

The explicit branch computes the stock first-call result once:

```js
let p = Xrd(r, t)
if (rpQ(4, p, r, t)) return t
```

When policy returns false, execution continues through the existing
`p=c(Jrd(Ei(r)),r)`, allowlist, fallback, provider remapping, and 1M paths. The second
frontmatter/default branch remains exactly:

```js
if (Xrd(u, t)) return t
```

The semantic harness proves absent facade retains the first stock shortcut, policy false reaches
the real alias result, and the second call stays stock and does not query domain 4.

## Verification record

### Static and build checks

```bash
./patches/semantic-bridge-2.1.220.sh --force
uv run verify/bridge-static-2.1.220.py
uv run verify/raw-capture-static-2.1.220.py
```

Passed checks:

- exact stock SHA and size;
- live `__BUN` range from `otool`;
- nine same-length, unique old=1/new=0 replacements;
- immediate old=0/new=1 post-checks;
- non-overlap and all ranges inside live `__BUN`;
- unchanged pre-sign length;
- candidate `__BUN` differs from stock only in the nine ranges;
- domains 0–4 each call `rpQ` exactly once, with no direct q call outside the helper;
- every d0–d5 publication/clear uses `rpC`, with no direct c call outside the helper;
- both helpers catch non-callable methods, throwing methods, and throwing property getters;
- unchanged stock `Hms` serializer;
- preserved second `Xrd` call and toggle telemetry;
- stock entitlement extraction and one final ad-hoc signature;
- strict `codesign` and `--version`.

### Semantic and live PTY checks

```bash
uv run verify/bridge-behavior-2.1.220.py \
  --session /path/to/disposable-source-session.jsonl \
  --startup-seconds 3 --phase-seconds 4
uv run verify/raw-capture-behavior-2.1.220.py
```

The harness copies the source JSONL into ignored `patched/bridge-fixtures/` paths, creates
only ignored trusted stub preloads, and separately exercises the real bootstrap without an
extension. It never edits production preload/runtime files.

Observed ED3 counts on the disposable test session:

| Variant | startup | expand | collapse | resize |
|---|---:|---:|---:|---:|
| stock 2.1.220 | 0 | 0 | 0 | 0 |
| patched, no preload | 0 | 0 | 0 | 0 |
| patched, real bootstrap with no extension | 0 | 0 | 0 | 0 |
| patched, fallback-only stub | 0 | 0 | 0 | 0 |
| patched, non-callable q/c collision | 0 | 0 | 0 | 0 |
| patched, throwing q/c collision | 0 | 0 | 0 | 0 |
| patched, throwing q/c getter collision | 0 | 0 | 0 | 0 |
| patched, renderer bridge on | 0 | 1 | 1 | 1 |

The bridge-on run expanded from roughly 16.6 KB stock output to 52.1 KB, then emitted one
ED2/ED3 authoritative replay on expansion, collapse, and resize. The trusted stub log confirmed
renderer domains 0, 1, and 2 were queried. No-preload, the real bootstrap with no extension,
fallback-only, non-callable collision, throwing-call collision, and throwing-getter collision
paths matched stock ED3 behavior. The semantic harness separately exercises all five policy domains
with all three collision shapes and
proves exact fallback values, including valid `false` and `0`, while the isolated toggle test
proves none of the stock-safe paths schedules `oFS`.

The raw-capture live smoke launches the real candidate in a PTY without preload, with the real
bootstrap only, with non-callable q/c, with throwing q/c calls, with throwing q/c getters, and with
a trusted frozen q/c stub. All six exited cleanly. The trusted stub run observed d0-d5 with exact
bitmap/slot-count metadata,
repeated d3/d4 replacements, and stale cleanup attempts rejected while a newer generation remained
current. The log contains only event kind, numeric domain, generation, bitmap, slot/defined counts,
and clear-match status; it never serializes a captured slot or terminal content.

## Prototype boundary

This is a disposable bridge artifact, not an installed candidate and not a launcher. It does not
modify the selected `claude`, any installed stock binary, `claude-mix`, settings, preload
bootstrap/runtime files, or the existing 2.1.219 artifact. Tier 1/2/3 facade construction remains
external runtime work; this binary supplies only the frozen q decisions and positional c captures.
