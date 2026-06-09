"""五桶配置：默认结构、解析与用户自定义名称。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

BUCKET_CODES = ("growth", "dividend", "gold", "bond_long", "bond_short")

DEFAULT_BUCKET_META: dict[str, dict[str, Any]] = {
    "growth": {"name": "成长", "color": "#3ABFF8", "signal_bucket": "growth"},
    "dividend": {"name": "红利", "color": "#F87272", "signal_bucket": "dividend"},
    "gold": {"name": "黄金", "color": "#FBBD23", "signal_bucket": "gold"},
    "bond_long": {"name": "长债", "color": "#B083F0", "signal_bucket": None},
    "bond_short": {"name": "短债", "color": "#67E8F9", "signal_bucket": None},
}

BOND_LONG_RATIO = Decimal("0.70")
BOND_SHORT_RATIO = Decimal("0.30")


@dataclass(frozen=True)
class BucketDef:
    code: str
    name: str
    target_pct: float
    color: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "target_pct": self.target_pct,
            "color": self.color,
        }


def default_buckets() -> list[BucketDef]:
    """平衡型默认五桶（与执行页一致）。"""
    return buckets_from_legacy(0.35, 0.40, 0.25)


def buckets_from_legacy(
    target_nasdaq: float,
    target_dividend: float,
    target_bond: float,
) -> list[BucketDef]:
    bond_long = target_bond * float(BOND_LONG_RATIO)
    bond_short = target_bond * float(BOND_SHORT_RATIO)
    targets = {
        "growth": target_nasdaq,
        "dividend": target_dividend,
        "gold": 0.0,
        "bond_long": bond_long,
        "bond_short": bond_short,
    }
    return [
        BucketDef(
            code=code,
            name=DEFAULT_BUCKET_META[code]["name"],
            target_pct=targets[code],
            color=DEFAULT_BUCKET_META[code]["color"],
        )
        for code in BUCKET_CODES
    ]


def parse_bucket_config(
    raw: dict | list | None,
    *,
    target_nasdaq: float = 0.35,
    target_dividend: float = 0.40,
    target_bond: float = 0.25,
) -> list[BucketDef]:
    """解析用户 bucket_config；缺失或无效时回退三档展开。"""
    fallback = buckets_from_legacy(target_nasdaq, target_dividend, target_bond)
    if not raw:
        return fallback

    items: list[dict] = []
    if isinstance(raw, dict) and "buckets" in raw:
        items = raw["buckets"]
    elif isinstance(raw, list):
        items = raw
    if not items:
        return fallback

    by_code: dict[str, BucketDef] = {b.code: b for b in fallback}
    for item in items:
        code = str(item.get("code", ""))
        if code not in DEFAULT_BUCKET_META:
            continue
        meta = DEFAULT_BUCKET_META[code]
        name = str(item.get("name") or meta["name"]).strip() or meta["name"]
        try:
            pct = float(item.get("target_pct", by_code[code].target_pct))
        except (TypeError, ValueError):
            pct = by_code[code].target_pct
        color = str(item.get("color") or meta["color"])
        by_code[code] = BucketDef(code=code, name=name, target_pct=pct, color=color)

    return [by_code[c] for c in BUCKET_CODES]


def bucket_config_to_json(buckets: list[BucketDef]) -> dict:
    return {"buckets": [b.to_dict() for b in buckets]}


def targets_map(buckets: list[BucketDef]) -> dict[str, float]:
    return {b.code: b.target_pct for b in buckets}


def labels_map(buckets: list[BucketDef]) -> dict[str, str]:
    return {b.code: b.name for b in buckets}


def colors_map(buckets: list[BucketDef]) -> dict[str, str]:
    return {b.code: b.color for b in buckets}


def sync_legacy_targets(buckets: list[BucketDef]) -> dict[str, Decimal]:
    """同步旧三档字段，供仪表盘/再平衡继续工作。"""
    t = targets_map(buckets)
    nasdaq = Decimal(str(t.get("growth", 0) + t.get("gold", 0)))
    dividend = Decimal(str(t.get("dividend", 0)))
    bond = Decimal(str(t.get("bond_long", 0) + t.get("bond_short", 0)))
    return {
        "target_nasdaq_pct": nasdaq,
        "target_dividend_pct": dividend,
        "target_bond_pct": bond,
    }


def validate_bucket_targets(buckets: list[BucketDef], tolerance: float = 0.02) -> bool:
    total = sum(b.target_pct for b in buckets)
    return abs(total - 1.0) <= tolerance


def buckets_from_update_items(items: list[Any]) -> list[BucketDef]:
    """从 API 提交的 bucket 列表构建 BucketDef。"""
    raw = {"buckets": [item if isinstance(item, dict) else item.model_dump() for item in items]}
    return parse_bucket_config(raw)
