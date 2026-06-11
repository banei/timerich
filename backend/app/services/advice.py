"""根据估值信号与配比偏离生成可执行操作建议。"""

from __future__ import annotations


def build_nasdaq_advice(pe_percentile: float, coefficient: float, label: str) -> dict:
    pct = round(pe_percentile * 100)
    actions: list[str] = []

    if pe_percentile < 0.30:
        actions = [
            f"纳指 PE 分位 {pct}%（{label}），下月系数 ×{coefficient}，可加大纳指档投入。",
            "优先按溢出阶梯买入可申购的纳指联接（如 270042、000834、040046 等）。",
            "若场内 ETF 溢价 ≤0.5%，可适量配置 513100 等场内标的。",
        ]
        tone = "aggressive"
    elif pe_percentile < 0.70:
        actions = [
            f"纳指 PE 分位 {pct}%（{label}），下月系数 ×{coefficient}，按目标权重正常定投。",
            "无需刻意加减仓，维持纪律即可。",
        ]
        tone = "neutral"
    elif pe_percentile < 0.90:
        actions = [
            f"纳指 PE 分位 {pct}%（{label}），下月系数 ×{coefficient}，纳指档适当减速。",
            "纳指档未满部分按策略溢出至红利低波或债券档。",
            "执行前检查限购公告，限购则跳同列表后续基金。",
        ]
        tone = "caution"
    else:
        actions = [
            f"纳指 PE 分位 {pct}%（{label}），下月系数 ×{coefficient}，纳指档明显减速。",
            "溢出资金优先补红利低波；红利也偏高时再转债券档。",
            "溢价 >2% 不碰场内纳指 ETF；>5% 可考虑反向套利（进阶）。",
            "仍维持纪律定投，系数不为 0，不要因高估完全停投。",
        ]
        tone = "caution"

    return {
        "headline": f"纳指100 · {label}（分位 {pct}%，系数 ×{coefficient}）",
        "actions": actions,
        "tone": tone,
    }


def build_dividend_advice(dividend_yield: float, coefficient: float, label: str) -> dict:
    yield_pct = round(dividend_yield * 100, 1)
    actions: list[str] = []

    if dividend_yield >= 0.06:
        actions = [
            f"H30269 股息率 {yield_pct}%（{label}），下月系数 ×{coefficient}，可加大红利档买入。",
            "单笔 ≥1 万：50% 场内 563020 + 50% 场外 007466。",
            "单笔 <1 万：全部走场外 007466，场内用限价单挂均价附近。",
        ]
        tone = "aggressive"
    elif dividend_yield >= 0.05:
        actions = [
            f"H30269 股息率 {yield_pct}%（{label}），下月系数 ×{coefficient}，红利档正常定投。",
            "按目标权重执行，无需额外加减仓。",
        ]
        tone = "neutral"
    elif dividend_yield >= 0.04:
        actions = [
            f"H30269 股息率 {yield_pct}%（{label}），下月系数 ×{coefficient}，红利档适当减速。",
            "可接收纳指档溢出资金，但自身不再加大投入。",
        ]
        tone = "caution"
    else:
        actions = [
            f"H30269 股息率 {yield_pct}%（{label}），下月系数 ×{coefficient}，暂停红利档大额买入。",
            "仅维持最小纪律投入；溢出资金转债券档 511010。",
        ]
        tone = "caution"

    return {
        "headline": f"红利低波 · {label}（股息率 {yield_pct}%，系数 ×{coefficient}）",
        "actions": actions,
        "tone": tone,
    }


def build_spillover_advice(
    nasdaq_coef: float,
    dividend_coef: float,
    amounts: dict[str, float],
) -> dict:
    actions: list[str] = []
    nasdaq = amounts.get("nasdaq", 0)
    dividend = amounts.get("dividend", 0)
    bond = amounts.get("bond", 0)

    actions.append(
        f"下月计划：纳指档 ¥{nasdaq:,.0f} · 红利档 ¥{dividend:,.0f} · 债券档 ¥{bond:,.0f}。"
    )

    if nasdaq_coef < 1.0:
        if dividend_coef >= 1.0:
            actions.append("纳指系数 <1，未满的纳指预算将溢出至红利低波档。")
        else:
            actions.append("纳指与红利系数均偏低，溢出资金优先进入债券档。")
    elif dividend_coef < 1.0:
        actions.append("红利系数偏低，除纪律性投入外，新增资金可向债券档倾斜。")

    actions.append("系数在月末确定后整月生效，月内不因估值波动临时调整。")
    actions.append("执行日：每月 10 日（遇节假日顺延），最佳时段 14:30–14:55。")

    return {"headline": "本月定投执行建议", "actions": actions, "tone": "neutral"}


def build_allocation_advice(
    deviations: dict[str, float],
    threshold_passive: float = 0.05,
    threshold_active: float = 0.10,
) -> dict:
    if not deviations:
        return {
            "headline": "配比偏离 · 暂无持仓数据",
            "actions": ["录入交易后，系统将给出再平衡与倾斜建议。"],
            "tone": "neutral",
            "recommendation": "no_data",
        }

    labels = {"nasdaq": "纳指", "dividend": "红利", "bond": "债券"}
    max_dev = max(abs(v) for v in deviations.values())
    over = {k: v for k, v in deviations.items() if v > threshold_passive}
    under = {k: v for k, v in deviations.items() if v < -threshold_passive}

    actions: list[str] = []
    for key, dev in deviations.items():
        name = labels.get(key, key)
        pct = round(dev * 100, 1)
        sign = "+" if dev > 0 else ""
        actions.append(f"{name}档偏离目标 {sign}{pct}%。")

    if max_dev <= threshold_passive:
        recommendation = "no_action"
        actions.append("偏离均在 ±5% 以内：不操作，继续正常定投。")
        tone = "neutral"
        headline = "配比偏离 · 正常"
    elif max_dev <= threshold_active:
        recommendation = "passive_via_new_investment"
        under_names = "、".join(labels[k] for k in under)
        actions.append(f"有档位偏离 ±5%–±10%：不卖出，下月新投入向 {under_names or '低配档'} 倾斜。")
        tone = "caution"
        headline = "配比偏离 · 被动调整"
    else:
        recommendation = "active_rebalance"
        over_names = "、".join(labels[k] for k in over)
        under_names = "、".join(labels[k] for k in under)
        actions.append(f"有档位偏离 >±10%：建议主动再平衡，减 {over_names}、增 {under_names}。")
        actions.append("可在「再平衡」页评估具体订单（二期功能）或按年度 SOP 手动执行。")
        tone = "caution"
        headline = "配比偏离 · 需再平衡"

    return {
        "headline": headline,
        "actions": actions,
        "tone": tone,
        "recommendation": recommendation,
        "max_deviation": max_dev,
    }


def build_overall_advice(
    nasdaq: dict,
    dividend: dict,
    spillover: dict,
    allocation: dict,
) -> dict:
    tones = [nasdaq["tone"], dividend["tone"], allocation["tone"]]
    if "caution" in tones:
        priority = "caution"
        headline = "整体建议：估值或配比提示谨慎，按系数减速、倾斜低配档"
    elif tones.count("aggressive") >= 2:
        priority = "aggressive"
        headline = "整体建议：估值偏友好，可适度加大权益档投入"
    else:
        priority = "neutral"
        headline = "整体建议：按目标配比与系数正常执行月度定投"

    actions = [
        nasdaq["actions"][0],
        dividend["actions"][0],
        *spillover["actions"][:2],
    ]
    if allocation.get("recommendation") not in {"no_data", "no_action"}:
        actions.append(allocation["actions"][-1])

    return {"headline": headline, "actions": actions, "priority": priority}
