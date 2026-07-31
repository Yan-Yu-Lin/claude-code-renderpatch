# Extension manifest 與註冊

Runtime API 2 使用：

```js
const activation = runtime.registerExtension(manifest, implementation)
```

Registration 是 transactional：所有 validation 通過後，extension 與 policy ownership 才會發布。

## Zero-policy manifest 結構

Normal user extension 建議使用：

```js
const manifest = {
  id: "my-extension",
  version: "1.0.0",
  schemaVersion: 1,
  unsafeRaw: false,
  requires: {
    policyApiVersion: 2,
    bridges: [],
  },
}
```

| 欄位 | 規則 |
|---|---|
| `id` | non-empty string；不可與 active extension 重複 |
| `version` | non-empty string |
| `schemaVersion` | 必須是 `1` |
| `requires.policyApiVersion` | 必須是 `2` |
| `requires.bridges` | array；zero-policy 時為 `[]` |

`implementation` 預設 `{}`，`implementation.policies` 預設 `[]`。

Zero-policy registration 可以：

- 在 `read.status()` 記錄 extension identity；
- 取得 frozen `read`/`actions` facade；
- 使用 `dispose()`；
- negotiation exact-version unsafe。

## Activation 回傳物件

成功時回傳 frozen object：

```text
{
  id: string,
  read: RuntimeReadFacade,
  actions: RuntimeActionFacade,
  dispose(): boolean,
  unsafe?: UnsafeFacade
}
```

`dispose()`：

- 第一次移除仍 active 的 registration 時回傳 `true`；
- 已移除或不再是 current registration 時回傳 `false`。

它只移除 extension record 與該 extension 擁有的 policy。Observer、subscription、legacy hook 或任意 global mutation 必須由 extension 自己保存 disposer 並清理。

## Policy bridge 需求

First-stage policy module 的 requirement：

```js
{ id: "provider.contextWindow", abiVersion: 1 }
```

`id` 可用 numeric ID 或 readable name：

| ID | Name |
|---:|---|
| `0` | `renderer.messages` |
| `1` | `renderer.reset` |
| `2` | `renderer.toggleRedraw` |
| `3` | `provider.contextWindow` |
| `4` | `subagent.explicitModelRouting` |

同一 domain 不可同時用 numeric/readable alias 重複列出。

Policy entry：

```js
{
  id: "provider.contextWindow",
  handler(fallback, canonicalModel) {
    return canonicalModel.startsWith("custom-") ? 300000 : fallback
  },
}
```

Rules：

- `implementation.policies` 必須是 array；
- 每個 entry 要有 known ID 與 function handler；
- required bridges 與 handlers 必須完全一致；
- 不可多 handler 或少 handler；
- domain 不可已被其他 extension 擁有；
- renderer `0/1/2` 必須三個一起註冊或全部不註冊。

## Normal user extension 不能註冊 policy

Candidate 正常啟動時，immutable default extension 先擁有 `0–4`。因此以上 policy registration shape 只適用於：

- release-owned first-stage/default module；
- 不先載入 defaults 的 controlled lab；
- 未來重新建構的 candidate release。

它不是 `--renderpatch-extension` 的 override 機制。

## 同步 validation

Declared `AsyncFunction` 在 registration 時拒絕：

```js
{ id: 3, handler: async () => 372000 }
```

普通 function 不會在 registration 時被預先執行。若它在 query 時回傳 Promise、thenable、`undefined`、錯誤型別或超出範圍，runtime 會：

1. 拒絕 result；
2. 增加該 domain 的 `rejectedResultCount`；
3. 回傳 exact fallback。

詳見 [../api/policies.md](../api/policies.md)。

## Unsafe manifest 額外欄位

Exact-version raw access 需要：

```js
{
  unsafeRaw: true,
  requires: {
    policyApiVersion: 2,
    bridges: [],
    bridgeAbi: 1,
    rawSlotApi: "2.1.220.1",
    target: {
      version: "2.1.220",
      bridgeBuildId: "internal-sdk-2.1.220.1",
      stockSha256: "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081",
      artifactSha256: "97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157"
    },
    captureDomains: [{ id: "d3", abiVersion: 1 }]
  }
}
```

Unsafe mismatch 不會讓 valid zero-policy extension registration 失敗；只會省略 `activation.unsafe`。

詳見 [../api/unsafe.md](../api/unsafe.md)。

## 不應修改凍結的 manifest

[`manifests/internal-sdk-2.1.220.json`](../../manifests/internal-sdk-2.1.220.json) 是 candidate hash-pinned asset 與 frozen exact-version contract。不要修改它來更新文件狀態。未來 contract 變更應建立新的 schema/build/raw slot identity。
