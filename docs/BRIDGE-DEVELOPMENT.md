# Bridge 開發指南

Binary bridge 把 Claude Code 2.1.220 closure-bound internals 接到外部 runtime。它是 exact-version prototype，不是通用或公開 SDK ABI。

## 精簡 facade

```js
globalThis.__rp.q(policyDomainId, fallback, ...primitivePayload)
globalThis.__rp.c(captureDomainId, generation, presenceBitmap, slotsOrNull)
```

Property 是 non-enumerable、non-writable、non-configurable。它只公開 `q` 與 `c`；完整 extension runtime 位於：

```js
globalThis[Symbol.for("claude-code-renderpatch.runtime")]
```

## Collision 與 stock-safe 失敗處理

若 `globalThis.__rp` 已有 incompatible value：

1. 不覆寫原值；
2. 標記 collision；
3. bridge inactive；
4. policy 使用 fallback；
5. capture no-op。

Patched helper 也必須處理 absent/non-callable method、throwing getter 與 throwing call。

## `q` policy 控制平面

```text
q(domain, fallback, ...payload)
  -> validated result 或 exact fallback
```

目前 domain 只有 `0–4`：

| ID | Policy | Binary semantic site |
|---:|---|---|
| `0` | `renderer.messages` | early Messages pipeline |
| `1` | `renderer.reset` | full-reset planner |
| `2` | `renderer.toggleRedraw` | transcript toggle |
| `3` | `provider.contextWindow` | raw context-window resolver tail |
| `4` | `subagent.explicitModelRouting` | first explicit same-family gate |

Minified names/offset 只適用 2.1.220，不是 public identifier。

## `c` capture 資料平面

```text
c(domain, generation, presenceBitmap, slotsOrNull)
  -> undefined
```

Return value 永遠忽略。

Publish/replace：non-null positional array + valid bitmap。

Clear：

```js
c(domain, matchingGeneration, 0, null)
```

Stale cleanup 不會刪掉 newer capture。

Invalid domain/generation/bitmap、缺少 bitmap 指定 slot、nonzero bitmap + null slots、static nonzero generation、older/conflicting replacement 都是 no-op。

## 2.1.220 的九個 physical ranges

| Range | 功能 |
|---|---|
| provider context-window | policy 3 + shared bridge helpers/state |
| renderer reset | policy 1 |
| key-provider payload | `d5` payload/generation |
| subagent/static-model | policy 4 + `d0` |
| key-provider lifecycle | `d5` publish/cleanup |
| app provider | `d2` |
| Messages | policy 0 + `d3` |
| transcript toggle | policy 2 |
| late REPL/static Ink | `d4` + guarded `d1` |

Exact offset、length、byte-budget compaction 與驗證紀錄以 [`reference/bridge-intent-2.1.220.md`](../reference/bridge-intent-2.1.220.md) 為準。

## Capture supplier 生命週期

| Domain | Lifecycle | Supplier 邊界 |
|---|---|---|
| `d0` | static generation 0 | model/context/subagent dependencies 初始化後 |
| `d1` | static + lookup-live | 全部 static slots 可用後；current Ink 使用時 lookup |
| `d2` | provider | app provider effect + matching cleanup |
| `d3` | render-latest | final rendered Messages array 可用後 |
| `d4` | render-latest | late REPL control object 可用後 |
| `d5` | provider | live interactive keybinding provider lifecycle |

Generation 使用 monotonic counter，不使用 timestamp/randomness。

## 權威來源順序

Bridge 開發時依序使用：

1. `preload/bootstrap.mjs`：consumer/validation contract；
2. `reference/bridge-intent-2.1.220.md`：目前九站實作；
3. `candidate/release-manifest.json`：本機 candidate identity；
4. frozen `manifests/internal-sdk-2.1.220.json`：domain、ABI、slot order；
5. `reference/internal-sdk-map.md`：semantic/minified landmark；
6. `REPATCHING-PLAYBOOK.md`：更新版 rediscovery 流程。

Frozen manifest 是 hash-pinned asset。不要修改它來更新 `planned` 文案；contract 改變時建立新的 build/raw slot identity。

## Banner 尚未 bridge

Banner renderer 的 exact 2.1.220 研究：

- [internals/BANNER-RENDERER-2.1.220.md](internals/BANNER-RENDERER-2.1.220.md)

目前沒有 Banner capture/action/policy。研究中 proposed domain 5 不是 runtime API 2，不能直接加入 user manifest。

## 新版本維護規則

1. 不重用舊 minified name 或 offset。
2. 從 stable semantic anchor 重新定位。
3. 先重建 exact stock fallback/control flow。
4. Replacement 必須 equal-length 且位於 live `__BUN`。
5. Old anchor 唯一、new pattern 預先不存在。
6. Policy payload 保持 primitive、narrow。
7. React supplier 不改 hook count/order。
8. Capture cleanup generation-safe。
9. Static slots 全部 initialized 後才 publish。
10. Patched-without-preload 與 safe mode 保持 stock behavior。
11. 建立新的 release metadata/hash/signature。
12. 跑 static、semantic、capture、PTY、launcher、terminal-title verification。

## Packaging 注意事項

Repository 內的 build scripts、launcher、manifest 不代表 fresh clone 已含 signed candidate artifact。Bridge developer 必須先產生/取得 exact artifact，再做 installer/release verification；不要把 ignored local artifact 當成 Git 內可重建資源。
