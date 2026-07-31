# 專案狀態

本頁用明確分類說明目前已驗證範圍。這是本機 verified release candidate／prototype，不是公開發布的 SDK。

## 本機驗證的 candidate 識別資訊

| 欄位 | 值 |
|---|---|
| Release ID | `2.1.220-internal-sdk-2.1.220.1-97dfb182` |
| Claude Code | `2.1.220`, macOS arm64 |
| Runtime API | `2` |
| Legacy registry API | `1` |
| Policy API | `2` |
| Bridge ABI | `1` |
| Raw slot API | `2.1.220.1` |
| Policy | `0–4` |
| Capture | `d0–d5` |

精確 hash 與 asset metadata 以 [`candidate/release-manifest.json`](../candidate/release-manifest.json) 為準。

目前狀態：

- feature branch：`docs/internal-sdk-2.1.220-guide`；
- 尚未 merge 到 `main`；
- 沒有 GitHub PR；
- 沒有 GitHub Release；
- 本機有 locally installed immutable candidate，不代表已有 public distribution。

Verification command 的責任不同：

- `candidate/install.sh --verify`：獨立檢查 release artifact/layout/hash/mode/signature integrity，不依賴 normal multi-provider runtime environment。
- `claude-renderpatch-candidate --renderpatch-status`：除了 release/assets verification，也會驗證本機 proxy key、settings overlay 與 listener/process environment；它不是純 artifact-only check。

## 1. 本機已驗證可運作

已在本機 candidate/prototype 驗證：Bun preload ordering、shared global、runtime/collision handling、policy `0–4`、capture `d0–d5`、default-first/user-second、safe read、validated actions、capture observe、env scrubbing、safe/status/diagnostic path，以及九個 bridge range 的 static/semantic/PTY verification。

## 2. Exact-version unsafe 存取

`activation.unsafe` 已實作，但只適用於 Claude Code `2.1.220`、bridge build `internal-sdk-2.1.220.1`、exact signed artifact、bridge ABI `1`、raw slot API `2.1.220.1` 與 manifest 明確要求的 capture ABI。

它不是跨版本 API。Raw slots 可能含 conversation、store、setter、React refs、terminal controls、handler map 與 callback。

## 3. 刻意拒絕的功能

- `repl.dispatch` 固定回傳 `denied`。
- 非 safe key allowlist 的 action 固定拒絕。
- stale generation 不執行 mutation。
- normal facade 不回答 dialog、不繞過 permission、不直接呼叫 raw handler。
- project/CWD autoload 不允許。
- unsafe negotiation 不完整時省略 `unsafe`。

Safe key allowlist：

```text
repl.toggleTranscript
repl.showAll
ink.redraw
```

## 4. 實作缺口

- `actions.list()` 包含 `app.subscribe` 與 `key.register`，但 generic `actions.invoke()` 無 callback/handler 參數；必須直接呼叫。
- `read.sr.trace` 目前只是 `read.sr.preview` alias，不是完整 resolver trace。
- `read.msg.snapshot` 實際是 bounded summary export，不回傳 raw message content。
- `repl.dispatch` interface 已存在，但 allowlist/dispatch implementation 尚未開放。

## 5. Packaging／release 缺口

- 目前沒有公開 release channel、相容性承諾或 package registry。
- Git repository 不包含本機已驗證、被 ignore 的 signed candidate binary artifact。
- 因此 **fresh clone 不能直接執行 `candidate/install.sh` 完成安裝**。
- Fresh clone 必須先取得 exact stock Claude Code `2.1.220`，另外執行 build 流程產生被 `.gitignore` 排除的 patched/signed artifact，之後 installer 才有完整輸入。
- Installer、launcher、manifest 與 build tools 的存在，不等於 clone 內含可安裝 artifact。
- 目前 locally installed immutable candidate 是本機驗證結果，不是 GitHub 可下載的公開發行版。

不要宣稱「clone 後直接執行 installer 即可」。

## 6. 未來／尚未 bridge 的範圍

尚未納入 runtime API 2：

- Banner renderer customization；
- proposed policy domain 5；
- Linux/Windows candidate packaging；
- 跨 Claude Code 版本的穩定 raw slot ABI；
- arbitrary command dispatch；
- public SDK/release lifecycle。

Banner 的 exact 2.1.220 internals map 已完成研究，但尚未 bridge：

- [internals/BANNER-RENDERER-2.1.220.md](internals/BANNER-RENDERER-2.1.220.md)

Proposed domain 5 不是目前 policy ID 或 extension manifest requirement。

## 凍結的 manifest

[`manifests/internal-sdk-2.1.220.json`](../manifests/internal-sdk-2.1.220.json) 是 hash-pinned frozen contract。它保存 domain、ABI、target 與 slot order，也保留 bridge build 前的 `planned` 狀態。

**不要修改 frozen manifest 來修正文案狀態。** 新版本應建立新的 contract/build identity。
