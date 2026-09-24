# 專案狀態

## 2026-09-22 Mac grep/find repair

Selected build: `internal-sdk-2.1.261-darwin-arm64.4`; release ID:
`2.1.261-internal-sdk-darwin-arm64-2931bbef`. The `.3` release below is retained
unchanged for rollback. Only the Bash tool's `CLAUDE_CODE_EXECPATH` assignment
now selects stock native Claude for embedded ugrep/bfs instead of bare Bun.
Application startup, renderer, provider routing, settings and tool set are unchanged.

Verified: release integrity/signature, bridge diagnostics, actual Claude Bash call,
latest zsh snapshot grep/find and gitignore control, version, and live `say hi`.
The `.3`/`.4` asset comparison found no other differences after normalizing paths
and build identity. Existing unknown-model warning remains; no warning was suppressed.
See [repair/rollback/upgrade details](../reference/bridge-intent-2.1.261.md#grepfind-repair-2026-09-22).
No deployment or version verification was performed on Omarchy in this repair.

## 2026-09-06 Mac update

macOS arm64 now has a verified **2.1.261** source-graph bridge, using Bun **1.4.1**.
Build ID: `internal-sdk-2.1.261-darwin-arm64.3`; release ID:
`2.1.261-internal-sdk-darwin-arm64-16461071`.
Full capture counts match the Mac predecessor: d0=22 slots, d1=17 present slots,
d2=6, d3=16, d4=16, d5=9. Raw-slot identity is `2.1.261-darwin-arm64.1`.

The Mac builder, launcher, native asset loading, stock fallback, exact extension negotiation,
context/routing resolvers, and PTY expand/collapse/resize behavior are verified. See
[the current Mac record](../reference/bridge-intent-2.1.261.md) for evidence and limitations.
The Linux release below remains at 2.1.246; it was not upgraded by the Mac work.

## Linux 2.1.246 release

本頁記錄目前本機 verified release；它不是公開發布的 SDK 或 GitHub binary release。

## 本機 candidate 識別

| 欄位 | 值 |
|---|---|
| Release ID | `2.1.246-internal-sdk-linux-x64-7ebd85a5` |
| Claude Code | `2.1.246`, Linux x64 |
| Bridge build | `internal-sdk-2.1.246-linux-x64.6` |
| Identity SHA-256 | `a4daf31c711a640ef9e9693f494fc74e048a472e951d4546fcfd5e1f268b647e` |
| Runtime | bundled Bun `1.4.0` |
| Runtime API | `2` |
| Policy API | `2` |
| Bridge ABI | `1` |
| Raw slot API | `2.1.246-linux-x64.1` |
| Policy | `0–4` |
| Capture | `d0–d5` |

安裝位置：

```text
~/.local/share/claude-renderpatch/releases/2.1.246-internal-sdk-linux-x64.6/
~/.local/bin/claude-renderpatch-2.1.246
~/.local/bin/claude-bridge
```

`claude-bridge` 預設使用 immutable renderpatch release；可用
`CLAUDE_BRIDGE_BIN=~/.local/bin/claude` 明確回到 stock launcher。

## 已驗證行為

- 從 official stock ELF SHA-256
  `1a0a662dc1bb938eaec38545abce9a4a69113d7d7f7c5e1a553ea276617b906a`
  抽出 1,576 個 Bun records，保留 1,405 個 JavaScript modules 與 3 個 N-API modules。
- 八個 semantic sites 套用於七個 source modules；stock executable 未修改。
- Release launcher 驗證 identity、asset list、全部 graph/runtime/extension hashes 與唯讀 modes。
- `--renderpatch-safe` 使用同一份 patched graph，但不載入 preload；bridge calls 全部回退 stock semantics。
- Policy domains `0–4`：full-frame messages、destructive reset、toggle redraw、provider context window、explicit subagent routing。
- Capture domains `d0–d5`：publication/replacement、generation-safe cleanup、collision/throwing/non-callable fallback 全部通過。
- PTY 100x30 → 80x30：expand `10,962` bytes / ED2 `2` / ED3 `2`；collapse
  `6,278` bytes / ED2 `1` / ED3 `1`；resize `5,662` bytes / ED2 `1` / ED3 `1`。
- Expand、collapse、resize 都重播 `FIRST_RENDERPATCH_ANCHOR` 與 `LAST_RENDERPATCH_ANCHOR`。
- 真實 proxy routing：parent `gpt-5.6-luna`，explicit `opus` subagent 的 API response model
  為 `claude-opus-5`；最終結果 `SUBAGENT_ROUTE_OK`。

Verification commands：

```bash
python3 tools/build-source-release-2.1.246-linux.py --verify \
  --output "$HOME/.local/share/claude-renderpatch/releases/2.1.246-internal-sdk-linux-x64.6"

uv run verify/raw-capture-behavior-2.1.246-linux.py \
  --binary /path/to/raw-source-launcher

uv run verify/pty-harness.py "$HOME/.local/bin/claude-bridge" \
  --session DISPOSABLE_SESSION_UUID --cwd TRUSTED_PROJECT \
  --anchor FIRST_RENDERPATCH_ANCHOR --anchor LAST_RENDERPATCH_ANCHOR
```

## Packaging architecture

Claude Code 2.1.245+ 不再是可直接抽出的一個 monolithic `cli.js`。目前 Linux release：

1. 解析 ELF `.bun` payload 與 52-byte module records；
2. 抽出完整 ESM chunk graph、assets、N-API modules；
3. 將 `/$bunfs/root/...` references 改寫到 immutable release path；
4. 在 source modules 套用 semantic patches；
5. 搭配 exact Bun 1.4.0 runtime、bootstrap、extensions 與 hash manifest；
6. 直接 build 到最終 versioned path，因 graph imports 綁定該 absolute release path。

因此 release directory 不可搬移；升版應建立新的 immutable directory，而不是覆寫現有 release。

## Exact-version unsafe 存取

Raw slots 仍是 exact-version/exact-build contract，可能包含 conversation、store、setter、React refs、
terminal controls、handler map 與 callback。它不是跨版本 API。Normal facade 仍不允許任意 command
dispatch、permission bypass 或 dialog answering。

## 已知 tradeoffs

- Full-frame mode 關閉 Claude 2.1.246 的 virtual/alternate-screen rendering，保留 native terminal scrollback。
- Expand、collapse、resize 的 authoritative reset 會送 ED2 + ED3，可能清除 Claude 上方的 shell scrollback。
- 每次 frame 載入所有目前 display-state messages；超大 session 會提高 memory/CPU 成本。
- 「Full」只包含 Claude Code 目前已載入的 display state，不能復原 compaction/resume pruning 已丟棄的 records。
- Source graph 綁定 release absolute path；launcher/asset verification 會增加約數百毫秒內的固定啟動成本。

## 仍未完成

- 沒有公開 release channel、package registry、GitHub Release 或跨機器 installer。
- Windows/ConPTY packaging 尚未實作。
- macOS 2.1.246 source-graph packaging 尚未移植；repo 只保留舊版 byte-patch/reference candidate。
- Banner renderer customization、policy domain 5、arbitrary command dispatch 仍未 bridge。
- `read.sr.trace` 仍只是 preview alias；generic `actions.invoke()` 仍不接受 callback/handler 參數。

不要宣稱 fresh clone 可直接執行 binary release；fresh clone 仍需要 exact stock 2.1.246 Linux x64
binary與 Bun 1.4.0，然後執行 source-release builder。
