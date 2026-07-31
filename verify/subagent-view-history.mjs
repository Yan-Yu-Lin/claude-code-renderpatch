import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import {
  mergeTranscriptMessages,
  parseRecentTranscriptSource,
} from "../candidate/subagent-view-history.mjs"

const agentId = "averifier-0123456789abcdef"
const uuids = Array.from({ length: 120 }, () => randomUUID())
const records = uuids.map((uuid, index) => ({
  parentUuid: index === 0 ? null : uuids[index - 1],
  isSidechain: true,
  agentId,
  type: index % 2 === 0 ? "assistant" : "user",
  uuid,
  timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, index)).toISOString(),
  message: {
    role: index % 2 === 0 ? "assistant" : "user",
    content: [{ type: "text", text: `message ${index}` }],
  },
}))
const source = [
  ...records.map((record) => JSON.stringify(record)),
  JSON.stringify({ ...records.at(-1), agentId: "aother-0123456789abcdef" }),
  "{incomplete",
].join("\n")

const recent = parseRecentTranscriptSource(source, agentId)
assert.equal(recent.length, 80)
assert.equal(recent[0].uuid, uuids[40])
assert.equal(recent.at(-1).uuid, uuids[119])
assert.equal("isSidechain" in recent[0], false)
assert.equal("parentUuid" in recent[0], false)

const liveLast = { ...recent.at(-1), live: true }
const merged = mergeTranscriptMessages(recent, [liveLast])
assert.equal(merged.length, 80)
assert.equal(merged.at(-1), liveLast)

const liveExtra = {
  ...liveLast,
  uuid: randomUUID(),
  timestamp: new Date(Date.UTC(2026, 0, 1, 0, 3)).toISOString(),
}
const mergedWithExtra = mergeTranscriptMessages(recent, [liveLast, liveExtra])
assert.equal(mergedWithExtra.length, 81)
assert.equal(mergedWithExtra.at(-1), liveExtra)

process.stdout.write("subagent view history verifier passed\n")
