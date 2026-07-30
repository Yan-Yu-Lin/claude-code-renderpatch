import { MIX_WINDOW_BRIDGES, MIX_WINDOW_POLICIES, manifest as makeManifest } from "./_shared.mjs"

export const manifest = makeManifest("mix-window", MIX_WINDOW_BRIDGES)

export function activate(runtime) {
  return runtime.registerExtension(manifest, { policies: MIX_WINDOW_POLICIES })
}

export default activate
