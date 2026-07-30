import { FULL_REDRAW_BRIDGES, FULL_REDRAW_POLICIES, manifest as makeManifest } from "./_shared.mjs"

export const manifest = makeManifest("full-redraw", FULL_REDRAW_BRIDGES)

export function activate(runtime) {
  return runtime.registerExtension(manifest, { policies: FULL_REDRAW_POLICIES })
}

export default activate
