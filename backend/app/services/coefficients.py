from decimal import Decimal


def calculate_nasdaq_coefficient(pe_percentile: float) -> tuple[float, str]:
    if pe_percentile < 0.30:
        return 1.5, "低估"
    if pe_percentile < 0.70:
        return 1.0, "合理"
    if pe_percentile < 0.90:
        return 0.7, "偏高"
    return 0.5, "高估"


def calculate_dividend_coefficient(dividend_yield: float) -> tuple[float, str]:
    if dividend_yield >= 0.06:
        return 1.5, "高股息"
    if dividend_yield >= 0.05:
        return 1.0, "正常"
    if dividend_yield >= 0.04:
        return 0.7, "偏高"
    return 0.3, "暂停大额"
