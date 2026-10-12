"""ロボット本体: 最新データから戦略の目標ポジションを求め、ブローカーに発注する."""

from __future__ import annotations

import pandas as pd

from .broker import Broker, Order
from .strategies import Strategy


def step(
    symbol: str,
    data: pd.DataFrame,
    strategy: Strategy,
    broker: Broker,
    lot_size: int = 100,
) -> Order | None:
    """1 回分の売買判断を行う（日足なら 1 日 1 回、引け後に実行する想定）.

    約定価格は直近終値で近似する。発注した注文を返し、何もしなければ None。
    """
    want = int(strategy.target_position(data).iloc[-1])
    held = broker.position(symbol)
    price = float(data["close"].iloc[-1])

    order = None
    if want == 1 and held == 0:
        lots = int(broker.cash() // (price * lot_size))
        if lots > 0:
            order = Order(symbol, "buy", lots * lot_size, price)
    elif want == 0 and held > 0:
        order = Order(symbol, "sell", held, price)

    if order:
        broker.submit(order)
    return order
