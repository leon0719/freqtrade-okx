# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
SampleStrategyV2 — 在 SampleStrategy 基礎上加「趨勢過濾」的改進版

相對原版的三項改動：
1. 加長期趨勢過濾：只在 close > EMA200（大方向偏多）時才做多，不在跌勢接刀。
2. RSI 設下限：只在 45 < RSI < 65 進場，避開「弱反彈」與「追高」。
3. 出場更積極：除了 RSI>70，EMA9 死亡交叉 EMA21 也出場；停損收緊到 -6%。

僅供學習/回測，不保證獲利。
"""
from datetime import datetime  # noqa: F401

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy


class SampleStrategyV2(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False

    # ROI 表（與原版相同，方便對照進出場訊號的影響）
    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01,
        "120": 0,
    }

    # 停損收緊：原版 -10% → -6%
    stoploss = -0.06

    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    # 因為用到 EMA200，啟動 K 棒數要 >= 200
    startup_candle_count: int = 200

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=21)
        # 長期趨勢線：價格在它之上才視為多頭
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])  # 黃金交叉
                & (dataframe["close"] > dataframe["ema_trend"])  # 大趨勢偏多才做多
                & (dataframe["rsi"] > 45)  # 動能不能太弱（避免接刀）
                & (dataframe["rsi"] < 65)  # 也不過熱（避免追高）
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (
                    (dataframe["rsi"] > 70)  # 超買出場
                    | qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"])  # 死亡交叉出場
                )
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
