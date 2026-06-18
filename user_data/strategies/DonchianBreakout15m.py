# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
DonchianBreakout15m — 15m Donchian 通道突破（短期順勢，配方同 1h 版）

短期交易版本：把已驗證的成功配方（順勢突破 + regime filter + 讓利潤奔跑）搬到 15m，
比 1h 版交易更頻繁，但比 5m 雜訊少、手續費侵蝕較輕。週期/regime 已適配 15m 尺度。

⚠️ 誠實前提：研究顯示短 timeframe 在 BTC/ETH/SOL 過去市場較難賺（雜訊+手續費），
本策略是「用最有機會的配方去試」，不保證獲利，需以樣本外回測與 dry-run 驗證。

- 進場：close 突破前 buy_period 根高點（Donchian 上軌，shift(1) 無未來偏誤）且 close > regime_sma
- 出場：close 跌破前 sell_period 根低點，或 trailing / stoploss
- 風控：讓利潤奔跑（roi 關閉）+ trailing + 熊市 regime filter

hyperopt 注意：趨勢策略用 CalmarHyperOptLoss、排除 roi space；經常 default 經典參數比 hyperopt 穩。
樣本：15m，補滿至 2024（含牛市）。樣本內 20240201-20250901 / 外 20250901-。

【驗證結論 2026-06-18】**失敗**：default 樣本內 -5.93%；Calmar-hyperopt 後樣本內勉強 +0.41%、
但樣本外崩 -10.91%、全期 -10.68%（Calmar -1.47）＝過擬合。同配方 1h 版 +16.56%、15m 卻虧。
**鐵證：短 timeframe(15m) 在此市場即使套成功配方+對的 loss 也做不出來**（雜訊+假突破+手續費侵蝕）。
不建議拿去 dry-run。保留作「短期難賺」的對照證據。
"""
from datetime import datetime  # noqa: F401

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter, CategoricalParameter


class DonchianBreakout15m(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = False

    # 讓利潤奔跑：實質關閉 ROI，只靠 trailing + 通道出場（順勢命脈，勿設低上限）
    minimal_roi = {
        "0": 10,
    }
    stoploss = -0.291

    trailing_stop = True
    trailing_stop_positive = 0.116
    trailing_stop_positive_offset = 0.144
    trailing_only_offset_is_reached = True

    # 涵蓋最大 regime SMA(1200) + buy_period(300) 暖機
    startup_candle_count: int = 1300

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 可優化參數（已適配 15m 尺度：1h 的 1 根 ≈ 15m 的 4 根）
    buy_period = IntParameter(50, 300, default=256, space="buy")    # 突破回看（200根≈50小時）
    sell_period = IntParameter(20, 100, default=77, space="sell")   # 出場回看（較短）
    regime_sma = IntParameter(400, 1200, default=821, space="buy")  # regime（800根≈8.3天）
    use_regime = CategoricalParameter([True, False], default=True, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["dc_upper"] = dataframe["high"].rolling(self.buy_period.value).max().shift(1)
        dataframe["dc_lower"] = dataframe["low"].rolling(self.sell_period.value).min().shift(1)
        dataframe["regime_sma"] = ta.SMA(dataframe, timeperiod=self.regime_sma.value)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cond = (
            (dataframe["close"] > dataframe["dc_upper"])
            & (dataframe["volume"] > 0)
        )
        if self.use_regime.value:
            cond &= dataframe["close"] > dataframe["regime_sma"]
        dataframe.loc[cond, ["enter_long", "enter_tag"]] = (1, "dc_breakout_15m")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["dc_lower"])
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
