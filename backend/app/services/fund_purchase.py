"""从东方财富/天天基金解析场外基金日限购与申购状态。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# 东方财富「日累计限定金额」极大值表示实质不限购
UNLIMITED_CAP_THRESHOLD = 1_000_000_000.0


@dataclass
class FundPurchaseInfo:
    fund_code: str
    fund_name: str
    subscribe_status: str
    daily_limit: float | None
    status: str  # active | limited | paused
    min_purchase: float | None = None
    source: str = "akshare"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "subscribe_status": self.subscribe_status,
            "daily_limit": self.daily_limit,
            "status": self.status,
            "min_purchase": self.min_purchase,
            "source": self.source,
        }


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


def parse_em_purchase_row(
    fund_code: str,
    fund_name: str,
    subscribe_status: str,
    daily_cap: Any,
    min_purchase: Any = None,
) -> FundPurchaseInfo:
    """
    解析 fund_purchase_em 单行。
    - 暂停申购 → daily_limit=0, paused
    - 限大额 → 取「日累计限定金额」
    - 开放申购且金额极大 → 视为不限购（daily_limit=None, active）
    """
    status_text = (subscribe_status or "").strip()
    cap = _safe_float(daily_cap)
    min_buy = _safe_float(min_purchase)

    if status_text == "暂停申购":
        return FundPurchaseInfo(
            fund_code=fund_code,
            fund_name=fund_name,
            subscribe_status=status_text,
            daily_limit=0.0,
            status="paused",
            min_purchase=min_buy,
        )

    if status_text in {"限大额", "开放申购", "认购期"}:
        if cap is None:
            return FundPurchaseInfo(
                fund_code=fund_code,
                fund_name=fund_name,
                subscribe_status=status_text,
                daily_limit=None,
                status="active",
                min_purchase=min_buy,
            )
        if cap <= 0:
            return FundPurchaseInfo(
                fund_code=fund_code,
                fund_name=fund_name,
                subscribe_status=status_text,
                daily_limit=0.0,
                status="paused",
                min_purchase=min_buy,
            )
        if cap >= UNLIMITED_CAP_THRESHOLD:
            return FundPurchaseInfo(
                fund_code=fund_code,
                fund_name=fund_name,
                subscribe_status=status_text,
                daily_limit=None,
                status="active",
                min_purchase=min_buy,
            )
        return FundPurchaseInfo(
            fund_code=fund_code,
            fund_name=fund_name,
            subscribe_status=status_text,
            daily_limit=cap,
            status="limited",
            min_purchase=min_buy,
        )

    return FundPurchaseInfo(
        fund_code=fund_code,
        fund_name=fund_name,
        subscribe_status=status_text or "未知",
        daily_limit=0.0,
        status="paused",
        min_purchase=min_buy,
    )


def fetch_em_purchase_table() -> Any:
    import akshare as ak

    return ak.fund_purchase_em()


def fetch_em_purchase_for_codes(codes: list[str]) -> list[FundPurchaseInfo]:
    """拉取全表并筛选指定基金代码。"""
    if not codes:
        return []
    df = fetch_em_purchase_table()
    code_set = {str(c) for c in codes}
    mask = df["基金代码"].astype(str).isin(code_set)
    rows = df.loc[mask]
    results: list[FundPurchaseInfo] = []
    for _, row in rows.iterrows():
        results.append(
            parse_em_purchase_row(
                fund_code=str(row["基金代码"]),
                fund_name=str(row.get("基金简称", "")),
                subscribe_status=str(row.get("申购状态", "")),
                daily_cap=row.get("日累计限定金额"),
                min_purchase=row.get("购买起点"),
            )
        )
    found = {r.fund_code for r in results}
    for code in codes:
        if str(code) not in found:
            results.append(
                FundPurchaseInfo(
                    fund_code=str(code),
                    fund_name=str(code),
                    subscribe_status="未找到",
                    daily_limit=None,
                    status="paused",
                )
            )
    return results
