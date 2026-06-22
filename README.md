# freqtrade-okx

本地 Freqtrade 量化交易開發環境，串接 **OKX**。用 `uv` 管理 Python 依賴，預設 **dry-run（模擬盤）**，不碰真錢。

## 環境

- Python 3.12（由 `uv` 管理，`.python-version` 已鎖定）
- Freqtrade 2026.5.1、CCXT 4.5.x
- TA-Lib C 函式庫（已透過 `brew install ta-lib` 安裝）

## 專案結構

```
freqtrade-okx/
├── pyproject.toml                    # uv 依賴（freqtrade）
├── docker-compose.yml                # 雙 bot 常駐部署（donchian 8080 + nfi 8081）
├── user_data/
│   ├── config.json                   # 主 bot 設定（含 API key / 帳密，已 gitignore）
│   ├── config.nfi.json               # NFI 對照組設定（已 gitignore）
│   ├── config.example.json           # 可提交的範本
│   ├── strategies/
│   │   ├── DonchianBreakout.py       # 主策略：順勢通道突破（1h，BTC/ETH/SOL）
│   │   └── NostalgiaForInfinityX7.py # 對照組：社群 DCA 策略（5m，~57 檔 USDT，第三方碼）
│   └── data/okx/                     # 下載的歷史 K 線（已 gitignore）
```

## 策略一覽

| Bot | 策略 | 哲學 | TF | UI Port |
|-----|------|------|-----|---------|
| 主 | `DonchianBreakout` | 順勢、追突破、讓利潤奔跑 | 1h | 8080 |
| 對照 | `NostalgiaForInfinityX7` | 接刀、DCA 攤平、小利累積（[社群最廣用策略](https://github.com/iterativv/NostalgiaForInfinity)） | 5m | 8081 |

> 📖 完整操作流程與 Makefile 指令封裝見 [`docs/操作指南.md`](docs/操作指南.md)，日常用 `make help` 即可查。

## 常用指令（皆以 `uv run` 前綴）

```bash
# 驗證設定檔
uv run freqtrade show-config --config user_data/config.json

# 下載 OKX 歷史資料
uv run freqtrade download-data --config user_data/config.json \
  --pairs BTC/USDT ETH/USDT SOL/USDT --timeframe 1h --days 180

# 回測
uv run freqtrade backtesting --config user_data/config.json \
  -s DonchianBreakout --timeframe 1h --timerange 20260518-

# 超參數最佳化（hyperopt）
uv run freqtrade hyperopt --config user_data/config.json \
  -s DonchianBreakout --hyperopt-loss SharpeHyperOptLoss -e 100

# 模擬盤實時運行（dry-run，不下真單）
uv run freqtrade trade --config user_data/config.json -s DonchianBreakout

# 雙 bot 常駐（主策略 + NFI 對照，背景跑）
make up        # = docker compose up -d；詳見 docs/DEPLOY.md

# 開新策略範本
uv run freqtrade new-strategy -s MyStrategy
```

## 切換到實盤前（謹慎！）

1. 在 OKX 建立 API key，**只開「交易」權限、務必關閉「提現」**，並綁定 IP 白名單。
2. 把 key 填進 `user_data/config.json` 的 `exchange.key` / `secret` / `password`(passphrase)。
3. 將 `config.json` 的 `"dry_run"` 改為 `false`。
4. 先用**極小額** `stake_amount` 測試，確認下單與成交行為正常。

⚠️ `config.json` 已被 `.gitignore` 排除，避免 key 外洩。切勿把含 key 的設定提交到 git。

## 風險提醒

- 範例策略僅供學習，**回測虧損屬正常**，過往績效不代表未來。
- 任何策略上實盤前都應充分回測 + 長時間 dry-run 驗證。
- 加密貨幣交易具高風險，請自負盈虧。
