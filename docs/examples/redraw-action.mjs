const manifest = Object.freeze({
  id: "example-redraw-action",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: false,
  requires: Object.freeze({
    policyApiVersion: 2,
    bridges: Object.freeze([]),
  }),
})

export function activate(runtime) {
  const activation = runtime.registerExtension(manifest)
  let stopObserving = null

  const redraw = (metadata) => {
    if (!metadata?.available) return false

    const result = activation.actions.ink.redraw({
      generation: metadata.generation,
    })
    process.stderr.write(
      `[example-redraw-action] ok=${result.ok} reason=${result.reason ?? "none"}\n`,
    )
    return result.ok
  }

  const current = activation.read.captureMetadata("d1")
  if (!redraw(current)) {
    stopObserving = activation.read.observe("d1", ({ event, metadata }) => {
      if (event === "clear" || !redraw(metadata)) return
      stopObserving?.()
      stopObserving = null
    })
  }

  runtime.register("example-redraw-action:dispose", () => {
    const observerRemoved = stopObserving?.() ?? false
    stopObserving = null
    const extensionRemoved = activation.dispose()
    return observerRemoved || extensionRemoved
  })
}
