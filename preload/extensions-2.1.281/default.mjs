import {
  FULL_REDRAW_BRIDGES,
  FULL_REDRAW_POLICIES,
  SUBAGENT_ROUTING_BRIDGES,
  SUBAGENT_ROUTING_POLICIES,
  manifest as makeManifest,
} from "./_shared.mjs"

// 2.1.281 bridge: renderer + explicit subagent routing. The provider context
// window policy was retired; the settings overlay supplies
// CLAUDE_CODE_MAX_CONTEXT_TOKENS and no 2.1.281 site queries domain 3.
export const manifest = makeManifest(
  "default",
  Object.freeze([...FULL_REDRAW_BRIDGES, ...SUBAGENT_ROUTING_BRIDGES]),
)

const policies = Object.freeze([...FULL_REDRAW_POLICIES, ...SUBAGENT_ROUTING_POLICIES])

export function activate(runtime) {
  return runtime.registerExtension(manifest, { policies })
}

export default activate
