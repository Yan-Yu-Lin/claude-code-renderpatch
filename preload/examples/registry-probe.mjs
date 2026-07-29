// Exercise registry replacement, disposal, freezing, and sync/async failure handling.
const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]
const results = {}

const disposeFirst = runtime.register("probe:replace", () => 1)
runtime.register("probe:replace", () => 2)
results.replacement = runtime.invoke("probe:replace")
results.staleDisposer = disposeFirst()
results.afterStaleDisposer = runtime.invoke("probe:replace")

runtime.register("probe:sync-error", () => {
  throw new Error("intentional sync hook error")
})
results.syncError = runtime.invoke("probe:sync-error") ?? null

runtime.register("probe:async-error", async () => {
  throw new Error("intentional async hook error")
})
results.asyncError = (await runtime.invoke("probe:async-error")) ?? null
results.runtimeFrozen = Object.isFrozen(runtime)
results.processMetadataFrozen = Object.isFrozen(runtime.process)
results.apiVersion = runtime.apiVersion

console.log("REGISTRY_API", JSON.stringify(results))
