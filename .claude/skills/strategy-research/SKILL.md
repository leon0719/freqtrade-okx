---
name: strategy-research
description: 在本 freqtrade-okx 專案中，系統化地研究加密貨幣技術指標、設計並迭代交易策略，以找出風險調整後報酬（Sharpe）最佳的策略。當使用者要求「找最佳策略」「優化策略」「比較指標」「研究 XX 指標」「調參數」「降低回撤」「提升勝率/Sharpe」，或想用各種技術指標組合出新策略時觸發。
---

# 策略研究助手（strategy-research）

在 `freqtrade-okx` 專案裡，用「假設 → 回測 → 防過擬合驗證 → 對照挑選」的循環，
參考各類加密貨幣技術指標，找出 **Sharpe 最佳**的策略。

主要評選標準：**風險調整後報酬（Sharpe / Sortino）**。hyperopt 預設用 `SharpeHyperOptLoss`。
報酬、回撤、勝率、交易數為輔助檢查指標，不可只看總報酬。

## 0. 開工前先確認

- 資料是否已下載：`make list-data`；不足就 `make download DAYS=90`（建議至少 60–90 天，樣本太短結論不可靠）。
- 既有策略基準：先 `make backtest` 拿到對照基準數字（報酬 / Sharpe / 回撤 / 勝率 / 交易數）。
- 一切在 dry-run，不碰真錢；所有指令走 `Makefile`（`make help`）。

## 1. 指標庫（設計進出場時的素材）

不要堆指標。**一條好策略通常 = 1 個趨勢過濾 + 1 個進場觸發 + 1 個出場/風控**，再多容易過擬合。
TA-Lib（`import talib.abstract as ta`）與 `technical.qtpylib` 都可用。

| 類別 | 指標 | 典型用途 |
|------|------|----------|
| 趨勢過濾 | EMA/SMA(50/200)、MACD、ADX、SAR、Ichimoku | 判斷大方向，只順勢交易、不接刀 |
| 進場觸發/動能 | RSI、Stochastic、StochRSI、CCI、Williams %R、ROC、MFI | 抓轉折/突破的時機點 |
| 波動/通道 | Bollinger Bands、ATR、Keltner、Donchian | 突破進場、用 ATR 設動態停損 |
| 量能確認 | volume、OBV、MFI、VWAP | 過濾無量假突破 |

設計原則：
- **趨勢過濾**決定「能不能做多」（例：`close > EMA200`），通常是提升勝率最有效的一招。
- **動能觸發**決定「何時進」（例：RSI 從低檔回升、StochRSI 黃金交叉）。
- **出場/風控**：訊號出場（RSI 超買）+ `minimal_roi` + `stoploss`（可用 ATR 動態化）+ `trailing_stop`。
- 進場條件**寧缺勿濫**：條件太鬆 → 交易數爆量、勝率崩（參考此專案 V2 的教訓）；太嚴 → 樣本太少不可信。

## 2. 把策略參數化（讓 hyperopt 能調）

新策略繼承 `IStrategy`，把要搜尋的數值改成可優化參數，hyperopt 才有東西可調：

```python
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter

class MyStrategy(IStrategy):
    timeframe = "5m"
    startup_candle_count = 200  # 用到 EMA200 時必須 >= 200

    # buy/sell space 的可調參數
    buy_rsi = IntParameter(20, 50, default=35, space="buy")
    buy_trend_ema = IntParameter(100, 200, default=200, space="buy")
    sell_rsi = IntParameter(60, 85, default=70, space="sell")
    # ROI 與 stoploss 也可交給 hyperopt 的 roi / stoploss / trailing space
```

進出場用 `self.buy_rsi.value` 取值。`populate_indicators` 算指標，
`populate_entry_trend` / `populate_exit_trend` 寫條件。

## 3. 研究循環（核心方法論）

對每個「假設」（= 一種指標組合）跑完整一輪，**逐一假設、不要一次塞十個指標**：

1. **建策略**：`make new-strategy NAME=MyHypothesisA`，寫入一個清楚的假設邏輯。
2. **樣本內回測**（in-sample）：保留最後一段資料當樣本外，例如
   `make backtest STRAT=MyHypothesisA TIMERANGE=20260301-20260520`
3. **hyperopt 調參**（以 Sharpe 為目標）：
   `make hyperopt STRAT=MyHypothesisA EPOCHS=150`（預設 `LOSS=SharpeHyperOptLoss`）
   `make hyperopt-show` 看最佳參數，回填進策略。
4. **樣本外驗證**（out-of-sample，最關鍵）：用**沒參與調參**的時間段重跑
   `make backtest STRAT=MyHypothesisA TIMERANGE=20260520-`
   樣本外若崩盤 → 是過擬合，丟棄或簡化。
5. **防偏誤檢查**：
   - `make lookahead`（look-ahead bias，偷看未來 = 回測虛假獲利）
   - `uv run freqtrade recursive-analysis --config user_data/config.json -s MyHypothesisA`
6. **多策略對照**：把候選一起跑
   `uv run freqtrade backtesting --config user_data/config.json --strategy-list A B C --timeframe 5m`

## 4. 評選與報告

以 **Sharpe 由高到低**排序候選，並用一張對照表呈現（最低限度欄位）：

| 策略 | Sharpe | Sortino | 總報酬% | 最大回撤% | 勝率% | 交易數 | 樣本外是否守住 |

挑選規則：
- 主排序 **Sharpe 最高**；Sharpe 相近時選**回撤較小**者。
- **樣本外必須撐住**：樣本內漂亮、樣本外崩 = 不選。
- 交易數要夠（30 天 / 5m 至少數十筆才有統計意義），太少的高 Sharpe 不可信。

**過擬合紅旗**（出現就降級或重做）：
- 樣本內 vs 樣本外績效落差巨大。
- hyperopt 參數落在搜尋範圍邊界（代表範圍沒框對）。
- 參數極端、條件超多、只在某一小段時間賺。
- 交易數個位數卻號稱高報酬。

## 5. 交付

完成一輪研究後，向使用者回報：
- 對照表（上面欄位）+ 一句話結論（推薦哪個、為什麼）。
- 推薦策略的**進出場邏輯白話說明**與**最佳參數**。
- 老實標註限制：樣本長度、僅回測未經長期 dry-run、過往績效不代表未來。
- 下一步建議（再迭代哪個方向 / 或丟去 `make trade` 做 dry-run 觀察）。

絕不誇大。回測虧損屬正常，找不到正報酬策略時就如實說，並提出可調整方向，不要硬湊數字。
