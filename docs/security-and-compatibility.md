# 安全性與相容性

Extension 是在 Claude Code process 內執行的 trusted same-user code。Runtime 提供 trust check、redaction 與 fail-safe boundary，但不是 sandbox。

## Entry path 信任檢查

Bootstrap 只接受明確指定的 entry module，要求：

- absolute path；
- resolve 後位於 current user home；
- path component 無 symlink；
- final target 是 regular file；
- file 與檢查到的 parent component 由 current user 擁有；
- 不得 group/world writable。

## 信任檢查未涵蓋的範圍

- transitive imports；
- Unix mode 以外的所有 macOS ACL 語意；
- runtime download；
- native module；
- extension 產生/eval 的 code；
- validation 後的實際行為。

Entry file import 的所有內容都應視為同等信任。

## 禁止 project autoload

Runtime 不掃描：

```text
$PWD
.claude/
package.json
repository plugin directory
relative module name
```

Claude Code 常在未信任的 repository 內啟動；project-relative autoload 會把「開啟 repo」變成 same-user arbitrary code execution。

## Same-realm 權限

Trusted module 可以讀寫 user files、修改 globals/env/argv、spawn process、連網、`process.exit`、永久 await，或在 throw 前留下 mutation。

Bootstrap 能 report 普通 import/activation failure，但不能 rollback same-realm side effect。

Recovery：

```bash
claude-renderpatch-candidate --renderpatch-safe
```

## 環境變數清理

Bootstrap 在 extension loading 前刪除 one-shot env：

```text
BUN_OPTIONS
CLAUDE_RENDERPATCH_MODULE
CLAUDE_RENDERPATCH_USER_MODULE
CLAUDE_RENDERPATCH_ACTIVE
CLAUDE_RENDERPATCH_TARGET
CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID
CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256
CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION
```

避免 Bun/Claude child process recursive preload 或繼承 artifact metadata。

Normal launcher 也拒絕 inherited values；status/safe paths 會 scrub。

## 拒絕授權（fail closed）

以下情況不授權行為：

- untrusted entry path；
- incompatible manifest/API/bridge requirement；
- duplicate policy ownership；
- incomplete renderer atomic bundle；
- invalid/stale action；
- non-allowlisted key action；
- unsafe exact-target mismatch。

## 回到 stock behavior（fail open）

以下情況回到 stock fallback，而不是變得 permissive：

- no preload；
- inactive/colliding compact facade；
- unregistered/throwing/async/invalid policy；
- invalid capture publication；
- stale cleanup；
- optional trusted module 的普通 throw/rejection。

## Safe read 邊界

Safe read 會 bounded/redact：

- prompt/message/tool/task content；
- secret/credential-like fields；
- handler/callback；
- live store/array/ref/setter；
- terminal frame；
- full operational path；
- telemetry payload history。

但 safe metadata 仍可能包含 model name、count、mode 等資訊；對外發布前仍需判斷資料敏感度。

## Validated action 邊界

- generation/liveness check；
- stale action 無 side effect；
- key action strict allowlist；
- `repl.dispatch` intentionally denied；
- normal facade 不回答 dialog、不繞過 permission。

`app.subscribe` 與 `key.register` 是 direct callback method，不是 generic `actions.invoke()`。

## Unsafe 存取邊界

Exact-version unsafe 可公開 message、store、setter、ref、callback、terminal control、handler map。禁止 network expose、logging/serialization 或跨版本重用。

詳見 [api/unsafe.md](api/unsafe.md)。

## 相容性對照

| Surface | 一般 Claude 更新是否要 repatch | 說明 |
|---|---:|---|
| External preload/runtime | 通常不需要 | 仍需 smoke test Bun preload/global/runtime APIs |
| Safe user extension | 通常不需要 | 依賴 runtime API compatibility |
| Policy/capture binary bridge | 需要 | closure-bound minified suppliers 是 exact-version |
| Raw slot extension | 需要重新 negotiation | exact artifact/build/raw slot API |
| Direct 2.1.219 patch | 需要 | byte pattern/version pinned |
| Banner renderer | 尚未 bridge | proposed domain 5 非目前 API |

## Packaging 相容性缺口

目前 feature branch 尚未 merge 到 `main`，沒有 GitHub PR 或 GitHub Release。Repository 沒有公開 release distribution，也不含被 `.gitignore` 排除的 signed candidate binary。

Fresh clone 必須先取得 exact stock Claude Code `2.1.220`，另外 build/sign patched artifact，之後才能使用 `candidate/install.sh`。本機 locally installed immutable candidate 只代表本機驗證成功，不代表外部可取得的公開發行版。

`candidate/install.sh --verify` 是 standalone release-integrity check；`claude-renderpatch-candidate --renderpatch-status` 還會驗證 local proxy key、settings overlay 與 listener/process environment。

Hash-pinned frozen manifest 不應為了更新說明而修改；新 binary/slot contract 應使用新的 build identity。
