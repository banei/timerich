def calculate_monthly_amounts(
    budget: float,
    target: dict[str, float],
    coefficients: dict[str, float],
) -> dict[str, float]:
    nasdaq_planned = budget * target["nasdaq"]
    nasdaq_actual = nasdaq_planned * coefficients["nasdaq"]
    nasdaq_spillover = nasdaq_planned - nasdaq_actual

    dividend_planned = budget * target["dividend"]
    dividend_actual = dividend_planned * coefficients["dividend"]
    dividend_spillover = dividend_planned - dividend_actual

    bond_planned = budget * target["bond"]

    if coefficients["dividend"] >= 1.0:
        dividend_actual += nasdaq_spillover
    else:
        bond_planned += nasdaq_spillover + dividend_spillover

    return {
        "nasdaq": nasdaq_actual,
        "dividend": dividend_actual,
        "bond": bond_planned,
        "total": nasdaq_actual + dividend_actual + bond_planned,
    }
