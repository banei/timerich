def calculate_percentile(current_value: float, historical_values: list[float]) -> float:
    if not historical_values:
        return 0.5
    arr = sorted(historical_values)
    count = sum(1 for v in arr if v <= current_value)
    return count / len(arr)
