"""ロボット本体: 最新データから売買判断を行い、ブローカーに発注する.

日足なら 1 日 1 回、引け後に実行する想定。約定価格は直近終値で近似する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .broker import Broker, Order, PaperBroker
from .risk import RiskRules
from .strategies import Strategy


@dataclass
class Holding:
    entry: float
    peak: float


@dataclass
class Robot:
    strategy: Strategy
    broker: Broker
    risk: RiskRules = field(default_factory=RiskRules)
    max_positions: int | None = None
    lot_size: int = 100
    holdings: dict[str, Holding] = field(default_factory=dict)
    blocked: set[str] = field(default_factory=set)  # ルールで手仕舞い後、シグナルのリセット待ち

    def step(self, data: dict[str, pd.DataFrame]) -> list[Order]:
        """全銘柄について売り → 買いの順に判断し、発注した注文を返す."""
        max_positions = self.max_positions or len(data)
        last = {s: d.iloc[-1] for s, d in data.items()}
        want = {s: int(self.strategy.target_position(d).iloc[-1]) for s, d in data.items()}
        orders: list[Order] = []

        def sell(sym: str) -> None:
            order = Order(sym, "sell", self.broker.position(sym), float(last[sym]["close"]))
            self.broker.submit(order)
            orders.append(order)
            self.holdings.pop(sym, None)

        # 1) 損切り・利確（終値で判定）とシグナルによる手仕舞い
        for sym in data:
            if self.broker.position(sym) == 0:
                self.holdings.pop(sym, None)
                continue
            close = float(last[sym]["close"])
            h = self.holdings.setdefault(sym, Holding(close, close))
            if self.risk.enabled and self.risk.check(h.entry, h.peak, close, close, close):
                sell(sym)
                self.blocked.add(sym)
            elif want[sym] == 0:
                sell(sym)
            else:
                h.peak = max(h.peak, close)

        self.blocked -= {s for s in self.blocked if want.get(s) == 0}

        # 2) 新規買い（1 銘柄あたり 総資産 / max_positions まで）
        equity = self.broker.cash() + sum(
            self.broker.position(s) * float(last[s]["close"]) for s in data
        )
        held = sum(1 for s in data if self.broker.position(s) > 0)
        for sym in data:
            if held >= max_positions:
                break
            if want[sym] != 1 or self.broker.position(sym) > 0 or sym in self.blocked:
                continue
            price = float(last[sym]["close"])
            budget = min(self.broker.cash(), equity / max_positions)
            lots = int(budget // (price * self.lot_size))
            if lots > 0:
                order = Order(sym, "buy", lots * self.lot_size, price)
                self.broker.submit(order)
                orders.append(order)
                self.holdings[sym] = Holding(price, price)
                held += 1
        return orders

    # 状態の保存（紙上取引用）
    def save(self, path: str | Path) -> None:
        if not isinstance(self.broker, PaperBroker):
            raise TypeError("保存できるのは PaperBroker の状態のみです")
        state = {
            "broker": json.loads(self.broker.to_json()),
            "holdings": {s: vars(h) for s, h in self.holdings.items()},
            "blocked": sorted(self.blocked),
        }
        Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2))

    def load_state(self, path: str | Path) -> None:
        state = json.loads(Path(path).read_text())
        self.broker = PaperBroker(**state["broker"])
        self.holdings = {s: Holding(**h) for s, h in state["holdings"].items()}
        self.blocked = set(state["blocked"])
