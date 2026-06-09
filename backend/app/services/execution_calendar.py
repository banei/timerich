"""定投执行日历：交易日、操作步骤日期与星期格式化。"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def month_weekdays(year: int, month: int) -> list[date]:
    days: list[date] = []
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, 1)
    end = date(year, month, last_day)
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5


def weekday_zh(d: date) -> str:
    return WEEKDAY_ZH[d.weekday()]


def date_label(d: date) -> str:
    return f"{d.month}月{d.day}日 {weekday_zh(d)}"


def date_info(d: date) -> dict[str, str]:
    return {
        "date": d.isoformat(),
        "weekday": weekday_zh(d),
        "date_label": date_label(d),
    }


def first_trading_day(year: int, month: int) -> date:
    days = month_weekdays(year, month)
    if not days:
        raise ValueError(f"no trading days in {year}-{month:02d}")
    return days[0]


def last_trading_day(year: int, month: int) -> date:
    days = month_weekdays(year, month)
    if not days:
        raise ValueError(f"no trading days in {year}-{month:02d}")
    return days[-1]


def next_trading_day_on_or_after(d: date) -> date:
    cur = d
    while not is_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def build_action_steps(month: str, as_of: date) -> list[dict[str, Any]]:
    """为执行清单各步骤生成建议操作日期（含星期）。"""
    year, mon = map(int, month.split("-"))
    month_start = first_trading_day(year, mon)
    month_end = last_trading_day(year, mon)
    today_action = next_trading_day_on_or_after(as_of)

    specs: list[tuple[str, str, date, str]] = [
        ("check_signals", "检查估值信号", month_start, "月初首个交易日，执行一次"),
        ("calc_amounts", "确认月金额分配", month_start, "月初首个交易日，执行一次"),
        ("execute_nasdaq", "成长档日定投", today_action, "每个交易日执行"),
        ("check_premium", "检查 ETF 溢价", month_end, "红利/ETF 执行日当天"),
        ("execute_dividend", "执行红利档", month_end, "月末最后交易日"),
        ("execute_bond", "执行债券档", month_end, "月末最后交易日"),
        ("record", "录入交易记录", today_action, "每次买入当日录入"),
    ]
    steps: list[dict[str, Any]] = []
    for key, title, action_date, hint in specs:
        info = date_info(action_date)
        steps.append(
            {
                "key": key,
                "title": title,
                "hint": hint,
                "recurrence": "daily" if key in {"execute_nasdaq", "record"} else "monthly",
                **info,
            }
        )
    return steps
