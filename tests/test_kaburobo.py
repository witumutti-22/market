import pandas as pd
import pytest

from kaburobo.backtest import run_backtest
from kaburobo.bot import step
from kaburobo.broker import Order, PaperBroker
from kaburobo.data import generate_sample
from kaburobo.indicators import rsi, sma
from kaburobo.strategies import RsiReversion, SmaCross, Strategy


class Fixed(Strategy):
    def __init__(self, positions):
        self.positions = positions

    def target_position(self, data):
        return pd.Series(self.positions, index=data.index)


def _frame(opens, closes):
    idx = pd.bdate_range("2024-01-01", periods=len(opens))
    return pd.DataFrame(
        {"open": opens, "high": closes, "low": opens, "close": closes, "volume": 1000.0},
        index=idx,
    )


def test_sma_and_rsi():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert sma(s, 2).iloc[-1] == 4.5
    assert rsi(pd.Series(range(30), dtype=float)).iloc[-1] == 100


def test_backtest_executes_next_open_in_lots():
    data = _frame([100, 100, 110, 120, 130], [100, 105, 115, 125, 135])
    result = run_backtest(data, Fixed([1, 1, 1, 0, 0]), initial_cash=25_000)
    t = result.trades[0]
    # 1 日目の終値シグナル -> 2 日目始値で 200 株 (100 株単位) 買い
    assert (t.entry_date, t.entry_price, t.shares) == (data.index[1], 100, 200)
    # 4 日目の終値シグナル -> 5 日目始値で売り
    assert (t.exit_date, t.exit_price) == (data.index[4], 130)
    assert result.equity.iloc[-1] == 25_000 + 30 * 200


def test_no_lookahead():
    data = generate_sample(300)
    full = SmaCross().target_position(data)
    partial = SmaCross().target_position(data.iloc[:200])
    pd.testing.assert_series_equal(full.iloc[:200], partial)


@pytest.mark.parametrize("strategy", [SmaCross(), RsiReversion()])
def test_strategies_run(strategy):
    m = run_backtest(generate_sample(), strategy, commission_rate=0.001).metrics()
    assert m["final_equity"] > 0
    assert -1 <= m["max_drawdown"] <= 0


def test_paper_broker(tmp_path):
    b = PaperBroker(initial_cash=100_000)
    b.submit(Order("7203.T", "buy", 100, 900))
    assert b.cash() == 10_000 and b.position("7203.T") == 100
    with pytest.raises(ValueError):
        b.submit(Order("7203.T", "buy", 100, 900))
    with pytest.raises(ValueError):
        b.submit(Order("7203.T", "sell", 200, 900))
    b.save(tmp_path / "s.json")
    b2 = PaperBroker.load(tmp_path / "s.json")
    assert b2.cash() == 10_000 and b2.position("7203.T") == 100


def test_bot_step():
    data = _frame([100] * 3, [100] * 3)
    b = PaperBroker(initial_cash=35_000)
    assert step("X", data, Fixed([0, 0, 1]), b).shares == 300
    assert step("X", data, Fixed([0, 0, 1]), b) is None
    assert step("X", data, Fixed([0, 0, 0]), b).side == "sell"
    assert b.position("X") == 0
