"""探测纳指联接当日可买额度（东方财富 fund_purchase_em）。

用法:
  cd backend && .venv/bin/python -m app.scripts.probe_purchase_limits
  cd backend && .venv/bin/python -m app.scripts.probe_purchase_limits --save
"""

from __future__ import annotations

import argparse
import sys

from app.services.fund_purchase import fetch_em_purchase_for_codes
from app.services.growth_limits import all_growth_fund_codes


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取纳指阶梯基金日限购")
    parser.add_argument("--save", action="store_true", help="写入数据库 fund_quote.purchase_limit")
    parser.add_argument("--codes", nargs="*", help="指定基金代码，默认成长档阶梯全部")
    args = parser.parse_args()

    codes = args.codes or all_growth_fund_codes()
    print(f"正在从天天基金拉取 {len(codes)} 只基金申购状态…\n")

    try:
        rows = fetch_em_purchase_for_codes(codes)
    except Exception as exc:
        print(f"拉取失败: {exc}", file=sys.stderr)
        return 1

    print(f"{'代码':<8} {'日限购':>10} {'状态':<8} {'申购状态':<10} 基金名称")
    print("-" * 72)
    for info in rows:
        limit_s = "不限" if info.daily_limit is None and info.status == "active" else (
            "暂停" if info.status == "paused" else f"¥{info.daily_limit:,.0f}"
        )
        print(
            f"{info.fund_code:<8} {limit_s:>10} {info.status:<8} {info.subscribe_status:<10} {info.fund_name}"
        )

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
