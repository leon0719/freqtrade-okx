# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
SampleStrategy — Freqtrade 入門範例策略

僅供學習/回測使用，不保證獲利。邏輯：
- 進場：RSI 從超賣區（<30）向上突破，且收盤價在 EMA 之上（順勢做多）
- 出場：RSI 進入超買區（>70）

用法：
  freqtrade backtesting -s SampleStrategy --timerange 20260101-20260601
"""
from datetime import datetime  # noqa: F401

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy


class SampleStrategy(IStrategy):
    INTERFACE_VERSION = 3

    # 交易時間框架
    timeframe = "5m"

    # 只做多
    can_short = False

    # 最低投資報酬（ROI）表：持倉時間(分鐘) -> 目標報酬率
    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01,
        "120": 0,
    }

    # 停損
    stoploss = -0.10

    # 移動停損
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    # 啟動所需的最少 K 棒數量
    startup_candle_count: int = 30

    # 進出場時是否只用訊號（不靠 ROI/停損）— 這裡用混合
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # EMA 趨勢過濾
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=21)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])  # EMA 黃金交叉
                & (dataframe["rsi"] < 70)  # 避免在超買區追高
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] > 70)  # 進入超買
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
