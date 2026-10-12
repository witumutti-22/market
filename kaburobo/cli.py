"""コマンドライン.

  python -m kaburobo backtest --symbol 7203.T 6758.T 9984.T --strategy sma --stop-loss 0.05
  python -m kaburobo backtest --sample 5 --max-positions 3 --take-profit 0.15
  python -m kaburobo run --symbol 7203.T 6758.T --state paper.json --trailing-stop 0.08
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import run_backtest
from .bot import Robot
from .broker import PaperBroker
from .data import generate_sample, load_csv, load_yahoo
from .risk import RiskRules
from .strategies import STRATEGIES


def _load_data(args) -> dict:
    if args.sample:
        return {f"SAMPLE{i + 1}": generate_sample(seed=i) for i in range(args.sample)}
    if args.csv:
        return {Path(p).stem: load_csv(p) for p in args.csv}
    if args.symbol:
        return {s: load_yahoo(s, start=args.start) for s in args.symbol}
    raise SystemExit("--symbol / --csv / --sample のいずれかを指定してください")


def _risk(args) -> RiskRules:
    return RiskRules(args.stop_loss, args.take_profit, args.trailing_stop)


def cmd_backtest(args) -> None:
    data = _load_data(args)
    strategy = STRATEGIES[args.strategy]()
    result = run_backtest(
        data,
        strategy,
        initial_cash=args.cash,
        commission_rate=args.commission,
        risk=_risk(args),
        max_positions=args.max_positions,
    )
    m = result.metrics()
    start = min(d.index[0] for d in data.values())
    end = max(d.index[-1] for d in data.values())
    print(f"銘柄: {', '.join(data)}  戦略: {strategy.name}  期間: {start:%Y-%m-%d} 〜 {end:%Y-%m-%d}")
    print(f"  最終資産     {m['final_equity']:>14,.0f} 円")
    print(f"  トータル     {m['total_return']:>14.2%}")
    print(f"  年率 (CAGR)  {m['cagr']:>14.2%}")
    print(f"  シャープ     {m['sharpe']:>14.2f}")
    print(f"  最大DD       {m['max_drawdown']:>14.2%}")
    print(f"  取引回数     {m['trades']:>14d}")
    print(f"  勝率         {m['win_rate']:>14.2%}")
    bh = sum(d["close"].iloc[-1] / d["close"].iloc[0] - 1 for d in data.values()) / len(data)
    print(f"  (参考) 均等買い持ち {bh:.2%}")
    table = result.by_symbol()
    if not table.empty:
        print("\n銘柄別:")
        print(table.to_string(float_format=lambda v: f"{v:,.2f}"))


def cmd_run(args) -> None:
    data = _load_data(args)
    state = Path(args.state)
    robot = Robot(
        STRATEGIES[args.strategy](),
        PaperBroker(initial_cash=args.cash),
        risk=_risk(args),
        max_positions=args.max_positions,
    )
    if state.exists():
        robot.load_state(state)
    orders = robot.step(data)
    robot.save(state)
    for o in orders:
        print(f"注文: {o.side} {o.symbol} {o.shares} 株 @ {o.price:,.1f}")
    if not orders:
        print("注文なし")
    print(f"現金 {robot.broker.cash():,.0f} 円 / 保有 {robot.broker.positions}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="kaburobo", description="カブロボ")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd, fn in (("backtest", cmd_backtest), ("run", cmd_run)):
        sp = sub.add_parser(cmd)
        sp.set_defaults(func=fn)
        src = sp.add_mutually_exclusive_group()
        src.add_argument("--symbol", nargs="+", help="例: 7203.T 6758.T")
        src.add_argument("--csv", nargs="+", help="date,open,high,low,close,volume の CSV（ファイル名が銘柄名）")
        src.add_argument("--sample", type=int, metavar="N", help="ランダム生成データ N 銘柄で試す")
        sp.add_argument("--start", default="2020-01-01")
        sp.add_argument("--strategy", choices=STRATEGIES, default="sma")
        sp.add_argument("--cash", type=float, default=1_000_000)
        sp.add_argument("--max-positions", type=int, help="同時保有の最大銘柄数（既定: 銘柄数）")
        sp.add_argument("--stop-loss", type=float, help="損切り率 例: 0.05 = -5%%")
        sp.add_argument("--take-profit", type=float, help="利確率 例: 0.10 = +10%%")
        sp.add_argument("--trailing-stop", type=float, help="最高値からの下落率 例: 0.08")
        if cmd == "backtest":
            sp.add_argument("--commission", type=float, default=0.0)
        else:
            sp.add_argument("--state", default="paper_state.json", help="紙上取引の状態ファイル")
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
