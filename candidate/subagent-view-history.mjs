import { lstat, readFile, readdir } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"

const MAX_DISK_MESSAGES = 80
const MAX_MERGED_MESSAGES = 100
const REFRESH_DELAY_MS = 150
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const AGENT_ID_PATTERN = /^a(?:[\w-]{1,63}-)?[0-9a-f]{16}$/
const PROJECTS_ROOT = join(homedir(), ".claude", "projects")

const manifest = Object.freeze({
  id: "subagent-view-history",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: true,
  requires: Object.freeze({
    policyApiVersion: 2,
    bridges: Object.freeze([]),
    bridgeAbi: 1,
    rawSlotApi: "2.1.220.1",
    target: Object.freeze({
      version: "2.1.220",
      bridgeBuildId: "internal-sdk-2.1.220.1",
      stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      artifactSha256: "97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157",
    }),
    captureDomains: Object.freeze([{ id: "d4", abiVersion: 1 }]),
  }),
})

function isMessageRecord(value, agentId) {
  return (
    value !== null &&
    typeof value === "object" &&
    UUID_PATTERN.test(value.uuid ?? "") &&
    value.agentId === agentId &&
    value.isSidechain === true
  )
}

function messageTimestamp(message) {
  const timestamp = Date.parse(message.timestamp)
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY
}

function reconstructLatestChain(messages) {
  if (messages.length === 0) return []

  const byUuid = new Map(messages.map((message) => [message.uuid, message]))
  const parentUuids = new Set(messages.map((message) => message.parentUuid).filter(Boolean))
  const leaves = messages.filter(
    (message) =>
      !parentUuids.has(message.uuid) &&
      !(message.type === "system" && message.subtype === "compact_boundary"),
  )
  const leaf = leaves.reduce((latest, message) => {
    if (!latest || messageTimestamp(message) >= messageTimestamp(latest)) return message
    return latest
  }, null)
  if (!leaf) return messages

  const chain = []
  const seen = new Set()
  let current = leaf
  while (current && !seen.has(current.uuid)) {
    seen.add(current.uuid)
    chain.push(current)
    current = current.parentUuid ? byUuid.get(current.parentUuid) : null
  }
  chain.reverse()

  return chain.length > 1 || messages.length === 1 ? chain : messages
}

function stripSidechainFields(message) {
  const { isSidechain, parentUuid, ...displayMessage } = message
  return displayMessage
}

export function parseRecentTranscriptSource(source, agentId, limit = MAX_DISK_MESSAGES) {
  const messages = []
  for (const line of source.split("\n")) {
    if (!line) continue
    try {
      const value = JSON.parse(line)
      if (isMessageRecord(value, agentId)) messages.push(value)
    } catch {
      // An actively written final line can be incomplete. The next refresh retries it.
    }
  }

  return reconstructLatestChain(messages).slice(-limit).map(stripSidechainFields)
}

export async function loadRecentTranscriptFile(path, agentId, limit = MAX_DISK_MESSAGES) {
  return parseRecentTranscriptSource(await readFile(path, "utf8"), agentId, limit)
}

export function mergeTranscriptMessages(diskMessages, liveMessages) {
  const liveByUuid = new Map()
  liveMessages.forEach((message) => {
    if (UUID_PATTERN.test(message?.uuid ?? "")) liveByUuid.set(message.uuid, message)
  })

  const merged = diskMessages.map((message) => liveByUuid.get(message.uuid) ?? message)
  const included = new Set(merged.map((message) => message?.uuid).filter(Boolean))
  for (const message of liveMessages) {
    if (!message?.uuid || !included.has(message.uuid)) merged.push(message)
  }

  return merged.slice(-MAX_MERGED_MESSAGES)
}

function sameMessageSequence(left, right) {
  if (left.length !== right.length) return false
  return left.every((message, index) => {
    const other = right[index]
    if (UUID_PATTERN.test(message?.uuid ?? "") && UUID_PATTERN.test(other?.uuid ?? "")) {
      return message.uuid === other.uuid
    }
    return message === other
  })
}

async function regularFile(path) {
  try {
    const info = await lstat(path)
    return info.isFile() && !info.isSymbolicLink()
  } catch {
    return false
  }
}

async function findNestedAgentFile(root, filename, depth = 0) {
  if (depth > 3) return null
  let entries
  try {
    entries = await readdir(root, { withFileTypes: true })
  } catch {
    return null
  }

  for (const entry of entries) {
    if (entry.isSymbolicLink()) continue
    const path = join(root, entry.name)
    if (entry.isFile() && entry.name === filename) return path
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const found = await findNestedAgentFile(join(root, entry.name), filename, depth + 1)
    if (found) return found
  }
  return null
}

async function findAgentTranscript(parentSessionId, agentId) {
  if (!UUID_PATTERN.test(parentSessionId) || !AGENT_ID_PATTERN.test(agentId)) return null

  let projects
  try {
    projects = await readdir(PROJECTS_ROOT, { withFileTypes: true })
  } catch {
    return null
  }

  const filename = `agent-${agentId}.jsonl`
  for (const project of projects) {
    if (!project.isDirectory() || project.isSymbolicLink()) continue
    const subagents = join(PROJECTS_ROOT, project.name, parentSessionId, "subagents")
    const direct = join(subagents, filename)
    if (await regularFile(direct)) return direct
    const nested = await findNestedAgentFile(subagents, filename)
    if (nested && (await regularFile(nested))) return nested
  }
  return null
}

export function activate(runtime) {
  const activation = runtime.registerExtension(manifest)
  if (!activation.unsafe) return

  const timers = new Map()
  const transcriptPaths = new Map()
  const inFlight = new Set()

  const refresh = async (taskId, parentSessionId, agentId) => {
    const key = `${parentSessionId}:${agentId}`
    if (inFlight.has(key)) return
    inFlight.add(key)
    try {
      let path = transcriptPaths.get(key)
      if (!path || !(await regularFile(path))) {
        path = await findAgentTranscript(parentSessionId, agentId)
        if (!path) return
        transcriptPaths.set(key, path)
      }

      const diskMessages = await loadRecentTranscriptFile(path, agentId)
      if (diskMessages.length === 0) return

      const latest = activation.unsafe.capture("d4")
      const store = latest?.slots[0]
      if (typeof store?.setState !== "function") return
      store.setState((state) => {
        if (state.viewingAgentTaskId !== taskId) return state
        const task = state.tasks?.[taskId]
        if (
          task?.type !== "in_process_teammate" ||
          task.identity?.parentSessionId !== parentSessionId ||
          task.identity?.resumableAgentId !== agentId
        ) {
          return state
        }

        const transcript = state.transcripts?.[taskId]
        const liveMessages = Array.isArray(transcript?.messages) ? transcript.messages : []
        const messages = mergeTranscriptMessages(diskMessages, liveMessages)
        if (sameMessageSequence(messages, liveMessages)) return state

        return {
          ...state,
          transcripts: {
            ...state.transcripts,
            [taskId]: {
              inProgressToolUseIDs: new Set(),
              ...transcript,
              messages,
            },
          },
        }
      })
    } finally {
      inFlight.delete(key)
    }
  }

  const scheduleCurrentView = () => {
    const capture = activation.unsafe.capture("d4")
    const store = capture?.slots[0]
    if (typeof store?.getState !== "function") return

    let state
    try {
      state = store.getState()
    } catch {
      return
    }
    const taskId = state.viewingAgentTaskId
    const task = taskId ? state.tasks?.[taskId] : null
    const parentSessionId = task?.identity?.parentSessionId
    const agentId = task?.identity?.resumableAgentId
    if (
      task?.type !== "in_process_teammate" ||
      !UUID_PATTERN.test(parentSessionId ?? "") ||
      !AGENT_ID_PATTERN.test(agentId ?? "")
    ) {
      return
    }

    const timerKey = `${taskId}:${agentId}`
    if (timers.has(timerKey)) return
    const timer = setTimeout(() => {
      timers.delete(timerKey)
      refresh(taskId, parentSessionId, agentId).catch(() => undefined)
    }, REFRESH_DELAY_MS)
    timers.set(timerKey, timer)
  }

  runtime.read.observe("d4", ({ event }) => {
    if (event !== "clear") scheduleCurrentView()
  })
  scheduleCurrentView()
}

export default activate
