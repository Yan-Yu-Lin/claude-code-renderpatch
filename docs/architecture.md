# 架構

目前 prototype 採用 hybrid architecture：大部分 runtime 與 policy 邏輯留在外部 JavaScript，只有必須接觸 Claude Code closure-bound internals 的位置使用 2.1.220 專用 binary bridge。

## 啟動流程

```text
claude-renderpatch-candidate
  -> 驗證 target、release assets、hash、mode、codesign、proxy/settings
  -> 設定 BUN_OPTIONS=--preload=<bootstrap.mjs>
  -> 啟動 patched Claude Code 2.1.220
  -> bootstrap 建立 runtime 與 globalThis.__rp
  -> 載入 immutable default.mjs
  -> 載入可選的 user extension
  -> Claude Code 繼續初始化與 render loop
```

Public runtime rendezvous：

```js
const runtime = globalThis[
  Symbol.for("claude-code-renderpatch.runtime")
]
```

Binary-facing compact facade：

```js
globalThis.__rp.q(policyDomainId, fallback, ...primitivePayload)
globalThis.__rp.c(captureDomainId, generation, presenceBitmap, slotsOrNull)
```

`globalThis.__rp` 只公開 `q` 與 `c`，不是完整 runtime。

## 為什麼需要 bridge

Bun preload 已驗證能使用 `globalThis`、`console`、`process`、CommonJS `require`、dynamic `import()`、Node-compatible modules 與 Bun APIs。

但同 process 不等於同 lexical scope。Claude Code bundled entry 沒有公開 renderer、React state、Ink instance、subagent resolver 等內部物件。

因此邊界是：

- **runtime-reachable**：放在外部 preload/runtime，不需要改 binary；
- **closure-bound**：以最小 exact-version bridge 接入。

背景實驗見 [`reference/preload-runtime.md`](../reference/preload-runtime.md)。

## 兩個獨立平面

### 控制平面：policy `0–4`

| ID | Policy |
|---:|---|
| `0` | `renderer.messages` |
| `1` | `renderer.reset` |
| `2` | `renderer.toggleRedraw` |
| `3` | `provider.contextWindow` |
| `4` | `subagent.explicitModelRouting` |

`q(...)` 同步查詢 primitive result。查詢失敗、handler 不存在、throw、回傳 Promise/thenable、`undefined`、錯誤型別或超出範圍時，必須回傳同一個 fallback。合法的 `false` 與 `0` 不是「未提供」。

詳見 [api/policies.md](api/policies.md)。

### Raw asset 資料平面：capture `d0–d5`

| ID | 內容 | Lifecycle |
|---|---|---|
| `d0` | model/context/subagent helpers | static |
| `d1` | Ink/terminal/dialog/diagnostics | static + lookup-live |
| `d2` | app state provider | provider |
| `d3` | Messages pipeline | render-latest |
| `d4` | REPL controls | render-latest |
| `d5` | keybinding provider | provider |

Raw publication 本身不會改變 Claude Code lexical control flow。只有 binary 內已存在的 policy query 才會改變對應決策。

## Runtime 存取層

- `runtime.read`：frozen、bounded、redacted metadata/summary。
- `runtime.actions`：驗證 request、generation、liveness 與 allowlist。
- `activation.unsafe`：只在 exact signed artifact/build/ABI/slot contract 全部吻合時出現。
- legacy hooks：`register`、`unregister`、`invoke`、`listHooks`，與 policy ownership 分開。

## Default-first ownership 規則

正常 candidate launch 固定先載入 immutable default extension。它註冊 policy `0–4`，之後才載入 user extension。

所以 second-stage user extension：

- 可以 zero-policy registration；
- 可以 read、observe、actions、legacy hooks；
- 可以要求 exact-version unsafe；
- 不能重新註冊已被 default 擁有的 policy。

Repository 內的 `full-redraw.mjs`、`mix-window.mjs`、`subagent-routing.mjs` 是 first-stage/default 組裝參考，不是 normal `--renderpatch-extension` override plugin。

## Capture 生命週期

| Lifecycle | 規則 |
|---|---|
| `static` | generation 固定為 `0`；相同重複發布忽略，衝突 replacement 拒絕。 |
| `provider` | 較新 generation 原子取代舊 capture；cleanup 只清除自己那一代。 |
| `render-latest` | 每次新 render 取代舊 graph；consumer 不應保留舊 array/ref/closure。 |
| `lookup-live` | 發布穩定 map/getter，使用時再取得 current instance。 |

Clear signal：

```js
c(domain, matchingGeneration, 0, null)
```

舊 effect cleanup 不會刪掉較新的 capture。

## 驗證模式

- `signed-bridge-artifact`：本機 verified patched candidate；policy/capture 可啟用，unsafe 可進一步 negotiation。
- `stock-lab`：只用 exact version/file-size 做 lab compatibility；不能證明 signed artifact identity，也不能啟用 unsafe。
- incompatible：compact bridge inactive，policy 使用 fallback，capture no-op。

## Banner renderer 不在目前 bridge

Banner renderer 的 exact 2.1.220 研究位於 [internals/BANNER-RENDERER-2.1.220.md](internals/BANNER-RENDERER-2.1.220.md)。目前 policy API 只有 `0–4`；研究文件內的 proposed domain 5 是未來設計方向，不是 runtime API 2 的一部分。
