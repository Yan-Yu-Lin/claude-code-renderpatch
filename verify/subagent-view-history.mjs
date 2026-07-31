// Verifier for candidate/subagent-view-history.mjs
//
// Covers the two live-testing failures from the original prototype (duplicate growth,
// writer fighting) plus the reconstruction/merge invariants. Run:
//
//   node verify/subagent-view-history.mjs

import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"
import {
  loadRecentTranscriptFile,
  mergeTranscriptMessages,
  parseRecentTranscriptSource,
  reconstructLatestChain,
} from "../candidate/subagent-view-history.mjs"

const checks = []
const check = (name, fn) => checks.push([name, fn])

const agentId = "averifier-0123456789abcdef"

function chainRecords(count, { agent = agentId, start = 0 } = {}) {
  const uuids = Array.from({ length: count }, () => randomUUID())
  return uuids.map((uuid, index) => ({
    parentUuid: index === 0 ? null : uuids[index - 1],
    isSidechain: true,
    agentId: agent,
    type: index % 2 === 0 ? "assistant" : "user",
    uuid,
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, start + index)).toISOString(),
    message: {
      role: index % 2 === 0 ? "assistant" : "user",
      content: [{ type: "text", text: `message ${index}` }],
    },
  }))
}

// --- parsing / reconstruction ----------------------------------------------------------

check("parse keeps chain order, strips sidechain fields, filters foreign agents", () => {
  const records = chainRecords(120)
  const source = [
    ...records.map((record) => JSON.stringify(record)),
    JSON.stringify({ ...records.at(-1), uuid: randomUUID(), agentId: "aother-0123456789abcdef" }),
    "{incomplete",
    "",
  ].join("\n")

  const parsed = parseRecentTranscriptSource(source, agentId, 400)
  assert.equal(parsed.length, 120)
  assert.equal(parsed[0].uuid, records[0].uuid)
  assert.equal(parsed.at(-1).uuid, records.at(-1).uuid)
  assert.equal("isSidechain" in parsed[0], false)
  assert.equal("parentUuid" in parsed[0], false)
})

check("limit keeps the newest tail", () => {
  const records = chainRecords(120)
  const parsed = parseRecentTranscriptSource(
    records.map((r) => JSON.stringify(r)).join("\n"),
    agentId,
    80,
  )
  assert.equal(parsed.length, 80)
  assert.equal(parsed[0].uuid, records[40].uuid)
  assert.equal(parsed.at(-1).uuid, records.at(-1).uuid)
})

check("abandoned branch is dropped in favour of the newest leaf", () => {
  const main = chainRecords(10)
  const branch = {
    parentUuid: main[4].uuid,
    isSidechain: true,
    agentId,
    type: "assistant",
    uuid: randomUUID(),
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, 5)).toISOString(),
    message: { role: "assistant", content: [{ type: "text", text: "abandoned" }] },
  }
  const chain = reconstructLatestChain([...main, branch])
  assert.equal(chain.length, 10)
  assert.equal(
    chain.some((m) => m.uuid === branch.uuid),
    false,
  )
})

check("compact_boundary is never chosen as the leaf", () => {
  const main = chainRecords(6)
  // Boundary hangs off an interior message, so a real leaf still exists.
  const boundary = {
    parentUuid: main[3].uuid,
    isSidechain: true,
    agentId,
    type: "system",
    subtype: "compact_boundary",
    uuid: randomUUID(),
    timestamp: new Date(Date.UTC(2026, 0, 1, 1, 0, 0)).toISOString(),
  }
  const chain = reconstructLatestChain([...main, boundary])
  assert.equal(chain.at(-1).uuid, main.at(-1).uuid, "newest non-boundary leaf must win")
  assert.equal(
    chain.some((m) => m.uuid === boundary.uuid),
    false,
  )
})

// When the boundary is the ONLY non-parent record, stock m$t yields undefined and Xft
// returns null. Refusing beats emitting an unordered pile of records.
check("no eligible leaf refuses rather than returning an unordered pile", () => {
  const main = chainRecords(6)
  const boundary = {
    parentUuid: main.at(-1).uuid,
    isSidechain: true,
    agentId,
    type: "system",
    subtype: "compact_boundary",
    uuid: randomUUID(),
    timestamp: new Date(Date.UTC(2026, 0, 1, 1, 0, 0)).toISOString(),
  }
  assert.deepEqual(reconstructLatestChain([...main, boundary]), [])
})

check("broken parent links yield a coherent partial chain, not a pile", () => {
  const orphanA = {
    parentUuid: randomUUID(), // dangling
    isSidechain: true,
    agentId,
    type: "assistant",
    uuid: randomUUID(),
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, 1)).toISOString(),
  }
  const orphanB = {
    parentUuid: randomUUID(), // dangling
    isSidechain: true,
    agentId,
    type: "assistant",
    uuid: randomUUID(),
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, 2)).toISOString(),
  }
  const chain = reconstructLatestChain([orphanA, orphanB])
  // Newest orphan wins; its parent is missing so the chain is length 1.
  assert.equal(chain.length, 1)
  assert.equal(chain[0].uuid, orphanB.uuid)
})

check("empty input yields empty output", () => {
  assert.deepEqual(reconstructLatestChain([]), [])
  assert.deepEqual(parseRecentTranscriptSource("", agentId), [])
})

// --- merge ------------------------------------------------------------------------------

check("live object replaces its disk twin, order preserved", () => {
  const disk = parseRecentTranscriptSource(
    chainRecords(20)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
  )
  const liveLast = { ...disk.at(-1), live: true }
  const merged = mergeTranscriptMessages(disk, [liveLast])

  assert.equal(merged.length, 20)
  assert.equal(merged.at(-1), liveLast, "live object identity must win")
  assert.deepEqual(
    merged.map((m) => m.uuid),
    disk.map((m) => m.uuid),
    "order must match disk chain",
  )
})

check("live-only messages append at the tail in order", () => {
  const disk = parseRecentTranscriptSource(
    chainRecords(10)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
  )
  const extraA = { uuid: randomUUID(), type: "user", message: { role: "user", content: "a" } }
  const extraB = { uuid: randomUUID(), type: "user", message: { role: "user", content: "b" } }
  const merged = mergeTranscriptMessages(disk, [extraA, extraB])

  assert.equal(merged.length, 12)
  assert.equal(merged.at(-2), extraA)
  assert.equal(merged.at(-1), extraB)
})

// This is the v1 duplicate bug: v1 keyed only on uuid and unconditionally appended anything
// without one, so every merge pass grew the array.
check("REGRESSION: uuid-less messages do not duplicate across repeated merges", () => {
  const disk = parseRecentTranscriptSource(
    chainRecords(5)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
  )
  const noUuid = { type: "system", subtype: "note", message: { role: "user", content: "x" } }

  let live = [noUuid]
  for (let pass = 0; pass < 25; pass++) live = mergeTranscriptMessages(disk, live)

  assert.equal(live.length, 6, `expected stable length, got ${live.length}`)
  assert.equal(live.filter((m) => m === noUuid).length, 1)
})

check("merge is idempotent: merge(disk, merge(disk, live)) === merge(disk, live)", () => {
  const disk = parseRecentTranscriptSource(
    chainRecords(30)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
  )
  const live = [
    { ...disk.at(-1), live: true },
    { uuid: randomUUID(), type: "user", message: { role: "user", content: "tail" } },
    { type: "system", subtype: "no-uuid" },
  ]

  const once = mergeTranscriptMessages(disk, live)
  const twice = mergeTranscriptMessages(disk, once)
  assert.equal(twice.length, once.length)
  once.forEach((message, index) => assert.equal(twice[index], message))
})

check("duplicate uuids inside the live array collapse to one", () => {
  const disk = parseRecentTranscriptSource(
    chainRecords(4)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
  )
  const dup = { uuid: randomUUID(), type: "user", message: { role: "user", content: "d" } }
  const merged = mergeTranscriptMessages(disk, [dup, { ...dup }])
  assert.equal(merged.length, 5)
})

check("collapsed single-message live array (the stock terminal case) recovers fully", () => {
  const records = chainRecords(297)
  const disk = parseRecentTranscriptSource(
    records.map((r) => JSON.stringify(r)).join("\n"),
    agentId,
    400,
  )
  // Stock collapses to [messages.at(-1)] on completion.
  const collapsed = [disk.at(-1)]
  const merged = mergeTranscriptMessages(disk, collapsed)

  assert.equal(merged.length, 297)
  assert.ok(merged.length > collapsed.length, "must be a strict gain to be injected")
})

// --- write-gate simulation --------------------------------------------------------------
//
// Reproduces the v1 flicker: the extension injects, then a stock writer runs. Confirms the
// terminal-status gate is what stops the fight, not any delay value.

check("SIMULATION: no re-injection loop once the extension owns the array", () => {
  const disk = parseRecentTranscriptSource(
    chainRecords(50)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
  )
  const injected = new Map()
  let writes = 0

  let live = [disk.at(-1)]
  const evaluate = () => {
    if (injected.get("task") === live) return // identity gate
    const merged = mergeTranscriptMessages(disk, live)
    if (merged.length <= live.length) return // no-gain gate
    injected.set("task", merged)
    live = merged
    writes++
  }

  for (let tick = 0; tick < 50; tick++) evaluate()
  assert.equal(writes, 1, `expected exactly one write, got ${writes}`)
})

check("SIMULATION: cpt() re-slice proves a running teammate cannot be held", () => {
  // Stock cpt: append and clamp to the last 50 entries. This runs per streamed message, so
  // no settle delay can win -- the competing write is driven by agent output, not a clock.
  const cpt = (messages, next) =>
    messages.length >= 50 ? [...messages.slice(-49), next] : [...messages, next]

  const disk = parseRecentTranscriptSource(
    chainRecords(300)
      .map((r) => JSON.stringify(r))
      .join("\n"),
    agentId,
    400,
  )

  let live = mergeTranscriptMessages(disk, [disk.at(-1)])
  assert.equal(live.length, 300, "injection succeeds momentarily")

  live = cpt(live, { uuid: randomUUID(), type: "assistant" })
  assert.equal(live.length, 50, "a single streamed message destroys the injection")
})

// --- real sample ------------------------------------------------------------------------

check("real 297-record sample reconstructs to a full single chain", async () => {
  const path = join(
    homedir(),
    ".claude/projects/-Users-linyanyu",
    "1b4bf064-e54e-4c32-8a38-cdc483a1ae49/subagents",
    "agent-atranscript-verifier-d5ae591aa9f66e78.jsonl",
  )
  let source
  try {
    source = await readFile(path, "utf8")
  } catch {
    return "skipped (sample transcript not present)"
  }

  const parsed = parseRecentTranscriptSource(
    source,
    "atranscript-verifier-d5ae591aa9f66e78",
    2000,
  )
  assert.equal(parsed.length, 297)
  assert.equal(new Set(parsed.map((m) => m.uuid)).size, 297, "no duplicates")
  assert.equal(
    parsed.every((m) => !("isSidechain" in m) && !("parentUuid" in m)),
    true,
  )

  const viaLoader = await loadRecentTranscriptFile(
    path,
    "atranscript-verifier-d5ae591aa9f66e78",
    2000,
  )
  assert.equal(viaLoader.length, 297)
  return `297 records -> 297-message chain`
})

// --- runner -----------------------------------------------------------------------------

let failed = 0
for (const [name, fn] of checks) {
  try {
    const note = await fn()
    process.stdout.write(`  ok   ${name}${note ? ` — ${note}` : ""}\n`)
  } catch (error) {
    failed++
    process.stdout.write(`  FAIL ${name}\n       ${error?.message ?? error}\n`)
  }
}

process.stdout.write(
  failed === 0
    ? `\nsubagent view history verifier passed (${checks.length} checks)\n`
    : `\nsubagent view history verifier FAILED (${failed}/${checks.length})\n`,
)
process.exit(failed === 0 ? 0 : 1)
