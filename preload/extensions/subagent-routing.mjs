import {
  SUBAGENT_ROUTING_BRIDGES,
  SUBAGENT_ROUTING_POLICIES,
  manifest as makeManifest,
} from "./_shared.mjs"

export const manifest = makeManifest("subagent-routing", SUBAGENT_ROUTING_BRIDGES)

export function activate(runtime) {
  return runtime.registerExtension(manifest, { policies: SUBAGENT_ROUTING_POLICIES })
}

export default activate
