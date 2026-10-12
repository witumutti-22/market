"""バックテストエンジン（現物・ロングのみ）."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .strategies import Strategy

TRADING_DAYS = 245  # 東証のおおよその年間営業日数


@dataclass
class Trade:
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None

    @property
    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * self.shares


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    initial_cash: float = 0.0

    def metrics(self) -> dict[str, float]:
        eq = self.equity
        total_return = eq.iloc[-1] / self.initial_cash - 1
        years = len(eq) / TRADING_DAYS
        cagr = (eq.iloc[-1] / self.initial_cash) ** (1 / years) - 1 if years > 0 else 0.0
        daily = eq.pct_change().dropna()
        sharpe = daily.mean() / daily.std() * np.sqrt(TRADING_DAYS) if daily.std() > 0 else 0.0
        max_dd = (eq / eq.cummax() - 1).min()
        closed = [t for t in self.trades if t.exit_price is not None]
        wins = [t for t in closed if t.pnl > 0]
        return {
            "final_equity": float(eq.iloc[-1]),
            "total_return": float(total_return),
            "cagr": float(cagr),
            "sharpe": float(sharpe),
            "max_drawdown": float(max_dd),
            "trades": len(closed),
            "win_rate": len(wins) / len(closed) if closed else 0.0,
        }


def run_backtest(
    data: pd.DataFrame,
    strategy: Strategy,
    initial_cash: float = 1_000_000,
    lot_size: int = 100,
    commission_rate: float = 0.0,
    slippage: float = 0.0,
) -> BacktestResult:
    """シグナルは当日終値で確定し、翌営業日の始値で約定させる.

    lot_size: 売買単位（東証は 100 株）。
    commission_rate: 約定代金に対する手数料率。
    slippage: 約定価格に対する不利な滑り（0.001 = 0.1%）。
    """
    target = strategy.target_position(data).reindex(data.index).fillna(0).astype(int)
    cash = float(initial_cash)
    shares = 0
    trades: list[Trade] = []
    equity = []

    opens, closes, dates = data["open"].to_numpy(), data["close"].to_numpy(), data.index
    for i in range(len(data)):
        if i > 0:
            want = target.iloc[i - 1]
            if want == 1 and shares == 0:
                price = opens[i] * (1 + slippage)
                lots = int(cash // (price * lot_size * (1 + commission_rate)))
                if lots > 0:
                    shares = lots * lot_size
                    cash -= price * shares * (1 + commission_rate)
                    trades.append(Trade(dates[i], price, shares))
            elif want == 0 and shares > 0:
                price = opens[i] * (1 - slippage)
                cash += price * shares * (1 - commission_rate)
                trades[-1].exit_date, trades[-1].exit_price = dates[i], price
                shares = 0
        equity.append(cash + shares * closes[i])

    return BacktestResult(pd.Series(equity, index=dates, name="equity"), trades, initial_cash)
