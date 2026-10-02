// PURE DIAGNOSTIC. Measures the memory-vs-screen gap for the in_process_teammate
// subagent view. Writes nothing back into state; only reads and logs counts.
//
// Question this answers: at the moment the user is looking at a teammate's subagent
// view, how many messages are in state.transcripts[taskId].messages, and how many
// survive each stage of the Messages render pipeline?
//
// d4 slot 0 = live app store   -> gives state.transcripts[taskId].messages.length
// d3 slots 0..4 = pipeline     -> raw / normalized / collapsedBase / postToolStats / rendered
// d3 slots 5..15               -> cap start, truncation flags, screen, showAll, renderRange
//
//   CLAUDE_RENDERPATCH_SUBAGENT_MEASURE_LOG = absolute path
//     (default ~/.claude/renderpatch-subagent-measure.log)
//   CLAUDE_RENDERPATCH_SUBAGENT_MEASURE_AUTOVIEW = 1
//     Reproduce the user's action without a human: as soon as a running,
//     NOT-idle in_process_teammate exists, set viewingAgentTaskId to it, exactly
//     as stock UQe() does. This writes ONLY viewingAgentTaskId/viewSelectionMode.
//     It never touches state.transcripts. Without it the measurement depends on a
//     human pressing the key at the right instant.

import { appendFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

const manifest = Object.freeze({
  id: "subagent-view-measure",
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
    captureDomains: Object.freeze([
      { id: "d3", abiVersion: 1 },
      { id: "d4", abiVersion: 1 },
    ]),
  }),
})

function resolveLogPath() {
  const override = process.env.CLAUDE_RENDERPATCH_SUBAGENT_MEASURE_LOG
  if (typeof override === "string" && override.startsWith("/")) return override
  return join(homedir(), ".claude", "renderpatch-subagent-measure.log")
}

function hasSlot(capture, index) {
  return Math.floor(capture.presenceBitmap / 2 ** index) % 2 === 1
}

function len(value) {
  return Array.isArray(value) ? value.length : value === undefined ? "abs" : `!arr(${typeof value})`
}

export function activate(runtime) {
  const path = resolveLogPath()
  const write = (line) => {
    try {
      appendFileSync(path, `${new Date().toISOString()} ${line}\n`)
    } catch {
      // never break Claude Code
    }
  }

  let activation
  try {
    activation = runtime.registerExtension(manifest)
  } catch (error) {
    write(`activate: registration failed: ${error?.message ?? error}`)
    throw error
  }
  if (!activation.unsafe) {
    write("activate: unsafe denied; measure inactive")
    return activation
  }
  write(`activate: measure active log=${path}`)

  // --- store side (memory truth) ---------------------------------------------------

  const store = () => {
    const capture = activation.unsafe.capture("d4")
    if (!capture || !hasSlot(capture, 0)) return null
    const s = capture.slots[0]
    return typeof s?.getState === "function" ? s : null
  }

  let lastStoreLine = null

  const readStore = (tag) => {
    const s = store()
    if (!s) return null
    let state
    try {
      state = s.getState()
    } catch {
      return null
    }
    const taskId = state?.viewingAgentTaskId
    if (typeof taskId !== "string" || taskId.length === 0) {
      const line = "store: viewing=main"
      if (line !== lastStoreLine) {
        lastStoreLine = line
        write(`${line} [${tag}]`)
      }
      return { taskId: null, state }
    }
    const task = state.tasks?.[taskId]
    const transcript = state.transcripts?.[taskId]
    const messages = transcript?.messages
    const line =
      `store: task=${taskId} type=${task?.type ?? "?"} status=${task?.status ?? "?"} ` +
      `idle=${task?.isIdle === true} transcript=${transcript ? "yes" : "MISSING"} ` +
      `messages=${len(messages)} inProgressTools=${transcript?.inProgressToolUseIDs?.size ?? "?"}`
    if (line !== lastStoreLine) {
      lastStoreLine = line
      write(`${line} [${tag}]`)
    }
    return { taskId, state, messages }
  }

  // --- render side (what the pipeline actually kept) --------------------------------
  //
  // d3 is render-latest: every <Messages> render republishes it. The subagent view and
  // the main REPL both render through the same component, so the log records `screen`
  // and the store's viewed task on the same line to keep them attributable.

  const SLOTS = [
    [0, "raw"],
    [1, "normalized"],
    [2, "collapsedBase"],
    [3, "postToolStats"],
    [4, "rendered"],
  ]

  let lastPipelineLine = null

  const readPipeline = (metadata) => {
    const capture = activation.unsafe.capture("d3")
    if (!capture) return

    const parts = []
    for (const [index, name] of SLOTS) {
      parts.push(`${name}=${hasSlot(capture, index) ? len(capture.slots[index]) : "-"}`)
    }

    const scalar = (index, name) =>
      hasSlot(capture, index) ? `${name}=${JSON.stringify(capture.slots[index]) ?? "?"}` : `${name}=-`

    // Attribute the raw -> collapsedBase drop. The collapse happens inside one
    // useMemo (@241199971) whose first step is:
    //
    //   He = hlp( Ee.filter(t!=="progress").filter(!SQo).filter(Dlp(_, ge)) , Fe)
    //
    // and hiddenMessageCount = He.length - 30, so the log already pins He. These
    // counts say which of the three filters is responsible. Only shapes are read;
    // no message content is logged.
    let breakdown = ""
    if (hasSlot(capture, 1) && Array.isArray(capture.slots[1])) {
      const normalized = capture.slots[1]
      const byType = new Map()
      let meta = 0
      let transcriptOnly = 0
      let toolResult = 0
      for (const m of normalized) {
        byType.set(m?.type, (byType.get(m?.type) ?? 0) + 1)
        if (m?.isMeta === true) meta++
        if (m?.isVisibleInTranscriptOnly === true) transcriptOnly++
        const first = m?.message?.content?.[0]
        if (m?.type === "user" && first?.type === "tool_result") toolResult++
      }
      const types = [...byType.entries()].map(([k, v]) => `${k}:${v}`).join(",")
      breakdown = ` || types={${types}} isMeta=${meta} transcriptOnly=${transcriptOnly} toolResults=${toolResult}`
    }

    const line =
      `${parts.join(" ")} ` +
      `${scalar(5, "capStart")} ${scalar(8, "truncated")} ${scalar(9, "hiddenCount")} ` +
      `${scalar(10, "virtScroll")} ${scalar(11, "capRows")} ${scalar(12, "screen")} ` +
      `${scalar(13, "showAll")} ${scalar(14, "noRenderCap")} ${scalar(15, "range")}` +
      breakdown

    if (line === lastPipelineLine) return
    lastPipelineLine = line

    const s = readStore("d3")
    write(`pipeline: gen=${metadata?.generation ?? "?"} viewing=${s?.taskId ?? "main"} storeMessages=${len(s?.messages)} | ${line}`)
  }

  const stopD3 = runtime.read.observe("d3", ({ event, metadata }) => {
    if (event === "clear") return
    readPipeline(metadata)
  })

  // Store subscription: catches view switches even when no re-render publishes d3.
  let unsubscribe = null
  let subscribed = null
  const attach = () => {
    const s = store()
    if (!s || s === subscribed) return
    unsubscribe?.()
    subscribed = s
    try {
      unsubscribe = s.subscribe(() => {
        readStore("store")
        maybeAutoview()
      })
      write("attach: subscribed")
      readStore("initial")
      maybeAutoview()
    } catch (error) {
      unsubscribe = null
      subscribed = null
      write(`attach: failed ${error?.message ?? error}`)
    }
  }

  // --- autoview (optional, reproduces the human keypress) ---------------------------

  const autoview = process.env.CLAUDE_RENDERPATCH_SUBAGENT_MEASURE_AUTOVIEW === "1"
  let autoviewed = false

  const maybeAutoview = () => {
    if (!autoview || autoviewed) return
    const s = store()
    if (!s) return
    let state
    try {
      state = s.getState()
    } catch {
      return
    }
    if (typeof state?.viewingAgentTaskId === "string") return
    const entries = Object.entries(state?.tasks ?? {})
    const hit = entries.find(
      ([, t]) => t?.type === "in_process_teammate" && t.status === "running" && t.isIdle !== true,
    )
    if (!hit) return
    autoviewed = true
    const [taskId] = hit
    write(`autoview: switching to task=${taskId} (running, not idle)`)
    // Mirror stock UQe: only the view fields, plus the retain/evictAfter clearing it does.
    s.setState((prev) => {
      const task = prev.tasks?.[taskId]
      if (!task) return prev
      return {
        ...prev,
        viewingAgentTaskId: taskId,
        viewSelectionMode: "viewing-agent",
        tasks: { ...prev.tasks, [taskId]: { ...task, evictAfter: undefined } },
      }
    })
  }

  const stopD4 = runtime.read.observe("d4", ({ event }) => {
    if (event === "clear") {
      unsubscribe?.()
      unsubscribe = null
      subscribed = null
      return
    }
    attach()
  })

  attach()

  runtime.register?.("subagent-view-measure:stop", () => {
    stopD3?.()
    stopD4?.()
    unsubscribe?.()
    unsubscribe = null
    subscribed = null
  })

  return activation
}

export default activate
