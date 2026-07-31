# Claude Code 2.1.220 Banner 與 Clawd 內部結構圖

> [!IMPORTANT]
> **Evidence/status：已針對 stock Claude Code 2.1.220、macOS arm64 驗證。**
> 本文件中的 offset、minified identifier、byte 長度與 component neighborhood 全部
> **version-pinned**；不得直接套用到其他 Claude Code 版本。**目前 frozen bridge API
> 沒有任何 Banner／mascot policy domain，也沒有可供 preload 使用的 Banner bridge。**
> 本文件後段的 `banner.mascot` policy domain 5 只是 **PROPOSED** 設計，不是目前 API。

本文件記錄 Claude Code **2.1.220 / macOS arm64** 中，終端歡迎 Banner、Clawd
吉祥物、首次設定 Welcome 畫面，以及 Web Gateway 小圖的已驗證內部結構。

這是一份**版本鎖定的二進位研究紀錄**，用途是：

1. 讓未來版本能靠穩定語意錨點重新找到 patch 位置；
2. 區分哪些自訂可直接用等長 byte patch 完成；
3. 區分哪些自訂需要 preload 加上最小 internal bridge；
4. 避免誤把三套彼此獨立的 Banner／吉祥物實作當成同一套。

本文件不表示下列 offset 可以直接沿用到其他版本。更新 Claude Code 後，必須依照
[`REPATCHING-PLAYBOOK.md`](../../REPATCHING-PLAYBOOK.md) 重新做語意定位。

相關文件：

- [專案總覽](../../README.md)
- [External preload runtime 與 closure boundary](../../reference/preload-runtime.md)
- [2.1.220 internal bridge 實作紀錄](../../reference/bridge-intent-2.1.220.md)
- [Bridge 開發指南](../BRIDGE-DEVELOPMENT.md)
- [目前 capability map](../CAPABILITY-MAP.md)

## 驗證目標

| 項目 | 值 |
|---|---|
| Claude Code 版本 | `2.1.220` |
| Stock 路徑 | `~/.local/share/claude/versions/2.1.220` |
| Stock SHA-256 | `8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081` |
| Stock 大小 | `256,908,272` bytes |
| `__BUN` file offset | `64,831,488` |
| `__BUN` 大小 | `191,365,120` bytes |
| Build version literal | `2.1.220` |
| Build time literal | `2026-07-24T22:17:45Z` |
| Build Git SHA literal | `4073f59596e272f39393db4f96abc5f4b10eff21` |

Offset 均為整個 Mach-O 檔案的 byte offset，不是 `__BUN` 內相對位置。

## 先講結論：不是一套，而是三套

2.1.220 內共有三套互不相同的歡迎圖／吉祥物實作：

1. **一般 Session Banner**
   - 顯示小型三行 Clawd；
   - 包含 `Claude Code v2.1.220`、model/billing、cwd/agent；
   - 有 condensed、full compact、full horizontal 三種版面；
   - Fleet/team view 也重用同一個小型 Clawd renderer。

2. **首次設定與授權流程的 WelcomeV2**
   - 是寬度 58 欄的大型點陣畫；
   - 不使用一般 Session Banner 的 Clawd pose table；
   - 被 onboarding、setup-token、Pro trial、Powerup discovery 共用。

3. **Web Gateway HTML 小圖**
   - 是獨立的三行 template literal；
   - 只出現在 Bedrock／Google Cloud／Microsoft Foundry Gateway 網頁；
   - 不會影響終端 Banner。

因此：

- patch 一般 Clawd 不會自動改 WelcomeV2 或 Web Gateway；
- patch WelcomeV2 不會改一般 Session Banner；
- 若想讓所有表面保持同一品牌，需要分別處理三套實作。

---

## 1. 可讀舊版原始碼對照

研究時使用下列可讀 source dump 理解元件結構：

- `src/components/LogoV2/Clawd.tsx`
  - 標準終端 pose fragments；
  - Apple Terminal 背景填色版本。
- `src/components/LogoV2/AnimatedClawd.tsx`
  - jump、look-around 動畫；
  - 固定寬高與裁切行為。
- `src/components/LogoV2/CondensedLogo.tsx`
  - 一般最常看到的小型 Header。
- `src/components/LogoV2/LogoV2.tsx`
  - condensed／full 模式選擇；
  - full compact 與 horizontal 版面。
- `src/components/LogoV2/WelcomeV2.tsx`
  - 首次設定的大型 58 欄點陣畫。
- `src/utils/logoV2Utils.ts`
  - version、cwd、billing、agent 資料；
  - layout width 計算。
- `src/components/Onboarding.tsx`
  - WelcomeV2 在 onboarding 的掛載點。
- `src/utils/theme.ts`
  - 六套 theme 中的 `clawd_body` 與 `clawd_background`。

可讀 source 只能用來理解語意。2.1.220 binary 中的實際 minified 內容才是 patch
依據；可讀 source 與 binary 之間已有少量功能差異，例如 binary 中存在 compile-time
branding fallback seam。

---

## 2. 一般 Session Banner 的資料與 layout helper

### 2.1 Layout helper

| Offset | 2.1.220 minified 名稱 | 語意 |
|---:|---|---|
| `241571502` | `kRr` | 終端寬度 `>= 70` 使用 `horizontal`，否則 `compact` |
| `241571562` | `CDa` | full logo 左右欄寬度計算 |
| `241571832` | `ADa` | 根據 welcome/cwd/model 內容求左欄最佳寬度 |
| `241573712` | 常數區 | `vdf=50,vqb=20,wDa=4,GXo=1,VXo=2` |

`ADa` 的核心語意是：

```text
max(width(welcome), width(cwd), width(model), 20)
然後加 padding，最後限制在 50 欄內
```

這個最小寬度 `20` 沒有把任意外部 art 的寬度納入計算。若自訂圖超過原本
footprint，只替換 Clawd renderer 仍可能造成 full logo 溢出、換行或裁切。

### 2.2 Welcome 文字

- `241571957`：`"Welcome back!"`
- 同一函式附近：``Welcome back ${username}!``
- username 超過 20 字元或不存在時，使用無名字版本。

### 2.3 Banner display data helper

- 函式起點：`241572621`
- 2.1.220 minified 名稱：`kSt`

穩定語意片段：

```js
Z.DEMO_VERSION ?? VERSION
Z.CLAUDE_CODE_HIDE_CWD ? "" : ...
"API Usage Billing"
return {version, cwd, billingType, agentName}
```

精確子錨點：

| Offset | 錨點 |
|---:|---|
| `241572642` | `Z.DEMO_VERSION??` |
| `241573113` | `Z.CLAUDE_CODE_HIDE_CWD` |
| `241573228` | `"API Usage Billing"` |

資料來源：

- `version`
  - `DEMO_VERSION`，否則 build version 加現有 suffix；
- `cwd`
  - `CLAUDE_CODE_HIDE_CWD` 可隱藏；
  - direct-connect server 存在時會追加 server hostname；
- `billingType`
  - provider／subscription 資料；
  - fallback 是 `API Usage Billing`；
- `agentName`
  - initial settings 的 agent 名稱。

### 2.4 已存在的零 patch runtime 輸入

| 輸入 | 可做什麼 | 限制 |
|---|---|---|
| `DEMO_VERSION` | 改顯示版本 | 同時會讓顯示路徑改成 `/code/claude`，也可能影響其他 demo 行為 |
| `CLAUDE_CODE_HIDE_CWD` | 隱藏 cwd | 不能指定任意替代文字 |
| `CLAUDE_CODE_FORCE_FULL_LOGO` | 強制 full logo | 只改版面選擇，不改 art |
| agent setting | 改 `@agent` 文字 | 不是 Banner 品牌 API |
| OAuth/account 設定 | 影響 username、organization、billing | 不是任意 Banner 資料來源 |

不建議 preload 為了改顯示 cwd 而呼叫 `process.chdir()`：那會真的改變 Claude Code 的
工作目錄與檔案行為，不只是顯示文字。

---

## 3. 小型 Clawd renderer

### 3.1 主 renderer

- 函式起點：`241573821`
- 2.1.220 minified 名稱：`d4`

重要執行順序：

1. 解析 `pose`，預設為 `default`；
2. 執行 `Ta()` gate；若成立直接回傳 `null`；
3. `Apple_Terminal` 走 Apple 專用 renderer；
4. 其他終端使用 pose table；
5. 用 `clawd_body`／`clawd_background` 畫三行內容。

任何 bridge 都應保留步驟 2 的 suppression/accessibility gate，不應讓外部 art 強制蓋過它。

### 3.2 標準終端三行結構

標準 Clawd 不是一個完整三行字串，而是被拆成多個 segment：

```text
row 1: r1L + r1E + r1R
row 2: r2L + 固定五格 body + r2R
row 3: 固定 feet
```

固定、未放在 pose table 內的部分：

| Offset | 內容 | 用途 |
|---:|---|---|
| `241574933` | `"█████"` | 第二行中間 body |
| `241575322` | `children:["  ","▘▘ ▝▝","  "]` | 第三行 feet |

目前 default 畫面概念上是：

```text
 ▐▛███▜▌
▝▜█████▛▘
  ▘▘ ▝▝
```

### 3.3 Pose table

完整 `Cdf + Adf` table 是一段唯一、連續的 596-byte 範圍：

```text
[241576541, 241577137)
```

| Offset | 語意 |
|---:|---|
| `241576541` | 標準終端 `Cdf={default:{...}` 起點 |
| `241577007` | Apple eye table `Adf={default:...}` 起點 |

Pose keys：

- `default`
- `look-left`
- `look-right`
- `arms-up`

每個標準 pose 有：

- `r1L`
- `r1E`
- `r1R`
- `r2L`
- `r2R`

#### 每個字串內容的精確 offset 與 encoded byte 長度

| Pose | Field | Offset | 長度 |
|---|---|---:|---:|
| default | `r1L` | `241576560` | 7 |
| default | `r1E` | `241576574` | 30 |
| default | `r1R` | `241576611` | 6 |
| default | `r2L` | `241576624` | 12 |
| default | `r2R` | `241576643` | 12 |
| look-left | `r1L` | `241576676` | 7 |
| look-left | `r1E` | `241576690` | 30 |
| look-left | `r1R` | `241576727` | 6 |
| look-left | `r2L` | `241576740` | 12 |
| look-left | `r2R` | `241576759` | 12 |
| look-right | `r1L` | `241576793` | 7 |
| look-right | `r1E` | `241576807` | 30 |
| look-right | `r1R` | `241576844` | 6 |
| look-right | `r2L` | `241576857` | 12 |
| look-right | `r2R` | `241576876` | 12 |
| arms-up | `r1L` | `241576907` | 12 |
| arms-up | `r1E` | `241576926` | 30 |
| arms-up | `r1R` | `241576963` | 12 |
| arms-up | `r2L` | `241576982` | 7 |
| arms-up | `r2R` | `241576996` | 7 |

Apple eye strings 都是 17 encoded bytes：

| Pose | Offset |
|---|---:|
| default | `241577021` |
| look-left | `241577053` |
| look-right | `241577086` |
| arms-up | `241577116` |

### 3.4 Apple Terminal renderer

- 函式起點：`241575582`
- 2.1.220 minified 名稱：`BDa`

Apple Terminal 因為 glyph vertical spacing 行為不同，使用 background fill 技巧，而不是標準
segment body。

固定片段：

| Offset | 內容 |
|---:|---|
| `241575684` | 左側 `▗` |
| `241575950` | 右側 `▖` |
| `241576168` | `" ".repeat(7)` body fill |
| `241576226` | `▘▘ ▝▝` feet |

Apple 的 `arms-up` eye 字串會退回 default；它沒有完整的抬手 silhouette。

### 3.5 Table 參照數量

Live executable 中：

- `Cdf`
  - 使用：`241574150`
  - 宣告列表：`241576481`
  - 賦值：`241576541`
- `Adf`
  - 使用：`241575741`
  - 宣告列表：`241576485`
  - 賦值：`241577007`

其他低 offset 同名內容不是這個 live executable 元件的可執行 table，不應以短名稱全域 patch。

---

## 4. Animated Clawd

| Offset | 語意 |
|---:|---|
| `241582594` | animation wrapper 函式起點 |
| `241582974` | wrapper 以動態 pose 呼叫 Clawd renderer |
| `241583872` | animation state/effect 函式起點 |
| `241585003` | click animation choices `qdf=[nQo,Gdf]` |
| `241584614` | 固定尺寸 `OSt=3,nOa=9` |

已觀察到的動畫：

- crouch + arms-up jump；
- look-right → look-left；
- 額外的 celebrate／skip／spin sequence 資料。

重要 layout 限制：

```text
width = 9
height = 3
reserve crouch row 時 height = 4
overflow = hidden
```

因此：

- 只換成相同 footprint 的 art 很容易；
- 超過 9 欄或 3 行的 art，在 animation wrapper 中會被裁切；
- 任意尺寸 art 不能只改 pose table 或 Clawd renderer。

若只 patch `default` pose：

- 非 fullscreen／非動畫時看起來會是自訂圖；
- click 後的 `look-left`、`look-right`、`arms-up` 仍會切回 stock 片段；
- 若想保持動畫一致，四個 pose 都必須一起設計。

---

## 5. Condensed Header：最常看到的一般 Banner

- 函式起點：`241586814`
- 2.1.220 minified 名稱：`uQo`

它負責組成：

```text
[Clawd]  Claude Code v2.1.220
         model · billing
         @agent · cwd
```

### 5.1 Width 計算

- `241587173`：`Math.max(Xdf-15,20)`

這裡固定預留 15 欄：

```text
Clawd footprint + gap + padding
```

若自訂 art 變寬，文字可用寬度仍會照 `columns - 15` 計算，造成 overflow 或錯誤截斷。

### 5.2 組成位置

| Offset | 內容 |
|---:|---|
| `241588263` | agent/cwd 用 `" \xB7 "` 連接 |
| `241588305` | branding `Mascot` fallback seam |
| `241588463` | branding `Title` fallback seam |
| `241588506` | `children:"Claude Code"` expression 起點 |
| `241588516` | `Claude Code` literal 起點 |
| `241588641` | version：`children:["v",lOa]` |
| `241588964` | model/billing：`children:[cQo," \xB7 ",lQo]` |
| `241589792` | `var bf,opf,PSt=null` |

### 5.3 Dormant branding seam

Condensed Header 已經有結構化 fallback：

```js
PSt
  ? jsx(PSt.Mascot, {fallback: animatedOrStaticClawd})
  : animatedOrStaticClawd

PSt
  ? jsx(PSt.Title, {})
  : <Text bold>Claude Code</Text>
```

但 external build 中：

```js
PSt = null
```

`PSt` 是 bundle 內 lexical binding，不是 `globalThis`、env、config 或 CommonJS export。
因此 preload 無法直接把它設成自訂 component provider。

這個 seam 仍是未來最小 bridge 的優良語意錨點，因為：

- 已有 stock fallback；
- 已分開 Mascot 與 Title；
- 可以把外部資料限制成窄介面，而不需要暴露整個 renderer。

---

## 6. Full Logo

- 函式起點：`241590896`
- 2.1.220 minified 名稱：`_Qo`

### 6.1 Condensed／full 選擇

- `241592294`：預設 condensed 條件的一部分；
- `241592297`：`CLAUDE_CODE_FORCE_FULL_LOGO` env anchor。

無 release notes、無 project onboarding、也未強制 full logo 時，會回傳 Condensed Header。
其餘情況會畫 full logo。

### 6.2 Full logo title 的四個一致性位置

若要改 `Claude Code` 品牌文字，不能只改 Condensed Header。Full logo 還有三份：

| Offset | 用途 |
|---:|---|
| `241592518` | horizontal border title 中的 `Claude Code` |
| `241592591` | compact border title 中的 ` Claude Code ` |
| `241592680` | fullscreen／無 border title 行 |

加上 Condensed Header 的 `241588516`，一般 Session Banner 共至少四個 title literal
需要一致處理。

### 6.3 Full compact layout

| Offset | 內容 |
|---:|---|
| `241592442` | `let o9e=kRr(TAn)` layout 選擇 |
| `241592927` | welcome message 計算 |
| `241593156` | agent/cwd join |
| `241593226` | `HSt.Mascot` seam |
| `241593261` | seam fallback 的 Clawd call |
| `241593277` | 無 seam 的 Clawd call |
| `241593367` | model text node |
| `241593736` | billing text node |

### 6.4 Full horizontal layout

| Offset | 內容 |
|---:|---|
| `241594120` | agent/cwd join |
| `241594812` | `HSt.Mascot` seam |
| `241594847` | seam fallback 的 Clawd call |
| `241594863` | 無 seam 的 Clawd call |
| `241594981` | model/billing text node |
| `241595089` | cwd text node |
| `241595531` 附近 | 左欄 `minHeight` 與 layout node |
| `241596531` | `var OOa,Mu,bpf,HSt=null,PRr=50` |

Full logo 的 dormant provider `HSt` 只有 `.Mascot`，沒有 `.Title`。Title 仍由 border/title
literal 組成。

和 `PSt` 一樣，`HSt` 是 lexical `null`，preload 無法直接修改。

### 6.5 Main Messages tree 掛載點

- `241700775`

語意：

```js
!hideWelcomeChrome && <LogoV2 />
```

這是整個一般 Session Banner 放進 messages tree 的最外層位置。

不建議直接在此處把 `_Qo` 完全替換成外部 art，因為 `_Qo` 內還負責：

- release-note seen state；
- project onboarding seen state；
- upsell／announcement lifecycle；
- 其他 sibling notices。

若在 `_Qo` mount 前就繞過它，可能讓這些 lifecycle side effect 消失。完整 Banner bridge
應在保留現有 hooks/effects 後才替換可視內容。

---

## 7. 一般 Clawd 的所有 call site

Live executable 中所有 `jsx(d4...)` 呼叫都已被分類，共 8 個：

| Offset | 使用位置 |
|---:|---|
| `241582974` | AnimatedClawd wrapper，帶動態 pose |
| `241588360` | Condensed Header branding fallback 分支 |
| `241588396` | Condensed Header 無 branding provider 分支 |
| `241593261` | Full compact branding fallback 分支 |
| `241593277` | Full compact 無 provider 分支 |
| `241594847` | Full horizontal branding fallback 分支 |
| `241594863` | Full horizontal 無 provider 分支 |
| `245547170` | Fleet/team view header |

所以：

- patch Clawd table／renderer 會自動影響一般 condensed、full 與 Fleet/team view；
- 沒有額外的 Clawd call 藏在 spinner、`/about`、help 或 release notes component；
- release notes 可能讓 full LogoV2 顯示，但它不是另一個 Clawd renderer。

Fleet/team view 的 call 受下列條件控制：

```text
非特定隱藏狀態 && columns >= 70
```

附近穩定文字包括：

- `awaiting input`
- `working`
- `completed`

可用來在未來版本重新辨認此使用點。

IDE onboarding 是另一套簡單 title：

- offset `231319256` 附近；
- 使用 `✻`；
- 顯示 `Welcome to Claude Code for <IDE>`；
- 不使用 Clawd。

---

## 8. Clawd theme 顏色

不要為了改顏色去 patch 所有 render call 的 `clawd_body` token。比較窄而完整的做法是改
六套 theme map 的 value。

### 8.1 `clawd_body`

| Theme | Value offset | 原始值 | Value 長度 |
|---|---:|---|---:|
| light | `230550893` | `rgb(215,119,87)` | 15 |
| light ANSI | `230553248` | `ansi:redBright` | 14 |
| dark ANSI | `230555616` | `ansi:redBright` | 14 |
| light daltonized | `230558013` | `rgb(215,119,87)` | 15 |
| dark | `230560500` | `rgb(215,119,87)` | 15 |
| dark daltonized | `230562980` | `rgb(215,119,87)` | 15 |

### 8.2 `clawd_background`

| Theme | Value offset | 原始值 | Value 長度 |
|---|---:|---|---:|
| light | `230550928` | `rgb(0,0,0)` | 10 |
| light ANSI | `230553282` | `ansi:black` | 10 |
| dark ANSI | `230555650` | `ansi:black` | 10 |
| light daltonized | `230558048` | `rgb(0,0,0)` | 10 |
| dark | `230560535` | `rgb(0,0,0)` | 10 |
| dark daltonized | `230563015` | `rgb(0,0,0)` | 10 |

### 8.3 Live token reference 統計

`clawd_body` 在 live bundle 中共 42 個：

- theme map：6；
- WelcomeV2：24；
- 小型 Clawd：12。

`clawd_background` 在 live bundle 中共 12 個：

- theme map：6；
- WelcomeV2：3；
- 小型 Clawd：3。

所有 live token reference 都只落在上述三個區域，沒有另一套未分類的 Clawd UI。

---

## 9. WelcomeV2：首次設定的大型點陣 Banner

WelcomeV2 不使用 `Cdf`、`Adf` 或小型 Clawd renderer。

### 9.1 主元件

- 函式起點：`238852083`
- 2.1.220 minified 名稱：`LDe`

重要 offset：

| Offset | 語意 |
|---:|---|
| `238852159` | fullscreen／rows 太少時的 compact fallback gate |
| `238852809` | `Apple_Terminal` branch |
| `238860335` | Apple Terminal full-art renderer 起點 |
| `238868354` | `Hgt=58`，固定 art 寬度 |
| `238868361` | `vEp=30`，row threshold |

當 fullscreen 或 terminal rows `< 30` 時，不畫完整點陣圖，只顯示：

```text
Welcome to Claude Code v2.1.220
```

### 9.2 Welcome title copies

| Offset | Branch |
|---:|---|
| `238852229` | compact fallback |
| `238852904` | Apple Terminal 呼叫參數 |
| `238853098` | light full art |
| `238856615` | dark full art |

### 9.3 Full-art branch 錨點

四份 58-dot line：

| Offset | Branch 類型 |
|---:|---|
| `238853698` | 標準 light |
| `238857210` | 標準 dark |
| `238861225` | Apple light |
| `238865029` | Apple dark |

這些點陣 branch 中還混合：

- 一般文字 span；
- `dimColor` span；
- `clawd_body` foreground；
- `clawd_background`／background fill；
- 不同 light/dark 裝飾。

若要完整換掉 WelcomeV2，必須處理四個 full-art branch，加上 compact title fallback。

### 9.4 WelcomeV2 的所有 call site

| Offset | UI |
|---:|---|
| `239201693` | `setup-token` auth flow |
| `246027168` | 首次 onboarding |
| `246038747` | Pro trial screen |
| `246040062` | Powerup discovery／tour |

所以任何 WelcomeV2 patch 都會同時改變上述四個流程，不只是第一次啟動。

---

## 10. Web Gateway HTML 小圖

Web Gateway 有一份完全獨立的三行 template literal：

- 定義：`246778889`
- 2.1.220 minified 名稱：`s_T`

內容概念上是：

```text
 ▐▛███▜▌
▝▜█████▛▘
  ▘▘ ▝▝
```

唯一使用點：

- `246773368`
- HTML：`<pre ...>${s_T}</pre>`

頁面 title：

```text
Claude gateway for Amazon Bedrock, Google Cloud, and Microsoft Foundry
```

這不是終端 Banner，也不是 OAuth success page。只 patch `s_T` 不會改任何 TUI 畫面。

---

## 11. 等長 byte patch 能做什麼

### 11.1 最簡單：同 footprint glyph swap

Bundle 內 UI glyph 使用 ASCII Unicode escape：

```text
\uXXXX
```

每個 escape 固定是 6 ASCII bytes，因此任何 BMP code point 都能一對一替換。

例如：

- `▛` → 另一個 `\uXXXX`：完全等長；
- 保留相同 segment 數量與顯示寬度時，最安全。

補充平面字元需要 surrogate pair：

```text
\uXXXX\uXXXX
```

會占 12 bytes，不能直接塞進單一 6-byte slot，除非重新利用更大的 contextual range。

### 11.2 建議 patch 整個唯一 table range

不要用單一 minified identifier 或舊 offset 當 patch pattern。較穩定的做法是以完整語意範圍：

```text
Cdf={default:{r1L:...,r1E:...},"look-left":...,"look-right":...,"arms-up":...},
Adf={default:...,"look-left":...,"look-right":...,"arms-up":...}
```

作為唯一 contextual anchor。

原始範圍長度是 596 bytes。替代內容較短時，可以在字串外、JavaScript 合法的位置加入空白，
而不是把多餘空白放進使用者看得到的字串。

### 11.3 不在 table 內的片段也要改

完整 redesign 還要處理：

- 標準 body 中間五格；
- 標準 feet；
- Apple 左右邊；
- Apple body fill；
- Apple feet。

只改 `Cdf`／`Adf` 不會改這些固定片段。

### 11.4 顏色

同長度 color value 可直接替換。

替代色比較短時，應把 patch range 擴到 closing quote 與逗號，例如概念上：

```js
clawd_body:"old-color",
```

改成：

```text
clawd_body:"new",<以合法 JavaScript source whitespace 補足 byte budget>
```

`<...>` 是說明標記，不是實際 replacement bytes；實際多餘 byte 應全部是 JavaScript
source whitespace，不會進入 color value。

不要在 color string 內加 padding；`"red     "` 可能不是有效 theme color。

### 11.5 Title、billing 與其他文字

可直接等長 patch 的 literal 包括：

- `Claude Code`
- `Welcome back!`
- `Welcome to Claude Code`
- `API Usage Billing`
- `v` prefix
- ` · ` separator

較短文字也應把多餘 byte 放在字串外的 source whitespace。若把空白放在引號內，會影響
畫面寬度、border title 與 truncation。

### 11.6 WelcomeV2

WelcomeV2 的每行也是固定 source literal，可逐行 patch；但要注意：

- 有四個 full-art branch；
- 每行視覺寬度原本是 58；
- 同一畫面可能由多個 Text span 組成；
- ASCII 一字元只占 1 source byte，`\uXXXX` 占 6 source bytes；
- 可在字串外以 source whitespace 回收 byte budget；
- 改 `Hgt=58`／`vEp=30` 雖然容易等長，但 layout 行為仍需 PTY 與真實終端驗證。

### 11.7 Web Gateway

`s_T` 是固定三行 template literal，最適合單獨做一個小型等長 patch；不要期待它同步一般
TUI Clawd。

---

## 12. 哪些情況需要 bridge

### 12.1 Preload 單獨做不到的事

外部 Bun preload 能使用：

- `globalThis`
- `process`／env／argv
- `console`
- Node/Bun API
- renderpatch runtime registry

但它不能直接存取：

- `Cdf`
- `Adf`
- Clawd renderer
- Condensed Header
- Full Logo
- React state／Ink component lexical bindings
- `PSt`／`HSt`

這些都在 bundle lexical/module closure 內，沒有可用 export。詳見
[`preload-runtime.md`](../../reference/preload-runtime.md)。

### 12.2 PROPOSED policy domain 5：固定 9×3 footprint 的 `banner.mascot`

> [!WARNING]
> `banner.mascot`、policy domain ID `5`、其 payload 與 result schema 都是**未實作提案**。
> 目前 frozen policy API 只有 domain `0`–`4`；raw capture 的 `d5` 是 keybinding domain，
> 和這個提案無關。未正式更新 manifest、bootstrap validator、binary bridge、API version
> 與驗證 harness 前，外部 extension 不得宣告或依賴此 capability。

若只需要讓外部 `.mjs` 提供不同的三行小圖，最小設計可沿用目前 total policy query 慣例：

1. 提案新增 policy domain ID `5`、名稱 `banner.mascot`；
2. result 限制為 `null | string`，並設定最大長度；
3. payload 只傳 primitive，例如 pose 與 terminal 名稱；
4. 在 Clawd renderer 中，保留 `Ta()` gate 後查詢；
5. internal code 自己用 Ink `Text` 包裝字串；
6. `null` 表示使用完整 stock fallback；
7. empty string 可明確表示隱藏 mascot。

概念程式碼：

```js
if (Ta()) return null

const externalArt = rpQ(5, null, pose, process.env.TERM_PROGRAM ?? null)
if (externalArt !== null) {
  return <Text color="clawd_body">{externalArt}</Text>
}

// stock Apple/standard Clawd follows
```

Binary helper 與 bootstrap validator 必須：

- 同步；
- catch getter／call／handler error；
- 拒絕 Promise／thenable；
- 驗證回傳 type 與長度；
- runtime 不存在時回傳**完全相同的 null fallback**。

外部 extension 不應直接取得 React／Ink internals，也不應回傳 raw React node。由 internal adapter
把受限 descriptor 轉成 Ink node，介面更穩定也更安全。

### 12.3 利用 dormant branding seam

另一種做法是把：

- `PSt.Mascot`
- `PSt.Title`
- `HSt.Mascot`

接到 internal adapter。

這能保留它們現有的 `fallback` 語意，但仍需要 binary patch 把 lexical `null` 接到 runtime。
外部 extension 若只回傳文字／descriptor，由 internal adapter 建立 Text／Box，會比把 React
component constructor 暴露到外部安全。

### 12.4 任意尺寸 art 需要更多 layout bridge

若 art 不再是 9×3，至少還要處理：

1. Animated wrapper 的 `width=9`；
2. Animated wrapper 的 `height=3/4` 與 `overflow:hidden`；
3. Condensed Header 的 `columns - 15`；
4. Full logo `ADa` 的最小寬度與 50 欄上限；
5. Full horizontal 左欄的 minHeight；
6. 是否仍允許 click animation。

比較穩定的介面可使用受驗證 descriptor：

```ts
{
  lines: string[]
  width: number
  height: number
}
```

Binary 仍負責：

- 驗證 width/height 和實際 line width；
- Ink node 建立；
- layout；
- clipping；
- stock fallback。

### 12.5 完整替換整個 Banner

若外部要控制 title、model、cwd、顏色、區塊排列與任意 art，這已不是單一 mascot bridge。

不可只在 `241700775` 的最外層 call site 直接跳過 `_Qo`，因為會跳過既有 lifecycle。
較安全的方向是：

1. 讓 `_Qo` 先執行原本 hooks/effects 與 display data 計算；
2. 把已整理、primitive-only 的 banner data 傳給 external policy；
3. external 回傳受限 descriptor，不回傳 React node；
4. internal renderer 將 descriptor 轉成 Ink UI；
5. 保留 announcements、notices、release/onboarding side effects；
6. runtime 不存在或 descriptor 無效時完整回到 stock output。

這會需要比 Clawd query 更大的 contextual patch，應當視為獨立 bridge capability。

### 12.6 Whole-renderer replacement 不屬於 Banner bridge

若目標不只是歡迎 Banner，而是替換整個 Claude Code Ink renderer、message tree、input composer
或 terminal diff/reset pipeline，`banner.mascot` 或完整 Banner descriptor 都不足以完成。

Whole-renderer 方案至少會碰到：

- private React component graph 與 hook ordering；
- AppState／REPL／Messages render lifecycle；
- Ink instance、screen buffer、diff planner 與 terminal serializer；
- alternate-screen／classic renderer 差異；
- transcript、virtual scroll、resize、focus、mouse 與 keybinding ownership；
- dialog、permission、tool rendering 與 accessibility behavior；
- renderer teardown、generation replacement與 stale cleanup。

目前 external preload 只能操作 runtime-reachable global；現有 raw capture domain 雖能在 exact-artifact
unsafe mode 取得部分 private handle，**raw publication 本身不會改變任何 lexical call site**。要讓
Claude Code 改走另一套 renderer，仍然必須加入新的 version-pinned internal dispatch／adapter，
而且 blast radius、hook safety、fallback 與更新成本都遠高於 Banner customization。

若真的需要 whole-renderer，應視為獨立專案能力：

1. 先定義窄而版本化的 renderer contract；
2. 讓 stock renderer 保持可完整 fallback；
3. 不把整個 mutable React／Ink graph直接暴露給一般 extension；
4. 每一個 lifecycle edge 都做 generation-safe teardown；
5. 分別驗證 classic、fullscreen、transcript、resize、dialog 與 crash recovery；
6. 每次 Claude Code 更新都重新做語意定位、等長 patch、簽章與 PTY／真實終端驗證。

這不是目前 bridge API 所支援的功能，也不應被描述成只需 preload 的 update-stable customization。

---

## 13. 更新版本時的穩定語意錨點

### 13.1 小型 Clawd

一起搜尋：

```text
Apple_Terminal
clawd_body
clawd_background
default
look-left
look-right
arms-up
r1L
r1E
r1R
r2L
r2R
```

並確認：

- row 2 有固定五個 full-block body；
- row 3 有 `▘▘ ▝▝` feet；
- Apple branch 使用 background fill；
- pose table 與 renderer 在同一語意模組附近。

### 13.2 Animation

搜尋：

```text
look-right
look-left
arms-up
60
height:3
width:9
overflow:"hidden"
```

確認 sequence 包含 jump 與 look-around，而不是其他同名資料。

### 13.3 Condensed Header

搜尋：

```text
CLAUDE_CODE_TUI_JUST_SWITCHED
Math.max(columns - 15, 20)
Claude Code
Mascot
Title
fallback
gap:2
```

確認同一元件同時包含：

- mascot；
- title/version；
- model/billing；
- agent/cwd。

### 13.4 Full Logo

搜尋：

```text
CLAUDE_CODE_FORCE_FULL_LOGO
Welcome back!
borderStyle:"round"
Mascot
fallback
50
70
```

確認有：

- condensed early return；
- compact full layout；
- horizontal full layout；
- release/onboarding feed column。

### 13.5 Display data

搜尋：

```text
DEMO_VERSION
CLAUDE_CODE_HIDE_CWD
API Usage Billing
version
cwd
billingType
agentName
```

### 13.6 WelcomeV2

搜尋：

```text
Welcome to Claude Code
Apple_Terminal
light-daltonized
light-ansi
58
30
..........................................................
```

確認四個 full-art branch 與 compact fallback 都存在。

### 13.7 Fleet/team view

在小型 Clawd call 附近確認：

```text
awaiting input
working
completed
>=70
```

### 13.8 Web Gateway

搜尋：

```text
Claude gateway for Amazon Bedrock, Google Cloud, and Microsoft Foundry
<pre style="line-height: 1;
```

以及連續三行小型 Clawd template literal。

---

## 14. 建議的 patch 驗證清單

### 靜態 byte 驗證

- 以 exact stock SHA guard 開始；
- 每個完整 contextual old pattern 必須恰好出現一次；
- new pattern 在 stock 中必須是零次；
- 每組 old/new 長度完全相同；
- patch 後 old=0、new=1；
- 所有範圍位於 live `__BUN`；
- patch 範圍互不重疊；
- pre-sign 檔案總長度不變；
- 不以舊 minified 名稱或 offset 單獨定位。

### 一般 Banner 行為驗證

至少測試：

1. 預設 condensed；
2. `CLAUDE_CODE_FORCE_FULL_LOGO=1`；
3. terminal `<70` 與 `>=70`；
4. fullscreen／classic renderer；
5. click animation 的四個 pose；
6. Apple Terminal branch；
7. light、dark、ANSI、daltonized theme；
8. 有／無 agent；
9. 長 cwd、CJK cwd、隱藏 cwd；
10. release notes／project onboarding 觸發 full logo；
11. Fleet/team view 寬度 >=70；
12. resize 後是否 overflow、錯誤 truncation 或 stale wrap。

### WelcomeV2 驗證

至少測試：

- rows `<30` compact fallback；
- rows `>=30` full art；
- light／dark；
- Apple Terminal light／dark；
- onboarding；
- setup-token；
- Pro trial；
- Powerup discovery。

### Bridge fallback 驗證

若新增 banner bridge，必須驗證：

- patched binary、無 preload：完全 stock；
- bootstrap only、無 handler：完全 stock；
- non-callable facade：完全 stock；
- throwing property getter：完全 stock；
- throwing handler：完全 stock；
- Promise／thenable result：完全 stock；
- wrong type／oversize descriptor：完全 stock；
- safe mode：完全 stock；
- valid empty string：明確隱藏 mascot；
- valid custom art：正確顯示；
- stale render／resize 不保留舊 descriptor；
- child process 無 preload／bridge metadata。

---

## 15. 維護結論

對 2.1.220 而言：

- **固定 footprint 的 Clawd glyph、顏色、title 與文字**：適合直接等長 byte patch；
- **大型 WelcomeV2**：也能等長 patch，但有四個 branch 與四個使用流程；
- **Web Gateway 小圖**：獨立 patch；
- **由外部檔案動態提供 9×3 mascot**：需要一個新的窄 policy bridge；
- **任意尺寸 art**：還需要 animation 與 layout dimension bridge；
- **完整任意 Banner UI**：需要保留 `_Qo` lifecycle 的較大型 descriptor bridge；
- **preload 單獨**無法修改 Cdf、Adf、PSt、HSt 或任何 React／Ink lexical binding。

最小、可維護的長期方向仍是：

```text
外部 preload/runtime 保存使用者設定與政策
+
版本鎖定的最小 internal semantic adapter
+
嚴格 stock fallback
```

不要把整個 private renderer graph 暴露到 external extension，也不要讓外部 module 回傳任意
React node。讓 binary 保有 layout、Ink node 建立、型別驗證與 fallback，更新時只需重新定位
最小 bridge site。
