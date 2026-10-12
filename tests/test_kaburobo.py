import pandas as pd
import pytest

from kaburobo.backtest import run_backtest
from kaburobo.bot import Robot
from kaburobo.broker import Order, PaperBroker
from kaburobo.data import generate_sample
from kaburobo.indicators import rsi, sma
from kaburobo.risk import RiskRules
from kaburobo.strategies import RsiReversion, SmaCross, Strategy


class Fixed(Strategy):
    def __init__(self, positions):
        self.positions = positions

    def target_position(self, data):
        return pd.Series(self.positions, index=data.index)


def _frame(opens, closes, highs=None, lows=None):
    idx = pd.bdate_range("2024-01-01", periods=len(opens))
    highs = highs or [max(o, c) for o, c in zip(opens, closes)]
    lows = lows or [min(o, c) for o, c in zip(opens, closes)]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1000.0},
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


def test_risk_check():
    r = RiskRules(stop_loss=0.05, take_profit=0.10)
    assert r.check(100, 100, 99, 101, 94) == (95, "stop_loss")
    assert r.check(100, 100, 90, 91, 89) == (90, "stop_loss")  # 窓下げは始値で約定
    assert r.check(100, 100, 101, 111, 99) == (pytest.approx(110), "take_profit")
    assert r.check(100, 100, 100, 111, 94) == (95, "stop_loss")  # 両方届いたら損切り優先
    assert r.check(100, 100, 100, 105, 96) is None
    t = RiskRules(trailing_stop=0.10)
    assert t.check(100, 150, 140, 141, 134) == (135, "trailing_stop")
    with pytest.raises(ValueError):
        RiskRules(stop_loss=5)


def test_backtest_stop_loss_blocks_reentry_until_signal_resets():
    data = _frame(
        opens=[100, 100, 96, 97, 98, 99, 100],
        closes=[100, 97, 96, 97, 98, 99, 100],
        lows=[100, 94, 95, 96, 97, 98, 99],
    )
    result = run_backtest(
        data, Fixed([1, 1, 1, 0, 1, 1, 1]), initial_cash=20_000, risk=RiskRules(stop_loss=0.05)
    )
    first, second = result.trades
    assert (first.exit_date, first.exit_price, first.exit_reason) == (data.index[1], 95, "stop_loss")
    # シグナルが 0 に戻った (3 日目終値) 後の 1 で再エントリー -> 5 日目始値
    assert (second.entry_date, second.entry_price) == (data.index[5], 99)


def test_multi_symbol_allocation():
    a = _frame([100] * 4, [100] * 4)
    b = _frame([200] * 4, [200] * 4)
    both = run_backtest({"A": a, "B": b}, Fixed([1, 1, 1, 1]), initial_cash=100_000)
    shares = {t.symbol: t.shares for t in both.trades}
    assert shares == {"A": 500, "B": 200}  # 1 銘柄 50,000 円まで

    one = run_backtest({"A": a, "B": b}, Fixed([1, 1, 1, 1]), initial_cash=100_000, max_positions=1)
    assert [(t.symbol, t.shares) for t in one.trades] == [("A", 1000)]
    assert set(both.by_symbol().index) == set()  # 未決済の取引は集計しない


def test_multi_symbol_misaligned_dates():
    a = generate_sample(300, seed=1)
    b = generate_sample(300, seed=2).iloc[50:]
    result = run_backtest({"A": a, "B": b}, SmaCross(), risk=RiskRules(stop_loss=0.05))
    assert len(result.equity) == 300 and result.equity.notna().all()
    assert {t.symbol for t in result.trades} == {"A", "B"}
    assert all(t.entry_date >= b.index[0] for t in result.trades if t.symbol == "B")


def test_robot_multi_symbol_and_stop(tmp_path):
    a = _frame([100] * 3, [100] * 3)
    b = _frame([200] * 3, [200] * 3)
    robot = Robot(Fixed([0, 0, 1]), PaperBroker(initial_cash=100_000), risk=RiskRules(stop_loss=0.05))
    orders = robot.step({"A": a, "B": b})
    assert [(o.symbol, o.shares) for o in orders] == [("A", 500), ("B", 200)]
    assert robot.step({"A": a, "B": b}) == []

    robot.save(tmp_path / "s.json")
    robot2 = Robot(Fixed([0, 0, 1]), PaperBroker(), risk=RiskRules(stop_loss=0.05))
    robot2.load_state(tmp_path / "s.json")

    a_down = _frame([100, 100, 94], [100, 100, 94])
    orders = robot2.step({"A": a_down, "B": b})
    assert [(o.symbol, o.side) for o in orders] == [("A", "sell")]
    assert "A" in robot2.blocked
    # シグナルが残っていても再購入しない
    assert robot2.step({"A": a_down, "B": b}) == []
    # シグナルが 0 になれば解除、売りは B
    robot2.strategy = Fixed([0, 0, 0])
    assert [o.symbol for o in robot2.step({"A": a_down, "B": b})] == ["B"]
    assert robot2.blocked == set()
