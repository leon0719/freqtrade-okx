# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
EmaTrendFollow — 1h EMA 趨勢跟隨（順勢策略，與 DonchianBreakout 互補對照）

直接套用本專案三個已驗證教訓（見 DonchianBreakout 與記憶 strategy-research-findings）：
  1. 順勢方向（這市場逆勢均值回歸全虧）
  2. 讓利潤奔跑：minimal_roi 實質關閉，只靠 trailing + 訊號出場
  3. 熊市保護：只在 close > 長期 SMA（多頭 regime）時才進場

訊號維度與 Donchian 不同：Donchian 抓「價格突破前高」，本策略抓「快慢 EMA 動能交叉」。

- 進場：快 EMA 上穿慢 EMA（黃金交叉，動能轉多）且 close > regime_sma（多頭 regime）
- 出場：快 EMA 下穿慢 EMA（死亡交叉，動能轉弱），或 trailing / stoploss
- 風控：較寬 stoploss 容忍波動 + trailing 抓波段

hyperopt 注意：趨勢策略要用 CalmarHyperOptLoss、排除 roi space（Sharpe/Sortino 會閹割趨勢財）。
樣本：1h，2023-12-31 → 2026-06-17（含 2024 牛市）。樣本內 20240201-20250901 / 外 20250901-。

【驗證結論 2026-06-18】**採用 default 經典參數（fast21/slow55/regime600/sl-0.121/trailing 25%）**：
全期(2024-2026) +14.12%、Calmar 5.40、Sortino 1.90、回撤僅 5.78%、lookahead No。
Calmar-hyperopt 版（fast30/slow200）樣本內 +18% 但樣本外崩 -7.49%＝過擬合，故捨棄。
**再次印證：趨勢策略 default 經典參數常比 hyperopt 穩。** 與 DonchianBreakout(+16.56%/Calmar4.78)
旗鼓相當、可並行對照（本策略回撤更低、Calmar 更高；訊號維度為 EMA 動能交叉而非價格突破）。
"""
from datetime import datetime  # noqa: F401

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy, IntParameter, CategoricalParameter


class EmaTrendFollow(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    # 讓利潤奔跑：實質關閉 ROI，只靠 trailing + 死叉出場（順勢策略命脈，勿設低上限）
    minimal_roi = {
        "0": 10,
    }
    stoploss = -0.121

    trailing_stop = True
    trailing_stop_positive = 0.242
    trailing_stop_positive_offset = 0.251
    trailing_only_offset_is_reached = True

    # 涵蓋最大 regime SMA(720) + slow_ema(200) 暖機
    startup_candle_count: int = 800

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 可優化參數（都在進場/出場條件，放 buy space）
    fast_ema = IntParameter(10, 50, default=21, space="buy")
    slow_ema = IntParameter(50, 200, default=55, space="buy")
    regime_sma = IntParameter(200, 720, default=600, space="buy")
    use_regime = CategoricalParameter([True, False], default=True, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["fast_ema"] = ta.EMA(dataframe, timeperiod=self.fast_ema.value)
        dataframe["slow_ema"] = ta.EMA(dataframe, timeperiod=self.slow_ema.value)
        dataframe["regime_sma"] = ta.SMA(dataframe, timeperiod=self.regime_sma.value)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cond = (
            qtpylib.crossed_above(dataframe["fast_ema"], dataframe["slow_ema"])  # 黃金交叉
            & (dataframe["volume"] > 0)
        )
        if self.use_regime.value:
            cond &= dataframe["close"] > dataframe["regime_sma"]  # 熊市保護：空頭 regime 不進場
        dataframe.loc[cond, ["enter_long", "enter_tag"]] = (1, "ema_golden_cross")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_below(dataframe["fast_ema"], dataframe["slow_ema"])  # 死亡交叉
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
