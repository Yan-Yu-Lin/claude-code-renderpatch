# 撰寫第一個 user extension

本頁描述 normal candidate mode 的 **second-stage user extension**。

## 啟動方式

```bash
claude-renderpatch-candidate \
  --renderpatch-extension "$HOME/path/to/my-extension.mjs" \
  [claude arguments...]
```

Entry file 必須：

- 使用 absolute path；
- 位於目前使用者 home 之下；
- 是 regular file；
- 由目前使用者擁有；
- path component 不得是 symlink；
- file 與檢查到的 parent component 不得 group/world writable。

只驗證 entry path；transitive imports 視為同等信任。

> 這是 feature branch 上的本機 prototype，尚未 merge 到 `main`，沒有 GitHub PR 或 GitHub Release。Fresh clone 必須先從 exact stock Claude Code `2.1.220` 另外 build/sign 被 `.gitignore` 排除的 patched artifact，不能假設 clone 後 installer 立即可用。詳見 [PROJECT-STATUS.md](../PROJECT-STATUS.md)。

## Default extension 的載入順序

Normal mode 固定先載入 immutable `default.mjs`，它已擁有 policy domain `0–4`。User extension 第二個載入，因此不能覆寫：

```text
renderer.messages
renderer.reset
renderer.toggleRedraw
provider.contextWindow
subagent.explicitModelRouting
```

一般 user extension 應使用 zero-policy manifest、safe reads、validated actions、capture observer 或 legacy hooks。

## 最小 zero-policy extension

```js
const manifest = Object.freeze({
  id: "status-example",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: false,
  requires: Object.freeze({
    policyApiVersion: 2,
    bridges: Object.freeze([]),
  }),
})

export function activate(runtime) {
  if (runtime.runtimeApiVersion !== 2) {
    throw new Error(`Unsupported runtime API ${runtime.runtimeApiVersion}`)
  }

  const activation = runtime.registerExtension(manifest)
  const status = activation.read.status()

  process.stderr.write(
    `[status-example] target=${status.target.selectedVersion ?? "unknown"} ` +
      `bridge=${status.bridgeFacade.active ? "active" : "inactive"}\n`,
  )
}
```

預計整合的完整範例：

- [docs/examples/read-status.mjs](../examples/read-status.mjs)

`activate(runtime)` 可以是 named export；若不存在，loader 會嘗試 default export。Loader 會 await activation function，但 policy handler 本身必須同步。

## 等待 capture 出現

Extension 啟動時，REPL/provider capture 可能尚未發布。使用 observer：

```js
export function activate(runtime) {
  const stop = runtime.read.observe("d4", ({ event, metadata }) => {
    if (event === "clear") return

    const state = runtime.read.repl.state(metadata.generation)
    if (!state) return

    process.stderr.write(
      `[repl] generation=${state.generation} screen=${state.screen ?? "unknown"}\n`,
    )
  })

  runtime.register("repl-example:stop", () => stop())
}
```

預計範例：

- [docs/examples/observe-repl.mjs](../examples/observe-repl.mjs)

Observer event 在 queued microtask 執行。Callback throw 會被 report 並忽略。Disposer 可重複呼叫，只有第一次有效移除時回傳 `true`。

## 呼叫 validated action

需要 live capture 的 action 必須帶目前 generation：

```js
const capture = runtime.read.captureMetadata("d1")
if (capture?.available) {
  const result = runtime.actions.ink.redraw({
    generation: capture.generation,
  })

  if (!result.ok) {
    process.stderr.write(`[my-extension] redraw skipped: ${result.reason}\n`)
  }
}
```

預計範例：

- [docs/examples/redraw-action.mjs](../examples/redraw-action.mjs)

Stale generation 會安全失敗，不執行 terminal side effect。

## 必須直接呼叫的 callback methods

這兩個 method 需要第二個 function argument：

```js
runtime.actions.app.subscribe({ generation }, callback)
runtime.actions.key.register({ generation, action }, handler)
```

它們雖出現在 `actions.list()`，但不能透過 `actions.invoke()` 呼叫。

## Module 失敗處理

Loader 流程：

1. 驗證 entry path；
2. dynamic import；
3. 選擇 named `activate`，否則 default export；
4. 呼叫並 await；
5. import/activation throw 或 reject 時 report，然後讓 Claude 繼續啟動。

但 same-realm module 可以 `process.exit`、永久 await，或在 throw 前留下 global mutation。Runtime 無法 rollback。

Recovery：

```bash
claude-renderpatch-candidate --renderpatch-safe
```

## 下一步

- [manifest-and-registration.md](manifest-and-registration.md)
- [../api/runtime.md](../api/runtime.md)
- [../api/read.md](../api/read.md)
- [../api/actions.md](../api/actions.md)
- [../security-and-compatibility.md](../security-and-compatibility.md)
