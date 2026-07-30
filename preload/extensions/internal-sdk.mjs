import {
  FULL_REDRAW_BRIDGES,
  FULL_REDRAW_POLICIES,
  MIX_WINDOW_BRIDGES,
  MIX_WINDOW_POLICIES,
  SUBAGENT_ROUTING_BRIDGES,
  SUBAGENT_ROUTING_POLICIES,
  manifest as makeManifest,
} from "./_shared.mjs"

export const manifest = makeManifest(
  "internal-sdk",
  Object.freeze([
    ...FULL_REDRAW_BRIDGES,
    ...MIX_WINDOW_BRIDGES,
    ...SUBAGENT_ROUTING_BRIDGES,
  ]),
)

const policies = Object.freeze([
  ...FULL_REDRAW_POLICIES,
  ...MIX_WINDOW_POLICIES,
  ...SUBAGENT_ROUTING_POLICIES,
])

export function activate(runtime) {
  return runtime.registerExtension(manifest, { policies })
}

export default activate
