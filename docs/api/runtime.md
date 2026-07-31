# Runtime API 參考

取得 runtime：

```js
const runtime = globalThis[
  Symbol.for("claude-code-renderpatch.runtime")
]
```

Runtime 與 public nested facades 都是 frozen。

## 版本與資料 properties

| Property | 目前值 | 說明 |
|---|---:|---|
| `apiVersion` | `1` | legacy named-hook API |
| `runtimeApiVersion` | `2` | runtime/read/actions/extension API |
| `policyApiVersion` | `2` | synchronous policy API |
| `bridgeAbi` | `1` | compact `globalThis.__rp` ABI |
| `bridgeBuildId` | `internal-sdk-2.1.220.1` | exact bridge build |
| `rawSlotApi` | `2.1.220.1` | positional slot contract |
| `runtimeVersion` | `0.3.0` | bootstrap runtime version |
| `bridge` | `{q, c}` | compact bridge facade |
| `read` | object | safe read facade |
| `actions` | object | validated action facade |

## `runtime.process`

Bootstrap 建立時凍結：

```text
{
  execPath: string,
  argv: readonly string[],
  bunVersion: string | null,
  target: string | null,
  launchedViaBunPreload: true
}
```

`argv` 是 frozen copy。不要只靠 `target` 判斷 bridge 是否 verified；使用 `runtime.read.status().target`。

## `registerExtension(manifest, implementation?)`

```text
registerExtension(
  manifest: object,
  implementation?: { policies?: PolicyEntry[] }
): Activation
```

成功回傳：

```text
{
  id: string,
  read,
  actions,
  dispose(): boolean,
  unsafe?: UnsafeFacade
}
```

Validation 與 manifest 規則見 [../extensions/manifest-and-registration.md](../extensions/manifest-and-registration.md)。

## Legacy named-hook API 方法

### `register(name, handler)`

```text
register(name: string, handler: Function): () => boolean
```

- `name` 必須是 non-empty string；
- `handler` 必須是 function；
- 相同 name 的新 registration 會取代舊 handler；
- disposer 只會刪除自己仍為 current 的 handler；
- stale/repeated disposer 回傳 `false`。

### `unregister(name)`

```text
unregister(name: string): boolean
```

直接回傳 current hook map 的 delete result。

### `invoke(name, payload)`

```text
invoke(name: string, payload?: unknown): unknown | Promise<unknown>
```

| 情況 | 結果 |
|---|---|
| hook 不存在 | `undefined` |
| sync value | 直接回傳 |
| sync throw | report failure，回傳 `undefined` |
| Promise/thenable | 回傳 Promise |
| rejected Promise/thenable | report failure，Promise resolve `undefined` |

Legacy registry 不 clone/validate successful payload 或 return value；雙方都是 trusted same-process code。

### `listHooks()`

```text
listHooks(): string[]
```

回傳目前 hook names 的新 array；array 本身不 frozen。

## `runtime.bridge`

```text
runtime.bridge.q(policyDomainId, fallback, ...payload)
runtime.bridge.c(captureDomainId, generation, presenceBitmap, slotsOrNull)
```

它與可用時的 `globalThis.__rp` 指向同一個 frozen facade。一般 extension 應使用 `registerExtension`、`read` 與 `actions`，而不是自行呼叫 `c` 模擬 binary publication。

## Global collision 處理

Runtime symbol 與 `globalThis.__rp` 分開處理：

- runtime symbol 若已被 incompatible value 佔用，不覆寫；
- `globalThis.__rp` 若已存在 incompatible value，保留原值、標記 collision、停用 bridge facade；
- bridge inactive 時 policy 使用 fallback、capture no-op。

請用：

```js
runtime.read.status().bridgeFacade
```

判斷 `active` 與 `collision`，不要只檢查 property 是否存在。

## Normal user extension 的限制

Immutable default extension 先註冊 policy `0–4`。Normal user extension 應使用 zero-policy manifest；重新 claim domain 會 transactional failure。
