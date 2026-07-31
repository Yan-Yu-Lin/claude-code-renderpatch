# Validated actions API 參考

`runtime.actions` 在使用 captured handle 前驗證 request、generation、liveness 與 allowlist。

## Action result 格式

大多數 action 回傳 frozen：

```text
{
  ok: boolean,
  reason: string | null,
  generation: number | null,
  value: unknown
}
```

常見 reason：

```text
invalid
stale
unavailable
unsupported
failed
async-result
denied
invalid-disposer
```

`msg.search` 與 `msg.export` 是例外，使用 read-style availability envelope：

```text
{ available: true, generation, value }
{ available: false, reason, generation }
```

## `actions.list()`

```text
list(): readonly string[]
```

目前列出：

```text
msg.search
msg.export
repl.redraw
repl.toggle
repl.showAll
repl.dispatch
app.subscribe
ink.redraw
ink.invalidate
ink.repaint
key.register
key.invoke
diag.log
```

## `actions.invoke(name, request)`

```text
invoke(name: string, request: object): ActionResult | Availability
```

Generic invoke 實際支援：

```text
msg.search
msg.export
repl.redraw
repl.toggle
repl.showAll
repl.dispatch
ink.redraw
ink.invalidate
ink.repaint
key.invoke
diag.log
```

Unknown name 回傳 `unsupported`。

`app.subscribe` 與 `key.register` 雖在 list 中，但需要第二個 callback/handler argument，**不是** generic `actions.invoke()` case。

## Message actions 方法

### `actions.msg.search(request)`

```text
{
  generation?: number | null,
  query: string
}
```

Rules：

- query sanitize 到 256 chars；
- 最少 2 chars；
- 搜尋 final rendered array；
- 最多檢查前 1000 messages；
- 最多回傳 100 matches。

Success value：

```text
{
  totalMessages: number,
  matches: [{ index: number, occurrences: number }]
}
```

不回傳 matched text。

### `actions.msg.export(request?)`

```text
{
  generation?: number | null,
  stage?: "raw" | "normalized" | "collapsed" |
          "postToolStats" | "rendered",
  limit?: number
}
```

`stage` 預設 `rendered`；`limit` 預設 50、範圍 1–100。

Success value：

```text
{
  stage,
  total,
  summaries: [{
    index,
    type,
    count?,
    keys,
    fields,
    textBytes
  }]
}
```

這是 summary export，不是 transcript content export。

## REPL actions 方法

### `actions.repl.showAll(request)`

```text
{ generation: number, enabled: boolean }
```

呼叫 captured show-all setter。

### `actions.repl.toggle(request)`

```text
{ generation: number }
```

依序嘗試：

```text
onToggleTranscript
toggleTranscript
```

### `actions.repl.redraw(request)`

```text
{ generation: number }
```

依序嘗試：

```text
redraw
invalidate
repaint
```

### `actions.repl.dispatch(request)`

```text
{ generation: number, command: string }
```

Runtime 0.3.0 在 shape valid 後仍固定回傳：

```text
{ ok: false, reason: "denied", generation, value: null }
```

Interface 已列出，但 command dispatch 尚未開放。

## App subscription 方法

### `actions.app.subscribe(request, callback)`

```text
subscribe(
  { generation: number },
  callback: (metadataResult) => void
): ActionResult<() => boolean>
```

必須直接呼叫。Callback 只在同一個 `d2` generation 仍 current 時收到 `read.app.metadata(generation)`。

Success `value` 是 idempotent safe disposer。

## Ink actions 方法

Request 都是：

```text
{ generation: number }
```

### `actions.ink.redraw(request)`

依序嘗試 `redraw`、`rerender`。

### `actions.ink.invalidate(request)`

嘗試 `invalidate`。

### `actions.ink.repaint(request)`

依序嘗試 `repaint`、`rerender`。

Current Ink instance 在 action 時 lookup-live resolve。

## Key actions 方法

Safe allowlist 只有：

```text
repl.toggleTranscript
repl.showAll
ink.redraw
```

其他 action name 回傳 `denied`。

### `actions.key.invoke(request)`

```text
{ generation: number, action: string }
```

依序嘗試 provider manager 的 `invoke`、`executeAction`。

### `actions.key.register(request, handler)`

```text
register(
  { generation: number, action: string },
  handler: Function
): ActionResult<() => boolean>
```

必須直接呼叫。依序嘗試 `registerAction`、`register`。Underlying method 必須回傳 disposer；success `value` 是 safe disposer。

## Diagnostic action 方法

### `actions.diag.log(request)`

```text
{ generation: number, message: string }
```

- message control characters 轉為 spaces；
- 最長 256 chars；
- 呼叫 captured debug logger；
- logger 收到 `[renderpatch-extension] ${message}`；
- 不會發送 arbitrary telemetry event。

## Stale generation 處理

Capture generation 在 read 與 action 之間改變時，action 回傳 `stale` 且不執行 side effect。不要盲目 retry；先重新確認新 generation 的操作仍符合使用者意圖。
