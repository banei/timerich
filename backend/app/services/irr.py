"""组合 IRR（内部收益率）计算，依赖 scipy。"""

from __future__ import annotations

from datetime import date

from scipy.optimize import brentq


def calculate_irr(cashflows: list[tuple[date, float]]) -> float:
    """
    计算不规则现金流的年化 IRR。

    现金流约定：投入为负，赎回/期末市值为正。
  """
    if len(cashflows) < 2:
        return 0.0

    ordered = sorted(cashflows, key=lambda x: x[0])
    t0 = ordered[0][0]
    years = [(cf[0] - t0).days / 365.25 for cf in ordered]
    amounts = [cf[1] for cf in ordered]

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** y for a, y in zip(amounts, years))

    try:
        if npv(-0.999) * npv(10.0) > 0:
            return 0.0
        return float(brentq(npv, -0.999, 10.0))
    except (ValueError, RuntimeError):
        return 0.0
