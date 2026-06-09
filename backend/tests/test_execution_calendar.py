from datetime import date

from app.services.execution_calendar import (
    build_action_steps,
    date_label,
    first_trading_day,
    last_trading_day,
    weekday_zh,
)


def test_date_label_includes_weekday():
    assert date_label(date(2026, 6, 9)) == "6月9日 周二"


def test_month_trading_bounds():
    assert first_trading_day(2026, 6) == date(2026, 6, 1)  # Monday
    assert last_trading_day(2026, 6) == date(2026, 6, 30)


def test_action_steps_have_dates():
    steps = build_action_steps("2026-06", date(2026, 6, 9))
    by_key = {s["key"]: s for s in steps}
    assert by_key["check_signals"]["date_label"] == "6月1日 周一"
    assert by_key["execute_dividend"]["date_label"] == "6月30日 周二"
    assert "周二" in by_key["execute_nasdaq"]["date_label"]
