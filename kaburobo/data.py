"""株価データの取得.

すべてのローダーは index が日付、列が open/high/low/close/volume の DataFrame を返す。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"必要な列がありません: {missing}")
    df = df[COLUMNS].astype(float).dropna()
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df.sort_index()


def load_csv(path: str | Path) -> pd.DataFrame:
    """date,open,high,low,close,volume 形式の CSV を読み込む."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return _normalize(df)


def load_yahoo(symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Yahoo Finance から日足を取得する（東証銘柄は "7203.T" のように指定）."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("pip install 'kaburobo[yahoo]' で yfinance を入れてください") from e

    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"{symbol} のデータが取得できませんでした")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _normalize(df)


def generate_sample(days: int = 750, start_price: float = 2000.0, seed: int = 0) -> pd.DataFrame:
    """動作確認用のランダムウォーク株価を生成する."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=days)
    returns = rng.normal(0.0003, 0.015, days)
    close = start_price * np.exp(np.cumsum(returns))
    open_ = close * np.exp(rng.normal(0, 0.005, days))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, days)))
    volume = rng.integers(100_000, 1_000_000, days)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    return _normalize(df)
