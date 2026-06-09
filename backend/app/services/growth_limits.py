"""成长档（纳指联接）日限购：阶梯、默认值、合并规则与暂停判定。"""

from __future__ import annotations

# 成长桶溢出阶梯（基金代码，按优先级；含标普500备胎）
GROWTH_FUND_LADDER: list[list[str]] = [
    ["161130", "018043", "270042"],
    ["000834", "160213", "018959", "040046", "019547"],
    ["017437", "019870"],
    ["050025", "118002", "096001"],
]

# 无行情/未配置时的场外日限购兜底（2026 初易方达纳指常态极低）
DEFAULT_DAILY_PURCHASE_LIMITS: dict[str, float] = {
    "161130": 10.0,
    "018043": 300.0,
    "270042": 300.0,
    "000834": 300.0,
    "160213": 300.0,
    "018959": 300.0,
    "040046": 300.0,
    "019547": 300.0,
    "017437": 500.0,
    "019870": 300.0,
    "050025": 1000.0,
    "118002": 1000.0,
    "096001": 500.0,
}

DEFAULT_UNKNOWN_LIMIT = 300.0


def all_growth_fund_codes() -> list[str]:
    codes: list[str] = []
    for tier in GROWTH_FUND_LADDER:
        for code in tier:
            if code not in codes:
                codes.append(code)
    return codes


def merge_purchase_limits(
    *,
    db_limits: dict[str, float] | None = None,
    user_overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    """优先级：用户覆盖 > 行情库 > 内置默认。"""
    merged = dict(DEFAULT_DAILY_PURCHASE_LIMITS)
    if db_limits:
        for code, value in db_limits.items():
            if value is not None:
                merged[code] = float(value)
    if user_overrides:
        for code, value in user_overrides.items():
            merged[code] = float(value)
    return merged


def resolve_daily_limit(code: str, limits: dict[str, float]) -> tuple[float | None, str]:
    """
    返回 (日限购, 状态)。
    limit 为 None 表示不限购（极少见）；0 表示暂停申购。
    """
    if code in limits:
        val = limits[code]
        if val <= 0:
            return 0.0, "paused"
        return val, "limited"
    if code in DEFAULT_DAILY_PURCHASE_LIMITS:
        return DEFAULT_DAILY_PURCHASE_LIMITS[code], "limited"
    return DEFAULT_UNKNOWN_LIMIT, "limited"


def growth_limit_snapshot(
    limits: dict[str, float],
    fund_catalog: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    catalog = fund_catalog or {}
    rows: list[dict[str, object]] = []
    for code in all_growth_fund_codes():
        daily_limit, status = resolve_daily_limit(code, limits)
        rows.append(
            {
                "fund_code": code,
                "fund_name": catalog.get(code, code),
                "daily_limit": daily_limit,
                "status": status,
            }
        )
    return rows
