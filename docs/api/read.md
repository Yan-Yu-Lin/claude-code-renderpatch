# Safe read API 參考

`runtime.read` 回傳 frozen、bounded、redacted metadata。它不公開 live store、message array、React ref、setter、handler map、terminal frame 或 submit callback。

## 兩種 result envelope

### Availability result 格式

大多數 domain read 回傳：

```text
{
  available: true,
  generation: number,
  value: T
}
```

或：

```text
{
  available: false,
  reason: string,
  generation: number | null
}
```

常見 reason：`invalid`、`unavailable`、`stale`、`failed`、`async-result`、`invalid-result`。

### Direct snapshot 或 `null`

以下 method 不使用 availability envelope：

```text
read.msg.counts(generation?)
read.messages(generation?)
read.repl(generation?)
read.repl.state(generation?)
```

它們直接回傳 frozen snapshot，capture 不存在或 generation stale 時回傳 `null`。

## Status 與 capture 生命週期

### `read.status()`

```text
status(): Status
```

主要 shape：

```text
{
  registryApiVersion,
  runtimeApiVersion,
  policyApiVersion,
  bridgeAbi,
  bridgeBuildId,
  rawSlotApi,
  target: {
    expectedVersion,
    selectedVersion,
    exactVersion,
    verificationMode,
    artifactVerified,
    bridgeMetadataPresent
  },
  bridgeFacade: { active, collision },
  policyDomains: [
    { id, name, abiVersion, active, owner, rejectedResultCount }
  ],
  captures: CaptureMetadata[],
  extensions: [
    { id, version, unsafeEnabled, policyDomainIds }
  ]
}
```

Status 不包含 raw slot value、handler、credential、transcript content、terminal frame 或 payload history。

### `read.captureMetadata(domain)`

```text
captureMetadata(
  domain: number | "d0" | ... | "d5" | captureName
): CaptureMetadata | null
```

Capture names：

```text
static-model-routing
static-ink-terminal-dialog-diagnostics
provider-app-state
render-messages-pipeline
render-repl-controls
provider-keybindings
```

Return：

```text
{
  id,
  compactId,
  name,
  abiVersion,
  lifecycle,
  available,
  generation,
  presenceBitmap,
  presentSlotCount,
  slotCount
}
```

Unknown domain 回傳 `null`。

### `read.observe(domain, callback)`

```text
observe(domain, callback): () => boolean
```

Invalid domain 或 non-function callback 會 throw `TypeError`。Callback 在 queued microtask 收到：

```text
{
  event: "publish" | "replace" | "clear",
  metadata: CaptureMetadata
}
```

Observer throw 會 report 並忽略；disposer idempotent。

## `read.mc`

```text
read.mc.canonicalize(model, generation?)
  -> Availability<string>

read.mc.catalog(model, generation?)
  -> Availability<ObjectSummary>

read.mc.provider(model, generation?)
  -> Availability<string | ObjectSummary>

read.mc.windowPreview(model, generation?)
  -> Availability<{
       canonicalModel: string,
       contextWindow: number
     }>
```

`model` 必須是 1–256 字元 string。這些 method 使用 capture `d0` 的 exact-version helpers，但只回傳 safe summary。

## `read.sr`

```text
read.sr.preview(requestedModel, parentModel, generation?)
read.sr.trace(requestedModel, parentModel, generation?)
```

兩者目前是同一個 function。Return：

```text
Availability<{
  requestedModel,
  parentModel,
  canonicalRequested,
  sameFamilyShortcut,
  requestedFamily,
  parentFamily
}>
```

個別 derived field 在 helper unavailable 時可能是 `null`。`trace` 不是完整 resolver execution trace。

## `read.msg`

### `read.msg.counts(generation?)`

```text
MessageSnapshot | null
```

```text
{
  generation,
  counts: {
    raw,
    normalized,
    collapsed,
    postToolStats,
    rendered
  },
  preNormalizationCapStart,
  hasTruncatedMessages,
  hiddenMessageCount,
  virtualScrollActive,
  effectiveCapRows,
  screen,
  showAllInTranscript,
  disableRenderCap
}
```

Slot absent 或型別不符時，對應 scalar/count 可能是 `null`。

### `read.messages(generation?)`

`read.msg.counts` alias。

### `read.msg.snapshot(request?)`

實際等同 bounded message summary export：

```text
snapshot({
  generation?: number | null,
  stage?: "raw" | "normalized" | "collapsed" |
          "postToolStats" | "rendered",
  limit?: number
}): Availability<MessageSummaryExport>
```

`limit` 預設 50，範圍 1–100。不回傳 raw content。

## `read.repl`

### `read.repl(generation?)`

### `read.repl.state(generation?)`

兩者是 alias：

```text
{
  generation,
  currentView: ObjectSummary,
  screen: string | null,
  showAllInTranscript: boolean | null,
  disableRenderCap: boolean | null
} | null
```

### `read.repl.catalogs(generation?)`

```text
Availability<{
  commands: CatalogEntry[],
  tools: CatalogEntry[],
  agents: CatalogEntry[]
}>
```

每個 catalog 最多 100 entries，只保留 bounded summary。

## `read.app.metadata(generation?)`

```text
Availability<{
  state: ObjectSummary,
  counts: Record<string, number>
}>
```

Safe scalar 包含可能存在的 `model`、`permissionMode`、`isLoading`、`isCompact`。Collection count 可能包含 `tasks`、`messages`、`notifications`、`mcpClients`、`plugins`、`open`。

## `read.ink.frame(generation?)`

```text
Availability<{
  stdout: { columns: number | null, rows: number | null },
  liveInstance: boolean,
  instance: ObjectSummary
}>
```

Current Ink instance 在呼叫時從 map/getter 取得，但不直接回傳 instance。

## `read.key.catalog(generation?)`

```text
Availability<{
  bindings: CatalogEntry[],
  activeContexts: CatalogEntry[],
  pendingChord: ObjectSummary
}>
```

不公開 handler registry 或 live refs。

## `read.diag.status(generation?)`

```text
Availability<{
  debugMode: boolean | null,
  stderrMode: boolean | null,
  logFile: string | null,
  telemetryAvailable: boolean
}>
```

`logFile` 只有 basename。

## Object summary 格式

常見 shape：

```text
{
  type: string,
  count?: number,
  keys: string[],
  fields: Record<string, boolean | number | string>
}
```

這是 metadata wrapper，不是 Claude Code internal object 的穩定 schema。
