const manifest = Object.freeze({
  id: "example-app-subscribe",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: false,
  requires: Object.freeze({ policyApiVersion: 2, bridges: Object.freeze([]) }),
})

export function activate(runtime) {
  const activation = runtime.registerExtension(manifest)
  const capture = activation.read.captureMetadata("d2")
  if (!capture?.available) {
    process.stderr.write("[example-app-subscribe] app capture unavailable\n")
    return
  }

  const subscription = activation.actions.app.subscribe(
    { generation: capture.generation },
    (metadata) => {
      const tasks = metadata.available ? metadata.value.counts.tasks ?? 0 : 0
      process.stderr.write(`[example-app-subscribe] tasks=${tasks}\n`)
    },
  )

  runtime.register("example-app-subscribe:dispose", () => {
    const subscriptionRemoved = subscription.ok ? subscription.value() : false
    const extensionRemoved = activation.dispose()
    return subscriptionRemoved || extensionRemoved
  })
}
