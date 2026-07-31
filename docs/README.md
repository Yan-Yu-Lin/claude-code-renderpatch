# Renderpatch 開發者文件

這組文件描述目前在本機完成驗證的 **Claude Code 2.1.220 release candidate／prototype**。它不是 Anthropic 公開發布或承諾相容性的 SDK，也不是可直接從 fresh clone 重建的正式 release。

目前文件與 prototype 位於 feature branch `docs/internal-sdk-2.1.220-guide`，尚未 merge 進 `main`，也沒有 GitHub PR 或 GitHub Release。Repository 中的 locally installed immutable candidate 與「可供外部下載的公開發行版」是兩件不同的事。

目標是讓開發者或 AI 不必逆向閱讀整份 `preload/bootstrap.mjs`，就能理解目前實作並撰寫安全的 second-stage user extension。

## 先讀哪一份

| 目的 | 文件 |
|---|---|
| 第一次理解整體 | [architecture.md](architecture.md) |
| 確認目前哪些能用 | [PROJECT-STATUS.md](PROJECT-STATUS.md) |
| 查 domain 與 capability | [CAPABILITY-MAP.md](CAPABILITY-MAP.md) |
| 寫第一個 user extension | [extensions/getting-started.md](extensions/getting-started.md) |
| 查 extension manifest | [extensions/manifest-and-registration.md](extensions/manifest-and-registration.md) |
| 查 runtime/read/actions API | [api/runtime.md](api/runtime.md)、[api/read.md](api/read.md)、[api/actions.md](api/actions.md) |
| 理解 policy 與 raw capture | [api/policies.md](api/policies.md)、[api/unsafe.md](api/unsafe.md) |
| 維護 binary bridge | [BRIDGE-DEVELOPMENT.md](BRIDGE-DEVELOPMENT.md) |
| 理解信任與版本邊界 | [security-and-compatibility.md](security-and-compatibility.md) |
| 驗證或閱讀 examples | [testing-and-examples.md](testing-and-examples.md) |
| 研究未 bridge 的 Banner renderer | [internals/BANNER-RENDERER-2.1.220.md](internals/BANNER-RENDERER-2.1.220.md) |

## 權威來源順序（Source of truth）

文件與實作若有衝突，依照以下順序判定：

1. [`preload/bootstrap.mjs`](../preload/bootstrap.mjs)：實際 runtime、read、actions、policy validation、unsafe negotiation 與 extension loader 行為。
2. [`candidate/claude-renderpatch-candidate`](../candidate/claude-renderpatch-candidate) 與 [`candidate/release-manifest.json`](../candidate/release-manifest.json)：launcher 行為、本機驗證的 candidate identity 與 asset metadata。
3. [`reference/bridge-intent-2.1.220.md`](../reference/bridge-intent-2.1.220.md)：已實作的 2.1.220 九個 bridge range 與驗證紀錄。
4. [`manifests/internal-sdk-2.1.220.json`](../manifests/internal-sdk-2.1.220.json)：已凍結的 domain ID、ABI、target constraint 與 raw slot 順序。
5. [`reference/internal-sdk-map.md`](../reference/internal-sdk-map.md)：人類可讀的 exact-version semantic map 與 minified landmark。

`internal-sdk-2.1.220.json` 是 hash-pinned、凍結的設計契約。裡面的 `planned` 狀態文字保留當時的設計歷史；**不要為了讓文字看起來更新而修改這份 manifest**。目前實作狀態應由 release metadata、bridge intent 與本文件說明。

## 三條不同路徑

### 直接 binary patches

2.1.219 的 renderer、context-window 與 subagent-routing 腳本是版本固定的直接 byte patch。它們仍是可用的歷史 recipe 與 rediscovery 參考，但不是本文件的 extension API target。

### 零 binary patch 的 preload lab

`preload/claude-preload-lab` 證明 Bun preload 可以在 Claude Code 解析 argv 前執行並共享 global realm。它能碰到 runtime-reachable surface，但 stock binary 不會自動公開 closure-bound renderer、React state 或 resolver internals。

### 2.1.220 internal-SDK 候選版本

本文件主要描述這條路徑：外部 preload runtime 加上 exact-version 九站 bridge，提供 policy `0–4`、capture `d0–d5`、safe read、validated actions 與 exact-artifact unsafe access。

## 寫 user extension 前必須知道

正常 candidate 啟動時：

1. immutable `default.mjs` 先載入；
2. 它擁有 policy domain `0–4`；
3. `--renderpatch-extension` 指定的 user module 第二個載入。

因此一般 user extension 應使用：

- zero-policy manifest；
- `runtime.read`；
- `runtime.actions`；
- `runtime.read.observe`；
- legacy named hooks；
- 必要時才使用 exact-version `unsafe`。

一般 user extension **不能覆寫 policy domain `0–4`**。

## 目前的重要邊界

- `repl.dispatch` 雖出現在 action 清單，實作目前永遠回傳 `denied`。
- `app.subscribe` 與 `key.register` 需要 callback/handler，只能直接呼叫，不能透過 generic `actions.invoke()`。
- safe key action allowlist 只有 `repl.toggleTranscript`、`repl.showAll`、`ink.redraw`。
- Banner renderer 尚未 bridge；研究文件中的 proposed domain 5 不是目前 API。
- fresh clone 不含本機已驗證、被 ignore 的 signed candidate binary；不要宣稱 clone 後執行 installer 就能完成安裝。

完整分類見 [PROJECT-STATUS.md](PROJECT-STATUS.md)。
