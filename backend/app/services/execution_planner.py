"""月度定投执行计划推导（信号 → 金额 → 桶内基金分配）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.services.bucket_config import (
    BUCKET_CODES,
    DEFAULT_BUCKET_META,
    BucketDef,
    buckets_from_legacy,
    colors_map,
    labels_map,
    targets_map,
)
from app.services.growth_limits import GROWTH_FUND_LADDER, resolve_daily_limit

BUCKET_ORDER = BUCKET_CODES

BUCKET_META = DEFAULT_BUCKET_META

SIGNAL_BUCKETS = ("growth", "dividend", "gold")
BOND_BUCKETS = ("bond_long", "bond_short")

DIVIDEND_FUNDS = {
    "otc": "007466",
    "etf_primary": "563020",
    "etf_secondary": "512890",
}

BOND_FUNDS = {
    "long": "511010",
    "short": "110007",
}

LARGE_DIVIDEND_SPLIT_THRESHOLD = Decimal("10000")


@dataclass
class BucketSignal:
    code: str
    name: str
    color: str
    signal_type: str
    signal_value: float
    signal_display: str
    coefficient: float
    coefficient_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "color": self.color,
            "signal_type": self.signal_type,
            "signal_value": self.signal_value,
            "signal_display": self.signal_display,
            "coefficient": self.coefficient,
            "coefficient_label": self.coefficient_label,
        }


@dataclass
class DerivationLine:
    bucket: str
    label: str
    base_amount: float
    coefficient: float
    after_coefficient: float
    spillover_in: float
    spillover_out: float
    final_amount: float
    editable: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "label": self.label,
            "base_amount": self.base_amount,
            "coefficient": self.coefficient,
            "after_coefficient": self.after_coefficient,
            "spillover_in": self.spillover_in,
            "spillover_out": self.spillover_out,
            "final_amount": self.final_amount,
            "editable": self.editable,
            "notes": self.notes,
        }


@dataclass
class FundAllocation:
    fund_code: str
    fund_name: str
    planned_amount: float
    tier: int | None = None
    notes: str = ""
    daily_limit: float | None = None
    purchase_status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "planned_amount": self.planned_amount,
            "tier": self.tier,
            "notes": self.notes,
            "daily_limit": self.daily_limit,
            "purchase_status": self.purchase_status,
        }


@dataclass
class BucketExecutionPlan:
    bucket: str
    name: str
    color: str
    total_amount: float
    funds: list[FundAllocation] = field(default_factory=list)
    execution_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "name": self.name,
            "color": self.color,
            "total_amount": self.total_amount,
            "funds": [f.to_dict() for f in self.funds],
            "execution_notes": self.execution_notes,
        }


@dataclass
class BudgetReconciliation:
    """月预算与计划合计的对账说明。"""

    budget: float
    total_planned: float
    delta: float
    aligned: bool
    target_sum_pct: float
    base_allocated: float
    after_signals_total: float
    has_manual_overrides: bool
    override_adjustments: list[dict[str, Any]] = field(default_factory=list)
    spillover_moves: list[dict[str, Any]] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "total_planned": self.total_planned,
            "delta": self.delta,
            "aligned": self.aligned,
            "target_sum_pct": self.target_sum_pct,
            "base_allocated": self.base_allocated,
            "after_signals_total": self.after_signals_total,
            "has_manual_overrides": self.has_manual_overrides,
            "override_adjustments": self.override_adjustments,
            "spillover_moves": self.spillover_moves,
            "summary_lines": self.summary_lines,
            "steps": self.steps,
        }


@dataclass
class ExecutionPlan:
    month: str
    budget: float
    signals: list[BucketSignal]
    derivations: list[DerivationLine]
    bucket_executions: list[BucketExecutionPlan]
    total_planned: float
    budget_reconciliation: BudgetReconciliation | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "month": self.month,
            "budget": self.budget,
            "signals": [s.to_dict() for s in self.signals],
            "derivations": [d.to_dict() for d in self.derivations],
            "bucket_executions": [b.to_dict() for b in self.bucket_executions],
            "total_planned": self.total_planned,
        }
        if self.budget_reconciliation is not None:
            data["budget_reconciliation"] = self.budget_reconciliation.to_dict()
        return data


def _money(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def expand_legacy_coefficients(
    nasdaq_coef: float,
    dividend_coef: float,
    *,
    gold_coef: float = 1.0,
) -> dict[str, float]:
    return {
        "growth": nasdaq_coef,
        "dividend": dividend_coef,
        "gold": gold_coef,
        "bond_long": 1.0,
        "bond_short": 1.0,
    }


def build_signal_summary(
    *,
    buckets: list[BucketDef],
    pe_percentile: float,
    nasdaq_coef: float,
    nasdaq_label: str,
    dividend_yield: float,
    dividend_coef: float,
    dividend_label: str,
    gold_coef: float = 1.0,
    gold_label: str = "固定",
) -> list[BucketSignal]:
    signals: list[BucketSignal] = []
    labels = labels_map(buckets)
    colors = colors_map(buckets)

    for bucket in buckets:
        code = bucket.code
        meta = BUCKET_META[code]
        signal_bucket = meta["signal_bucket"]
        display_name = labels.get(code, bucket.name)
        color = colors.get(code, bucket.color)
        if signal_bucket == "growth":
            signals.append(
                BucketSignal(
                    code=code,
                    name=display_name,
                    color=color,
                    signal_type="pe_percentile",
                    signal_value=pe_percentile,
                    signal_display=f"{pe_percentile * 100:.0f}%",
                    coefficient=nasdaq_coef,
                    coefficient_label=nasdaq_label,
                )
            )
        elif signal_bucket == "dividend":
            signals.append(
                BucketSignal(
                    code=code,
                    name=display_name,
                    color=color,
                    signal_type="dividend_yield",
                    signal_value=dividend_yield,
                    signal_display=f"{dividend_yield * 100:.1f}%",
                    coefficient=dividend_coef,
                    coefficient_label=dividend_label,
                )
            )
        elif signal_bucket == "gold":
            signals.append(
                BucketSignal(
                    code=code,
                    name=display_name,
                    color=color,
                    signal_type="fixed",
                    signal_value=1.0,
                    signal_display="—",
                    coefficient=gold_coef,
                    coefficient_label=gold_label,
                )
            )
        else:
            signals.append(
                BucketSignal(
                    code=code,
                    name=display_name,
                    color=color,
                    signal_type="none",
                    signal_value=0.0,
                    signal_display="—",
                    coefficient=1.0,
                    coefficient_label="定额",
                )
            )
    return signals


def derive_bucket_amounts(
    budget: float,
    targets: dict[str, float],
    coefficients: dict[str, float],
    bucket_labels: dict[str, str] | None = None,
) -> list[DerivationLine]:
    """
    推导各桶金额，含溢出逻辑：
    - 成长桶系数 <1 的溢出优先给红利（红利系数 ≥1）
    - 红利也减速时，溢出给长债 → 短债
    """
    labels = bucket_labels or {c: BUCKET_META[c]["name"] for c in BUCKET_ORDER}
    lines: list[DerivationLine] = []
    spillover_pool = 0.0

    for code in SIGNAL_BUCKETS:
        base = budget * targets.get(code, 0.0)
        coef = coefficients.get(code, 1.0)
        after = base * coef
        out = max(base - after, 0.0)
        spillover_pool += out
        lines.append(
            DerivationLine(
                bucket=code,
                label=labels.get(code, code),
                base_amount=_money(base),
                coefficient=coef,
                after_coefficient=_money(after),
                spillover_in=0.0,
                spillover_out=_money(out),
                final_amount=_money(after),
                notes=f"预算×{targets.get(code, 0):.0%}×{coef}" if coef != 1 else f"预算×{targets.get(code, 0):.0%}",
            )
        )

    line_by_code = {line.bucket: line for line in lines}
    growth_line = line_by_code["growth"]
    dividend_line = line_by_code["dividend"]

    # 红利接收成长溢出
    growth_spill = growth_line.spillover_out
    dividend_in = 0.0
    if growth_spill > 0 and coefficients.get("dividend", 1.0) >= 1.0:
        dividend_in += growth_spill
        spillover_pool -= growth_spill

    dividend_line.spillover_in = _money(dividend_in)
    dividend_line.final_amount = _money(dividend_line.after_coefficient + dividend_in)
    if dividend_in > 0:
        dividend_line.notes += f"；接收成长溢出 ¥{dividend_in:,.0f}"

    # 红利系数 <1 时不接收成长溢出（溢出已在上方循环计入 spillover_pool）
    if coefficients.get("dividend", 1.0) < 1.0 and growth_spill > 0:
        dividend_line.notes += "；红利减速，成长溢出转债券"
    if coefficients.get("dividend", 1.0) < 1.0 and dividend_line.spillover_out > 0:
        dividend_line.notes += "；红利减速，溢出转债券"

    # 债券桶（无系数，接收剩余溢出）
    bond_targets_sum = sum(targets.get(c, 0.0) for c in BOND_BUCKETS)
    for code in BOND_BUCKETS:
        share = targets.get(code, 0.0)
        base = budget * share
        lines.append(
            DerivationLine(
                bucket=code,
                label=labels.get(code, code),
                base_amount=_money(base),
                coefficient=1.0,
                after_coefficient=_money(base),
                spillover_in=0.0,
                spillover_out=0.0,
                final_amount=_money(base),
                editable=False,
                notes=f"预算×{share:.0%}",
            )
        )

    line_by_code = {line.bucket: line for line in lines}
    if spillover_pool > 0 and bond_targets_sum > 0:
        long_line = line_by_code["bond_long"]
        short_line = line_by_code["bond_short"]
        long_share = targets.get("bond_long", 0.0) / bond_targets_sum
        short_share = targets.get("bond_short", 0.0) / bond_targets_sum
        long_in = spillover_pool * long_share
        short_in = spillover_pool * short_share
        long_line.spillover_in = _money(long_in)
        short_line.spillover_in = _money(short_in)
        long_line.final_amount = _money(long_line.after_coefficient + long_in)
        short_line.final_amount = _money(short_line.after_coefficient + short_in)
        long_line.notes += f"；接收溢出 ¥{long_in:,.0f}"
        short_line.notes += f"；接收溢出 ¥{short_in:,.0f}"

    return lines


def build_budget_reconciliation(
    *,
    budget: float,
    derivations: list[DerivationLine],
    targets: dict[str, float],
    coefficients: dict[str, float],
    final_by_bucket: dict[str, float],
    bucket_labels: dict[str, str] | None = None,
    amount_overrides: dict[str, float] | None = None,
) -> BudgetReconciliation:
    """生成月预算 vs 计划合计的推导与差额说明。"""
    labels = bucket_labels or {c: BUCKET_META[c]["name"] for c in BUCKET_ORDER}
    target_sum = _money(sum(targets.get(c, 0.0) for c in BUCKET_ORDER))
    base_allocated = _money(sum(d.base_amount for d in derivations))
    derived_finals = {d.bucket: d.final_amount for d in derivations}
    after_signals_total = _money(sum(derived_finals.values()))
    total_planned = _money(sum(final_by_bucket.values()))
    delta = _money(total_planned - budget)
    aligned = abs(delta) < 0.01

    spillover_moves: list[dict[str, Any]] = []
    line_by = {d.bucket: d for d in derivations}
    growth = line_by.get("growth")
    dividend = line_by.get("dividend")
    if growth and growth.spillover_out > 0 and dividend and dividend.spillover_in > 0:
        spillover_moves.append(
            {
                "from_bucket": "growth",
                "from_label": labels.get("growth", "成长"),
                "to_bucket": "dividend",
                "to_label": labels.get("dividend", "红利"),
                "amount": dividend.spillover_in,
            }
        )
    for code in BOND_BUCKETS:
        bond_line = line_by.get(code)
        if bond_line and bond_line.spillover_in > 0:
            spillover_moves.append(
                {
                    "from_bucket": "signal_buckets",
                    "from_label": "信号桶减速溢出",
                    "to_bucket": code,
                    "to_label": labels.get(code, code),
                    "amount": bond_line.spillover_in,
                }
            )

    override_adjustments: list[dict[str, Any]] = []
    if amount_overrides:
        for bucket, new_val in amount_overrides.items():
            if bucket not in derived_finals:
                continue
            old_val = derived_finals[bucket]
            new_money = _money(new_val)
            if abs(new_money - old_val) < 0.01:
                continue
            override_adjustments.append(
                {
                    "bucket": bucket,
                    "label": labels.get(bucket, bucket),
                    "from_amount": old_val,
                    "to_amount": new_money,
                    "delta": _money(new_money - old_val),
                }
            )

    summary_lines: list[str] = [
        f"月预算 ¥{budget:,.0f}；五桶目标占比合计 {target_sum:.0%}，基础切分 ¥{base_allocated:,.0f}。",
    ]
    if abs(target_sum - 1.0) > 0.001:
        summary_lines.append(
            f"目标占比合计为 {target_sum:.1%}（非 100%），基础切分与月预算相差 ¥{base_allocated - budget:,.0f}。"
        )

    slowed: list[str] = []
    for code in SIGNAL_BUCKETS:
        coef = coefficients.get(code, 1.0)
        if coef < 1.0:
            slowed.append(f"{labels.get(code, code)}×{coef}")
    if slowed:
        summary_lines.append(
            f"信号减速（{', '.join(slowed)}）减少的额度会在桶间再分配（优先红利，其次债券），不销毁现金。"
        )
    for move in spillover_moves:
        summary_lines.append(
            f"¥{move['amount']:,.0f}：{move['from_label']} → {move['to_label']}"
        )
    if override_adjustments:
        parts = [
            f"{a['label']} {a['from_amount']:,.0f}→{a['to_amount']:,.0f}"
            for a in override_adjustments
        ]
        summary_lines.append(f"手动调整各桶最终金额（{'; '.join(parts)}），计划合计随之变化。")
    elif aligned:
        summary_lines.append("未手动改桶金额时，信号与溢出仅在桶间搬家，计划合计应等于月预算。")

    if aligned:
        summary_lines.append(f"计划合计 ¥{total_planned:,.0f}，与月预算一致。")
    else:
        summary_lines.append(
            f"计划合计 ¥{total_planned:,.0f}，较月预算{'多' if delta > 0 else '少'} ¥{abs(delta):,.0f}。"
        )

    steps: list[dict[str, Any]] = [
        {"key": "budget", "label": "① 月预算（设置页）", "amount": budget},
        {
            "key": "base_split",
            "label": f"② 按目标占比切分（合计 {target_sum:.0%}）",
            "amount": base_allocated,
            "delta_from_budget": _money(base_allocated - budget),
        },
        {
            "key": "after_signals",
            "label": "③ 信号系数与溢出再分配后",
            "amount": after_signals_total,
            "delta_from_budget": _money(after_signals_total - budget),
        },
    ]
    if override_adjustments:
        steps.append(
            {
                "key": "after_overrides",
                "label": "④ 手动调整各桶后",
                "amount": total_planned,
                "delta_from_budget": delta,
            }
        )
    steps.append(
        {
            "key": "total_planned",
            "label": "计划合计（各桶最终金额之和）",
            "amount": total_planned,
            "delta_from_budget": delta,
        }
    )

    return BudgetReconciliation(
        budget=budget,
        total_planned=total_planned,
        delta=delta,
        aligned=aligned,
        target_sum_pct=target_sum,
        base_allocated=base_allocated,
        after_signals_total=after_signals_total,
        has_manual_overrides=bool(override_adjustments),
        override_adjustments=override_adjustments,
        spillover_moves=spillover_moves,
        summary_lines=summary_lines,
        steps=steps,
    )


def _fund_name_lookup(fund_code: str, fund_catalog: dict[str, str] | None) -> str:
    if fund_catalog and fund_code in fund_catalog:
        return fund_catalog[fund_code]
    return fund_code


def _ladder_for_preferred(
    preferred_fund_codes: list[str] | None,
    *,
    base_ladder: list[list[str]] | None = None,
) -> list[list[str]]:
    ladder_source = base_ladder or GROWTH_FUND_LADDER
    if not preferred_fund_codes:
        return ladder_source
    pref_order = {code: idx for idx, code in enumerate(preferred_fund_codes)}
    pref_set = set(preferred_fund_codes)
    ladder: list[list[str]] = []
    for tier in ladder_source:
        codes = sorted([c for c in tier if c in pref_set], key=lambda c: pref_order[c])
        if codes:
            ladder.append(codes)
    in_ladder = {c for tier in ladder_source for c in tier}
    extras = [c for c in preferred_fund_codes if c not in in_ladder]
    if extras:
        ladder.append(extras)
    return ladder if ladder else ladder_source


def plan_growth_bucket(
    amount: float,
    fund_catalog: dict[str, str] | None = None,
    purchase_limits: dict[str, float] | None = None,
    *,
    name: str | None = None,
    color: str | None = None,
    preferred_fund_codes: list[str] | None = None,
    growth_ladder: list[list[str]] | None = None,
) -> BucketExecutionPlan:
    """成长桶：按阶梯轮询多只纳指联接，日限购内填满后由下一只承接。"""
    limits = purchase_limits or {}
    remaining = Decimal(str(amount))
    funds: list[FundAllocation] = []
    notes: list[str] = []
    base_ladder = growth_ladder or GROWTH_FUND_LADDER
    ladder = _ladder_for_preferred(preferred_fund_codes, base_ladder=base_ladder)

    if remaining <= 0:
        return BucketExecutionPlan(
            bucket="growth",
            name=name or BUCKET_META["growth"]["name"],
            color=color or BUCKET_META["growth"]["color"],
            total_amount=0.0,
            execution_notes=["本月该桶无需投入"],
        )

    if preferred_fund_codes:
        notes.append(f"沿用上日定投组合（{len(preferred_fund_codes)} 只）")

    for tier_idx, tier in enumerate(ladder, start=1):
        for code in tier:
            if remaining <= 0:
                break
            fund_name = _fund_name_lookup(code, fund_catalog)
            daily_limit, status = resolve_daily_limit(code, limits)
            if status == "paused":
                notes.append(f"{fund_name}（{code}）暂停申购，由下一只纳指承接")
                continue
            if daily_limit is None:
                cap = remaining
                status = "active"
            else:
                cap = min(remaining, Decimal(str(daily_limit)))
            if cap <= 0:
                continue
            note = "优先联接" if tier_idx == 1 else "溢出阶梯"
            if daily_limit is not None and cap < remaining:
                note = f"日限 ¥{_money(daily_limit)}，凑额度"
            funds.append(
                FundAllocation(
                    fund_code=code,
                    fund_name=fund_name,
                    planned_amount=_money(cap),
                    tier=tier_idx,
                    notes=note,
                    daily_limit=daily_limit,
                    purchase_status=status,
                )
            )
            remaining -= cap
        if remaining <= 0:
            break

    if remaining > 0:
        notes.append(
            f"今日目标尚有 ¥{_money(remaining)} 无法由纳指阶梯承接，"
            "可明日继续或临时转入标普500备胎（050025/118002）"
        )

    return BucketExecutionPlan(
        bucket="growth",
        name=name or BUCKET_META["growth"]["name"],
        color=color or BUCKET_META["growth"]["color"],
        total_amount=amount,
        funds=funds,
        execution_notes=notes,
    )


def plan_dividend_bucket(
    amount: float,
    fund_catalog: dict[str, str] | None = None,
    *,
    name: str | None = None,
    color: str | None = None,
) -> BucketExecutionPlan:
    amt = Decimal(str(amount))
    funds: list[FundAllocation] = []
    notes: list[str] = []

    if amt <= 0:
        return BucketExecutionPlan(
            bucket="dividend",
            name=name or BUCKET_META["dividend"]["name"],
            color=color or BUCKET_META["dividend"]["color"],
            total_amount=0.0,
            execution_notes=["本月该桶无需投入"],
        )

    if amt >= LARGE_DIVIDEND_SPLIT_THRESHOLD:
        half = amt / 2
        funds.extend(
            [
                FundAllocation(
                    fund_code=DIVIDEND_FUNDS["etf_primary"],
                    fund_name=_fund_name_lookup(DIVIDEND_FUNDS["etf_primary"], fund_catalog),
                    planned_amount=_money(half),
                    notes="场内 50%",
                ),
                FundAllocation(
                    fund_code=DIVIDEND_FUNDS["otc"],
                    fund_name=_fund_name_lookup(DIVIDEND_FUNDS["otc"], fund_catalog),
                    planned_amount=_money(half),
                    notes="场外 50%",
                ),
            ]
        )
        notes.append("单笔≥1万：场内563020 + 场外007466 各半")
    else:
        funds.append(
            FundAllocation(
                fund_code=DIVIDEND_FUNDS["otc"],
                fund_name=_fund_name_lookup(DIVIDEND_FUNDS["otc"], fund_catalog),
                planned_amount=_money(amt),
                notes="单笔<1万：全部场外",
            )
        )

    return BucketExecutionPlan(
        bucket="dividend",
        name=name or BUCKET_META["dividend"]["name"],
        color=color or BUCKET_META["dividend"]["color"],
        total_amount=amount,
        funds=funds,
        execution_notes=notes,
    )


def plan_simple_bucket(
    bucket: str,
    amount: float,
    fund_code: str,
    fund_catalog: dict[str, str] | None = None,
    notes: list[str] | None = None,
    *,
    name: str | None = None,
    color: str | None = None,
) -> BucketExecutionPlan:
    meta = BUCKET_META[bucket]
    funds: list[FundAllocation] = []
    if amount > 0:
        funds.append(
            FundAllocation(
                fund_code=fund_code,
                fund_name=_fund_name_lookup(fund_code, fund_catalog),
                planned_amount=_money(amount),
            )
        )
    return BucketExecutionPlan(
        bucket=bucket,
        name=name or meta["name"],
        color=color or meta["color"],
        total_amount=amount,
        funds=funds,
        execution_notes=notes or [],
    )


def build_execution_plan(
    *,
    month: str,
    budget: float,
    buckets: list[BucketDef],
    pe_percentile: float,
    nasdaq_coef: float,
    nasdaq_label: str,
    dividend_yield: float,
    dividend_coef: float,
    dividend_label: str,
    gold_coef: float = 1.0,
    fund_catalog: dict[str, str] | None = None,
    purchase_limits: dict[str, float] | None = None,
    amount_overrides: dict[str, float] | None = None,
) -> ExecutionPlan:
    targets = targets_map(buckets)
    labels = labels_map(buckets)
    colors = colors_map(buckets)
    coefficients = expand_legacy_coefficients(nasdaq_coef, dividend_coef, gold_coef=gold_coef)

    signals = build_signal_summary(
        buckets=buckets,
        pe_percentile=pe_percentile,
        nasdaq_coef=nasdaq_coef,
        nasdaq_label=nasdaq_label,
        dividend_yield=dividend_yield,
        dividend_coef=dividend_coef,
        dividend_label=dividend_label,
        gold_coef=gold_coef,
    )
    derivations = derive_bucket_amounts(budget, targets, coefficients, bucket_labels=labels)

    derived_finals = {d.bucket: d.final_amount for d in derivations}
    final_by_bucket = dict(derived_finals)
    if amount_overrides:
        for bucket, value in amount_overrides.items():
            if bucket in final_by_bucket:
                final_by_bucket[bucket] = _money(value)

    reconciliation = build_budget_reconciliation(
        budget=budget,
        derivations=derivations,
        targets=targets,
        coefficients=coefficients,
        final_by_bucket=final_by_bucket,
        bucket_labels=labels,
        amount_overrides=amount_overrides,
    )

    bucket_executions = [
        plan_growth_bucket(
            final_by_bucket.get("growth", 0),
            fund_catalog,
            purchase_limits,
            name=labels.get("growth"),
            color=colors.get("growth"),
        ),
        plan_dividend_bucket(
            final_by_bucket.get("dividend", 0),
            fund_catalog,
            name=labels.get("dividend"),
            color=colors.get("dividend"),
        ),
        plan_simple_bucket(
            "gold",
            final_by_bucket.get("gold", 0),
            "518880",
            fund_catalog,
            ["黄金 ETF 占位，可按持仓调整"],
            name=labels.get("gold"),
            color=colors.get("gold"),
        ),
        plan_simple_bucket(
            "bond_long",
            final_by_bucket.get("bond_long", 0),
            BOND_FUNDS["long"],
            fund_catalog,
            name=labels.get("bond_long"),
            color=colors.get("bond_long"),
        ),
        plan_simple_bucket(
            "bond_short",
            final_by_bucket.get("bond_short", 0),
            BOND_FUNDS["short"],
            fund_catalog,
            name=labels.get("bond_short"),
            color=colors.get("bond_short"),
        ),
    ]

    total = _money(sum(final_by_bucket.values()))
    return ExecutionPlan(
        month=month,
        budget=budget,
        signals=signals,
        derivations=derivations,
        bucket_executions=bucket_executions,
        total_planned=total,
        budget_reconciliation=reconciliation,
    )
