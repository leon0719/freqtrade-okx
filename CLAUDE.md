# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概觀

本地 Freqtrade 量化交易開發環境，串接 **OKX** 交易所。用 `uv` 管理 Python 依賴。
**預設 dry-run（模擬盤），不碰真錢。** 這是學習/練習用環境，範例策略不保證獲利。

- Python 3.12（由 `uv` 鎖定，見 `.python-version`）
- Freqtrade 2026.5.1、CCXT 4.5.x、TA-Lib（需先 `brew install ta-lib`）

## 常用指令

所有操作都封裝在 `Makefile`，底層是 `uv run freqtrade <子指令>`。執行 `make help` 可列出全部。
變數可在命令列覆寫，例如 `make download DAYS=60 TF=15m`、`make backtest STRAT=MyStrategy TIMERANGE=20260518-`。

```bash
make config                       # 驗證並顯示解析後的設定
make download                     # 下載歷史 K 線（預設 BTC/ETH/SOL，5m，30 天）— 回測前必做
make list-data                    # 列出已下載資料
make backtest                     # 回測（用全部已下載資料）
make backtest-show                # 顯示最近一次回測結果
make backtest-analysis            # 分析最近一次回測：各進場/出場/pair 賺賠（優化進出場用）
make lookahead                    # 檢查策略是否偷看未來資料（look-ahead bias）
make recursive                    # 檢查指標遞迴穩定性（recursive bias）
make hyperopt                     # 超參數最佳化（預設 100 回合，SharpeHyperOptLoss）
make hyperopt-show                # 顯示最佳調參結果
make trade                        # 啟動模擬盤 dry-run + Web UI（http://127.0.0.1:8080，常駐，Ctrl-C 停止）
make webserver                    # 只開 Web 伺服器做回測分析，不下單
make strategies                   # 列出可被載入的策略類別
make new-strategy NAME=MyStrategy # 建新策略範本
make clean                        # 清 Python 快取（__pycache__）
make clean-results                # 清回測 / hyperopt 結果、圖檔、log（保留原始資料與策略）
make clean-all                    # clean + clean-results
```

> 沒有自動化測試套件。驗證策略正確性靠 `make backtest`（看績效）+ `make lookahead`（查未來函數偏誤）。
> 改參數想重跑乾淨對照時用 `make clean-results`，別手動刪 `user_data/` 子目錄。
> Lint：`uv run ruff check .`（`ruff` 是 dev 依賴，用預設規則、無自訂設定）；`uv run ruff format .` 排版。

## 可覆寫變數（Makefile）

`STRAT`（策略類別名，預設 `DonchianBreakout`）、`TF`（時間框架，預設 `1h`）、`PAIRS`、`DAYS`、
`TIMERANGE`（如 `20260518-`，空值時不帶該參數）、`LOSS`、`EPOCHS`、`SPACES`（hyperopt 最佳化空間）。

## 架構與工作流程

核心循環：**寫/改策略 → 下載歷史資料 → 回測看績效 → hyperopt 調參 → 模擬盤實跑 → (謹慎)實盤**

- **策略**：`user_data/strategies/*.py`，每個檔案是一個繼承 `IStrategy`（`INTERFACE_VERSION = 3`）的類別，
  類別名必須與 `STRAT` 對應。四個核心方法：
  - `populate_indicators`：用 `talib.abstract` + `technical.qtpylib` 算指標（RSI、EMA…）
  - `populate_entry_trend`：設 `enter_long = 1` 的進場條件
  - `populate_exit_trend`：設 `exit_long = 1` 的出場條件
  - 類別屬性 `minimal_roi` / `stoploss` / `trailing_stop` 控制風控

  目前工作目錄保留的策略，反映研究脈絡（落選實驗檔已移除，但留在初始 commit `9f0d171`，
  需回顧可 `git show 9f0d171:user_data/strategies/<檔名>.py`）。研究決定性結論：**均值回歸（接刀）
  在過去市場全面失血，改走順勢；短 timeframe 唯有「高波動幣＋量能確認」才做得出來**。
  目前自研主力是 `DonchianBreakout`，另接一支社群策略當對照組（`make up` 雙 bot 並行）：
  - `DonchianBreakout`（1h，預設 `STRAT`，pairlist=BTC/ETH/SOL，config.json，port 8080）：通道突破順勢
    + 趨勢 EMA + 熊市 regime filter，讓利潤奔跑（roi 關閉，靠 trailing 出場）。**研究最佳基準**
    （全期 +16.56%、Calmar 4.78；注意該數字是樂觀成本下的舊期間，加真實成本後近期 180 天回測為負）。
  - `NostalgiaForInfinityX7`（5m，config.nfi.json，port 8081）：[社群最廣用策略](https://github.com/iterativv/NostalgiaForInfinity)，
    接刀 + DCA 攤平 + 小利累積，**接刀型對照組**（73k 行第三方碼，已 vendored 進 git；ruff 對它 `extend-exclude`，不自行改動）。
    哲學與 Donchian 相反，用來驗證「順勢 vs 接刀在當前 OKX 市場誰風險調整後報酬較佳」。看績效重淨值/回撤，不是勝率。
  - 先前的對照策略（`EmaTrendFollow`、`VolBreakout` DOGE/XRP 短線、`DonchianBreakout15m`）已移除，
    需回顧可從 git 歷史 `git show <commit>:user_data/strategies/<檔名>.py` 取回。
- **設定**：`user_data/config.json`（主 bot）與 `user_data/config.nfi.json`（NFI 對照）是實際設定
  （含 API key 與帳密，皆已 gitignore）；`config.example.json` 是可提交範本。交易所固定 `okx`、
  `trading_mode: spot`、`dry_run: true`。改 pairlist、stake、UI 帳密都在這裡。
  **真實成本設定**：config 已加 `fee: 0.001`（OKX taker）、市價單 `order_types`、`price_side: "other"`（吃買賣價差），
  讓回測貼近實盤；高頻小利策略對成本敏感，比較時務必沿用。NFI 走限價單(其 DCA 不適合市價)，故 config.nfi.json 不設市價。
- **資料**：下載的歷史 K 線存到 `user_data/data/okx/`（gitignore）。
- **Web UI**：FreqUI 前端。本機 `make trade` / `make webserver` 連 `http://127.0.0.1:8080`；
  常駐雙 bot `make up` 後分別連 8080（Donchian）/ 8081（NFI），帳密各在對應 config 的 `api_server`。
  FreqUI 的 bot 連線清單存在**瀏覽器 localStorage**（非 server），故換裝置/瀏覽器要各自重加連線；
  跨 port/跨來源連線需在目標 config 的 `CORS_origins` 加上來源(含 port)。部署細節見 `docs/DEPLOY.md`。

## 策略研究方法論

要「找最佳策略 / 優化 / 比較指標 / 調參 / 提升 Sharpe」時，先用 `strategy-research` skill
（`.claude/skills/strategy-research/SKILL.md`），裡面有指標庫、進階寫法範本與業界及格線。核心規矩：

- **主要評選標準是 Sharpe（風險調整後報酬），不是總報酬**；hyperopt 預設 `SharpeHyperOptLoss`。
- **強制樣本內 / 樣本外切分**：hyperopt 只在樣本內調參（如 `20260319-20260520`），再用樣本外
  （`20260520-`）驗證，避免過擬合。樣本外崩掉的參數即使樣本內漂亮也不採用。
- 改完策略**必跑 `make lookahead`** 確認 `has_bias=No`。
- 別堆指標：一條好策略 ≈ 1 趨勢過濾 + 1 進場觸發 + 1 出場/風控。
- 過往已試假設與結論記錄在記憶 `strategy-research-findings.md`（避免重複研究已知失敗方向）。
  關鍵背景：過去 90 天 BTC/ETH/SOL 在 5m 偏震盪/偏空，追動能做多整體難賺，回測虧損屬正常。

## 重要注意事項

- **切勿提交 `config.json` / `config.nfi.json`**（含 API key / 帳密，已被 `.gitignore` 排除）。修改設定範本時改 `config.example.json`。
- 切換實盤前：OKX API key 只開「交易」權限並關閉「提現」、綁 IP 白名單、`dry_run` 改 `false`、
  先用極小額 `stake_amount` 測試、把預設 UI 密碼與 `jwt_secret_key` 換掉。
- 新增/修改策略後務必跑 `make lookahead` 確認沒有未來函數偏誤，回測虧損屬正常現象。
