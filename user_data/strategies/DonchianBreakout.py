# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
DonchianBreakout — 1h Donchian 通道突破（順勢策略）

動機：均值回歸（接刀）在 BTC/ETH/SOL 過去一年偏空/震盪市場全面失血（見研究進度的
決定性結論）。改走**順勢**：價格突破近期高點 = 動能啟動 → 跟進做多，跌破近期低點 = 趨勢
轉弱 → 出場。順趨勢而非逆勢接刀，並靠 trailing stop 讓獲利奔跑、虧損快砍。

- 進場：close 突破「前 buy_period 根的最高」（Donchian 上軌，shift(1) 不含當根 → 無未來偏誤）
        可選 EMA 趨勢過濾（只在 close > EMA 時順勢突破）
- 出場：close 跌破「前 sell_period 根的最低」（Donchian 下軌），或 trailing / stoploss
- 風控：較寬 stoploss 容忍波動 + trailing stop 抓波段

【演進 2026-06，1h 2024-2026 含牛熊】**研究第一個正報酬策略**。
關鍵發現：原本帶 roi 封頂(0.14)時牛市(+89%)也虧 -14.83%、空頭虧 -17.99%＝roi 封頂扼殺
順勢策略命脈「讓利潤奔跑」。**移除 roi 封頂後**：2024 牛市 +14.82%、空頭 -4.63%、
全期(2024-2026) +4.82%(Sharpe +0.16，buy&hold 僅 -1.59%)＝牛賺熊守、outperform 持有。
勝率僅 34.5% 卻賺＝靠少數大波段的正確順勢 DNA。lookahead No(shift(1) 無偏誤)。
★ 教訓：**順勢策略的 minimal_roi 不可設低上限**，hyperopt 的 roi space 會在空頭段調出
「早獲利了結」反而閹割趨勢財 → 順勢策略 hyperopt 應排除 roi space（SPACES=buy sell trailing stoploss）。

★★ 第二教訓：在含牛熊區間用 SortinoHyperOptLossDaily 重 hyperopt（排除 roi）反而把全期做成 -20%、
牛市 -2.79%——它選了 sell_period=12 + trailing 5%啟動鎖1.5% 的「早出場鎖小利」解。
**Sharpe/Sortino loss 懲罰波動，而順勢策略的大波段必然帶回撤波動 → 這類 loss 系統性閹割趨勢策略。**
故當前用「手動寬鬆出場」參數（buy 70 / sell 32 / trailing 25%啟動鎖24% / stoploss -0.121 / use_trend）。
趨勢策略若要 hyperopt，應改用 Calmar/總報酬導向 loss，不可用 Sharpe/Sortino。

★★★ 第三進展（熊市保護 regime filter）：加「只在 close > 長期 SMA(regime_sma=600，約25天) 時才突破進場」
後大躍進——全期(2024-2026) +16.56%、Calmar 4.78、Sortino 1.89、回撤僅 7.65%、lookahead No。
2024 牛市段 Sharpe 1.31。**研究最佳、堪用版本。** regime filter 砍掉熊市的爛突破，只留多頭 regime 的好突破。
註：Sharpe 僅 0.53 對趨勢策略偏嚴（它連大賺的上行波動都當風險罰）→ 趨勢策略該看 Sortino(1.89)/Calmar(4.78)。
限制：空頭段仍小虧 -6%（SMA regime 在熊市反彈會誤判），未經 dry-run。

全參數化。樣本：1h，2023-12-31 → 2026-06-17（含 2024 牛市 / 2025-26 空頭）。
"""

from datetime import datetime  # noqa: F401

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter, CategoricalParameter


class DonchianBreakout(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    # 順勢策略「讓利潤奔跑」是命脈：實質關閉 ROI（設 1000%），只靠 trailing + 通道出場。
    # 切勿給低 roi 上限——實測 roi 封頂 0.14 會讓牛市也虧 -14.83%（砍掉大波段）。
    minimal_roi = {
        "0": 10,
    }
    stoploss = -0.121

    trailing_stop = True
    trailing_stop_positive = 0.242
    trailing_stop_positive_offset = 0.251
    trailing_only_offset_is_reached = True

    # 涵蓋最大 regime SMA(720) + buy_period(80) 暖機
    startup_candle_count: int = 800

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 可優化參數
    buy_period = IntParameter(20, 80, default=70, space="buy")  # 突破回看週期
    sell_period = IntParameter(10, 40, default=32, space="sell")  # 出場回看週期（較短）
    trend_ema = IntParameter(50, 200, default=74, space="buy")  # 趨勢過濾 EMA
    use_trend = CategoricalParameter([True, False], default=True, space="buy")
    # 熊市保護：只在大盤站上長期 SMA（多頭 regime）時才突破進場，空頭段休息避開回吐
    regime_sma = IntParameter(200, 720, default=600, space="buy")
    use_regime = CategoricalParameter([True, False], default=True, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Donchian 通道：用 shift(1) → 只看「截至前一根」的高低點，當根 close 突破才算（無未來偏誤）
        dataframe["dc_upper"] = (
            dataframe["high"].rolling(self.buy_period.value).max().shift(1)
        )
        dataframe["dc_lower"] = (
            dataframe["low"].rolling(self.sell_period.value).min().shift(1)
        )
        dataframe["trend_ema"] = ta.EMA(dataframe, timeperiod=self.trend_ema.value)
        dataframe["regime_sma"] = ta.SMA(dataframe, timeperiod=self.regime_sma.value)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cond = (
            (dataframe["close"] > dataframe["dc_upper"])  # 突破前 N 根高點
            & (dataframe["volume"] > 0)
        )
        if self.use_trend.value:
            cond &= dataframe["close"] > dataframe["trend_ema"]  # 只順勢突破
        if self.use_regime.value:
            cond &= (
                dataframe["close"] > dataframe["regime_sma"]
            )  # 熊市保護：空頭 regime 不進場
        dataframe.loc[cond, ["enter_long", "enter_tag"]] = (1, "dc_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["dc_lower"])  # 跌破近期低點 → 趨勢轉弱
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
