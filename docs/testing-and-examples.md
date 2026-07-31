# 測試與 examples

本頁說明現有 harness 的用途，以及後續 `docs/examples/*.mjs` 的角色。這些測試證明本機 candidate/prototype 行為，不代表公開 SDK certification。

## 快速檢查

已具備本機 candidate artifact 時，先做 standalone release-integrity check：

```bash
candidate/install.sh --verify
```

安裝 locally verified candidate 後，再測 launcher environment：

```bash
claude-renderpatch-candidate --renderpatch-status
claude-renderpatch-candidate --renderpatch-diagnose
claude-renderpatch-candidate --version
claude-renderpatch-candidate --renderpatch-safe --version
```

`candidate/install.sh --verify` 專注 release artifact/layout/hash/mode/signature integrity；`--renderpatch-status` 還會檢查本機 proxy key、settings overlay 與 listener/process environment。

注意：fresh clone 不含被 `.gitignore` 排除的 signed candidate artifact。必須先從 exact stock Claude Code `2.1.220` 另外 build/sign 該 artifact，才能執行 installer。

## Harness 對照

| Harness | 驗證範圍 |
|---|---|
| `verify/preload-harness.py` | preload ordering、global、runtime APIs、trust、failure、env cleanup、bypass |
| `verify/bridge-static-2.1.220.py` | equal-length ranges、unique anchors、helper/query invariants、signing/version |
| `verify/bridge-behavior-2.1.220.py` | policy fallback semantic 與 live PTY redraw |
| `verify/raw-capture-static-2.1.220.py` | capture supplier、domain/slot/lifecycle invariants |
| `verify/raw-capture-behavior-2.1.220.py` | `d0–d5` publish/replace/stale clear/collision |
| `verify/candidate-launcher-harness.py` | installer/layout、wrapper parsing、default/user order、safe/status/diagnose |
| `verify/pty-harness.py` | direct renderer expand/collapse/resize |
| `verify/terminal-title-osc-2.1.220.py` | candidate terminal-title OSC preservation |

常用命令：

```bash
uv run verify/preload-harness.py
uv run verify/bridge-static-2.1.220.py
uv run verify/raw-capture-static-2.1.220.py
uv run verify/raw-capture-behavior-2.1.220.py
uv run verify/candidate-launcher-harness.py
uv run verify/terminal-title-osc-2.1.220.py
```

Semantic/live bridge harness 需要 disposable session：

```bash
uv run verify/bridge-behavior-2.1.220.py \
  --session /path/to/disposable-source-session.jsonl \
  --startup-seconds 3 \
  --phase-seconds 4
```

## 現有 preload examples

### 教學用途

- [`preload/examples/argv-version.mjs`](../preload/examples/argv-version.mjs)：preload 早於 argv parsing。
- [`preload/examples/console-prefix.mjs`](../preload/examples/console-prefix.mjs)：shared global realm。
- [`preload/examples/registry-probe.mjs`](../preload/examples/registry-probe.mjs)：legacy hook replacement、stale disposer、sync/async failure。

### 驗證 fixtures

- [`api-probe.mjs`](../preload/examples/api-probe.mjs)：Bun/Node/runtime/env surface。
- [`child-env-probe.mjs`](../preload/examples/child-env-probe.mjs)：child env scrubbing。
- [`alias-collision-bootstrap.mjs`](../preload/examples/alias-collision-bootstrap.mjs)：`globalThis.__rp` collision。
- [`target-mismatch-probe.mjs`](../preload/examples/target-mismatch-probe.mjs)：incompatible target fallback。
- [`throwing.mjs`](../preload/examples/throwing.mjs)：optional extension failure。
- [`patched-candidate-probe.mjs`](../preload/examples/patched-candidate-probe.mjs)：exact artifact/unsafe/capture。

### 相容性 probe

[`sdk-v2-probe.mjs`](../preload/examples/sdk-v2-probe.mjs) 會刻意 fabricated captures、invalid policies、collision、unsafe allow/deny 與 redaction checks。它不是 starter template。

## 開發者 examples 預留連結

整合階段將新增 scan-friendly examples：

- [docs/examples/read-status.mjs](examples/read-status.mjs)：zero-policy + `read.status()`。
- [docs/examples/observe-repl.mjs](examples/observe-repl.mjs)：`read.observe("d4", ...)`。
- [docs/examples/redraw-action.mjs](examples/redraw-action.mjs)：generation-checked Ink action。
- [docs/examples/app-subscribe.mjs](examples/app-subscribe.mjs)：direct callback subscription。
- [docs/examples/key-register.mjs](examples/key-register.mjs)：safe key allowlist + direct handler。
- [docs/examples/unsafe-capture.mjs](examples/unsafe-capture.mjs)：exact-artifact unsafe skeleton。

這些 path 由 main integration task 建立；本文件先保留 link contract。

## Extension 測試清單

### Safe read 測試

- capture absent；
- publish event；
- current generation success；
- stale result envelope；
- output 不含 raw content；
- observer disposer idempotent。

### Actions 測試

- invalid request；
- unavailable/stale capture；
- current generation success；
- captured method throw；
- app/key callback disposer；
- non-allowlisted key action denied；
- `repl.dispatch` 固定 denied。

### Policy 測試

Policy module 不能用 normal second-stage user path 測 override，因 default 已擁有 `0–4`。Controlled first-stage/lab 測試應包含：

- exact manifest/handler match；
- renderer `0/1/2` atomicity；
- absent/throw/Promise/thenable/undefined/type/range fallback；
- valid `false`/`0`；
- rejected-result count；
- dispose 後 fallback。

### Unsafe 測試

- `unsafeRaw` missing；
- wrong build/version/stock SHA/artifact SHA/ABI/raw slot API；
- stock-lab denied；
- exact signed artifact success；
- unauthorized domain `null`；
- replace/clear staleness；
- 不記錄 raw values。

## 文件驗證

本次 docs change 至少執行：

```bash
git diff --check
```

並人工確認：

- 只修改被指派的新文件；
- API method 與 `preload/bootstrap.mjs` 一致；
- release identity 與 candidate manifest 一致；
- normal user extension 不宣稱可覆寫 policy；
- policy `0–4` 與 capture `d0–d5` 分開；
- Banner/domain 5 明確標示 unbridged/future；
- 不宣稱 fresh clone installer works；
- 不要求修改 frozen hash-pinned manifest。
