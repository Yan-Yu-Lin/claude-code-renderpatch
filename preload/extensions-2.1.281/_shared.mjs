export const SCHEMA_VERSION = 1
export const POLICY_API_VERSION = 2

export const FULL_REDRAW_BRIDGES = Object.freeze([
  Object.freeze({ id: "renderer.messages", abiVersion: 1 }),
  Object.freeze({ id: "renderer.reset", abiVersion: 1 }),
  Object.freeze({ id: "renderer.toggleRedraw", abiVersion: 1 }),
])
export const MIX_WINDOW_BRIDGES = Object.freeze([
  Object.freeze({ id: "provider.contextWindow", abiVersion: 1 }),
])
export const SUBAGENT_ROUTING_BRIDGES = Object.freeze([
  Object.freeze({ id: "subagent.explicitModelRouting", abiVersion: 1 }),
])

export function rendererMessages(_fallback, screen) {
  return 2 | (screen === "transcript" ? 1 : 0)
}

export function rendererReset(_fallback, _reason, altScreen) {
  return !altScreen
}

export function rendererToggleRedraw() {
  // Enter and exit both need one authoritative replay after the screen changes.
  return true
}

export function providerContextWindow(fallback, canonicalModel) {
  if (canonicalModel.startsWith("kimi")) return 262144
  if (canonicalModel.startsWith("claude-")) return fallback
  return 372000
}

export function explicitModelRouting() {
  return false
}

export const FULL_REDRAW_POLICIES = Object.freeze([
  Object.freeze({ id: "renderer.messages", handler: rendererMessages }),
  Object.freeze({ id: "renderer.reset", handler: rendererReset }),
  Object.freeze({ id: "renderer.toggleRedraw", handler: rendererToggleRedraw }),
])
export const MIX_WINDOW_POLICIES = Object.freeze([
  Object.freeze({ id: "provider.contextWindow", handler: providerContextWindow }),
])
export const SUBAGENT_ROUTING_POLICIES = Object.freeze([
  Object.freeze({ id: "subagent.explicitModelRouting", handler: explicitModelRouting }),
])

export function manifest(id, bridges) {
  return Object.freeze({
    id,
    version: "1.0.0",
    schemaVersion: SCHEMA_VERSION,
    unsafeRaw: false,
    requires: Object.freeze({
      policyApiVersion: POLICY_API_VERSION,
      bridges,
    }),
  })
}
