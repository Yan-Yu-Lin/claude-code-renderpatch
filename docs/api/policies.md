# Policy API 參考

Policy 是 binary 內五個 exact-version decision point 的同步 primitive override。Policy ID `0–4` 與 capture `d0–d5` 是兩套不同 namespace。

## Handler 契約

```js
{
  id: "provider.contextWindow",
  handler(fallback, ...payload) {
    return fallback
  },
}
```

Handler 必須：

- synchronous；
- 接收 exact stock fallback 作為第一個 argument；
- 只接收 primitive payload；
- 回傳 domain 指定型別/範圍；
- 不回傳 `undefined`、Promise 或 thenable。

Query 在以下情況回傳 exact fallback：

- bridge inactive/incompatible；
- unknown domain 或 invalid payload；
- domain 無 owner；
- handler throw；
- Promise/thenable；
- `then` getter throw；
- `undefined`；
- wrong type/range。

合法 `false` 與 `0` 會保留。Registered handler 的 rejected result 會增加 `read.status().policyDomains[].rejectedResultCount`。

## Domain 0：`renderer.messages`

```text
handler(fallback: 0, screen: string): integer 0..3
```

Bitmask：

- bit 0 (`1`)：force effective `showAllInTranscript`；
- bit 1 (`2`)：force effective `disableRenderCap` for both caps。

Default：

```js
function rendererMessages(_fallback, screen) {
  return 2 | (screen === "transcript" ? 1 : 0)
}
```

Binary query：

```js
globalThis.__rp.q(0, 0, screen)
```

## Domain 1：`renderer.reset`

```text
handler(
  fallback: boolean,
  reason: string | null,
  altScreen: boolean
): boolean
```

`true` 原子授權：

- replay 從 row zero 開始；
- clear patch 帶 destructive intent。

Default：

```js
function rendererReset(_fallback, _reason, altScreen) {
  return !altScreen
}
```

Binary query：

```js
globalThis.__rp.q(1, false, reason, altScreen)
```

## Domain 2：`renderer.toggleRedraw`

```text
handler(
  fallback: boolean,
  enteringTranscript: boolean
): boolean
```

`true` 只授權進入 transcript 時的 extra redraw。Private redraw helper、50 ms timer、state setter 與 telemetry 仍由 binary 擁有。

Default：

```js
function rendererToggleRedraw(_fallback, enteringTranscript) {
  return enteringTranscript
}
```

Binary query：

```js
globalThis.__rp.q(2, false, enteringTranscript)
```

## Renderer atomic bundle 規則

Domain `0/1/2` 必須三個一起註冊或全部不註冊，避免 complete message frame、destructive reset 與 transcript redraw 只啟用一部分。

## Domain 3：`provider.contextWindow`

```text
handler(
  fallback: positive safe integer,
  canonicalModel: string
): integer 1..10,000,000
```

Fallback 是完整 precomputed stock result，包含 native 1M、cache、valid env override 與 default path。

Default：

```js
function providerContextWindow(fallback, canonicalModel) {
  if (canonicalModel.startsWith("kimi")) return 262144
  if (canonicalModel.startsWith("claude-")) return fallback
  return 372000
}
```

Binary query：

```js
globalThis.__rp.q(3, stockWindow, canonicalModel)
```

## Domain 4：`subagent.explicitModelRouting`

```text
handler(
  fallback: boolean,
  requestedModel: string,
  parentModel: string
): boolean
```

Result 表示是否保留第一個 explicit same-family shortcut。

Default：

```js
function explicitModelRouting() {
  return false
}
```

`false` 讓流程進入 stock alias resolver、allowlist、provider remapping、fallback 與 1M path。第二個 default/frontmatter shortcut 不查詢 domain 4。

## Policy ownership 規則

Normal candidate mode 先載入 immutable `default.mjs`，已擁有 `0–4`。Second-stage user extension 不能覆寫這些 policy；應使用 zero-policy manifest。

## Domain 5 不存在

目前 policy API 只有 `0–4`。Banner internals 文件中的 proposed domain 5 是未來/unbridged 概念，不可用於目前 manifest 或 `q` call。

Banner map：

- [../internals/BANNER-RENDERER-2.1.220.md](../internals/BANNER-RENDERER-2.1.220.md)
