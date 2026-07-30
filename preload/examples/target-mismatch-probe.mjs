const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]
const activation = runtime.registerExtension(
  {
    id: "target-mismatch-probe",
    version: "1.0.0",
    schemaVersion: 1,
    requires: {
      policyApiVersion: 2,
      bridges: [{ id: 3, abiVersion: 1 }],
    },
  },
  { policies: [{ id: 3, handler: () => 372000 }] },
)

globalThis.__rp.c(3, 1, 1, [["must-not-publish"]])
console.log(
  "TARGET_MISMATCH",
  JSON.stringify({
    fallback: globalThis.__rp.q(3, 91, "gpt-test"),
    captureAvailable: runtime.read.captureMetadata(3).available,
    bridgeActive: runtime.read.status().bridgeFacade.active,
    exactVersion: runtime.read.status().target.exactVersion,
    verificationMode: runtime.read.status().target.verificationMode,
    artifactVerified: runtime.read.status().target.artifactVerified,
    bridgeMetadataPresent: runtime.read.status().target.bridgeMetadataPresent,
  }),
)
activation.dispose()
