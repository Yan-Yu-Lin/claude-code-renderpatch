// External bootstrap for the zero-patch Claude Code preload experiment.
// Bun executes this module before Claude Code parses its command-line arguments.

const runtimeKey = Symbol.for("claude-code-renderpatch.runtime")
const externalModuleInput = process.env.CLAUDE_RENDERPATCH_MODULE
const targetInput = process.env.CLAUDE_RENDERPATCH_TARGET ?? null

// Do not leak one-shot preload state into Bun or Claude child processes.
delete process.env.BUN_OPTIONS
delete process.env.CLAUDE_RENDERPATCH_MODULE
delete process.env.CLAUDE_RENDERPATCH_ACTIVE
delete process.env.CLAUDE_RENDERPATCH_TARGET

function report(message) {
  process.stderr.write(`[renderpatch-preload] ${message}\n`)
}

function reportHookFailure(name, error) {
  report(`hook ${name} failed: ${error?.stack ?? error}`)
  return undefined
}

function createRuntime() {
  const hooks = new Map()
  const processMetadata = Object.freeze({
    execPath: process.execPath,
    argv: Object.freeze([...process.argv]),
    bunVersion: globalThis.Bun?.version ?? null,
    target: targetInput,
    launchedViaBunPreload: true,
  })

  const runtime = {
    apiVersion: 1,
    runtimeVersion: "0.2.0",
    process: processMetadata,
    register(name, handler) {
      if (typeof name !== "string" || !name) {
        throw new TypeError("Hook name must be a non-empty string")
      }
      if (typeof handler !== "function") {
        throw new TypeError(`Hook ${name} must be a function`)
      }
      hooks.set(name, handler)
      return () => {
        if (hooks.get(name) !== handler) return false
        return hooks.delete(name)
      }
    },
    unregister(name) {
      return hooks.delete(name)
    },
    invoke(name, payload) {
      const handler = hooks.get(name)
      if (!handler) return undefined
      try {
        const result = handler(payload)
        if (result && typeof result.then === "function") {
          return Promise.resolve(result).catch((error) => reportHookFailure(name, error))
        }
        return result
      } catch (error) {
        return reportHookFailure(name, error)
      }
    },
    listHooks() {
      return [...hooks.keys()]
    },
  }
  return Object.freeze(runtime)
}

const existingRuntime = globalThis[runtimeKey]
if (existingRuntime === undefined) {
  Object.defineProperty(globalThis, runtimeKey, {
    value: createRuntime(),
    configurable: false,
    enumerable: false,
    writable: false,
  })
} else if (
  typeof existingRuntime !== "object" ||
  existingRuntime === null ||
  existingRuntime.apiVersion !== 1
) {
  report("global runtime symbol already contains an incompatible value; extensions disabled")
}

async function resolveTrustedModule(input) {
  const { homedir } = await import("node:os")
  const path = await import("node:path")
  const fs = await import("node:fs/promises")

  if (!path.isAbsolute(input)) {
    throw new Error(`CLAUDE_RENDERPATCH_MODULE must be absolute: ${input}`)
  }

  const unresolved = path.resolve(input)
  const root = path.parse(unresolved).root
  let unresolvedComponent = root
  for (const part of unresolved.slice(root.length).split(path.sep).filter(Boolean)) {
    unresolvedComponent = path.join(unresolvedComponent, part)
    if ((await fs.lstat(unresolvedComponent)).isSymbolicLink()) {
      throw new Error(
        `External module path component must not be a symlink: ${unresolvedComponent}`,
      )
    }
  }

  const resolved = await fs.realpath(unresolved)
  const home = await fs.realpath(homedir())
  if (resolved !== home && !resolved.startsWith(`${home}${path.sep}`)) {
    throw new Error(`External module must live under the current user's home: ${resolved}`)
  }

  const uid = typeof process.getuid === "function" ? process.getuid() : null
  let current = resolved
  while (true) {
    const info = await fs.stat(current)
    if (uid !== null && info.uid !== uid) {
      throw new Error(`External module path component is not user-owned: ${current}`)
    }
    if ((info.mode & 0o022) !== 0) {
      throw new Error(`External module path component is group/world writable: ${current}`)
    }
    if (current === home) break
    current = path.dirname(current)
  }

  if (!(await fs.stat(resolved)).isFile()) {
    throw new Error(`External module is not a regular file: ${resolved}`)
  }

  return resolved
}

if (externalModuleInput && globalThis[runtimeKey]?.apiVersion === 1) {
  try {
    const { pathToFileURL } = await import("node:url")
    const externalModule = await resolveTrustedModule(externalModuleInput)
    await import(pathToFileURL(externalModule).href)
  } catch (error) {
    // Thrown or rejected imports are reported and skipped. Same-realm code can still
    // intentionally exit, hang, or leave partial mutations; use the safe launcher then.
    report(`external module was skipped: ${error?.stack ?? error}`)
  }
}
