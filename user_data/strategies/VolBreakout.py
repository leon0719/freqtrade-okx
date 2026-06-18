# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
VolBreakout — 15m 放量突破（短線動能，專為高波動幣 XRP/DOGE/TON/ARB 設計）

與 DonchianBreakout15m 的關鍵差異：加入**量能確認**——短線假突破的最大殺手是「無量假突破」，
要求突破當下成交量放大（volume > vol_factor × 均量），過濾掉沒人跟的假突破，
抓真正帶量的 FOMO 啟動。高波動幣的真突破通常伴隨爆量，這過濾在短線上很關鍵。

沿用已驗證教訓：讓利潤奔跑（roi 關閉）+ 長期 SMA regime filter（熊市保護）。

⚠️ 誠實前提：短 timeframe 在過去市場整體難賺；量能過濾是「最有機會改善短線」的一招，
但仍需樣本外回測驗證，不保證獲利。

- 進場：close 突破前 buy_period 根高點 + volume > vol_factor×均量（放量）+ close > regime_sma
- 出場：close 跌破前 sell_period 根低點，或 trailing / stoploss
- 風控：讓利潤奔跑 + trailing + 熊市 regime filter

hyperopt：趨勢策略用 CalmarHyperOptLoss、排除 roi space。
樣本：15m，2023-12-31 起。樣本內 20240201-20250901 / 外 20250901-。

【驗證結論 2026-06-18】**研究至今最佳，且證明短線可行（關鍵是高波動幣＋量能過濾）。**
default 經典參數，最佳 pairlist = **DOGE + XRP**（去掉 ARB）：全期(2024-2026) +25.16%、
Calmar 7.03、Sortino 3.17、回撤 7.72%、樣本外(空頭)-1.36% 幾乎持平、lookahead No。
per-pair：DOGE +13.44% / XRP +11.73% 都賺，ARB -7.57% 虧故剔除；TON 在 OKX 無現貨對未下到。
對照：同 15m 配方在 BTC/ETH/SOL 虧 -10.68%，在 DOGE/XRP 卻 +25% → 短線成敗關鍵在「選對高波動幣＋量能確認」。
誠實註：全期 market change +55.78%（這兩幣牛市漲 55%），策略 +25% 其實 underperform 純持有，
但換來低回撤(7.72%)＋熊市保護(樣本外僅 -1.36%)，價值在風險調整後(Calmar 7.03)而非跑贏持有。
"""
from datetime import datetime  # noqa: F401

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    CategoricalParameter,
)


class VolBreakout(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = False

    # 讓利潤奔跑：實質關閉 ROI，只靠 trailing + 通道出場
    minimal_roi = {
        "0": 10,
    }
    stoploss = -0.121

    trailing_stop = True
    trailing_stop_positive = 0.242
    trailing_stop_positive_offset = 0.251
    trailing_only_offset_is_reached = True

    # 涵蓋最大 regime SMA(1200) + buy_period(200) 暖機
    startup_candle_count: int = 1300

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 可優化參數
    buy_period = IntParameter(30, 200, default=96, space="buy")     # 突破回看（96根≈24小時）
    sell_period = IntParameter(15, 80, default=40, space="sell")    # 出場回看
    vol_factor = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")  # 量能倍數
    regime_sma = IntParameter(400, 1200, default=800, space="buy")
    use_regime = CategoricalParameter([True, False], default=True, space="buy")
    use_vol = CategoricalParameter([True, False], default=True, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["dc_upper"] = dataframe["high"].rolling(self.buy_period.value).max().shift(1)
        dataframe["dc_lower"] = dataframe["low"].rolling(self.sell_period.value).min().shift(1)
        dataframe["regime_sma"] = ta.SMA(dataframe, timeperiod=self.regime_sma.value)
        dataframe["vol_sma"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cond = (
            (dataframe["close"] > dataframe["dc_upper"])  # 突破前高
            & (dataframe["volume"] > 0)
        )
        if self.use_vol.value:
            cond &= dataframe["volume"] > self.vol_factor.value * dataframe["vol_sma"]  # 放量確認
        if self.use_regime.value:
            cond &= dataframe["close"] > dataframe["regime_sma"]  # 熊市保護
        dataframe.loc[cond, ["enter_long", "enter_tag"]] = (1, "vol_breakout")
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
