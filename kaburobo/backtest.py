"""バックテストエンジン（現物・ロングのみ・複数銘柄対応）."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .risk import RiskRules
from .strategies import Strategy

TRADING_DAYS = 245  # 東証のおおよその年間営業日数


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason: str | None = None  # signal / stop_loss / trailing_stop / take_profit
    peak: float = 0.0

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

    def by_symbol(self) -> pd.DataFrame:
        """銘柄ごとの取引回数・損益・手仕舞い理由の内訳."""
        rows = [
            {"symbol": t.symbol, "pnl": t.pnl, "win": t.pnl > 0, "reason": t.exit_reason}
            for t in self.trades
            if t.exit_price is not None
        ]
        if not rows:
            return pd.DataFrame(columns=["trades", "pnl", "win_rate"])
        df = pd.DataFrame(rows)
        out = df.groupby("symbol").agg(trades=("pnl", "size"), pnl=("pnl", "sum"), win_rate=("win", "mean"))
        reasons = df.pivot_table(index="symbol", columns="reason", values="pnl", aggfunc="size", fill_value=0)
        return out.join(reasons)


def run_backtest(
    data: pd.DataFrame | dict[str, pd.DataFrame],
    strategy: Strategy,
    initial_cash: float = 1_000_000,
    lot_size: int = 100,
    commission_rate: float = 0.0,
    slippage: float = 0.0,
    risk: RiskRules | None = None,
    max_positions: int | None = None,
) -> BacktestResult:
    """シグナルは当日終値で確定し、翌営業日の始値で約定させる.

    data: 1 銘柄の DataFrame、または {銘柄コード: DataFrame}。
    lot_size: 売買単位（東証は 100 株）。
    commission_rate: 約定代金に対する手数料率。
    slippage: 約定価格に対する不利な滑り（0.001 = 0.1%）。
    risk: 損切り・利確ルール。足の高値・安値で場中に判定する。
        ルールで手仕舞った銘柄は、戦略のシグナルが一度 0 に戻るまで再エントリーしない。
    max_positions: 同時に保有する最大銘柄数（既定は銘柄数）。
        1 銘柄あたりの投資額は「前日の総資産 / max_positions」が上限。
    """
    if isinstance(data, pd.DataFrame):
        data = {"_": data}
    symbols = list(data)
    max_positions = max_positions or len(symbols)
    risk = risk or RiskRules()

    index = pd.DatetimeIndex(sorted(set().union(*(d.index for d in data.values()))))
    # 前日終値のシグナル = 当日始値で取りたいポジション。その銘柄の足がない日は NaN。
    want = pd.DataFrame(
        {s: strategy.target_position(d).reindex(d.index).fillna(0).shift(1) for s, d in data.items()}
    ).reindex(index)
    opens = pd.DataFrame({s: d["open"] for s, d in data.items()}).reindex(index)
    highs = pd.DataFrame({s: d["high"] for s, d in data.items()}).reindex(index)
    lows = pd.DataFrame({s: d["low"] for s, d in data.items()}).reindex(index)
    closes = pd.DataFrame({s: d["close"] for s, d in data.items()}).reindex(index)
    marks = closes.ffill()

    cash = float(initial_cash)
    open_trades: dict[str, Trade] = {}
    blocked: set[str] = set()  # ルールで手仕舞い後、シグナルのリセット待ち
    trades: list[Trade] = []
    equity: list[float] = []
    prev_equity = cash

    def close_trade(sym: str, date, price: float, reason: str) -> None:
        nonlocal cash
        t = open_trades.pop(sym)
        cash += price * t.shares * (1 - commission_rate)
        t.exit_date, t.exit_price, t.exit_reason = date, price, reason

    for date in index:
        w, o, h, l, c = want.loc[date], opens.loc[date], highs.loc[date], lows.loc[date], closes.loc[date]

        # 1) シグナルによる手仕舞い（始値）
        for sym in list(open_trades):
            if pd.notna(o[sym]) and w[sym] == 0:
                close_trade(sym, date, o[sym] * (1 - slippage), "signal")
        for sym in list(blocked):
            if w[sym] == 0:
                blocked.discard(sym)

        # 2) 新規エントリー（始値）
        for sym in symbols:
            if len(open_trades) >= max_positions:
                break
            if pd.isna(o[sym]) or w[sym] != 1 or sym in open_trades or sym in blocked:
                continue
            price = o[sym] * (1 + slippage)
            budget = min(cash, prev_equity / max_positions)
            lots = int(budget // (price * lot_size * (1 + commission_rate)))
            if lots > 0:
                shares = lots * lot_size
                cash -= price * shares * (1 + commission_rate)
                t = Trade(sym, date, price, shares, peak=price)
                open_trades[sym] = t
                trades.append(t)

        # 3) 場中の損切り・利確
        if risk.enabled:
            for sym in list(open_trades):
                if pd.isna(o[sym]):
                    continue
                t = open_trades[sym]
                hit = risk.check(t.entry_price, t.peak, o[sym], h[sym], l[sym])
                if hit:
                    price, reason = hit
                    close_trade(sym, date, price * (1 - slippage), reason)
                    blocked.add(sym)
                else:
                    t.peak = max(t.peak, h[sym])

        m = marks.loc[date]
        prev_equity = cash + sum(t.shares * m[s] for s, t in open_trades.items())
        equity.append(prev_equity)

    return BacktestResult(pd.Series(equity, index=index, name="equity"), trades, initial_cash)
