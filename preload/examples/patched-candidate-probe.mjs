import { activate as activateDefault } from "../extensions/default.mjs"

const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]
const alias = globalThis.__rp
const defaultActivation = activateDefault(runtime)
const unsafeDeniedActivation = runtime.registerExtension(
  {
    id: "patched-candidate-unsafe-denied-probe",
    version: "1.0.0",
    schemaVersion: 1,
    unsafeRaw: true,
    requires: {
      policyApiVersion: 2,
      bridges: [],
      bridgeAbi: 1,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [{ id: "d3", abiVersion: 1 }],
    },
  },
)
const unsafeActivation = runtime.registerExtension(
  {
    id: "patched-candidate-probe",
    version: "1.0.0",
    schemaVersion: 1,
    unsafeRaw: true,
    requires: {
      policyApiVersion: 2,
      bridges: [],
      bridgeAbi: 1,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157",
      },
      captureDomains: [{ id: "d3", abiVersion: 1 }],
    },
  },
)

const slots = []
slots[8] = true
alias.c(3, 91, 2 ** 8, slots)
const status = runtime.read.status()
console.log(
  "PATCHED_CANDIDATE",
  JSON.stringify({
    query: alias.q(3, 1, "gpt-5.6"),
    captureGeneration: runtime.read.captureMetadata(3).generation,
    unsafeArtifactMismatchDenied: !("unsafe" in unsafeDeniedActivation),
    unsafeEnabled: "unsafe" in unsafeActivation,
    unsafeGeneration: unsafeActivation.unsafe?.capture(3)?.generation ?? null,
    bridgeActive: status.bridgeFacade.active,
    verificationMode: status.target.verificationMode,
    artifactVerified: status.target.artifactVerified,
    bridgeMetadataPresent: status.target.bridgeMetadataPresent,
    buildEnvPresent: "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID" in process.env,
    shaEnvPresent: "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256" in process.env,
    versionEnvPresent: "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION" in process.env,
  }),
)

alias.c(3, 91, 0, null)
unsafeDeniedActivation.dispose()
unsafeActivation.dispose()
defaultActivation.dispose()
