"""从天天基金采集纳指100场外基金申购状态，输出可购名单。

用法:
  cd backend && python -m app.scripts.collect_nasdaq_funds
  cd backend && python -m app.scripts.collect_nasdaq_funds --save
"""

from __future__ import annotations

import argparse
import os
import sys

from app.services.fund_purchase import fetch_em_purchase_for_codes
from app.services.growth_limits import (
    NASDAQ100_FUND_META,
    RETIRED_NDX_CODES,
    SP500_BACKUP_META,
    all_growth_fund_codes,
)


def _strip_proxy_env() -> None:
    for key in list(os.environ):
        if "proxy" in key.lower():
            os.environ.pop(key, None)


def main() -> int:
    parser = argparse.ArgumentParser(description="采集纳指100场外基金申购状态")
    parser.add_argument("--save", action="store_true", help="写入 fund_quote.purchase_limit")
    parser.add_argument("--codes", nargs="*", help="指定代码，默认阶梯全部")
    args = parser.parse_args()

    _strip_proxy_env()
    codes = args.codes or all_growth_fund_codes()
    print(f"拉取 {len(codes)} 只基金…\n")

    try:
        rows = fetch_em_purchase_for_codes(codes)
    except Exception as exc:
        print(f"拉取失败: {exc}", file=sys.stderr)
        return 1

    by_code = {r.fund_code: r for r in rows}
    buyable: list[tuple[str, str, str]] = []
    paused: list[tuple[str, str, str]] = []

    print(f"{'代码':<8} {'日限购':>10} {'状态':<8} 名称 / 备注")
    print("-" * 80)
    for code in codes:
        info = by_code.get(code)
        meta = NASDAQ100_FUND_META.get(code) or SP500_BACKUP_META.get(code, {})
        name = info.fund_name if info else meta.get("name", code)
        note = meta.get("note", "")
        if info is None:
            line = f"{code:<8} {'—':>10} {'unknown':<8} {name}"
            print(line)
            continue
        if info.status == "paused":
            limit_s = "暂停"
            paused.append((code, name, note))
        elif info.daily_limit is None:
            limit_s = "不限"
            buyable.append((code, name, note))
        else:
            limit_s = f"¥{info.daily_limit:,.0f}"
            buyable.append((code, name, note))
        print(f"{code:<8} {limit_s:>10} {info.status:<8} {name}  ({note})")

    print(f"\n可参与轮询: {len(buyable)} 只，暂停/未知: {len(paused)} 只")
    if RETIRED_NDX_CODES:
        print(f"已退役代码（请勿使用）: {', '.join(RETIRED_NDX_CODES)}")

    if args.save:
        from app.database import SessionLocal
        from app.services.market_data import MarketDataService

        db = SessionLocal()
        try:
            saved = MarketDataService(db).fetch_fund_purchase_limits(codes, force=True)
            print(f"\n已写入数据库 {len(saved)} 条")
        finally:
            db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
