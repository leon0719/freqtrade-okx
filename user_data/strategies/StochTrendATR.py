# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
StochTrendATR — strategy-research 產出的參數化策略

假設：在「大趨勢偏多」時，用 StochRSI 抓回檔後的動能轉強進場，並用 ATR 設動態停損。
- 趨勢過濾：close > EMA(trend_ema)，只順勢做多。
- 進場觸發：StochRSI 的 %K 由下向上穿越 %D，且 %K 仍在偏低區（避免追高）。
- 出場：StochRSI %K 進入超買區。
- 風控：custom_stoploss 用 ATR 動態停損（波動大則停損寬、波動小則緊）。

所有關鍵數值皆為 hyperopt 可調參數，以 SharpeHyperOptLoss 最佳化。
"""
from datetime import datetime
from functools import reduce

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
)
from freqtrade.persistence import Trade


class StochTrendATR(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False

    # ROI 與停損交給 hyperopt 的 roi / stoploss space，但給合理初值
    minimal_roi = {
        "0": 0.05,
        "30": 0.025,
        "60": 0.01,
        "120": 0,
    }
    stoploss = -0.08  # 後備固定停損；實際以 custom_stoploss(ATR) 為主

    trailing_stop = False

    # 用到 EMA200，啟動 K 棒數須 >= 200
    startup_candle_count: int = 200

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    use_custom_stoploss = True

    # ---- hyperopt 可調參數 --------------------------------------------------
    # 趨勢過濾長度
    buy_trend_ema = IntParameter(100, 200, default=200, space="buy")
    # StochRSI 進場時 %K 上限（偏低才進，避免追高）
    buy_stoch_max = IntParameter(20, 50, default=35, space="buy")
    # StochRSI 出場超買門檻
    sell_stoch = IntParameter(70, 95, default=80, space="sell")
    # ATR 停損倍數：停損距離 = atr_mult * ATR / price
    atr_mult = DecimalParameter(2.0, 8.0, default=4.0, decimals=1, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 趨勢線（取最大可能長度算一次，進場時依參數選用對應欄位）
        for length in self.buy_trend_ema.range:
            dataframe[f"ema_{length}"] = ta.EMA(dataframe, timeperiod=length)

        # StochRSI（%K / %D）
        stoch = ta.STOCHRSI(dataframe, timeperiod=14, fastk_period=3, fastd_period=3)
        dataframe["srsi_k"] = stoch["fastk"]
        dataframe["srsi_d"] = stoch["fastd"]

        # ATR（給動態停損用）
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend_col = f"ema_{self.buy_trend_ema.value}"
        conditions = [
            dataframe["close"] > dataframe[trend_col],  # 大趨勢偏多
            qtpylib.crossed_above(dataframe["srsi_k"], dataframe["srsi_d"]),  # StochRSI 黃金交叉
            dataframe["srsi_k"] < self.buy_stoch_max.value,  # 仍在偏低區，不追高
            dataframe["volume"] > 0,
        ]
        dataframe.loc[reduce(lambda a, b: a & b, conditions), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["srsi_k"] > self.sell_stoch.value)  # StochRSI 超買
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        """以進場當下的 ATR 設動態停損距離（相對開倉價的負比例）。"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return self.stoploss
        last_atr = dataframe["atr"].iat[-1]
        if last_atr is None or last_atr <= 0 or current_rate <= 0:
            return self.stoploss
        # 停損距離（正數比例），回傳需為負值
        sl_distance = (self.atr_mult.value * last_atr) / current_rate
        return -abs(sl_distance)
