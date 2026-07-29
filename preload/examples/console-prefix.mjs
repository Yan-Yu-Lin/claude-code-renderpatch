// Demonstrate that the preload shares Claude Code's JavaScript global realm.
const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]
const originalLog = console.log.bind(console)

console.log = (...args) => originalLog("PRELOAD_LAB", ...args)
runtime?.register("example:restore-console", () => {
  console.log = originalLog
})
