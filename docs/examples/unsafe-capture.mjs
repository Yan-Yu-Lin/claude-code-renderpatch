const manifest = Object.freeze({
  id: "example-unsafe-capture",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: true,
  requires: Object.freeze({
    policyApiVersion: 2,
    bridges: Object.freeze([]),
    bridgeAbi: 1,
    rawSlotApi: "2.1.220.1",
    target: Object.freeze({
      version: "2.1.220",
      bridgeBuildId: "internal-sdk-2.1.220.1",
      stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      artifactSha256: "97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157",
    }),
    captureDomains: Object.freeze([{ id: "d3", abiVersion: 1 }]),
  }),
})

export function activate(runtime) {
  const activation = runtime.registerExtension(manifest)
  if (!activation.unsafe) {
    process.stderr.write("[example-unsafe-capture] exact-artifact negotiation denied\n")
    return
  }

  const capture = activation.unsafe.capture("d3")
  process.stderr.write(
    capture
      ? `[example-unsafe-capture] generation=${capture.generation} bitmap=${capture.presenceBitmap}\n`
      : "[example-unsafe-capture] capture unavailable\n",
  )

  // Do not log, serialize, retain, or network-expose capture.slots.
}
