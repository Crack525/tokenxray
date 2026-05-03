#!/usr/bin/env python3
"""TokenXRay status line — persistent session health in Claude Code UI.

Receives native Claude Code JSON via stdin (cost, context, model, rate limits).
Enriches with tokenxray data from live_session.json (turns, velocity).
When a trigger fires, replaces normal metrics with a focused action line.
Otherwise shows full metrics at the bottom of the terminal every turn.
"""

import json
import sys
from pathlib import Path

LIVE_SESSION = Path.home() / ".tokenxray" / "live_session.json"
CONFIG_FILE = Path.home() / ".tokenxray" / "config.json"


def color(text, code):
    return f"\033[{code}m{text}\033[0m"


def cost_color(cost):
    if cost < 1:
        return "32"
    elif cost < 5:
        return "33"
    elif cost < 15:
        return "33;1"
    else:
        return "31;1"


def ctx_color(pct):
    if pct < 50:
        return "32"
    elif pct < 75:
        return "33"
    elif pct < 90:
        return "33;1"
    else:
        return "31;1"


def velocity_indicator(cost, turns):
    if turns == 0:
        return ""
    cpt = cost / turns
    if cpt < 0.05:
        return "\u25b8"
    elif cpt < 0.15:
        return "\u25b8\u25b8"
    elif cpt < 0.40:
        return "\u25b8\u25b8\u25b8"
    else:
        return "\U0001f525"


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_hint(model_name, total_cost, ctx_pct, turns, rate_data):
    """Return (hint_text, ansi_code) for the highest-priority action, or None."""
    # P1: rate limit critical
    if rate_data:
        remaining = rate_data.get("requests_remaining")
        if remaining is not None and remaining < 3:
            return (
                f"\u26a0 {remaining} req left \u2014 pause or hit rate limit",
                "31;1",
            )

    # P2: context critical — checkpoint not guaranteed, tell user to run it
    if ctx_pct > 85:
        return (
            f"\U0001f525 ctx {ctx_pct:.0f}% \u2014 run: tokenxray --checkpoint \u00b7 new session",
            "31;1",
        )

    # P3: context warning — advisory, no emergency HOW needed
    if ctx_pct > 60:
        return (
            f"\u26a0 ctx {ctx_pct:.0f}% \u2014 new session soon \u00b7 saves ~60% tokens",
            "33;1",
        )

    # P4: Opus cost nudge
    if model_name and "opus" in model_name.lower() and total_cost > 3:
        return ("\u2192 /model sonnet \u2014 same task, 5x cheaper", "35")

    # P5: marathon session — auto-checkpoint saved at 60 turns, but may be stale; run fresh one
    if turns > 80 and total_cost > 2:
        return (
            "\u2192 run: tokenxray --checkpoint \u00b7 new session \u00b7 say: read checkpoint.md.loaded",
            "33",
        )

    return None


def main():
    try:
        native = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        native = {}

    cost_data = native.get("cost", {})
    ctx_data = native.get("context_window", {})
    model_data = native.get("model", {})
    rate_data = native.get("rate_limits", {})

    total_cost = cost_data.get("total_cost_usd", 0)
    ctx_pct = ctx_data.get("used_percentage", 0)
    model_name = model_data.get("display_name", "")
    duration_ms = cost_data.get("total_duration_ms", 0)

    turns = 0
    try:
        with open(LIVE_SESSION) as f:
            tx = json.load(f)
        turns = tx.get("turns", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    cfg = load_config()
    hints_enabled = cfg.get("statusline_hints", True)

    hint = (
        get_hint(model_name, total_cost, ctx_pct, turns, rate_data)
        if hints_enabled
        else None
    )

    if hint:
        # Triggered: minimal metrics + action
        hint_text, hint_code = hint
        parts = []
        short = model_name.split()[0] if model_name else ""
        if short:
            parts.append(color(short, "2"))
        parts.append(color(f"${total_cost:.2f}", cost_color(total_cost)))
        parts.append(color(f"ctx {ctx_pct:.0f}%", ctx_color(ctx_pct)))
        parts.append(color(hint_text, hint_code))
        print(" \u2502 ".join(parts))
        return

    # Normal: full metrics
    parts = []

    if model_name:
        short = model_name.split()[0] if model_name else ""
        if short:
            parts.append(color(short, "2"))

    cc = cost_color(total_cost)
    parts.append(color(f"${total_cost:.2f}", cc))

    vel = velocity_indicator(total_cost, turns)
    if vel:
        parts.append(color(vel, cc))

    if turns > 0:
        parts.append(color(f"T{turns}", "2"))
        parts.append(color(f"~${total_cost / turns:.2f}/t", "2"))

    cc2 = ctx_color(ctx_pct)
    parts.append(color(f"ctx {ctx_pct:.0f}%", cc2))
    if ctx_pct > 20 and ctx_pct < 95 and turns > 5:
        avg_per_turn = ctx_pct / turns if turns > 0 else 1.5
        remaining = int((95 - ctx_pct) / avg_per_turn) if avg_per_turn > 0 else 0
        if 0 < remaining < 200:
            parts.append(color(f"~{remaining} left", cc2))

    if duration_ms > 0:
        mins = duration_ms / 60000
        if mins >= 1:
            parts.append(color(f"{mins:.0f}m", "2"))

    if rate_data:
        remaining = rate_data.get("requests_remaining")
        if remaining is not None and remaining < 5:
            parts.append(color(f"\u26a0 {remaining} req left", "31;1"))

    print(" \u2502 ".join(parts))


if __name__ == "__main__":
    main()
