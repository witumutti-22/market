"""売買戦略.

戦略は価格データから「目標ポジション」系列（1=買い持ち, 0=ノーポジ）を返す。
シグナルはその日の終値で確定し、翌営業日の始値で約定する想定（先読み防止）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from . import indicators as ind


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def target_position(self, data: pd.DataFrame) -> pd.Series:
        """各日の終値時点での目標ポジション (0 or 1)."""


class SmaCross(Strategy):
    """短期移動平均が長期移動平均を上回っている間だけ保有する."""

    name = "sma"

    def __init__(self, fast: int = 5, slow: int = 25):
        if fast >= slow:
            raise ValueError("fast は slow より小さくしてください")
        self.fast, self.slow = fast, slow

    def target_position(self, data: pd.DataFrame) -> pd.Series:
        fast = ind.sma(data["close"], self.fast)
        slow = ind.sma(data["close"], self.slow)
        return (fast > slow).astype(int).where(slow.notna(), 0)


class RsiReversion(Strategy):
    """RSI が売られすぎ水準で買い、買われすぎ水準で手仕舞う逆張り."""

    name = "rsi"

    def __init__(self, window: int = 14, buy_below: float = 30, sell_above: float = 70):
        self.window, self.buy_below, self.sell_above = window, buy_below, sell_above

    def target_position(self, data: pd.DataFrame) -> pd.Series:
        r = ind.rsi(data["close"], self.window)
        pos, holding = [], 0
        for v in r:
            if pd.notna(v):
                if not holding and v < self.buy_below:
                    holding = 1
                elif holding and v > self.sell_above:
                    holding = 0
            pos.append(holding)
        return pd.Series(pos, index=data.index)


STRATEGIES: dict[str, type[Strategy]] = {s.name: s for s in (SmaCross, RsiReversion)}
