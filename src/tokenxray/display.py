"""Formatting helpers for terminal display."""
from __future__ import annotations


def display_project_name(project: str, max_len: int | None = None) -> str:
    """Format Claude project slugs into a shorter human-readable label."""
    display = project

    if project.startswith("-"):
        parts = [part for part in project.split("-") if part]
        if "Documents" in parts:
            parts = parts[parts.index("Documents") + 1:]
        elif parts[:1] == ["Users"] and len(parts) > 3:
            parts = parts[3:]
        if parts:
            display = "/".join(parts)

    if max_len is not None and len(display) > max_len:
        display = "..." + display[-(max_len - 3):]

    return display


def display_models(models_used, max_items: int = 3) -> str:
    """Format session models, skipping synthetic placeholders."""
    from tokenxray.config import get_model_label

    labels = []
    seen = set()

    for model in sorted(set(models_used)):
        if model == "<synthetic>":
            continue
        label = get_model_label(model)
        if label not in seen:
            labels.append(label)
            seen.add(label)

    if not labels:
        return "synthetic"

    return ", ".join(labels[:max_items])


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
    if hours > 24:
        return ">1d"
    return f"{hours:.1f}hrs"
