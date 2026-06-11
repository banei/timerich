"""成长档（纳指联接）日限购：阶梯、候选名单、默认值与暂停判定。

候选名单来源：东方财富 fund_purchase_em（2026-06 复核）。
场外人民币 A 类为主；暂停基金仍保留在阶梯中，恢复后可继续轮询。
"""

from __future__ import annotations

from typing import Any

# 纳指100 场外候选（code → 元数据）
NASDAQ100_FUND_META: dict[str, dict[str, Any]] = {
    # —— 当前常见可买（日限约 ¥10）——
    "270042": {"name": "广发纳斯达克100ETF联接(QDII)A", "default_limit": 10.0, "note": "限大额 ¥10"},
    "000834": {"name": "大成纳斯达克100ETF联接(QDII)A", "default_limit": 10.0, "note": "限大额 ¥10"},
    "040046": {"name": "华安纳斯达克100ETF联接(QDII)A", "default_limit": 10.0, "note": "限大额 ¥10"},
    "019547": {"name": "招商纳斯达克100ETF发起式联接(QDII)A", "default_limit": 10.0, "note": "限大额 ¥10"},
    "019524": {"name": "华泰柏瑞纳斯达克100ETF发起式联接(QDII)A", "default_limit": 10.0, "note": "限大额 ¥10"},
    # —— 日限 ¥50–200 ——
    "019441": {"name": "万家纳斯达克100指数发起式(QDII)A", "default_limit": 50.0, "note": "限大额 ¥50"},
    "539001": {"name": "建信纳斯达克100指数(QDII)A", "default_limit": 100.0, "note": "限大额 ¥100"},
    "018966": {"name": "汇添富纳斯达克100ETF发起式联接(QDII)A", "default_limit": 100.0, "note": "限大额 ¥100"},
    "019172": {"name": "摩根纳斯达克100指数(QDII)A", "default_limit": 100.0, "note": "限大额 ¥100"},
    "019736": {"name": "宝盈纳斯达克100指数发起(QDII)A", "default_limit": 100.0, "note": "限大额 ¥100"},
    "016452": {"name": "南方纳斯达克100指数发起(QDII)A", "default_limit": 200.0, "note": "限大额 ¥200"},
    # —— 精选/高限额（非纯指数，作补充）——
    "017436": {"name": "华宝纳斯达克精选股票发起(QDII)A", "default_limit": 1000.0, "note": "精选股票型"},
    # —— 常态暂停或限额极紧，保留备选 ——
    "161130": {"name": "易方达纳斯达克100ETF联接(QDII-LOF)A", "default_limit": 0.0, "note": "常暂停/限 ¥10"},
    "018043": {"name": "天弘纳斯达克100指数发起(QDII)A", "default_limit": 0.0, "note": "暂停"},
    "160213": {"name": "国泰纳斯达克100指数", "default_limit": 0.0, "note": "暂停"},
    "015299": {"name": "华夏纳斯达克100ETF发起式联接(QDII)A", "default_limit": 0.0, "note": "暂停"},
    "016532": {"name": "嘉实纳斯达克100ETF发起联接(QDII)A", "default_limit": 0.0, "note": "暂停"},
}

SP500_BACKUP_META: dict[str, dict[str, Any]] = {
    "050025": {"name": "博时标普500ETF联接A", "default_limit": 1000.0, "note": "标普备胎"},
    "118002": {"name": "易方达标普500人民币A", "default_limit": 1000.0, "note": "标普备胎"},
    "096001": {"name": "大成标普500等权重A", "default_limit": 500.0, "note": "标普备胎"},
}

# 成长桶溢出阶梯（按优先级；含标普500备胎）
GROWTH_FUND_LADDER: list[list[str]] = [
    ["270042", "000834", "040046", "019547", "019524"],
    ["016452", "019441", "539001", "018966", "019172", "019736"],
    ["017436", "161130", "018043", "160213", "015299", "016532"],
    ["050025", "118002", "096001"],
]

# 已从阶梯移除的错误/更名代码（种子库中标记 inactive）
RETIRED_NDX_CODES = ("018959", "019870")

DEFAULT_DAILY_PURCHASE_LIMITS: dict[str, float] = {
    **{code: float(meta["default_limit"]) for code, meta in NASDAQ100_FUND_META.items()},
    **{code: float(meta["default_limit"]) for code, meta in SP500_BACKUP_META.items()},
}

DEFAULT_UNKNOWN_LIMIT = 300.0

CUSTOM_GROWTH_FUNDS_KEY = "custom_growth_funds"


def normalize_fund_code(raw: str) -> str:
    code = str(raw or "").strip()
    if len(code) != 6 or not code.isdigit():
        raise ValueError("基金代码须为 6 位数字")
    return code


def parse_custom_growth_funds(detail: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not detail or not isinstance(detail, dict):
        return []
    raw = detail.get(CUSTOM_GROWTH_FUNDS_KEY)
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            code = normalize_fund_code(str(entry.get("fund_code", "")))
        except ValueError:
            continue
        name = str(entry.get("fund_name") or "").strip() or code
        tier = int(entry.get("tier", 2))
        tier = max(1, min(tier, len(GROWTH_FUND_LADDER)))
        limit_raw = entry.get("daily_limit")
        daily_limit = float(limit_raw) if limit_raw is not None else DEFAULT_UNKNOWN_LIMIT
        items.append(
            {
                "fund_code": code,
                "fund_name": name,
                "daily_limit": daily_limit,
                "tier": tier,
            }
        )
    return items


def custom_fund_codes(custom_funds: list[dict[str, Any]] | None) -> list[str]:
    return [item["fund_code"] for item in (custom_funds or [])]


def effective_growth_ladder(custom_funds: list[dict[str, Any]] | None = None) -> list[list[str]]:
    """在内置阶梯上注入用户自定义基金（按 tier 插入，默认第 2 阶梯）。"""
    ladder = [list(tier) for tier in GROWTH_FUND_LADDER]
    for item in custom_funds or []:
        code = item["fund_code"]
        tier_idx = max(1, min(int(item.get("tier", 2)), len(ladder))) - 1
        for tier in ladder:
            if code in tier:
                tier.remove(code)
        ladder[tier_idx].append(code)
    return ladder


def merge_custom_limits(
    limits: dict[str, float],
    custom_funds: list[dict[str, Any]] | None,
) -> dict[str, float]:
    merged = dict(limits)
    for item in custom_funds or []:
        merged[item["fund_code"]] = float(item.get("daily_limit", DEFAULT_UNKNOWN_LIMIT))
    return merged


def all_growth_fund_codes() -> list[str]:
    codes: list[str] = []
    for tier in GROWTH_FUND_LADDER:
        for code in tier:
            if code not in codes:
                codes.append(code)
    return codes


def all_growth_fund_codes_with_custom(custom_funds: list[dict[str, Any]] | None = None) -> list[str]:
    codes = all_growth_fund_codes()
    for code in custom_fund_codes(custom_funds):
        if code not in codes:
            codes.append(code)
    return codes


def nasdaq_fund_catalog() -> dict[str, str]:
    return {code: meta["name"] for code, meta in NASDAQ100_FUND_META.items()}


def growth_fund_roster(
    limits: dict[str, float],
    fund_catalog: dict[str, str] | None = None,
    *,
    custom_funds: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """完整纳指候选名单（含暂停与用户自定义），供前端展示。"""
    catalog = fund_catalog or {}
    custom_by_code = {item["fund_code"]: item for item in (custom_funds or [])}
    ladder = effective_growth_ladder(custom_funds)
    rows: list[dict[str, Any]] = []
    for tier_idx, tier in enumerate(ladder, start=1):
        for order, code in enumerate(tier, start=1):
            if code in SP500_BACKUP_META:
                continue
            meta = NASDAQ100_FUND_META.get(code, {})
            custom = custom_by_code.get(code)
            daily_limit, status = resolve_daily_limit(code, limits)
            note = meta.get("note", "")
            is_custom = custom is not None
            if is_custom:
                note = "自定义"
            rows.append(
                {
                    "fund_code": code,
                    "fund_name": catalog.get(code)
                    or (custom or {}).get("fund_name")
                    or meta.get("name")
                    or code,
                    "tier": tier_idx,
                    "ladder_order": order,
                    "daily_limit": daily_limit,
                    "status": status,
                    "note": note,
                    "buyable": status != "paused",
                    "is_custom": is_custom,
                }
            )
    return rows


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
        val = DEFAULT_DAILY_PURCHASE_LIMITS[code]
        if val <= 0:
            return 0.0, "paused"
        return val, "limited"
    return DEFAULT_UNKNOWN_LIMIT, "limited"


def growth_limit_snapshot(
    limits: dict[str, float],
    fund_catalog: dict[str, str] | None = None,
    *,
    custom_funds: list[dict[str, Any]] | None = None,
) -> list[dict[str, object]]:
    catalog = fund_catalog or {}
    custom_by_code = {item["fund_code"]: item for item in (custom_funds or [])}
    rows: list[dict[str, object]] = []
    for code in all_growth_fund_codes_with_custom(custom_funds):
        daily_limit, status = resolve_daily_limit(code, limits)
        meta = NASDAQ100_FUND_META.get(code) or SP500_BACKUP_META.get(code, {})
        custom = custom_by_code.get(code)
        note = meta.get("note", "")
        if custom:
            note = "自定义"
        rows.append(
            {
                "fund_code": code,
                "fund_name": catalog.get(code)
                or (custom or {}).get("fund_name")
                or meta.get("name", code),
                "daily_limit": daily_limit,
                "status": status,
                "note": note,
                "is_custom": custom is not None,
            }
        )
    return rows
