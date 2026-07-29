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
    runtimeApiVersion: runtime?.apiVersion ?? null,
    execPath: process.execPath,
  }),
)
