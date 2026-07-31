// Restores the full transcript for a finished in_process_teammate in the subagent view.
//
// Stock 2.1.220 keeps a teammate's live transcript inside a 50-entry window (cpt), then
// collapses it to [messages.at(-1)] when the agent reaches a terminal status. The Ahl
// disk-backfill effect that would restore it only accepts local_agent, so a collapsed
// teammate can never come back. The complete sidechain JSONL is still on disk.
//
// This extension reads that JSONL and writes the reconstructed chain back into
// state.transcripts[taskId].messages, but only while the teammate is in a terminal status.
// That restriction is the whole design: see WRITE OWNERSHIP below.

import { appendFileSync, statSync, truncateSync } from "node:fs"
import { lstat, readFile, readdir, stat } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"

// WRITE OWNERSHIP
//
// Every stock writer of transcripts[taskId].messages for an in_process_teammate is gated
// on the task still running:
//
//   Hko            -> returns early unless task.status === "running"
//   Zsn            -> returns early when CT(status)
//   agent loop     -> Iid(...)/cpt(...) per streamed message; the loop exits at terminal status
//   Opd (progress) -> only reached when the preceding update saw status === "running"
//
// So once status is completed/failed/killed, nothing in Claude Code rewrites that array
// again; only evictTerminal/remove can delete the whole entry. Writing there is therefore
// a single-writer operation and needs no timers, no retries, and no debounce.
//
// While the teammate is still RUNNING the opposite is true, and it is not a timing problem:
// cpt() (abs offset 232793368, fvo = 50) re-slices to the last 49 entries on every appended
// message. Any array injected is destroyed by the next streamed message, no matter how long
// we wait first. That is what made the first prototype flicker on a ~2s cycle.
//
// This also rules out a quiet-period/settle gate for running teammates: a delay measures
// elapsed silence, but the competing write is triggered by agent output, not by a clock.
// Two independent rewrites of this file converged on the same terminal-status gate; the
// binary evidence above is why it is sufficient rather than merely safer. A running
// teammate is therefore left on its stock 50-entry window on purpose.

const DEFAULT_MESSAGE_LIMIT = 400
const MAX_MESSAGE_LIMIT = 2000
const MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
const MAX_LOG_BYTES = 256 * 1024
const NESTED_SEARCH_DEPTH = 3
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const AGENT_ID_PATTERN = /^a(?:[\w-]{1,63}-)?[0-9a-f]{16}$/
const TERMINAL_STATUSES = new Set(["completed", "failed", "killed"])
const PROJECTS_ROOT = join(homedir(), ".claude", "projects")

const manifest = Object.freeze({
  id: "subagent-view-history",
  version: "2.0.0",
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

// --- diagnostics -----------------------------------------------------------------------
//
// The terminal belongs to Ink, so nothing here writes to stdout/stderr. Everything goes to
// an append-only log the user can tail. Level "summary" is the default so that "did it even
// load" is always answerable; "verbose" traces every evaluation.
//
//   CLAUDE_RENDERPATCH_SUBAGENT_VIEW_DEBUG = off | summary (default) | verbose
//   CLAUDE_RENDERPATCH_SUBAGENT_VIEW_LOG   = absolute path (default ~/.claude/renderpatch-subagent-view.log)
//   CLAUDE_RENDERPATCH_SUBAGENT_VIEW_LIMIT = max messages to restore (default 400, cap 2000)

function resolveLogLevel() {
  const raw = (process.env.CLAUDE_RENDERPATCH_SUBAGENT_VIEW_DEBUG ?? "").trim().toLowerCase()
  if (raw === "off" || raw === "0" || raw === "false") return "off"
  if (raw === "verbose" || raw === "2" || raw === "trace") return "verbose"
  return "summary"
}

function resolveLogPath() {
  const override = process.env.CLAUDE_RENDERPATCH_SUBAGENT_VIEW_LOG
  if (typeof override === "string" && override.startsWith("/")) return override
  return join(homedir(), ".claude", "renderpatch-subagent-view.log")
}

function resolveMessageLimit() {
  const raw = Number.parseInt(process.env.CLAUDE_RENDERPATCH_SUBAGENT_VIEW_LIMIT ?? "", 10)
  if (!Number.isFinite(raw) || raw < 1) return DEFAULT_MESSAGE_LIMIT
  return Math.min(raw, MAX_MESSAGE_LIMIT)
}

function createLogger() {
  const level = resolveLogLevel()
  const path = resolveLogPath()
  let rotated = false

  // Deliberately synchronous. An async logger loses every line when the process exits
  // before the queue drains -- `--version` does exactly that, which made a working
  // extension look like a broken one. Volume is a handful of lines per session, so the
  // blocking cost is irrelevant and never lands on a render path.
  const write = (line) => {
    try {
      if (!rotated) {
        rotated = true
        try {
          if (statSync(path).size > MAX_LOG_BYTES) truncateSync(path, 0)
        } catch {
          // No existing log, or it is unreadable: appending below creates it.
        }
      }
      appendFileSync(path, `${new Date().toISOString()} ${line}\n`)
    } catch {
      // Diagnostics must never break Claude Code. An unwritable log is silently dropped.
    }
  }

  return {
    level,
    path,
    // Never log message content: only counts, ids, and decisions.
    summary(line) {
      if (level !== "off") write(line)
    },
    verbose(line) {
      if (level === "verbose") write(line)
    },
  }
}

// --- transcript reconstruction ---------------------------------------------------------

function isMessageRecord(value, agentId) {
  return (
    value !== null &&
    typeof value === "object" &&
    typeof value.uuid === "string" &&
    value.agentId === agentId &&
    value.isSidechain === true
  )
}

function messageTimestamp(message) {
  const timestamp = Date.parse(message?.timestamp)
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY
}

// Mirrors the stock Xft/jze walk: pick the newest leaf that is not a compact boundary, then
// follow parentUuid back to the root. Records off that chain (abandoned branches) are
// dropped, which is what makes the result a coherent conversation rather than a pile.
export function reconstructLatestChain(messages) {
  if (messages.length === 0) return []

  const byUuid = new Map()
  for (const message of messages) if (!byUuid.has(message.uuid)) byUuid.set(message.uuid, message)

  const parentUuids = new Set()
  for (const message of messages) if (message.parentUuid) parentUuids.add(message.parentUuid)

  let leaf = null
  for (const message of messages) {
    if (parentUuids.has(message.uuid)) continue
    if (message.type === "system" && message.subtype === "compact_boundary") continue
    if (!leaf || messageTimestamp(message) >= messageTimestamp(leaf)) leaf = message
  }
  // Stock m$t returns undefined here and Xft then returns null, i.e. no backfill at all.
  // Match that refusal. Returning the unfiltered record set instead would hand the renderer
  // a pile in file order rather than a conversation, which is worse than showing nothing.
  if (!leaf) return []

  const chain = []
  const seen = new Set()
  let current = leaf
  while (current && !seen.has(current.uuid)) {
    seen.add(current.uuid)
    chain.push(current)
    current = current.parentUuid ? byUuid.get(current.parentUuid) : null
  }
  chain.reverse()

  // A short chain means broken parent links. Stock's jze has a timestamp-based repair pass
  // we cannot fully reproduce from outside; returning the coherent partial chain is the
  // honest degraded mode. If it ends up no longer than what is already displayed, the
  // no-gain gate in inject() suppresses the write.
  return chain
}

// Stock strips these two fields before handing disk records to the renderer; match it so the
// injected messages are indistinguishable from what Ahl produces for a local_agent.
function stripSidechainFields(message) {
  const { isSidechain, parentUuid, ...displayMessage } = message
  return displayMessage
}

export function parseRecentTranscriptSource(source, agentId, limit = DEFAULT_MESSAGE_LIMIT) {
  const messages = []
  for (const line of source.split("\n")) {
    if (!line) continue
    try {
      const value = JSON.parse(line)
      if (isMessageRecord(value, agentId)) messages.push(value)
    } catch {
      // The final line can be half-written while the queue is flushing. Skipping it is safe:
      // this extension only reads after the agent reached a terminal status.
    }
  }

  return reconstructLatestChain(messages).slice(-limit).map(stripSidechainFields)
}

export async function loadRecentTranscriptFile(path, agentId, limit = DEFAULT_MESSAGE_LIMIT) {
  const info = await stat(path)
  if (info.size > MAX_TRANSCRIPT_BYTES) throw new Error(`transcript too large: ${info.size}`)
  return parseRecentTranscriptSource(await readFile(path, "utf8"), agentId, limit)
}

// Order-preserving, identity-stable union. Disk order wins (it is the reconstructed parent
// chain); a live object replaces its disk twin so live-only fields survive; live-only
// messages keep their relative order at the tail.
//
// Identity, not uuid-presence, is the dedupe fallback. The v1 merge appended any message
// lacking a uuid unconditionally, so those grew duplicates on every pass. Using the object
// itself as the map key makes a repeated merge idempotent even with no uuid at all.
export function mergeTranscriptMessages(diskMessages, liveMessages) {
  const identify = (message) => {
    const uuid = message?.uuid
    return typeof uuid === "string" && uuid.length > 0 ? uuid : message
  }

  const liveByKey = new Map()
  for (const message of liveMessages) {
    const key = identify(message)
    if (!liveByKey.has(key)) liveByKey.set(key, message)
  }

  const merged = []
  const seen = new Set()
  for (const message of diskMessages) {
    const key = identify(message)
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(liveByKey.get(key) ?? message)
  }
  for (const message of liveMessages) {
    const key = identify(message)
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(message)
  }

  return merged
}

// --- transcript file lookup ------------------------------------------------------------

async function regularFile(path) {
  try {
    const info = await lstat(path)
    return info.isFile() && !info.isSymbolicLink()
  } catch {
    return false
  }
}

async function findNestedAgentFile(root, filename, depth = 0) {
  if (depth > NESTED_SEARCH_DEPTH) return null
  let entries
  try {
    entries = await readdir(root, { withFileTypes: true })
  } catch {
    return null
  }

  for (const entry of entries) {
    if (entry.isSymbolicLink()) continue
    if (entry.isFile() && entry.name === filename) return join(root, entry.name)
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink()) continue
    const found = await findNestedAgentFile(join(root, entry.name), filename, depth + 1)
    if (found) return found
  }
  return null
}

// Stock resolves this with KA(), which needs the project-dir encoder we cannot reach from
// outside. Scanning ~/.claude/projects for <parentSessionId>/subagents/agent-<id>.jsonl
// reaches the same file; results are cached per agent for the process lifetime.
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
    if (nested) return nested
  }
  return null
}

// --- state inspection ------------------------------------------------------------------

function hasSlot(capture, index) {
  return Math.floor(capture.presenceBitmap / 2 ** index) % 2 === 1
}

// Returns the teammate the user is currently viewing, but only when it is in a terminal
// status and therefore has no remaining stock writer.
function eligibleTarget(state) {
  const taskId = state?.viewingAgentTaskId
  if (typeof taskId !== "string" || taskId.length === 0) return null

  const task = state.tasks?.[taskId]
  if (task?.type !== "in_process_teammate") return null
  if (!TERMINAL_STATUSES.has(task.status)) return null

  const parentSessionId = task.identity?.parentSessionId
  const agentId = task.identity?.resumableAgentId
  if (!UUID_PATTERN.test(parentSessionId ?? "")) return null
  // tmux-pane teammates (lvd) have no resumableAgentId and no JSONL in this session.
  if (!AGENT_ID_PATTERN.test(agentId ?? "")) return null

  return { taskId, parentSessionId, agentId, status: task.status }
}

export function activate(runtime) {
  const log = createLogger()
  const messageLimit = resolveMessageLimit()

  let activation
  try {
    activation = runtime.registerExtension(manifest)
  } catch (error) {
    log.summary(`activate: registration failed: ${error?.message ?? error}`)
    throw error
  }

  if (!activation.unsafe) {
    log.summary(
      "activate: unsafe capture denied (exact target/build/ABI negotiation failed); extension inactive",
    )
    return activation
  }

  log.summary(`activate: active limit=${messageLimit} level=${log.level} log=${log.path}`)

  const transcriptPaths = new Map() // `${parentSessionId}:${agentId}` -> jsonl path
  const injected = new Map() // taskId -> the array reference this extension installed
  const inFlight = new Set() // taskId
  let subscribedStore = null
  let unsubscribe = null

  const currentStore = () => {
    const capture = activation.unsafe.capture("d4")
    if (!capture || !hasSlot(capture, 0)) return null
    const store = capture.slots[0]
    if (typeof store?.getState !== "function" || typeof store?.setState !== "function") return null
    return store
  }

  // Drops markers for tasks that no longer exist, so an evicted-then-respawned teammate is
  // evaluated fresh instead of being skipped by a stale marker.
  const pruneMarkers = (state) => {
    if (injected.size === 0) return
    for (const taskId of [...injected.keys()]) {
      if (!state.tasks || !(taskId in state.tasks)) injected.delete(taskId)
    }
  }

  const inject = async (store, target) => {
    const { taskId, parentSessionId, agentId } = target
    const key = `${parentSessionId}:${agentId}`
    inFlight.add(taskId)
    try {
      let path = transcriptPaths.get(key)
      if (!path || !(await regularFile(path))) {
        path = await findAgentTranscript(parentSessionId, agentId)
        if (!path) {
          log.summary(`inject: no transcript file for ${agentId} (session ${parentSessionId})`)
          return
        }
        transcriptPaths.set(key, path)
      }

      let diskMessages
      try {
        diskMessages = await loadRecentTranscriptFile(path, agentId, messageLimit)
      } catch (error) {
        log.summary(`inject: read failed for ${agentId}: ${error?.message ?? error}`)
        return
      }
      if (diskMessages.length === 0) {
        log.summary(`inject: transcript for ${agentId} yielded 0 usable records`)
        return
      }

      let outcome = "skipped"
      let liveCount = 0
      let mergedCount = 0

      // Everything is re-verified inside the updater: the state may have moved while the
      // disk read was in flight. Returning the same object makes setState a no-op (stock BC
      // bails on Object.is), so a stale attempt cannot notify subscribers or overwrite a
      // newer decision.
      store.setState((state) => {
        const stillEligible = eligibleTarget(state)
        if (!stillEligible || stillEligible.taskId !== taskId) {
          outcome = "target-moved"
          return state
        }

        const transcript = state.transcripts?.[taskId]
        if (!transcript) {
          outcome = "transcript-evicted"
          return state
        }

        const liveMessages = Array.isArray(transcript.messages) ? transcript.messages : []
        liveCount = liveMessages.length
        if (injected.get(taskId) === liveMessages) {
          outcome = "already-injected"
          return state
        }

        const messages = mergeTranscriptMessages(diskMessages, liveMessages)
        mergedCount = messages.length
        if (messages.length <= liveMessages.length) {
          outcome = "no-gain"
          return state
        }

        injected.set(taskId, messages)
        outcome = "injected"
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

      log.summary(
        `inject: ${outcome} task=${taskId} agent=${agentId} disk=${diskMessages.length} live=${liveCount} merged=${mergedCount}`,
      )
    } finally {
      inFlight.delete(taskId)
    }
  }

  const evaluate = (store) => {
    let state
    try {
      state = store.getState()
    } catch (error) {
      log.verbose(`evaluate: getState threw: ${error?.message ?? error}`)
      return
    }

    pruneMarkers(state)

    const target = eligibleTarget(state)
    if (!target) return
    if (inFlight.has(target.taskId)) return

    const transcript = state.transcripts?.[target.taskId]
    const liveMessages = Array.isArray(transcript?.messages) ? transcript.messages : null
    // Identity check, not a length check: this is what stops the re-entrant loop, since our
    // own setState re-enters evaluate() synchronously through the subscriber list.
    if (liveMessages && injected.get(target.taskId) === liveMessages) return

    log.verbose(
      `evaluate: eligible task=${target.taskId} status=${target.status} live=${liveMessages?.length ?? "none"}`,
    )
    inject(store, target).catch((error) => {
      inFlight.delete(target.taskId)
      log.summary(`inject: unexpected failure: ${error?.message ?? error}`)
    })
  }

  // The store notifies on every setState, which is exactly when viewingAgentTaskId or
  // task.status can change. Gating is O(1), so subscribing directly is cheaper and far more
  // precise than reacting to render generations on a timer.
  const attach = () => {
    const store = currentStore()
    if (!store) return
    if (store === subscribedStore) {
      evaluate(store)
      return
    }

    unsubscribe?.()
    subscribedStore = store
    try {
      unsubscribe = store.subscribe(() => evaluate(store))
    } catch (error) {
      unsubscribe = null
      subscribedStore = null
      log.summary(`attach: subscribe failed: ${error?.message ?? error}`)
      return
    }
    log.summary("attach: subscribed to app store")
    evaluate(store)
  }

  // d4 is render-latest, so its slots are replaced on every render. Re-resolving the store
  // here keeps the subscription bound to the live object instead of a stale generation.
  // In practice the store identity is stable (useState holds it), so attach() usually
  // short-circuits.
  runtime.read.observe("d4", ({ event }) => {
    if (event === "clear") {
      unsubscribe?.()
      unsubscribe = null
      subscribedStore = null
      log.verbose("observe: d4 cleared; detached")
      return
    }
    attach()
  })

  attach()

  runtime.register?.("subagent-view-history:stop", () => {
    unsubscribe?.()
    unsubscribe = null
    subscribedStore = null
  })

  return activation
}

export default activate
