# Exact-version unsafe API 參考

Unsafe facade 直接公開 binary capture 的 raw live values。只有 safe read/actions 無法表達需求時才使用。

它是：

- same-process；
- local-only；
- exact-version/exact-artifact；
- mutable、sensitive；
- 不保證 forward compatibility；
- 不提供 sandbox。

## Negotiation manifest 結構

```js
const manifest = {
  id: "unsafe-example",
  version: "1.0.0",
  schemaVersion: 1,
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
    captureDomains: [
      { id: "d3", abiVersion: 1 }
    ]
  }
}

const activation = runtime.registerExtension(manifest)
```

預計整合範例：

- [docs/examples/unsafe-capture.mjs](../examples/unsafe-capture.mjs)

## 全部必須吻合

1. `unsafeRaw === true`；
2. verification mode 是 `signed-bridge-artifact`；
3. bridge build ID；
4. bridge ABI；
5. raw slot API；
6. target version；
7. stock provenance SHA；
8. actual executable SHA 等於 requested artifact SHA；
9. 每個 requested capture domain/ABI。

`stockSha256` 與 `artifactSha256` 是不同事實。Stock provenance 不能取代 patched artifact identity。

`stock-lab` 不能啟用 unsafe。

## 拒絕時的行為

Unsafe mismatch 不會拒絕 valid zero-policy extension；只省略 property：

```js
if (!("unsafe" in activation)) {
  // Exact unsafe contract 未滿足。
}
```

Runtime 不回傳空的 permissive proxy。

## `unsafe.capture(domain)`

```text
capture(
  domain: number | "d0" | ... | "d5" | captureName
): RawCapture | null
```

Domain 必須列在 manifest `captureDomains`。

Return：

```text
{
  domainId: number,
  generation: number,
  presenceBitmap: number,
  slots: unknown[]
}
```

Wrapper frozen，但 `slots` 與裡面的值是 raw live references，不 clone、不 freeze。

Unknown、unavailable、未授權 domain 回傳 `null`。

## Presence bitmap 規則

Bit `N` 表示 slot `N` 是否存在；optional slot 缺少時不會讓後續 index 位移。

```js
function hasSlot(capture, index) {
  return Math.floor(capture.presenceBitmap / 2 ** index) % 2 === 1
}
```

不要用 truthiness 判斷 presence；合法 slot value 可能是 `false`、`0`、`null` 或 `undefined`。

## Capture domain 對照

| ID | Lifecycle | Slots | 內容 |
|---|---|---:|---|
| `d0` | static | 22 | model/context/subagent helpers |
| `d1` | static + lookup-live | 24 | Ink/terminal/dialog/diagnostics |
| `d2` | provider | 6 | app store/state/subscription |
| `d3` | render-latest | 16 | Messages arrays/cap/render state |
| `d4` | render-latest | 16 | REPL store/setters/catalogs/refs/callbacks |
| `d5` | provider | 9 | key manager/bindings/refs/contexts/chord |

Exact positional order：

- [`manifests/internal-sdk-2.1.220.json`](../../manifests/internal-sdk-2.1.220.json)
- [`reference/internal-sdk-map.md`](../../reference/internal-sdk-map.md)

Frozen manifest 是 hash-pinned contract；不要修改它來反映文件狀態。

## Stale reference 處理

Raw capture object 不可撤銷。Domain `replace`/`clear`、generation 改變、provider unmount 或 REPL rerender 後，舊 reference 應視為 stale。

不要跨 generation 保留 message array、React ref、store、setter、callback 或 handler map。

## 敏感資料

Raw slots 可能包含 conversation/tool content、prompt、task state、model/routing decision、terminal controls、dialog store、submit callback、handler registry 與 telemetry function。

禁止將 raw slots：

- 寫入 status/log/analytics/crash report；
- network expose；
- 當成跨版本 API；
- 由 remote caller 直接操作。

Unsafe capture 不等於 policy override；只有已 bridge 的 `q` call site 能改變對應 lexical decision。
