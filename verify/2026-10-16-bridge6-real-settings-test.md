# claude-bridge `.6` 真實設定實測(2026-10-16)

測試者:隊友 `bridge6-test`(session `35207cb5` 的 lead 派出)。時間一律是台灣時間(UTC+8);transcript 裡的時間戳是 UTC,已經換算過。

## 結論

**`.6` 只修好了一半。結果取決於 session 的 permission mode。**

| permission mode | 隊友派背景 helper | 隊友背景 Bash | Esc |
|---|---|---|---|
| `default`(manual)/ `bypassPermissions` | **通過**:helper 的完整結果回到隊友,lead 什麼都沒收到 | **通過** | **通過** |
| **`auto`**(`~/.claude/settings.json` 的 `defaultMode`,新 session 預設就是這個) | **失敗**:隊友不會再卡住,但 helper 的**報告內容還是送到 lead**,隊友只收到一句「報告已經用訊息送給你了,去那裡讀」,其實它根本沒收到 | **通過**(Bash 不走這條路) | **通過**(shell 和 helper 都活著、也都通知到隊友;但 helper 的報告內容一樣送到 lead) |

最近 4 天 Arthur 真實 session 最後的 permission mode:`auto` 34 個、`default` 22 個、`bypassPermissions` 14 個。session `35207cb5` 本身是 `default`。所以大部分新開的 session 會踩到 `auto` 這個問題。

原本 `.6` 的 gate 都用 `--permission-mode bypassPermissions` 跑,所以沒抓到這個問題。

## 根本原因:auto mode 的 `SubagentHandback`

- 在 auto mode 下,背景子代理最後要呼叫 `SubagentHandback` 工具交報告(`chunk-pbc3rb7p.js`:`F8o(e){return e.mode==="auto"&&YQe()}`,`YQe()` = env `CLAUDE_CODE_SENDMESSAGE_HANDBACK` 或 flag `tengu_lively_waffle`,預設 true)。task-notification 的 `<result>` 不再附報告,只寫:`This agent's report was delivered to you as a message from "<id>" (its SubagentHandback call). Read it there; it is not repeated here.`
- 報告送給誰,是 `chunk-j6afv9nb.js` 裡 `SubagentHandback.call()` 決定的:
  `b=Pn(O)&&O.isBackgrounded&&!Jgn(i.recipient,n.taskRegistry)?ze():i.recipient`
  `Jgn(e)` = `e===ze()||nXe(task)`,而 `nXe` 只接受 `local_agent`(`chunk-v1gtm86q.js`)。收件人是 `in_process_teammate` → `Jgn` 回 false → `b = ze()` = **lead**。報告就被塞進 lead 的 message queue,以 `Another Claude session sent a message: <agent-message from="..."> [Subagent hand-back] ...` 的形式出現在 lead 的對話裡。
- `.6` 的 T2 只在 `Ymt()` 加了 `__rpLiveTeammate`(task-notification 的 owner),**沒有改 `Jgn` / `z8o` 這條 hand-back 路徑**。所以通知送對了(給隊友),內容卻送錯了(給 lead)。
- 在 `default` / `bypassPermissions` 下 `F8o` 是 false,沒有 hand-back 合約,報告直接放在 task-notification 的 `<result>` 裡,而 `.6` 已經把這個通知送給隊友,所以完全正常。

修法建議(下一個 release `.7`,這次沒動):在 hand-back 收件人判斷(`Jgn` 或 `SubagentHandback.call()` 的 `b=`)也接受 live 的 in-process teammate,並把報告送進隊友會讀的路徑(例如用 `agentId`=隊友 enqueue,讓 T4/T5 讀到)。比較簡單的做法是:caller 是隊友時不給 hand-back 合約(`Bt=false`),報告就會回到 `<result>`。新的 gate 一定要在 `auto` mode 下跑。

這就是 incident 3(`physics-toys`)的「reviewer 的訊息出現在 lead,不是隊友」。在 `.6` + auto mode 下,隊友不會再被 foreground 卡住,但會變成「idle 等一份已經送到 lead 的報告」。

## 怎麼測的

- Launcher:`~/.local/bin/claude-bridge`(→ `.6`)。控制組直接指 `.5` / `.6` release 的 `claude-renderpatch-candidate`。
- **用 Arthur 的真實設定**:沒有 `env -i`,沒有 `--setting-sources`。只把從父 session 繼承來的 `CLAUDE*`/`ANTHROPIC_*`/`CMUX*`/`TMUX` 環境變數拿掉,模擬在終端機新開一個 session。真實 hook 全部都有跑:`subagent_guard.sh`、`teammate_inbox_wake.py`、memory hook、`pre_tool_use.py`、logger 等等。腳本:`verify/fixtures/bridge6-real-launch.sh`、`bridge6-real-send.sh`。
- 在 tmux 裡要加 `--teammate-mode in-process`:Arthur 的 `teammateMode` 是 `auto`,在 tmux 裡會把隊友開成 tmux pane(另一個 process)。第一輪(round 0)就是這樣,已經丟掉。Arthur 平常在 cmux 裡跑,隊友是 in-process,所以這樣測才對。
- Lead `sonnet`,隊友 `haiku`,case C 的 reviewer `sonnet`。Prompt:`verify/fixtures/bridge6-real-prompt-{a,b,c,c2,d,e}.txt`。
- 量測:transcript 自己的時間戳。新工具 `verify/teammate-bg-measure-2.1.291.py` 會列出每個完成事件(queue enqueue)、誰的對話裡出現了 task-notification 或 hand-back。完整輸出在 `verify/2026-10-16-bridge6-real-settings-evidence.txt`。
- 一次性的提示:第一個 session 跳出「auto mode classifier billing」通知(proxy 不相容,但 auto mode 照常運作),按了 `y`。這會在 `~/.claude.json` 寫入 `autoModeClassifierBillingNoticeAcknowledgedAt`,Arthur 自己的 session 之後就不會再跳這個通知。其他設定都沒動。

## 各 case 結果

Session id 都在 `~/.claude/projects/-private-tmp-bridge6-test-<case>/`。

### A:隊友 → 背景 helper(incident 1、3)

| 執行 | release / mode | Agent 呼叫回傳 | 隊友繼續工作 | helper 結果送到哪 | 隊友有沒有照結果行動 | 判定 |
|---|---|---|---|---|---|---|
| `a`(`c565ee7a`) | `.6` / auto | 2.67 s,async | 是(做了 3 + 6 個 call) | 通知 07:08:44.93 → 隊友;**報告 `HELPER-A RESULT 7341` 07:08:44.76 → lead** | **否**:又輪詢 6 次後回報 lead「沒收到結果」,沒寫 `acted.txt` | **失敗** |
| `a-def`(`a34e03b2`) | `.6` / default | 0.16 s,async | 是 | 07:25:30.97 完成 → 隊友在下一個 tool round 收到(含報告) | 是:07:25:35 寫 `ACTED-ON-7341`,lead 什麼都沒收到 | **通過** |
| `a-bypass`(`2a98efc8`) | `.6` / bypass | 0.18 s,async | 是 | 07:15:45.81 完成 → idle 的隊友 **0.33 s 後被叫醒** | 是:`ACTED-ON-7341` | **通過** |
| `a-r5`(`5e3f9146`) | `.5` / auto,控制組 | **63.9 s,foreground 卡住** | 否 | 報告 → lead;隊友只看到「helper 沒交報告」,要自己 SendMessage 叫回 helper 才拿到 | 拖了約 3 分鐘才完成 | incident 1 重現 |

Agent 呼叫在 auto mode 要 2.6–4.8 s,是 auto mode classifier 在審這個 Agent 呼叫,不是 `.6` 造成的;default/bypass 是 0.16–0.19 s。

### B:隊友背景 Bash,然後 idle(incident 2、4)

`b`(`.6` / auto,`98856d6b`):隊友一次開了兩個背景指令就結束 turn。

| 指令 | 完成 | 隊友被叫醒 | 延遲 | 隊友回報 |
|---|---|---|---|---|
| `FAKE-BUILD-B`(故意 exit 2) | 07:08:39.839 | 07:08:39.904 | **0.07 s** | `BRAVO GOT FAKE-BUILD-B exit=2 output=FAILED` |
| `LONG-JOB-B`(`sleep 45; echo DONE_B`) | 07:08:50.393 | 07:08:50.615 | **0.22 s** | `BRAVO GOT LONG-JOB-B exit=0 output=DONE_B` |

**通過**(auto mode 也通過,因為 Bash 不走 hand-back)。失敗的 build 也會叫醒它,這正是 incident 4 的情況。

控制組 `b-r5`(`.5` / auto,`857fce75`):兩個指令 07:19:18 和 07:19:35 完成,**隊友一直沒被叫醒**。12 分鐘後關掉時還在 idle,lead 也沒收到任何東西。incident 2/4 重現。

### C:實際的 review 流程(incident 3 縮小版)

| 執行 | mode | reviewer 怎麼交結果 | 結果 | 判定 |
|---|---|---|---|---|
| `c`(`d9205f24`) | auto | prompt 叫 reviewer 把檔案路徑 **SendMessage 給 charlie** | 07:08:24 reviewer 傳訊 → 07:08:30 隊友收到(inbox-wake hook 有紀錄)→ 讀 review、修 `avg()` 空 list、回報。但 reviewer 最後的 hand-back `REVIEW-C DONE` 也送到 lead | 通過,但只因為 reviewer 被明確要求 SendMessage |
| `c2`(`2b7902cd`) | auto | **自然寫法**:reviewer 直接回報 findings | 兩份 review(隊友不小心派了兩個)07:22:15 都送到 **lead**;隊友只收到「去別處讀」,07:22:29 結束 turn 說 `CHARLIE WAITING FOR REVIEW`,**`calc.py` 一直沒修** | **失敗**(就是 incident 3) |
| `c-def`(`266035a8`) | default | 自然寫法 | review 07:24:57.50 完成;隊友正在跑 `sleep 8`,07:25:03 下一個 tool round 收到;07:25:07 修好;07:25:09 回報 | **通過** |

另外看到一個(upstream 的)限制:`c2` 的隊友想用 `TaskStop` 停掉自己多派的 reviewer,被拒絕:`Task ac394… is owned by ac394…; agent acharlie-… cannot stop it`(`chunk-t73sf08e.js`,local agent 只有 main 能停)。隊友沒辦法停自己的 helper。

### D:lead 隔離 + `subagent_guard.sh`

Guard(auto `d`/`ece8f627` 和 default `d-def`/`2000e6b3` 結果一樣):

| 測試 | 結果 |
|---|---|
| 隊友派 `model: opus` 的 helper | 0.09 s 被拒:`Helper subagents may only use model "haiku" or "sonnet"…` |
| 隊友派 `subagent_type: fork` | 0.10 s 被拒:`Forks inherit your own (expensive) model…` |
| 隊友不指定 model、`run_in_background:true` | 放行,meta `model:"haiku"`、`requestShape:"background"`、`parentAgentId` = 隊友;async 回傳(auto 2.83 s / default 0.17 s)。**guard 沒有擋隊友的背景 helper** |
| helper 再往下派 | helper 手上還是有 Agent 工具,但 hook 拒絕:`You are already a helper at the last allowed layer…` |

auto mode 下,隊友看不到 helper 回報的 nested 結果(回報 `nested=unknown`),因為報告送到 lead;default 下就看得到。

Lead 隔離(所有 `.6` 執行):lead 的對話裡**沒有任何**隊友 child 的 task-notification(queue 裡有 enqueue/remove 紀錄,但都被隊友拿走)。**但在 auto mode,每個 helper 都會在 lead 的對話裡多一則 `[Subagent hand-back]` 訊息**,內容就是 helper 的完整報告(`a`、`c`、`c2`×2、`d`、`e` 都有;`a-def`、`a-bypass`、`c-def`、`d-def`、`e-def` 都是 0)。所以 auto mode 下 lead 隔離不成立。

### E:Esc

| 執行 | Esc | 背景 shell | 背景 helper | 判定 |
|---|---|---|---|---|
| `e`(auto,`caa4a231`) | 07:09:46 打斷 `sleep 150`;runner log `work interrupted, returning to idle` | 07:10:10.91 完成 → idle 的隊友 0.32 s 被叫醒(`taking 1 queued task-notification`),回報 `ECHO GOT BG-E-SHELL` | 07:10:23.78 完成 → 0.41 s 通知到隊友;**報告內容送到 lead** | 通過(存活 + 通知);報告內容問題同 A |
| `e-def`(default,`4cf156e7`) | 07:30:00 打斷 | 07:30:38.49 完成 → 0.11 s 叫醒 | 07:30:44.00 完成 → 隊友下一個 tool round 收到(含報告) | **通過** |

Vim mode 要先按一次 Esc 離開 insert,第二次才會打斷,跟 `.6` gate notes 寫的一樣。

## 跟 `.5` 比,Arthur 會注意到的差異

- **變好**:隊友派背景 helper 不會再卡住(`.5`:63.9 s foreground;`.6`:馬上回傳)。隊友背景 Bash 做完會叫醒它(`.5`:永遠不會)。Esc 不會殺掉背景工作。
- **auto mode 沒有變好、也沒有變差**:helper 的報告在 `.5` 和 `.6` 都送到 lead。差別在 `.5` 隊友卡在 foreground 等;`.6` 隊友繼續工作,然後 idle 等一份不會來的報告。lead 那邊每個 helper 多一則 hand-back 訊息,`.5` 也一樣。
- 沒有看到其他退步。Bash、guard、inbox-wake hook(`wake.log` 有 `charlie` 那筆)、memory hook 在真實設定下都正常。

## 暫時的做法(到 `.7` 之前)

- 隊友要派 helper 時,在 helper 的 prompt 裡**明確要求它用 SendMessage 把結果(或報告檔路徑)傳給隊友的名字**。case `c` 證明這樣可以通(inbox-wake hook 會在下一個 tool round 送到)。
- 或者讓派 helper 的那個 session 用 `default` mode。

## Rollback

不建議 rollback:`.5` 在 auto mode 一樣把報告送到 lead,還會讓隊友卡住。需要的話,receipt 裡的指令是:

```bash
ln -s "$HOME/.local/share/claude-renderpatch/releases/2.1.291-host-darwin-arm64.5/claude-renderpatch-candidate" "$HOME/.local/bin/claude-bridge.rollback-2.1.291.5" && mv -h "$HOME/.local/bin/claude-bridge.rollback-2.1.291.5" "$HOME/.local/bin/claude-bridge"
```

## 清理

- 所有 `b6*` tmux session 都關了,沒有殘留的 `bridge6` claude process。
- `/tmp/bridge6-test/` 用 `trash` 丟掉了。測試 transcript 留在 `~/.claude/projects/-private-tmp-bridge6-test-*` 當證據。
- 沒動 `~/.claude/settings.json`、hook、overlay、release 目錄、`claude-bridge` link,也沒碰 session `35207cb5` / `physics-toys`。
