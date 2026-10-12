"""ブローカー（発注先）の抽象化.

今は紙上取引 (PaperBroker) のみ。実ブローカーは Broker を継承して実装する。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Order:
    symbol: str
    side: str  # "buy" | "sell"
    shares: int
    price: float


class Broker(ABC):
    @abstractmethod
    def cash(self) -> float: ...

    @abstractmethod
    def position(self, symbol: str) -> int: ...

    @abstractmethod
    def submit(self, order: Order) -> None: ...


@dataclass
class PaperBroker(Broker):
    """指定価格で即時約定する紙上取引ブローカー. 状態は JSON に保存できる."""

    initial_cash: float = 1_000_000
    commission_rate: float = 0.0
    _cash: float = field(default=-1.0)
    positions: dict[str, int] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self._cash < 0:
            self._cash = float(self.initial_cash)

    def cash(self) -> float:
        return self._cash

    def position(self, symbol: str) -> int:
        return self.positions.get(symbol, 0)

    def submit(self, order: Order) -> None:
        if order.shares <= 0:
            raise ValueError("株数は正の数にしてください")
        amount = order.price * order.shares
        if order.side == "buy":
            cost = amount * (1 + self.commission_rate)
            if cost > self._cash:
                raise ValueError(f"資金不足: 必要 {cost:,.0f} / 残高 {self._cash:,.0f}")
            self._cash -= cost
            self.positions[order.symbol] = self.position(order.symbol) + order.shares
        elif order.side == "sell":
            if order.shares > self.position(order.symbol):
                raise ValueError("保有株数を超える売りはできません（空売り非対応）")
            self._cash += amount * (1 - self.commission_rate)
            self.positions[order.symbol] -= order.shares
            if self.positions[order.symbol] == 0:
                del self.positions[order.symbol]
        else:
            raise ValueError(f"不明な売買区分: {order.side}")
        self.history.append(asdict(order))

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> PaperBroker:
        return cls(**json.loads(Path(path).read_text()))
