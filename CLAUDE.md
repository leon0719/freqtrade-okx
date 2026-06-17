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
make lookahead                    # 檢查策略是否偷看未來資料（look-ahead bias）
make hyperopt                     # 超參數最佳化（預設 100 回合，SharpeHyperOptLoss）
make hyperopt-show                # 顯示最佳調參結果
make plot-profit                  # 產生獲利曲線圖到 user_data/plot/
make trade                        # 啟動模擬盤 dry-run + Web UI（http://127.0.0.1:8080，常駐，Ctrl-C 停止）
make webserver                    # 只開 Web 伺服器做回測分析，不下單
make new-strategy NAME=MyStrategy # 建新策略範本
make clean                        # 清 Python 快取
```

> 沒有自動化測試套件。驗證策略正確性靠 `make backtest`（看績效）+ `make lookahead`（查未來函數偏誤）。

## 可覆寫變數（Makefile）

`STRAT`（策略類別名，預設 `SampleStrategy`）、`TF`（時間框架，預設 `5m`）、`PAIRS`、`DAYS`、
`TIMERANGE`（如 `20260518-`，空值時不帶該參數）、`LOSS`、`EPOCHS`、`SPACES`（hyperopt 最佳化空間）。

## 架構與工作流程

核心循環：**寫/改策略 → 下載歷史資料 → 回測看績效 → hyperopt 調參 → 模擬盤實跑 → (謹慎)實盤**

- **策略**：`user_data/strategies/*.py`，每個檔案是一個繼承 `IStrategy`（`INTERFACE_VERSION = 3`）的類別，
  類別名必須與 `STRAT` 對應。四個核心方法：
  - `populate_indicators`：用 `talib.abstract` + `technical.qtpylib` 算指標（RSI、EMA…）
  - `populate_entry_trend`：設 `enter_long = 1` 的進場條件
  - `populate_exit_trend`：設 `exit_long = 1` 的出場條件
  - 類別屬性 `minimal_roi` / `stoploss` / `trailing_stop` 控制風控
  `SampleStrategyV2` 是 `SampleStrategy` 的改進版（加 EMA200 長趨勢過濾、RSI 區間進場、收緊停損），
  可作為「如何在既有策略上迭代」的範例對照。
- **設定**：`user_data/config.json` 是實際設定（含 API key 與帳密，已 gitignore）；
  `config.example.json` 是可提交範本。交易所固定 `okx`、`trading_mode: spot`、`dry_run: true`。
  改 pairlist、stake、UI 帳密都在這裡。
- **資料**：下載的歷史 K 線存到 `user_data/data/okx/`（gitignore）。
- **Web UI**：FreqUI 前端，`make trade` 或 `make webserver` 後連 `http://127.0.0.1:8080`，
  帳密在 `config.json` 的 `api_server.username / password`。

## 重要注意事項

- **切勿提交 `config.json`**（含 API key / 帳密，已被 `.gitignore` 排除）。修改設定範本時改 `config.example.json`。
- 切換實盤前：OKX API key 只開「交易」權限並關閉「提現」、綁 IP 白名單、`dry_run` 改 `false`、
  先用極小額 `stake_amount` 測試、把預設 UI 密碼與 `jwt_secret_key` 換掉。
- 新增/修改策略後務必跑 `make lookahead` 確認沒有未來函數偏誤，回測虧損屬正常現象。
