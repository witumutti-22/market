"""コマンドライン.

  python -m kaburobo backtest --symbol 7203.T --strategy sma
  python -m kaburobo backtest --sample --strategy rsi
  python -m kaburobo run --symbol 7203.T --state paper.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import run_backtest
from .bot import step
from .broker import PaperBroker
from .data import generate_sample, load_csv, load_yahoo
from .strategies import STRATEGIES


def _load_data(args):
    if args.sample:
        return generate_sample(), "SAMPLE"
    if args.csv:
        return load_csv(args.csv), Path(args.csv).stem
    if args.symbol:
        return load_yahoo(args.symbol, start=args.start), args.symbol
    raise SystemExit("--symbol / --csv / --sample のいずれかを指定してください")


def cmd_backtest(args) -> None:
    data, name = _load_data(args)
    strategy = STRATEGIES[args.strategy]()
    result = run_backtest(
        data, strategy, initial_cash=args.cash, commission_rate=args.commission
    )
    m = result.metrics()
    print(f"銘柄: {name}  戦略: {strategy.name}  期間: {data.index[0]:%Y-%m-%d} 〜 {data.index[-1]:%Y-%m-%d}")
    print(f"  最終資産     {m['final_equity']:>14,.0f} 円")
    print(f"  トータル     {m['total_return']:>14.2%}")
    print(f"  年率 (CAGR)  {m['cagr']:>14.2%}")
    print(f"  シャープ     {m['sharpe']:>14.2f}")
    print(f"  最大DD       {m['max_drawdown']:>14.2%}")
    print(f"  取引回数     {m['trades']:>14d}")
    print(f"  勝率         {m['win_rate']:>14.2%}")
    bh = data["close"].iloc[-1] / data["close"].iloc[0] - 1
    print(f"  (参考) 買い持ち {bh:.2%}")


def cmd_run(args) -> None:
    data, name = _load_data(args)
    state = Path(args.state)
    broker = PaperBroker.load(state) if state.exists() else PaperBroker(initial_cash=args.cash)
    order = step(name, data, STRATEGIES[args.strategy](), broker)
    broker.save(state)
    print(f"注文: {order}" if order else "注文なし")
    print(f"現金 {broker.cash():,.0f} 円 / 保有 {broker.positions}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="kaburobo", description="カブロボ")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd, fn in (("backtest", cmd_backtest), ("run", cmd_run)):
        sp = sub.add_parser(cmd)
        sp.set_defaults(func=fn)
        src = sp.add_mutually_exclusive_group()
        src.add_argument("--symbol", help="例: 7203.T (トヨタ)")
        src.add_argument("--csv", help="date,open,high,low,close,volume の CSV")
        src.add_argument("--sample", action="store_true", help="ランダム生成データで試す")
        sp.add_argument("--start", default="2020-01-01")
        sp.add_argument("--strategy", choices=STRATEGIES, default="sma")
        sp.add_argument("--cash", type=float, default=1_000_000)
        if cmd == "backtest":
            sp.add_argument("--commission", type=float, default=0.0)
        else:
            sp.add_argument("--state", default="paper_state.json", help="紙上取引の状態ファイル")
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
