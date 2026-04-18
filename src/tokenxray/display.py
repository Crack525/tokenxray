"""Formatting helpers for terminal display."""


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_cost(n: float) -> str:
    if n >= 100:
        return f"${n:.0f}"
    if n >= 1:
        return f"${n:.2f}"
    return f"${n:.3f}"


def bar(value: float, max_value: float, width: int = 30,
        char: str = "\u2588", empty: str = "\u2591") -> str:
    if max_value == 0:
        return empty * width
    filled = int(value / max_value * width)
    return char * filled + empty * (width - filled)


def duration_str(start, end) -> str:
    if not start or not end:
        return "unknown"
    delta = end - start
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{delta.total_seconds() / 60:.0f}min"
    return f"{hours:.1f}hrs"
