// Trusted host loader for the 2.1.281 bridge (sole Bun --preload).
//
// Claude Code >= 2.1.271 renders through Bun.ant.CellSegmenter, which exists
// only in the internal Bun embedded in the official executable, so the patched
// graph runs inside a verbatim copy of that executable. This preload:
//   1. removes its own launch settings so no child inherits the preload;
//   2. evaluates the patched entry that sits beside it (./graph/cli);
//   3. stops the embedded, unpatched entry at its first statement.
// The embedded entry's static imports are six small side-effect-free helpers;
// its body begins with process.env.NoDefaultCurrentDirectoryInExePath="1".
// A one-shot trap on that write, accepted only from /$bunfs/root/cli, throws a
// private sentinel that this module swallows, so the embedded main never runs.
// Everything else (exit codes, stdin, signals) stays with the patched app.

delete process.env.BUN_OPTIONS

const SENTINEL = Symbol("renderpatch.embedded-entry-stopped")
const TRAP_KEY = "NoDefaultCurrentDirectoryInExePath"
const EMBEDDED_ENTRY_FRAME = /\(?\/\$bunfs\/root\/cli:\d+:\d+\)?$/m

function fatal(message) {
  process.stderr.write(`claude-bridge host: ${message}\n`)
  process.exit(70)
}

if (typeof Bun === "undefined" || Bun.isStandaloneExecutable !== true) {
  fatal("must run inside the official Claude Code executable")
}
if (typeof Bun.ant?.CellSegmenter !== "function") {
  fatal("host executable lacks Bun.ant.CellSegmenter")
}

const realEnv = process.env
let stopped = false

function renderpatchHostSentinel(error) {
  if (error?.[SENTINEL] === true) {
    // One-shot: afterwards uncaught-exception handling is exactly the app's.
    process.off("uncaughtException", renderpatchHostSentinel)
    return
  }
  // Not ours: keep the default fatal behaviour when no app handler exists yet.
  if (process.listenerCount("uncaughtException") === 1) {
    process.stderr.write(`${error?.stack ?? error}\n`)
    process.exit(1)
  }
}
process.prependListener("uncaughtException", renderpatchHostSentinel)

try {
  await import(new URL("./graph/cli", import.meta.url).href)
} catch (error) {
  fatal(`patched graph failed to load: ${error?.stack ?? error}`)
}

process.env = new Proxy(realEnv, {
  set(target, key, value) {
    if (!stopped && key === TRAP_KEY) {
      const caller = (new Error().stack ?? "").split("\n")[2] ?? ""
      if (EMBEDDED_ENTRY_FRAME.test(caller.trim())) {
        stopped = true
        process.env = realEnv
        const error = new Error("claude-bridge host: embedded entry stopped")
        error[SENTINEL] = true
        throw error
      }
    }
    target[key] = value
    return true
  },
})
