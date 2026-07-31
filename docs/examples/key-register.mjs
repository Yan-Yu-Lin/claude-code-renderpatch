const manifest = Object.freeze({
  id: "example-key-register",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: false,
  requires: Object.freeze({ policyApiVersion: 2, bridges: Object.freeze([]) }),
})

export function activate(runtime) {
  const activation = runtime.registerExtension(manifest)
  const capture = activation.read.captureMetadata("d5")
  if (!capture?.available) {
    process.stderr.write("[example-key-register] key capture unavailable\n")
    return
  }

  const registration = activation.actions.key.register(
    { generation: capture.generation, action: "ink.redraw" },
    () => process.stderr.write("[example-key-register] ink.redraw invoked\n"),
  )

  runtime.register("example-key-register:dispose", () => {
    const handlerRemoved = registration.ok ? registration.value() : false
    const extensionRemoved = activation.dispose()
    return handlerRemoved || extensionRemoved
  })
}
