from datetime import date

from app.services.irr import calculate_irr


def test_irr_simple_investment():
    cashflows = [
        (date(2024, 1, 1), -1000),
        (date(2025, 1, 1), 1100),
    ]
    irr = calculate_irr(cashflows)
    assert 0.09 < irr < 0.11
