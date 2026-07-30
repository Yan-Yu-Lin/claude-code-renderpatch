import { activate as activateDefault } from "../extensions/default.mjs"

const runtime = globalThis[Symbol.for("claude-code-renderpatch.runtime")]
const alias = globalThis.__rp
const results = {}

function extensionManifest(id, bridges, extra = {}) {
  const { requires = {}, ...fields } = extra
  return {
    id,
    version: "1.0.0",
    schemaVersion: 1,
    requires: {
      policyApiVersion: 2,
      bridges,
      ...requires,
    },
    ...fields,
  }
}

function policyCase(id, handler, fallback, ...payload) {
  const activation = runtime.registerExtension(
    extensionManifest(id, [{ id: 3, abiVersion: 1 }]),
    { policies: [{ id: 3, handler }] },
  )
  const value = alias.q(3, fallback, ...payload)
  activation.dispose()
  return value
}

const descriptor = Object.getOwnPropertyDescriptor(globalThis, "__rp")
results.alias = {
  keys: Object.keys(alias).sort(),
  enumerable: descriptor.enumerable,
  writable: descriptor.writable,
  configurable: descriptor.configurable,
  frozen: Object.isFrozen(alias),
  sameAsRuntimeBridge: alias === runtime.bridge,
}
results.versions = {
  registryApi: runtime.apiVersion,
  runtimeApi: runtime.runtimeApiVersion,
  policyApi: runtime.policyApiVersion,
  bridgeAbi: runtime.bridgeAbi,
  bridgeBuildId: runtime.bridgeBuildId,
  rawSlotApi: runtime.rawSlotApi,
}
results.stockVerification = runtime.read.status().target

const objectFallback = Object.freeze({ marker: "exact-fallback" })
results.fallbacks = {
  missingIdentity: alias.q(99, objectFallback) === objectFallback,
  missing: alias.q(3, 81, "gpt-test"),
  thrown: policyCase("probe-throw", () => {
    throw new Error("policy failure")
  }, 82, "gpt-test"),
  promise: policyCase("probe-promise", () => Promise.resolve(1), 83, "gpt-test"),
  rejectedPromise: policyCase(
    "probe-rejected-promise",
    () => Promise.reject(new Error("rejected policy promise")),
    831,
    "gpt-test",
  ),
  thenable: policyCase("probe-thenable", () => ({ then() {} }), 84, "gpt-test"),
  throwingThenGetter: policyCase(
    "probe-then-getter",
    () => Object.defineProperty({}, "then", { get() { throw new Error("then getter") } }),
    85,
    "gpt-test",
  ),
  undefined: policyCase("probe-undefined", () => undefined, 86, "gpt-test"),
  wrongType: policyCase("probe-type", () => "372000", 87, "gpt-test"),
  belowRange: policyCase("probe-low", () => 0, 88, "gpt-test"),
  aboveRange: policyCase("probe-high", () => 10_000_001, 89, "gpt-test"),
  badPayload: policyCase("probe-payload", () => 372000, 90, { model: "gpt" }),
}

const zeroActivation = runtime.registerExtension(
  extensionManifest("probe-zero", [{ id: 0, abiVersion: 1 }, { id: 1, abiVersion: 1 }, { id: 2, abiVersion: 1 }]),
  {
    policies: [
      { id: 0, handler: () => 0 },
      { id: 1, handler: () => false },
      { id: 2, handler: () => false },
    ],
  },
)
results.validSentinels = {
  zero: alias.q(0, 3, "transcript"),
  falseReset: alias.q(1, true, "resize", false),
  falseToggle: alias.q(2, true, true),
}
let ownershipRejected = false
try {
  runtime.registerExtension(
    extensionManifest("probe-owner", [{ id: "renderer.messages", abiVersion: 1 }, { id: 1, abiVersion: 1 }, { id: 2, abiVersion: 1 }]),
    {
      policies: [
        { id: 0, handler: () => 3 },
        { id: 1, handler: () => true },
        { id: 2, handler: () => true },
      ],
    },
  )
} catch {
  ownershipRejected = true
}
zeroActivation.dispose()

let incompleteRejected = false
try {
  runtime.registerExtension(
    extensionManifest("probe-incomplete", [{ id: 0, abiVersion: 1 }]),
    { policies: [{ id: 0, handler: () => 3 }] },
  )
} catch {
  incompleteRejected = true
}
let aliasDuplicateRejected = false
try {
  runtime.registerExtension(
    extensionManifest("probe-alias-duplicate", [
      { id: 3, abiVersion: 1 },
      { id: "provider.contextWindow", abiVersion: 1 },
    ]),
    {
      policies: [
        { id: 3, handler: () => 1 },
        { id: "provider.contextWindow", handler: () => 2 },
      ],
    },
  )
} catch {
  aliasDuplicateRejected = true
}
let asyncRejected = false
try {
  runtime.registerExtension(
    extensionManifest("probe-async", [{ id: 3, abiVersion: 1 }]),
    { policies: [{ id: 3, handler: async () => 1 }] },
  )
} catch {
  asyncRejected = true
}
results.transactions = {
  incompleteRejected,
  aliasDuplicateRejected,
  ownershipRejected,
  asyncRejected,
  inactiveAfterReject: alias.q(0, 17, "transcript"),
}

const deniedUnsafe = runtime.registerExtension(
  extensionManifest("probe-unsafe-denied", [], {
    unsafeRaw: true,
    requires: {
      bridgeAbi: 1,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "wrong-build",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [{ id: "d0", abiVersion: 1 }],
    },
  }),
)
const deniedRawSlot = runtime.registerExtension(
  extensionManifest("probe-unsafe-raw-slot-denied", [], {
    unsafeRaw: true,
    requires: {
      bridgeAbi: 1,
      rawSlotApi: "wrong-raw-slot-api",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [{ id: "d0", abiVersion: 1 }],
    },
  }),
)
const deniedTarget = runtime.registerExtension(
  extensionManifest("probe-unsafe-target-denied", [], {
    unsafeRaw: true,
    requires: {
      bridgeAbi: 1,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "wrong-stock-sha",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [{ id: "d0", abiVersion: 1 }],
    },
  }),
)
const deniedBridgeAbi = runtime.registerExtension(
  extensionManifest("probe-unsafe-bridge-abi-denied", [], {
    unsafeRaw: true,
    requires: {
      bridgeAbi: 2,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [{ id: "d0", abiVersion: 1 }],
    },
  }),
)
const deniedCaptureAbi = runtime.registerExtension(
  extensionManifest("probe-unsafe-capture-abi-denied", [], {
    unsafeRaw: true,
    requires: {
      bridgeAbi: 1,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [{ id: "d0", abiVersion: 2 }],
    },
  }),
)
results.unsafeDenied = {
  bridgeBuild: !("unsafe" in deniedUnsafe),
  rawSlotApi: !("unsafe" in deniedRawSlot),
  target: !("unsafe" in deniedTarget),
  bridgeAbi: !("unsafe" in deniedBridgeAbi),
  captureAbi: !("unsafe" in deniedCaptureAbi),
}

const exactUnsafe = runtime.registerExtension(
  extensionManifest("probe-unsafe-exact", [], {
    unsafeRaw: true,
    requires: {
      bridgeAbi: 1,
      rawSlotApi: "2.1.220.1",
      target: {
        version: "2.1.220",
        bridgeBuildId: "internal-sdk-2.1.220.1",
        stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
        artifactSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      },
      captureDomains: [
        { id: "d0", abiVersion: 1 },
        { id: "d3", abiVersion: 1 },
        { id: "d4", abiVersion: 1 },
      ],
    },
  }),
)
results.unsafeExact = "unsafe" in exactUnsafe

const staticFirst = () => "first"
const staticConflict = () => "conflict"
const staticSlots = []
staticSlots[1] = staticFirst
staticSlots[4] = (model) => (model.startsWith("claude-") ? "anthropic" : "proxy")
staticSlots[5] = (model) => ({ id: model, name: "Synthetic Model", secret: "hidden" })
staticSlots[6] = () => 200000
staticSlots[18] = (requested, parent) => requested === parent
staticSlots[20] = (model) => model.split("-")[0]
const staticBitmap = 2 ** 1 + 2 ** 4 + 2 ** 5 + 2 ** 6 + 2 ** 18 + 2 ** 20
const conflictSlots = [...staticSlots]
conflictSlots[1] = staticConflict
results.captureReturnIgnored = alias.c(0, 0, staticBitmap, staticSlots) === undefined
alias.c(0, 0, staticBitmap, conflictSlots)
alias.c(0, 1, staticBitmap, conflictSlots)
results.staticCapturePreserved = runtime.read.mc.canonicalize("probe").value === "first"

const secretOne = "RAW_CAPTURE_SECRET_ONE"
const secretTwo = "RAW_CAPTURE_SECRET_TWO"
const renderOne = []
renderOne[0] = [secretOne]
renderOne[4] = [1, 2]
renderOne[8] = true
const renderBitmap = 2 ** 0 + 2 ** 4 + 2 ** 8
alias.c(3, 1, renderBitmap, renderOne)
const firstMetadata = runtime.read.captureMetadata(3)
alias.c(3, 1, 2 ** 0, [["same-generation-conflict"]])
alias.c(3, 2, 2 ** 16, [])
alias.c(3, 2, 1, null)
alias.c(3, 2, 2, [])

const renderTwo = []
renderTwo[0] = [secretTwo, "second"]
renderTwo[4] = [
  { role: "assistant", content: "second secret" },
  { role: "user", content: "other" },
  { role: "assistant", content: "second again" },
]
renderTwo[8] = false
alias.c(3, 2, renderBitmap, renderTwo)
alias.c(3, 1, 0, null)
const afterStaleClear = runtime.read.captureMetadata(3)
const messageSnapshot = runtime.read.messages(2)
const messageExport = runtime.actions.msg.export({ generation: 2, stage: "rendered", limit: 10 })
const messageSearch = runtime.actions.msg.search({ generation: 2, query: "second" })
const statusJson = JSON.stringify(runtime.read.status())
alias.c(3, 2, 0, null)
results.capture = {
  firstGeneration: firstMetadata.generation,
  firstBitmap: firstMetadata.presenceBitmap,
  afterStaleGeneration: afterStaleClear.generation,
  afterStaleBitmap: afterStaleClear.presenceBitmap,
  safeReplacementVisible: messageSnapshot.counts.raw === 2,
  snapshotRawCount: messageSnapshot.counts.raw,
  snapshotRenderedCount: messageSnapshot.counts.rendered,
  exportAvailable: messageExport.available,
  exportSummaryCount: messageExport.value.summaries.length,
  exportContainsContent: JSON.stringify(messageExport).includes("second secret"),
  searchMatchCount: messageSearch.value.matches.length,
  statusContainsRaw: statusJson.includes("RAW_CAPTURE_SECRET"),
  cleared: runtime.read.captureMetadata(3).available === false,
  captureDomainCount: runtime.read.status().captures.length,
}

let actionValue = null
let toggleValue = false
let redrawValue = false
const replSlots = []
replSlots[2] = { id: "main", type: "repl", prompt: "must-not-leak" }
replSlots[5] = false
replSlots[6] = (enabled) => {
  actionValue = enabled
}
replSlots[9] = [{ id: "help", name: "Help", handler: () => undefined }]
replSlots[11] = [{ id: "read", name: "Read", secret: "hidden" }]
replSlots[12] = [{ id: "agent", name: "Agent" }]
replSlots[15] = {
  toggleTranscript() {
    toggleValue = true
  },
  redraw() {
    redrawValue = true
  },
}
const replBitmap = 2 ** 2 + 2 ** 5 + 2 ** 6 + 2 ** 9 + 2 ** 11 + 2 ** 12 + 2 ** 15
alias.c(4, 10, replBitmap, replSlots)
const listedActions = runtime.actions.list()
const staleAction = runtime.actions.invoke("repl.showAll", { generation: 9, enabled: true })
const validAction = runtime.actions.invoke("repl.showAll", { generation: 10, enabled: true })
const invalidAction = runtime.actions.invoke("repl.showAll", { generation: 10, enabled: "yes" })
const toggleAction = runtime.actions.repl.toggle({ generation: 10 })
const redrawAction = runtime.actions.repl.redraw({ generation: 10 })
const replSafe = runtime.read.repl.state(10)
const replCatalogs = runtime.read.repl.catalogs(10)
alias.c(4, 10, 0, null)
results.actions = {
  listed: listedActions,
  stale: staleAction,
  valid: validAction,
  invalid: invalidAction,
  toggle: toggleAction,
  redraw: redrawAction,
  value: actionValue,
  toggleValue,
  redrawValue,
  currentViewType: replSafe.currentView.type,
  currentViewFields: replSafe.currentView.fields,
  commandCount: replCatalogs.value.commands.length,
}

let inkRedraw = false
let inkInvalidated = false
let diagnosticMessage = null
const inkInstance = {
  width: 120,
  height: 40,
  redraw() {
    inkRedraw = true
  },
  invalidate() {
    inkInvalidated = true
  },
}
const inkSlots = []
inkSlots[0] = new Map([[process.stdout, inkInstance]])
inkSlots[15] = (message) => {
  diagnosticMessage = message
}
inkSlots[17] = "/private/sensitive/debug.log"
inkSlots[18] = true
inkSlots[19] = false
const inkBitmap = 2 ** 0 + 2 ** 15 + 2 ** 17 + 2 ** 18 + 2 ** 19
alias.c(1, 0, inkBitmap, inkSlots)
const inkRead = runtime.read.ink.frame(0)
const diagRead = runtime.read.diag.status(0)
const inkRedrawAction = runtime.actions.ink.redraw({ generation: 0 })
const inkInvalidateAction = runtime.actions.ink.invalidate({ generation: 0 })
const diagLogAction = runtime.actions.diag.log({ generation: 0, message: "diagnostic\nmessage" })

let appListener = null
let appObserved = null
const appSlots = []
appSlots[2] = () => ({
  model: "claude-opus-5",
  permissionMode: "default",
  tasks: [{ secret: "task-content" }],
  notifications: [1, 2],
  prompt: "must-not-leak",
})
appSlots[4] = (listener) => {
  appListener = listener
  return () => {
    appListener = null
  }
}
alias.c(2, 20, 2 ** 2 + 2 ** 4, appSlots)
const appRead = runtime.read.app.metadata(20)
const appSubscription = runtime.actions.app.subscribe({ generation: 20 }, (value) => {
  appObserved = value
})
appListener?.()
const appDisposed = appSubscription.value?.() ?? false
alias.c(2, 20, 0, null)

let keyInvoked = null
let keyRegistered = null
const keySlots = []
keySlots[0] = {
  invoke(action) {
    keyInvoked = action
  },
  registerAction(action) {
    keyRegistered = action
    return () => {
      keyRegistered = null
    }
  },
}
keySlots[1] = [{ id: "ink.redraw", name: "Redraw", handler: () => undefined }]
keySlots[5] = [{ id: "repl", name: "REPL" }]
keySlots[8] = { key: "ctrl+x", secret: "hidden" }
const captureEvents = []
const stopObserving = runtime.read.observe(5, (event) => captureEvents.push(event))
alias.c(5, 30, 2 ** 0 + 2 ** 1 + 2 ** 5 + 2 ** 8, keySlots)
await Promise.resolve()
const keyRead = runtime.read.key.catalog(30)
const keyInvokeAction = runtime.actions.key.invoke({ generation: 30, action: "ink.redraw" })
const keyRegisterAction = runtime.actions.key.register(
  { generation: 30, action: "ink.redraw" },
  () => undefined,
)
const registeredBeforeDispose = keyRegistered
const keyDisposed = keyRegisterAction.value?.() ?? false
stopObserving()
alias.c(5, 30, 0, null)

results.safeFacades = {
  mc: {
    canonical: runtime.read.mc.canonicalize("gpt-test").value,
    provider: runtime.read.mc.provider("gpt-test").value,
    window: runtime.read.mc.windowPreview("gpt-test").value.contextWindow,
    catalogContainsSecret: JSON.stringify(runtime.read.mc.catalog("gpt-test")).includes("hidden"),
  },
  sr: runtime.read.sr.preview("opus", "claude-opus-5").value,
  app: {
    available: appRead.available,
    taskCount: appRead.value.counts.tasks,
    containsPrompt: JSON.stringify(appRead).includes("must-not-leak"),
    subscriptionOk: appSubscription.ok,
    observed: appObserved?.available ?? false,
    disposed: appDisposed,
  },
  ink: {
    available: inkRead.available,
    liveInstance: inkRead.value.liveInstance,
    redrawOk: inkRedrawAction.ok,
    invalidateOk: inkInvalidateAction.ok,
    redrawValue: inkRedraw,
    invalidateValue: inkInvalidated,
  },
  key: {
    available: keyRead.available,
    bindingCount: keyRead.value.bindings.length,
    invokeOk: keyInvokeAction.ok,
    invoked: keyInvoked,
    registerOk: keyRegisterAction.ok,
    registered: registeredBeforeDispose,
    disposed: keyDisposed,
    observedEvents: captureEvents.length,
    containsSecret: JSON.stringify(keyRead).includes("hidden"),
  },
  diag: {
    available: diagRead.available,
    logFile: diagRead.value.logFile,
    logOk: diagLogAction.ok,
    message: diagnosticMessage,
  },
}

deniedUnsafe.dispose()
deniedRawSlot.dispose()
deniedTarget.dispose()
deniedBridgeAbi.dispose()
deniedCaptureAbi.dispose()
exactUnsafe.dispose()

const defaultActivation = activateDefault(runtime)
results.defaultPolicies = {
  messageTranscript: alias.q(0, 0, "transcript"),
  messageRepl: alias.q(0, 0, "repl"),
  resetClassic: alias.q(1, false, "resize", false),
  resetAltScreen: alias.q(1, false, "resize", true),
  toggleEnter: alias.q(2, false, true),
  toggleLeave: alias.q(2, false, false),
  kimiWindow: alias.q(3, 1, "kimi-k3"),
  otherWindow: alias.q(3, 1, "gpt-5.6"),
  claudeFallback: alias.q(3, 123456, "claude-opus-5"),
  explicitShortcut: alias.q(4, true, "opus", "claude-opus-5"),
}
defaultActivation.dispose()
results.statusFrozen = Object.isFrozen(runtime.read.status())
results.runtimeFrozen = Object.isFrozen(runtime)

console.log("SDK_V2", JSON.stringify(results))
