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

### 1.1 順勢 vs 逆勢：先選對「方向性」（本專案實證，最重要）

策略賺賠的第一決定因素是**方向性對不對 regime**，比指標選擇更關鍵：
- **逆勢（均值回歸 / 抄底）**：跌破布林下軌 + RSI 超賣抓反彈。**只在震盪市有效；趨勢市（尤其空頭）會一路接刀**。
  本專案 5m 均值回歸在 2025-26 空頭段全面失血，per-pair/360天/換 loss 都救不了。
- **順勢（突破 / 趨勢跟隨）**：突破 Donchian 上軌/前高跟進。**牛市賺大波段；震盪市被假突破巴**。

**順勢策略三大陷阱（本專案血淚，務必避開）**：
1. **`minimal_roi` 不可設低上限** → 會砍掉賴以獲利的大波段，連 +89% 牛市都能做成 -15%。順勢策略 ROI 設很高（`{"0": 10}`）實質關閉，只靠 trailing + 通道出場「讓利潤奔跑」。
2. **不可用 Sharpe/Sortino loss 做 hyperopt** → 它們懲罰波動，會把趨勢策略閹割成「早出場鎖小利」（實測重 hyperopt 後 -20%）。趨勢策略 hyperopt 要用 **`CalmarHyperOptLoss`** 或排除 roi/trailing space，甚至手動設「寬鬆出場」別過度 hyperopt。
3. **加長期 SMA regime filter**（`close > SMA(~600根/25天)` 才進場）是拉高風險調整報酬最有效的一招 → 砍掉熊市爛突破，本專案報酬翻 3 倍（+4.8%→+16.6%）、回撤砍半。

**先用 `Market change`（回測報告內）確認資料段是牛/熊/震盪**，再選方向性。逆著 regime 做注定虧。

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

### 2.1 進階功能（Freqtrade callbacks）— 進階素材，非必用

基礎三函數不夠時，可用這些。**但先確認瓶頸是什麼**：本專案實證下列工具多半把交易數砍更少（見教訓）。

- **多時間框架過濾（`@informative`）**：5m 進場但用 1h 趨勢確認方向，過濾雜訊。
  ```python
  from freqtrade.strategy import informative
  @informative("1h")
  def populate_indicators_1h(self, dataframe, metadata):
      dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
      return dataframe
  # 主框架條件裡用合併後的欄位（自動加 _1h 後綴）：dataframe["close_1h"] > dataframe["ema50_1h"]
  ```
  需先 `make download TF=1h`，且 `startup_candle_count` 要涵蓋 1h 暖機（50 根 1h ≈ 600 根 5m）。
- **動態止損（`custom_stoploss`）**：依持倉盈利收緊止損。**回傳值是相對「當前價」的比例，鎖開倉價要用 `stoploss_from_open`**：
  ```python
  from freqtrade.strategy import stoploss_from_open
  def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
      if current_profit >= 0.02:
          return stoploss_from_open(0.01, current_profit, is_short=False)  # 鎖在開倉價 +1%
      return self.stoploss
  # 需設 use_custom_stoploss = True
  ```
- **動態倉位（`custom_stake_amount`）**：高波動（ATR 大）降倉、低波動加倉。
- **量能過濾**：`volume > vol_factor * volume.rolling(20).mean()`，過濾無量假突破。

把要驗證的進階開關做成 `CategoricalParameter([True, False])`，交給 hyperopt 自己決定開不開 → **乾淨歸因**：無效它會關掉。

> **實證教訓（2026-06，BBMeanRevHTF）**：1h 趨勢過濾 + 量能過濾(2.5×) 在樣本內被 hyperopt 選上（提高 objective），
> 但把均值回歸本就稀疏的訊號砍到樣本內 11 筆、樣本外 3 筆 → 不可信。**過濾類技巧只適合「訊號多、需汰選品質」的策略；
> 訊號本就稀疏時別再疊過濾，那只會惡化樣本不足**。瓶頸是訊號數/資料量時，該做的是拉長 timeframe 或下載更多資料，而非加過濾。
> 另：所有進階 callback 寫完都要 `make lookahead` 驗證沒引入未來偏誤（informative 合併、custom_stoploss 都是常見出錯點）。

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
5. **診斷優化**（找出哪裡賺賠，據此改進出場）：`make backtest-analysis`（讀最近一次回測，
   `make backtest` 已自動 `--export signals`）。看 Group 3/4 的 `enter_reason / exit_reason / pair`
   各自賺賠：哪個 pair 或哪種出場原因在虧 → 針對性收緊/移除該條件，而非盲調 hyperopt。
   **訣竅**：進場時設 `enter_tag`（例：`dataframe.loc[cond, ["enter_long","enter_tag"]] = (1, "bb_oversold")`），
   不同進場邏輯就會在 analysis 表分開歸因，看得出哪條進場規則賺、哪條賠。
6. **防偏誤檢查**：
   - `make lookahead`（look-ahead bias，偷看未來 = 回測虛假獲利）
   - `make recursive`（指標遞迴穩定性，startup 不足會讓指標漂移）
7. **多策略對照**：把候選一起跑
   `uv run freqtrade backtesting --config user_data/config.json --strategy-list A B C --timeframe 5m`

## 4. 評選與報告

以 **Sharpe 由高到低**排序候選，並用一張對照表呈現（最低限度欄位）：

| 策略 | Sharpe | Sortino | 總報酬% | 最大回撤% | 勝率% | 交易數 | 樣本外是否守住 |

挑選規則：
- 主排序 **Sharpe 最高**；Sharpe 相近時選**回撤較小**者。
- **但趨勢/順勢策略改看 Sortino 與 Calmar，不要只看 Sharpe** → Sharpe 把「大賺的上行波動」也當風險罰，
  天生對趨勢策略不友善（本專案 DonchianBreakout：Sharpe 僅 0.53 看似差，但 Sortino 1.89、Calmar 4.78 其實很好）。
  Sortino 只罰下行波動、Calmar = 報酬/最大回撤，才真實反映「少數大賺、多數小賠」的趨勢策略品質。
- **樣本外必須撐住**：樣本內漂亮、樣本外崩 = 不選。
- 交易數要夠（30 天 / 5m 至少數十筆才有統計意義），太少的高 Sharpe 不可信。

**及格線（業界 / 文章常見參考值，非硬性）**：3 個月總報酬 > 15%、勝率 > 50%、最大回撤 < 20%、Sharpe > 1.0。
> 誠實註記：本專案目前資料區間（2026 春，BTC/ETH/SOL 偏震盪/偏空）**沒有任何策略達到這條及格線**，
> 多數連正報酬都做不到——這是市場環境問題，不是調參不夠。此時的合理目標是「風險調整後明顯優於基準
> （Sharpe 沒那麼負、回撤大幅縮小）」，並如實說明未達及格線，**絕不為了湊及格線而過擬合**。

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
