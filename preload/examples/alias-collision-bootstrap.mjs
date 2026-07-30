const occupiedAlias = Object.freeze({
  q() {
    return "occupied"
  },
})
Object.defineProperty(globalThis, "__rp", {
  value: occupiedAlias,
  configurable: false,
  enumerable: false,
  writable: false,
})

await import("../bootstrap.mjs")

const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]
console.log(
  "ALIAS_COLLISION",
  JSON.stringify({
    preserved: globalThis.__rp === occupiedAlias,
    result: globalThis.__rp.q(),
    active: runtime.read.status().bridgeFacade.active,
    collision: runtime.read.status().bridgeFacade.collision,
  }),
)
