"""損切り・利確ルール."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskRules:
    """比率で指定する（0.05 = 5%）. None なら無効.

    stop_loss:     取得価格から何 % 下がったら損切りするか
    take_profit:   取得価格から何 % 上がったら利確するか
    trailing_stop: 保有中の最高値から何 % 下がったら手仕舞うか
    """

    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop: float | None = None

    def __post_init__(self):
        for name in ("stop_loss", "take_profit", "trailing_stop"):
            v = getattr(self, name)
            if v is not None and not 0 < v < 1:
                raise ValueError(f"{name} は 0〜1 の比率で指定してください: {v}")

    @property
    def enabled(self) -> bool:
        return any(v is not None for v in (self.stop_loss, self.take_profit, self.trailing_stop))

    def stop_price(self, entry: float, peak: float) -> tuple[float, str] | None:
        """有効な逆指値のうち高い方を (価格, 理由) で返す."""
        levels = []
        if self.stop_loss is not None:
            levels.append((entry * (1 - self.stop_loss), "stop_loss"))
        if self.trailing_stop is not None:
            levels.append((peak * (1 - self.trailing_stop), "trailing_stop"))
        return max(levels) if levels else None

    def target_price(self, entry: float) -> float | None:
        return entry * (1 + self.take_profit) if self.take_profit is not None else None

    def check(
        self, entry: float, peak: float, open_: float, high: float, low: float
    ) -> tuple[float, str] | None:
        """1 本の足の中で損切り・利確に引っかかるか判定し (約定価格, 理由) を返す.

        peak はこの足より前までの最高値。窓を開けて逆指値を飛び越えた場合は始値で約定。
        同じ足で両方に届いた場合は、足の中の順序が分からないので損切りを優先する（保守的）。
        """
        stop = self.stop_price(entry, peak)
        target = self.target_price(entry)
        if stop is not None and low <= stop[0]:
            return min(open_, stop[0]), stop[1]
        if target is not None and high >= target:
            return max(open_, target), "take_profit"
        return None
