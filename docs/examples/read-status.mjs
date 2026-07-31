const manifest = Object.freeze({
  id: "example-read-status",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: false,
  requires: Object.freeze({
    policyApiVersion: 2,
    bridges: Object.freeze([]),
  }),
})

export function activate(runtime) {
  if (runtime.runtimeApiVersion !== 2) {
    throw new Error(`Unsupported runtime API ${runtime.runtimeApiVersion}`)
  }

  const activation = runtime.registerExtension(manifest)
  const status = activation.read.status()

  process.stderr.write(
    `[example-read-status] target=${status.target.selectedVersion ?? "unknown"} ` +
      `bridge=${status.bridgeFacade.active ? "active" : "inactive"} ` +
      `captures=${status.captures.filter((capture) => capture.available).length}\n`,
  )
}
