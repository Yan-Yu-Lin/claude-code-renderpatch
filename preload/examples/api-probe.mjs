// Report the Bun/Node capabilities visible to an in-process preload.
const fs = await import("node:fs")
const path = await import("node:path")
const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]

console.log(
  "PRELOAD_API",
  JSON.stringify({
    bunVersion: globalThis.Bun?.version ?? null,
    bunFile: typeof globalThis.Bun?.file,
    require: typeof require,
    nodeFs: typeof fs.readFileSync,
    nodePath: typeof path.resolve,
    importMetaUrl: typeof import.meta.url,
    bunOptionsPresent: "BUN_OPTIONS" in process.env,
    activePresent: "CLAUDE_RENDERPATCH_ACTIVE" in process.env,
    targetPresent: "CLAUDE_RENDERPATCH_TARGET" in process.env,
    bridgeBuildPresent: "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID" in process.env,
    bridgeArtifactShaPresent:
      "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256" in process.env,
    bridgeTargetVersionPresent:
      "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION" in process.env,
    userModulePresent: "CLAUDE_RENDERPATCH_USER_MODULE" in process.env,
    registryApiVersion: runtime?.apiVersion ?? null,
    runtimeApiVersion: runtime?.runtimeApiVersion ?? null,
    policyApiVersion: runtime?.policyApiVersion ?? null,
    bridgeAbi: runtime?.bridgeAbi ?? null,
    execPath: process.execPath,
  }),
)
