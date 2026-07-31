const manifest = Object.freeze({
  id: "example-observe-repl",
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
  const stopObserving = activation.read.observe("d4", ({ event, metadata }) => {
    if (event === "clear" || !metadata.available) return

    const state = activation.read.repl.state(metadata.generation)
    if (!state) return

    process.stderr.write(
      `[example-observe-repl] event=${event} generation=${state.generation} ` +
        `screen=${state.screen ?? "unknown"}\n`,
    )
  })

  runtime.register("example-observe-repl:dispose", () => {
    const observerRemoved = stopObserving()
    const extensionRemoved = activation.dispose()
    return observerRemoved || extensionRemoved
  })
}
