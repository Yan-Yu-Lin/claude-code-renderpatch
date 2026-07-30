// External bootstrap for the zero-patch Claude Code preload experiment.
// Bun executes this module before Claude Code parses its command-line arguments.

import { createHash } from "node:crypto"
import { closeSync, openSync, readSync, statSync } from "node:fs"
import { basename } from "node:path"

const runtimeKey = Symbol.for("claude-code-renderpatch.runtime")
const externalModuleInput = process.env.CLAUDE_RENDERPATCH_MODULE
const userModuleInput = process.env.CLAUDE_RENDERPATCH_USER_MODULE
const targetInput = process.env.CLAUDE_RENDERPATCH_TARGET ?? null
const bridgeBuildInput = process.env.CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID ?? null
const bridgeArtifactShaInput =
  process.env.CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256 ?? null
const bridgeTargetVersionInput =
  process.env.CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION ?? null

// Do not leak one-shot preload state into Bun or Claude child processes.
delete process.env.BUN_OPTIONS
delete process.env.CLAUDE_RENDERPATCH_MODULE
delete process.env.CLAUDE_RENDERPATCH_USER_MODULE
delete process.env.CLAUDE_RENDERPATCH_ACTIVE
delete process.env.CLAUDE_RENDERPATCH_TARGET
delete process.env.CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID
delete process.env.CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256
delete process.env.CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION

const RELEASE = Object.freeze({
  bridgeBuildId: "internal-sdk-2.1.220.1",
  bridgeAbi: 1,
  bridgeManifestSchema: 1,
  extensionManifestSchema: 1,
  policyApiVersion: 2,
  rawSlotApi: "2.1.220.1",
  targetVersion: "2.1.220",
  targetStockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
  targetFileSize: 256908272,
})

const POLICY_DOMAINS = Object.freeze([
  Object.freeze({ id: 0, name: "renderer.messages", abiVersion: 1 }),
  Object.freeze({ id: 1, name: "renderer.reset", abiVersion: 1 }),
  Object.freeze({ id: 2, name: "renderer.toggleRedraw", abiVersion: 1 }),
  Object.freeze({ id: 3, name: "provider.contextWindow", abiVersion: 1 }),
  Object.freeze({ id: 4, name: "subagent.explicitModelRouting", abiVersion: 1 }),
])
const POLICY_BY_NAME = new Map(POLICY_DOMAINS.map((domain) => [domain.name, domain]))
const RENDERER_POLICY_IDS = Object.freeze([0, 1, 2])

const CAPTURE_DOMAINS = Object.freeze([
  Object.freeze({ id: 0, compactId: "d0", name: "static-model-routing", lifecycle: "static", slotCount: 22, abiVersion: 1 }),
  Object.freeze({ id: 1, compactId: "d1", name: "static-ink-terminal-dialog-diagnostics", lifecycle: "static", slotCount: 24, abiVersion: 1 }),
  Object.freeze({ id: 2, compactId: "d2", name: "provider-app-state", lifecycle: "provider", slotCount: 6, abiVersion: 1 }),
  Object.freeze({ id: 3, compactId: "d3", name: "render-messages-pipeline", lifecycle: "render-latest", slotCount: 16, abiVersion: 1 }),
  Object.freeze({ id: 4, compactId: "d4", name: "render-repl-controls", lifecycle: "render-latest", slotCount: 16, abiVersion: 1 }),
  Object.freeze({ id: 5, compactId: "d5", name: "provider-keybindings", lifecycle: "provider", slotCount: 9, abiVersion: 1 }),
])
const CAPTURE_BY_ID = new Map(CAPTURE_DOMAINS.map((domain) => [domain.id, domain]))
const CAPTURE_BY_NAME = new Map(
  CAPTURE_DOMAINS.flatMap((domain) => [
    [domain.compactId, domain],
    [domain.name, domain],
  ]),
)

function report(message) {
  process.stderr.write(`[renderpatch-preload] ${message}\n`)
}

function reportHookFailure(name, error) {
  report(`hook ${name} failed: ${error?.stack ?? error}`)
  return undefined
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.length > 0
}

function isSafeGeneration(value) {
  return Number.isSafeInteger(value) && value >= 0
}

function isPrimitive(value) {
  return value === null || ["boolean", "number", "string"].includes(typeof value)
}

function bitmapHas(bitmap, index) {
  return Math.floor(bitmap / 2 ** index) % 2 === 1
}

function deepFreeze(value, seen = new Set()) {
  if (value === null || typeof value !== "object" || seen.has(value)) return value
  seen.add(value)
  for (const child of Object.values(value)) deepFreeze(child, seen)
  return Object.freeze(value)
}

function cloneMetadata(value) {
  if (Array.isArray(value)) return value.map(cloneMetadata)
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, cloneMetadata(child)]))
  }
  return value
}

function normalizePolicyDomain(input) {
  if (Number.isInteger(input)) return POLICY_DOMAINS[input] ?? null
  if (typeof input === "string") return POLICY_BY_NAME.get(input) ?? null
  return null
}

function normalizeCaptureDomain(input) {
  if (Number.isInteger(input)) return CAPTURE_BY_ID.get(input) ?? null
  if (typeof input === "string") return CAPTURE_BY_NAME.get(input) ?? null
  return null
}

function validatePolicyPayload(domainId, payload) {
  if (!payload.every(isPrimitive)) return false
  switch (domainId) {
    case 0:
      return payload.length === 1 && typeof payload[0] === "string"
    case 1:
      return (
        payload.length === 2 &&
        (payload[0] === null || typeof payload[0] === "string") &&
        typeof payload[1] === "boolean"
      )
    case 2:
      return payload.length === 1 && typeof payload[0] === "boolean"
    case 3:
      return payload.length === 1 && typeof payload[0] === "string"
    case 4:
      return (
        payload.length === 2 &&
        typeof payload[0] === "string" &&
        typeof payload[1] === "string"
      )
    default:
      return false
  }
}

function validatePolicyResult(domainId, result) {
  switch (domainId) {
    case 0:
      return Number.isInteger(result) && result >= 0 && result <= 3
    case 1:
    case 2:
    case 4:
      return typeof result === "boolean"
    case 3:
      return Number.isSafeInteger(result) && result >= 1 && result <= 10_000_000
    default:
      return false
  }
}

function thenableStatus(value) {
  if ((typeof value !== "object" || value === null) && typeof value !== "function") {
    return false
  }
  return typeof value.then === "function"
}

function exactTargetVersion() {
  return targetInput === null ? null : basename(targetInput)
}

let targetFingerprint
function actualTargetHash() {
  if (targetFingerprint !== undefined) return targetFingerprint
  targetFingerprint = null
  if (targetInput === null) return null
  let descriptor
  try {
    const info = statSync(targetInput)
    if (!info.isFile()) return null
    const hash = createHash("sha256")
    descriptor = openSync(targetInput, "r")
    const buffer = Buffer.allocUnsafe(1024 * 1024)
    while (true) {
      const count = readSync(descriptor, buffer, 0, buffer.length, null)
      if (count === 0) break
      hash.update(buffer.subarray(0, count))
    }
    targetFingerprint = hash.digest("hex")
  } catch {
    targetFingerprint = null
  } finally {
    if (descriptor !== undefined) closeSync(descriptor)
  }
  return targetFingerprint
}

function stockLabCompatible() {
  if (targetInput === null || exactTargetVersion() !== RELEASE.targetVersion) return false
  try {
    const info = statSync(targetInput)
    return info.isFile() && info.size === RELEASE.targetFileSize
  } catch {
    return false
  }
}

function signedBridgeCompatible() {
  return (
    bridgeBuildInput === RELEASE.bridgeBuildId &&
    bridgeTargetVersionInput === RELEASE.targetVersion &&
    typeof bridgeArtifactShaInput === "string" &&
    /^[0-9a-f]{64}$/.test(bridgeArtifactShaInput) &&
    actualTargetHash() === bridgeArtifactShaInput
  )
}

function targetVerificationMode() {
  if (signedBridgeCompatible()) return "signed-bridge-artifact"
  if (stockLabCompatible()) return "stock-lab"
  return null
}

function selectedTargetCompatible() {
  return targetVerificationMode() !== null
}

function createRuntime() {
  const legacyHooks = new Map()
  const policyHandlers = new Map()
  const extensions = new Map()
  const captures = new Map()
  const captureObservers = new Map(CAPTURE_DOMAINS.map((domain) => [domain.id, new Set()]))
  const policyHealth = new Map(POLICY_DOMAINS.map((domain) => [domain.id, 0]))
  let bridgeFacadeActive = false
  let bridgeFacadeCollision = false

  const processMetadata = Object.freeze({
    execPath: process.execPath,
    argv: Object.freeze([...process.argv]),
    bunVersion: globalThis.Bun?.version ?? null,
    target: targetInput,
    launchedViaBunPreload: true,
  })

  function policyQuery(policyDomainId, fallback, ...payload) {
    try {
      if (!bridgeFacadeActive) return fallback
      const domain = normalizePolicyDomain(policyDomainId)
      if (!domain || !validatePolicyPayload(domain.id, payload)) return fallback
      const registration = policyHandlers.get(domain.id)
      if (!registration || registration.abiVersion !== domain.abiVersion) return fallback

      const result = registration.handler(fallback, ...payload)
      if (thenableStatus(result)) {
        Promise.resolve(result).catch(() => undefined)
        policyHealth.set(domain.id, (policyHealth.get(domain.id) ?? 0) + 1)
        return fallback
      }
      if (result === undefined) {
        policyHealth.set(domain.id, (policyHealth.get(domain.id) ?? 0) + 1)
        return fallback
      }
      if (!validatePolicyResult(domain.id, result)) {
        policyHealth.set(domain.id, (policyHealth.get(domain.id) ?? 0) + 1)
        return fallback
      }
      return result
    } catch {
      const domain = normalizePolicyDomain(policyDomainId)
      if (domain) policyHealth.set(domain.id, (policyHealth.get(domain.id) ?? 0) + 1)
      return fallback
    }
  }

  function validCapturePayload(domain, generation, presenceBitmap, slotsOrNull) {
    if (!isSafeGeneration(generation) || !Number.isSafeInteger(presenceBitmap)) return false
    if (presenceBitmap < 0 || presenceBitmap >= 2 ** domain.slotCount) return false
    if (slotsOrNull === null) return presenceBitmap === 0
    if (!Array.isArray(slotsOrNull) || slotsOrNull.length > domain.slotCount) return false
    for (let index = 0; index < domain.slotCount; index += 1) {
      if (bitmapHas(presenceBitmap, index) && !(index in slotsOrNull)) return false
    }
    return true
  }

  function capturesIdentical(current, presenceBitmap, slots) {
    if (current.presenceBitmap !== presenceBitmap) return false
    for (let index = 0; index < current.domain.slotCount; index += 1) {
      if (bitmapHas(presenceBitmap, index) && current.slots[index] !== slots[index]) return false
    }
    return true
  }

  function capturePublish(captureDomainId, generation, presenceBitmap, slotsOrNull) {
    try {
      if (!bridgeFacadeActive) return undefined
      const domain = normalizeCaptureDomain(captureDomainId)
      if (!domain || !validCapturePayload(domain, generation, presenceBitmap, slotsOrNull)) {
        return undefined
      }

      const current = captures.get(domain.id)
      if (slotsOrNull === null) {
        if (current?.generation === generation) {
          captures.delete(domain.id)
          notifyCapture(domain.id, "clear")
        }
        return undefined
      }

      if (domain.lifecycle === "static" && generation !== 0) return undefined
      if (current) {
        if (domain.lifecycle === "static") {
          if (capturesIdentical(current, presenceBitmap, slotsOrNull)) return undefined
          return undefined
        }
        if (generation < current.generation) return undefined
        if (generation === current.generation) {
          if (capturesIdentical(current, presenceBitmap, slotsOrNull)) return undefined
          return undefined
        }
      }

      const slots = new Array(domain.slotCount)
      for (let index = 0; index < domain.slotCount; index += 1) {
        if (bitmapHas(presenceBitmap, index)) slots[index] = slotsOrNull[index]
      }
      captures.set(domain.id, {
        domain,
        generation,
        presenceBitmap,
        slots,
      })
      notifyCapture(domain.id, current ? "replace" : "publish")
    } catch {
      // Bridge capture is deliberately total and ignored by its binary callers.
    }
    return undefined
  }

  const bridgeFacade = Object.freeze({ q: policyQuery, c: capturePublish })

  function captureMetadata(input) {
    const domain = normalizeCaptureDomain(input)
    if (!domain) return null
    const capture = captures.get(domain.id)
    return deepFreeze({
      id: domain.id,
      compactId: domain.compactId,
      name: domain.name,
      abiVersion: domain.abiVersion,
      lifecycle: domain.lifecycle,
      available: Boolean(capture),
      generation: capture?.generation ?? null,
      presenceBitmap: capture?.presenceBitmap ?? 0,
      presentSlotCount: capture
        ? Array.from({ length: domain.slotCount }, (_, index) => index).filter((index) =>
            bitmapHas(capture.presenceBitmap, index),
          ).length
        : 0,
      slotCount: domain.slotCount,
    })
  }

  function status() {
    return deepFreeze({
      registryApiVersion: 1,
      runtimeApiVersion: 2,
      policyApiVersion: RELEASE.policyApiVersion,
      bridgeAbi: RELEASE.bridgeAbi,
      bridgeBuildId: RELEASE.bridgeBuildId,
      rawSlotApi: RELEASE.rawSlotApi,
      target: {
        expectedVersion: RELEASE.targetVersion,
        selectedVersion: bridgeTargetVersionInput ?? exactTargetVersion(),
        exactVersion:
          (bridgeTargetVersionInput ?? exactTargetVersion()) === RELEASE.targetVersion,
        verificationMode: targetVerificationMode(),
        artifactVerified: targetVerificationMode() === "signed-bridge-artifact",
        bridgeMetadataPresent:
          bridgeBuildInput !== null ||
          bridgeArtifactShaInput !== null ||
          bridgeTargetVersionInput !== null,
      },
      bridgeFacade: {
        active: bridgeFacadeActive,
        collision: bridgeFacadeCollision,
      },
      policyDomains: POLICY_DOMAINS.map((domain) => ({
        id: domain.id,
        name: domain.name,
        abiVersion: domain.abiVersion,
        active: policyHandlers.has(domain.id),
        owner: policyHandlers.get(domain.id)?.extensionId ?? null,
        rejectedResultCount: policyHealth.get(domain.id) ?? 0,
      })),
      captures: CAPTURE_DOMAINS.map((domain) => captureMetadata(domain.id)),
      extensions: [...extensions.values()].map((extension) => ({
        id: extension.id,
        version: extension.version,
        unsafeEnabled: extension.unsafeEnabled,
        policyDomainIds: [...extension.policyDomainIds],
      })),
    })
  }

  function safeText(value, maximum = 160) {
    if (typeof value !== "string") return null
    return value.replace(/[ -]/g, " ").slice(0, maximum)
  }

  function unavailable(reason, generation = null) {
    return deepFreeze({ available: false, reason, generation })
  }

  function available(generation, value) {
    return deepFreeze({ available: true, generation, value })
  }

  function currentCapture(domainId, expectedGeneration = null) {
    const capture = captures.get(domainId)
    if (!capture) return null
    if (expectedGeneration !== null && capture.generation !== expectedGeneration) return null
    return capture
  }

  function captureSlot(capture, index) {
    return bitmapHas(capture.presenceBitmap, index) ? capture.slots[index] : undefined
  }

  function callCaptured(capture, index, args = []) {
    const handler = captureSlot(capture, index)
    if (typeof handler !== "function") return { ok: false, reason: "unavailable" }
    try {
      const value = handler(...args)
      if (thenableStatus(value)) {
        Promise.resolve(value).catch(() => undefined)
        return { ok: false, reason: "async-result" }
      }
      return { ok: true, value }
    } catch {
      return { ok: false, reason: "failed" }
    }
  }

  function scalarFields(value, names) {
    if (!value || typeof value !== "object") return {}
    const fields = {}
    for (const name of names) {
      try {
        const child = value[name]
        if (typeof child === "boolean" || (typeof child === "number" && Number.isFinite(child))) {
          fields[name] = child
        } else if (typeof child === "string") {
          fields[name] = safeText(child)
        }
      } catch {
        // Accessors are omitted from safe summaries.
      }
    }
    return fields
  }

  function objectSummary(value, scalarNames = []) {
    if (value === null) return { type: "null", keys: [], fields: {} }
    if (Array.isArray(value)) return { type: "array", count: value.length, keys: [], fields: {} }
    if (value instanceof Map) return { type: "map", count: value.size, keys: [], fields: {} }
    if (value instanceof Set) return { type: "set", count: value.size, keys: [], fields: {} }
    if (typeof value !== "object") {
      return { type: typeof value, keys: [], fields: {} }
    }
    let keys = []
    try {
      keys = Object.keys(value).filter((key) => !/(prompt|content|message|token|secret)/i.test(key)).slice(0, 32)
    } catch {
      // Proxies and throwing getters collapse to type-only metadata.
    }
    return {
      type: "object",
      keys,
      fields: scalarFields(value, scalarNames),
    }
  }

  function catalogEntries(value, maximum = 100) {
    let entries
    if (Array.isArray(value)) entries = value
    else if (value instanceof Map) entries = [...value.values()]
    else if (value && typeof value === "object") entries = Object.values(value)
    else return []
    return entries.slice(0, maximum).map((entry, index) => ({
      index,
      ...objectSummary(entry, ["id", "name", "type", "category", "key", "description"]),
    }))
  }

  function countStrings(value, needle, budget = { remaining: 4096 }) {
    if (budget.remaining <= 0) return 0
    budget.remaining -= 1
    if (typeof value === "string") {
      const lowered = value.toLowerCase()
      let count = 0
      let offset = 0
      while ((offset = lowered.indexOf(needle, offset)) !== -1 && count < 100) {
        count += 1
        offset += Math.max(needle.length, 1)
      }
      return count
    }
    if (!value || typeof value !== "object") return 0
    let children
    try {
      children = Array.isArray(value) ? value.slice(0, 64) : Object.values(value).slice(0, 64)
    } catch {
      return 0
    }
    return children.reduce((count, child) => count + countStrings(child, needle, budget), 0)
  }

  function stringBytes(value, budget = { remaining: 4096 }) {
    if (budget.remaining <= 0) return 0
    budget.remaining -= 1
    if (typeof value === "string") return value.length
    if (!value || typeof value !== "object") return 0
    let children
    try {
      children = Array.isArray(value) ? value.slice(0, 64) : Object.values(value).slice(0, 64)
    } catch {
      return 0
    }
    return children.reduce((count, child) => count + stringBytes(child, budget), 0)
  }

  function messageSummary(message, index) {
    const summary = objectSummary(message, ["type", "role", "subtype", "status"])
    return {
      index,
      ...summary,
      textBytes: stringBytes(message, { remaining: 256 }),
    }
  }

  function messageSnapshot(expectedGeneration = null) {
    const capture = currentCapture(3, expectedGeneration)
    if (!capture) return null
    const arrayLength = (index) => {
      const value = captureSlot(capture, index)
      return Array.isArray(value) ? value.length : null
    }
    const primitive = (index, type) => {
      const value = captureSlot(capture, index)
      return typeof value === type ? value : null
    }
    return deepFreeze({
      generation: capture.generation,
      counts: {
        raw: arrayLength(0),
        normalized: arrayLength(1),
        collapsed: arrayLength(2),
        postToolStats: arrayLength(3),
        rendered: arrayLength(4),
      },
      preNormalizationCapStart: primitive(5, "number"),
      hasTruncatedMessages: primitive(8, "boolean"),
      hiddenMessageCount: primitive(9, "number"),
      virtualScrollActive: primitive(10, "boolean"),
      effectiveCapRows: primitive(11, "number"),
      screen: primitive(12, "string"),
      showAllInTranscript: primitive(13, "boolean"),
      disableRenderCap: primitive(14, "boolean"),
    })
  }

  function messageExport(request = {}) {
    if (!request || typeof request !== "object" || Array.isArray(request)) {
      return unavailable("invalid")
    }
    const generation = request.generation ?? null
    const capture = currentCapture(3, generation)
    if (!capture) return unavailable(generation === null ? "unavailable" : "stale", generation)
    const stage = request.stage ?? "rendered"
    const stageSlots = { raw: 0, normalized: 1, collapsed: 2, postToolStats: 3, rendered: 4 }
    if (!(stage in stageSlots)) return unavailable("invalid-stage", capture.generation)
    const limit = request.limit ?? 50
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
      return unavailable("invalid-limit", capture.generation)
    }
    const messages = captureSlot(capture, stageSlots[stage])
    if (!Array.isArray(messages)) return unavailable("unavailable", capture.generation)
    return available(capture.generation, {
      stage,
      total: messages.length,
      summaries: messages.slice(0, limit).map(messageSummary),
    })
  }

  function messageSearch(request = {}) {
    if (!request || typeof request !== "object" || Array.isArray(request)) {
      return unavailable("invalid")
    }
    const query = safeText(request.query, 256)
    if (!query || query.length < 2) return unavailable("invalid-query")
    const generation = request.generation ?? null
    const capture = currentCapture(3, generation)
    if (!capture) return unavailable(generation === null ? "unavailable" : "stale", generation)
    const messages = captureSlot(capture, 4)
    if (!Array.isArray(messages)) return unavailable("unavailable", capture.generation)
    const needle = query.toLowerCase()
    const matches = []
    messages.slice(0, 1000).forEach((message, index) => {
      const occurrences = countStrings(message, needle)
      if (occurrences > 0 && matches.length < 100) matches.push({ index, occurrences })
    })
    return available(capture.generation, { totalMessages: messages.length, matches })
  }

  function replSnapshot(expectedGeneration = null) {
    const capture = currentCapture(4, expectedGeneration)
    if (!capture) return null
    const primitive = (index, type) => {
      const value = captureSlot(capture, index)
      return typeof value === type ? value : null
    }
    return deepFreeze({
      generation: capture.generation,
      currentView: objectSummary(captureSlot(capture, 2), ["id", "name", "type", "status"]),
      screen: primitive(3, "string"),
      showAllInTranscript: primitive(5, "boolean"),
      disableRenderCap: primitive(7, "boolean"),
    })
  }

  function replCatalogs(expectedGeneration = null) {
    const capture = currentCapture(4, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    return available(capture.generation, {
      commands: catalogEntries(captureSlot(capture, 9)),
      tools: catalogEntries(captureSlot(capture, 11)),
      agents: catalogEntries(captureSlot(capture, 12)),
    })
  }

  function modelCanonicalize(model, expectedGeneration = null) {
    if (!isNonEmptyString(model) || model.length > 256) return unavailable("invalid")
    const capture = currentCapture(0, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const result = callCaptured(capture, 1, [model])
    if (!result.ok || typeof result.value !== "string") return unavailable(result.reason, capture.generation)
    return available(capture.generation, safeText(result.value, 256))
  }

  function modelCatalog(model, expectedGeneration = null) {
    if (!isNonEmptyString(model) || model.length > 256) return unavailable("invalid")
    const capture = currentCapture(0, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const result = callCaptured(capture, 5, [model])
    if (!result.ok) return unavailable(result.reason, capture.generation)
    return available(capture.generation, objectSummary(result.value, ["id", "name", "provider", "family"] ))
  }

  function modelProvider(model, expectedGeneration = null) {
    if (!isNonEmptyString(model) || model.length > 256) return unavailable("invalid")
    const capture = currentCapture(0, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const result = callCaptured(capture, 4, [model])
    if (!result.ok) return unavailable(result.reason, capture.generation)
    if (typeof result.value === "string") return available(capture.generation, safeText(result.value))
    return available(capture.generation, objectSummary(result.value, ["id", "name", "provider"] ))
  }

  function modelWindowPreview(model, expectedGeneration = null) {
    if (!isNonEmptyString(model) || model.length > 256) return unavailable("invalid")
    const capture = currentCapture(0, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const canonical = callCaptured(capture, 1, [model])
    const canonicalModel = canonical.ok && typeof canonical.value === "string" ? canonical.value : model
    const window = callCaptured(capture, 6, [canonicalModel])
    if (!window.ok || !Number.isSafeInteger(window.value) || window.value < 1) {
      return unavailable(window.reason ?? "invalid-result", capture.generation)
    }
    return available(capture.generation, {
      canonicalModel: safeText(canonicalModel, 256),
      contextWindow: window.value,
    })
  }

  function routePreview(requestedModel, parentModel, expectedGeneration = null) {
    if (!isNonEmptyString(requestedModel) || !isNonEmptyString(parentModel)) {
      return unavailable("invalid")
    }
    const capture = currentCapture(0, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const canonical = callCaptured(capture, 1, [requestedModel])
    const sameFamily = callCaptured(capture, 18, [requestedModel, parentModel])
    const requestedFamily = callCaptured(capture, 20, [requestedModel])
    const parentFamily = callCaptured(capture, 20, [parentModel])
    return available(capture.generation, {
      requestedModel: safeText(requestedModel, 256),
      parentModel: safeText(parentModel, 256),
      canonicalRequested:
        canonical.ok && typeof canonical.value === "string" ? safeText(canonical.value, 256) : null,
      sameFamilyShortcut:
        sameFamily.ok && typeof sameFamily.value === "boolean" ? sameFamily.value : null,
      requestedFamily:
        requestedFamily.ok && typeof requestedFamily.value === "string"
          ? safeText(requestedFamily.value)
          : null,
      parentFamily:
        parentFamily.ok && typeof parentFamily.value === "string"
          ? safeText(parentFamily.value)
          : null,
    })
  }

  function appState(capture) {
    const direct = callCaptured(capture, 2)
    if (direct.ok && direct.value && typeof direct.value === "object") return direct.value
    const store = captureSlot(capture, 0)
    if (store && typeof store.getState === "function") {
      try {
        return store.getState()
      } catch {
        return null
      }
    }
    return null
  }

  function appMetadata(expectedGeneration = null) {
    const capture = currentCapture(2, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const state = appState(capture)
    if (!state || typeof state !== "object") return unavailable("unavailable", capture.generation)
    const counts = {}
    for (const name of ["tasks", "messages", "notifications", "mcpClients", "plugins", "open"]) {
      try {
        const value = state[name]
        if (Array.isArray(value)) counts[name] = value.length
        else if (value instanceof Map || value instanceof Set) counts[name] = value.size
      } catch {
        // Content-bearing or throwing fields are omitted.
      }
    }
    return available(capture.generation, {
      state: objectSummary(state, ["model", "permissionMode", "isLoading", "isCompact"]),
      counts,
    })
  }

  function resolveInkInstance(capture) {
    const registry = captureSlot(capture, 0)
    if (registry && typeof registry.get === "function") {
      try {
        return registry.get(process.stdout) ?? null
      } catch {
        return null
      }
    }
    const getter = captureSlot(capture, 10)
    if (typeof getter === "function") {
      try {
        return getter() ?? null
      } catch {
        return null
      }
    }
    return null
  }

  function inkMetadata(expectedGeneration = null) {
    const capture = currentCapture(1, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const instance = resolveInkInstance(capture)
    return available(capture.generation, {
      stdout: {
        columns: Number.isSafeInteger(process.stdout?.columns) ? process.stdout.columns : null,
        rows: Number.isSafeInteger(process.stdout?.rows) ? process.stdout.rows : null,
      },
      liveInstance: Boolean(instance),
      instance: objectSummary(instance, ["width", "height", "viewportWidth", "viewportHeight"]),
    })
  }

  function keyMetadata(expectedGeneration = null) {
    const capture = currentCapture(5, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    return available(capture.generation, {
      bindings: catalogEntries(captureSlot(capture, 1)),
      activeContexts: catalogEntries(captureSlot(capture, 5)),
      pendingChord: objectSummary(captureSlot(capture, 8), ["id", "key", "name"]),
    })
  }

  function diagnosticMetadata(expectedGeneration = null) {
    const capture = currentCapture(1, expectedGeneration)
    if (!capture) return unavailable(expectedGeneration === null ? "unavailable" : "stale")
    const path = captureSlot(capture, 17)
    return available(capture.generation, {
      debugMode: typeof captureSlot(capture, 18) === "boolean" ? captureSlot(capture, 18) : null,
      stderrMode: typeof captureSlot(capture, 19) === "boolean" ? captureSlot(capture, 19) : null,
      logFile: typeof path === "string" ? basename(path) : null,
      telemetryAvailable: typeof captureSlot(capture, 20) === "function",
    })
  }

  function observeCapture(input, callback) {
    const domain = normalizeCaptureDomain(input)
    if (!domain || typeof callback !== "function") throw new TypeError("Capture observer is invalid")
    const observers = captureObservers.get(domain.id)
    observers.add(callback)
    let active = true
    return () => {
      if (!active) return false
      active = false
      return observers.delete(callback)
    }
  }

  function notifyCapture(domainId, event) {
    const observers = captureObservers.get(domainId)
    if (!observers?.size) return
    const metadata = captureMetadata(domainId)
    queueMicrotask(() => {
      for (const observer of [...observers]) {
        try {
          observer(deepFreeze({ event, metadata }))
        } catch (error) {
          reportHookFailure(`capture:d${domainId}`, error)
        }
      }
    })
  }

  const messageRead = Object.freeze({
    counts: messageSnapshot,
    snapshot: messageExport,
  })
  const replRead = Object.assign((generation = null) => replSnapshot(generation), {
    state: replSnapshot,
    catalogs: replCatalogs,
  })
  Object.freeze(replRead)
  const readFacade = Object.freeze({
    status,
    captureMetadata,
    observe: observeCapture,
    mc: Object.freeze({
      catalog: modelCatalog,
      canonicalize: modelCanonicalize,
      provider: modelProvider,
      windowPreview: modelWindowPreview,
    }),
    sr: Object.freeze({ preview: routePreview, trace: routePreview }),
    msg: messageRead,
    messages: messageSnapshot,
    repl: replRead,
    app: Object.freeze({ metadata: appMetadata }),
    ink: Object.freeze({ frame: inkMetadata }),
    key: Object.freeze({ catalog: keyMetadata }),
    diag: Object.freeze({ status: diagnosticMetadata }),
  })

  function actionResult(ok, reason = null, generation = null, value = null) {
    return deepFreeze({ ok, reason, generation, value })
  }

  function validActionRequest(request) {
    return request && typeof request === "object" && !Array.isArray(request)
  }

  function replShowAll(request) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation) || typeof request.enabled !== "boolean") {
      return actionResult(false, "invalid")
    }
    const capture = currentCapture(4, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const setter = captureSlot(capture, 6)
    if (typeof setter !== "function") return actionResult(false, "unavailable", capture.generation)
    try {
      setter(request.enabled)
      return actionResult(true, null, capture.generation)
    } catch {
      return actionResult(false, "failed", capture.generation)
    }
  }

  function callNamedMethod(target, names, args = []) {
    if (!target || typeof target !== "object") return { ok: false, reason: "unavailable" }
    for (const name of names) {
      let method
      try {
        method = target[name]
      } catch {
        continue
      }
      if (typeof method !== "function") continue
      try {
        const value = method.apply(target, args)
        if (thenableStatus(value)) {
          Promise.resolve(value).catch(() => undefined)
          return { ok: false, reason: "async-result" }
        }
        return { ok: true, value }
      } catch {
        return { ok: false, reason: "failed" }
      }
    }
    return { ok: false, reason: "unsupported" }
  }

  function replToggle(request) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation)) {
      return actionResult(false, "invalid")
    }
    const capture = currentCapture(4, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const result = callNamedMethod(captureSlot(capture, 15), ["onToggleTranscript", "toggleTranscript"])
    return actionResult(result.ok, result.ok ? null : result.reason, capture.generation)
  }

  function replRedraw(request) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation)) {
      return actionResult(false, "invalid")
    }
    const capture = currentCapture(4, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const result = callNamedMethod(captureSlot(capture, 15), ["redraw", "invalidate", "repaint"])
    return actionResult(result.ok, result.ok ? null : result.reason, capture.generation)
  }

  function replDispatch(request) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation) || !isNonEmptyString(request.command)) {
      return actionResult(false, "invalid")
    }
    return actionResult(false, "denied", request.generation)
  }

  function appSubscribe(request, callback) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation) || typeof callback !== "function") {
      return actionResult(false, "invalid")
    }
    const capture = currentCapture(2, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const subscribe = captureSlot(capture, 4)
    if (typeof subscribe !== "function") return actionResult(false, "unavailable", capture.generation)
    try {
      const disposer = subscribe(() => {
        const current = currentCapture(2, capture.generation)
        if (!current) return
        try {
          callback(appMetadata(capture.generation))
        } catch (error) {
          reportHookFailure("app.subscribe", error)
        }
      })
      if (typeof disposer !== "function") return actionResult(false, "invalid-disposer", capture.generation)
      let active = true
      const safeDisposer = () => {
        if (!active) return false
        active = false
        try {
          disposer()
          return true
        } catch {
          return false
        }
      }
      return actionResult(true, null, capture.generation, safeDisposer)
    } catch {
      return actionResult(false, "failed", capture.generation)
    }
  }

  function inkAction(kind, request) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation)) {
      return actionResult(false, "invalid")
    }
    const capture = currentCapture(1, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const instance = resolveInkInstance(capture)
    const names = {
      redraw: ["redraw", "rerender"],
      invalidate: ["invalidate"],
      repaint: ["repaint", "rerender"],
    }[kind]
    const result = callNamedMethod(instance, names)
    return actionResult(result.ok, result.ok ? null : result.reason, capture.generation)
  }

  const SAFE_KEY_ACTIONS = new Set(["repl.toggleTranscript", "repl.showAll", "ink.redraw"])
  function keyInvoke(request) {
    if (
      !validActionRequest(request) ||
      !isSafeGeneration(request.generation) ||
      !isNonEmptyString(request.action) ||
      !SAFE_KEY_ACTIONS.has(request.action)
    ) {
      return actionResult(false, "denied")
    }
    const capture = currentCapture(5, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const result = callNamedMethod(captureSlot(capture, 0), ["invoke", "executeAction"], [request.action])
    return actionResult(result.ok, result.ok ? null : result.reason, capture.generation)
  }

  function keyRegister(request, handler) {
    if (
      !validActionRequest(request) ||
      !isSafeGeneration(request.generation) ||
      !isNonEmptyString(request.action) ||
      !SAFE_KEY_ACTIONS.has(request.action) ||
      typeof handler !== "function"
    ) {
      return actionResult(false, "denied")
    }
    const capture = currentCapture(5, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const result = callNamedMethod(captureSlot(capture, 0), ["registerAction", "register"], [request.action, handler])
    if (!result.ok || typeof result.value !== "function") {
      return actionResult(false, result.reason ?? "invalid-disposer", capture.generation)
    }
    let active = true
    const safeDisposer = () => {
      if (!active) return false
      active = false
      try {
        result.value()
        return true
      } catch {
        return false
      }
    }
    return actionResult(true, null, capture.generation, safeDisposer)
  }

  function diagnosticLog(request) {
    if (!validActionRequest(request) || !isSafeGeneration(request.generation)) {
      return actionResult(false, "invalid")
    }
    const message = safeText(request.message, 256)
    if (!message) return actionResult(false, "invalid")
    const capture = currentCapture(1, request.generation)
    if (!capture) return actionResult(false, "stale", request.generation)
    const logger = captureSlot(capture, 15)
    if (typeof logger !== "function") return actionResult(false, "unavailable", capture.generation)
    try {
      logger(`[renderpatch-extension] ${message}`)
      return actionResult(true, null, capture.generation)
    } catch {
      return actionResult(false, "failed", capture.generation)
    }
  }

  const actionFacade = Object.freeze({
    list() {
      return Object.freeze([
        "msg.search",
        "msg.export",
        "repl.redraw",
        "repl.toggle",
        "repl.showAll",
        "repl.dispatch",
        "app.subscribe",
        "ink.redraw",
        "ink.invalidate",
        "ink.repaint",
        "key.register",
        "key.invoke",
        "diag.log",
      ])
    },
    invoke(name, request) {
      if (name === "msg.search") return messageSearch(request)
      if (name === "msg.export") return messageExport(request)
      if (name === "repl.redraw") return replRedraw(request)
      if (name === "repl.toggle") return replToggle(request)
      if (name === "repl.showAll") return replShowAll(request)
      if (name === "repl.dispatch") return replDispatch(request)
      if (name === "ink.redraw") return inkAction("redraw", request)
      if (name === "ink.invalidate") return inkAction("invalidate", request)
      if (name === "ink.repaint") return inkAction("repaint", request)
      if (name === "key.invoke") return keyInvoke(request)
      if (name === "diag.log") return diagnosticLog(request)
      return actionResult(false, "unsupported")
    },
    msg: Object.freeze({ search: messageSearch, export: messageExport }),
    repl: Object.freeze({
      redraw: replRedraw,
      toggle: replToggle,
      showAll: replShowAll,
      dispatch: replDispatch,
    }),
    app: Object.freeze({ subscribe: appSubscribe }),
    ink: Object.freeze({
      redraw: (request) => inkAction("redraw", request),
      invalidate: (request) => inkAction("invalidate", request),
      repaint: (request) => inkAction("repaint", request),
    }),
    key: Object.freeze({ register: keyRegister, invoke: keyInvoke }),
    diag: Object.freeze({ log: diagnosticLog }),
  })

  function unsafeNegotiated(manifest) {
    if (manifest.unsafeRaw !== true || targetVerificationMode() !== "signed-bridge-artifact") {
      return false
    }
    const requirements = manifest.requires
    if (
      requirements.target?.bridgeBuildId !== RELEASE.bridgeBuildId ||
      requirements.bridgeAbi !== RELEASE.bridgeAbi ||
      requirements.rawSlotApi !== RELEASE.rawSlotApi ||
      requirements.target?.version !== RELEASE.targetVersion ||
      requirements.target?.stockSha256 !== RELEASE.targetStockSha256 ||
      typeof requirements.target?.artifactSha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(requirements.target.artifactSha256) ||
      actualTargetHash() !== requirements.target.artifactSha256 ||
      !Array.isArray(requirements.captureDomains)
    ) {
      return false
    }
    return requirements.captureDomains.every((requirement) => {
      const domain = normalizeCaptureDomain(requirement?.id)
      return domain !== null && requirement.abiVersion === domain.abiVersion
    })
  }

  function createUnsafeFacade(manifest) {
    const allowedDomains = new Set(
      manifest.requires.captureDomains.map((requirement) => normalizeCaptureDomain(requirement.id).id),
    )
    return Object.freeze({
      capture(input) {
        const domain = normalizeCaptureDomain(input)
        if (!domain || !allowedDomains.has(domain.id)) return null
        const capture = captures.get(domain.id)
        if (!capture) return null
        return Object.freeze({
          domainId: domain.id,
          generation: capture.generation,
          presenceBitmap: capture.presenceBitmap,
          slots: capture.slots,
        })
      },
    })
  }

  function validateExtensionManifest(manifest, policyEntries) {
    if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
      throw new TypeError("Extension manifest must be an object")
    }
    if (!isNonEmptyString(manifest.id) || !isNonEmptyString(manifest.version)) {
      throw new TypeError("Extension id and version must be non-empty strings")
    }
    if (manifest.schemaVersion !== RELEASE.extensionManifestSchema) {
      throw new TypeError("Unsupported extension manifest schema")
    }
    if (
      !manifest.requires ||
      manifest.requires.policyApiVersion !== RELEASE.policyApiVersion ||
      !Array.isArray(manifest.requires.bridges)
    ) {
      throw new TypeError("Extension requires policy API 2 and a bridges array")
    }
    if (extensions.has(manifest.id)) throw new Error(`Extension ${manifest.id} is already active`)

    const requirements = new Map()
    for (const requirement of manifest.requires.bridges) {
      const domain = normalizePolicyDomain(requirement?.id)
      if (!domain || requirement.abiVersion !== domain.abiVersion) {
        throw new TypeError("Extension requires an unknown or incompatible bridge")
      }
      if (requirements.has(domain.id)) throw new Error("Duplicate numeric/readable bridge alias")
      requirements.set(domain.id, domain)
    }

    const handlers = new Map()
    for (const entry of policyEntries) {
      const domain = normalizePolicyDomain(entry?.id)
      if (!domain || typeof entry.handler !== "function") {
        throw new TypeError("Every policy entry needs a known id and function handler")
      }
      if (entry.handler.constructor?.name === "AsyncFunction") {
        throw new TypeError(`Policy ${domain.name} must be synchronous`)
      }
      if (handlers.has(domain.id)) throw new Error("Duplicate numeric/readable policy alias")
      handlers.set(domain.id, entry.handler)
    }
    if (handlers.size !== requirements.size) {
      throw new Error("Policy handlers must exactly match required bridges")
    }
    for (const domainId of requirements.keys()) {
      if (!handlers.has(domainId)) throw new Error("Required bridge has no policy handler")
      if (policyHandlers.has(domainId)) throw new Error("Policy bridge is already owned")
    }

    const rendererCount = RENDERER_POLICY_IDS.filter((id) => requirements.has(id)).length
    if (rendererCount !== 0 && rendererCount !== RENDERER_POLICY_IDS.length) {
      throw new Error("Full-redraw policy registration must be atomic")
    }
    return { requirements, handlers }
  }

  function registerExtension(manifest, implementation = {}) {
    const policyEntries = implementation.policies ?? []
    if (!Array.isArray(policyEntries)) throw new TypeError("Extension policies must be an array")
    const { requirements, handlers } = validateExtensionManifest(manifest, policyEntries)
    const unsafeEnabled = unsafeNegotiated(manifest)
    const extension = {
      id: manifest.id,
      version: manifest.version,
      policyDomainIds: Object.freeze([...requirements.keys()]),
      unsafeEnabled,
    }
    extensions.set(extension.id, extension)
    for (const [domainId, handler] of handlers) {
      policyHandlers.set(domainId, {
        extensionId: extension.id,
        abiVersion: POLICY_DOMAINS[domainId].abiVersion,
        handler,
      })
    }

    let active = true
    const activation = {
      id: extension.id,
      read: readFacade,
      actions: actionFacade,
      dispose() {
        if (!active || extensions.get(extension.id) !== extension) return false
        active = false
        extensions.delete(extension.id)
        for (const domainId of extension.policyDomainIds) {
          if (policyHandlers.get(domainId)?.extensionId === extension.id) {
            policyHandlers.delete(domainId)
          }
        }
        return true
      },
    }
    if (unsafeEnabled) activation.unsafe = createUnsafeFacade(manifest)
    return Object.freeze(activation)
  }

  const runtime = {
    // apiVersion is the legacy registry API and intentionally remains 1.
    apiVersion: 1,
    runtimeApiVersion: 2,
    policyApiVersion: RELEASE.policyApiVersion,
    bridgeAbi: RELEASE.bridgeAbi,
    bridgeBuildId: RELEASE.bridgeBuildId,
    rawSlotApi: RELEASE.rawSlotApi,
    runtimeVersion: "0.3.0",
    process: processMetadata,
    bridge: bridgeFacade,
    read: readFacade,
    actions: actionFacade,
    registerExtension,
    register(name, handler) {
      if (!isNonEmptyString(name)) throw new TypeError("Hook name must be a non-empty string")
      if (typeof handler !== "function") throw new TypeError(`Hook ${name} must be a function`)
      legacyHooks.set(name, handler)
      return () => {
        if (legacyHooks.get(name) !== handler) return false
        return legacyHooks.delete(name)
      }
    },
    unregister(name) {
      return legacyHooks.delete(name)
    },
    invoke(name, payload) {
      const handler = legacyHooks.get(name)
      if (!handler) return undefined
      try {
        const result = handler(payload)
        if (thenableStatus(result)) {
          return Promise.resolve(result).catch((error) => reportHookFailure(name, error))
        }
        return result
      } catch (error) {
        return reportHookFailure(name, error)
      }
    },
    listHooks() {
      return [...legacyHooks.keys()]
    },
  }

  return {
    runtime: Object.freeze(runtime),
    bridgeFacade,
    activateBridgeFacade() {
      bridgeFacadeActive = true
    },
    markBridgeCollision() {
      bridgeFacadeCollision = true
    },
  }
}

let runtimeState = null
const existingRuntime = globalThis[runtimeKey]
if (existingRuntime === undefined) {
  runtimeState = createRuntime()
  Object.defineProperty(globalThis, runtimeKey, {
    value: runtimeState.runtime,
    configurable: false,
    enumerable: false,
    writable: false,
  })
} else if (
  typeof existingRuntime !== "object" ||
  existingRuntime === null ||
  existingRuntime.apiVersion !== 1 ||
  existingRuntime.runtimeApiVersion !== 2 ||
  existingRuntime.policyApiVersion !== RELEASE.policyApiVersion ||
  existingRuntime.bridgeAbi !== RELEASE.bridgeAbi
) {
  report("global runtime symbol already contains an incompatible value; extensions disabled")
}

const runtime = runtimeState?.runtime ?? existingRuntime
if (runtimeState) {
  const aliasDescriptor = Object.getOwnPropertyDescriptor(globalThis, "__rp")
  if (aliasDescriptor === undefined) {
    Object.defineProperty(globalThis, "__rp", {
      value: runtimeState.bridgeFacade,
      configurable: false,
      enumerable: false,
      writable: false,
    })
    if (selectedTargetCompatible()) runtimeState.activateBridgeFacade()
  } else if (
    aliasDescriptor.value === runtimeState.bridgeFacade &&
    aliasDescriptor.configurable === false &&
    aliasDescriptor.enumerable === false &&
    aliasDescriptor.writable === false
  ) {
    if (selectedTargetCompatible()) runtimeState.activateBridgeFacade()
  } else {
    runtimeState.markBridgeCollision()
    report("globalThis.__rp already contains an incompatible value; bridge facade disabled")
  }
}

async function resolveTrustedModule(
  input,
  environmentName = "CLAUDE_RENDERPATCH_MODULE",
  label = "External module",
) {
  const { homedir } = await import("node:os")
  const path = await import("node:path")
  const fs = await import("node:fs/promises")

  if (!path.isAbsolute(input)) {
    throw new Error(`${environmentName} must be absolute: ${input}`)
  }

  const unresolved = path.resolve(input)
  const root = path.parse(unresolved).root
  let unresolvedComponent = root
  for (const part of unresolved.slice(root.length).split(path.sep).filter(Boolean)) {
    unresolvedComponent = path.join(unresolvedComponent, part)
    if ((await fs.lstat(unresolvedComponent)).isSymbolicLink()) {
      throw new Error(`${label} path component must not be a symlink: ${unresolvedComponent}`)
    }
  }

  const resolved = await fs.realpath(unresolved)
  const home = await fs.realpath(homedir())
  if (resolved !== home && !resolved.startsWith(`${home}${path.sep}`)) {
    throw new Error(`${label} must live under the current user's home: ${resolved}`)
  }

  const uid = typeof process.getuid === "function" ? process.getuid() : null
  let current = resolved
  while (true) {
    const info = await fs.stat(current)
    if (uid !== null && info.uid !== uid) {
      throw new Error(`${label} path component is not user-owned: ${current}`)
    }
    if ((info.mode & 0o022) !== 0) {
      throw new Error(`${label} path component is group/world writable: ${current}`)
    }
    if (current === home) break
    current = path.dirname(current)
  }

  if (!(await fs.stat(resolved)).isFile()) {
    throw new Error(`${label} is not a regular file: ${resolved}`)
  }

  return resolved
}

async function loadTrustedExtension(input, environmentName, label, reportLabel) {
  try {
    const { pathToFileURL } = await import("node:url")
    const modulePath = await resolveTrustedModule(input, environmentName, label)
    const loaded = await import(pathToFileURL(modulePath).href)
    const activate = typeof loaded.activate === "function" ? loaded.activate : loaded.default
    if (typeof activate === "function") await activate(runtime)
  } catch (error) {
    // Thrown or rejected imports are reported and skipped. Same-realm code can still
    // intentionally exit, hang, or leave partial mutations; use the safe launcher then.
    report(`${reportLabel} was skipped: ${error?.stack ?? error}`)
  }
}

if (runtime?.apiVersion === 1 && runtime?.runtimeApiVersion === 2) {
  if (externalModuleInput) {
    await loadTrustedExtension(
      externalModuleInput,
      "CLAUDE_RENDERPATCH_MODULE",
      "External module",
      "external module",
    )
  }
  if (userModuleInput) {
    await loadTrustedExtension(
      userModuleInput,
      "CLAUDE_RENDERPATCH_USER_MODULE",
      "User module",
      "user module",
    )
  }
}
